"""
NorthPeak — channel-agnostic alerting.

send_alert() posts a formatted message to Slack if SLACK_WEBHOOK_URL is set,
otherwise falls back to console/log. This keeps the pipeline code channel-neutral:
wiring up real Slack later is a matter of setting one env var, no code change.

Env:
    SLACK_WEBHOOK_URL   Slack incoming-webhook URL (optional). If unset -> console.
    NORTHPEAK_ENV       label shown in the alert (default: "local").

Design notes:
  - Network failure to Slack NEVER raises: an alerting problem must not itself crash
    or mask the pipeline. We try Slack, and on any error fall back to console and
    return a status dict describing what happened.
  - Short timeout so a hung Slack endpoint can't stall the run.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.request

SEVERITY_EMOJI = {"error": ":red_circle:", "warn": ":large_yellow_circle:", "info": ":large_blue_circle:"}


def _format_slack(subject: str, body: str, severity: str, fields: dict) -> dict:
    env = os.environ.get("NORTHPEAK_ENV", "local")
    emoji = SEVERITY_EMOJI.get(severity, ":white_circle:")
    lines = [f"{emoji} *NorthPeak pipeline — {severity.upper()}*  `[{env}]`",
             f"*{subject}*", body]
    if fields:
        lines += [f"• *{k}:* {v}" for k, v in fields.items()]
    return {"text": "\n".join(lines)}


def _format_console(subject: str, body: str, severity: str, fields: dict) -> str:
    env = os.environ.get("NORTHPEAK_ENV", "local")
    bar = "=" * 64
    out = [bar, f"[ALERT:{severity.upper()}] NorthPeak pipeline [{env}]",
           f"  {subject}", f"  {body}"]
    out += [f"  - {k}: {v}" for k, v in fields.items()]
    out.append(bar)
    return "\n".join(out)


def send_alert(subject: str, body: str = "", severity: str = "error", **fields) -> dict:
    """Send an alert. Returns {'channel': 'slack'|'console', 'ok': bool}."""
    webhook = os.environ.get("SLACK_WEBHOOK_URL")
    if webhook:
        try:
            payload = json.dumps(_format_slack(subject, body, severity, fields)).encode()
            req = urllib.request.Request(
                webhook, data=payload, headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                ok = 200 <= resp.status < 300
            if ok:
                return {"channel": "slack", "ok": True}
            # non-2xx -> fall through to console
            print(f"[alerts] Slack returned {resp.status}; falling back to console", file=sys.stderr)
        except Exception as e:  # network/timeout/etc — never let alerting crash the run
            print(f"[alerts] Slack post failed ({e}); falling back to console", file=sys.stderr)

    print(_format_console(subject, body, severity, fields), file=sys.stderr)
    return {"channel": "console", "ok": True}


if __name__ == "__main__":
    # manual smoke test: `python orchestration/alerts.py`
    send_alert(
        "Pipeline step failed: dbt_models",
        "dbt build exited non-zero during the 06:00 UTC daily refresh.",
        severity="error",
        run_id="demo-123", step="dbt_models", sla="07:00 UTC",
    )
