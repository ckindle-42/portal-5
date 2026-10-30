# Jarvis Local — unattended runbook (operator)

Jarvis Local runs the queued WFE program alone, sends Telegram notices, asks Jarvis Cloud lanes
to repair a blocked job, has each repair reviewed by a different model family before it merges,
and takes `/jarvis` commands from Telegram. Claude is not needed while it runs.

Enabled (10-30, `config/portal.yaml` → `orchestration_arm.queue`): `escalation`, `escalation.oracle`,
`telegram_control`. Turn any off there, then `./launch.sh sync-config` and reinstall the agent.

## Start

```bash
cd ~/projects/portal-5
# 1. one runner only — stop any manual runner first
pkill -f "portal arm queue-run --poll-seconds 60"
# 2. install the KeepAlive launchd agent (restarts after crash/reboot; takes only PIPELINE_API_KEY from .env)
./launch.sh install-arm-queue
```

Queued jobs start on their own. Check with `uv run portal arm queue-status` or
`uv run portal arm queue-digest --no-send`.

## Stop / pause

```bash
./launch.sh uninstall-arm-queue      # a job mid-step is adopted when the runner returns
uv run portal arm queue-cancel <job>  # drop a queued job (releases its quiet-host claim)
```

## Telegram commands (only the TELEGRAM_USER_IDS allowlist; empty list = refused)

`/jarvis status` · `digest` · `held` (escalations waiting on you) · `canary <job>` · `diff <job>` ·
`pause` / `resume` (stop / restart picking new jobs; the running job continues) · `requeue <job>` ·
`escalate <job>` · `keep <job>` · `cancel <job>` and `merge <job>` (both ask Confirm first) · `help`.
Notices carry buttons for the same actions. A Telegram merge runs the auto-merge checks (allowlist,
weakened-test check, gates + canary in a throwaway worktree, oracle) and never merges `portal/`,
`scripts/`, Dockerfiles, or `config/` outside `config/arm_jobs/`. Every request is logged
(`queue-status` shows the last 10).

## What the Telegram messages mean

| Message | Meaning | You do |
|---|---|---|
| Runner started | Agent (re)started; one per restart, max ~1/min | Nothing, unless it repeats — crash loop: `uninstall-arm-queue`, check `~/AI_Output/generated/tasks/arm-queue.launchd.log` |
| Job DONE + `CAMPAIGN <id>: complete … rows n/n` | Finished; report path included | Nothing — results wait for review |
| Job BLOCKED + `CANARY … SETUP` rows | The live canary found a harness/setup fault before the long run | With escalation on: wait for its notices. Off: leave for the next session |
| Escalation dispatched / result | A cloud lane is repairing it (2 routed tries, then 1 escalated tier) | Nothing |
| Escalation merged | A harness/plan-only fix passed the weakened-test check, unit+WFE tests, the canary, and the oracle review; job re-queued | Nothing |
| Escalation quota | The lane's plan ran out; not counted as an attempt; resume command included | Nothing — it retries after the plan resets |
| Escalation held | The fix touches portal/, config/, scripts/ or a Dockerfile — never auto-merged | Review the branch named in the message |
| Escalation exhausted / parked | 3 tries failed; job left blocked, queue moved on | Next session |
| Memory trip / orphan adopted | Safety stop, or a job carried across a runner restart | Nothing |
| Daily digest | Done / blocked / queued counts | Nothing |

## Rules it keeps

- WFE jobs run from the pinned snapshot `~/projects/portal-5-jarvis-snapshot` (re-pin only right after a rebuild).
- Every campaign step is gated by a live canary; a SETUP verdict stops the job before the long run.
- Never rebuilds, restarts the stack, or pushes. Auto-merge only `tests/wfe/`, plans, `config/arm_jobs/`, `coding_task/`.
- Security/compliance/detection repairs route `--kind security` (never a cloud free gateway); their oracle is daybreak only.
- Oracle order: sol → grok-max → GLM flagship → free DeepSeek/GLM flash → metered deep-pro; first seat of
  another family than the lane, a seat out of quota passes to the next. Any reviewer fault = hold, never merge.

## Next session (Claude) on return

Read the newest `coding_task/RESUME_*.md` (local, newest entry first), then `uv run portal arm queue-status`,
the job receipts under `~/AI_Output/generated/tasks/<job>/receipt.json`, and each campaign's report.
Audit escalations: `~/AI_Output/generated/tasks/escalation.sqlite3` (events, verdict tags), the lane branches
`lane/esc-*`, and `python3 ~/.claude/orchestrate/bin/dispatch.py score` for per-tier accept rates.
