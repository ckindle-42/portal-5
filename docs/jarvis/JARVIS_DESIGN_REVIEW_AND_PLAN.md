# Jarvis Local (Personal Lane) — Design Review & Rebuild Plan

**Date:** 2026-11-20 · **Tree:** `76a92c605` · **Scope:** Design review of the Jarvis Local personal lane (`portal/modules/orchestration/personal_*.py`, `portal_channels/telegram/`, `escalate.py`, Pipeline tool scoping) and a concrete rebuild plan sized for DeepSeek-flash lanes.

**Verdict:** The personal lane fails by design because it grafts the orchestration arm's **multi-bite WFE planner** (blind toolless JSON planning on `auto-reasoning` + handcuffed execution + whack-a-mole regex acceptance) onto a 1–4 tool personal assistant, and escalates personal questions into **repo-mutating coding worktrees** governed by `WORKER_CONTRACT.md`. Stop patching symptoms; drop the upfront LLM planner, replace it with deterministic tool-bundle routing into a native tool-calling loop on `auto-daily::fast` (or `auto-coding`), make memory pull-on-demand, and separate personal cloud escalation from coding worktrees.

---

## 1. How It Works Today

Every personal request traverses seven stages from Telegram or Open WebUI to the final notice.

```
Telegram (/jarvis do …) or OWUI (jarvis_submit)
  │  personal_intake.py:29-68 · jarvis_control.py:118-159 · owui_entry.py:41-70
  ▼
personal_tasks.sqlite3 (status='queued')
  │  cli.py:338-357 (poll_seconds=60, 1 task/poll when arm queue is not WAITING/BUSY)
  ▼
poll_personal_tasks (personal_runner.py:151-211)
  ├─ 1. reconcile_cloud_lanes (personal_runner.py:646-659)
  ├─ 2. text_gate (personal_policy.py:154-165) -> deny | confirm | allow
  ├─ 3. _recall_memory (personal_runner.py:1092-1126) -> unconditional HTTP call to memory MCP :8920
  ├─ 4. PLAN: auto-reasoning (K2-Horizon-MoVA, tools=[], JSON mode)
  │     personal_runner.py:1016-1067 · personal_policy.py:290-350
  │     + plan_gap() (personal_policy.py:482-494) + validate_personal_plan() (personal_policy.py:168-200)
  ├─ 5. CONFIRM (optional): pending row + Telegram inline Confirm/Abort
  │     personal_runner.py:916-918,999-1013 · jarvis_control.py:162-224
  ├─ 6. EXECUTE: _hop_loop on auto-daily::fast or auto-coding (<= 8 hops)
  │     personal_runner.py:930-996,1396-1457 · streaming.py:2901-3016 · eval_gate.py:162-183
  ├─ 7. ACCEPTANCE: acceptance_failure() (personal_policy.py:404-455)
  │     Fail 1 -> status='queued' retry; Fail 2 -> _run_cloud_attempt (dispatch.py)
  ▼
_finish -> receipt.json + arm_notice -> Telegram outbox (bot.py:82-99, 2s poll)
```

### Stage-by-stage trace (`file:line`)

| Stage | Entry & code path | What actually happens |
|---|---|---|
| **Intake** | `portal_channels/telegram/bot.py:188-199` → `jarvis_control.py:98-159` → `personal_intake.py:29-68`; OWUI `owui_entry.py:41-70` | Checks `TELEGRAM_USER_IDS` allowlist, parses optional `at <UTC ISO-8601>`, runs `refusal_reason()` (`personal_policy.py:117-124`) to hard-refuse `docker compose down`, `docker … prune`, `rm -rf`, `launch.sh down/rebuild`, `git push --force`. Inserts a `queued` row in `~/AI_Output/generated/tasks/personal_tasks.sqlite3` (`personal_store.py:48-69`) and replies `queued pt-<id>\nQueue position: N`. |
| **Runner poll** | `portal/modules/orchestration/cli.py:338-364` → `personal_runner.py:151-211` | `com.portal5.arm-queue` (`portal arm queue-run`) loops every `poll_seconds` (60 s). When `OvernightQueue.run_next()` is not `WAITING`/`BUSY`, calls `poll_personal_tasks()` **once** per poll: reconciles finished cloud lanes, then claims the oldest runnable row (`confirmed` > `queued` > `cloud_retry`, honoring `not_before`). |
| **Memory preamble** | `personal_runner.py:913,1092-1167` | Calls memory MCP (`:8920`) `recall(query="operator id <uid>: preferences relevant to <text>", top_k=5)`, filters `similarity >= 0.65` and `_SCRATCH_MEMORY` regex (`personal_runner.py:80-83`). Appends `"recall"` to `_CheckIn.called` (`L1100`) — even though the model never called it. |
| **Plan** | `personal_runner.py:1016-1089`, `personal_policy.py:15,168-200,290-365,482-494` | Short-circuits `"clean things up"` via `concrete_work_question()` (`L1023`). Otherwise builds `planner_body()` targeting `auto-reasoning` (`K2-Horizon-MoVA-36B-A4B-GGUF:Q4_K_M-ctx64k`, `portal_no_tools=True`, `response_format=json_object`, `enable_thinking=True`) with a flat sorted list of ~95 tool names (`KNOWN_TOOLS | _personal_available_tools()`). Parses JSON, checks `plan_gap()` (Word doc must name `create_word_document` or `read_word_document`), retries once on parse/gap error, then runs `validate_personal_plan()` (no unknown/hidden tools, no read+act in same step, budget ≤ 98,304, `paths` under `tasks_root`). |
| **Confirm** | `personal_runner.py:916-918,999-1013,846-880`, `jarvis_control.py:162-240` | If `text_gate()` is `"confirm"` or `plan.needs_confirm` (`CONFIRM_TOOLS`, `unifi_*`, `browser_*`, non-read `proxmox_*`/`git_*`), saves `plan_json`, sets `status='pending'`, writes a `control_requests` row (`verb='personal'`), and sends `"Confirm pt-<id> before any tool call?"` with Confirm/Abort buttons. Confirm sets `status='confirmed'`; next poll runs `_run_confirmed()`. |
| **Execute & Tools** | `personal_runner.py:930-996,1396-1457`, `personal_tools.py:16-90`, `eval_gate.py:162-183`, `streaming.py:2901-3016` | Selects `auto-coding` (`Qwen3.8-27B`, 96K) if `plan.tools & CODE_TOOLS`, else `auto-daily::fast` (`Qwen3.6-35B-A3B`, 96K, think off). Sends `portal_bite_tools = sorted(plan.tools)`, `portal_bite_max_hops = 8`, `exec_audit = True`, plus OpenAI schemas for any `LOCAL_TOOLS` in `plan.tools`. Pipeline intersects `portal_bite_tools` with the workspace's `tools` list (`eval_gate.py:162-183`), runs MCP tools inside the Pipeline streaming loop, emits `exec_audit` events (`streaming.py:176-193`), and hands any client-side `LOCAL_TOOLS` calls back to `_hop_loop` (`personal_runner.py:1424-1439`), which runs `run_read_tool()` on the host. |
| **Acceptance & Retry** | `personal_policy.py:404-480,510-532`, `personal_runner.py:194-273` | After `_hop_loop` finishes, `acceptance_failure()` rejects: empty content, any JSON tool output with `"error"`, any planned step tool not in `called` (`_unsatisfied_step`), Word-doc ask without `create_word_document`, repo path in request without a `content`/`matches` read (`_repo_file_read`), placeholder/refusal phrases (`_FABRICATED_ANSWER`), or `"largest"` ask omitting `max(size)`. Attempt 1 writes `attempts/local-1/receipt.json` (with `plan: null` because `task.plan_json` is only written on `pending`!), re-queues `status='queued'`, and sends a Telegram retry notice. Attempt 2 escalates to cloud if `personal_cloud.enabled` is true, else marks `blocked`. |
| **Escalation** | `personal_runner.py:302-425,557-769,803-823`, `escalate.py:224-232,384-534` | Classifies `kind` via `personal_dispatch_kind()` (`security` \| `review` \| `research` \| `code`), writes `cloud-brief-1.md`, and launches `ProcessDispatcher.start()` → `dispatch.py --repo <portal-5> run --role jarvis-personal-<id>-a1 --tier auto --kind <kind> --brief … --new` detached (`status='cloud-running'`). Subsequent polls call `reconcile_cloud_lanes()` → `dispatch.py result`, extract user text via `user_answer()` (`L557-569`), and call `_finish()`. |
| **Reply** | `personal_runner.py:1460-1510`, `arm_bridge.py:95-103,430-481`, `bot.py:82-99` | `_finish()` writes `receipt.json`, updates `personal_tasks`, and inserts `final_text` into `arm_notice` (`~/AI_Output/.portal_arm/telegram.sqlite3`). Note: `SUMMARY_WORKSPACE = "auto-daily"` (`personal_policy.py:18`) is **never called**. The Telegram bot container polls `arm_notice` every 2 s and sends `_telegram_chunks()` (4096-char plain-text splits, no `parse_mode`). |

---

## 2. Why It Fails, By Design

Three rounds of targeted fixes (`2129309ea`, `76a92c605`, and earlier R5/R6 commits) patched individual symptoms while preserving six structural defects.

### 2.1 The upfront local planner (`auto-reasoning`) is an anti-pattern

`JARVIS_LOCAL_PLAN.md` copied the orchestration arm's **WFE bite planner** (`planner.py`, built for multi-bite graded coding/detection repairs) onto a personal assistant whose requests take 1–4 tool calls.

- **It plans blind.** `planner_body()` (`personal_policy.py:318-350`) runs `auto-reasoning` (`K2-Horizon-MoVA`, `tools: []`) with **zero tool schemas and zero tool descriptions** — only a flat sorted JSON array of ~95 tool names (`PLANNER_PROMPT`, `L314`). The planner cannot see what arguments a tool takes, what directory it reads, or what a first read returns before deciding step 2.
- **It handcuffs the actual tool-caller.** `_execute_plan()` passes `portal_bite_tools = sorted(plan.tools)` and instructs `auto-daily::fast`: *"Execute only this validated plan. Use only the tools it names."* (`personal_runner.py:970`). When the blind planner omits a tool or picks the wrong one, the capable tool-calling model (`Qwen3.6-35B-A3B`, 96K) is forbidden from recovering.
- **It pays a cold model-swap tax on every task.** Live probe (`GET :11434/api/ps`, 2026-11-20 16:27 CST) shows `K2-Horizon-MoVA-36B-A4B-GGUF:Q4_K_M-ctx64k` (7.77 GB VRAM) sitting loaded solely for planning, forcing a swap to/from `Qwen3.6-35B-A3B` on every personal task.
- **Receipts:**
  - `pt-f3e6d5b993ed` (Round 2 Word doc re-test): even *after* adding `security_sweep` and explicit prompt rules, `attempts/local-1/receipt.json` failed with `plan_gap` (`hops: 0`) because the planner emitted `{"steps": [{"id": "s1", "tools": ["security_sweep"], "paths": [], "budget": {"context_tokens": 8192}}]}` and omitted `create_word_document`.
  - `pt-56d4acbfe892` (Round 1 Word doc): planner emitted only `["workspace_files"]`; the executor replied *"The validated plan only allows listing files in the workspace. It does not include any steps for creating a Word document"* and passed acceptance (`done`) with no document.
  - `pt-64e4e4751602` (Pipeline status): local-1 planned `workspace_files` (executor called `queue_status` instead and failed `_unsatisfied_step`); local-2 planned `kb_search` and burned 7 hops inventing `kb_id='portal_pipeline_status'`.
  - `pt-762f21e03768`: `K2-Horizon-MoVA` emitted `<ifm|tool_calls>` instead of JSON when forced into toolless planning.

### 2.2 The acceptance layer is a whack-a-mole regex patch over a broken contract

`personal_policy.py` now carries six bespoke task-specific regexes (`_NO_CONCRETE_WORK`, `_WORD_DOC_REQUEST`, `_FABRICATED_ANSWER`, `_REPO_FILE`, `_LARGEST_REQUEST`, plus `plan_gap`) — one added after each live failure.

- **It cannot generalize.** Adding Excel, PowerPoint, PDF, UniFi, or browser asks will each fail silently until another regex is added to `plan_gap()` and `_ungrounded_answer()`.
- **It fails both ways:**
  - *False negative (`pt-46b3e7c492af`)*: `_workspace_files` echoed `"path": "scripts/engine_install_plan.py"` with `"count": 0`; the Round 1 `_repo_file_missing` substring check saw the path in the JSON blob and marked *"The file does not exist in the workspace"* as `done`.
  - *False positive (`pt-64e4e4751602` local-1)*: `_unsatisfied_step` rejected the run because the executor skipped a bad tool (`workspace_files`) the blind planner had hallucinated.
- **Failed receipts erase their own plan.** `_record_local_failure()` (`personal_runner.py:245`) reads `task.plan_json`, which is only persisted on `pending` confirm. Every `attempts/local-*/receipt.json` across `pt-f3e6d5b993ed`, `pt-b540a922c5c3`, `pt-7447e778ecd5`, `pt-64e4e4751602`, and `pt-56d4acbfe892` has `"plan": null`.

### 2.3 Tool exposure and filesystem scoping are fragmented across three incompatible worlds

1. **Runner-local Python tools** (`LOCAL_TOOLS` in `personal_tools.py:16-25`: `queue_status`, `read_receipt`, `wiki_search`, `wiki_get_unit`, `workspace_files`, `security_sweep`) execute on the host inside `queue-run`.
2. **Pipeline MCP tools on `auto-daily::fast`** (`config/portal.yaml`): **82 tools** — mixing safe read tools with destructive ones (`proxmox_delete_vm`, `proxmox_node_exec`, `git_push`, `execute_python`). Too wide to dump raw into a local model, yet too opaque for a toolless planner to pick from by name alone.
3. **Siloed read scopes & silent discovery failures:**
   - `workspace_files` lists names and sizes in `~/AI_Output`, cannot read file contents, and cannot see the repo (`pt-f77f9d0555f0`, `pt-46b3e7c492af`).
   - `read_text_file` sees the repo and `/tmp`, not `~/.portal5/security/` — forcing a bespoke `security_sweep` tool just to read one markdown report (`pt-7447e778ecd5`).
   - When `MCP_PROXMOX_URL` was missing from `deploy/portal-5/docker-compose.yml`, Pipeline discovery silently dropped Proxmox tools (`streaming.py:2982-3011`), offered **0 tools** to the model, and `pt-b540a922c5c3` failed twice with `hops: 0` (while `tool_calls: ["recall"]` falsely suggested a tool ran, because `_CheckIn` logged the runner's memory preamble).

### 2.4 The escalation contract turns personal questions into software engineering lanes

`_run_cloud_attempt()` (`personal_runner.py:302-367`) invokes `ProcessDispatcher.start()` → `~/.claude/orchestrate/bin/dispatch.py --repo <portal-5> run --role jarvis-personal-<id>-a1 … --new`.

- **`dispatch.py` is a coding-lane dispatcher.** It unconditionally creates a git worktree (`~/projects/portal-5-jarvis-personal-pt-<id>-a1`) on a new branch (`lane/jarvis-personal-pt-<id>-a1`) and injects `coding_task/WORKER_CONTRACT.md` (`dispatch.py:136`). `WORKER_CONTRACT.md` tells the worker to make minimum code changes, run `uv run pytest tests/unit/ -q && uv run ruff check . && uv run mypy portal/`, commit on the lane branch, and return `## RESULT / ## WHAT CHANGED / ## EVIDENCE / ## ORCHESTRATOR RUNS / ## UNPROVEN / ## OPEN / RISK`.
- **Receipts prove the structural collision:**
  - `pt-b540a922c5c3` (*"list the Proxmox VMs that are currently stopped"*, `kind=research`): the cloud lane (`qwen4-max-preview`) saw the local failure, **edited `deploy/portal-5/docker-compose.yml`** on branch `lane/jarvis-personal-pt-b540a922c5c3-a1`, and answered with a git diff report instead of listing the VMs.
  - `pt-7447e778ecd5` (*"write a one-page Word document summarising tonight's security sweep"*): the cloud lane ran `uv run pytest tests/unit/ -q` (89.87 s!) and `uv run ruff check .` and dumped the entire worker report into Telegram.
- Round 2's `_cloud_brief()` (`personal_runner.py:811-819`) and `user_answer()` (`L557-569`) try to override `WORKER_CONTRACT.md` in prose and strip its headers with regexes, while still spawning a repo worktree and git branch and injecting the conflicting contract.

### 2.5 Unconditional memory injection pollutes context

`_recall_memory()` (`personal_runner.py:1092-1126`) fires on every task before planning, with a broad query (`"operator id <uid>: preferences relevant to <text>"`), no memory category filter, and a hardcoded `0.65` similarity floor.

- **Receipts:**
  - `pt-46b3e7c492af` & `pt-f77f9d0555f0`: injected `"Unable to locate /workspace/report.txt"` and `"row count is <output of previous execution>"` into a code review of `scripts/engine_install_plan.py`.
  - `pt-f3e6d5b993ed` (**post-Round-2**, 2026-11-20 16:23 CST): *still* injected 4 unrelated memories (`row_count: 123` and two Splunk/Windows Event 4624/4688 investigation notes) into a security-sweep Word-doc task.
  - `pt-f0b6d5a5a9b6` (`"clean things up"`): injected `"My favourite city is Paris"` and `row_count: 123` before short-circuiting to `{"action": "ask"}`.

### 2.6 Reply formation, approval UX, and queue latency are rough

- **Unused summary layer & raw Markdown:** `SUMMARY_WORKSPACE = "auto-daily"` (`personal_policy.py:18`) is dead code. Raw model output goes straight into `arm_notice` → Telegram `send_message` with no `parse_mode` (`arm_bridge.py:450`), so `### 1. **...**` and `[here](https://...)` render as raw markup.
- **Opaque confirm prompt:** `_request_confirm()` (`personal_runner.py:1013`) sends `"Confirm pt-<id> before any tool call?"` without naming the tool, arguments, or target.
- **1-task-per-60s ceiling:** `cli.py:348-357` runs at most one personal task per 60-second idle poll, adding up to 60 s of dead wait between queued Telegram tasks.

---

## 3. Target Design

The simplest architecture that gets all of these task classes right without adding a second agent framework: **deterministic intake + deterministic tool-bundle routing → single native tool-calling loop on one capable local seat → structural verification → personal-mode cloud fallback (no worktree, no `WORKER_CONTRACT.md`) → clean Telegram reply.**

```
Telegram (/jarvis do …) or OWUI (jarvis_submit)
  │  1. Intake gate: allowlist, not_before, refusal_reason() (hard deny),
  │     ambiguous-ask shortcut (before any model/memory call)
  ▼
personal_tasks.sqlite3  ──►  queue-run drains all due personal tasks per wake
  │
  ▼
2. Deterministic Router (Python, 0 LLM calls, 0 model swaps)
  │  - Maps request -> ToolBundle (core ~10 read-only tools + 0..2 domain bundles)
  │  - Picks seat: auto-coding (sandbox/code exec) vs auto-daily::fast (all other)
  │  - Pre-flight check: verifies domain MCP tools are actually registered on Pipeline
  │  - Mutating intent? -> builds explicit Confirm proposal (action + target) -> pending
  ▼
3. Native Tool-Calling Loop (auto-daily::fast, Qwen3.6-35B-A3B 96K, <= 8 hops)
  │  - Real OpenAI tool schemas (6–18 tools max, read-only + safe workspace writes)
  │  - Memory is PULL via `recall` tool (no unconditional preamble paste)
  │  - `remember` / mutating tools stay behind explicit Telegram Confirm
  ▼
4. Structural Gate (no task-specific regexes)
  │  - Fail only on: empty reply, unrecovered tool error, hop exhaustion without answer,
  │    unavailable required MCP tool, or claimed file path missing on disk
  │  - Always persists bundle + offered tools + per-hop audit to receipt.json
  ▼
5. Personal Cloud Escalation (optional, max_attempts=1, switchable)
  │  - Runs in scratch dir ~/AI_Output/generated/tasks/<id>/cloud-work/
  │  - NO git worktree, NO repo branch, NO WORKER_CONTRACT.md
  │  - Uses coding_task/PERSONAL_CONTRACT.md (read-only repo, user-facing answer only)
  ▼
6. Clean Reply Formatter -> arm_notice -> Telegram (plain readable text + raw URL/path)
```

### Key architectural choices

1. **Native tool-calling loop beats plan-then-execute on local seats.**
   - `auto-daily::fast` (`Qwen3.6-35B-A3B`, 96K, think off, ~58 tok/s) already succeeded in **1 hop** on `pt-3571db6926d2` (code review with line numbers), **1 hop** on `pt-92d5b11d0d19` (Proxmox stopped VMs), and **3 hops** on `pt-f3e6d5b993ed` (security sweep + `.docx` with download URL) *the moment it was actually offered the right tools*.
   - The planner added latency (model swap to `K2-Horizon-MoVA`), failure modes (`<ifm|tool_calls>`, omitted tools, `plan_gap` retries), and zero safety that deterministic tool-bundle scoping does not already enforce more reliably.
2. **Deterministic tool bundles (6–18 tools, read-only by default).**
   - **Core bundle (always offered, 10 tools):** `workspace_files`, `read_local_file` (new general read-only reader scoped to allowlisted roots: `~/AI_Output`, `~/.portal5/security`, `~/AI_Output/generated/tasks`), `read_text_file`, `search_files`, `list_directory`, `queue_status`, `read_receipt`, `wiki_search`, `wiki_get_unit`, `get_pipeline_status`, `get_loaded_models`, `recall`.
   - **Additive domain bundles (keyword/pattern matched, never > ~18 tools total):**
     - *Documents:* `create_word_document`, `read_word_document`, `create_excel`, `read_excel`, `read_pdf`, `create_powerpoint`, `security_sweep`.
     - *Proxmox (read-only):* `proxmox_list_vms`, `proxmox_list_all_vms`, `proxmox_list_nodes`, `proxmox_vm_status`, `proxmox_cluster_status`, `proxmox_list_containers`, `proxmox_list_storage`.
     - *Git (read-only):* `git_status`, `git_log`, `git_diff`.
     - *Web:* `web_search`, `web_fetch`.
     - *Code / Sandbox (routes to `auto-coding`):* `execute_python` (confirm-gated if shell/mutating).
   - **Pre-flight availability check:** Query Pipeline tool list (or `GET :9099` / tool-registry endpoint) before running a domain bundle. If a domain tool (e.g., `proxmox_list_vms`) is not registered on the Pipeline, fail immediately with a clear diagnostic (`"Proxmox MCP tools are not registered on the Pipeline"`) instead of running 0-hop loops and escalating to cloud.
   - **Arm template handoff (J10):** Keep as an explicit deterministic route (e.g. `/jarvis template <discipline> <key> …` or explicit `"queue a <discipline> repair"` pattern) rather than a hidden JSON branch of a free-form planner.
3. **Memory: pull, not push (and clean write confirm).**
   - Remove `_recall_memory()` from the runner preamble. Offer `recall` in the core bundle so the model calls it only when user preferences or prior context matter.
   - Keep `remember` / `forget` behind Telegram Confirm, with the confirm message showing the exact proposed memory sentence (`"Confirm pt-xxxx: save memory 'Telegram replies under 400 chars'?"`).
   - Keep `receipt.tool_calls` strictly for model-invoked tools.
4. **Escalation: personal-mode contract, zero repo worktrees.**
   - Introduce `coding_task/PERSONAL_CONTRACT.md` (15–20 lines: read-only against the repo, deliverables only under `~/AI_Output/generated/`, no `git`/edits/`pytest`/`ruff`/`mypy`, reply in plain user-facing prose with any generated file path).
   - Launch personal cloud escalation in a scratch directory (`~/AI_Output/generated/tasks/<id>/cloud-work/`) with `--no-worktree` / `--contract coding_task/PERSONAL_CONTRACT.md` (or a thin personal-cloud invocation wrapper around the same tier router in `dispatch.py` that skips git worktree creation and `WORKER_CONTRACT.md`).
   - Escalate **at most once** (`max_attempts: 1`), only after a genuine local failure (not on a local MCP wiring outage or an operator refusal/confirm).
5. **Reply & runner polish.**
   - Normalize Telegram replies (strip any stray `## RESULT` scaffolding, convert `[label](url)` to `label: url` so links are tappable in plain-text Telegram, trim excess markdown headers) and keep `_telegram_chunks()` for the 4096-char limit.
   - Drain multiple queued personal tasks in `queue-run` (loop until no runnable personal task remains, yielding between tasks if an arm job is due) so back-to-back Telegram asks don't wait 60 s each.

### What to Keep vs. What to Delete

| Keep | Delete |
|---|---|
| `personal_store.py` (SQLite schema, queue positions, `not_before`, `in_flight_cloud`) | `PLANNER_WORKSPACE` (`auto-reasoning` planner call) and `PLANNER_PROMPT` (`personal_policy.py:15,290-350`) |
| `personal_intake.py` (`/jarvis do`, `refusal_reason`, `not_before`) & `owui_entry.py` (`jarvis_submit`, `arm_queue_task`) | `_validated_plan()`, `_planner_json()`, `_planner_parse()`, `_corrective_body()`, `parse_planner_json()` (`personal_runner.py:1016-1089`, `personal_policy.py:353-365`) |
| `portal_channels/telegram/jarvis_control.py` & `arm_bridge.py` (outbox, Confirm/Abort inline buttons) | `plan_gap()`, `validate_personal_plan()` step-splitting (`_reject_mixed`, `_validate_budget`, `_unsatisfied_step`) |
| `personal_tools.py` (`LOCAL_TOOLS`, extended with read-only `read_local_file`) | Unconditional `_recall_memory()` preamble & `_SCRATCH_MEMORY` band-aid (`personal_runner.py:80-83,1092-1167`) |
| `reconcile_cloud_lanes()`, `cancel_personal_task()`, non-blocking cloud status | Unused `SUMMARY_WORKSPACE` (`personal_policy.py:18`) |
| Arm queue (`jobs.py`, `queue.py`, `escalate.py` WFE path, `control.py`, digest, oracle) | Task-specific regexes in `_ungrounded_answer()` (`_WORD_DOC_REQUEST`, `_REPO_FILE`, `_LARGEST_REQUEST`) once replaced by structural checks |

---

## 4. Rebuild Slices (DeepSeek-Flash Sized, Ordered)

Each slice is scoped to 1–3 files, has a crisp offline unit acceptance property, and ends with the operator's exact **live Telegram proof**.

### Slice S1 — Deterministic Tool-Bundle Router & Direct Native Loop (Drop the Planner)
- **What to build:** Replace `_validated_plan()` + `auto-reasoning` planning with a deterministic `route_personal_task(text, hidden_fleets)` returning `PersonalRoute(workspace, tools, bundle_name, needs_confirm, confirm_summary, ask_question)`. Pass `route.tools` directly to `_hop_loop` on `auto-daily::fast` (or `auto-coding` for code/sandbox). Delete `PLANNER_PROMPT`, `planner_body`, `_planner_json`, `plan_gap`, and `SUMMARY_WORKSPACE`. Always persist `route` (bundle, workspace, offered tools) in both `receipt.json` and `attempts/local-*/receipt.json`.
- **Files:** `portal/modules/orchestration/personal_policy.py`, `portal/modules/orchestration/personal_runner.py`, `tests/unit/test_jarvis_personal_loop.py` (update/prune planner-specific tests).
- **Acceptance property (offline):** Given any of the 5 benchmark requests (largest files, Word doc sweep, repo code review, Proxmox VMs, pipeline status), `poll_personal_tasks` makes **0 calls** to `auto-reasoning`, offers a bounded tool list (≤ 18 tools) to `auto-daily::fast`, and records `route` in every attempt receipt.
- **Live proof (Telegram):**
  1. `/jarvis do write a one-page Word document summarising tonight's security sweep: MAL count, critical count, and what is still open`
     — **PASS:** `status: done` on **attempt 1** (no `attempts/local-1` failure), `workspace: auto-daily::fast`, `tool_calls` contains `security_sweep` and `create_word_document`, `.docx` exists on disk, and `K2-Horizon-MoVA` is not loaded (`GET :11434/api/ps`).
  2. `/jarvis do review scripts/engine_install_plan.py and report every code path that can downgrade a package, with line numbers`
     — **PASS:** `status: done` on attempt 1, `tool_calls` contains `read_text_file`, cites real line numbers from `scripts/engine_install_plan.py`.
  3. `/jarvis do list the Proxmox VMs that are currently stopped`
     — **PASS:** `status: done` on attempt 1, `tool_calls` contains `proxmox_list_vms`, lists stopped VMs with `vmid`s.

### Slice S2 — General Read-Only Local File Tool & Pre-Flight MCP Availability Check
- **What to build:** Add `read_local_file(path, max_bytes=32768)` to `LOCAL_TOOLS` (`personal_tools.py`), read-only and strictly confined to allowlisted roots (`~/AI_Output`, `~/.portal5/security`). Keep `security_sweep` as a convenience wrapper or delegate through it. Add a pre-flight check in `personal_runner.py` (or fail-fast when a domain bundle's MCP tools are absent from the Pipeline) so an unwired MCP fails loudly on attempt 1 with `"<bundle> tools unavailable on Pipeline"` rather than burning retries and cloud escalation.
- **Files:** `portal/modules/orchestration/personal_tools.py`, `portal/modules/orchestration/personal_runner.py`, `tests/unit/test_jarvis_personal_tools.py`.
- **Acceptance property (offline):** `read_local_file` reads files under `~/AI_Output` and `~/.portal5/security`, rejects `..` and paths outside allowlisted roots (e.g. `~/.ssh`, `/etc/passwd`), and a missing domain MCP tool produces an explicit `blocked` diagnostic without escalating to cloud.
- **Live proof (Telegram):**
  1. `/jarvis do List the three largest files in /workspace/generated and report their sizes`
     — **PASS:** `status: done`, `tool_calls` contains `workspace_files`, sizes match `ls -lS` on `~/AI_Output/generated`.
  2. `/jarvis do read the newest security sweep file in ~/.portal5/security and tell me its date and MAL count`
     — **PASS:** `status: done`, date and MAL count match the newest `security_sweep_*.md`.

### Slice S3 — Pull-Only Memory & Actionable Confirm Prompts
- **What to build:** Remove `_recall_memory()` preamble injection from `_run_planned()`. Offer `recall` inside the core tool bundle so the model pulls memory only when relevant; never log synthetic `"recall"` in `receipt.tool_calls`. Update `_request_confirm()` to include the specific action and target (`"Confirm pt-<id>: <action summary>?"`), and ensure `"remember …"` tasks show the exact proposed sentence before Confirm and only call `remember` after Confirm.
- **Files:** `portal/modules/orchestration/personal_runner.py`, `portal/modules/orchestration/personal_policy.py`, `tests/unit/test_jarvis_r5_recall_workspace.py`.
- **Acceptance property (offline):** Running a code review or Word-doc task sends zero memory preamble in the prompt and zero `"recall"` in `tool_calls` unless the model invokes `recall`. Confirm messages include the proposed action text.
- **Live proof (Telegram):**
  1. `/jarvis do review scripts/engine_install_plan.py and summarize its exit codes`
     — **PASS:** `receipt.json` has no `_memory_context` scratch (`row_count: 123`, Windows 4624/4688, etc.) and `tool_calls` has only the tools the model called.
  2. `/jarvis do remember that I prefer concise bullet points in Telegram replies`
     — **PASS:** Bot replies with Confirm/Abort naming the exact sentence; no memory row written until Confirm is pressed.
  3. `/jarvis do clean things up`
     — **PASS:** Immediate reply `"Which files may I delete?"`, `hops: 0`, no model call, no memory recall.

### Slice S4 — Structural Acceptance Gate (Replace Regex Whack-a-Mole)
- **What to build:** Simplify `acceptance_failure()` to structural checks only: (1) non-empty answer, (2) no unrecovered tool error (if a tool errored and a later call didn't succeed), (3) `hops >= 1` whenever the request matched a data/action bundle (so a 0-hop hallucinated answer fails), and (4) if a file-creation tool (`create_word_document`, `create_excel`, `create_powerpoint`) was called, verify it returned a path/URL without error. Remove `_unsatisfied_step`, `_WORD_DOC_REQUEST`, `_REPO_FILE`, and `_LARGEST_REQUEST`.
- **Files:** `portal/modules/orchestration/personal_policy.py`, `portal/modules/orchestration/personal_runner.py`, `tests/unit/test_jarvis_personal_loop.py`.
- **Acceptance property (offline):** Empty answers, unrecovered tool errors, and 0-hop answers to data-bundle requests are rejected; valid answers for arbitrary new task classes (Excel, PDF, UniFi) pass without adding new regexes.
- **Live proof (Telegram):**
  1. `/jarvis do what is the Portal pipeline status and which models are loaded right now`
     — **PASS:** `status: done`, `hops >= 1`, `tool_calls` contains `get_pipeline_status` and/or `get_loaded_models`, counts match live `GET :9099/health` and `GET :11434/api/ps`.
  2. `/jarvis do docker compose down -v`
     — **PASS:** Refused immediately at intake with the refusal reason; no row in `personal_tasks.sqlite3`; `docker inspect` start times unchanged.

### Slice S5 — Personal-Mode Cloud Escalation Contract (Zero Repo Worktrees)
- **What to build:** Add `coding_task/PERSONAL_CONTRACT.md` (read-only repo, deliverables only in `~/AI_Output/generated/`, no `git`/`pytest`/`ruff`/`mypy`, plain user-facing answer only). Update `ProcessDispatcher` (`escalate.py`) and `personal_runner.py` to launch personal cloud lanes in personal mode (scratch cwd `~/AI_Output/generated/tasks/<id>/cloud-work/`, no git worktree, `PERSONAL_CONTRACT.md` instead of `WORKER_CONTRACT.md`, `max_attempts: 1`). Keep `user_answer()` only as a defensive fallback. *(Requires operator decision D1 on `dispatch.py` flag vs. thin wrapper.)*
- **Files:** `coding_task/PERSONAL_CONTRACT.md`, `portal/modules/orchestration/escalate.py`, `portal/modules/orchestration/personal_runner.py`, `tests/unit/test_jarvis_cloud_handoff.py` (and `~/.claude/orchestrate/bin/dispatch.py` if D1 picks Option A).
- **Acceptance property (offline):** Cloud dispatch argv never passes `--repo <portal-5>` for worktree creation and references `PERSONAL_CONTRACT.md`; no git branch `lane/jarvis-personal-*` is created; delivered notice contains zero `## RESULT` / `## EVIDENCE` / `uv run pytest`.
- **Live proof (Telegram, with `personal_cloud.enabled: true`):**
  1. Send a deliberately hard multi-document synthesis task that exceeds local hops (or test via a read-only personal escalation trigger).
     — **PASS:** Cloud lane runs in scratch dir, `git branch --list 'lane/jarvis-personal-*'` gains **0** new branches, `git status` in main checkout is untouched, and Telegram receives only the plain user-facing answer.

### Slice S6 — Telegram Reply Formatting & Runner Queue Drain
- **What to build:** Add a small `format_telegram_reply(text)` helper in `personal_runner.py` (converts `[label](url)` to `label: url`, strips raw `###` heading markers and `---` rules, trims trailing whitespace) so plain-text Telegram messages are readable and links are tappable. In `cli.py:348-357`, drain due personal tasks in a bounded loop (up to e.g. 5 tasks or until an arm job is runnable) instead of sleeping 60 s between every single personal task.
- **Files:** `portal/modules/orchestration/personal_runner.py`, `portal/modules/orchestration/cli.py`, `tests/unit/test_jarvis_personal_loop.py`.
- **Acceptance property (offline):** Markdown links convert to tappable URLs, raw `###` headers are cleaned, and 3 queued personal tasks complete in a single poll cycle without 60 s sleeps between them.
- **Live proof (Telegram):**
  1. Send two `/jarvis do` read-only asks back-to-back within 5 seconds.
     — **PASS:** Both answers arrive within one execution window (no 60 s gap between task 1 and task 2), and any download link in a Word-doc reply is directly tappable in Telegram.

---

## 5. Risks & Decisions the Operator Must Make

### Risks

1. **Tool-bundle misrouting on novel phrasing.** A deterministic keyword router can occasionally miss a domain bundle (e.g. a user asks about a VM by hostname without saying "Proxmox" or "VM"). *Mitigation:* Keep the core bundle broad enough for general file/wiki/status reads, log the chosen bundle in `receipt.json`, and allow a single fallback retry with the expanded read-only bundle (all read-only tools across domains, ~22 tools, still excluding mutating tools) if the model says it lacks a tool.
2. **Model-driven mutating requests.** Without an upfront planner, a user might phrase a mutating ask subtly (e.g. *"power off blah-dc-01"*). *Mitigation:* Mutating tools are **never** included in initial bundles, so the model physically cannot execute them without first going through the Confirm gate.
3. **Junk rows still in the live memory store.** Even with pull-only `recall`, stale tool-scratch rows (`row_count: 123`, `row count is <output of previous execution>`) remain in `:8920` until purged (`scripts/cleanup_junk_memories.py`).
4. **Pipeline image rebuild discipline.** Any `config/portal.yaml` or `docker-compose.yml` change requires `./launch.sh rebuild && ./launch.sh up` (`CLAUDE.md` Rule 6); `queue-run` auto-restarts on repo HEAD change (`cli.py:339-342`), so Python-only slices in `portal/modules/orchestration/` land on `git pull --ff-only` without a Docker rebuild.

### Operator Decisions Required (in order)

1. **D1 — Cloud escalation mechanism (blocks Slice S5):**
   - **Option A (Recommended):** Add `--personal` (or `--no-worktree --contract <path>`) to `~/.claude/orchestrate/bin/dispatch.py` so personal escalations reuse `dispatch.py`'s tier routing/headroom ledger but run in `~/AI_Output/generated/tasks/<id>/cloud-work/` with `coding_task/PERSONAL_CONTRACT.md` and **no git worktree**.
   - **Option B:** Bypass `dispatch.py` for personal tasks and invoke the cloud provider CLI directly from `personal_runner.py` (simpler isolation, but loses `dispatch.py`'s unified quota/headroom tracking).
   - **Option C:** Turn `personal_cloud.enabled: false` and keep Jarvis 100% local until D1 is built.
2. **D2 — Allowlisted host read roots for `read_local_file` (Slice S2):**
   - Confirm the read-only host roots Jarvis may read directly: `~/AI_Output` and `~/.portal5/security` (recommended), plus whether any other operator folder (e.g. `~/Documents`) should be included.
3. **D3 — Arm template handoff syntax (Slice S1):**
   - Keep J10 arm-template enqueueing as an explicit Telegram verb (`/jarvis template <discipline> <key> …`) rather than relying on free-form NL detection inside `/jarvis do`? (Recommended: yes — eliminates ambiguity between personal asks and WFE jobs.)
4. **D4 — Live memory store cleanup (independent of rebuild):**
   - Approve running a targeted cleanup on the live memory MCP (`:8920`) to remove the legacy tool-scratch rows (`row_count: 123`, `Unable to locate /workspace/report.txt`, `output of previous execution`).
