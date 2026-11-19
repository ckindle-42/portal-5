# Phase 1d test trim — role `trim-1d`

Operator direction (2026-11-18): the offline suite is a fast merge gate, not evidence. Keep only
(R1) tests that pin a named live bug, (R2) tests that validate config/contracts the running system
loads, (R3) pure logic with no I/O and no mocks. Delete the rest. Scope: the 40 largest files listed
in `coding_task/BRIEF_TEST_TRIM_P1D.md`.

## Headline

| measure | value |
|---|---|
| scope lines at HEAD | 44,916 |
| scope lines after | 43,885 |
| removed by this lane | **1,031 (2.3%)** |
| scope files deleted | 0 |
| scope files split | 3 |
| test items removed | 34 (`pytest` collection: 2,720 → 2,686 = 2,700→2,666 passed + 20 skipped), from 33 test functions |
| kept share of scope | 97.7% |

Two structural facts drive that number, and both are in **Why the scope did not shrink further**
below: 23 of the 40 files (29,167 lines, 64.9% of the scope) are not tests at all — they are the
live WFE/bench harness — and the 17 pytest modules (15,749 → 14,718 lines) are, line for line,
pinned defects, loaded-config contracts and pure parsers. Re-derive any of it with the commands in Evidence.

## Deleted tests

All three files keep the tests whose introducing commit names a defect (`git log -S<test> -- <file>`,
shown per row) and drop the ones landed by `feat`/`merge` commits whose bodies drive mocked I/O.

### `tests/unit/test_no_answer.py` — 613 → 98 lines, 26 → 9 tests

| test | introducing commit | why it fails the keep rule |
|---|---|---|
| `test_owui_turn_through_the_route_ends_with_a_completion` | `65a6be885 feat(router): no dead ends…` | offline route flow; the streaming path is faked end to end |
| `test_alternative_workspace_is_a_loaded_model` | `65a6be885` | monkeypatches `loaded_models` to steer the branch |
| `test_no_alternative_when_nothing_else_is_loaded` | `65a6be885` | same patched probe |
| `test_chat_reply_counts_the_turn` | `65a6be885` | asserts a mocked call counter |
| `test_loaded_models_merges_both_engines` | `65a6be885` | drives a fake httpx registry |
| `test_loaded_models_without_a_registry_is_empty` | `65a6be885` | monkeypatched registry, no loaded contract |
| `test_chat_ui_gets_a_completion_not_a_502` | `65a6be885` | offline end-to-end flow over faked handlers |
| `test_api_client_keeps_the_502` | `65a6be885` | same flow, program audience |
| `test_capacity_refusal_reaches_a_chat_ui_as_a_completion` | `65a6be885` | same flow over a faked stream |
| `test_malformed_request_still_surfaces_its_status` | `65a6be885` | same flow |
| `test_single_candidate_guard_refusal_answers_a_chat_ui` | `65a6be885` | same flow |
| `test_single_candidate_guard_refusal_keeps_the_technical_ending_for_programs` | `65a6be885` | same flow |
| `test_fallback_exhausted_answers_a_chat_ui` | `65a6be885` | same flow with `MagicMock` candidates |
| `test_malformed_stream_error_keeps_the_technical_ending` | `65a6be885` | same flow |
| `test_capacity_rejection_is_a_retryable_chat_notice` | `65a6be885` | same flow |
| `test_failed_chain_hop_answers_a_chat_ui` | `65a6be885` | same flow |
| `test_fallback_exhausted_keeps_the_technical_ending_for_programs` | `65a6be885` | same flow with `MagicMock` candidates |

### `tests/unit/test_hunt_product_path.py` — 880 → 498 lines, 18 → 9 tests

| test | introducing commit | why it fails the keep rule |
|---|---|---|
| `test_hunt_start_routes_to_the_r2_job_runner` | `36aa8f49a feat(hunt): expose R2 notables…` | offline job-dispatch flow over a patched worker |
| `test_status_long_polls_until_terminal_and_returns_latest_progress` | `9f63185ed feat(hunt): wait for long jobs…` | fake clock + patched runner |
| `test_status_long_poll_is_bounded` | `9f63185ed` | fake clock bounds, no loaded contract |
| `test_start_persists_queued_job_and_dispatches_background_worker` | `36aa8f49a` | patches the background worker to assert dispatch |
| `test_r2_job_persists_stage_progress_cost_and_analyst_views` | `36aa8f49a` | offline stage flow over patched stages |
| `test_pipeline_requests_use_the_remaining_hunt_deadline` | `36aa8f49a` | faked pipeline client, deadline arithmetic over the fake |
| `test_hunt_timeout_is_not_sent_as_a_pipeline_completion_field` | `36aa8f49a` | same faked client |
| `test_embedding_requests_stop_at_the_shared_hunt_deadline` | `36aa8f49a` | same faked client |
| `test_product_generator_defaults_include_misfit_and_configured_knowledge` | `b21884a48 merge(hunt): integrate misfit…` | monkeypatches `product_jobs.notables_stage` to capture kwargs |

### `tests/unit/test_pipeline_hardening.py` — 2,389 → 2,255 lines, 78 → 71 tests

| test | introducing commit | why it fails the keep rule |
|---|---|---|
| `test_bite_allowlist_does_not_readd_filtered_nonstream_client_tools` | `6ef1c5055 feat(orchestration): local task arm Phase 1` | mocked tool-allowlist flow, no named defect |
| `test_an_empty_answer_with_tools_retries_once_without_tools` | `ad326c1ff feat(pipeline): hunt reasoning seat…` | feature behaviour over faked replies |
| `test_an_empty_answer_without_tools_is_not_retried` | `ad326c1ff` | same feature flow |
| `test_tool_choice_none_sends_no_workspace_tools_non_streaming` | `ad326c1ff` | same feature flow |
| `test_tools_array_empty_sends_no_workspace_tools_non_streaming` | `ad326c1ff` | same feature flow |
| `test_non_streaming_omlx_forwards_client_budget_over_workspace_default` | `4e3800ad6 feat(inference): forward per-seat thinking budgets` | feature flow over faked engine body |
| `test_chain_hop_injects_workspace_budget_on_omlx` | `4e3800ad6` | same feature flow |

No `pytest.fixture` or data module was used only by the deleted tests: the trimmed modules' remaining
helpers are still referenced (checked), and the one autouse fixture in `test_no_answer.py` was kept for
state isolation.

## Kept — rule each one meets

### Not tests (live harness / acceptance drivers) — 23 files, 29,167 lines, untouched

| lines | path | why it is not in the trim |
|---:|---|---|
| 6,160 | `tests/wfe/campaign.py` | WFE campaign runner (`python -m tests.wfe…`), imported by `runner`, `report`, `canary`, `e2e/rig`; PHASE2_PLAN §2 keeps the harness |
| 2,304 | `tests/wfe/runner.py` | live rig runner (`tests/wfe/e2e/rig --live`), imported by the suites and `controls` |
| 2,192 | `tests/wfe/settings_audit.py` | live seat-settings auditor; the product mirrors it (`portal/platform/inference/cli/renderers.py`, `router/truncation.py` cite it) |
| 1,623 | `tests/wfe/report.py` | WFE report builder, imported by `campaign` and both e2e drivers |
| 1,401 | `tests/benchmarks/bench_lab_exec.py` | live bench harness; `portal/modules/security/core/matrix.py` imports it at runtime |
| 1,300 | `tests/wfe/checkers.py` | WFE checker library imported by `runner`, `controls`, the suites and the tests |
| 1,211 | `tests/wfe/suites/build_coding_production.py` | workload generator for `coding_production.jsonl` |
| 1,123 | `tests/benchmarks/bench_omlx_v3.py` | live bench driver cited by `unit-design-omlx-dual-backend-plumbing` |
| 1,090 | `tests/wfe/suites/build_documents_production.py` | workload generator |
| 1,079 | `tests/benchmarks/bench_judgment_probe_v6.py` | live probe; imported by `tests/unit/test_judgment_probe_instrument.py` and the compliance probe |
| 1,021 | `tests/benchmarks/bench_capability.py` | live capability driver; `tests/benchmarks/bench_repair/runner.py` imports `_emits_reasoning` from it |
| 912 | `tests/wfe/e2e/rig_orchestration_arm.py` | acceptance driver (`docs/ORCHESTRATION_ARM_OPERATORS.md`); brief excludes acceptance drivers |
| 900 | `tests/benchmarks/bench_router_conditions.py` | live router bench (`tests/benchmarks/README.md`) |
| 890 | `tests/wfe/suites/build_realuse_v1.py` | workload generator |
| 848 | `tests/wfe/suites/build_reasoning_hard_production.py` | workload generator |
| 823 | `tests/benchmarks/bench_mbptl.py` | live bench phase library imported by `bench_lab_exec` |
| 771 | `tests/wfe/e2e/rig.py` | live rig driver |
| 665 | `tests/benchmarks/bench_candidates_v10.py` | live candidate-probe driver |
| 631 | `tests/wfe/canary.py` | live pre-campaign canary (`wfe_campaign.sh --canary`) |
| 585 | `tests/benchmarks/bench_router.py` | live router bench (`unit-ADMIN_GUIDE-router-benchmarks`) |
| 566 | `tests/wfe/e2e/live.py` | live driver against production Pipeline/MCP |
| 541 | `tests/wfe/suites/build_general_production.py` | workload generator |
| 531 | `tests/wfe/decision.py` | WFE decision module imported by `tests/wfe/tests/test_wfe_plan_suites.py` |

### pytest modules — 17 files, 15,749 → 14,718 lines

| lines | path | rule |
|---:|---|---|
| 1,452 | `tests/wfe/tests/test_wfe_checkers.py` | R3 — grader/checker logic and answer normalizers, value-in/value-out |
| 1,436 | `tests/unit/test_pipeline.py` | R2 — `portal.yaml`/`backends.yaml`/persona/workspace-routing contracts; R3 — `_record_usage`, tool registry, persona-tool resolution; R1 — `P5-SEC-001`, `P5-MAINT-001`, `P5-OBS-001`, `P5-ROUTER-EVICTION-001`, seat 3 (2026-11-16) |
| 1,237 | `tests/wfe/tests/test_wfe_contracts.py` | R2/R3 — tool-schema, settings-audit and sampling contracts the harness loads |
| 887 | `tests/unit/test_stream_pipeline_errors.py` | R1 — five `fix(pipeline)` commits naming stream-framing defects (a failed hop, an in-band error, usage on every turn) |
| 838 | `portal/modules/security/tests/test_bench_scoring.py` | R3 — in-memory scoring |
| 832 | `portal/modules/security/tests/test_rbp_episode_grounding.py` | R3 — episode verdict math |
| 798 | `tests/unit/test_load_guard.py` | R1 — all 19 admission tests were introduced by `fix(load-guard)` commits naming the refusal they pin (dated docstrings on 7); R3 — `_cross_engine_copies`, wait-header parser. Kept symbols (`GIB`, `OLLAMA_URL`, `Engines`, `guard`) are imported by `tests/unit/test_seat_fit.py` |
| 761 | `tests/unit/test_hunt_scoreboard.py` | R3 — pure scoreboard/recall math (also the brief's notables/relate skip) |
| 699 | `tests/unit/test_trace_sections.py` | R3 — `portal trace` parsers and verdicts, no network or docker |
| 632 | `tests/unit/test_ollama_native.py` | R3 — `to_native_request`/`messages_to_native`/`to_openai_completion`; R1 — Ollama `/v1` sampling (2026-09-25), in-band abort (ollama#18563), Gemma 4 post-tool prefill |
| 597 | `tests/unit/test_tps_metrics.py` | R3 — decode-time and rate math |
| 596 | `portal/modules/security/tests/test_ablation_attribution.py` | R3 — attribution classify/summarize |
| 560 | `tests/unit/test_hunt_observations.py` | R3 — grid scoring/ordering math |
| 542 | `portal/modules/security/tests/test_blue_orchestrate_loop.py` | R1 — dated live pins (2026-07-18/20); R3 — loop helpers |
| 498 | `tests/unit/test_hunt_product_path.py` | R1 — nine `fix(hunt)` pins (Stage 1 ranking, bounded cards, lead paging) |
| 98 | `tests/unit/test_no_answer.py` | R3 — `is_chat_ui`/`reason_class`/`message`; R1 — bite body stays an API request, case-only resident match |

## Why the scope did not shrink further

1. **64.9% of the scope is not tests.** `tests/wfe/{campaign,runner,settings_audit,report,checkers,
   canary,decision}.py`, `tests/wfe/suites/build_*`, `tests/wfe/e2e/*` and `tests/benchmarks/bench_*`
   have no `test_` name, are not collected by `pytest`, and are reached as `python -m tests.wfe…` or by
   importing them. Deleting them would remove the exercisers the orchestrator runs and, in one case,
   break product code: `portal/modules/security/core/matrix.py:479` does `from bench_lab_exec import …`.
   `PHASE2_PLAN.md` §2 and `PHASE1B_trim-wfe.md` §Scope both rule the harness out of test trimming.
2. **The pytest share is 15,749 lines and was already trimmed twice on 2026-11-18.** `a8e5d8046`
   (tests/unit m–z −37,972) and `82ed444f9` (a–l −48,403) applied these same rules hours earlier; the
   survivors are the ones those lanes judged keepers. Removing them again is a rule change, not a
   trim: the standing R1 wording ("the test **or its introducing commit** names the bug — a fix
   commit") protects 71/71 of `test_pipeline_hardening.py`, 25/25 of `test_stream_pipeline_errors.py`
   and 21/21 of `test_load_guard.py`, whose per-test introducing commits are all `fix(...)` subjects
   that name a concrete defect.

## If you want more (scope of the alternative, not applied)

R1 as written protects any test whose introducing commit is a `fix(...)` that names a defect. Read
strictly — "keep the test only when its own text names the bug" — these four files are the mass, and
each line below is one revert away:

| file | now | strict-R1 estimate | what would survive |
|---|---:|---:|---|
| `tests/unit/test_pipeline_hardening.py` | 2,255 | ~450 | the module receipt's 11 named defects + the pure predicates |
| `tests/unit/test_stream_pipeline_errors.py` | 887 | ~120 | the two `Live 2026-11-16` usage pins + the terminal-framing pair |
| `tests/unit/test_load_guard.py` | 798 | ~470 | the 7 dated docstring pins + 2 pure helpers (the `Engines` fake stays for `test_seat_fit`) |
| `tests/unit/test_ollama_native.py` | 632 | ~430 | the pure request/response translators + the `ollama#18563` in-band pins |
| **total** | **4,572** | **~1,470** | **≈ −3,100 more lines** |

That is a policy change (it deletes named-defect nets the previous lanes kept), so it is the
orchestrator's call, not this lane's.

## Evidence

```
baseline: uv run pytest tests/unit/ tests/wfe -q -n auto  ->  2700 passed, 20 skipped, 56.01s, exit 0
after:    uv run pytest tests/unit/ tests/wfe -q -n auto  ->  2666 passed, 20 skipped, 36.17s, exit 0
uv run ruff check .                        -> All checks passed!
uv run ruff format --check .               -> 1666 files already formatted
uv run mypy portal/                        -> Success: no issues found in 716 source files
python3 scripts/complexity_report.py --gate -> GATE OK (data_lines 11,846/13,370; god_lines
                                               66,115/71,202; unwired_scripts 25/25;
                                               identical_pairs 0; committed_blob_bytes 1,792,894/1,873,616)
```

Scope line counts: `git show HEAD:<path> | wc -l` vs `wc -l <path>` over the 40 listed files —
44,916 → 43,885.

## Live checks for the orchestrator

| product area my deletions touched | what to run | what proves it |
|---|---|---|
| Pipeline no-answer framing (chat UI vs program) | `./scripts/smoke_stream.sh`, then one OWUI turn on a workspace whose seat cannot load (`auto-daily` with the seat pinned out of memory) | the chat turn ends with readable text and no error banner; `uv run portal trace --section workspaces` shows the served route and one terminal usage frame; a scripted `curl` to `/v1/chat/completions` still returns the technical status |
| Hunt product path (job start, long-poll status, leads paging, bounded cards) | `python scripts/proofs/owui_hunt_chat.py`, then read `job_id` → status → leads from the review MCP | a real job id reaches `terminal`, leads rows are non-empty and capped, and the trace shows the `security-reviewer` → review MCP hop |
| Pipeline request path (tool loop, fallback cascade, usage frame) | `./scripts/smoke_stream.sh` plus one tool-using turn on `auto` | SSE ends with exactly one `[DONE]`, a `usage` chunk on every turn, and the tool span in `/v1/trace` |
