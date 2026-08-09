"""
NorthPeak — self-serve BI dashboard generator.

Queries the governed marts and emits a single self-contained HTML file
(dashboards/northpeak_dashboard.html) with KPI cards and interactive charts.
No server required — open the file in any browser.

Every number comes from the marts, so the dashboard inherits the governed metric
definitions automatically (docs/metric_definitions.md). Regenerate after each daily
refresh to keep it current.

Usage:
    python dashboards/build_dashboard.py --db ./warehouse/northpeak.duckdb \
        --out dashboards/northpeak_dashboard.html
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import duckdb


def fetch(con, sql):
    cur = con.execute(sql)
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def one(con, sql):
    return con.execute(sql).fetchone()


def gather(db_path: str) -> dict:
    con = duckdb.connect(db_path, read_only=True)

    # headline KPIs (full history), straight from the governed marts
    net_rev, net_orders = one(con,
        "select sum(net_revenue), sum(net_orders) from main_marts.fct_daily_kpis")
    gmv, recognized, refunds = one(con,
        "select sum(gmv), sum(recognized_revenue), sum(refunds) from main_marts.fct_daily_kpis")
    gross = one(con, "select sum(gross_revenue) from main_marts.fct_daily_kpis")[0]
    net_margin = one(con, "select sum(net_margin) from main_marts.fct_daily_kpis")[0]
    purchasers = one(con,
        "select count(*) from main_marts.dim_customers where lifetime_net_orders >= 1")[0]
    repeat = one(con,
        "select count(*) from main_marts.dim_customers where is_repeat_customer")[0]
    dmin, dmax = one(con, "select min(order_date), max(order_date) from main_marts.fct_daily_kpis")

    kpis = {
        "net_revenue": net_rev,
        "gmv": gmv,
        "recognized_revenue": recognized,
        "refunds": refunds,
        "net_orders": net_orders,
        "aov": (net_rev / net_orders) if net_orders else 0,
        "purchasers": purchasers,
        "repeat_rate": (repeat / purchasers) if purchasers else 0,
        "refund_rate": (refunds / gross) if gross else 0,
        "net_margin_rate": (net_margin / net_rev) if net_rev else 0,
        "date_min": str(dmin),
        "date_max": str(dmax),
    }

    monthly = fetch(con, """
        select strftime(order_date, '%Y-%m') as month,
               round(sum(net_revenue), 0)        as net_revenue,
               round(sum(recognized_revenue), 0) as recognized_revenue,
               sum(net_orders)                   as net_orders
        from main_marts.fct_daily_kpis
        group by 1 order by 1
    """)

    by_category = fetch(con, """
        select category, round(sum(net_revenue), 0) as net_revenue
        from main_marts.dim_products
        where category is not null
        group by 1 order by 2 desc limit 12
    """)

    by_department = fetch(con, """
        select department, round(sum(net_revenue), 0) as net_revenue
        from main_marts.dim_products
        where department is not null group by 1 order by 2 desc
    """)

    by_traffic = fetch(con, """
        select traffic_source, round(sum(lifetime_net_revenue), 0) as net_revenue
        from main_marts.dim_customers
        where traffic_source is not null group by 1 order by 2 desc
    """)

    top_brands = fetch(con, """
        select brand, round(sum(net_revenue), 0) as net_revenue
        from main_marts.dim_products
        where brand is not null group by 1 order by 2 desc limit 10
    """)

    by_status = fetch(con, """
        select status, count(*) as orders
        from main_marts.fct_orders group by 1 order by 2 desc
    """)

    con.close()
    return {
        "kpis": kpis, "monthly": monthly, "by_category": by_category,
        "by_department": by_department, "by_traffic": by_traffic,
        "top_brands": top_brands, "by_status": by_status,
    }


def render(data: dict) -> str:
    payload = json.dumps(data)
    return HTML_TEMPLATE.replace("__DATA__", payload)


HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>NorthPeak — Analytics Dashboard</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>
<style>
  :root{
    --pine:#1f4d3a; --pine2:#2e6f52; --sky:#3d7ea6; --sun:#e8a33d;
    --ink:#1c2530; --muted:#6b7785; --line:#e5e9ee; --bg:#f6f8f9; --card:#ffffff;
  }
  *{box-sizing:border-box}
  body{margin:0;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
       background:var(--bg);color:var(--ink)}
  header{background:linear-gradient(135deg,var(--pine),var(--pine2));color:#fff;padding:28px 32px}
  header h1{margin:0;font-size:22px;letter-spacing:.2px}
  header p{margin:6px 0 0;color:#cfe3d8;font-size:13px}
  .wrap{max-width:1200px;margin:0 auto;padding:24px 32px 56px}
  .kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:14px;margin-bottom:8px}
  .kpi{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px 18px}
  .kpi .label{font-size:12px;color:var(--muted);text-transform:uppercase;letter-spacing:.4px}
  .kpi .value{font-size:26px;font-weight:650;margin-top:6px}
  .kpi .sub{font-size:12px;color:var(--muted);margin-top:2px}
  .grid{display:grid;grid-template-columns:2fr 1fr;gap:16px;margin-top:16px}
  .grid3{display:grid;grid-template-columns:1fr 1fr 1fr;gap:16px;margin-top:16px}
  .panel{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px 18px}
  .panel h3{margin:0 0 4px;font-size:14px}
  .panel .hint{font-size:12px;color:var(--muted);margin:0 0 12px}
  .toolbar{display:flex;align-items:center;gap:10px;margin-top:18px}
  select{padding:7px 10px;border:1px solid var(--line);border-radius:8px;background:#fff;font-size:13px}
  canvas{max-height:300px}
  .foot{margin-top:26px;font-size:12px;color:var(--muted);line-height:1.6}
  @media(max-width:860px){.grid,.grid3{grid-template-columns:1fr}}
</style>
</head>
<body>
<header>
  <h1>NorthPeak — Analytics Dashboard</h1>
  <p id="subtitle"></p>
</header>
<div class="wrap">
  <div class="kpis" id="kpis"></div>

  <div class="toolbar">
    <label for="yearSel" style="font-size:13px;color:var(--muted)">Revenue trend — year:</label>
    <select id="yearSel"></select>
  </div>

  <div class="grid">
    <div class="panel">
      <h3>Monthly revenue</h3>
      <p class="hint">Net revenue vs finance-recognized revenue. Gap = unshipped "Processing" orders.</p>
      <canvas id="trend"></canvas>
    </div>
    <div class="panel">
      <h3>Orders by status</h3>
      <p class="hint">Order lifecycle distribution.</p>
      <canvas id="status"></canvas>
    </div>
  </div>

  <div class="grid3">
    <div class="panel"><h3>Net revenue by category</h3><p class="hint">Top categories.</p><canvas id="category"></canvas></div>
    <div class="panel"><h3>Top brands</h3><p class="hint">By net revenue.</p><canvas id="brands"></canvas></div>
    <div class="panel"><h3>Revenue by traffic source</h3><p class="hint">Customer acquisition channel.</p><canvas id="traffic"></canvas></div>
  </div>

  <p class="foot" id="foot"></p>
</div>

<script>
const D = __DATA__;
const fmtUSD = n => "$" + Math.round(n).toLocaleString();
const fmtUSDk = n => "$" + (n/1e6).toFixed(2) + "M";
const fmtPct = n => (n*100).toFixed(1) + "%";
const PINE="#1f4d3a", PINE2="#2e6f52", SKY="#3d7ea6", SUN="#e8a33d", GREY="#c3ccd4";

// KPI cards
const k = D.kpis;
const cards = [
  ["Net revenue", fmtUSDk(k.net_revenue), "governed headline"],
  ["Recognized (finance)", fmtUSDk(k.recognized_revenue), "shipped/complete only"],
  ["GMV (demand)", fmtUSDk(k.gmv), "all items ordered"],
  ["Net orders", k.net_orders.toLocaleString(), "excl. cancelled"],
  ["AOV", fmtUSD(k.aov), "net rev / net orders"],
  ["Purchasing customers", k.purchasers.toLocaleString(), fmtPct(k.repeat_rate)+" repeat"],
  ["Refund rate", fmtPct(k.refund_rate), "returns / gross"],
  ["Net margin", fmtPct(k.net_margin_rate), "of net revenue"],
];
document.getElementById("kpis").innerHTML = cards.map(c =>
  `<div class="kpi"><div class="label">${c[0]}</div><div class="value">${c[1]}</div><div class="sub">${c[2]}</div></div>`
).join("");
document.getElementById("subtitle").textContent =
  `Self-serve KPIs from the governed marts · ${k.date_min} → ${k.date_max}`;
document.getElementById("foot").innerHTML =
  "Generated from <code>fct_daily_kpis</code>, <code>dim_products</code>, <code>dim_customers</code>, <code>fct_orders</code>. "+
  "Every metric resolves to <code>docs/metric_definitions.md</code>. Regenerate after each daily refresh.";

Chart.defaults.font.family = getComputedStyle(document.body).fontFamily;
Chart.defaults.plugins.legend.labels.boxWidth = 12;

// Year filter for trend
const years = [...new Set(D.monthly.map(m => m.month.slice(0,4)))];
const sel = document.getElementById("yearSel");
sel.innerHTML = `<option value="ALL">All years</option>` + years.map(y=>`<option value="${y}">${y}</option>`).join("");

let trendChart;
function drawTrend(year){
  const rows = year==="ALL" ? D.monthly : D.monthly.filter(m=>m.month.startsWith(year));
  const labels = rows.map(r=>r.month);
  if(trendChart) trendChart.destroy();
  trendChart = new Chart(document.getElementById("trend"), {
    type:"line",
    data:{labels, datasets:[
      {label:"Net revenue", data:rows.map(r=>r.net_revenue), borderColor:PINE, backgroundColor:"rgba(31,77,58,.08)", fill:true, tension:.3},
      {label:"Recognized", data:rows.map(r=>r.recognized_revenue), borderColor:SUN, backgroundColor:"transparent", borderDash:[5,4], tension:.3},
    ]},
    options:{responsive:true, plugins:{tooltip:{callbacks:{label:c=>c.dataset.label+": "+fmtUSD(c.parsed.y)}}},
      scales:{y:{ticks:{callback:v=>"$"+(v/1000)+"k"}}}}
  });
}
drawTrend("ALL");
sel.addEventListener("change", e=>drawTrend(e.target.value));

// Orders by status (doughnut)
new Chart(document.getElementById("status"), {
  type:"doughnut",
  data:{labels:D.by_status.map(r=>r.status),
    datasets:[{data:D.by_status.map(r=>r.orders),
      backgroundColor:[PINE,PINE2,SKY,SUN,GREY]}]},
  options:{plugins:{legend:{position:"bottom"}}}
});

function bar(id, rows, labelKey, valKey, color, horizontal){
  new Chart(document.getElementById(id), {
    type:"bar",
    data:{labels:rows.map(r=>r[labelKey]),
      datasets:[{data:rows.map(r=>r[valKey]), backgroundColor:color}]},
    options:{indexAxis:horizontal?"y":"x", plugins:{legend:{display:false},
      tooltip:{callbacks:{label:c=>fmtUSD(c.parsed[horizontal?"x":"y"])}}},
      scales:{[horizontal?"x":"y"]:{ticks:{callback:v=>"$"+(v/1000)+"k"}}}}
  });
}
bar("category", D.by_category, "category", "net_revenue", PINE2, true);
bar("brands", D.top_brands, "brand", "net_revenue", SKY, true);
bar("traffic", D.by_traffic, "traffic_source", "net_revenue", SUN, false);
</script>
</body>
</html>
"""


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="./warehouse/northpeak.duckdb")
    ap.add_argument("--out", default="dashboards/northpeak_dashboard.html")
    args = ap.parse_args(argv)
    data = gather(args.db)
    html = render(data)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    print(f"[dashboard] wrote {out}  ({len(html):,} bytes)")
    print(f"[dashboard] net_revenue={data['kpis']['net_revenue']:,.0f}  "
          f"months={len(data['monthly'])}  categories={len(data['by_category'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
