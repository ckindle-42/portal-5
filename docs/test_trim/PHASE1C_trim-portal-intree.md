# Phase 1c test trim — trim-portal-intree

Scope: every `test_*.py` and `*/tests/*.py` under `portal/`. Before this pass the tree was 116 files and 23,329 lines, and it had not been trimmed. The keep rules are a named live bug, a contract the running system loads, or pure logic with no I/O and no mocks.

No WFE or bench workload task file under this tree is imported by portal code at runtime. The search was for imports of `portal.modules.*.tests`, `portal.platform.*.tests`, and `test_graph_memory` / `test_rag_multimodal` from product modules and scripts. The only caller was `scripts/validation/security_bench.py`, which shelled out to `test_ci_parity.py`. That check now imports `portal.modules.security.core.matrix` with `PYTHONPATH` unset.

`portal/modules/security/tests/conftest.py` stays. `test_write_isolation.py` pins the 2026-07-29 write-through bug and uses the `isolated_security_writes` fixture.

Kept share is 13,490 / 23,329 lines (57.8%), above the ~40% mark. The largest survivors are pure scorers and verdict math, plus a smaller set of dated live-bug pins. They are listed below.

## Counts

| measure | before | after |
| --- | ---: | ---: |
| Scope files | 116 | 101 |
| Scope Python lines | 23329 | 13490 |
| Share kept | | 57.8% (13490/23329) |
| Whole files deleted | | 15 |
| `uv run pytest portal -q -n auto` | | 1493 passed, 1 warning, 189.47s, exit 0 |
| `uv run pytest tests/unit/ tests/wfe -q -n auto` | | 2793 passed, 20 skipped, 32.58s, exit 0 |
| `uv run ruff check .` and `uv run ruff format --check .` | | clean |
| `uv run mypy portal/` | | Success: no issues found in 715 source files |
| `python3 scripts/complexity_report.py --gate` | | GATE OK. data_lines 12292/13370, god_lines 68050/71202, unwired_scripts 24/25, identical_pairs 0, committed_blob_bytes 1792894/1873616 |

## Largest kept files

| lines | path | keep rule |
| ---: | --- | --- |
| 838 | `portal/modules/security/tests/test_bench_scoring.py` | rule 3 — in-memory scoring |
| 832 | `portal/modules/security/tests/test_rbp_episode_grounding.py` | rule 3 — episode verdict math |
| 596 | `portal/modules/security/tests/test_ablation_attribution.py` | rule 3 — attribution classify/summarize |
| 542 | `portal/modules/security/tests/test_blue_orchestrate_loop.py` | rule 1 dated pins, plus rule 3 helpers that stayed reachable |
| 465 | `portal/modules/security/tests/test_splunk_blue.py` | rule 3 parsers plus rule 1 pins |
| 413 | `portal/modules/security/tests/test_blue_linux.py` | rule 1 (Found live 2026-07-05 and 2026-07-18) plus rule 3 |
| 408 | `portal/modules/security/tests/test_capability_graph.py` | rule 3 — in-memory gap graph |
| 366 | `portal/modules/security/tests/test_target_readiness_ports.py` | rule 1 (Found live 2026-07-05, 2026-07-22, 2026-07-24) plus rule 3 |
| 343 | `portal/modules/security/tests/test_unknown_defense.py` | rule 1 (Found live 2026-07-20) plus rule 3 |
| 313 | `portal/modules/security/tests/test_agentic_blue_scoring.py` | rule 3 — tiered scoring |

## Deleted files

| path | lines | why it fails the keep rules |
| --- | ---: | --- |
| `portal/modules/binary_research/tests/test_policy.py` | 53 | filesystem or tmp_path I/O |
| `portal/modules/binary_research/tests/test_re_client.py` | 68 | mocks, fakes, or monkeypatches control flow; network or HTTP client |
| `portal/modules/binary_research/tests/test_tools.py` | 81 | filesystem or tmp_path I/O; mocks, fakes, or monkeypatches control flow |
| `portal/modules/binary_research/tests/test_workspace.py` | 52 | filesystem or tmp_path I/O; mocks, fakes, or monkeypatches control flow |
| `portal/modules/research/tools/test_rag_multimodal.py` | 183 | filesystem or tmp_path I/O; mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_bench_security_lab_gate.py` | 112 | mocks, fakes, or monkeypatches control flow; filesystem or tmp_path I/O |
| `portal/modules/security/tests/test_ci_parity.py` | 71 | snapshot of pyproject.toml, conftest, and ci_local.sh; not a contract the running system loads |
| `portal/modules/security/tests/test_field_journal.py` | 112 | filesystem or tmp_path I/O; mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_live_exec.py` | 283 | mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_loop_resume.py` | 141 | filesystem or tmp_path I/O; mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_objective_entry.py` | 327 | mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_objective_executor.py` | 189 | mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_security_mcp.py` | 352 | module-level torch/transformers mocks; the tests only run against that harness |
| `portal/modules/security/tests/test_sweep_checkpoint_safety.py` | 91 | filesystem or tmp_path I/O; mocks, fakes, or monkeypatches control flow; subprocess or process capture |
| `portal/platform/memory/test_graph_memory.py` | 155 | filesystem or tmp_path I/O; mocks, fakes, or monkeypatches control flow |

## Tests removed from split files

| path | test | lines | why it fails the keep rules |
| --- | --- | ---: | --- |
| `portal/modules/binary_research/tests/test_scaffold.py` | `test_answer_asks_next_when_model_wants_more` | 12 | filesystem or tmp_path I/O; mocks, fakes, or monkeypatches control flow |
| `portal/modules/binary_research/tests/test_scaffold.py` | `test_answer_forces_done_after_max` | 10 | filesystem or tmp_path I/O; mocks, fakes, or monkeypatches control flow |
| `portal/modules/binary_research/tests/test_scaffold.py` | `test_answer_scaffolds_when_model_done` | 17 | filesystem or tmp_path I/O; mocks, fakes, or monkeypatches control flow |
| `portal/modules/binary_research/tests/test_scaffold.py` | `test_apply_plan_writes_structure` | 12 | filesystem or tmp_path I/O |
| `portal/modules/binary_research/tests/test_scaffold.py` | `test_start_writes_opening_question` | 6 | filesystem or tmp_path I/O |
| `portal/modules/binary_research/tests/test_verifiers.py` | `test_discover` | 2 | filesystem or tmp_path I/O |
| `portal/modules/binary_research/tests/test_verifiers.py` | `test_partial` | 3 | filesystem or tmp_path I/O |
| `portal/modules/compliance/tests/test_compliance_mcp.py` | `test_patch_evidence_bridges_triage` | 12 | mocks, fakes, or monkeypatches control flow |
| `portal/modules/data/tests/test_data_mcp.py` | `test_attach_query_profile` | 16 | filesystem or tmp_path I/O; mocks, fakes, or monkeypatches control flow |
| `portal/modules/data/tests/test_data_mcp.py` | `test_connection_cache_evicts_least_recent` | 14 | filesystem or tmp_path I/O; mocks, fakes, or monkeypatches control flow |
| `portal/modules/data/tests/test_data_mcp.py` | `test_connections_are_memory_bounded` | 12 | filesystem or tmp_path I/O; mocks, fakes, or monkeypatches control flow |
| `portal/modules/data/tests/test_data_mcp.py` | `test_out_of_memory_is_retried_with_more_memory` | 15 | filesystem or tmp_path I/O; mocks, fakes, or monkeypatches control flow |
| `portal/modules/data/tests/test_data_mcp.py` | `test_out_of_memory_reports_ceiling_when_host_cannot_spare_more` | 10 | filesystem or tmp_path I/O; mocks, fakes, or monkeypatches control flow |
| `portal/modules/data/tests/test_data_mcp.py` | `test_path_escape_rejected` | 4 | filesystem or tmp_path I/O; mocks, fakes, or monkeypatches control flow |
| `portal/modules/data/tests/test_data_mcp.py` | `test_run_sql_cannot_read_arbitrary_files` | 23 | filesystem or tmp_path I/O; mocks, fakes, or monkeypatches control flow |
| `portal/modules/icsot/tests/test_icsot_mcp.py` | `test_modbus_dissection_tags_write` | 21 | filesystem or tmp_path I/O |
| `portal/modules/netforensics/tests/test_netforensics_mcp.py` | `test_lab_cidr_reuses_security_guard` | 5 | mocks, fakes, or monkeypatches control flow |
| `portal/modules/netforensics/tests/test_netforensics_mcp.py` | `test_path_escape_rejected` | 4 | filesystem or tmp_path I/O; mocks, fakes, or monkeypatches control flow |
| `portal/modules/netforensics/tests/test_netforensics_mcp.py` | `test_recon_disabled_by_default` | 4 | mocks, fakes, or monkeypatches control flow |
| `portal/modules/netforensics/tests/test_netforensics_mcp.py` | `test_recon_refuses_cidr_outside_lab` | 4 | mocks, fakes, or monkeypatches control flow |
| `portal/modules/netforensics/tests/test_netforensics_mcp.py` | `test_recon_refuses_outside_lab` | 4 | mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_ability_port.py` | `TestAntiStub.test_module_has_detect_logic` | 7 | filesystem or tmp_path I/O |
| `portal/modules/security/tests/test_ablation_attribution.py` | `test_driver_marks_unvalidated_rescore_exploratory` | 29 | filesystem or tmp_path I/O; mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_benign_corpus_bench.py` | `test_targeted_rerun_replaces_only_selected_retained_cell` | 30 | filesystem or tmp_path I/O; mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_blue_linux.py` | `TestSyntheticFallbackGate.test_synthetic_fallback_never_pass` | 21 | mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_blue_linux.py` | `TestTelemetryBackendPluggable.test_fake_backend_protocol` | 16 | mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_blue_orchestrate_expert.py` | `test_anomalous_unclassified_never_requires_a_valid_technique_id` | 20 | mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_blue_orchestrate_expert.py` | `test_confirmed_failing_cite_or_drop_downgrades_to_anomalous` | 33 | mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_blue_orchestrate_expert.py` | `test_dry_run_never_calls_model` | 7 | mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_blue_orchestrate_expert.py` | `test_expert_request_more_round_trips` | 17 | mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_blue_orchestrate_expert.py` | `test_ruled_out_is_a_valid_conclusion_without_citation_check` | 17 | mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_blue_orchestrate_expert.py` | `test_supports_tools_false_expert_id_is_accepted` | 32 | mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_blue_orchestrate_expert.py` | `test_unparseable_output_becomes_request_more` | 5 | mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_blue_orchestrate_loop.py` | `test_barrier_tools_disabled_reproduces_v2_json_path` | 32 | mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_blue_orchestrate_loop.py` | `test_broken_mentor_response_falls_back_cleanly` | 55 | mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_blue_orchestrate_loop.py` | `test_budget_starve_expert_can_still_confirm` | 33 | mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_blue_orchestrate_loop.py` | `test_budget_starve_expert_declining_still_unresolved` | 22 | mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_blue_orchestrate_loop.py` | `test_budget_starve_forces_expert_turn_not_unresolved` | 24 | mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_blue_orchestrate_loop.py` | `test_budget_starve_honors_capture_only` | 21 | mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_blue_orchestrate_loop.py` | `test_budgets_dict_is_not_mutated_by_orchestration` | 19 | mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_blue_orchestrate_loop.py` | `test_budgets_hunter_key_overrides_max_rounds_for_hunter_only` | 24 | mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_blue_orchestrate_loop.py` | `test_budgets_none_and_max_rounds_only_is_v2_identical` | 30 | mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_blue_orchestrate_loop.py` | `test_budgets_partial_override_falls_back_for_unnamed_roles` | 31 | mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_blue_orchestrate_loop.py` | `test_capture_expert_handoff_resume_matches_live_run_and_skips_rerun` | 95 | mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_blue_orchestrate_loop.py` | `test_capture_hunter_handoff_resume_matches_live_run_and_skips_rerun` | 87 | mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_blue_orchestrate_loop.py` | `test_confirmed_sibling_misattribution_demoted_to_anomalous` | 55 | mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_blue_orchestrate_loop.py` | `test_confirmed_via_barrier_tool_still_cite_or_drops` | 36 | mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_blue_orchestrate_loop.py` | `test_correct_confirmed_survives_discriminator_gate` | 35 | mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_blue_orchestrate_loop.py` | `test_council_aggregate_sibling_misattribution_demoted` | 53 | mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_blue_orchestrate_loop.py` | `test_council_budget_starve_still_reaches_non_voting_members` | 43 | mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_blue_orchestrate_loop.py` | `test_council_dispatch_unanimous_confirmed` | 83 | mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_blue_orchestrate_loop.py` | `test_council_fit_roster_produces_no_warning` | 4 | subprocess or process capture |
| `portal/modules/security/tests/test_blue_orchestrate_loop.py` | `test_council_lead_hunter_uses_mentor_when_configured` | 62 | mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_blue_orchestrate_loop.py` | `test_council_members_use_barrier_tools_when_configured` | 62 | mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_blue_orchestrate_loop.py` | `test_council_non_voting_members_counted_against_quorum` | 48 | mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_blue_orchestrate_loop.py` | `test_council_split_with_arbiter_breaks_tie` | 79 | mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_blue_orchestrate_loop.py` | `test_council_unfit_model_warns_but_does_not_block` | 6 | subprocess or process capture |
| `portal/modules/security/tests/test_blue_orchestrate_loop.py` | `test_council_uses_hunter_budget_for_shared_lead_hunt` | 25 | mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_blue_orchestrate_loop.py` | `test_emit_verdict_confirmed_path` | 38 | mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_blue_orchestrate_loop.py` | `test_escalate_anomalous_is_first_class_not_demoted_confirmed` | 27 | mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_blue_orchestrate_loop.py` | `test_expert_handoff_round_trips_through_json` | 52 | mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_blue_orchestrate_loop.py` | `test_hunter_handoff_round_trips_through_json` | 40 | mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_blue_orchestrate_loop.py` | `test_json_fallback_when_no_tool_call_emitted` | 26 | mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_blue_orchestrate_loop.py` | `test_malformed_toolcall_args_falls_back_to_json_scrape` | 18 | mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_blue_orchestrate_loop.py` | `test_max_rounds_alone_reproduces_v2_behavior` | 51 | mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_blue_orchestrate_loop.py` | `test_mentor_absent_reproduces_v2_behavior` | 45 | mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_blue_orchestrate_loop.py` | `test_mentor_block_appears_in_next_hunter_context` | 59 | mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_blue_orchestrate_loop.py` | `test_mentor_fires_at_second_no_hypothesis_round` | 56 | mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_blue_orchestrate_loop.py` | `test_mentor_max_invocations_is_two_per_hunt` | 55 | mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_blue_orchestrate_loop.py` | `test_multichain_divergent_chains_escalate_to_human` | 62 | mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_blue_orchestrate_loop.py` | `test_multichain_does_not_alter_existing_arms` | 53 | mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_blue_orchestrate_loop.py` | `test_multichain_forwards_budgets_to_each_chain` | 23 | mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_blue_orchestrate_loop.py` | `test_multichain_independent_convergence_is_auto_confirm` | 72 | mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_blue_orchestrate_loop.py` | `test_never_concluding_pipeline_hits_max_rounds_unresolved` | 34 | mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_blue_orchestrate_loop.py` | `test_request_more_barrier_tool_matches_v2_request_more_semantics` | 19 | mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_blue_orchestrate_loop.py` | `test_request_more_tool_reasoning_expert_confirmed_terminates_confirmed` | 69 | mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_blue_orchestrate_loop.py` | `test_sections_list_order_is_honored_model_swap_works` | 41 | mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_blue_orchestrate_loop.py` | `test_similar_variant_hunt_flows_to_anomalous_unclassified` | 31 | mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_blue_orchestrate_loop.py` | `test_three_section_and_two_section_unaffected_by_council_dispatch` | 64 | mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_blue_orchestrate_loop.py` | `test_two_section_ablation_arm_confirms_without_a_separate_expert` | 67 | mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_blue_orchestrate_loop.py` | `test_two_section_ablation_arm_requests_more_then_confirms` | 52 | mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_blue_orchestrate_loop.py` | `test_two_section_never_concluding_hits_max_rounds_unresolved` | 32 | mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_blue_orchestrate_loop.py` | `test_wall_clock_backstop_fires_independently` | 37 | mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_blue_orchestrate_reasoning.py` | `test_dry_run_never_calls_model` | 7 | mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_blue_orchestrate_reasoning.py` | `test_ground_similarity_corrects_a_claimed_similarity_that_does_not_hold_up` | 23 | mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_blue_orchestrate_reasoning.py` | `test_ground_similarity_overrides_unverified_self_report_with_grounded_grade` | 31 | mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_blue_orchestrate_reasoning.py` | `test_ground_similarity_skips_when_wiki_not_seeded` | 6 | mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_blue_orchestrate_reasoning.py` | `test_insufficient_evidence_emits_request_more_not_a_guess` | 18 | mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_blue_orchestrate_reasoning.py` | `test_run_reasoning_model_without_history_is_unchanged` | 20 | mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_blue_orchestrate_reasoning.py` | `test_similar_grade_yields_similar_to_and_steers_anomalous` | 19 | mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_blue_orchestrate_reasoning.py` | `test_think_wrapped_hypothesis_parses` | 19 | mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_blue_orchestrate_reasoning.py` | `test_unparseable_free_text_falls_back_to_request_more_never_guesses` | 12 | mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_blue_orchestrate_toolleg.py` | `test_dispatch_tool_call_falls_back_to_freetext_when_broad_summary` | 14 | mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_blue_orchestrate_toolleg.py` | `test_list_valued_event_ids_actually_narrow_the_query` | 35 | mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_blue_orchestrate_toolleg.py` | `test_live_tool_call_dispatches_and_returns_matched_exact` | 30 | mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_blue_orchestrate_toolleg.py` | `test_live_tool_call_ignores_non_retrieval_tool_calls` | 28 | mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_blue_orchestrate_toolleg.py` | `test_live_tool_call_with_string_encoded_arguments_does_not_crash` | 31 | mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_blue_orchestrate_toolleg.py` | `test_targeted_miss_broadens_to_model_visible_raw_evidence` | 45 | mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_candidate_eval_incumbent.py` | `TestFailLoudGuard.test_fail_loud_on_unresolvable` | 18 | mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_candidate_eval_incumbent.py` | `TestFailLoudGuard.test_override_bypasses_resolution` | 20 | mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_candidate_eval_incumbent.py` | `TestGetIncumbentModel.test_reads_from_portal_yaml` | 20 | mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_candidate_eval_incumbent.py` | `TestGetIncumbentModel.test_returns_empty_on_missing_workspace` | 9 | mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_candidate_eval_incumbent.py` | `TestGetIncumbentModel.test_returns_empty_on_missing_yaml` | 8 | mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_capability_index.py` | `TestCapabilityCLI.test_arsenal` | 4 | subprocess or process capture |
| `portal/modules/security/tests/test_capability_index.py` | `TestCapabilityCLI.test_list_json` | 4 | subprocess or process capture |
| `portal/modules/security/tests/test_capability_index.py` | `TestCapabilityCLI.test_query_json` | 4 | subprocess or process capture |
| `portal/modules/security/tests/test_capability_index.py` | `TestCapabilityCLI.test_tools` | 4 | subprocess or process capture |
| `portal/modules/security/tests/test_capture_recipes.py` | `test_recipes_resolve_runtime_placeholders_and_use_image_contract_tools` | 16 | filesystem or tmp_path I/O |
| `portal/modules/security/tests/test_compliance_mapping.py` | `TestComplianceMappingSchema.test_every_detection_has_compliance_mapping` | 6 | filesystem or tmp_path I/O |
| `portal/modules/security/tests/test_compliance_mapping.py` | `TestComplianceMappingSchema.test_every_detection_has_matrix` | 4 | filesystem or tmp_path I/O |
| `portal/modules/security/tests/test_compliance_mapping.py` | `TestComplianceMappingSchema.test_every_mapping_cites_a_source` | 11 | filesystem or tmp_path I/O |
| `portal/modules/security/tests/test_compliance_mapping.py` | `TestComplianceMappingSchema.test_matrix_values_are_known` | 7 | filesystem or tmp_path I/O |
| `portal/modules/security/tests/test_compliance_mapping.py` | `TestComplianceMappingSchema.test_mitre_tactic_present_for_every_technique` | 7 | filesystem or tmp_path I/O |
| `portal/modules/security/tests/test_compliance_mapping.py` | `TestComplianceMappingSchema.test_nist_800_53_present_for_every_technique` | 7 | filesystem or tmp_path I/O |
| `portal/modules/security/tests/test_compliance_report.py` | `TestGeneratedFiles.test_insufficient_data_report_says_so` | 5 | filesystem or tmp_path I/O |
| `portal/modules/security/tests/test_compliance_report.py` | `TestGeneratedFiles.test_md_and_html_carry_generated_marker` | 17 | filesystem or tmp_path I/O |
| `portal/modules/security/tests/test_compliance_report.py` | `TestGeneratedFiles.test_pdf_format_honestly_reports_unavailable` | 5 | filesystem or tmp_path I/O |
| `portal/modules/security/tests/test_compliance_report.py` | `TestLoadPurpleResults.test_malformed_json_returns_empty` | 4 | filesystem or tmp_path I/O |
| `portal/modules/security/tests/test_compliance_report.py` | `TestLoadPurpleResults.test_missing_file_returns_empty` | 2 | filesystem or tmp_path I/O |
| `portal/modules/security/tests/test_compliance_report.py` | `TestLoadPurpleResults.test_purple_tests_key` | 3 | filesystem or tmp_path I/O |
| `portal/modules/security/tests/test_compliance_report.py` | `TestLoadPurpleResults.test_results_key_fallback` | 4 | filesystem or tmp_path I/O |
| `portal/modules/security/tests/test_compliance_report.py` | `TestReportData.test_every_provenance_claim_has_source_or_is_coverage_ref` | 17 | filesystem or tmp_path I/O |
| `portal/modules/security/tests/test_compliance_report.py` | `TestReportData.test_framework_rollup_denominator_is_mapped_techniques_only` | 10 | filesystem or tmp_path I/O |
| `portal/modules/security/tests/test_compliance_report.py` | `TestReportData.test_gap_technique_appears_as_gap_not_hidden` | 25 | filesystem or tmp_path I/O |
| `portal/modules/security/tests/test_compliance_report.py` | `TestReportData.test_insufficient_data_when_empty_results` | 4 | filesystem or tmp_path I/O |
| `portal/modules/security/tests/test_compliance_report.py` | `TestReportData.test_insufficient_data_when_no_results` | 4 | filesystem or tmp_path I/O |
| `portal/modules/security/tests/test_compliance_report.py` | `TestReportData.test_verdict_distribution_counts` | 17 | filesystem or tmp_path I/O |
| `portal/modules/security/tests/test_corpus_coverage.py` | `test_agentic_blue_loader_uses_valid_capture_not_newest_hollow` | 30 | filesystem or tmp_path I/O; mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_corpus_coverage.py` | `test_declared_external_inventory_cannot_pass_live_validation_gate` | 12 | filesystem or tmp_path I/O; mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_corpus_coverage.py` | `test_empty_external_probe_cannot_pass_readiness_gate` | 14 | filesystem or tmp_path I/O; mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_corpus_coverage.py` | `test_external_techniques_never_substitute_for_live_scenario_proof` | 19 | filesystem or tmp_path I/O; mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_corpus_coverage.py` | `test_hollow_newest_capture_does_not_hide_older_valid_capture` | 27 | filesystem or tmp_path I/O; mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_corpus_coverage.py` | `test_report_identifies_catalog_as_lab_exercises` | 13 | filesystem or tmp_path I/O; mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_corpus_coverage.py` | `test_theory_and_unbacked_scenarios_do_not_inflate_lab_denominator` | 15 | filesystem or tmp_path I/O; mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_corpus_replay_bench.py` | `TestCheckpointBackupDiscipline.test_checkpoint_roundtrips` | 7 | filesystem or tmp_path I/O |
| `portal/modules/security/tests/test_corpus_replay_bench.py` | `TestCheckpointBackupDiscipline.test_different_cell_keys_both_kept` | 11 | filesystem or tmp_path I/O |
| `portal/modules/security/tests/test_corpus_replay_bench.py` | `TestCheckpointBackupDiscipline.test_no_checkpoint_loads_empty` | 2 | filesystem or tmp_path I/O |
| `portal/modules/security/tests/test_corpus_replay_bench.py` | `TestCheckpointBackupDiscipline.test_resume_backs_up_existing_checkpoint_before_any_new_write` | 19 | filesystem or tmp_path I/O |
| `portal/modules/security/tests/test_corpus_replay_bench.py` | `TestCheckpointBackupDiscipline.test_same_cell_key_overwrites_not_duplicates` | 10 | filesystem or tmp_path I/O |
| `portal/modules/security/tests/test_corpus_replay_bench.py` | `TestCorpusEpisode.test_builds_episode_from_real_row_shape` | 15 | mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_corpus_replay_bench.py` | `TestCorpusEpisode.test_preserves_label_blind_correlation_aggregate` | 26 | mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_corpus_replay_bench.py` | `TestCorpusEpisode.test_returns_none_when_no_corpus_rows` | 7 | mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_corpus_replay_bench.py` | `TestCorpusEpisode.test_returns_none_when_rows_have_no_raw_field` | 8 | mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_corpus_replay_bench.py` | `TestRunCellWiring.test_orchestrated_cell_wires_mentor_budgets_barrier_tools` | 82 | mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_corpus_replay_bench.py` | `TestRunCellWiring.test_scoring_is_confirm_only` | 37 | mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_corpus_replay_bench.py` | `TestRunCellWiring.test_skips_cleanly_when_corpus_has_no_data` | 14 | mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_council_agreement.py` | `test_security_quorum_delegates_to_platform_aggregate` | 31 | mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_coverage_expand.py` | `TestLabExerciseImageContract.test_all_executable_sequence_command_heads_are_declared` | 4 | filesystem or tmp_path I/O |
| `portal/modules/security/tests/test_coverage_expand.py` | `TestLabExerciseImageContract.test_contract_is_lab_exercise_only` | 4 | filesystem or tmp_path I/O |
| `portal/modules/security/tests/test_coverage_expand.py` | `TestLabExerciseImageContract.test_previously_missing_tools_are_hard_requirements` | 11 | filesystem or tmp_path I/O |
| `portal/modules/security/tests/test_coverage_expand.py` | `TestLabExerciseImageContract.test_scenario_entry_commands_are_declared` | 9 | filesystem or tmp_path I/O |
| `portal/modules/security/tests/test_coverage_expand.py` | `TestMeta3Scenarios.test_attack_image_installs_required_meta3_tools` | 6 | filesystem or tmp_path I/O |
| `portal/modules/security/tests/test_coverage_expand.py` | `TestSPLDetectionCoverage.test_spl_detections_valid_yaml` | 12 | filesystem or tmp_path I/O |
| `portal/modules/security/tests/test_drift_gate.py` | `TestDriftCLI.test_drift_check_json_is_parseable` | 7 | subprocess or process capture |
| `portal/modules/security/tests/test_drift_gate.py` | `TestModelCanary.test_flipped_probe_detected` | 23 | filesystem or tmp_path I/O; mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_drift_gate.py` | `TestModelCanary.test_identical_behavior_is_none` | 21 | filesystem or tmp_path I/O; mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_drift_gate.py` | `TestModelCanary.test_no_baseline_reports_no_baseline_status` | 7 | filesystem or tmp_path I/O; mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_drift_gate.py` | `TestModelCanary.test_run_canary_probe_mocked` | 15 | mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_drift_gate.py` | `TestModelCanary.test_run_canary_probe_mocked_pipeline_default` | 21 | mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_evidence_chain_validity.py` | `test_bad_blue_query_is_a_grounded_miss_not_na` | 45 | mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_evidence_chain_validity.py` | `test_each_red_model_gets_an_isolated_blue_episode` | 68 | offline end-to-end flow; mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_evidence_chain_validity.py` | `test_episode_query_recovers_origin_from_hec_source` | 21 | mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_evidence_chain_validity.py` | `test_freeform_query_cannot_escape_episode_scope` | 22 | mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_evidence_chain_validity.py` | `test_hollow_episode_scoped_capture_is_not_replayable` | 19 | filesystem or tmp_path I/O |
| `portal/modules/security/tests/test_evidence_chain_validity.py` | `test_known_scenario_revalidates_stale_stored_validity` | 19 | filesystem or tmp_path I/O |
| `portal/modules/security/tests/test_evidence_chain_validity.py` | `test_legacy_unscoped_capture_is_not_replayable` | 16 | filesystem or tmp_path I/O |
| `portal/modules/security/tests/test_evidence_chain_validity.py` | `test_replay_never_ships_counterfactual_transcript` | 38 | filesystem or tmp_path I/O; mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_evidence_chain_validity.py` | `test_replay_normalizes_stale_target_metadata` | 44 | filesystem or tmp_path I/O; mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_kali_enable.py` | `TestLabDispatchRouting.test_execute_bash_dispatches_to_mcp` | 10 | mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_kali_enable.py` | `TestLabDispatchRouting.test_execute_python_dispatches_to_mcp` | 10 | mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_kali_enable.py` | `TestLabDispatchRouting.test_getnpusers_alias_is_bounded_to_known_lab_accounts` | 17 | mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_kali_enable.py` | `TestLabDispatchRouting.test_impacket_getuserspns_alias_dispatches_same_as_exploit_service` | 14 | mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_kali_enable.py` | `TestLabDispatchRouting.test_nmap_alias_dispatches_same_as_run_nmap_scan` | 15 | mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_kali_enable.py` | `TestLabDispatchRouting.test_read_only_emergent_aliases_dispatch_verified_commands` | 28 | mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_lab_targets.py` | `TestChallengeClasses.test_classes_parse` | 4 | filesystem or tmp_path I/O |
| `portal/modules/security/tests/test_lab_targets.py` | `TestChallengeClasses.test_every_class_has_ground_truth` | 4 | filesystem or tmp_path I/O |
| `portal/modules/security/tests/test_lab_targets.py` | `TestChallengeClasses.test_every_class_has_source` | 4 | filesystem or tmp_path I/O |
| `portal/modules/security/tests/test_lab_targets.py` | `TestChallengeClasses.test_no_orphan_classes` | 8 | filesystem or tmp_path I/O |
| `portal/modules/security/tests/test_lab_targets.py` | `TestLabTargetsCatalog.test_catalog_parses` | 4 | filesystem or tmp_path I/O |
| `portal/modules/security/tests/test_lab_targets.py` | `TestLabTargetsCatalog.test_every_entry_has_source` | 4 | filesystem or tmp_path I/O |
| `portal/modules/security/tests/test_lab_targets.py` | `TestLabTargetsCatalog.test_preexisting_entries_marked` | 4 | filesystem or tmp_path I/O |
| `portal/modules/security/tests/test_labexec_coverage.py` | `TestLabTargetTable.test_target_skipped_when_vmid_not_set` | 10 | mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_loop.py` | `TestRunEngagement.test_invalid_playbook_rejected` | 3 | offline end-to-end flow |
| `portal/modules/security/tests/test_loop.py` | `TestRunEngagement.test_valid_playbook_dry_runs` | 5 | offline end-to-end flow |
| `portal/modules/security/tests/test_loop_notify.py` | `TestCheckpointResume.test_checkpoint_writes_and_roundtrips` | 17 | filesystem or tmp_path I/O; mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_loop_notify.py` | `TestLoopNotifyFiring.test_escalation_fires_engagement_escalated_with_resume_cmd` | 21 | mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_loop_notify.py` | `TestLoopNotifyFiring.test_goal_met_no_notify_by_default` | 12 | mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_loop_notify.py` | `TestLoopNotifyFiring.test_goal_met_notifies_when_opted_in` | 12 | mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_loop_notify.py` | `TestLoopNotifyFiring.test_hard_cap_fires_engagement_stuck` | 7 | mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_loop_notify.py` | `TestLoopNotifyFiring.test_no_runnable_phase_fires_engagement_stuck` | 14 | mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_loop_notify.py` | `TestLoopNotifyFiring.test_notifications_disabled_is_a_noop` | 8 | mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_loop_notify.py` | `TestLoopNotifyFiring.test_notify_failure_is_swallowed` | 11 | mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_loop_notify.py` | `TestLoopNotifyFiring.test_out_of_scope_step_target_escalates_and_notifies` | 21 | mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_matrix.py` | `TestBuildRunMatrix.test_build_classes_only` | 6 | filesystem or tmp_path I/O; mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_matrix.py` | `TestBuildRunMatrix.test_build_scenarios_only` | 8 | filesystem or tmp_path I/O; mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_matrix.py` | `TestBuildRunMatrix.test_build_with_fixture_vulhub_tree` | 31 | filesystem or tmp_path I/O; mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_matrix.py` | `TestBuildRunMatrix.test_domain_filter` | 10 | filesystem or tmp_path I/O; mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_matrix.py` | `TestBuildRunMatrix.test_every_scenario_has_oracle_or_explicit_null` | 11 | mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_matrix.py` | `TestBuildRunMatrix.test_every_scenario_resolves_to_unit` | 8 | mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_matrix.py` | `TestClassOracleBinding.test_class_oracles_registered` | 12 | filesystem or tmp_path I/O; mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_matrix.py` | `TestCoverageReport.test_coverage_report_structure` | 33 | mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_matrix.py` | `TestDomainClassification.test_ad_keywords` | 4 | mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_matrix.py` | `TestDomainClassification.test_linux_keywords` | 4 | mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_matrix.py` | `TestDomainClassification.test_unknown_is_mixed` | 2 | mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_matrix.py` | `TestDomainClassification.test_web_keywords` | 4 | mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_matrix.py` | `TestInferTarget.test_dc_hint` | 3 | mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_matrix.py` | `TestInferTarget.test_fallback` | 2 | mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_matrix.py` | `TestInferTarget.test_web_hint` | 3 | mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_matrix.py` | `TestRunMatrix.test_dry_run_plans_all_units` | 8 | filesystem or tmp_path I/O; mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_matrix.py` | `TestRunMatrix.test_lab_exec_unavailable_indeterminate` | 9 | filesystem or tmp_path I/O; mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_matrix.py` | `TestRunMatrix.test_max_concurrent_respected` | 6 | filesystem or tmp_path I/O; mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_matrix.py` | `TestTelemetryBackend.test_canonical_telemetry_protocol_importable` | 5 | mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_matrix.py` | `TestTelemetryBackend.test_matrix_imports_canonical_protocol` | 8 | mocks, fakes, or monkeypatches control flow; source or golden snapshot |
| `portal/modules/security/tests/test_matrix.py` | `TestVulhubGlobExpansion.test_empty_patterns_returns_empty` | 2 | filesystem or tmp_path I/O; mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_matrix.py` | `TestVulhubGlobExpansion.test_expands_glob_patterns` | 15 | filesystem or tmp_path I/O; mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_matrix.py` | `TestVulhubGlobExpansion.test_nonexistent_pattern_returns_empty` | 2 | filesystem or tmp_path I/O; mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_prerun_readiness.py` | `TestSPLIntegrity.test_all_entries_have_required_fields` | 7 | filesystem or tmp_path I/O |
| `portal/modules/security/tests/test_prerun_readiness.py` | `TestSPLIntegrity.test_spl_references_real_sourcetype` | 10 | filesystem or tmp_path I/O |
| `portal/modules/security/tests/test_prerun_readiness.py` | `TestSPLIntegrity.test_spl_yaml_parses` | 4 | filesystem or tmp_path I/O |
| `portal/modules/security/tests/test_rbp_episode_grounding.py` | `TestTelemetryFailureReasonCode.test_no_silent_pass_in_matrix` | 18 | filesystem or tmp_path I/O |
| `portal/modules/security/tests/test_sec_intake.py` | `test_run_candidate_intake_all_pass` | 27 | mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_sec_intake.py` | `test_run_candidate_intake_pull_fail` | 10 | mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_sec_intake.py` | `test_run_candidate_intake_tool_fail` | 27 | mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_sec_intake.py` | `test_run_candidate_intake_tps_below_floor` | 22 | mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_self_index.py` | `TestBuildSelfIndex.test_coverage_stale_when_no_results` | 18 | filesystem or tmp_path I/O; mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_self_index.py` | `TestBuildSelfIndex.test_journal_absent_when_no_entries` | 12 | filesystem or tmp_path I/O; mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_self_index.py` | `TestBuildSelfIndex.test_journal_reads_entries_without_index` | 14 | filesystem or tmp_path I/O; mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_self_index.py` | `TestBuildSelfIndex.test_journal_reads_index` | 13 | filesystem or tmp_path I/O; mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_self_index.py` | `TestBuildSelfIndex.test_read_only_no_writes_outside_report` | 35 | filesystem or tmp_path I/O; mocks, fakes, or monkeypatches control flow; subprocess or process capture |
| `portal/modules/security/tests/test_self_index.py` | `TestBuildSelfIndex.test_reads_oracle_fidelity_registry` | 12 | mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_self_index.py` | `TestBuildSelfIndex.test_reads_validator_health` | 16 | filesystem or tmp_path I/O; mocks, fakes, or monkeypatches control flow; subprocess or process capture |
| `portal/modules/security/tests/test_self_index.py` | `TestRankWeaknesses.test_absent_signals_marked_not_fabricated` | 41 | filesystem or tmp_path I/O; mocks, fakes, or monkeypatches control flow; subprocess or process capture |
| `portal/modules/security/tests/test_selfindex_fidelity.py` | `TestAntiRecursionGuard.test_nested_env_var_still_passed` | 11 | mocks, fakes, or monkeypatches control flow; subprocess or process capture |
| `portal/modules/security/tests/test_selfindex_fidelity.py` | `TestReadCoverageSelection.test_picks_newest_real_coverage_across_both_dirs_and_schemas` | 31 | filesystem or tmp_path I/O; mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_selfindex_fidelity.py` | `TestReadCoverageSelection.test_stale_when_only_empty_files_present` | 14 | filesystem or tmp_path I/O; mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_selfindex_fidelity.py` | `TestReadOnlyGuarantee.test_no_writes_outside_report` | 25 | filesystem or tmp_path I/O; mocks, fakes, or monkeypatches control flow; subprocess or process capture |
| `portal/modules/security/tests/test_selfindex_fidelity.py` | `TestValidatorJsonParsing.test_empty_stdout_is_honestly_absent` | 6 | mocks, fakes, or monkeypatches control flow; subprocess or process capture |
| `portal/modules/security/tests/test_selfindex_fidelity.py` | `TestValidatorJsonParsing.test_nonzero_returncode_is_not_treated_as_absent` | 13 | mocks, fakes, or monkeypatches control flow; subprocess or process capture |
| `portal/modules/security/tests/test_selfindex_fidelity.py` | `TestValidatorJsonParsing.test_parses_multiline_pretty_printed_json_with_preamble` | 19 | mocks, fakes, or monkeypatches control flow; subprocess or process capture |
| `portal/modules/security/tests/test_selfindex_fidelity.py` | `TestValidatorJsonParsing.test_unparseable_stdout_is_honestly_absent` | 5 | mocks, fakes, or monkeypatches control flow; subprocess or process capture |
| `portal/modules/security/tests/test_splunk_blue.py` | `TestBlueTriage.test_report_triage_writes_file` | 8 | filesystem or tmp_path I/O |
| `portal/modules/security/tests/test_splunk_blue.py` | `TestCaptureStore.test_list_captures_filters_by_scenario` | 22 | filesystem or tmp_path I/O; mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_splunk_blue.py` | `TestCaptureStore.test_replay_capture_dry_run_skips_indexed_check` | 26 | filesystem or tmp_path I/O; mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_splunk_blue.py` | `TestCaptureStore.test_replay_capture_reships_and_confirms` | 37 | filesystem or tmp_path I/O; mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_splunk_blue.py` | `TestCaptureStore.test_save_capture_returns_none_for_empty_telemetry` | 10 | filesystem or tmp_path I/O; mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_splunk_blue.py` | `TestCaptureStore.test_save_capture_writes_file` | 22 | filesystem or tmp_path I/O; mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_splunk_blue.py` | `TestIndexWait.test_wait_indexed_timeout_returns_false` | 20 | mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_splunk_blue.py` | `TestMatrixTelemetryWiring.test_execute_unit_calls_telemetry_collection` | 36 | mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_splunk_blue.py` | `TestMeta3Collect.test_collect_meta3_does_not_tail_unbounded_tomcat_history` | 26 | mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_splunk_blue.py` | `TestMeta3Collect.test_collect_meta3_empty_output_omits_sourcetype` | 11 | mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_splunk_blue.py` | `TestMeta3Collect.test_collect_meta3_never_requests_flat_file_tails` | 19 | mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_splunk_blue.py` | `TestMeta3Collect.test_collect_meta3_no_mcp_call_returns_empty` | 8 | mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_splunk_blue.py` | `TestMeta3Collect.test_collect_meta3_returns_time_bounded_windows_events_only` | 25 | mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_splunk_blue.py` | `TestTalonRemoved.test_no_talon_image_in_compose_lab` | 7 | filesystem or tmp_path I/O |
| `portal/modules/security/tests/test_stage2_propose.py` | `TestFalsePromotionGuard.test_hollow_flag_flip_never_promotable` | 21 | mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_stage2_propose.py` | `TestGateHolds.test_apply_batch_applies_only_when_promotable_and_diff_staged` | 21 | filesystem or tmp_path I/O |
| `portal/modules/security/tests/test_stage2_propose.py` | `TestGateHolds.test_apply_batch_is_never_invoked_by_run_stage2_or_write_report` | 13 | filesystem or tmp_path I/O; source or golden snapshot |
| `portal/modules/security/tests/test_stage2_propose.py` | `TestGateHolds.test_propose_without_apply_writes_nothing_to_oracle_source` | 16 | filesystem or tmp_path I/O; mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_sweep_parallel.py` | `TestGetWorkers.test_default` | 3 | mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_sweep_parallel.py` | `TestGetWorkers.test_override` | 3 | mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_target_readiness_ports.py` | `TestEnsureTargetReady.test_already_up_no_cmd_up` | 12 | mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_target_readiness_ports.py` | `TestEnsureTargetReady.test_down_target_healed_via_cmd_up` | 22 | mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_target_readiness_ports.py` | `TestEnsureTargetReady.test_heal_fails_returns_unrecoverable` | 17 | mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_target_readiness_ports.py` | `TestEnsureTargetReady.test_phpmyadmin_version_mismatch_is_persistently_repaired` | 28 | mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_target_readiness_ports.py` | `TestEnsureTargetReady.test_rails_port_requires_the_expected_web_console_service` | 30 | mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_target_readiness_ports.py` | `TestExistingPrimitives.test_gate_imports_only_existing_functions` | 40 | source or golden snapshot |
| `portal/modules/security/tests/test_target_readiness_ports.py` | `TestPublishedPort.test_falls_back_to_first_port_when_nothing_answers_http` | 15 | mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_target_readiness_ports.py` | `TestPublishedPort.test_prefers_http_responsive_port_over_first_listed` | 14 | mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_target_readiness_ports.py` | `TestPublishedPort.test_retries_across_a_wait_window_before_falling_back` | 27 | mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_target_readiness_ports.py` | `TestPublishedPort.test_scenario_owned_binary_port_does_not_require_http` | 19 | mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_target_readiness_ports.py` | `TestPublishedPort.test_scenario_owned_container_port_avoids_auxiliary_listener` | 20 | mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_target_readiness_ports.py` | `TestPublishedPort.test_single_port_waits_for_http_readiness` | 11 | mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_target_readiness_ports.py` | `TestPublishedPort.test_unpublished_matching_port_does_not_mask_published_service` | 22 | mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_target_readiness_ports.py` | `TestRunLoopIntegration.test_prepare_scenario_calls_gate` | 19 | mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_target_readiness_ports.py` | `TestRunLoopIntegration.test_prepare_scenario_default_heal_matches_lab_exec` | 16 | mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_target_readiness_ports.py` | `TestRunLoopIntegration.test_prepare_scenario_injects_port_into_prompt` | 19 | mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_target_readiness_ports.py` | `TestRunLoopIntegration.test_prepare_scenario_unrecoverable` | 18 | mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_telemetry_contracts.py` | `TestProtocolUnification.test_blue_does_not_define_own_protocol` | 11 | source or golden snapshot |
| `portal/modules/security/tests/test_telemetry_contracts.py` | `TestProtocolUnification.test_matrix_does_not_define_own_protocol` | 10 | source or golden snapshot |
| `portal/modules/security/tests/test_telemetry_contracts.py` | `TestTelemetryHealth.test_backend_exception_returns_collection_failed` | 8 | mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_telemetry_contracts.py` | `TestTelemetryHealth.test_empty_telemetry_returns_not_configured` | 11 | mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_telemetry_contracts.py` | `TestTelemetryHealth.test_health_result_has_timestamp` | 6 | mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_telemetry_contracts.py` | `TestTelemetryHealth.test_health_result_to_dict` | 12 | mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_telemetry_contracts.py` | `TestTelemetryHealth.test_healthy_source_returns_observed` | 12 | mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_telemetry_contracts.py` | `TestTelemetryHealth.test_synthetic_fallback_returns_not_configured` | 11 | mocks, fakes, or monkeypatches control flow |
| `portal/modules/security/tests/test_toolcall_reliability.py` | `test_chain_retry_messages_use_user_role_not_tool_role` | 24 | source or golden snapshot |
| `portal/modules/security/tests/test_validation.py` | `TestValidateUsecase.test_no_lab_exec_indeterminate` | 4 | mocks, fakes, or monkeypatches control flow |
| `portal/modules/vulnintel/tests/test_vulnintel_mcp.py` | `test_kev_hard_override` | 13 | mocks, fakes, or monkeypatches control flow |
| `portal/modules/vulnintel/tests/test_vulnintel_mcp.py` | `test_non_kev_low_signal_is_low` | 11 | mocks, fakes, or monkeypatches control flow |
| `portal/platform/agent/tests/test_agent_core.py` | `test_decide_declines_when_no_candidates` | 4 | mocks, fakes, or monkeypatches control flow |
| `portal/platform/agent/tests/test_agent_core.py` | `test_decide_is_grounded_and_deterministic` | 8 | mocks, fakes, or monkeypatches control flow |
| `portal/platform/agent/tests/test_agent_core.py` | `test_deterministic_fallback_progresses_to_oracle_after_recon` | 25 | mocks, fakes, or monkeypatches control flow |
| `portal/platform/agent/tests/test_agent_core.py` | `test_deterministic_fallback_starts_with_reconnaissance` | 12 | mocks, fakes, or monkeypatches control flow |
| `portal/platform/agent/tests/test_agent_core.py` | `test_deterministic_fallback_understands_direct_decision_history` | 17 | mocks, fakes, or monkeypatches control flow |
| `portal/platform/agent/tests/test_agent_core.py` | `test_invalid_goal_short_circuits` | 3 | mocks, fakes, or monkeypatches control flow |
| `portal/platform/agent/tests/test_agent_core.py` | `test_loop_completes_on_stop_condition` | 6 | mocks, fakes, or monkeypatches control flow |
| `portal/platform/agent/tests/test_agent_core.py` | `test_loop_flags_low_confidence` | 10 | mocks, fakes, or monkeypatches control flow |
| `portal/platform/agent/tests/test_agent_core.py` | `test_loop_honest_blocked_not_faked_green` | 3 | mocks, fakes, or monkeypatches control flow |
| `portal/platform/agent/tests/test_agent_core.py` | `test_loop_respects_iteration_budget` | 14 | mocks, fakes, or monkeypatches control flow |
| `portal/platform/agent/tests/test_agent_core.py` | `test_model_turn_is_never_load_bearing` | 4 | mocks, fakes, or monkeypatches control flow |
| `portal/platform/agent/tests/test_agent_core.py` | `test_writeback_is_hermetic` | 16 | filesystem or tmp_path I/O |
| `portal/platform/inference/tool_preselect/tests/test_config.py` | `TestGlobalFlag.test_default_off` | 3 | mocks, fakes, or monkeypatches control flow |
| `portal/platform/inference/tool_preselect/tests/test_config.py` | `TestGlobalFlag.test_explicit_off` | 3 | mocks, fakes, or monkeypatches control flow |
| `portal/platform/inference/tool_preselect/tests/test_config.py` | `TestGlobalFlag.test_explicit_on` | 3 | mocks, fakes, or monkeypatches control flow |
| `portal/platform/inference/tool_preselect/tests/test_config.py` | `TestIsPreselectEnabled.test_auto_disabled_workspace_returns_false` | 12 | mocks, fakes, or monkeypatches control flow |
| `portal/platform/inference/tool_preselect/tests/test_config.py` | `TestIsPreselectEnabled.test_both_on_enables` | 4 | mocks, fakes, or monkeypatches control flow |
| `portal/platform/inference/tool_preselect/tests/test_config.py` | `TestIsPreselectEnabled.test_global_off_disables_regardless_of_workspace` | 4 | mocks, fakes, or monkeypatches control flow |
| `portal/platform/inference/tool_preselect/tests/test_config.py` | `TestIsPreselectEnabled.test_global_on_but_no_workspace_optin` | 3 | mocks, fakes, or monkeypatches control flow |
| `portal/platform/inference/tool_preselect/tests/test_config.py` | `TestPreselectModel.test_default_model` | 3 | mocks, fakes, or monkeypatches control flow |
| `portal/platform/inference/tool_preselect/tests/test_config.py` | `TestPreselectModel.test_env_override` | 3 | mocks, fakes, or monkeypatches control flow |
| `portal/platform/inference/tool_preselect/tests/test_metrics.py` | `TestRecordPreselectCall.test_fallback_outcome_does_not_raise` | 4 | mocks, fakes, or monkeypatches control flow |
| `portal/platform/inference/tool_preselect/tests/test_metrics.py` | `TestRecordPreselectCall.test_ok_outcome_increments_counter` | 5 | mocks, fakes, or monkeypatches control flow |
| `portal/platform/inference/tool_preselect/tests/test_preselector.py` | `TestOllamaOutcomes.test_connection_error_falls_back` | 20 | mocks, fakes, or monkeypatches control flow; network or HTTP client |
| `portal/platform/inference/tool_preselect/tests/test_preselector.py` | `TestOllamaOutcomes.test_low_confidence_falls_back` | 21 | mocks, fakes, or monkeypatches control flow |
| `portal/platform/inference/tool_preselect/tests/test_preselector.py` | `TestOllamaOutcomes.test_ok_path_returns_topk_subset` | 21 | mocks, fakes, or monkeypatches control flow |
| `portal/platform/inference/tool_preselect/tests/test_preselector.py` | `TestOllamaOutcomes.test_payload_caps_num_ctx` | 26 | mocks, fakes, or monkeypatches control flow |
| `portal/platform/inference/tool_preselect/tests/test_preselector.py` | `TestOllamaOutcomes.test_timeout_falls_back` | 20 | mocks, fakes, or monkeypatches control flow; network or HTTP client |
| `portal/platform/inference/tool_preselect/tests/test_preselector.py` | `TestOllamaOutcomes.test_unexpected_exception_never_raises` | 20 | mocks, fakes, or monkeypatches control flow |
| `portal/platform/inference/tool_preselect/tests/test_preselector.py` | `TestOllamaOutcomes.test_unparseable_output_falls_back` | 20 | mocks, fakes, or monkeypatches control flow |
| `portal/platform/wiki/tests/test_migration.py` | `TestDocIsMigratedV2.test_fence_without_reason_not_migrated` | 16 | filesystem or tmp_path I/O |
| `portal/platform/wiki/tests/test_migration.py` | `TestDocIsMigratedV2.test_no_generated_blocks_not_migrated` | 12 | filesystem or tmp_path I/O |
| `portal/platform/wiki/tests/test_migration.py` | `TestDocIsMigratedV2.test_ratio_boundary_at_max` | 22 | filesystem or tmp_path I/O |
| `portal/platform/wiki/tests/test_migration.py` | `TestDocIsMigratedV2.test_ratio_within_bound` | 21 | filesystem or tmp_path I/O |
| `portal/platform/wiki/tests/test_migration.py` | `TestDocIsMigratedV2.test_real_generated_block_with_small_fence_is_migrated` | 19 | filesystem or tmp_path I/O |
| `portal/platform/wiki/tests/test_migration.py` | `TestDocIsMigratedV2.test_unmigrated_content_detected` | 14 | filesystem or tmp_path I/O |
| `portal/platform/wiki/tests/test_migration.py` | `TestDocIsMigratedV2.test_v1_fence_everything_not_migrated` | 15 | filesystem or tmp_path I/O |
| `portal/platform/wiki/tests/test_render.py` | `TestProjectionSymmetry.test_render_then_currency_check_agree` | 14 | filesystem or tmp_path I/O; mocks, fakes, or monkeypatches control flow |
| `portal/platform/wiki/tests/test_render.py` | `TestProjectionSymmetry.test_second_render_is_idempotent` | 15 | filesystem or tmp_path I/O; mocks, fakes, or monkeypatches control flow |
| `portal/platform/wiki/tests/test_render.py` | `TestRenderReport.test_blocks_counted` | 15 | filesystem or tmp_path I/O |
| `portal/platform/wiki/tests/test_render.py` | `TestRenderReport.test_coverage_pct_calculation` | 13 | filesystem or tmp_path I/O |
| `portal/platform/wiki/tests/test_render.py` | `TestRenderReport.test_migrated_doc_detected` | 13 | filesystem or tmp_path I/O |
| `portal/platform/wiki/tests/test_render.py` | `TestRenderReport.test_report_structure` | 11 | filesystem or tmp_path I/O |
| `portal/platform/wiki/tests/test_render.py` | `TestRenderReport.test_unmigrated_doc_detected` | 11 | filesystem or tmp_path I/O |

## Kept files

| lines | path | keep rule |
| ---: | --- | --- |
| 838 | `portal/modules/security/tests/test_bench_scoring.py` | rule3 x81 |
| 832 | `portal/modules/security/tests/test_rbp_episode_grounding.py` | rule3 x44 |
| 596 | `portal/modules/security/tests/test_ablation_attribution.py` | rule3 x32 |
| 542 | `portal/modules/security/tests/test_blue_orchestrate_loop.py` | rule1 x6, rule3 x7 |
| 465 | `portal/modules/security/tests/test_splunk_blue.py` | rule1 x3, rule2 x1, rule3 x29 |
| 413 | `portal/modules/security/tests/test_blue_linux.py` | rule1 x6, rule3 x8 |
| 408 | `portal/modules/security/tests/test_capability_graph.py` | rule3 x35 |
| 366 | `portal/modules/security/tests/test_target_readiness_ports.py` | rule1 x6, rule3 x13 |
| 343 | `portal/modules/security/tests/test_unknown_defense.py` | rule1 x4, rule3 x23 |
| 313 | `portal/modules/security/tests/test_agentic_blue_scoring.py` | rule3 x31 |
| 285 | `portal/modules/security/tests/test_coverage_expand.py` | rule3 x22 |
| 268 | `portal/modules/security/tests/test_investigation_evidence.py` | rule3 x13 |
| 247 | `portal/modules/security/tests/test_kali_enable.py` | rule3 x21 |
| 241 | `portal/modules/security/tests/test_self_index.py` | rule3 x11 |
| 235 | `portal/modules/security/tests/test_capture_enrichment.py` | rule1 x3, rule3 x11 |
| 221 | `portal/modules/security/tests/test_candidate_eval.py` | rule2 x1, rule3 x13 |
| 218 | `portal/modules/security/tests/test_web_exec_coverage.py` | rule3 x16 |
| 215 | `portal/modules/security/tests/test_stage2_propose.py` | rule1 x1, rule3 x7 |
| 213 | `portal/modules/security/tests/test_multichain.py` | rule3 x13 |
| 209 | `portal/modules/security/tests/test_agentic_blue_multitrial.py` | rule3 x20 |
| 205 | `portal/modules/security/tests/test_labexec_coverage.py` | rule3 x16 |
| 203 | `portal/modules/security/tests/test_council_agreement.py` | rule3 x15 |
| 198 | `portal/platform/wiki/tests/test_migration.py` | rule3 x16 |
| 187 | `portal/modules/security/tests/test_bench_investigation.py` | rule3 x18 |
| 184 | `portal/modules/security/tests/test_sweep_reporting.py` | rule3 x10 |
| 175 | `portal/modules/security/tests/test_response_loop.py` | rule3 x15 |
| 173 | `portal/modules/security/tests/test_goal_decide.py` | rule3 x18 |
| 168 | `portal/modules/security/tests/test_blue_grounding.py` | rule1 x1, rule3 x10 |
| 168 | `portal/modules/security/tests/test_capability_index.py` | rule3 x24 |
| 162 | `portal/modules/security/tests/test_prerun_readiness.py` | rule3 x7 |
| 157 | `portal/modules/security/tests/test_sweep_confidence.py` | rule3 x15 |
| 139 | `portal/modules/security/tests/test_drift_gate.py` | rule3 x13 |
| 138 | `portal/modules/security/tests/test_blue_orchestrate_reasoning.py` | rule1 x2, rule3 x9 |
| 138 | `portal/modules/security/tests/test_toolcall_reliability.py` | rule1 x2, rule3 x11 |
| 132 | `portal/modules/security/tests/test_recall_attribution.py` | rule3 x16 |
| 126 | `portal/modules/security/tests/test_telemetry_contracts.py` | rule3 x13 |
| 116 | `portal/modules/security/tests/test_sweep_parallel.py` | rule3 x11 |
| 116 | `portal/platform/wiki/tests/test_render.py` | rule3 x14 |
| 115 | `portal/modules/security/tests/test_candidate_eval_incumbent.py` | rule2 x5, rule3 x5 |
| 115 | `portal/modules/security/tests/test_notify_scoreboard.py` | rule3 x7 |
| 111 | `portal/modules/security/tests/test_oracles.py` | rule3 x14 |
| 109 | `portal/modules/security/tests/test_blue_orchestrate_expert.py` | rule1 x2, rule3 x1 |
| 108 | `portal/modules/security/tests/test_spl_variants.py` | rule3 x10 |
| 105 | `portal/modules/security/tests/test_blue_orchestrate_toolleg.py` | rule3 x10 |
| 104 | `portal/modules/security/tests/test_benign_corpus_bench.py` | rule3 x7 |
| 101 | `portal/modules/security/tests/test_capsules.py` | rule3 x5 |
| 100 | `portal/modules/security/tests/test_ability_port.py` | rule3 x18 |
| 95 | `portal/modules/security/tests/test_selfindex_fidelity.py` | rule3 x5 |
| 93 | `portal/modules/security/tests/test_analyst_verdict.py` | rule3 x11 |
| 93 | `portal/modules/security/tests/test_corpus_replay_bench.py` | rule3 x6 |
| 92 | `portal/modules/security/tests/test_playbooks.py` | rule3 x7 |
| 87 | `portal/modules/security/tests/test_replay_captured_red_no_evidence.py` | rule1 x3 |
| 85 | `portal/modules/security/tests/test_compliance_mapping.py` | rule3 x3 |
| 78 | `portal/modules/security/tests/test_perception_scope.py` | rule3 x7 |
| 71 | `portal/modules/security/tests/test_emergent_recall.py` | rule3 x3 |
| 68 | `portal/modules/detection/tests/test_detection_mcp.py` | rule3 x7 |
| 68 | `portal/modules/security/tests/test_subtechnique_gate.py` | rule1 x8 |
| 67 | `portal/platform/inference/tool_preselect/tests/test_parser.py` | rule3 x17 |
| 64 | `portal/modules/security/tests/test_red_only_network_capture_wiring.py` | rule1 x3 |
| 64 | `portal/modules/security/tests/test_technique_signatures.py` | rule3 x7 |
| 60 | `portal/modules/security/tests/test_attack_telemetry_bridge.py` | rule3 x4 |
| 59 | `portal/modules/security/tests/test_sec_capabilities.py` | rule3 x7 |
| 56 | `portal/modules/security/tests/test_loop.py` | rule3 x8 |
| 55 | `portal/modules/compliance/tests/test_compliance_mcp.py` | rule2 x1, rule3 x5 |
| 55 | `portal/modules/security/tests/test_compliance_report.py` | rule3 x4 |
| 55 | `portal/modules/security/tests/test_emergent_gaps.py` | rule3 x5 |
| 54 | `portal/modules/security/tests/test_trajectory_scoring.py` | rule3 x6 |
| 50 | `portal/modules/security/tests/test_capture_recipes.py` | rule3 x2 |
| 49 | `portal/modules/security/tests/test_matrix.py` | rule1 x1 |
| 46 | `portal/platform/inference/tool_preselect/tests/test_preselector.py` | rule3 x3 |
| 45 | `portal/modules/security/tests/test_loop_notify.py` | rule3 x3 |
| 44 | `portal/platform/inference/tool_preselect/tests/test_config.py` | rule3 x7 |
| 44 | `portal/platform/inference/tool_preselect/tests/test_state.py` | rule3 x7 |
| 41 | `portal/modules/security/tests/test_sandbox_output_cap.py` | rule1 x3 |
| 40 | `portal/modules/icsot/tests/test_icsot_mcp.py` | rule3 x4 |
| 36 | `portal/modules/binary_research/tests/test_loop.py` | rule3 x5 |
| 36 | `portal/modules/security/tests/conftest.py` | rule 1 — isolation fixture the write-through regression test pins |
| 35 | `portal/modules/data/tests/test_data_mcp.py` | rule3 x4 |
| 35 | `portal/platform/inference/tool_preselect/tests/test_metrics.py` | rule3 x3 |
| 34 | `portal/platform/agent/tests/test_agent_core.py` | rule3 x2 |
| 33 | `portal/modules/vulnintel/tests/test_vulnintel_mcp.py` | rule3 x3 |
| 29 | `portal/modules/security/tests/test_write_isolation.py` | rule1 x1 |
| 27 | `portal/modules/security/tests/test_sec_intake.py` | rule3 x3 |
| 21 | `portal/modules/netforensics/tests/test_netforensics_mcp.py` | rule3 x2 |
| 20 | `portal/modules/binary_research/tests/test_verifiers.py` | rule3 x3 |
| 20 | `portal/modules/security/tests/test_evidence_chain_validity.py` | rule3 x1 |
| 20 | `portal/modules/security/tests/test_validation.py` | rule3 x1 |
| 19 | `portal/modules/binary_research/tests/test_scaffold.py` | rule3 x4 |
| 13 | `portal/modules/security/tests/test_lab_targets.py` | rule3 x1 |
| 12 | `portal/modules/security/tests/test_corpus_coverage.py` | rule3 x1 |
