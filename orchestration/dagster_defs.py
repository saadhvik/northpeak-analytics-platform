"""
NorthPeak — Dagster orchestration.

Models the daily pipeline as three dependent software-defined assets:

    raw_sources  ──►  dbt_models  ──►  data_quality
    (EL: CSV→raw)     (dbt build)      (Great Expectations gate)

Each asset shells out to the same scripts a human would run, checks the return
code, and raises on failure — so Dagster marks the step failed, stops the
downstream steps, and (Phase 6) fires an alert. A daily schedule runs the whole
job before the SLA deadline.

Run locally:
    dagster dev -f orchestration/dagster_defs.py        # UI at localhost:3000
    dagster asset materialize -f orchestration/dagster_defs.py --select '*'   # headless

Config via env vars (sensible repo-relative defaults):
    NORTHPEAK_HOME        repo root            (default: parent of this file's dir)
    NORTHPEAK_DB          duckdb path          (default: $HOME/warehouse/northpeak.duckdb)
    NORTHPEAK_SOURCE_DIR  raw CSV directory    (default: $HOME/raw_data)
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from dagster import (
    Definitions,
    HookContext,
    ScheduleDefinition,
    asset,
    define_asset_job,
    failure_hook,
)

# make sibling module importable whether loaded as a file or a package
sys.path.insert(0, str(Path(__file__).resolve().parent))
from alerts import send_alert  # noqa: E402

# --- resolve paths ---------------------------------------------------------------
HOME = Path(os.environ.get("NORTHPEAK_HOME", Path(__file__).resolve().parents[1]))
DB = os.environ.get("NORTHPEAK_DB", str(HOME / "warehouse" / "northpeak.duckdb"))
SOURCE_DIR = os.environ.get("NORTHPEAK_SOURCE_DIR", str(HOME / "raw_data"))
DBT_DIR = HOME / "dbt_project"


def _run(context, cmd: list[str], cwd: Path, extra_env: dict | None = None):
    """Run a subprocess, stream output to the Dagster log, raise on non-zero exit."""
    env = {**os.environ, **(extra_env or {})}
    context.log.info(f"$ {' '.join(cmd)}  (cwd={cwd})")
    proc = subprocess.run(cmd, cwd=str(cwd), env=env, capture_output=True, text=True)
    if proc.stdout:
        context.log.info(proc.stdout[-4000:])
    if proc.returncode != 0:
        context.log.error(proc.stderr[-4000:])
        raise Exception(f"step failed (exit {proc.returncode}): {' '.join(cmd)}")
    return proc.stdout


# --- assets ----------------------------------------------------------------------
@asset(
    group_name="northpeak",
    description="Extract & Load: land the 7 TheLook CSVs into DuckDB raw schema.",
)
def raw_sources(context) -> None:
    _run(context, ["python", "ingestion/load_sources.py",
                   "--source-dir", SOURCE_DIR, "--db", DB, "--strict"], cwd=HOME)


@asset(
    deps=[raw_sources],
    group_name="northpeak",
    description="Transform: dbt build (staging -> intermediate -> marts) + dbt tests.",
)
def dbt_models(context) -> None:
    _run(context, ["dbt", "build", "--profiles-dir", "."], cwd=DBT_DIR,
         extra_env={"NORTHPEAK_DUCKDB": DB})


@asset(
    deps=[dbt_models],
    group_name="northpeak",
    description="Quality gate: Great Expectations suite over the marts. Fails the run on any violation.",
)
def data_quality(context) -> None:
    _run(context, ["python", "quality/run_quality_checks.py", "--db", DB], cwd=HOME)


# --- alerting: fire on any step failure ------------------------------------------
@failure_hook
def alert_on_failure(context: HookContext) -> None:
    """Runs whenever a step in the job fails. Sends a channel-agnostic alert
    (Slack if SLACK_WEBHOOK_URL is set, else console). See orchestration/alerts.py."""
    err = context.op_exception
    send_alert(
        subject=f"Pipeline step failed: {context.op.name}",
        body=f"{type(err).__name__}: {err}" if err else "Step failed.",
        severity="error",
        run_id=context.run_id,
        step=context.op.name,
        sla="07:00 UTC daily refresh",
    )


# --- job + daily schedule --------------------------------------------------------
daily_refresh_job = define_asset_job(
    name="daily_refresh",
    selection="*",
    description="Full daily refresh: ingest -> dbt build -> quality gate.",
    hooks={alert_on_failure},
)

# SLA: KPI data refreshes by 07:00. Run at 06:00 to leave headroom for retries.
daily_schedule = ScheduleDefinition(
    name="daily_refresh_6am",
    job=daily_refresh_job,
    cron_schedule="0 6 * * *",
    execution_timezone="UTC",
)

defs = Definitions(
    assets=[raw_sources, dbt_models, data_quality],
    jobs=[daily_refresh_job],
    schedules=[daily_schedule],
)
