# Jarvis Local — unattended runbook (operator)

Jarvis Local runs the queued WFE program alone, sends Telegram notices, and (if enabled) asks
Jarvis Cloud lanes to repair a blocked job. Claude is not needed while it runs.

## Start

```bash
cd ~/projects/portal-5
# 1. one runner only — stop any manual runner first
pkill -f "portal arm queue-run --poll-seconds 60"
# 2. install the KeepAlive launchd agent (restarts after crash/reboot; takes only PIPELINE_API_KEY from .env)
./launch.sh install-arm-queue
# 3. optional: let blocked jobs escalate to cloud lanes
#    config/portal.yaml → orchestration_arm.queue.escalation.enabled: true, then:
./launch.sh sync-config && ./launch.sh uninstall-arm-queue && ./launch.sh install-arm-queue
```

Queued jobs start on their own. Check with `uv run portal arm queue-status` or
`uv run portal arm queue-digest --no-send`.

## Stop / pause

```bash
./launch.sh uninstall-arm-queue      # a job mid-step is adopted when the runner returns
uv run portal arm queue-cancel <job>  # drop a queued job (releases its quiet-host claim)
```

## What the Telegram messages mean

| Message | Meaning | You do |
|---|---|---|
| Runner started | Agent (re)started; one per restart, max ~1/min | Nothing, unless it repeats — crash loop: `uninstall-arm-queue`, check `~/AI_Output/generated/tasks/arm-queue.launchd.log` |
| Job DONE + `CAMPAIGN <id>: complete … rows n/n` | Finished; report path included | Nothing — results wait for review |
| Job BLOCKED + `CANARY … SETUP` rows | The live canary found a harness/setup fault before the long run | With escalation on: wait for its notices. Off: leave for the next session |
| Escalation dispatched / result | A cloud lane is repairing it (2 routed tries, then 1 escalated tier) | Nothing |
| Escalation merged | A harness/plan-only fix passed unit+WFE tests and the canary; job re-queued | Nothing |
| Escalation held | The fix touches portal/, config/, scripts/ or a Dockerfile — never auto-merged | Review the branch named in the message |
| Escalation exhausted / parked | 3 tries failed; job left blocked, queue moved on | Next session |
| Memory trip / orphan adopted | Safety stop, or a job carried across a runner restart | Nothing |
| Daily digest | Done / blocked / queued counts | Nothing |

## Rules it keeps

- WFE jobs run from the pinned snapshot `~/projects/portal-5-jarvis-snapshot` (re-pin only right after a rebuild).
- Every campaign step is gated by a live canary; a SETUP verdict stops the job before the long run.
- Never rebuilds, restarts the stack, or pushes. Auto-merge only `tests/wfe/`, plans, `config/arm_jobs/`, `coding_task/`.
- Security/compliance/detection repairs route `--kind security` (never a cloud free gateway).

## Next session (Claude) on return

Read the newest `coding_task/RESUME_*.md` (local, newest entry first), then `uv run portal arm queue-status`,
the job receipts under `~/AI_Output/generated/tasks/<job>/receipt.json`, and each campaign's report.
