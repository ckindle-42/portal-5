# Jarvis Local — unattended runbook (operator)

Jarvis Local runs the queued WFE program alone, sends Telegram notices, asks Jarvis Cloud lanes
to repair a blocked job, has each repair reviewed by a different model family before it merges,
and takes `/jarvis` commands from Telegram. Claude is not needed while it runs.

`telegram_control` is on (`config/portal.yaml` → `orchestration_arm.queue.telegram_control.enabled`).
`escalation.enabled` is false (since 2026-10-31). `escalation.oracle` remains in that file and does
nothing while the parent flag is false. Change a flag in `config/portal.yaml`, then
`./launch.sh sync-config` and reinstall the agent.

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
`escalate <job>` · `keep <job>` · `cancel <job>` and `merge <job>` (both ask Confirm first; a
`pt-` id cancels the personal task and signals a cloud lane already running for it) · `help`.
Notices carry buttons for the same actions. A Telegram merge runs the auto-merge checks (allowlist,
weakened-test check, gates + canary in a throwaway worktree, oracle) and never merges `portal/`,
`scripts/`, Dockerfiles, or `config/` outside `config/arm_jobs/`. Every request is logged
(`queue-status` shows the last 10).

## Personal tasks (`/jarvis do`)

`/jarvis do <text>` queues one personal task beside the arm queue
(`~/AI_Output/generated/tasks/personal_tasks.sqlite3`) and answers `queued pt-<id>` plus its queue
position. The runner drains due tasks back to back, between arm jobs — up to five per wake, and
to empty under `queue-run --drain` — so back-to-back `/jarvis do` asks do not wait a poll each:

- A read-only request is routed (no LLM planner) to a bounded tool bundle and executed on
  `auto-daily::fast` (or `auto-coding` when the request needs a sandbox); the chosen bundle, seat
  and offered tools are in the receipt's `route`. A Portal status question answers through
  `get_pipeline_status` / `get_loaded_models`.
- A host file outside the repo — a security sweep report, a generated file — is read by
  `read_local_file` (full path, at most 32 KB), confined to `~/AI_Output` and `~/.portal5/security`;
  a path outside them is refused.
- Before the first tool call the runner asks the Pipeline's `GET /v1/tools` what the registry
  actually serves. A route needing a tool it lacks is `blocked` on attempt 1 with
  `<bundle> tools unavailable on Pipeline: …`, and `preflight` sits beside `route` in the receipt —
  no retry, no cloud lane. An unanswered probe is unknown, and the attempt runs.
- A risky step (shell, file write, `remember`, git write, a mutating proxmox or unifi/browser call)
  waits for a Confirm button. Read-only proxmox and git reads do not.
- A destructive request (`docker compose down`, a docker prune, `rm -rf`, `launch.sh down`, a force
  push) is refused at intake, and the refusal is the reply — nothing is queued.
- After two failed local attempts the task is retried one rung at a time up
  `orchestration_arm.queue.escalation_ladder` (`config/portal.yaml`) — the same request sent to a
  stronger local workspace over the Pipeline (`auto-reasoning`, then `auto-coding` by default).
  Each hop is one ordinary Pipeline call: no repo worktree, no git branch, and the reason it was
  tried is recorded in `attempts/escalation-<n>/receipt.json`. The ladder is the bound: when it is
  exhausted the task is `blocked` with every hop's reason in its receipt. Personal cloud stays off;
  if an operator enables it, it is only tried after the ladder is exhausted. `cloud-running` means
  that cloud lane is in flight: **it does not hold the queue** — the runner keeps taking tasks,
  then collects the lane's own `## RESULT` block through `dispatch.py` and sends it to Telegram as
  the task's answer (`done`, or `blocked` with the block). A killed lane is terminal for that task.
- The receipt is `~/AI_Output/generated/tasks/<pt-id>/receipt.json`; per-attempt receipts and the
  lane's dispatch log sit under `attempts/`. The Telegram notice is plain text: `[label](url)`
  arrives as `label: url` (tappable), and markdown heading markers and `---` rules are stripped.

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
