# Phase 1b test trim — role `trim-wfe` (tests/wfe)

Operator direction (2026-11-18): the offline suite's only job is a fast merge gate; a passing
test is not evidence. Keep only tests that (R1) pin a named live bug, (R2) validate config or
contracts the running system loads, or (R3) are pure logic with no I/O and no mocks.

**Scope:** `tests/wfe/tests/` — the pytest-collected tests of the WFE harness.
`tests/wfe/suites/`, `plans/`, `graded/`, `e2e/` and the harness modules (`runner.py`,
`campaign.py`, `report.py`, `checkers.py`, `judge*.py`, `schema.py`, …) are **not tests**: they
are the live evaluation harness and its fixture data the orchestrator runs. They are untouched.

## Numbers

| | files | lines |
|---|---|---|
| before | 62 | 20,311 |
| after | 20 | 5,754 |
| removed | 43 deleted + 6 trimmed | 14,557 (−71.7 %) |

## Files deleted whole (path, lines, why it fails the keep rule)

| path | lines | why |
|---|---|---|
| `test_wfe_canary.py` | 996 | offline end-to-end canary runs on fake engine replies (R1 flows, not pure logic) |
| `test_wfe_incumbent_reuse.py` | 888 | campaign-bookkeeping (reuse keys/digests) driven over recorded local campaigns |
| `test_wfe_reasoning_hard_slice.py` | 768 | fixture-data checks (suite soundness, regeneration, gold re-derivation) on committed JSONL |
| `test_longread_agg_diag.py` | 509 | one-off 2026-11-07 diagnostic plan structure + report plumbing |
| `test_wfe_eval_mode.py` | 480 | production staging/cleanup flow over patched module internals |
| `test_wfe_run_arm.py` | 466 | subprocess supervisor (child process, PID, signals) |
| `test_wfe_fitness_report.py` | 423 | report/ledger view flows over tmp campaigns |
| `test_wfe_upload_fidelity.py` | 379 | golden Open WebUI RAG prepend text + attachment flow |
| `test_wfe_supervise.py` | 370 | supervisor tick flows over campaign directories |
| `test_wfe_multiturn.py` | 338 | offline multi-turn `run_task` flows with fabricated turns |
| `test_wfe_provenance.py` | 308 | instrument fingerprint/drift flow with patched git/env |
| `test_wfe_judge_council.py` | 304 | every judge transport mocked |
| `test_wfe_reasoning_math_slice.py` | 293 | fixture-data checks on committed JSONL |
| `test_wfe_backfill.py` | 285 | closeout-backfill script (off product path) classification + file IO |
| `test_wfe_production_surface.py` | 282 | tool-proxy surface flows with faked MCP calls |
| `test_wfe_tools_specialist_slice.py` | 277 | fixture-data checks on committed JSONL |
| `test_wfe_component.py` | 265 | offline component flow screen → ledger |
| `test_wfe_general_slice.py` | 257 | fixture-data checks on committed JSONL |
| `test_wfe_cad_slice.py` | 248 | fixture-data checks on committed JSONL |
| `test_wfe_reading_long_slice.py` | 234 | fixture-data checks on committed JSONL |
| `test_wfe_controls.py` | 220 | controls-gate CLI execution paths (open/append/resume/smoke) |
| `test_wfe_coding_slice.py` | 215 | fixture-data checks on committed JSONL |
| `test_wfe_routing_slice.py` | 208 | fixture-data checks of routing-suite prompts |
| `test_wfe_reading_slice.py` | 204 | fixture-data checks on committed JSONL |
| `test_wfe_security_analysis_production_slice.py` | 199 | fixture-data checks on committed JSONL |
| `test_wfe_audio_slice.py` | 197 | fixture-data checks + clip staging flow |
| `test_wfe_research_slice.py` | 185 | fixture-data checks on committed JSONL |
| `test_wfe_extract_slice.py` | 171 | fixture-data checks on committed JSONL |
| `test_wfe_tool_surface_proxy.py` | 165 | proxy flows with patched sandbox/MCP dispatch |
| `test_wfe_ledger_check.py` | 155 | ledger-evidence checker over on-disk campaigns |
| `test_wfe_vision_preflight.py` | 149 | probe route with patched probes |
| `test_wfe_vision_slice.py` | 137 | fixture-data checks on committed JSONL |
| `test_wfe_documents_slice.py` | 115 | fixture-data checks on committed JSONL |
| `test_wfe_judge_cloud.py` | 111 | all-mock cloud judge transport |
| `test_wfe_compliance_slice.py` | 111 | planted-corpus staging / suite fixture checks |
| `test_wfe_production_path.py` | 98 | pipeline `?model=` override flow over faked HTTP |
| `test_wfe_compliance_classify.py` | 89 | classifier trap over a faked model call + store diff |
| `test_wfe_compliance_attainability.py` | 89 | planted-corpus fixture checks |
| `test_wfe_data_slice.py` | 64 | fixture-data checks (DuckDB gold) |
| `tests/wfe/tests/conftest.py` | 61 | autouse fixture stubbing campaign/runner/eval_mode internals for the deleted flows |
| `test_wfe_baseline.py` | 55 | baseline-reuse flow over tmp campaigns |
| `test_variant_module_audit.py` | 50 | seat-audit script filter (off product path) |
| `test_wfe_preflight_scope.py` | 35 | CLI gating with patched campaign internals |

## Split files — deleted per test/class

**`test_wfe_contracts.py` (4,177 → 1,833).** Deleted classes: `TestOfflineRescore` (21 tests:
offline re-grade flow over campaign dirs), `TestModelIdentity` (19: engine identity observations
with faked responses), `TestFailedTurnTrace` (4), `TestModelRelease` (3), `TestDrain` (4),
`TestLaneWithNoIncumbent` (3, rendered prose), `TestWatch` (6), `TestHealth` (9, patched probes),
`TestSamplingDelivery` (4), `TestThinkingOnlyBuildsAreNotFlaggedAsBrokenTemplates` (3, fake
`_post`), `TestThinkingOnlyBuildThinkProbe` (2, fake `_post`), `TestSamplingModeFit` (7),
`TestUnreachableIsNotAModelFailure` (3), `TestTextToolCallParity` (1), `TestToolOutputRetentionForRescore`
(1), `TestTransientPreflightIsRecoverable` (4), helpers `_FakeResp`/`_Ctx`. Deleted individual
tests inside kept classes: `TestWfeCurtailment::test_execute_arm_*` (2, patched `execute_arm`),
`TestStallDetection` 4 mocked-stream tests, `TestAdaptiveThink` 6 request-mocking tests,
`TestPipelineMode` 8 fake-pipeline tests, `TestV2ReviewInstrumentFixes` 7 mock-driven run tests,
`TestTagsAudit` 7 patched-`/api/show` tests, `TestOmlxSettings` 4 file-mocking tests,
`TestMatrixExpansion::test_append_is_additive_and_preserves_completed_rows` (opens a campaign).

**`test_wfe_checkers.py` (1,715 → 1,542).** Deleted `test_agentic_task_that_never_answers_*`,
`test_empty_response_breaks_*`, `test_stall_after_passing_artifact_*`,
`test_text_answer_without_signal_*`, `test_http_error_body_*` and `_fake_turn` — all drive
`run_task` with a fake turn.

**`test_wfe_judge.py` (295 → 87).** Deleted `TestJudgeCampaign` (7, patched `ask_judge`),
`TestReportShowsPreferences` (2), the `campaign` fixture, and
`TestParsing::test_ask_judge_posts_to_the_ollama_chat_api` (patched `urlopen`).

**`test_wfe_judge_compare.py` (304 → 126).** Deleted `TestMainAgreement` (6, patched stdout) and
the three module-level CLI tests; kept the loader and kappa math.

**`test_wfe_realuse_tier.py` (306 → 146).** Deleted 9 tests on the tool-surface report, committed
plans, CLI choice and plan repeats; kept tier expansion and the repeats policy.

**`test_wfe_prompt_surface.py` (158 → 117).** Deleted
`test_pipeline_run_row_sends_the_note_only_in_sandbox_mode` (drove `run_row` into the live
memory/RAG ports).

## Files kept, and the rule each meets

| path | rule |
|---|---|
| `test_wfe_contracts.py` | R3 schema/stream/statistics/matrix/report/template-conformance logic; R2 backends.yaml routing (`TestServedEngine`), portal.yaml prompts and card registry, renderer table |
| `test_wfe_checkers.py` | R3 checker + normalization logic; R1 named live rows (`ready4`, `ready5`, `realuse_*` runs) |
| `test_wfe_decision.py` | R3 decision/curtailment/eligibility/disposition math |
| `test_wfe_timing.py` | R3 engine timing payload parse + speed summary/format |
| `test_wfe_office_contains.py` | R3 docx/xlsx/pptx parse + phrase matching; R1 named live rows |
| `test_wfe_judge.py` | R3 verdict parsing; R2 judge endpoint/config policy |
| `test_wfe_judge_compare.py` | R3 kappa + judgement-dir loader |
| `test_wfe_realuse_tier.py` | R3 tier expansion + repeats policy |
| `test_wfe_sweep_plan.py` | R3 queue→plan placement; R2 routing/window consistency |
| `test_wfe_tiers.py` | R3 tier expansion / append reuse |
| `test_wfe_cells.py` | R3 expected task sets |
| `test_wfe_plan_suites.py` | R2 plan suite floor consistency |
| `test_wfe_next_screens_slice.py` | R2 current seat/routing/window registration |
| `test_wfe_prompt_surface.py` | R3 production tool-name detection + taxonomy conflict |
| `test_wfe_tool_modes.py` | R2 allowlist ⊆ workspace tools (`portal.yaml`, bench workspaces) |
| `test_wfe_gold_isolation.py` | R2 harness deny-prefix contract; R1 (answer-key reachability) |
| `test_wfe_publish.py` | R1 xdist publish collision (seen twice); R3 atomic-write logic |
| `test_wfe_stop_rules.py` | R3 stop-rule logic |
| `test_wfe_runner_timing_guard.py` | R1 `wfe_math_20261018c`; R3 timing coercion |

Mock use left in kept files is path/config redirection (`SUITE_DIR`, `tmp_path`, env vars,
`WFE_JUDGE_*`), never a substitute for the function under test.

## Live checks the orchestrator runs per area

| area the deletions touched | live check |
|---|---|
| suite fixture data (all `*_slice` files) | one real row per family, then `uv run python -m tests.wfe.report --campaign <id>`; the suite builders are unchanged, so a broken fixture shows as a graded FAIL, not a silent pass |
| checkers / gold hygiene | `uv run scripts/wfe_production_smoke.py --workspaces auto-documents,auto-coding` and a real campaign row |
| canary / preflight / run_arm | `uv run python -m tests.wfe.campaign --plan tests/wfe/plans/decision_run_v1.yaml --campaign-id <new> --preflight` then `--smoke` |
| production tool mode / proxy surface | `uv run scripts/wfe_production_smoke.py` (real OWUI → pipeline turn per workspace tool) |
| provenance / instrument drift | the same `--preflight` on a plan; it freezes the served identity |
| supervisor / health / watch | `uv run python scripts/wfe_supervise.py <campaign-id> --once --sample 5` |
| judge (local/cloud/council) | `uv run python -m tests.wfe.judge_compare --campaign <id>` on the newest campaign |
| upload fidelity | one OWUI upload → pipeline turn; expect the RAG prepend in the served prompt |
| closeout backfill | `uv run python scripts/wfe_disposition_backfill.py --help` then a dry run (`--write` refused while anything is unverified) |

## Follow-ups the trim creates

- `scripts/seat_screen/grade_sidecar.py:170` runs
  `pytest tests/wfe/tests/test_wfe_reasoning_hard_slice.py`, which no longer exists. The
  `slice_tests` field is a gate (`grade_sidecar.py:215-216` requires `"passed"` in its last
  line), so every sidecar grade now fails until the path is repointed or the field is dropped.
  The same command is written into `scripts/seat_screen/SIDECAR_BENCH_BRIEF.md:31`.
- `docs/DESIGN_ROOTS_REFINEMENT_20261020.md:52` and `docs/WFE_ROOT_FIX_ACCEPTANCE.md:20,21,26,31`
  cite deleted test files by name/ path; dated acceptance records were left as written.
- `scripts/wfe_disposition_backfill.py` loses its only reference (`test_wfe_backfill.py` was its
  caller), so `unwired_scripts` moves 24 → 25 — exactly at the ceiling (`25 <= 25`), zero
  headroom. No code added to satisfy the census.
- `tests/wfe/e2e/*_attainability.py` and `compliance_classify.py` keep their CLI entry points but
  no longer have a pytest caller; they are live suite checks, not tests, and were kept.
