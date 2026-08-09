# Phase 6 — Alerting & SLA

*Making failure loud, and writing down the promise the business runs on.*

## What we set out to do

A pipeline that fails silently is worse than no pipeline — people keep trusting stale
numbers. This phase makes any failure page someone, and turns the implicit "data
should be fresh" into an explicit, measurable SLA with a runbook for when it breaks.

## Decisions & rationale

**Channel-agnostic alerting (`orchestration/alerts.py`).** `send_alert()` posts to
Slack if `SLACK_WEBHOOK_URL` is set, otherwise logs to console — same call site either
way. Wiring real Slack later is one env var, no code change. This avoids coupling the
pipeline to a specific connector's OAuth.

**Alerting can never crash the pipeline.** A hung or failing Slack endpoint must not
take down (or mask) the run. `send_alert` uses a short timeout and swallows all
network errors, falling back to console and returning a status dict. An alerting
failure degrades to a quieter alert — never to a broken pipeline.

**Failure hook, not polling.** `alert_on_failure` is a Dagster `@failure_hook`
attached to the daily job. It runs the instant any step raises, with the failing
step name, run id, and SLA context — no separate watcher to maintain.

**Fail-closed, and downstream stops.** Because the quality gate raises on violation
and hooks fire on failure, a bad refresh both alerts *and* prevents dbt/quality from
publishing. Verified: when `raw_sources` fails, `dbt_models` and `data_quality` never
run.

**The SLA is measurable, not aspirational.** Every commitment in `SLA.md` maps to a
real signal: freshness → `dbt source freshness` on `_loaded_at`; quality → the two
test suites' exit codes; timeliness → the 06:00 schedule vs 07:00 deadline.

## Results (verified 2026-07-20)

- `alerts.py` console path formats correctly; with a webhook set but unreachable, it
  **degrades gracefully to console** and returns `{'channel':'console','ok':True}` —
  never raises.
- **Failure hook fires end-to-end:** forced `raw_sources` failure → `STEP_FAILURE` →
  `alert_on_failure` triggered → alert emitted with run_id/step/SLA →
  `HOOK_COMPLETED` → `JOB_SUCCESS: False`, downstream steps skipped.

Example alert (console fallback):

```
================================================================
[ALERT:ERROR] NorthPeak pipeline [sandbox-demo]
  Pipeline step failed: raw_sources
  - run_id: 0ee10398-...
  - step: raw_sources
  - sla: 07:00 UTC daily refresh
================================================================
```

## Deliverables

```
orchestration/alerts.py          # channel-agnostic send_alert()
orchestration/dagster_defs.py    # @failure_hook alert_on_failure wired to the job
docs/SLA.md                      # the promise: freshness, quality gate, severities
docs/runbook.md                  # on-call playbook per failing asset
```

## Turning on Slack (when ready)

```bash
export SLACK_WEBHOOK_URL="https://hooks.slack.com/services/XXX/YYY/ZZZ"
export NORTHPEAK_ENV="prod"
# that's it — the hook now posts to Slack instead of console.
```

## Next: Phase 7 — Self-serve BI

Stand up the semantic/BI layer (Metabase or a lightweight dashboard) over the governed
marts so marketing/ops/finance explore metrics themselves, with the metric definitions
baked in so self-serve can't reinvent "revenue."
