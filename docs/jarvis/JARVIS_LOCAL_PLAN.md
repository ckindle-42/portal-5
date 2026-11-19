# Jarvis Local — personal agent plan

Written 2026-11-19 from the tree at `610b08e0f` (`lane/jarvis-research`) and from
`~/.claude/orchestrate/bin/dispatch.py` plus `~/.claude/orchestrate/RESUME.md` as read the
same day. This is a plan. It does not change `config/portal.yaml`, start the queue, or send
Telegram. Claims are marked **sourced** (path or URL + date) or **estimated**.

Jarvis Local stays the operator's unattended runner. The personal agent is a second intake
on that same runner: a request comes in from Telegram or Open WebUI, a local planner writes
a small plan, a local tool-caller runs it through the Pipeline tool loop and the MCP fleet
already exposed to the Pipeline, and a blocked or oversized task goes to a cloud lane through
the dispatcher that already admits work. The arm queue, its jobs, its oracle, and its
Telegram control verbs stay. No second agent framework is added.

## 1. Current state

Jarvis Local is the host process `portal arm queue-run`, kept alive by the launchd agent
`com.portal5.arm-queue` (`docs/JARVIS_LOCAL_RUNBOOK.md`, `docs/ORCHESTRATION_ARM_OPERATORS.md`,
both dated by commit `4ec4f0776` / `c70775b44` on 2026-10-30). It is not a chat agent.

```
Telegram allowlist                Open WebUI
  /jarvis <verb>                    arm_queue_task
  plain "jarvis <verb>"                 |
        |                               v
        v                         QueueLedger.enqueue
 control_requests rows                  |
 (bot writes, runner executes)          v
        |                         bites on Pipeline :9099
        +--------> queue-run <----+  seated fast/deep models
                     |
                     +-- job steps (WFE argv, canary, quiet-host window)
                     +-- daily digest + per-job Telegram notices
                     +-- escalation hook (compiled, switched off)
```

**Queue and runner.** `JobSpec` / `JobRunner` (`portal/modules/orchestration/jobs.py`) run
allowlisted argv steps, adopt a live pid across restart, trip on memory pressure, and write
`receipt.json`. The queue yields on `~/.portal5/locks/`, a live WFE pid, or a Pipeline load
plan that is busy. One runner holds `queue-runner.lock`. WFE jobs are pinned to
`~/projects/portal-5-jarvis-snapshot`. **Sourced:** operator guide and `jobs.py`.

**Bite loop, separate from the chat tool loop.** A bite is one Pipeline request with
`portal_bite_tools`, a task-directory sandbox (`file_read`, `file_write`, `pytest_run`, plus
the discipline allowlist), and deterministic `accept` checks. The worker does not import
`portal/platform/agent/run_loop`. Bite requests skip recalled-memory injection.
**Sourced:** wiki unit `unit-module-orchestration` (queried 2026-11-19) and
`portal/modules/orchestration/planner.py` (`PLANNER_RULES`: read tools and action tools stay
in different bites; plans end in `assembly` then `final_review`).

**Seats that the arm already uses.** Both disciplines bind `fast: auto-daily::gemma-fast`
(Gemma-4-26B-A4B QAT, 32K, think off) and `deep: auto-daily::deep` (Qwen3.8-27B, 96K).
Gate C rates in `config/portal.yaml` `orchestration_arm.calibration` are frozen from
2026-10-22 / 2026-10-23 / 2026-10-28 receipts (`test_fixing` 6/6 both seats;
`detection-engineering` fast 11/12, deep 12/12). **Sourced:** `config/portal.yaml`
`orchestration_arm.disciplines`. Those seats are not retargeted by this plan.

**Telegram.** `portal_channels/telegram/jarvis_control.py` parses `/jarvis` and plain
`jarvis …`. Known verbs execute or queue; anything else is stored as `refused` /
`unknown verb`. Verbs (`portal/modules/orchestration/control.py`): direct `status`, `digest`,
`canary`; queued `pause`, `resume`, `requeue`, `held`, `keep`, `escalate`, `diff`; confirm
required for `cancel` and `merge`. Empty `TELEGRAM_USER_IDS` refuses control (chat is looser).
`telegram_control.enabled` is `true` in both `config/portal.yaml` and the generated
`config/orchestration_arm.yaml`. **Sourced:** those files at `610b08e0f`, blame `cbade2521`
(2026-10-30).

**Digest and notices.** `portal arm queue-digest` sends once per UTC day. Job notices name
the failing step, the campaign or canary line, and the next queued job.
**Sourced:** `docs/ORCHESTRATION_ARM_OPERATORS.md`.

**Escalation and oracle — present, off.** `queue.escalation.enabled` is `false` in
`config/portal.yaml` (blame `bc1ce55ff`, 2026-10-31, message: "Queue escalation is off") and
in `config/orchestration_arm.yaml`. It was turned on the day before (`cbade2521`, 2026-10-30).
While off, `portal arm escalate` refuses and `queue-run` does not call the dispatcher.
The code path, when the flag is true, classifies a blocked job as `canary_setup`,
`harness_error`, `step_failure`, or `memory_trip` (`escalate.classify_block`), writes
`coding_task/escalations/<job>-<n>.md`, and calls `dispatch.py`: attempts 1–2 `--tier auto`,
attempt 3 `--tier escalate`. Security, compliance, and detection jobs pass `--kind security`.
Auto-merge is limited to `tests/wfe/`, `tests/wfe/plans/`, `config/arm_jobs/`, and
`coding_task/`. A diff that touches `portal/`, other `config/`, `scripts/`, or a Dockerfile
is held. The oracle list is `sol`, `grok-max`, `flagship`, `oc-deep-flash`, `oc-glm-flash`,
`deep-pro`, with `security_tier: daybreak`. **Sourced:** `escalate.py`, operator guide,
`config/portal.yaml`.

**Open WebUI intake.** `arm_queue_task` renders a stored template and enqueues it. It does
not plan on the Deep seat. **Sourced:** operator guide, `owui_entry.py`.

**What works in code (offline-proven, live-unproven in this lane).** Control verbs, queue
lock, digest window, canary-before-long-run, escalation classification, hold-vs-merge, and
the Telegram confirm keyboard have unit tests (`tests/unit/test_telegram_jarvis_control.py`,
`tests/unit/test_arm_job_specs.py`, orchestration unit modules). The 2026-10-23 live
end-to-end note in the wiki unit is a historical claim this lane did not re-run.

**What is stale.**

| Claim | Where | What the tree says now |
|---|---|---|
| Escalation, oracle, and Telegram control are enabled (2026-10-30) | `docs/JARVIS_LOCAL_RUNBOOK.md` lines 7–8 | Telegram control is on. Escalation is off since `bc1ce55ff` (2026-10-31). Oracle config remains, and does nothing while the parent flag is false. |
| `detection-engineering` is unseated and has no model binding | `docs/ORCHESTRATION_ARM_OPERATORS.md` paragraph beginning "`detection-engineering` is an unseated candidate" | `seating_status: seated` since the 2026-10-28 note in `config/portal.yaml`, with fast/deep bindings and calibration rates. |
| Oracle tier `oc-glm-flash` is a live reviewer | `config/portal.yaml` `orchestration_arm.queue.escalation.oracle.tiers` | `dispatch.py` marks that tier `retired: True` (comment 2026-11-18, "Model unavailable"). The walker would have to skip it. **Sourced:** `dispatch.py` tier table. |
| Jarvis can be asked to do arbitrary work | operator expectation | A non-verb after `jarvis` is refused. Chat that does not start with `jarvis` goes to the normal Pipeline workspace and never enters the queue. **Sourced:** `jarvis_control.parse` / `handle_jarvis`. |

Nothing in `portal/modules/orchestration/` implements reminders, a personal preference
store, or a free-form tool loop over the MCP fleet. `jobs.py` has no `not_before` / cron
field (search 2026-11-19). The word "schedule" in `service.py` is the arm residency mode
(`swap`), not a calendar.

## 2. What the personal agent needs, and current practice

| Need | Today | Gap |
|---|---|---|
| Intake from Telegram and OWUI | Control verbs; `arm_queue_task` for templates | A personal request has no row |
| Planning | Deep-seat JSON plans inside one discipline; stored templates | No planner for "do this for me" |
| Tool use | Bite tools, task directory only | Pipeline MCP tools are a different loop |
| Memory of preferences and projects | `remember` / `recall` / `link` on the memory MCP; `auto-daily` has `inject_memory` | Bites deliberately skip injection; Jarvis never writes operator preferences |
| Scheduling / reminders | launchd runner + daily digest | No reminder record |
| Long work with check-ins | Job notices and the digest | Personal work has no job, so no notice |
| Approval for risky or outward actions | High-risk bite approval; confirm on `cancel` / `merge`; escalation hold | No denylist for outward MCP tools |
| Reporting | Digest, receipt, Telegram | No personal-task receipt |

**Practice worth copying (published).** The harness, not a bigger prompt, is what makes a
local model usable.

- OpenHands' local-LLM guide (page fetched 2026-11-19; news line dated 2026/05/21,
  <https://docs.openhands.dev/openhands/usage/llms/local-llms>) recommends Qwen3.6-35B-A3B
  as the first local model for agentic coding, tells operators to set the context window to
  at least 22K and preferably 32K, and says a local model that "behaves like a plain chatbot"
  or fails tool calls is a model/context problem. Their Ollama note: the default 4096 context
  cannot hold the system prompt plus tools. The same vendor's overview
  (<https://docs.openhands.dev/openhands/usage/llms/llms>, search snippet dated 2026-10-23)
  says open-weight tool use still varies, and the recovery is a stronger model, a larger
  window, or a frontier model for that one task.
- MarkTechPost, 2026-09-18, "Best Open-Source Agent Harnesses for Local LLMs in 2026"
  (<https://www.marktechpost.com/2026/09/18/best-open-source-agent-harnesses-for-local-llms-in-2026/>):
  the harness runs tools, holds state, manages permissions, and feeds context back; with a
  local model the harness matters more because small windows and weaker tool calling expose
  design flaws. Goose will only chat on a model with no tool calling. A short tool list
  leaves context for the work. (Page fetch returned Cloudflare 520 on 2026-11-19; the
  2026-09-18 date and these sentences are from the search extract, so treat the wording as
  secondary.)
- Berkeley function-calling aggregators on 2026-11-16 and 2026-11-19 disagree with each
  other (pricepertoken BFCL v3 vs BenchLM BFCL v3/v4, both lab-reported). They do not name
  the checkpoints seated in this repo. **Estimated usefulness: low.** Seat choice below uses
  Portal's own screens, not those tables.

**Practice worth copying (this repo).**

- One tool loop already exists: Pipeline streaming hops, default `MAX_TOOL_HOPS` 20
  (`portal/platform/inference/router/workspaces.py`), overridable per workspace
  (`security-reviewer` sets `max_tool_hops: 8`). The arm's bite loop is the other, and it
  is the right loop for graded WFE work. A personal task uses the Pipeline loop. It does
  not grow a third loop.
- Read and act stay split (`PLANNER_RULES`). High-risk writes wait on Telegram
  (`service._approval_required`, `review.is_high_risk`: risk level, tool `file_write`, or
  `write_scope: outside_task`). Destructive control verbs already confirm.
- Memory is a graph the model calls (`remember`, `recall`, `link`, `neighbors`,
  `entity_timeline`, `forget` in `portal/platform/memory/memory_mcp.py`), not a transcript
  pasted into every turn. Bites already refuse the paste. The personal agent recalls at the
  start of a task and writes back only what the operator confirmed.
- MCP servers stay independent. The personal agent calls tools the Pipeline already
  exposes. Fleet entries with `expose_to_pipeline: false` (filesystem, fetch, git, serena,
  docker, browser, proxmox, binresearch, context7 — `config/portal.yaml` `mcp_fleet`) are
  IDE servers. They are not silently flipped on.

**External piece.** The only program outside the repo that this plan calls is
`~/.claude/orchestrate/bin/dispatch.py`, which Jarvis Local's escalation path already calls.
LangChain, LlamaIndex, OpenHands, Goose, and deepseek-harness are not added. They would be
a second runtime beside the Pipeline, with their own permission model and their own model
router. Portal's measured seats, tool allowlists, and the dispatcher's admission already
cover those jobs. **Estimated** judgement, from the architecture rules in `CLAUDE.md` and
from the two loops above.

## 3. Local seats, and when a cloud lane is allowed

Roles call workspaces that are already seated. This plan does not change `model_hint` on
any seat. A new workspace id, if a later lane adds one, points at one of these tags only
after an A/B the operator asks for. Until then the runner passes the existing workspace id
on the Pipeline request.

| Role | Workspace | Why this one | Evidence |
|---|---|---|---|
| Intake reply and summary | `auto-daily` | Daily driver, `inject_memory` already on, text tools include remember/recall | `realuse_autodaily_postfix_20261106`: Nemotron 28/28 vs Gemma 26/28 (`config/portal.yaml` comment, 2026-11-06). Text-only; images stay on `auto-vision`. |
| Planner (no tools) | `auto-reasoning` | `tools: []`, thinking on, 64K | `wfe_reasoning_hard_20261019b`: K2-Horizon 12/12 vs DeepSeek-R1-8B 8/12 (comment, 2026-10-19). |
| Tool caller, everyday | `auto-daily::fast` | Same Qwen3.6-35B-A3B family OpenHands names, at this repo's 96K window, think off, documents/web/python/memory | Seat comment 2026-11-05 / variant block. `tools-specialist` is the same family but `context_limit: 8192`, under the 22K floor OpenHands documents, and it is `expose_to_owui: false`. Leave it as the internal composer. |
| Tool caller, code | `auto-coding` | 96K, sandbox tools, working rule tells the model to run code and report real output | `realuse_s5s7s10_20261030b` 15/16 vs Qwen3-Coder 5/16 (comment, 2026-11-01). |
| Review of a risky personal plan | `auto-daily::deep` | Arm deep seat already | Gate C comments above. Three votes / two approves stays the arm's review block; a personal plan reuses that quorum only when the plan is high risk. |
| Arm fast/deep bites | unchanged | Lineage split is intentional | Do not repoint. |

**Estimated routing inside one personal task:** planner request (tools off) → validator →
zero or more tool-caller requests on `auto-daily::fast`, switching to `auto-coding` when the
plan's tools include `execute_python` / `execute_bash` / `execute_nodejs` → one summary
request on `auto-daily`. Hop cap for the personal tool caller starts at 8 (the cap already
used by `security-reviewer`), not the env default 20. A short list is the practice both
OpenHands and the MarkTechPost note describe, and it matches the arm's per-bite allowlist.

**Cloud rule, reused, not redesigned.** `dispatch.py` `_resolve_auto` (read 2026-11-19)
drops a seat for scope, discount window, peak, and headroom, then ranks by meter class
(free and prepaid before cash; Go behind free unless a long bucket would expire), family
accept rate, and `AUTO_ORDER`. Headroom below `CAP_SWITCH_AT = 0.15` skips the plan.
Metered seats need `--allow-metered`, except `--tier escalate`, which may walk
`ESCALATION`. Security kinds use `_security_candidates`, and `SECURITY_TIER` is `daybreak`.
Jarvis does not rank seats itself.

A personal task may call the dispatcher only when all of these hold:

1. The local plan failed its acceptance check twice, or the planner's context budget
   exceeds the tool-caller window (96K on the seats above; the arm's comfortable budget is
   16384 tokens and stays the cap for arm bites).
2. The task is not operator-cancelled.
3. `kind=security` when the text matches the escalation classifier's security/compliance/
   detection rule; otherwise `kind=code`.
4. Attempts 1–2 are `--tier auto`. Attempt 3 is `--tier escalate`. No `--allow-metered`
   on the personal path unless the operator sets a flag that this plan leaves off.
5. The existing WFE escalation flag stays off until the operator turns it on. Personal
   cloud calls use a separate switch, default off, so repairing a blocked campaign does
   not start just because personal tasks gained a cloud option.

Quota, a retired tier, or a plan out of headroom is a Telegram notice with the dispatcher's
reason string, then the task stays local-blocked. That matches "Escalation quota" in the
runbook.

## 4. Lane steps

Each step is one lane. Later steps assume the earlier receipt shape exists. The orchestrator
runs the live proof on the merged tree, with the stack it already has up. Workers do not.

**Delete, in J1, and not before:** the two stale sentences in
`docs/JARVIS_LOCAL_RUNBOOK.md` (escalation "Enabled") and
`docs/ORCHESTRATION_ARM_OPERATORS.md` (detection-engineering "unseated"). Do not delete
`escalate.py`, the oracle, the control verbs, the digest, the launchd agent, or the arm
disciplines. Do not remove `oc-glm-flash` from the oracle list in this docs lane; that is
a `config/portal.yaml` edit and waits on the operator (see OPEN).

**J1 — make the operator docs match the flags.** Edit only the two stale claims above.
Live proof: `git grep -n "escalation" docs/JARVIS_LOCAL_RUNBOOK.md` shows the flag is off
by reference to `config/portal.yaml`, and `uv run python -c "import yaml; print(yaml.safe_load(open('config/portal.yaml'))['orchestration_arm']['queue']['escalation']['enabled'])"`
prints `False` while telegram control prints `True`. A sentence that still says the
2026-10-30 enablement is current means J1 failed.

**J2 — personal task row.** Add a `personal_tasks` record beside the arm queue (same tasks
directory, own table or own sqlite file — the arm `queue.sqlite3` schema stays). Fields:
id, source (`telegram`|`owui`), user id, text, status, plan json, receipt path, created.
`/jarvis do <text>` and an OWUI tool `jarvis_submit` write a row and reply `queued <id>`.
Unknown verbs stay refused. Live proof: from the allowlisted Telegram account send
`/jarvis do what is the queue status in one paragraph`. Read the new table; one row exists
with that text and status `queued`. The bot reply is `queued <id>` and nothing in
`portal arm queue-status` changed. Then send `/jarvis do` with no text; the row is absent
and the reply is a usage line.

**J3 — one local tool loop, fixed allowlist.** The runner, between arm jobs, takes the
oldest `queued` personal task, calls the Pipeline as `auto-daily::fast` with tools limited
to `recall`, `wiki` search/get (the pipeline wiki tools already registered), and
`queue-status` via the existing arm status function (a local read, not an MCP). Cap 8 hops.
Write `receipt.json` next to the row: workspace id, hop count, final text. Post that text
through the arm outbox. Live proof: the same Telegram sentence returns a paragraph whose
job counts match `uv run portal arm queue-status` read in the same minute. The receipt's
workspace is `auto-daily::fast` and `hops <= 8`. A reply that invents jobs the status
command does not list means J3 failed.

**J4 — planner, then tool seat.** `auto-reasoning` returns JSON only, validated with the
same rules as `validate_planned_plan` where they fit (known tools, read/act split, budget,
no invented paths) and rejected otherwise. The tool seat sees only the validated plan.
Code-shaped tool lists go to `auto-coding`. Live proof: Telegram `/jarvis do read the
newest arm receipt and quote its status field`. The receipt for that personal task contains
a plan naming a read tool, a tool-seat workspace, and a final status string that equals
`jq -r .status` on the newest `~/AI_Output/generated/tasks/*/receipt.json` the runner is
allowed to read. A plan that names a tool outside the allowlist is status `rejected` and
no tool call is logged.

**J5 — approvals.** Extend the confirm keyboard to personal plans. Default deny, before
any call, for: shell/sandbox exec, file write outside the task dir, `remember`/`forget`,
proxmox, unifi, git push, sending mail or chat to anyone but the requesting Telegram user,
and any fleet id with `expose_to_pipeline: false`. High-risk arm bites keep today's gate.
Live proof: `/jarvis do restart the pipeline` (or the closest verb the denylist names)
creates a `pending` confirm row and does not change the pipeline container start time
(`docker inspect -f '{{.State.StartedAt}}' portal5-pipeline` identical before and after).
Abort leaves the task `cancelled`. Confirm is a second message and is the only path that
may proceed — and even then J5 does not actually restart anything; the executor returns
`held: operator must run launch.sh`. A container restart means J5 failed.

**J6 — memory, confirm-to-write.** At task start, one `recall` for the operator id.
`remember` is a proposed sentence in the reply. The row is written only after the operator
presses confirm. Live proof: `/jarvis do remember that I want Telegram replies under 400
characters`. No new memory row until Confirm. After Confirm, a new task `/jarvis do how
long should a Telegram reply be` quotes that sentence, and the memory MCP list shows one
new row. A row that appears before Confirm means J6 failed.

**J7 — reminders on the runner poll.** A personal task may carry `not_before` (UTC).
`queue-run` leaves it queued until then, then runs J3–J4, and the notice is the result.
No new cron, no second launchd agent. Live proof: submit a task with `not_before` two
minutes ahead (`/jarvis do at <utc> send me queue status`). It does not run on the poll
before that time (receipt absent). The poll after that time sends a status whose counts
match `queue-status`. A second scheduler process means J7 failed.

**J8 — check-ins for long personal tasks.** Reuse `JobNoticeSink`. A personal task still
running at 15 minutes sends one notice: id, hop, last tool name. Completion sends the
summary. Live proof: a task whose plan the orchestrator knows will call a slow read
(large document the operator names) produces a check-in notice before the final notice,
and the outbox has both. Missing the final notice means J8 failed.

**J9 — cloud handoff, switch off.** New flag `orchestration_arm.queue.personal_cloud.enabled`,
default `false`, rendered by sync-config the same way `escalation.enabled` is. When false
the runner never calls `dispatch.py` for a personal task. When the operator sets it true,
the rule in section 3 applies, the brief is the personal receipt plus the two failure
tails, and the dispatcher ledger records `requested=auto` (or `escalate` on attempt 3).
WFE `escalation.enabled` is a different flag and stays false. Live proof, only after the
operator enables the flag: a fixture task with an acceptance check the local seat cannot
meet (the brief will name it) produces two local receipts then one `dispatch.py` run line
the orchestrator reads from the dispatcher ledger, with no `--allow-metered`. While the
flag is false, that same task ends `blocked` and the dispatcher ledger gains no row.

Since 2026-11-19 the handoff is bounded: a task gets at most
`orchestration_arm.queue.personal_cloud.max_attempts` cloud dispatches (default 1); an
interrupted/killed lane (dispatch status `interrupted`, exit 143/-15) is terminal for the
task — the row, the receipt and a Telegram notice to the requester say why, and the runner
never re-dispatches on its own. `/jarvis cancel pt-<id>` (Telegram, Confirm first) cancels
the row and stops a lane already running for it.

**J10 — arm templates from a personal request.** If the planner emits a known
`enqueue-template` (discipline, template key, parameters) and the path checks in
`owui_entry.py` pass, the runner enqueues that arm job and the personal receipt points at
it. Live proof: `/jarvis do queue a test_fixing repair for <a fixture the operator names
under the repo or workspace root>`. `portal arm queue-status` shows the new arm job, and
the personal task status is `handed-to-arm`. A parameter path outside the allow roots is
`rejected` and the arm queue is unchanged.

## RESULT

Architecture:

```
Telegram /jarvis verb  --> control_requests --> queue-run (unchanged)
Telegram /jarvis do    --> personal_tasks ---+
OWUI jarvis_submit     --> personal_tasks ---+--> queue-run poll
                                              |
                                              +--> arm template? --> existing queue
                                              |
                                              +--> auto-reasoning plan (tools off)
                                                        |
                                                        v
                                              validator + denylist
                                                        |
                                          pending confirm (Telegram) if risky
                                                        |
                          auto-daily::fast  or  auto-coding   (Pipeline tool loop, <=8 hops)
                                                        |
                                          auto-daily summary --> outbox + receipt
                                                        |
                          two failures or over window, and personal_cloud on
                                                        |
                                          dispatch.py --tier auto | escalate
                                          (WFE escalation flag stays independent)
```

Steps, in order: J1 docs truth, J2 task row, J3 one tool loop, J4 planner, J5 approvals,
J6 memory confirm, J7 reminders, J8 check-ins, J9 cloud switch (default off), J10 handoff
into the existing arm queue. Delete only the two stale doc claims in J1. Keep the runner,
jobs, oracle, digest, control verbs, and both arm disciplines.

## OPEN

1. Which Telegram account is the operator (the allowlist already gates control). Confirm
   it is the only account that may `jarvis_submit` from OWUI.
2. May Jarvis read `~/AI_Output/generated/tasks/` receipts (J3/J4 assume yes) and which
   other roots, if any.
3. May Jarvis call proxmox, unifi, browser, or git at all, even after confirm. This plan
   default-denies them. Enabling any of them is an operator decision and a fleet
   `expose_to_pipeline` change, which this plan does not make.
4. Turn WFE `queue.escalation.enabled` back on, or leave it off (it was switched off on
   purpose on 2026-10-31). Personal cloud is a separate flag and also starts off.
5. Drop retired `oc-glm-flash` from the oracle tier list. That is a config edit plus
   `sync-config` and a pipeline rebuild, so it is not part of J1.
6. Whether a dedicated `jarvis` workspace id is worth an A/B, or callers keep using
   `auto-daily::fast`, `auto-coding`, `auto-reasoning`, and `auto-daily` by id. This plan
   does the latter until an A/B is requested.
7. Reminder granularity: J7 is "run on the next poll after `not_before`", which is the
   runner's poll interval (60 s in the launchd command), not a calendar UI.

## UNPROVEN

- No live Telegram, OWUI, queue-run, or dispatcher call was made in this lane. The
  historical "enabled 2026-10-23 end-to-end" wiki sentence was not re-checked against
  today's stack.
- Whether `oc-glm-flash` is skipped cleanly by the oracle walker was not executed.
- Seat quality numbers are the comments and frozen calibration blocks in `config/portal.yaml`,
  not a new screen. Role assignment across those seats is **estimated**.
- OpenHands' 22K context floor is their requirement for their harness, not a measurement
  on Portal's tool loop. Using it to avoid the 8192-token `tools-specialist` seat is
  **estimated** transfer.
- The MarkTechPost sentences are from a search extract after the origin returned HTTP 520.
- BFCL aggregator scores were not used for seating because the two 2026-11 pages disagree
  and do not name these checkpoints.
- `dispatch.py` `AUTO_ORDER` will keep moving (RESUME.md, 2026-11-18). The plan depends on
  `--tier auto` / `--tier escalate`, not on a copied seat list.
