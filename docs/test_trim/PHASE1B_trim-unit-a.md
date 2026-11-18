# Phase 1B test trim — lane `trim-unit-a`

Scope: `tests/unit/test_[a-l]*.py`, top level only. Rule (operator 2026-11-18, replaces phase 1): KEEP only (K1) a named live bug, (K2) config/contracts the running system loads, (K3) pure logic with no I/O and no mocks; delete everything else.

## Totals

- Baseline (HEAD): **240 files / 68,111 lines**.
- After: **152 files / 19,708 lines**.
- Removed: **88 files / 48,403 lines (71.1% of lines)**; 29% of lines kept (< 40% threshold).
- Whole-file deletions: 88 (87 this run + `test_judgment_probe_scope.py` carried from the interrupted phase-1 run). Split files: 102 (keepers only). Kept whole: 50.

## Deleted whole (path — lines — why it fails the keep rule)

| Path | Lines | Reason |
|---|---|---|
| tests/unit/test_judgment_probe_scope.py | 12 | Golden-text test: asserts a fixed phrase in a bench probe docstring; no product branch decided (carried from phase-1 run). |
| tests/unit/test_acceptance_common.py | 50 | Tests of tooling off the product path (scripts/ or tests/ harness); mock-I/O / offline flows (delete clause: tooling scripts). |
| tests/unit/test_adhoc_probe.py | 139 | Tests of tooling off the product path (scripts/ or tests/ harness); mock-I/O / offline flows (delete clause: tooling scripts). |
| tests/unit/test_all_writebacks.py | 96 | Offline end-to-end flows with mocked/patched I/O (httpx/subprocess/docker/Splunk/store) or monkeypatched internals; no named live bug, live-config contract, or pure logic survives. |
| tests/unit/test_anchor_semantic_card.py | 158 | Offline end-to-end flows with mocked/patched I/O (httpx/subprocess/docker/Splunk/store) or monkeypatched internals; no named live bug, live-config contract, or pure logic survives. |
| tests/unit/test_apply_params_write_back.py | 53 | Offline end-to-end flows with mocked/patched I/O (httpx/subprocess/docker/Splunk/store) or monkeypatched internals; no named live bug, live-config contract, or pure logic survives. |
| tests/unit/test_apply_renderers.py | 169 | Offline end-to-end flows with mocked/patched I/O (httpx/subprocess/docker/Splunk/store) or monkeypatched internals; no named live bug, live-config contract, or pure logic survives. |
| tests/unit/test_arm_digests_refresh.py | 199 | Offline end-to-end flows with mocked/patched I/O (httpx/subprocess/docker/Splunk/store) or monkeypatched internals; no named live bug, live-config contract, or pure logic survives. |
| tests/unit/test_arm_shadow_batch.py | 187 | Offline end-to-end flows with mocked/patched I/O (httpx/subprocess/docker/Splunk/store) or monkeypatched internals; no named live bug, live-config contract, or pure logic survives. |
| tests/unit/test_attack_data_identity.py | 69 | Offline end-to-end flows with mocked/patched I/O (httpx/subprocess/docker/Splunk/store) or monkeypatched internals; no named live bug, live-config contract, or pure logic survives. |
| tests/unit/test_bench_cad_probe_think.py | 83 | Tests of tooling off the product path (scripts/ or tests/ harness); mock-I/O / offline flows (delete clause: tooling scripts). |
| tests/unit/test_bench_capability_cli.py | 54 | Tests of tooling off the product path (scripts/ or tests/ harness); mock-I/O / offline flows (delete clause: tooling scripts). |
| tests/unit/test_bench_config_coverage.py | 123 | Tests of tooling off the product path (scripts/ or tests/ harness); mock-I/O / offline flows (delete clause: tooling scripts). |
| tests/unit/test_bench_repair.py | 326 | Tests of tooling off the product path (scripts/ or tests/ harness); mock-I/O / offline flows (delete clause: tooling scripts). |
| tests/unit/test_bench_supervisor.py | 368 | Tests of tooling off the product path (scripts/ or tests/ harness); mock-I/O / offline flows (delete clause: tooling scripts). |
| tests/unit/test_build_specimen_corpus_v3.py | 42 | Tests of tooling off the product path (scripts/ or tests/ harness); mock-I/O / offline flows (delete clause: tooling scripts). |
| tests/unit/test_cad_gauntlet_scoring.py | 26 | Tests of tooling off the product path (scripts/ or tests/ harness); mock-I/O / offline flows (delete clause: tooling scripts). |
| tests/unit/test_cad_generate_part.py | 75 | Offline end-to-end flows with mocked/patched I/O (httpx/subprocess/docker/Splunk/store) or monkeypatched internals; no named live bug, live-config contract, or pure logic survives. |
| tests/unit/test_cad_grader.py | 73 | Tests of tooling off the product path (scripts/ or tests/ harness); mock-I/O / offline flows (delete clause: tooling scripts). |
| tests/unit/test_cad_loop.py | 121 | Offline end-to-end flows with mocked/patched I/O (httpx/subprocess/docker/Splunk/store) or monkeypatched internals; no named live bug, live-config contract, or pure logic survives. |
| tests/unit/test_cad_render_fallback.py | 57 | Offline end-to-end flows with mocked/patched I/O (httpx/subprocess/docker/Splunk/store) or monkeypatched internals; no named live bug, live-config contract, or pure logic survives. |
| tests/unit/test_calibrate_builder.py | 272 | Offline end-to-end flows with mocked/patched I/O (httpx/subprocess/docker/Splunk/store) or monkeypatched internals; no named live bug, live-config contract, or pure logic survives. |
| tests/unit/test_cam_lds_extract.py | 375 | Tests of tooling off the product path (scripts/ or tests/ harness); mock-I/O / offline flows (delete clause: tooling scripts). |
| tests/unit/test_cancellation_w3.py | 285 | Offline disconnect flows over real local sockets/threads + fake seats; feat commit, no named live-bug pin (W3 is a workstream). |
| tests/unit/test_capability_probe.py | 34 | Tests of tooling off the product path (scripts/ or tests/ harness); mock-I/O / offline flows (delete clause: tooling scripts). |
| tests/unit/test_check_model_bindings.py | 123 | Tests of tooling off the product path (scripts/ or tests/ harness); mock-I/O / offline flows (delete clause: tooling scripts). |
| tests/unit/test_check_updates.py | 763 | Tests of tooling off the product path (scripts/ or tests/ harness); mock-I/O / offline flows (delete clause: tooling scripts). |
| tests/unit/test_code_sandbox_sessions.py | 192 | Offline end-to-end flows with mocked/patched I/O (httpx/subprocess/docker/Splunk/store) or monkeypatched internals; no named live bug, live-config contract, or pure logic survives. |
| tests/unit/test_coding_fixtures.py | 76 | Tests of tooling off the product path (scripts/ or tests/ harness); mock-I/O / offline flows (delete clause: tooling scripts). |
| tests/unit/test_complexity_budget.py | 116 | Tests of tooling off the product path (scripts/ or tests/ harness); mock-I/O / offline flows (delete clause: tooling scripts). |
| tests/unit/test_compliance_acceptance_currency.py | 361 | Tests of tooling off the product path (scripts/ or tests/ harness); mock-I/O / offline flows (delete clause: tooling scripts). |
| tests/unit/test_compliance_assertions.py | 205 | Tests of tooling off the product path (scripts/ or tests/ harness); mock-I/O / offline flows (delete clause: tooling scripts). |
| tests/unit/test_compliance_assessment_runs.py | 231 | Offline end-to-end flows with mocked/patched I/O (httpx/subprocess/docker/Splunk/store) or monkeypatched internals; no named live bug, live-config contract, or pure logic survives. |
| tests/unit/test_compliance_candidate_closure.py | 222 | Offline end-to-end flows with mocked/patched I/O (httpx/subprocess/docker/Splunk/store) or monkeypatched internals; no named live bug, live-config contract, or pure logic survives. |
| tests/unit/test_compliance_council.py | 284 | Injects a fake model seat (_fake) into run_council — mocks inference I/O; no named live bug (Y09/Y04 are check ids). |
| tests/unit/test_compliance_draft_revisions.py | 77 | Offline end-to-end flows with mocked/patched I/O (httpx/subprocess/docker/Splunk/store) or monkeypatched internals; no named live bug, live-config contract, or pure logic survives. |
| tests/unit/test_compliance_dual_document.py | 350 | Offline end-to-end flows with mocked/patched I/O (httpx/subprocess/docker/Splunk/store) or monkeypatched internals; no named live bug, live-config contract, or pure logic survives. |
| tests/unit/test_compliance_fixtures.py | 77 | Tests of tooling off the product path (scripts/ or tests/ harness); mock-I/O / offline flows (delete clause: tooling scripts). |
| tests/unit/test_compliance_gaps_live.py | 136 | Offline end-to-end flows with mocked/patched I/O (httpx/subprocess/docker/Splunk/store) or monkeypatched internals; no named live bug, live-config contract, or pure logic survives. |
| tests/unit/test_compliance_judgment_contract_v2.py | 149 | Tests of tooling off the product path (scripts/ or tests/ harness); mock-I/O / offline flows (delete clause: tooling scripts). |
| tests/unit/test_compliance_judgment_r1_experiment.py | 67 | Tests of tooling off the product path (scripts/ or tests/ harness); mock-I/O / offline flows (delete clause: tooling scripts). |
| tests/unit/test_compliance_migrate_legacy.py | 159 | Offline end-to-end flows with mocked/patched I/O (httpx/subprocess/docker/Splunk/store) or monkeypatched internals; no named live bug, live-config contract, or pure logic survives. |
| tests/unit/test_compliance_operator_text_audit.py | 314 | Tests of tooling off the product path (scripts/ or tests/ harness); mock-I/O / offline flows (delete clause: tooling scripts). |
| tests/unit/test_compliance_p6r_amendment1.py | 122 | Tests of tooling off the product path (scripts/ or tests/ harness); mock-I/O / offline flows (delete clause: tooling scripts). |
| tests/unit/test_compliance_p6r_measurement.py | 337 | Tests of tooling off the product path (scripts/ or tests/ harness); mock-I/O / offline flows (delete clause: tooling scripts). |
| tests/unit/test_compliance_payload_tools.py | 238 | Offline end-to-end flows with mocked/patched I/O (httpx/subprocess/docker/Splunk/store) or monkeypatched internals; no named live bug, live-config contract, or pure logic survives. |
| tests/unit/test_compliance_propose.py | 377 | Offline coverage-retrieval flows through a wired fake rerank transport; no dated/numbered live-bug pin. |
| tests/unit/test_compliance_prospective.py | 76 | Offline end-to-end flows with mocked/patched I/O (httpx/subprocess/docker/Splunk/store) or monkeypatched internals; no named live bug, live-config contract, or pure logic survives. |
| tests/unit/test_compliance_public_text.py | 101 | Tests of tooling off the product path (scripts/ or tests/ harness); mock-I/O / offline flows (delete clause: tooling scripts). |
| tests/unit/test_compliance_public_text_changed_only.py | 105 | Tests of tooling off the product path (scripts/ or tests/ harness); mock-I/O / offline flows (delete clause: tooling scripts). |
| tests/unit/test_compliance_quote_fidelity_and_snapshot.py | 109 | Tests of tooling off the product path (scripts/ or tests/ harness); mock-I/O / offline flows (delete clause: tooling scripts). |
| tests/unit/test_compliance_reading_boundaries.py | 265 | Offline end-to-end flows with mocked/patched I/O (httpx/subprocess/docker/Splunk/store) or monkeypatched internals; no named live bug, live-config contract, or pure logic survives. |
| tests/unit/test_compliance_reading_live_runner.py | 102 | Tests of tooling off the product path (scripts/ or tests/ harness); mock-I/O / offline flows (delete clause: tooling scripts). |
| tests/unit/test_compliance_reading_truth_tools.py | 493 | Tests of tooling off the product path (scripts/ or tests/ harness); mock-I/O / offline flows (delete clause: tooling scripts). |
| tests/unit/test_compliance_recapture_guard.py | 45 | Tests of tooling off the product path (scripts/ or tests/ harness); mock-I/O / offline flows (delete clause: tooling scripts). |
| tests/unit/test_compliance_requirement_scope.py | 430 | Offline end-to-end flows with mocked/patched I/O (httpx/subprocess/docker/Splunk/store) or monkeypatched internals; no named live bug, live-config contract, or pure logic survives. |
| tests/unit/test_compliance_requirement_scoping.py | 492 | Offline end-to-end flows with mocked/patched I/O (httpx/subprocess/docker/Splunk/store) or monkeypatched internals; no named live bug, live-config contract, or pure logic survives. |
| tests/unit/test_compliance_rewrite_integrity.py | 177 | Tests of tooling off the product path (scripts/ or tests/ harness); mock-I/O / offline flows (delete clause: tooling scripts). |
| tests/unit/test_compliance_search_pushdown.py | 465 | Offline end-to-end flows with mocked/patched I/O (httpx/subprocess/docker/Splunk/store) or monkeypatched internals; no named live bug, live-config contract, or pure logic survives. |
| tests/unit/test_compliance_section_index.py | 409 | Offline end-to-end flows with mocked/patched I/O (httpx/subprocess/docker/Splunk/store) or monkeypatched internals; no named live bug, live-config contract, or pure logic survives. |
| tests/unit/test_compliance_vertical_slice.py | 161 | Offline end-to-end flows with mocked/patched I/O (httpx/subprocess/docker/Splunk/store) or monkeypatched internals; no named live bug, live-config contract, or pure logic survives. |
| tests/unit/test_corpus_reingest.py | 1545 | Tests of tooling off the product path (scripts/ or tests/ harness); mock-I/O / offline flows (delete clause: tooling scripts). |
| tests/unit/test_council_bench.py | 336 | Tests of tooling off the product path (scripts/ or tests/ harness); mock-I/O / offline flows (delete clause: tooling scripts). |
| tests/unit/test_direct_engine_diagnostic_gate.py | 64 | Monkeypatched switch/gate steering; architectural guard, no named live bug or live-config contract. |
| tests/unit/test_eg2_embedding_server.py | 217 | Tests of tooling off the product path (scripts/ or tests/ harness); mock-I/O / offline flows (delete clause: tooling scripts). |
| tests/unit/test_embedding_consumers_harness.py | 130 | Tests of tooling off the product path (scripts/ or tests/ harness); mock-I/O / offline flows (delete clause: tooling scripts). |
| tests/unit/test_engine_autoupdate.py | 409 | Tests of tooling off the product path (scripts/ or tests/ harness); mock-I/O / offline flows (delete clause: tooling scripts). |
| tests/unit/test_engine_contract_check.py | 109 | Tests of tooling off the product path (scripts/ or tests/ harness); mock-I/O / offline flows (delete clause: tooling scripts). |
| tests/unit/test_eval_workspace_hygiene.py | 115 | Tests of tooling off the product path (scripts/ or tests/ harness); mock-I/O / offline flows (delete clause: tooling scripts). |
| tests/unit/test_expected_models.py | 50 | Tests of tooling off the product path (scripts/ or tests/ harness); mock-I/O / offline flows (delete clause: tooling scripts). |
| tests/unit/test_fetch_mlx_asr_models.py | 141 | Tests of tooling off the product path (scripts/ or tests/ harness); mock-I/O / offline flows (delete clause: tooling scripts). |
| tests/unit/test_gate_c_calculator.py | 458 | Tests of tooling off the product path (scripts/ or tests/ harness); mock-I/O / offline flows (delete clause: tooling scripts). |
| tests/unit/test_graph_memory_eg2.py | 135 | Fake embedder/store fixtures + tmp_path re-embed flows; mocks I/O. |
| tests/unit/test_health_checked.py | 31 | Offline end-to-end flows with mocked/patched I/O (httpx/subprocess/docker/Splunk/store) or monkeypatched internals; no named live bug, live-config contract, or pure logic survives. |
| tests/unit/test_host_quiet.py | 354 | Tests of tooling off the product path (scripts/ or tests/ harness); mock-I/O / offline flows (delete clause: tooling scripts). |
| tests/unit/test_hunt_driver.py | 117 | Tests of tooling off the product path (scripts/ or tests/ harness); mock-I/O / offline flows (delete clause: tooling scripts). |
| tests/unit/test_hunt_env_resolve.py | 344 | Offline end-to-end flows with mocked/patched I/O (httpx/subprocess/docker/Splunk/store) or monkeypatched internals; no named live bug, live-config contract, or pure logic survives. |
| tests/unit/test_hunt_judge.py | 210 | Offline end-to-end flows with mocked/patched I/O (httpx/subprocess/docker/Splunk/store) or monkeypatched internals; no named live bug, live-config contract, or pure logic survives. |
| tests/unit/test_hunt_judged_runner.py | 677 | Tests of tooling off the product path (scripts/ or tests/ harness); mock-I/O / offline flows (delete clause: tooling scripts). |
| tests/unit/test_hunt_product_path.py | 877 | Offline hunt job flows with monkeypatched runners/fake judge+client; the two no-arg tests inject fakes. |
| tests/unit/test_hunt_run_injection.py | 254 | Offline end-to-end flows with mocked/patched I/O (httpx/subprocess/docker/Splunk/store) or monkeypatched internals; no named live bug, live-config contract, or pure logic survives. |
| tests/unit/test_image_security_update.py | 331 | Tests of tooling off the product path (scripts/ or tests/ harness); mock-I/O / offline flows (delete clause: tooling scripts). |
| tests/unit/test_import_environment.py | 36 | Tests of tooling off the product path (scripts/ or tests/ harness); mock-I/O / offline flows (delete clause: tooling scripts). |
| tests/unit/test_intent_eval.py | 36 | Tests of tooling off the product path (scripts/ or tests/ harness); mock-I/O / offline flows (delete clause: tooling scripts). |
| tests/unit/test_lab_exec_posture.py | 73 | Tests of tooling off the product path (scripts/ or tests/ harness); mock-I/O / offline flows (delete clause: tooling scripts). |
| tests/unit/test_lab_setup.py | 301 | Tests of tooling off the product path (scripts/ or tests/ harness); mock-I/O / offline flows (delete clause: tooling scripts). |
| tests/unit/test_launchd_plist_install.py | 155 | Tests of tooling off the product path (scripts/ or tests/ harness); mock-I/O / offline flows (delete clause: tooling scripts). |
| tests/unit/test_launchd_reload.py | 295 | Tests of tooling off the product path (scripts/ or tests/ harness); mock-I/O / offline flows (delete clause: tooling scripts). |

## Split files (keepers only; path — lines removed — kept tests — keep rule / deleted portion)

| Path | Lines removed | Kept | Keep rule for kept tests; deleted portion |
|---|---|---|---|
| tests/unit/test_arm_escalation.py | 1494 | 6 | K3 pure logic over values (parsers/scorers/ranking/contracts); K2 where the keeper reads committed config/register. Deleted: mock/patch-I/O and offline end-to-end tests. |
| tests/unit/test_attachment_paths.py | 184 | 12 | K1 (OWUI attachment-path defect, fix cb0011b94) + K2 seeded filter spec. Deleted: mock/patch-I/O and offline end-to-end tests. |
| tests/unit/test_b123d_emitter.py | 75 | 5 | K3 pure logic over values (parsers/scorers/ranking/contracts); K2 where the keeper reads committed config/register. Deleted: mock/patch-I/O and offline end-to-end tests. |
| tests/unit/test_backend_registry_health.py | 444 | 1 | K2 shipped config preferred_residents warms auto-daily. Deleted: mock/patch-I/O and offline end-to-end tests. |
| tests/unit/test_bench_skip.py | 55 | 1 | K2 real backends.yaml pipeline_bench_skip consistency. Deleted: mock/patch-I/O and offline end-to-end tests. |
| tests/unit/test_cad_b123d_bridge.py | 171 | 3 | K3 pure logic over values (parsers/scorers/ranking/contracts); K2 where the keeper reads committed config/register. Deleted: mock/patch-I/O and offline end-to-end tests. |
| tests/unit/test_cad_capabilities.py | 8 | 2 | K3 pure logic over values (parsers/scorers/ranking/contracts); K2 where the keeper reads committed config/register. Deleted: mock/patch-I/O and offline end-to-end tests. |
| tests/unit/test_cad_coverage_corpus.py | 24 | 1 | K3 pure logic over values (parsers/scorers/ranking/contracts); K2 where the keeper reads committed config/register. Deleted: mock/patch-I/O and offline end-to-end tests. |
| tests/unit/test_cad_ir_bases.py | 44 | 3 | K3 pure logic over values (parsers/scorers/ranking/contracts); K2 where the keeper reads committed config/register. Deleted: mock/patch-I/O and offline end-to-end tests. |
| tests/unit/test_cad_schema_parity.py | 69 | 1 | K3 pure logic over values (parsers/scorers/ranking/contracts); K2 where the keeper reads committed config/register. Deleted: mock/patch-I/O and offline end-to-end tests. |
| tests/unit/test_candidate_eval.py | 38 | 1 | K3 pure logic over values (parsers/scorers/ranking/contracts); K2 where the keeper reads committed config/register. Deleted: mock/patch-I/O and offline end-to-end tests. |
| tests/unit/test_capability_lib.py | 118 | 12 | K1 V10 receipt (v10_candidates_20260629T194541Z.json) preamble/decoy-number regressions. Deleted: mock/patch-I/O and offline end-to-end tests. |
| tests/unit/test_capacity_fallback.py | 145 | 1 | K3 pure logic over values (parsers/scorers/ranking/contracts); K2 where the keeper reads committed config/register. Deleted: mock/patch-I/O and offline end-to-end tests. |
| tests/unit/test_catalog_schema.py | 70 | 10 | K2 persona catalog schema + live persona/workspace checks. Deleted: mock/patch-I/O and offline end-to-end tests. |
| tests/unit/test_channels.py | 632 | 7 | K2 MCP manifest/registered-name parity + channel workspace map + dispatcher workspace coverage. Deleted: mock/patch-I/O and offline end-to-end tests. |
| tests/unit/test_chunking_5tuple.py | 23 | 1 | K3 pure logic over values (parsers/scorers/ranking/contracts); K2 where the keeper reads committed config/register. Deleted: mock/patch-I/O and offline end-to-end tests. |
| tests/unit/test_compliance_analyze_live.py | 80 | 2 | K3 pure logic over values (parsers/scorers/ranking/contracts); K2 where the keeper reads committed config/register. Deleted: mock/patch-I/O and offline end-to-end tests. |
| tests/unit/test_compliance_assessment_source.py | 317 | 14 | K3 pure logic over values (parsers/scorers/ranking/contracts); K2 where the keeper reads committed config/register. Deleted: mock/patch-I/O and offline end-to-end tests. |
| tests/unit/test_compliance_authority_surfaces.py | 192 | 1 | K1 coverage.py:550 Measures false-positive shape. Deleted: mock/patch-I/O and offline end-to-end tests. |
| tests/unit/test_compliance_capture.py | 209 | 3 | K3 pure logic over values (parsers/scorers/ranking/contracts); K2 where the keeper reads committed config/register. Deleted: mock/patch-I/O and offline end-to-end tests. |
| tests/unit/test_compliance_change_pipeline.py | 444 | 8 | K3 pure register diff + K1 ambient-machine-state impact regression. Deleted: mock/patch-I/O and offline end-to-end tests. |
| tests/unit/test_compliance_citation_by_quote.py | 216 | 12 | K3 pure logic over values (parsers/scorers/ranking/contracts); K2 where the keeper reads committed config/register. Deleted: mock/patch-I/O and offline end-to-end tests. |
| tests/unit/test_compliance_citation_integrity.py | 218 | 2 | K3 pure logic over values (parsers/scorers/ranking/contracts); K2 where the keeper reads committed config/register. Deleted: mock/patch-I/O and offline end-to-end tests. |
| tests/unit/test_compliance_currency.py | 98 | 1 | K1 F02 next-version enumeration + K3 never-infer enforcement date. Deleted: mock/patch-I/O and offline end-to-end tests. |
| tests/unit/test_compliance_data_truth_instruments.py | 554 | 24 | K3 pure logic over values (parsers/scorers/ranking/contracts); K2 where the keeper reads committed config/register. Deleted: mock/patch-I/O and offline end-to-end tests. |
| tests/unit/test_compliance_engine.py | 122 | 10 | K3 pure logic over values (parsers/scorers/ranking/contracts); K2 where the keeper reads committed config/register. Deleted: mock/patch-I/O and offline end-to-end tests. |
| tests/unit/test_compliance_eval_instance.py | 137 | 3 | K1 Live 2026-10-15/16 tilde-root/planted-corpus/register-capture defects. Deleted: mock/patch-I/O and offline end-to-end tests. |
| tests/unit/test_compliance_evaluation.py | 266 | 1 | K3 pure logic over values (parsers/scorers/ranking/contracts); K2 where the keeper reads committed config/register. Deleted: mock/patch-I/O and offline end-to-end tests. |
| tests/unit/test_compliance_gate.py | 6 | 5 | K3 pure logic over values (parsers/scorers/ranking/contracts); K2 where the keeper reads committed config/register. Deleted: mock/patch-I/O and offline end-to-end tests. |
| tests/unit/test_compliance_glossary.py | 141 | 6 | K3 pure logic over values (parsers/scorers/ranking/contracts); K2 where the keeper reads committed config/register. Deleted: mock/patch-I/O and offline end-to-end tests. |
| tests/unit/test_compliance_internal_corpus.py | 372 | 13 | K3 pure parsing + K1 D-DT-19 F-R-1 revision-log rows. Deleted: mock/patch-I/O and offline end-to-end tests. |
| tests/unit/test_compliance_mapping_store_consolidation.py | 74 | 1 | K3 pure logic over values (parsers/scorers/ranking/contracts); K2 where the keeper reads committed config/register. Deleted: mock/patch-I/O and offline end-to-end tests. |
| tests/unit/test_compliance_mcp.py | 195 | 4 | K3 compact citation/projection + K1 mode=material AnswerContract leak. Deleted: mock/patch-I/O and offline end-to-end tests. |
| tests/unit/test_compliance_nerc_source_sync.py | 262 | 1 | K3 pure logic over values (parsers/scorers/ranking/contracts); K2 where the keeper reads committed config/register. Deleted: mock/patch-I/O and offline end-to-end tests. |
| tests/unit/test_compliance_obligation_alignment.py | 223 | 3 | K3 pure logic over values (parsers/scorers/ranking/contracts); K2 where the keeper reads committed config/register. Deleted: mock/patch-I/O and offline end-to-end tests. |
| tests/unit/test_compliance_operations.py | 326 | 5 | K3 pure logic over values (parsers/scorers/ranking/contracts); K2 where the keeper reads committed config/register. Deleted: mock/patch-I/O and offline end-to-end tests. |
| tests/unit/test_compliance_operator_traceability.py | 283 | 10 | K3 pure logic over values (parsers/scorers/ranking/contracts); K2 where the keeper reads committed config/register. Deleted: mock/patch-I/O and offline end-to-end tests. |
| tests/unit/test_compliance_planner.py | 71 | 3 | K3 pure question routing/plan ops/unrun-step guard (fake-seat tests dropped). Deleted: mock/patch-I/O and offline end-to-end tests. |
| tests/unit/test_compliance_prove_then_scale.py | 385 | 2 | K3 pure logic over values (parsers/scorers/ranking/contracts); K2 where the keeper reads committed config/register. Deleted: mock/patch-I/O and offline end-to-end tests. |
| tests/unit/test_compliance_reader.py | 720 | 12 | K3 pure logic over values (parsers/scorers/ranking/contracts); K2 where the keeper reads committed config/register. Deleted: mock/patch-I/O and offline end-to-end tests. |
| tests/unit/test_compliance_reading_acceptance.py | 1204 | 1 | K3 pure dependent-annotation invalidation. Deleted: mock/patch-I/O and offline end-to-end tests. |
| tests/unit/test_compliance_reading_assembly.py | 241 | 3 | K3 pure logic over values (parsers/scorers/ranking/contracts); K2 where the keeper reads committed config/register. Deleted: mock/patch-I/O and offline end-to-end tests. |
| tests/unit/test_compliance_reading_transport.py | 277 | 5 | K3 inline-reasoning strip + K1 case-10 think-key invariant / measured default effort. Deleted: mock/patch-I/O and offline end-to-end tests. |
| tests/unit/test_compliance_reasoning_v2_regressions.py | 27 | 10 | K1 numbered findings F01/F02/F05/F06/F09 (receipt REASONING_V2_BASELINE.md). Deleted: mock/patch-I/O and offline end-to-end tests. |
| tests/unit/test_compliance_regulatory_bundle.py | 203 | 1 | K3 pure logic over values (parsers/scorers/ranking/contracts); K2 where the keeper reads committed config/register. Deleted: mock/patch-I/O and offline end-to-end tests. |
| tests/unit/test_compliance_regulatory_corpus.py | 159 | 3 | K3 pure logic over values (parsers/scorers/ranking/contracts); K2 where the keeper reads committed config/register. Deleted: mock/patch-I/O and offline end-to-end tests. |
| tests/unit/test_compliance_relevance_arbiter.py | 109 | 2 | K1 stage-3 silent-non-match regression + K3 band gating. Deleted: mock/patch-I/O and offline end-to-end tests. |
| tests/unit/test_compliance_repository.py | 387 | 1 | K1 CORRECTED-branch coverage-not-status regression. Deleted: mock/patch-I/O and offline end-to-end tests. |
| tests/unit/test_compliance_requirement_anchor.py | 450 | 5 | K3 pure logic over values (parsers/scorers/ranking/contracts); K2 where the keeper reads committed config/register. Deleted: mock/patch-I/O and offline end-to-end tests. |
| tests/unit/test_compliance_result_contract.py | 125 | 13 | K3 pure result vocabulary/contract + K1 unregistered-disagreement-code regression. Deleted: mock/patch-I/O and offline end-to-end tests. |
| tests/unit/test_compliance_retrieval_seam.py | 77 | 1 | K3 pure logic over values (parsers/scorers/ranking/contracts); K2 where the keeper reads committed config/register. Deleted: mock/patch-I/O and offline end-to-end tests. |
| tests/unit/test_compliance_review_queue.py | 16 | 5 | K3 pure logic over values (parsers/scorers/ranking/contracts); K2 where the keeper reads committed config/register. Deleted: mock/patch-I/O and offline end-to-end tests. |
| tests/unit/test_compliance_scenarios.py | 24 | 1 | K3 pure logic over values (parsers/scorers/ranking/contracts); K2 where the keeper reads committed config/register. Deleted: mock/patch-I/O and offline end-to-end tests. |
| tests/unit/test_compliance_sources.py | 128 | 1 | K1 live P8-L alias-path logical-id gap. Deleted: mock/patch-I/O and offline end-to-end tests. |
| tests/unit/test_compliance_technical_basis.py | 257 | 3 | K3 pure logic over values (parsers/scorers/ranking/contracts); K2 where the keeper reads committed config/register. Deleted: mock/patch-I/O and offline end-to-end tests. |
| tests/unit/test_compliance_temporal_projections.py | 322 | 1 | K3 pure logic over values (parsers/scorers/ranking/contracts); K2 where the keeper reads committed config/register. Deleted: mock/patch-I/O and offline end-to-end tests. |
| tests/unit/test_compliance_v3_contract.py | 38 | 1 | K3 pure logic over values (parsers/scorers/ranking/contracts); K2 where the keeper reads committed config/register. Deleted: mock/patch-I/O and offline end-to-end tests. |
| tests/unit/test_compliance_v3_matrices.py | 478 | 11 | K3 pure A/Q acceptance-case logic over values (matrix-completeness meta-test dropped). Deleted: mock/patch-I/O and offline end-to-end tests. |
| tests/unit/test_compliance_vocabulary_bridge.py | 6 | 5 | K3 pure vocabulary derivation/alignment over the register. Deleted: mock/patch-I/O and offline end-to-end tests. |
| tests/unit/test_compliance_y21_error_classes.py | 23 | 8 | K1 adjudicated council error classes P6J-12/14/19 (y21_adjudication.json). Deleted: mock/patch-I/O and offline end-to-end tests. |
| tests/unit/test_compliance_y23_variants.py | 47 | 4 | K1 Y21/Y23 prompt-variant contract (distinct prompts, output contract, trigger). Deleted: mock/patch-I/O and offline end-to-end tests. |
| tests/unit/test_config_ollama_url.py | 75 | 2 | K2 live portal.yaml/backends.yaml ollama_url contract. Deleted: mock/patch-I/O and offline end-to-end tests. |
| tests/unit/test_config_schema.py | 56 | 18 | K2 portal.yaml schema validator (ports, ids, model schema, runtime flags). Deleted: mock/patch-I/O and offline end-to-end tests. |
| tests/unit/test_context_overflow_guard.py | 432 | 5 | K1 Live 2026-11-16 truncation/trace defects + K3 conservative estimate. Deleted: mock/patch-I/O and offline end-to-end tests. |
| tests/unit/test_corpus_truth_key.py | 42 | 9 | K3 pure logic over values (parsers/scorers/ranking/contracts); K2 where the keeper reads committed config/register. Deleted: mock/patch-I/O and offline end-to-end tests. |
| tests/unit/test_council_review.py | 729 | 10 | K3 opinion parsing/quorum/dissent + K2 production council config. Deleted: mock/patch-I/O and offline end-to-end tests. |
| tests/unit/test_council_speed.py | 660 | 11 | K3 coded-decision lock rules + override validation + K2 production speed defaults. Deleted: mock/patch-I/O and offline end-to-end tests. |
| tests/unit/test_detector_precision.py | 25 | 13 | K3 numeric detector + K2 live wiki store/source integrity. Deleted: mock/patch-I/O and offline end-to-end tests. |
| tests/unit/test_document_mcp.py | 442 | 18 | K2 tool manifest + K1 named schema defects (create_excel title, Qwen title/text, file_name/file). Deleted: mock/patch-I/O and offline end-to-end tests. |
| tests/unit/test_embeddings_route.py | 286 | 1 | K3 pure logic over values (parsers/scorers/ranking/contracts); K2 where the keeper reads committed config/register. Deleted: mock/patch-I/O and offline end-to-end tests. |
| tests/unit/test_engine_call_metrics.py | 355 | 1 | K3 pure logic over values (parsers/scorers/ranking/contracts); K2 where the keeper reads committed config/register. Deleted: mock/patch-I/O and offline end-to-end tests. |
| tests/unit/test_eval_scope.py | 256 | 9 | K3 pure scope binding + K1 REST-403 ScopeError-escape defect. Deleted: mock/patch-I/O and offline end-to-end tests. |
| tests/unit/test_exposed_workspace_variants.py | 139 | 2 | K3 pure logic over values (parsers/scorers/ranking/contracts); K2 where the keeper reads committed config/register. Deleted: mock/patch-I/O and offline end-to-end tests. |
| tests/unit/test_fleet_consolidate.py | 671 | 2 | K2 read-only live-config keep/remove guarantees. Deleted: mock/patch-I/O and offline end-to-end tests. |
| tests/unit/test_followup_artifact_tool.py | 314 | 9 | K3 pure followup/link logic + K1 case 032 turn-0 / earlier-turn real-file link. Deleted: mock/patch-I/O and offline end-to-end tests. |
| tests/unit/test_generated_artifacts_fresh.py | 114 | 6 | K2 sync-config idempotency + workspace_routing/.mcp.json/OWUI preset consistency. Deleted: mock/patch-I/O and offline end-to-end tests. |
| tests/unit/test_hunt_baselines.py | 101 | 7 | K3 pure logic over values (parsers/scorers/ranking/contracts); K2 where the keeper reads committed config/register. Deleted: mock/patch-I/O and offline end-to-end tests. |
| tests/unit/test_hunt_bounded.py | 671 | 4 | K1 Wheeler's fatal row-cap read + K3 pure time normalization. Deleted: mock/patch-I/O and offline end-to-end tests. |
| tests/unit/test_hunt_case_focus.py | 517 | 11 | K3 pure logic over values (parsers/scorers/ranking/contracts); K2 where the keeper reads committed config/register. Deleted: mock/patch-I/O and offline end-to-end tests. |
| tests/unit/test_hunt_discovery.py | 319 | 4 | K3 pure logic over values (parsers/scorers/ranking/contracts); K2 where the keeper reads committed config/register. Deleted: mock/patch-I/O and offline end-to-end tests. |
| tests/unit/test_hunt_evidence.py | 378 | 3 | K3 pure logic over values (parsers/scorers/ranking/contracts); K2 where the keeper reads committed config/register. Deleted: mock/patch-I/O and offline end-to-end tests. |
| tests/unit/test_hunt_executor.py | 311 | 2 | K1 wheeler-shaped capped evidence read + K3 pure cut classification. Deleted: mock/patch-I/O and offline end-to-end tests. |
| tests/unit/test_hunt_graph_runner.py | 313 | 5 | K3 pure logic over values (parsers/scorers/ranking/contracts); K2 where the keeper reads committed config/register. Deleted: mock/patch-I/O and offline end-to-end tests. |
| tests/unit/test_hunt_knowledge.py | 255 | 1 | K3 pure logic over values (parsers/scorers/ranking/contracts); K2 where the keeper reads committed config/register. Deleted: mock/patch-I/O and offline end-to-end tests. |
| tests/unit/test_hunt_manifest.py | 297 | 9 | K3 pure logic over values (parsers/scorers/ranking/contracts); K2 where the keeper reads committed config/register. Deleted: mock/patch-I/O and offline end-to-end tests. |
| tests/unit/test_hunt_notables.py | 330 | 22 | K3 pure logic over values (parsers/scorers/ranking/contracts); K2 where the keeper reads committed config/register. Deleted: mock/patch-I/O and offline end-to-end tests. |
| tests/unit/test_hunt_notables_backpressure.py | 204 | 2 | K3 pure logic over values (parsers/scorers/ranking/contracts); K2 where the keeper reads committed config/register. Deleted: mock/patch-I/O and offline end-to-end tests. |
| tests/unit/test_hunt_notables_behaviours.py | 234 | 13 | K3 pure logic over values (parsers/scorers/ranking/contracts); K2 where the keeper reads committed config/register. Deleted: mock/patch-I/O and offline end-to-end tests. |
| tests/unit/test_hunt_notables_generators.py | 131 | 12 | K3 pure logic over values (parsers/scorers/ranking/contracts); K2 where the keeper reads committed config/register. Deleted: mock/patch-I/O and offline end-to-end tests. |
| tests/unit/test_hunt_notables_judge.py | 210 | 1 | K3 pure logic over values (parsers/scorers/ranking/contracts); K2 where the keeper reads committed config/register. Deleted: mock/patch-I/O and offline end-to-end tests. |
| tests/unit/test_hunt_notables_merge.py | 144 | 10 | K3 pure logic over values (parsers/scorers/ranking/contracts); K2 where the keeper reads committed config/register. Deleted: mock/patch-I/O and offline end-to-end tests. |
| tests/unit/test_hunt_notables_misfit.py | 265 | 1 | K3 pure logic over values (parsers/scorers/ranking/contracts); K2 where the keeper reads committed config/register. Deleted: mock/patch-I/O and offline end-to-end tests. |
| tests/unit/test_hunt_notables_similarity.py | 403 | 1 | K3 pure logic over values (parsers/scorers/ranking/contracts); K2 where the keeper reads committed config/register. Deleted: mock/patch-I/O and offline end-to-end tests. |
| tests/unit/test_hunt_observations.py | 222 | 10 | K3 pure logic over values (parsers/scorers/ranking/contracts); K2 where the keeper reads committed config/register. Deleted: mock/patch-I/O and offline end-to-end tests. |
| tests/unit/test_hunt_order.py | 297 | 2 | K3 pure logic over values (parsers/scorers/ranking/contracts); K2 where the keeper reads committed config/register. Deleted: mock/patch-I/O and offline end-to-end tests. |
| tests/unit/test_hunt_relate.py | 418 | 18 | K3 pure logic over values (parsers/scorers/ranking/contracts); K2 where the keeper reads committed config/register. Deleted: mock/patch-I/O and offline end-to-end tests. |
| tests/unit/test_hunt_rerank.py | 331 | 7 | K3 pure logic over values (parsers/scorers/ranking/contracts); K2 where the keeper reads committed config/register. Deleted: mock/patch-I/O and offline end-to-end tests. |
| tests/unit/test_hunt_scoreboard.py | 686 | 3 | K3 pure logic over values (parsers/scorers/ranking/contracts); K2 where the keeper reads committed config/register. Deleted: mock/patch-I/O and offline end-to-end tests. |
| tests/unit/test_hunt_stage2.py | 170 | 3 | K3 pure logic over values (parsers/scorers/ranking/contracts); K2 where the keeper reads committed config/register. Deleted: mock/patch-I/O and offline end-to-end tests. |
| tests/unit/test_hunt_tool_result_size.py | 88 | 1 | K3 pure logic over values (parsers/scorers/ranking/contracts); K2 where the keeper reads committed config/register. Deleted: mock/patch-I/O and offline end-to-end tests. |
| tests/unit/test_hunt_wire.py | 204 | 4 | K3 pure logic over values (parsers/scorers/ranking/contracts); K2 where the keeper reads committed config/register. Deleted: mock/patch-I/O and offline end-to-end tests. |
| tests/unit/test_load_guard.py | 2528 | 9 | K1 dated canary/R2/R4/2026-11-16 admission defects + K3 pure admission math. Deleted: mock/patch-I/O and offline end-to-end tests. |

## Kept whole (path — lines — keep rule)

| Path | Lines | Keep rule |
|---|---|---|
| tests/unit/test_arm_job_specs.py | 469 | K2 — validates the committed config/arm_jobs/ specs the arm runner loads (schema, plan existence, canary gating). |
| tests/unit/test_bully_field_roles_time_parse.py | 82 | K1+K3 — pins the 2026-11-07 live Zulu/UTC strptime defect (six-hour offset on a Central host); pure parser. |
| tests/unit/test_calibration_slice.py | 45 | K3 — pure intake/funnel/pipeline logic over values (self-window basis refusal); fake builder is pure data, no I/O. |
| tests/unit/test_candidates_probe_max_tokens.py | 51 | K1 (N-3, fix c31208bc5) — candidates probe leaves max_tokens to the seat. |
| tests/unit/test_cip_register.py | 179 | K2 — fidelity/completeness contract of the committed nerc_cip_register.json the compliance engine loads. |
| tests/unit/test_compliance_answer_contract.py | 95 | K1+K3 — pins the measured CIP-007-6 unused_latitude mistyped-citation case (LOAD_AND_CONVERSE_V1 §P5); pure. |
| tests/unit/test_compliance_applicability.py | 145 | K3 (+F07) — pure four-state applicability logic; pins finding F07 (corpus-derived candidate never auto-APPLIES). |
| tests/unit/test_compliance_assessment_report.py | 265 | K3+K1 — pure bounded-explanation logic; pins the null-coercion defect ('null' read as 'None'). |
| tests/unit/test_compliance_auth.py | 63 | K1 (F09) — local trusted-reviewer auth contract; pure token checks. |
| tests/unit/test_compliance_comparison.py | 105 | K3 — pure obligation-expression evaluator over values. |
| tests/unit/test_compliance_constraints.py | 86 | K3 (+F05) — pure typed constraint comparison; pins F05 (no silent cross-unit conversion). |
| tests/unit/test_compliance_docling_chunking.py | 66 | K1 — pins Y25, measured 1508/1508 chunks at page=-1 (docling strategy without read_document). |
| tests/unit/test_compliance_duty_decomposition.py | 180 | K3 — pure duty decomposition/expression logic over register text values. |
| tests/unit/test_compliance_duty_lineage.py | 137 | K3 — pure duty-text normalizer/similarity/lineage math. |
| tests/unit/test_compliance_duty_verification.py | 348 | K3 — hermetic deterministic verification layer over constructed dataclass values. |
| tests/unit/test_compliance_gate_aligned.py | 229 | K3 — pure aligned-gate packet arithmetic, no model calls. |
| tests/unit/test_compliance_governing_packet.py | 150 | K1 — pins program lesson L13 (Measures/Technical Basis were dead '' placeholders); corpus-gated. |
| tests/unit/test_compliance_ingest.py | 58 | K3 — pure derive_tier over filename strings. |
| tests/unit/test_compliance_ingest_roots.py | 114 | K1 (N-33) — compliance_ingest read-root confinement. |
| tests/unit/test_compliance_intentionality.py | 72 | K3 — pure intentionality/flexibility comparison logic. |
| tests/unit/test_compliance_machine_seat_isolation.py | 47 | K2+K1 — machine addresses resolve to bare compliance workspaces (PIPELINE_ALIGNMENT_V1 §12). |
| tests/unit/test_compliance_org_graph.py | 105 | K3 — pure org-graph parsers over in-memory markdown. |
| tests/unit/test_compliance_planted.py | 158 | K2+K3 — deterministic scoring over the committed planted corpus + register; pins F03 invariants. |
| tests/unit/test_compliance_policy_graph.py | 258 | K2+K3 — policy-graph typing invariants (Y01) over the committed register. |
| tests/unit/test_compliance_reading_judgment.py | 427 | K1 — pins acceptance case 10 (live seats answered DIFFERENT on a malformed L22 question; council verdict discarded). |
| tests/unit/test_compliance_review_decide_auth.py | 94 | K1 (F09) — compliance_review_decide requires a verified reviewer token. |
| tests/unit/test_compliance_sme_packet_kinds.py | 93 | K1 — measured 2026-09-12 (1107 OPEN items, 0 SME kinds); receipt SME_PACKET_STATE_20260912.md; pure taxonomy. |
| tests/unit/test_compliance_tiers.py | 103 | K3 (+F05) — pure authority-tier conflict detection over Span values. |
| tests/unit/test_compliance_tool_manifest_parity.py | 79 | K2+K1 — MCP tool schema parity (PIPELINE_ALIGNMENT_V1 §13 live drift). |
| tests/unit/test_config_validate.py | 66 | K2 — portal.yaml validator contract (port collisions, empty hints, bool typing). |
| tests/unit/test_council_review_bench.py | 109 | K3 — pure scorers in portal/modules/security/core/council_review_bench.py over values. |
| tests/unit/test_dependency_drift.py | 83 | K2 — lock/venv drift (uv sync --check), pyproject upper-bound receipts, installer starlette pin. |
| tests/unit/test_documents_read_refusal.py | 45 | K1 (N-23) — out-of-root read returns the tool's structured error, not an exception. |
| tests/unit/test_download_link_safety.py | 181 | K1 (fix 21d5aed12 S2 production-smoke) — only successful file creation justifies a Download link. |
| tests/unit/test_egress_aliyuncs.py | 77 | K1 (fix 62f4d83ae) — aliyuncs.com proxy domain blocked in web_fetch and browser gates. |
| tests/unit/test_failover_protection_and_empty_hop.py | 102 | K1 (P-1, fix ad353ee3d) — empty streamed tool-loop hop gets one salvaging retry; protection orders eviction. |
| tests/unit/test_failover_window_floor.py | 50 | K1+K2 — R2-29; portal.yaml/backends.yaml context-window floor consistency. |
| tests/unit/test_fallback_sampling.py | 113 | K1 (fix 32e8fce1c) — a fallback is sampled at its own card, not the seat's. |
| tests/unit/test_fara_probe_scoring.py | 48 | K1 (N-2, fix 3ce3d332b) — Fara probe credits a call only when the reply carries it. |
| tests/unit/test_graph_memory_extract.py | 32 | K1 (fix a328776e3) — extraction failures stay observable without failing the write. |
| tests/unit/test_growth_guard.py | 70 | K2 — C3 engine-declaration and behavioural-persona reason guards over live config. |
| tests/unit/test_hec_ship_dns_error.py | 71 | K1 (fix 15f6bd547 'four observed defects found during live runs') — HEC DNS failure names LAB_SPLUNK_HEC_URL. |
| tests/unit/test_hint_validator.py | 136 | K2 — workspace hint validator against the live WORKSPACES dict and backends.yaml; thinking-mode contract. |
| tests/unit/test_hunt_graph.py | 343 | K3 — pure entity-graph segmentation/co-occurrence/deviation math. |
| tests/unit/test_hunt_history.py | 57 | K3 — pure host-hour novelty weighting math. |
| tests/unit/test_judgment_probe_instrument.py | 44 | K1 — 2026-10-13 selection-bias audit instrument fixes. |
| tests/unit/test_lab_guard_shell_injection.py | 98 | K1 (fix 60ab50237) — lab guard rejects shell-injection before the sandbox call. |
| tests/unit/test_lance_guard.py | 87 | K1 (fix 5b3e2c423) — stray tree on an unmounted volume must not satisfy the lance guard. |
| tests/unit/test_lancedb_table_listing.py | 61 | K1 (A5, fix 09d7ff0bf) — paginated list_tables without deprecation. |
| tests/unit/test_launchd_process_type.py | 32 | K2 — committed serving plists must not run at Background priority. |

## Fixtures / data

- No orphaned helper module: `tests/unit/orchestration_fake_pipeline.py` is still used by out-of-scope `test_orchestration_*` and `tests/wfe`; `tests/unit/conftest.py` autouse fixtures are shared and kept. Cross-module helpers imported by kept tests (`test_hunt_observations` GridSearch/_event/_keyed/_ref_burst/_universe, `test_hunt_wire` JobSearch/_plant, `test_cad_coverage_corpus` CORPUS) were preserved.
- `tests/unit/cip_pdf_dependent_tests.txt` (read by conftest) now lists some deleted node ids; stale entries are inert (skip marker on a non-existent item). Left as-is; regenerate per the conftest comment if desired.
- Wiki reconciliation (Rule 12): removed deleted-test `sources:` entries from 6 canonical units (unit-compliance-engine, -bilateral-corpus, -substrate-properties, -requirement-join, unit-design-client-disconnect-cancellation, unit-known-limitations-…-prometheus-multiproc-dir-host-side) so `check_wiki_core` integrity passes. The known-limitations unit body still describes the removed subprocess regression test historically; only the dead source path was removed.

## Gates

- `uv run pytest tests/unit/ tests/wfe -q -n auto` → **exit 0**, 5399 passed, 23 skipped.
- `uv run ruff check .` → All checks passed! · `uv run ruff format --check .` → 1904 files already formatted.
- `uv run mypy portal/` → Success: no issues found in 730 source files.
- `python3 scripts/complexity_report.py --gate` → **FAIL: unwired_scripts 32 > ceiling 25** (baseline 24). This is a ceiling broken by deletions: removing tooling tests unwired 8 scripts (e.g. cam_lds_extract, compliance/truth/copy_probe, substrate_vs_key, truth_corpus, bench_compliance_thinking, compliance_acceptance_report, compliance_capture_fidelity, compliance_prompt_comparison, compliance_reading_seat_probe). Per the brief, NOT fixed by adding code and the ceiling NOT raised — operator decision (see OPEN).
