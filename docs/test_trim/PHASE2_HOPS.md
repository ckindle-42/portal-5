# Phase 2 — live `portal trace` hops and the offline tests they replaced

Four parked lanes (waves 3b–4, 6, 7, jarvis) landed as one change on main; this file
replaces their four `PHASE2_WAVE*.md` docs. Each hop is wired into `portal trace` on
current main and the offline tests it replaces were deleted. The six per-MCP sections are
opt-in by name (`--section documents|memory|rag|wiki|data|compliance`) because each drives
its own seat through the Pipeline; a bare sweep skips them.

| Hop | What the live run proves | Offline tests it replaced (deleted) |
|---|---|---|
| `documents` | `auto-documents` calls `create_excel`; the reply's `/api/v1/files/` URL fetches with `OWUI_API_KEY` (the media hop's `media.fetch_file`) and returns 200 + XLSX bytes. | — |
| `memory` | `auto-research` calls `remember` + `recall`; the store returns the marker and `forget` removes it. | — |
| `rag` | `auto-research` calls `kb_search`; the answer names a `source_file` the live store's own search returns. | `test_rag_multimodal.py` fake-driven `_search` fusion case and its fakes |
| `wiki` | The Pipeline's own MCP client calls `wiki_search`; the ranked unit is a canonical file whose body contains the returned preview, and it outranks `-s0*` acceptance sections. | — |
| `data` | `auto-research::data` calls `run_sql`; the same session reads the marker row back, then drops the table. | — |
| `compliance` | `auto-compliance` calls `compliance_requirement`; the answer cites the first part the register serves. The target is pinned to the register (`CIP-007-6 R1 Part 1.2`; `...1.2.6` does not exist in it — the `served=none` the orchestrator saw). | — |
| `platform` | `scripts/check_owui_preset_drift.py` runs against live OWUI: every seeded workspace/persona preset still matches the repo; drift names the stale prompt/tool binding. | `test_owui_preset_drift.py::test_check_reads_each_workspace_file_but_not_the_bundle` |
| `jarvis` | The personal path live: `jarvis_submit` → operator confirm → arm-queue runner → receipt (done + a read tool + a real named file with its size); a confirm-required write stays `pending` until aborted; the section's rows are deleted. | `test_jarvis_personal_loop.py::test_tool_loop_writes_receipt_and_outbox_within_eight_hops`, `::test_read_only_plan_without_budget_defaults_and_runs_from_receipt_shape`, `::test_code_tools_wait_for_confirm` |
| WFE/bench (`scripts/wfe_production_smoke.py --wfe-case`) | One suite case through OWUI: decoded by the harness's own `_read_stream`/`_audited_calls`, graded by `apply_checkers`, and paired with its `/v1/trace` (resolved workspace, complete outcome, served backend/model, required tool dispatches, exec_audit agreement). `--bench-runs` repeats it, timing only turns with a matching trace. | `test_wfe_exec_audit.py::test_audit_event_becomes_the_rows_tool_log_and_grounds_the_answer`, `::test_no_audit_means_no_calls_and_tool_grounded_fails` |

One implementation each, shared across the hops: the Pipeline turn (`workspaces.stream_turn`
with `prompt`/`cid`), the MCP tool readback (`mcps.mcp_call`, reused by the jarvis submit),
the artifact fetch (`media.fetch_file`, reused by `mcps.file_hop`), and the
module-contributed hops adapter (`lab.contributed`, reused by the jarvis section).
