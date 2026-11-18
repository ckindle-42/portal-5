# Phase 1b test trim — trim-unit-b

Scope: `tests/unit/test_[m-z]*.py` plus every file under a `tests/unit/` subdirectory (`tests/unit/router/`). Phase 1 had already cut this scope from 55,737 to 55,472 lines. This pass applies the phase-1b keep rules: a named live bug, a contract the running system loads, or pure logic with no I/O and no mocks. Anything else in scope was deleted.

The offline suite is the merge gate. It is not live proof.

## Counts

| measure | before (HEAD, after phase 1) | after |
| --- | --- | --- |
| Scope files | 189 | 110 |
| Scope Python lines | 55472 | 19816 |
| Share kept | | 35.7% (19816/55472) |
| Whole files deleted | | 79 |
| Files kept whole | | 56, then `test_uat_grading.py` was cut further |
| Files split | | 54 |
| `uv run pytest tests/unit/ tests/wfe -q -n auto` | 7461 passed, 127 skipped (phase 1) | 5731 passed, 127 skipped, 123.37s, exit 0 |
| `uv run ruff check .` and `uv run ruff format --check .` | | clean (1913 files already formatted) |
| `python3 scripts/complexity_report.py --gate` | GATE OK, unwired_scripts 24/25 | GATE FAIL: unwired_scripts 26 > ceiling 25. Other ceilings hold: data_lines 12442/13370, god_lines 70469/71202, identical_pairs 0, committed_blob_bytes 1792894/1873616. Budget file not edited. |

Deleting `tests/unit/test_rotate_logs.py` and `tests/unit/test_speed_bench.py` left `scripts/rotate_logs.py` and `scripts/speed_bench.py` with no remaining reference in the census haystack, which is why `unwired_scripts` went from 24 to 26. The brief says a ceiling that deletions break is reported, not raised.

## Corrections after the classifier

- `tests/unit/test_uat_grading.py` matched rule 1 (inverted-critical grading and the word-boundary mismatch) and was kept whole. The tests that use `tmp_path` or monkeypatch were then removed by hand. Dropped: `test_remove_rows_for_test_ids`, `test_rebuild_summary_from_rows`, `test_wait_for_response_arrival_returns_immediately_on_content`, `test_wait_for_response_arrival_no_token_falls_back_to_safety_buffer`, `test_wait_for_backend_alive_returns_true_on_recovery`, `test_wait_for_backend_alive_skips_polling_for_non_backend_tier`, `test_polling_constants_present`, `test_send_and_wait_signature_accepts_token_and_chat_id`. Kept: `test_critical_fail_overrides_high_pct`, `test_no_critical_marker_defaults_to_critical`, `test_all_pass_returns_pass`, `test_word_boundary_excludes_substring_match`, `test_word_boundary_default_preserves_legacy_behavior`, `test_word_boundary_keyword_with_trailing_nonword`, `test_word_boundary_word_to_word_transition_does_not_fire`.
- Name-closure missed helpers that a kept test, or an out-of-scope test, still calls. Restored from HEAD, not as new behavior: `_restore_digest_state` in `tests/unit/test_tps_metrics.py` (the fixture name only appeared in a string decorator); `_FakeClient.embed_texts` in `tests/unit/test_platform_embedding.py` (called by `AnchorClassifier.build`); `_FakeHealthResp` and `_FakeTable` in `tests/unit/test_rag_multimodal.py` (the kept search test reads `results`); `_watcher`, `_Gate`, `_stub_page_cache_drop`, and `_runner` in `tests/unit/test_orchestration_jobs.py` (`tests/unit/test_arm_escalation.py`, outside this lane, imports `_runner`).
- Fixtures used only by removed tests: `tests/data/cad_scad_golden/` (only `test_scad_golden.py`) and `tests/fixtures/wiki_search_baseline.json` (only the dropped baseline loop in `test_wiki_search_ranking.py`). `portal/modules/cad/PLATFORM.md`, `portal_wiki/canonical/unit-module-cad.md`, and `portal_wiki/canonical/unit-tests-unit-test-wiki-search-ranking.md` no longer cite those paths.
- Spine citations of deleted tests were retargeted, not restored. Source paths removed from: `unit-design-wiki-archive-mechanism`, `unit-host-log-rotation`, `unit-known-limitations-auto-rag-silent-miss`, `unit-known-limitations-request-size-cap-relies-on-content-length-only`, `unit-ollama-native-passthrough` (passthrough and direct-allowlist), `unit-platform-retrieval-substrate-migration`. `KNOWN_LIMITATIONS.md` and `unit-known-limitations-pipeline-hardening-20260925` now cite `portal/platform/inference/load_guard.py` where they cited `tests/unit/test_stream_parity.py`. The auto-RAG item cites `portal/platform/inference/router/context_inject.py`. The request-size unit no longer backticks the deleted test name.

## Deleted files

| path | lines | why it fails the keep rules |
| --- | ---: | --- |
| `tests/unit/router/test_image_reroute.py` | 150 | mocks, patches, or I/O |
| `tests/unit/test_mcp_vendor_smoke.py` | 66 | upstream MCP SDK import smoke, not a loaded contract |
| `tests/unit/test_memory_eval_scope.py` | 131 | mocks, patches, or I/O |
| `tests/unit/test_memory_gate_headroom.py` | 186 | mocks, patches, or I/O |
| `tests/unit/test_memrag_native_rest_parity.py` | 183 | mocks, patches, or I/O |
| `tests/unit/test_mlx_audio_idle_unload.py` | 350 | tooling script off the product path |
| `tests/unit/test_mlx_cache_probe.py` | 339 | tooling script off the product path |
| `tests/unit/test_mlx_cache_release.py` | 458 | tooling script off the product path |
| `tests/unit/test_model_management_dashboard.py` | 68 | mocks, patches, or I/O |
| `tests/unit/test_model_upstream.py` | 761 | tooling script off the product path |
| `tests/unit/test_module_services.py` | 624 | mocks, patches, or I/O |
| `tests/unit/test_module_toggle.py` | 161 | mocks, patches, or I/O |
| `tests/unit/test_netguard.py` | 69 | unit-harness network guard, not product logic |
| `tests/unit/test_ollama_direct_allowlist.py` | 59 | tooling script off the product path |
| `tests/unit/test_ollama_passthrough.py` | 376 | mocks, patches, or I/O |
| `tests/unit/test_omlx_auth.py` | 55 | mocks, patches, or I/O |
| `tests/unit/test_omlx_chat_template_patch.py` | 76 | tooling script, off the product path |
| `tests/unit/test_omlx_memory_tier.py` | 38 | tooling script, off the product path |
| `tests/unit/test_orchestration_rbp_injection.py` | 116 | mocks, patches, or I/O |
| `tests/unit/test_owui_hunt_chat_proof.py` | 436 | tooling script off the product path |
| `tests/unit/test_owui_seeding_payloads.py` | 182 | golden snapshot of seed payloads |
| `tests/unit/test_pending_verdicts_alignment.py` | 82 | tooling script off the product path |
| `tests/unit/test_persona_matrix_diff.py` | 92 | tests a test helper, off the product path |
| `tests/unit/test_pipeline_tool_carry.py` | 450 | mocks, patches, or I/O |
| `tests/unit/test_platform_module_boundary.py` | 33 | mocks, patches, or I/O |
| `tests/unit/test_prismml_mlx_server.py` | 114 | tooling script off the product path |
| `tests/unit/test_promptfoo_configs.py` | 101 | promptfoo is not a contract the running system loads |
| `tests/unit/test_proxmox_mcp.py` | 126 | mocks, patches, or I/O |
| `tests/unit/test_quality_signals.py` | 156 | scorer lives under tests/, off the product path |
| `tests/unit/test_rag_eval_scope.py` | 140 | mocks, patches, or I/O |
| `tests/unit/test_rag_kb_list.py` | 70 | mocks, patches, or I/O |
| `tests/unit/test_rag_tool_contract.py` | 219 | mocks, patches, or I/O |
| `tests/unit/test_realuse_fixture_builder.py` | 23 | tooling script off the product path |
| `tests/unit/test_request_limits.py` | 60 | mocks, patches, or I/O |
| `tests/unit/test_request_slot.py` | 187 | mocks, patches, or I/O |
| `tests/unit/test_research_probe_scoring.py` | 138 | mocks, patches, or I/O |
| `tests/unit/test_retrieval_catalog_pagination.py` | 34 | mocks, patches, or I/O |
| `tests/unit/test_retrieval_contextualize_gate.py` | 67 | tooling script off the product path |
| `tests/unit/test_retrieval_predicates.py` | 405 | mocks, patches, or I/O |
| `tests/unit/test_root_dispatcher.py` | 72 | mocks, patches, or I/O |
| `tests/unit/test_rotate_logs.py` | 138 | tooling script off the product path |
| `tests/unit/test_router_bench.py` | 52 | tooling script off the product path |
| `tests/unit/test_sandbox_network_flag.py` | 41 | source-text snapshot of the sandbox flag |
| `tests/unit/test_scad_golden.py` | 25 | golden SCAD snapshot |
| `tests/unit/test_seat_preflight.py` | 219 | tooling script off the product path |
| `tests/unit/test_seat_screen.py` | 191 | tooling script off the product path |
| `tests/unit/test_seat_screen_grader.py` | 116 | tooling script off the product path |
| `tests/unit/test_seat_screen_kit_apply.py` | 104 | tooling script off the product path |
| `tests/unit/test_security_autoupdate.py` | 249 | tooling script off the product path |
| `tests/unit/test_security_call_model_route.py` | 97 | mocks, patches, or I/O |
| `tests/unit/test_semaphore.py` | 67 | mocks, patches, or I/O |
| `tests/unit/test_settings_audit_backend_reachability.py` | 187 | tooling script off the product path |
| `tests/unit/test_settings_audit_card_preflight.py` | 245 | tooling script off the product path |
| `tests/unit/test_smoke_stream_script.py` | 91 | mocks, patches, or I/O |
| `tests/unit/test_speed_bench.py` | 368 | tooling script off the product path |
| `tests/unit/test_spine_coverage.py` | 387 | mocks, patches, or I/O |
| `tests/unit/test_state_persistence.py` | 142 | mocks, patches, or I/O |
| `tests/unit/test_stream_parity.py` | 329 | mocks, patches, or I/O |
| `tests/unit/test_tool_registry_duplicate_precedence.py` | 105 | mocks, patches, or I/O |
| `tests/unit/test_tool_registry_refresh.py` | 492 | mocks, patches, or I/O |
| `tests/unit/test_tool_registry_retry.py` | 68 | mocks, patches, or I/O |
| `tests/unit/test_transcribe_diarize.py` | 283 | tooling script off the product path |
| `tests/unit/test_triage_layer2.py` | 501 | tooling script off the product path |
| `tests/unit/test_uat_adaptive.py` | 311 | tooling script off the product path |
| `tests/unit/test_uat_browser.py` | 176 | tooling script off the product path |
| `tests/unit/test_uat_dispatch_route_params.py` | 83 | tooling script off the product path |
| `tests/unit/test_uat_engines.py` | 394 | tooling script off the product path |
| `tests/unit/test_uat_settings_gate.py` | 53 | tooling script off the product path |
| `tests/unit/test_uat_swap.py` | 374 | tooling script off the product path |
| `tests/unit/test_validation_compliance_currency_gate.py` | 39 | tooling script off the product path |
| `tests/unit/test_validation_orchestration_arm.py` | 290 | tooling script off the product path |
| `tests/unit/test_validation_serving_conformance.py` | 63 | tooling script off the product path |
| `tests/unit/test_validation_unit_tests_skip.py` | 121 | tooling script off the product path |
| `tests/unit/test_vl_retrieval_server.py` | 371 | tooling script off the product path |
| `tests/unit/test_wfe_campaign_finish.py` | 331 | tooling script off the product path |
| `tests/unit/test_wfe_campaign_script.py` | 1288 | tooling script off the product path |
| `tests/unit/test_wiki_archive.py` | 192 | mocks, patches, or I/O |
| `tests/unit/test_wiki_seed_security.py` | 92 | mocks, patches, or I/O |
| `tests/unit/test_wiki_writeback.py` | 289 | mocks, patches, or I/O |

## Split files — tests removed

A split file stays. Each row is a test that failed all three keep rules. Helpers used only by those tests were removed with them, except the restorations in the corrections section.

### `tests/unit/router/test_context_inject.py`

Was 152 lines. Now 44. Kept 6, dropped 6.

Dropped: 6 (mocks, patches, or I/O).

- `test_recall_noop_when_not_opted_in` (5 lines) — mocks, patches, or I/O
- `test_writeback_noop_when_not_opted_in` (7 lines) — mocks, patches, or I/O
- `test_writeback_all_captures_everything` (6 lines) — mocks, patches, or I/O
- `test_writeback_dispatch_args_match_memory_contract` (33 lines) — mocks, patches, or I/O
- `test_recall_dispatch_args_match_memory_contract` (25 lines) — mocks, patches, or I/O
- `test_recalled_memory_is_skipped_for_bite_requests` (18 lines) — mocks, patches, or I/O

Kept under: rule 3: values in, values out, no mocks.

Kept tests: `test_extract_snippets_shapes`, `test_extract_unknown_shape_raises`, `test_inject_merges_into_system`, `test_inject_prepends_when_no_system`, `test_salience_explicit_marker`, `test_salience_skips_ordinary_question`.

### `tests/unit/test_mcp_endpoints.py`

Was 268 lines. Now 106. Kept 5, dropped 11.

Dropped: 11 (mocks, patches, or I/O).

- `TestTTSOpenAIEndpoints.test_health_endpoint` (9 lines) — mocks, patches, or I/O
- `TestTTSOpenAIEndpoints.test_v1_models_returns_list` (7 lines) — mocks, patches, or I/O
- `TestTTSOpenAIEndpoints.test_audio_speech_endpoint_exists` (9 lines) — mocks, patches, or I/O
- `TestTTSOpenAIEndpoints.test_audio_speech_empty_input_returns_400` (9 lines) — mocks, patches, or I/O
- `TestTTSOpenAIEndpoints.test_audio_speech_missing_body_handled_gracefully` (11 lines) — mocks, patches, or I/O
- `TestWhisperOpenAIEndpoints.test_health_endpoint` (5 lines) — mocks, patches, or I/O
- `TestWhisperOpenAIEndpoints.test_v1_models_returns_whisper_1` (8 lines) — mocks, patches, or I/O
- `TestWhisperOpenAIEndpoints.test_transcriptions_endpoint_exists` (4 lines) — mocks, patches, or I/O
- `TestWhisperOpenAIEndpoints.test_transcriptions_no_file_returns_400` (8 lines) — mocks, patches, or I/O
- `TestBackendModelHintRouting.test_all_workspaces_have_routing_entries` (15 lines) — mocks, patches, or I/O
- `TestBackendModelHintRouting.test_security_workspaces_use_security_models` (15 lines) — mocks, patches, or I/O

Kept under: rule 3: values in, values out, no mocks.

Kept tests: `TestBackendModelHintRouting.test_all_workspaces_have_model_hint`, `TestBackendModelHintRouting.test_exec_workspaces_have_execute_bash_tool`, `TestBackendModelHintRouting.test_purpleteam_exec_has_chain_hops`, `TestBackendModelHintRouting.test_backend_registry_loads_all_groups`, `TestWhisperToolSchema.test_schema_names_the_parameter_the_function_takes`.

### `tests/unit/test_mcp_http_client.py`

Was 635 lines. Now 82. Kept 3, dropped 14.

Dropped: 14 (mocks, patches, or I/O).

- `test_list_tools_sends_modern_metadata_and_follows_cursors` (30 lines) — mocks, patches, or I/O
- `test_call_tool_parses_sse_and_sets_mcp_name_header` (42 lines) — mocks, patches, or I/O
- `test_call_tool_follows_same_origin_redirect_and_keeps_the_post` (23 lines) — mocks, patches, or I/O
- `test_call_tool_does_not_follow_cross_origin_or_method_changing_redirects` (19 lines) — mocks, patches, or I/O
- `test_jsonrpc_errors_are_preserved_even_on_http_error_status` (18 lines) — mocks, patches, or I/O
- `test_call_tool_cancellation_propagates_to_the_http_request` (15 lines) — mocks, patches, or I/O
- `test_tool_registry_uses_configured_native_mcp_server` (44 lines) — mocks, patches, or I/O
- `test_native_dispatch_rejects_unknown_and_missing_arguments` (59 lines) — mocks, patches, or I/O
- `test_native_scoped_compliance_routes_to_eval_and_forwards_scope` (49 lines) — mocks, patches, or I/O
- `test_legacy_server_falls_back_once_and_caches_its_session` (64 lines) — mocks, patches, or I/O
- `test_legacy_session_404_reinitializes_and_retries_once` (47 lines) — mocks, patches, or I/O
- `test_legacy_request_timeout_and_cancellation_propagate` (41 lines) — mocks, patches, or I/O
- `test_legacy_request_timeout_uses_the_call_deadline` (35 lines) — mocks, patches, or I/O
- `test_native_is_error_returns_rest_error_shape_without_tripping_breaker` (28 lines) — mocks, patches, or I/O

Kept under: rule 3: values in, values out, no mocks.

Kept tests: `test_native_tool_result_maps_to_raw_json`, `test_pipeline_mcp_native_tools_list_keeps_its_contract`, `test_map_tool_result_unwraps_sdk_wrapped_non_object_returns`.

### `tests/unit/test_media_admission.py`

Was 202 lines. Now 66. Kept 9, dropped 15.

Dropped: 15 (mocks, patches, or I/O).

- `test_no_comfyui_residue_in_launch_scripts` (4 lines) — mocks, patches, or I/O
- `test_mflux_installer_is_apple_silicon_only` (5 lines) — mocks, patches, or I/O
- `test_routine_rebuilds_do_not_reference_removed_video_service` (4 lines) — mocks, patches, or I/O
- `TestAdmit.test_admits_when_sufficient_memory` (4 lines) — mocks, patches, or I/O
- `TestAdmit.test_refuses_when_insufficient_memory` (7 lines) — mocks, patches, or I/O
- `TestAdmit.test_refusal_message_is_actionable` (13 lines) — mocks, patches, or I/O
- `TestAdmit.test_unknown_model_admitted_when_memory_plentiful` (4 lines) — mocks, patches, or I/O
- `TestAdmit.test_unknown_model_refused_on_low_memory` (5 lines) — mocks, patches, or I/O
- `TestAdmit.test_borderline_passes` (7 lines) — mocks, patches, or I/O
- `TestAdmit.test_borderline_fails` (6 lines) — mocks, patches, or I/O
- `TestAdmit.test_fails_open_when_memory_unmeasurable` (5 lines) — mocks, patches, or I/O
- `TestAdmit.test_headroom_zero_disables_check` (8 lines) — mocks, patches, or I/O
- `TestFreeGbFromVmStat.test_counts_free_inactive_speculative_purgeable` (6 lines) — mocks, patches, or I/O
- `TestFreeGbFromVmStat.test_missing_speculative_and_purgeable_default_to_zero` (8 lines) — mocks, patches, or I/O
- `TestFreeGbFromVmStat.test_returns_none_when_inactive_missing` (4 lines) — mocks, patches, or I/O

Kept under: rule 3: values in, values out, no mocks.

Kept tests: `TestMediaModelMemoryDict.test_dict_exists_and_nonempty`, `TestMediaModelMemoryDict.test_values_are_positive_floats`, `TestMediaModelMemoryDict.test_video_model_has_large_estimate`, `TestMediaModelMemoryDict.test_music_models_use_live_complete_quality_estimates`, `TestMediaModelMemoryDict.test_headroom_constant_exists`, `TestMediaModelMemoryDict.test_mflux_image_models_use_measured_estimates`, `TestEstimateJobGb.test_known_model_returns_table_value`, `TestEstimateJobGb.test_unknown_model_returns_conservative_default`, `TestMediaModelMemoryDictInSyncWithWikiFact.test_tables_match`.

### `tests/unit/test_memory_safety_watch.py`

Was 515 lines. Now 19. Kept 1, dropped 24.

Dropped: 24 (tooling script off the product path).

- `test_watch_trips_on_critical_pressure_or_low_swap_with_low_memory` (7 lines) — tooling script off the product path
- `test_watch_pid_file_ignores_invalid_and_own_pid` (5 lines) — tooling script off the product path
- `test_omlx_emergency_unload_authenticates_status_and_unloads_idle_models` (30 lines) — tooling script off the product path
- `test_ollama_base_rewrites_docker_host_for_the_host_watchdog` (9 lines) — tooling script off the product path
- `test_omlx_unload_continues_past_a_model_already_evicted` (25 lines) — tooling script off the product path
- `test_host_services_derive_labels_from_portal_config` (30 lines) — tooling script off the product path
- `test_host_services_come_from_the_real_config_without_hardcoded_labels` (5 lines) — tooling script off the product path
- `test_service_ceilings_overlay_defaults_and_ignore_bad_entries` (7 lines) — tooling script off the product path
- `test_only_eg2_embedding_has_a_measured_ceiling` (8 lines) — tooling script off the product path
- `test_footprint_under_ceiling_never_restarts` (19 lines) — tooling script off the product path
- `test_over_ceiling_restarts_only_that_service_after_n_samples` (24 lines) — tooling script off the product path
- `test_provisional_ceiling_logs_the_breach_and_never_restarts` (15 lines) — tooling script off the product path
- `test_provisional_override_of_a_measured_service_is_log_only` (18 lines) — tooling script off the product path
- `test_under_ceiling_sample_resets_the_debounce` (15 lines) — tooling script off the product path
- `test_restarts_are_rate_limited_per_service` (25 lines) — tooling script off the product path
- `test_unmeasurable_service_is_logged_once_and_never_restarted` (22 lines) — tooling script off the product path
- `test_unparseable_footprint_output_is_unmeasurable` (16 lines) — tooling script off the product path
- `test_service_without_a_declared_ceiling_uses_the_provisional_global_default` (16 lines) — tooling script off the product path
- `test_python_child_is_measured_when_launchd_job_is_a_shell_wrapper` (13 lines) — tooling script off the product path
- `test_services_only_mode_never_samples_trips_kills_or_unloads` (20 lines) — tooling script off the product path
- `test_services_only_restarts_a_measured_breach_after_three_samples` (25 lines) — tooling script off the product path
- `test_main_services_only_selects_the_services_loop_with_a_30s_default` (21 lines) — tooling script off the product path
- `test_host_ml_watch_plist_runs_the_services_only_mode` (13 lines) — tooling script off the product path
- `test_launch_sh_installs_the_host_ml_watch_job_idempotently` (10 lines) — tooling script off the product path

Kept under: rule 1: names a live bug or dated observation.

Kept tests: `test_watch_ignores_low_swap_while_memory_is_plentiful`.

### `tests/unit/test_model_refresh.py`

Was 635 lines. Now 73. Kept 4, dropped 18.

Dropped: 18 (mocks, patches, or I/O).

- `test_registry_targets_dedupe_ollama_ids_and_skip_omlx` (69 lines) — mocks, patches, or I/O
- `test_live_backends_keep_library_tags_and_do_not_pull_hf` (30 lines) — mocks, patches, or I/O
- `test_missing_pin_does_not_call_ollama_or_http` (12 lines) — mocks, patches, or I/O
- `test_sha_mismatch_refuses_create` (10 lines) — mocks, patches, or I/O
- `test_pinned_create_writes_from_and_num_ctx_only` (13 lines) — mocks, patches, or I/O
- `test_think_stop_fails_render_check` (12 lines) — mocks, patches, or I/O
- `test_template_think_text_is_not_a_stop` (4 lines) — mocks, patches, or I/O
- `test_undeclared_stop_fails_and_declared_stop_passes` (14 lines) — mocks, patches, or I/O
- `test_fleet_shaped_ids_prefer_configured_num_ctx_and_pinned_base` (49 lines) — mocks, patches, or I/O
- `test_derive_pulls_the_base_and_creates_the_ctx_tag` (25 lines) — mocks, patches, or I/O
- `test_local_and_unpinned_hf_derive_do_not_call_ollama` (28 lines) — mocks, patches, or I/O
- `test_library_pull_keeps_the_tag` (12 lines) — mocks, patches, or I/O
- `test_pull_hf_model_skips_unpinned_without_subprocess` (9 lines) — mocks, patches, or I/O
- `test_pull_hf_model_library_tag_is_unchanged` (14 lines) — mocks, patches, or I/O
- `test_registry_404_skips_local_import_shapes` (15 lines) — mocks, patches, or I/O
- `test_registry_error_skips_without_calling_the_tag_local` (25 lines) — mocks, patches, or I/O
- `test_bare_ctx_tag_derives_and_a_missing_base_is_not_pulled` (32 lines) — mocks, patches, or I/O
- `test_pinned_ctx_tag_derives_from_its_own_pin` (26 lines) — mocks, patches, or I/O

Kept under: rule 1: names a live bug or dated observation; rule 3: values in, values out, no mocks.

Kept tests: `test_update_module_has_no_hardcoded_model_list`, `test_catalog_entries_without_a_pin_skip`, `test_manifest_urls_cover_library_and_namespaced_tags`, `test_update_downloads_no_models_unless_asked`.

### `tests/unit/test_native_mcp_service.py`

Was 213 lines. Now 48. Kept 1, dropped 10.

Dropped: 10 (mocks, patches, or I/O).

- `test_native_mcp_wrapper_has_valid_shell_syntax` (9 lines) — mocks, patches, or I/O
- `test_native_mcp_wrapper_rejects_unknown_service` (10 lines) — mocks, patches, or I/O
- `test_native_mcp_wrapper_declares_every_host_native_service` (11 lines) — mocks, patches, or I/O
- `test_native_mcp_wrapper_usage_guard_matches_its_dispatch` (9 lines) — mocks, patches, or I/O
- `test_native_launchers_never_fall_back_to_global_python` (10 lines) — mocks, patches, or I/O
- `test_data_mcp_root_follows_ai_output_dir` (2 lines) — mocks, patches, or I/O
- `test_an_explicit_data_mcp_root_wins` (5 lines) — mocks, patches, or I/O
- `test_data_mcp_root_defaults_to_home_ai_output` (2 lines) — mocks, patches, or I/O
- `test_native_services_report_the_head_and_dirtiness_they_launched_from` (44 lines) — mocks, patches, or I/O
- `test_a_url_naming_a_real_host_is_left_as_the_operator_set_it` (6 lines) — mocks, patches, or I/O

Kept under: rule 1: names a live bug or dated observation.

Kept tests: `test_container_urls_from_env_are_rewritten_to_loopback_for_host_services`.

### `tests/unit/test_notifications.py`

Was 934 lines. Now 421. Kept 15, dropped 13.

Dropped: 13 (mocks, patches, or I/O).

- `TestSlackChannel.test_send_alert_success` (17 lines) — mocks, patches, or I/O
- `TestTelegramChannel.test_send_alert_skips_when_not_configured` (13 lines) — mocks, patches, or I/O
- `TestPushoverChannel.test_send_alert_skips_when_not_configured` (11 lines) — mocks, patches, or I/O
- `TestNotificationDispatcher.test_dispatcher_disabled_by_default` (17 lines) — mocks, patches, or I/O
- `TestNotificationDispatcher.test_threshold_tracking_consecutive_failures` (31 lines) — mocks, patches, or I/O
- `TestNotificationDispatcher.test_recovery_fires_event` (34 lines) — mocks, patches, or I/O
- `TestNotificationDispatcher.test_all_backends_down_fires_once` (46 lines) — mocks, patches, or I/O
- `TestNotificationDispatcher.test_all_down_clears_on_recovery` (25 lines) — mocks, patches, or I/O
- `TestNotificationScheduler.test_send_daily_summary_includes_extended_metrics` (108 lines) — mocks, patches, or I/O
- `TestSchedulerSettings.test_scheduler_disabled_when_apscheduler_missing` (17 lines) — mocks, patches, or I/O
- `TestWebhookSummaryExtendedMetrics.test_webhook_send_summary_includes_extended_metrics` (40 lines) — mocks, patches, or I/O
- `TestPushoverSummaryPriority.test_pushover_summary_uses_normal_priority` (33 lines) — mocks, patches, or I/O
- `TestDailySummaryDeltaComputation.test_summary_clamps_negative_deltas_to_zero` (76 lines) — mocks, patches, or I/O

Kept under: rule 1: names a live bug or dated observation; rule 3: values in, values out, no mocks.

Kept tests: `TestAlertEvent.test_format_slack`, `TestAlertEvent.test_format_telegram`, `TestAlertEvent.test_format_pushover_truncates`, `TestAlertEvent.test_format_email`, `TestSummaryEvent.test_format_slack`, `TestSummaryEvent.test_format_telegram`, `TestSummaryEvent.test_ttft_median_includes_sample_count_in_each_format`, `TestSummaryEvent.test_format_pushover`, `TestSummaryEvent.test_format_slack_top_models`, `TestSlackChannel.test_send_alert_skips_when_not_configured`, `TestEmailChannel.test_send_alert_skips_when_not_configured`, `TestNotificationDispatcher.test_schedule_actually_runs_the_coroutine_with_no_running_loop`, `TestDailySummaryDeltaComputation.test_summary_shows_deltas_not_cumulative_totals`, `TestNotificationChannelInterface.test_channel_has_name_property`, `TestNotificationChannelInterface.test_all_channels_registered`.

### `tests/unit/test_omlx_backend.py`

Was 411 lines. Now 148. Kept 8, dropped 12.

Dropped: 12 (mocks, patches, or I/O).

- `TestOmlxBackendBasics.test_update_omlx_live_models_warns_on_gap` (20 lines) — mocks, patches, or I/O
- `TestOmlxConfigLoad.test_loads_omlx_fields` (30 lines) — mocks, patches, or I/O
- `TestPriorityOrdering.test_higher_priority_serves_first` (30 lines) — mocks, patches, or I/O
- `TestPriorityOrdering.test_zero_priority_preserves_shuffle_semantics` (28 lines) — mocks, patches, or I/O
- `TestInjectOmlxOptions.test_caller_values_win_and_no_mutation` (10 lines) — mocks, patches, or I/O
- `TestInjectOmlxOptions.test_think_profile_wins_over_flat_fields` (20 lines) — mocks, patches, or I/O
- `TestBackendIntrospect.test_omlx_loaded_model_means_busy` (25 lines) — mocks, patches, or I/O
- `TestBackendIntrospect.test_omlx_without_loaded_models_is_not_busy` (25 lines) — mocks, patches, or I/O
- `TestBackendIntrospect.test_omlx_unreachable_means_down` (20 lines) — mocks, patches, or I/O
- `TestBackendIntrospect.test_ollama_path_uses_legacy_probe` (14 lines) — mocks, patches, or I/O
- `TestBackendIntrospect.test_type_resolution_falls_back_to_ollama` (6 lines) — mocks, patches, or I/O
- `TestBackendIntrospect.test_request_timeout_allows_omlx_prefill` (11 lines) — mocks, patches, or I/O

Kept under: rule 1: names a live bug or dated observation; rule 3: values in, values out, no mocks.

Kept tests: `TestOmlxBackendBasics.test_health_url_omlx_uses_v1_models`, `TestOmlxBackendBasics.test_health_path_override_wins`, `TestOmlxBackendBasics.test_health_url_ollama_unchanged`, `TestOmlxBackendBasics.test_resolve_model_direct_alias_and_miss`, `TestOmlxBackendBasics.test_resolve_model_skips_unserved_live_model`, `TestInjectOmlxOptions.test_injects_full_sampling_surface`, `TestAutoCodingOmlxShadowRouting.test_omlx_coding_outranks_ollama_coding`, `TestAutoCodingOmlxShadowRouting.test_production_hints_resolve_and_prioritize_omlx`.

### `tests/unit/test_omlx_capacity_retry.py`

Was 524 lines. Now 27. Kept 1, dropped 14.

Dropped: 14 (mocks, patches, or I/O).

- `test_freeable_skips_the_router_busy_and_protected_models` (8 lines) — mocks, patches, or I/O
- `test_freeable_matches_a_config_id_that_differs_from_the_served_tag_by_case` (9 lines) — mocks, patches, or I/O
- `test_an_omlx_protection_never_shields_an_ollama_model` (8 lines) — mocks, patches, or I/O
- `test_a_507_on_the_tool_loop_frees_once_and_retries_omlx` (41 lines) — mocks, patches, or I/O
- `test_a_connect_timeout_retries_the_same_backend_once` (10 lines) — mocks, patches, or I/O
- `test_a_second_connect_timeout_and_any_read_timeout_surface_as_errors` (15 lines) — mocks, patches, or I/O
- `test_non_stream_prefill_refusal_falls_back_to_the_ollama_sibling` (12 lines) — mocks, patches, or I/O
- `test_non_stream_prefill_refusal_reports_capacity_once_the_chain_is_exhausted` (14 lines) — mocks, patches, or I/O
- `test_streamed_prefill_refusal_falls_back_to_the_ollama_sibling` (12 lines) — mocks, patches, or I/O
- `test_stream_chain_exhausted_reports_the_capacity_error` (11 lines) — mocks, patches, or I/O
- `test_fallback_served_after_the_free_retry_still_wins` (14 lines) — mocks, patches, or I/O
- `test_tool_loop_prefill_refusal_falls_back_to_the_ollama_sibling` (61 lines) — mocks, patches, or I/O
- `test_non_stream_repeated_refusal_after_a_free_retry_still_cascades` (16 lines) — mocks, patches, or I/O
- `test_a_fallback_candidates_refusal_does_not_stop_the_chain` (46 lines) — mocks, patches, or I/O

Kept under: rule 3: values in, values out, no mocks.

Kept tests: `test_the_predicate_matches_both_omlx_refusals_and_nothing_else`.

### `tests/unit/test_orchestration_acceptance.py`

Was 441 lines. Now 22. Kept 1, dropped 21.

Dropped: 21 (mocks, patches, or I/O).

- `test_live_happy_path_accepts_a_goal_stated_answer` (15 lines) — mocks, patches, or I/O
- `test_live_happy_path_reports_the_failed_check` (14 lines) — mocks, patches, or I/O
- `test_acceptance_dry_run_repeats_in_the_same_workdir` (9 lines) — mocks, patches, or I/O
- `test_acceptance_dry_run_all_scenarios_pass` (16 lines) — mocks, patches, or I/O
- `test_acceptance_dry_run_phase_filter` (8 lines) — mocks, patches, or I/O
- `test_acceptance_receipts_written` (14 lines) — mocks, patches, or I/O
- `test_markdown_escapes_table_cells` (24 lines) — mocks, patches, or I/O
- `test_live_scenarios_are_required_and_skip` (9 lines) — mocks, patches, or I/O
- `test_run_live_wait_for_quiet_uses_the_shared_helper` (33 lines) — mocks, patches, or I/O
- `test_run_live_refuses_while_wfe_is_active` (23 lines) — mocks, patches, or I/O
- `test_run_live_rechecks_before_each_scenario` (35 lines) — mocks, patches, or I/O
- `test_live_force_records_overridden_host_blockers` (36 lines) — mocks, patches, or I/O
- `test_live_receipt_carries_dispatch_lane_start_and_end_snapshots` (23 lines) — mocks, patches, or I/O
- `test_wfe_clear_without_state` (6 lines) — mocks, patches, or I/O
- `test_wfe_pid_file_live_pid` (8 lines) — mocks, patches, or I/O
- `test_wfe_pid_file_dead_pid` (10 lines) — mocks, patches, or I/O
- `test_wfe_pid_file_malformed_line_fails_closed` (8 lines) — mocks, patches, or I/O
- `test_wfe_process_scan_failure_fails_closed` (10 lines) — mocks, patches, or I/O
- `test_process_scan_matches_campaign` (11 lines) — mocks, patches, or I/O
- `test_run_live_task_uses_repo_config_and_unattended_false` (20 lines) — mocks, patches, or I/O
- `test_run_live_task_missing_config_fails_loudly` (13 lines) — mocks, patches, or I/O

Kept under: rule 3: values in, values out, no mocks.

Kept tests: `test_exit_code_never_treats_required_skips_as_success`.

### `tests/unit/test_orchestration_arm.py`

Was 2270 lines. Now 337. Kept 10, dropped 68.

Dropped: 68 (mocks, patches, or I/O).

- `test_read_shadow_records_comparison_without_changing_gate` (62 lines) — mocks, patches, or I/O
- `test_read_shadow_runs_once_for_a_bite_that_retries` (39 lines) — mocks, patches, or I/O
- `test_shadow_summary_counts_false_accept_and_false_fail` (37 lines) — mocks, patches, or I/O
- `test_shadow_summary_separates_waited_from_errors` (42 lines) — mocks, patches, or I/O
- `test_shadow_clock_patch_does_not_change_process_time` (6 lines) — mocks, patches, or I/O
- `test_shadow_waits_out_busy_load_plan_then_compares` (16 lines) — mocks, patches, or I/O
- `test_shadow_honours_retry_after_on_429` (13 lines) — mocks, patches, or I/O
- `test_shadow_load_plan_429_waits_for_retry_after` (17 lines) — mocks, patches, or I/O
- `test_shadow_wait_cap_is_not_an_error` (9 lines) — mocks, patches, or I/O
- `test_shadow_model_error_after_admission_is_an_error` (5 lines) — mocks, patches, or I/O
- `test_load_plan_429_keeps_retry_after` (19 lines) — mocks, patches, or I/O
- `test_job_memory_plan_and_reclaim_use_pipeline_admin_routes` (33 lines) — mocks, patches, or I/O
- `test_arm_config_rejects_non_positive_shadow_wait` (8 lines) — mocks, patches, or I/O
- `test_arm_config_rejects_invalid_shadow_seat` (16 lines) — mocks, patches, or I/O
- `test_shadow_client_pins_spark_with_card_sampling` (35 lines) — mocks, patches, or I/O
- `test_happy_path_uses_one_pipeline_port_and_guarded_model_seat` (27 lines) — mocks, patches, or I/O
- `test_bite_tools_are_sent_as_a_strict_pipeline_allowlist` (11 lines) — mocks, patches, or I/O
- `test_client_file_tools_loop_back_to_the_model_and_keep_reading_bites_read_only` (40 lines) — mocks, patches, or I/O
- `test_action_bite_prompt_contains_read_only_snapshots_without_file_read` (41 lines) — mocks, patches, or I/O
- `test_action_bite_snapshot_truncates_to_its_context_budget` (38 lines) — mocks, patches, or I/O
- `test_finish_ignores_model_output_path_and_records_the_worker_path` (27 lines) — mocks, patches, or I/O
- `test_client_tool_loop_honors_the_hop_limit_before_executing_a_last_hop_action` (27 lines) — mocks, patches, or I/O
- `test_parallel_file_reads_execute_in_order_and_continue_to_finish` (39 lines) — mocks, patches, or I/O
- `test_parallel_batch_mixing_finish_defers_it_and_executes_the_tools` (46 lines) — mocks, patches, or I/O
- `test_parallel_batch_with_unoffered_tool_keeps_red_flags` (35 lines) — mocks, patches, or I/O
- `test_parallel_batch_over_hop_budget_is_rejected_before_tool_execution` (32 lines) — mocks, patches, or I/O
- `test_task_tools_confine_paths_and_enforce_size_limits` (20 lines) — mocks, patches, or I/O
- `test_task_tools_resist_parent_symlink_swap` (44 lines) — mocks, patches, or I/O
- `test_task_tools_cannot_write_control_plane_files` (11 lines) — mocks, patches, or I/O
- `test_task_tools_enforce_a_cumulative_data_quota` (8 lines) — mocks, patches, or I/O
- `test_task_tools_enforce_a_cumulative_file_quota` (10 lines) — mocks, patches, or I/O
- `test_pytest_copyback_uses_the_exact_write_allowlist` (27 lines) — mocks, patches, or I/O
- `test_orchestration_pytest_uses_the_locked_down_dind_envelope` (42 lines) — mocks, patches, or I/O
- `test_orchestration_pytest_timeout_removes_the_whole_container` (34 lines) — mocks, patches, or I/O
- `test_pytest_run_is_limited_to_local_tests_and_uses_container_sandbox` (24 lines) — mocks, patches, or I/O
- `test_worker_sends_input_paths_without_packing_file_contents` (16 lines) — mocks, patches, or I/O
- `test_toolless_bite_gets_its_inputs_as_snapshots` (10 lines) — mocks, patches, or I/O
- `test_submit_rejects_tools_outside_the_discipline_allowlist` (8 lines) — mocks, patches, or I/O
- `test_submit_rejects_absolute_inputs_outside_the_source_root` (14 lines) — mocks, patches, or I/O
- `test_queue_rejects_unvalidated_raw_plan` (6 lines) — mocks, patches, or I/O
- `test_refusal_red_flag_is_discarded_then_retried` (14 lines) — mocks, patches, or I/O
- `test_output_token_budget_blocks_over_cap_output` (14 lines) — mocks, patches, or I/O
- `test_wall_clock_budget_rejects_late_pipeline_output` (11 lines) — mocks, patches, or I/O
- `test_wandering_bite_without_finish_is_blocked` (9 lines) — mocks, patches, or I/O
- `test_pipeline_http_failure_mid_bite_retries_on_fast` (11 lines) — mocks, patches, or I/O
- `test_sigterm_leaves_running_bite_for_resume` (23 lines) — mocks, patches, or I/O
- `test_resume_retries_failed_bite_when_history_records_a_remaining_attempt` (25 lines) — mocks, patches, or I/O
- `test_resume_does_not_reopen_failed_bite_after_the_ladder_is_exhausted` (26 lines) — mocks, patches, or I/O
- `test_resume_refuses_build_and_model_digest_mismatch` (9 lines) — mocks, patches, or I/O
- `test_plausible_wrong_output_fails_checker_while_independent_branch_passes` (15 lines) — mocks, patches, or I/O
- `test_one_json_repair_turn_reaches_pipeline_again` (11 lines) — mocks, patches, or I/O
- `test_text_only_reply_gets_one_finish_repair_turn_then_passes` (23 lines) — mocks, patches, or I/O
- `test_finish_repair_request_forces_the_finish_tool_choice` (11 lines) — mocks, patches, or I/O
- `test_ignored_finish_repair_keeps_todays_red_flags` (13 lines) — mocks, patches, or I/O
- `test_no_finish_repair_when_the_turn_budget_is_exhausted` (10 lines) — mocks, patches, or I/O
- `test_no_finish_repair_when_the_token_budget_is_exhausted` (25 lines) — mocks, patches, or I/O
- `test_residency_config_defaults_to_swap_and_reads_co_resident` (5 lines) — mocks, patches, or I/O
- `test_overnight_queue_runs_tasks_in_fifo_order_and_records_receipts` (33 lines) — mocks, patches, or I/O
- `test_queue_blocks_one_broken_task_and_still_runs_the_next` (34 lines) — mocks, patches, or I/O
- `test_queue_review_waits_when_a_bench_lock_appears_mid_bite` (39 lines) — mocks, patches, or I/O
- `test_queue_review_capacity_refusal_waits_instead_of_burning_an_attempt` (23 lines) — mocks, patches, or I/O
- `test_queue_yield_before_the_request_does_not_count_an_attempt` (36 lines) — mocks, patches, or I/O
- `test_queue_ledger_reclaims_a_task_after_its_runner_process_dies` (22 lines) — mocks, patches, or I/O
- `test_queue_gate_yields_for_live_lock_and_pipeline_busy_or_unknown_fit` (29 lines) — mocks, patches, or I/O
- `test_fake_pipeline_enforces_production_bearer_auth` (22 lines) — mocks, patches, or I/O
- `test_fake_trace_tools_offered_matches_production_bite_gate` (11 lines) — mocks, patches, or I/O
- `test_fake_registry_missing_the_bite_tool_offers_only_what_it_owns` (23 lines) — mocks, patches, or I/O
- `test_tools_resolve_listed_input_names_to_staged_paths` (34 lines) — mocks, patches, or I/O

Kept under: rule 1: names a live bug or dated observation; rule 3: values in, values out, no mocks.

Kept tests: `test_shadow_kind_uses_discipline_read_tools`, `test_detection_engineering_template_validates_and_runs_offline`, `test_fake_pipeline_drops_server_side_tools_without_client_schemas`, `test_absent_bite_scope_preserves_existing_pipeline_tools`, `test_bite_scope_intersects_mcp_tools_and_filters_client_tools`, `test_malformed_bite_scope_is_rejected`, `test_module_switch_is_on_in_repo_config`, `test_seated_model_tags_default_follow_config_and_reject_conflicts`, `test_review_vote_parser_accepts_fenced_json_and_reports_bad_replies`, `test_review_votes_are_tool_less_bite_requests`.

### `tests/unit/test_orchestration_bite_suite.py`

Was 490 lines. Now 83. Kept 5, dropped 10.

Dropped: 10 (mocks, patches, or I/O).

- `test_detection_bite_pipeline_tools_are_auto_spl_workspace_tools` (9 lines) — mocks, patches, or I/O
- `test_bite_dry_run_sends_one_sequential_request_per_case_and_repeat` (38 lines) — mocks, patches, or I/O
- `test_testfix_bite_suite_splits_reading_and_action_tools` (20 lines) — mocks, patches, or I/O
- `test_planner_suite_uses_live_pipeline_identity_and_stays_out_of_gate_c` (21 lines) — mocks, patches, or I/O
- `test_live_bite_receipts_feed_gate_c_with_the_chosen_seat` (49 lines) — mocks, patches, or I/O
- `test_missing_tools_in_pipeline_trace_is_a_harness_error_and_gate_c_skips_it` (33 lines) — mocks, patches, or I/O
- `test_replayed_calibration_markup_is_a_harness_error` (39 lines) — mocks, patches, or I/O
- `test_all_suite_clears_bite_guard_before_the_planner_request` (46 lines) — mocks, patches, or I/O
- `test_checker_suite_scores_control_pairs_without_counting_them_as_bites` (18 lines) — mocks, patches, or I/O
- `test_invalid_model_json_is_a_scored_fail_and_only_a_json_fence_parses` (62 lines) — mocks, patches, or I/O

Kept under: rule 1: names a live bug or dated observation; rule 3: values in, values out, no mocks.

Kept tests: `test_suite_engine_identifies_as_an_api_client`, `test_planner_judge_valid_split_plan_is_valid_by_accept_and_rules_say_so`, `test_bite_worker_rejects_missing_allowlist_before_sending_request`, `test_checker_messages_state_the_exact_artifact_contract`, `test_planner_and_checker_requests_carry_the_production_output_budget`.

### `tests/unit/test_orchestration_jobs.py`

Was 2809 lines. Now 129. Kept 1, dropped 93.

Dropped: 93 (mocks, patches, or I/O).

- `test_job_spec_rejects_argv_outside_the_allowlist` (15 lines) — mocks, patches, or I/O
- `test_job_spec_accepts_repo_scripts_and_wfe_modules` (14 lines) — mocks, patches, or I/O
- `test_job_spec_rejects_a_non_executable_direct_script` (4 lines) — mocks, patches, or I/O
- `test_step_quiet_host_parses_and_round_trips` (12 lines) — mocks, patches, or I/O
- `test_preconditions_refuse_before_a_step_runs` (44 lines) — mocks, patches, or I/O
- `test_checkpoint_is_copied_before_the_step_overwrites_it` (34 lines) — mocks, patches, or I/O
- `test_job_level_output_and_checkpoint_paths_are_honoured` (34 lines) — mocks, patches, or I/O
- `test_resume_skips_done_steps_and_rerun_forces_one_step` (46 lines) — mocks, patches, or I/O
- `test_resumed_job_with_a_two_day_old_first_start_runs_under_a_fresh_budget` (34 lines) — mocks, patches, or I/O
- `test_one_attempt_that_exceeds_max_job_minutes_stops` (19 lines) — mocks, patches, or I/O
- `test_non_idempotent_rerun_requires_force` (33 lines) — mocks, patches, or I/O
- `test_job_resume_cli_requires_force_before_requeue` (58 lines) — mocks, patches, or I/O
- `test_receipt_records_argv_exit_duration_peak_tails_outputs_and_report` (51 lines) — mocks, patches, or I/O
- `test_memory_trip_stops_the_step_and_records_it` (14 lines) — mocks, patches, or I/O
- `test_step_timeout_blocks_the_job` (17 lines) — mocks, patches, or I/O
- `test_a_nonzero_step_exit_blocks_the_job_with_the_campaign_line_in_its_receipt` (23 lines) — mocks, patches, or I/O
- `test_output_marker_stops_the_job` (18 lines) — mocks, patches, or I/O
- `test_queue_runs_a_job_without_the_arm_service` (29 lines) — mocks, patches, or I/O
- `test_queue_adopts_a_live_orphaned_job_step_and_continues` (58 lines) — mocks, patches, or I/O
- `test_queue_blocks_a_gone_orphaned_step_without_rerunning_it` (58 lines) — mocks, patches, or I/O
- `test_queue_runs_a_job_from_its_enqueued_source_dir` (27 lines) — mocks, patches, or I/O
- `test_queue_defers_a_job_until_its_preconditions_clear` (39 lines) — mocks, patches, or I/O
- `test_job_reclaims_idle_model_memory_before_running_its_first_step` (38 lines) — mocks, patches, or I/O
- `test_job_waits_until_requested_model_unloads_settle` (33 lines) — mocks, patches, or I/O
- `test_quiet_host_step_drops_the_guest_page_cache_once_and_records_swap` (32 lines) — mocks, patches, or I/O
- `test_a_page_cache_drop_failure_is_recorded_and_never_blocks_the_step` (25 lines) — mocks, patches, or I/O
- `test_a_waiting_step_drops_the_page_cache_only_once` (15 lines) — mocks, patches, or I/O
- `test_a_quiet_host_false_step_does_not_drop_the_guest_page_cache` (21 lines) — mocks, patches, or I/O
- `test_drop_guest_page_cache_runs_a_privileged_container_and_records_swap` (28 lines) — mocks, patches, or I/O
- `test_drop_guest_page_cache_reports_a_docker_failure_without_raising` (15 lines) — mocks, patches, or I/O
- `test_swap_used_gib_parses_the_darwin_swapusage` (16 lines) — mocks, patches, or I/O
- `test_queue_ledger_adds_kind_to_an_existing_database` (18 lines) — mocks, patches, or I/O
- `test_enqueue_job_cli_persists_a_valid_spec` (23 lines) — mocks, patches, or I/O
- `test_telegram_job_notice_reaches_the_outbox` (18 lines) — mocks, patches, or I/O
- `test_a_job_blocked_by_cloud_lanes_claims_the_window_until_it_finishes` (19 lines) — mocks, patches, or I/O
- `test_bully_r0b_real_dryrun_spec_parses_against_the_repo` (12 lines) — mocks, patches, or I/O
- `test_the_window_is_held_while_a_step_runs` (14 lines) — mocks, patches, or I/O
- `test_a_quiet_host_false_step_runs_while_a_lane_lock_exists` (25 lines) — mocks, patches, or I/O
- `test_a_waiting_quiet_host_false_job_holds_no_window_claim` (18 lines) — mocks, patches, or I/O
- `test_a_report_step_runs_while_a_campaign_step_still_waits` (32 lines) — mocks, patches, or I/O
- `test_trip_line_is_recorded_when_the_watcher_has_not_exited` (12 lines) — mocks, patches, or I/O
- `test_a_trip_line_from_before_this_attempt_is_ignored` (7 lines) — mocks, patches, or I/O
- `test_sigterm_without_a_trip_line_stays_a_plain_exit` (11 lines) — mocks, patches, or I/O
- `test_a_live_lock_matching_start_time_blocks` (15 lines) — mocks, patches, or I/O
- `test_a_reused_pid_lock_is_stale` (15 lines) — mocks, patches, or I/O
- `test_a_dead_pid_lock_is_stale` (12 lines) — mocks, patches, or I/O
- `test_a_bare_pid_lock_is_held_only_for_portal_arm` (19 lines) — mocks, patches, or I/O
- `test_an_unreadable_command_keeps_a_bare_pid_lock` (13 lines) — mocks, patches, or I/O
- `test_window_claim_records_start_and_a_reused_pid_does_not_release` (18 lines) — mocks, patches, or I/O
- `test_a_legacy_window_claim_releases_on_pid_alone` (8 lines) — mocks, patches, or I/O
- `test_step_exports_only_named_dotenv_keys_and_redacts_them` (62 lines) — mocks, patches, or I/O
- `test_missing_dotenv_key_fails_before_the_step_starts` (29 lines) — mocks, patches, or I/O
- `test_env_from_dotenv_parse_rejects_a_key_the_allowlist_omits` (8 lines) — mocks, patches, or I/O
- `test_env_from_dotenv_requires_the_allowlist_file` (7 lines) — mocks, patches, or I/O
- `test_log_redaction_catches_a_secret_split_across_reads` (8 lines) — mocks, patches, or I/O
- `test_queue_cancel_marks_a_queued_task_and_keeps_the_prior_db` (31 lines) — mocks, patches, or I/O
- `test_queue_cancel_refuses_a_live_runner_and_accepts_a_dead_pid` (43 lines) — mocks, patches, or I/O
- `test_queue_requeue_rereads_the_job_spec` (27 lines) — mocks, patches, or I/O
- `test_queue_requeue_refuses_a_queued_task_without_a_backup` (11 lines) — mocks, patches, or I/O
- `test_queue_requeue_refuses_a_plan` (12 lines) — mocks, patches, or I/O
- `test_queue_requeue_of_a_cancelled_job_starts_at_the_canary` (49 lines) — mocks, patches, or I/O
- `test_queue_requeue_refused_by_the_ledger_leaves_prior_run_files` (21 lines) — mocks, patches, or I/O
- `test_queue_requeue_resume_reruns_the_canary_and_keeps_other_steps` (41 lines) — mocks, patches, or I/O
- `test_queue_requeue_refuses_a_live_job_lock` (22 lines) — mocks, patches, or I/O
- `test_queue_run_keeps_polling_when_the_queue_is_empty` (26 lines) — mocks, patches, or I/O
- `test_queue_run_drain_exits_once_the_queue_is_empty` (12 lines) — mocks, patches, or I/O
- `test_queue_run_restarts_between_jobs_when_the_runner_code_changes` (16 lines) — mocks, patches, or I/O
- `test_queue_run_keeps_running_while_head_is_stable` (14 lines) — mocks, patches, or I/O
- `TestCanarySteps.test_canary_derives_the_referenced_argv_and_precedes_it` (7 lines) — mocks, patches, or I/O
- `TestCanarySteps.test_canary_round_trips_through_as_dict_without_double_applying` (5 lines) — mocks, patches, or I/O
- `TestCanarySteps.test_a_canary_step_may_not_carry_its_own_argv` (9 lines) — mocks, patches, or I/O
- `TestCanarySteps.test_an_unknown_canary_reference_is_rejected` (9 lines) — mocks, patches, or I/O
- `TestCanarySteps.test_a_canary_must_precede_the_step_it_gates` (9 lines) — mocks, patches, or I/O
- `TestCanarySteps.test_a_canary_may_not_gate_another_canary` (10 lines) — mocks, patches, or I/O
- `TestCanarySteps.test_a_step_without_argv_or_canary_still_fails_the_schema` (7 lines) — mocks, patches, or I/O
- `TestCanarySteps.test_a_pilot_canary_drops_pilot_and_keeps_the_base_campaign_id` (37 lines) — mocks, patches, or I/O
- `TestCanarySteps.test_pilot_equals_form_strips_a_baked_pilot_suffix` (14 lines) — mocks, patches, or I/O
- `TestCanarySteps.test_a_bare_pilot_flag_does_not_eat_the_next_token` (10 lines) — mocks, patches, or I/O
- `TestCanarySteps.test_a_non_pilot_campaign_canary_is_the_same_argv_plus_canary` (11 lines) — mocks, patches, or I/O
- `TestRehearseSteps.test_rehearse_derives_the_referenced_argv_and_round_trips` (16 lines) — mocks, patches, or I/O
- `TestRehearseSteps.test_failed_rehearsal_gate_blocks_the_sprint_step` (25 lines) — mocks, patches, or I/O
- `test_queue_cancel_releases_a_window_claim_held_by_a_live_runner` (15 lines) — mocks, patches, or I/O
- `test_queue_cancel_keeps_another_jobs_window_claim` (15 lines) — mocks, patches, or I/O
- `test_an_idle_queue_drops_a_window_claim_whose_job_is_gone` (20 lines) — mocks, patches, or I/O
- `test_a_stale_sweep_keeps_a_waiting_jobs_window_claim` (27 lines) — mocks, patches, or I/O
- `test_a_failed_job_notice_names_the_step_its_last_output_and_the_next_job` (44 lines) — mocks, patches, or I/O
- `test_a_canary_setup_stop_is_worded_as_a_harness_failure` (25 lines) — mocks, patches, or I/O
- `test_a_memory_trip_sends_a_runner_notice` (11 lines) — mocks, patches, or I/O
- `test_an_orphan_adoption_sends_a_runner_notice` (16 lines) — mocks, patches, or I/O
- `test_the_runner_lock_admits_exactly_one_runner` (18 lines) — mocks, patches, or I/O
- `test_queue_run_drain_announces_the_runner_and_sends_one_daily_digest` (26 lines) — mocks, patches, or I/O
- `test_queue_digest_prints_and_queues_the_digest` (40 lines) — mocks, patches, or I/O
- `test_an_empty_queue_digest_reports_idle` (8 lines) — mocks, patches, or I/O

Kept under: rule 3: values in, values out, no mocks.

Kept tests: `test_build_queue_digest_counts_jobs_rows_and_long_waits`.

### `tests/unit/test_orchestration_owui_entry.py`

Was 356 lines. Now 32. Kept 3, dropped 14.

Dropped: 14 (mocks, patches, or I/O).

- `test_disabled_module_is_inert_and_never_queues` (10 lines) — mocks, patches, or I/O
- `test_enabled_module_enqueues_through_the_queue_ledger` (30 lines) — mocks, patches, or I/O
- `test_omitted_source_dir_defaults_to_the_uploads_directory` (13 lines) — mocks, patches, or I/O
- `test_source_dir_must_be_an_existing_directory` (21 lines) — mocks, patches, or I/O
- `test_source_dir_outside_the_workspace_and_repository_is_refused` (12 lines) — mocks, patches, or I/O
- `test_absolute_parameter_path_outside_the_allowlist_is_not_queued` (17 lines) — mocks, patches, or I/O
- `test_relative_parameter_path_that_escapes_the_source_dir_is_not_queued` (17 lines) — mocks, patches, or I/O
- `test_symlink_input_that_resolves_outside_the_allowlist_is_not_queued` (19 lines) — mocks, patches, or I/O
- `test_duplicate_task_id_is_reported_not_raised` (12 lines) — mocks, patches, or I/O
- `test_missing_fields_are_refused_before_queueing` (25 lines) — mocks, patches, or I/O
- `test_unsafe_task_id_is_refused_by_the_plan_contract` (11 lines) — mocks, patches, or I/O
- `test_pipeline_mcp_serves_the_entry_point` (17 lines) — mocks, patches, or I/O
- `test_pipeline_mcp_route_enqueues_off_the_event_loop` (29 lines) — mocks, patches, or I/O
- `test_pipeline_mcp_route_is_inert_while_the_module_is_disabled` (11 lines) — mocks, patches, or I/O

Kept under: rule 3: values in, values out, no mocks.

Kept tests: `test_repository_directory_is_an_allowed_source_dir`, `test_plugin_seam_exposes_the_entry_point`, `test_pipeline_mcp_tool_schema_names_every_accepted_argument`.

### `tests/unit/test_orchestration_phase2.py`

Was 531 lines. Now 109. Kept 6, dropped 18.

Dropped: 18 (mocks, patches, or I/O).

- `test_planned_plan_rejects_phase2_contract_violations` (21 lines) — mocks, patches, or I/O
- `test_planned_plan_accepts_review_only_bite_with_reason` (8 lines) — mocks, patches, or I/O
- `test_execution_plan_caps_each_bite_budget` (13 lines) — mocks, patches, or I/O
- `test_stored_repair_template_renders_and_passes_phase2_validation` (21 lines) — mocks, patches, or I/O
- `test_stored_template_rejects_phase2_read_and_action_violation` (17 lines) — mocks, patches, or I/O
- `test_wfe_planner_suite_is_backed_by_the_validator` (23 lines) — mocks, patches, or I/O
- `test_wfe_checker_suite_rejects_plausible_wrong_outputs` (20 lines) — mocks, patches, or I/O
- `test_test_fixing_wfe_suite_uses_hidden_pytest` (24 lines) — mocks, patches, or I/O
- `test_fake_telegram_bot_decision_round_trip` (23 lines) — mocks, patches, or I/O
- `test_telegram_approval_replay_with_changed_bite_requests_new_decision` (13 lines) — mocks, patches, or I/O
- `test_telegram_approval_escapes_control_characters_in_untrusted_fields` (17 lines) — mocks, patches, or I/O
- `test_telegram_approval_same_content_in_new_run_requests_new_decision` (12 lines) — mocks, patches, or I/O
- `test_expired_telegram_approval_is_replaced_and_old_click_is_rejected` (21 lines) — mocks, patches, or I/O
- `test_expired_queued_approval_gets_replaced_after_outbox_prunes_it` (14 lines) — mocks, patches, or I/O
- `test_approval_expiring_between_enqueue_and_read_retries` (35 lines) — mocks, patches, or I/O
- `test_telegram_deny_wins_and_unknown_decision_does_not_approve` (11 lines) — mocks, patches, or I/O
- `test_telegram_approval_ttl_is_configurable` (6 lines) — mocks, patches, or I/O
- `test_telegram_store_migrates_legacy_schema_without_reusing_queued_approval` (43 lines) — mocks, patches, or I/O

Kept under: rule 3: values in, values out, no mocks.

Kept tests: `test_planner_prompt_includes_required_decomposition_rules`, `test_calibration_projects_remaining_probability_cost_and_pause`, `test_unattended_run_refuses_null_gate_c_threshold`, `test_unattended_run_refuses_disabled_gate_c_threshold`, `test_unattended_run_accepts_a_positive_gate_c_threshold`, `test_plan_rejects_control_characters_in_bite_id`.

### `tests/unit/test_orchestration_repair_quote.py`

Was 55 lines. Now 19. Kept 2, dropped 3.

Dropped: 3 (mocks, patches, or I/O).

- `test_transcript_records_server_side_tool_calls` (13 lines) — mocks, patches, or I/O
- `test_repair_note_quotes_the_last_call_per_tool` (13 lines) — mocks, patches, or I/O
- `test_no_note_without_server_side_calls` (2 lines) — mocks, patches, or I/O

Kept under: rule 3: values in, values out, no mocks.

Kept tests: `test_bite_requests_ask_for_the_execution_audit`, `test_lab_rows_match_the_backends_nested_fields`.

### `tests/unit/test_orchestration_router_fixes.py`

Was 941 lines. Now 59. Kept 2, dropped 19.

Dropped: 19 (mocks, patches, or I/O).

- `test_cli_loads_arm_and_module_config_from_repo_root` (31 lines) — mocks, patches, or I/O
- `test_cli_resolves_seat_digests_when_the_env_var_is_unset` (31 lines) — mocks, patches, or I/O
- `test_router_bite_request_reaches_engine_without_workspace_prompt_injections` (110 lines) — mocks, patches, or I/O
- `test_bite_trace_records_the_final_tools_offered_to_the_model` (15 lines) — mocks, patches, or I/O
- `test_stream_trace_records_schemas_attached_to_backend_body` (30 lines) — mocks, patches, or I/O
- `test_streaming_bite_persona_selects_pool_without_changing_seat` (53 lines) — mocks, patches, or I/O
- `test_streaming_bite_persona_accepts_workspace_slug` (31 lines) — mocks, patches, or I/O
- `test_non_streaming_bite_persona_selects_pool_without_changing_seat` (53 lines) — mocks, patches, or I/O
- `test_bite_tools_stay_scoped_across_client_tool_turns` (58 lines) — mocks, patches, or I/O
- `test_workspace_tool_loop_keeps_prompt_and_tools_across_hops` (37 lines) — mocks, patches, or I/O
- `test_workspace_tool_loop_obeys_configured_hop_limit` (20 lines) — mocks, patches, or I/O
- `test_bite_finish_is_returned_on_last_hop_but_workspace_tool_is_not_dispatched` (43 lines) — mocks, patches, or I/O
- `test_bite_allowlist_gates_real_stream_dispatch` (23 lines) — mocks, patches, or I/O
- `test_empty_workspace_intersection_keeps_only_finish_schema` (12 lines) — mocks, patches, or I/O
- `test_ordinary_last_hop_keeps_existing_client_tool_limit_behavior` (17 lines) — mocks, patches, or I/O
- `test_invalid_bite_hop_limit_fails_before_tool_setup_or_stream` (14 lines) — mocks, patches, or I/O
- `test_configured_nonpositive_global_hops_keeps_empty_loop_for_ordinary_request` (20 lines) — mocks, patches, or I/O
- `test_thinking_bite_follows_think_on_seat_and_reserves_answer_budget` (22 lines) — mocks, patches, or I/O
- `test_production_fast_and_deep_seats_remain_think_off` (5 lines) — mocks, patches, or I/O

Kept under: rule 3: values in, values out, no mocks.

Kept tests: `test_bite_sampling_follows_think_off_seat`, `test_bite_persona_inherits_tools_from_its_own_workspace_model`.

### `tests/unit/test_overview_accuracy.py`

Was 331 lines. Now 17. Kept 1, dropped 12.

Dropped: 10 (mocks, patches, or I/O); 2 (tooling script off the product path).

- `test_dashboard_is_valid_provisioning_json_with_unique_panel_ids` (6 lines) — mocks, patches, or I/O
- `test_every_query_names_a_metric_the_pipeline_emits` (5 lines) — mocks, patches, or I/O
- `test_every_queried_collector_is_recorded_somewhere` (25 lines) — mocks, patches, or I/O
- `test_counters_are_only_read_through_rate_or_increase` (11 lines) — mocks, patches, or I/O
- `test_session_totals_are_range_based` (15 lines) — mocks, patches, or I/O
- `test_overview_excludes_internal_pipeline_traffic` (16 lines) — mocks, patches, or I/O
- `test_retired_mlx_panels_and_queries_are_gone` (4 lines) — mocks, patches, or I/O
- `test_load_guard_row_summarises_and_links_to_the_full_panels` (14 lines) — mocks, patches, or I/O
- `test_colours_use_the_shared_palette` (8 lines) — mocks, patches, or I/O
- `test_one_served_turn_is_one_persona_count` (29 lines) — mocks, patches, or I/O
- `test_stream_without_a_usage_frame_still_counts_the_model_call` (26 lines) — tooling script off the product path
- `test_stream_with_a_usage_frame_counts_the_model_call_once` (22 lines) — tooling script off the product path

Kept under: rule 3: values in, values out, no mocks.

Kept tests: `test_concurrent_requests_gauge_is_summed_across_workers`.

### `tests/unit/test_parallel_seat.py`

Was 164 lines. Now 42. Kept 3, dropped 5.

Dropped: 5 (mocks, patches, or I/O).

- `test_idle_fallback_copy_is_unloaded` (6 lines) — mocks, patches, or I/O
- `test_busy_protected_and_router_copies_stay` (17 lines) — mocks, patches, or I/O
- `test_release_is_a_no_op_for_a_seat_that_is_not_parallel` (5 lines) — mocks, patches, or I/O
- `test_release_swallows_a_registry_failure` (12 lines) — mocks, patches, or I/O
- `test_single_candidate_stream_drops_the_twin_after_the_frames` (24 lines) — mocks, patches, or I/O

Kept under: rule 3: values in, values out, no mocks.

Kept tests: `test_pins_hold_until_every_admission_releases`, `test_a_yield_holds_new_seat_requests_until_release`, `test_a_yield_does_not_hold_a_different_workspace`.

### `tests/unit/test_persona_system_prompt.py`

Was 395 lines. Now 58. Kept 3, dropped 14.

Dropped: 14 (mocks, patches, or I/O).

- `test_persona_id_via_api_gets_the_prompt` (14 lines) — mocks, patches, or I/O
- `test_openwebui_duplicate_persona_prompt_is_not_doubled` (19 lines) — mocks, patches, or I/O
- `test_different_caller_system_message_follows_persona_prompt` (20 lines) — mocks, patches, or I/O
- `test_plain_workspace_id_is_unchanged` (6 lines) — mocks, patches, or I/O
- `test_prompt_template_persona_uses_the_template_file` (16 lines) — mocks, patches, or I/O
- `test_role_slash_keeps_the_engine_and_injects_the_prompt` (17 lines) — mocks, patches, or I/O
- `test_unknown_slash_is_untouched` (4 lines) — mocks, patches, or I/O
- `test_slash_without_the_separating_space_is_untouched` (6 lines) — mocks, patches, or I/O
- `test_variant_persona_slash_is_not_a_role` (14 lines) — mocks, patches, or I/O
- `test_role_slash_streams_on_the_same_engine` (44 lines) — mocks, patches, or I/O
- `test_role_slash_selects_its_variant_on_its_parent_engine` (15 lines) — mocks, patches, or I/O
- `test_role_slash_routes_the_parent_engine_to_its_variant` (24 lines) — mocks, patches, or I/O
- `test_role_prefix_is_removed_before_auto_routing` (26 lines) — mocks, patches, or I/O
- `test_behavioural_persona_slash_is_untouched` (7 lines) — mocks, patches, or I/O

Kept under: rule 3: values in, values out, no mocks.

Kept tests: `test_follow_up_keeps_the_role_prompt_and_strips_history`, `test_role_slash_strips_a_text_part`, `test_list_system_content_keeps_caller_after_the_persona_prompt`.

### `tests/unit/test_pipeline.py`

Was 2531 lines. Now 1436. Kept 76, dropped 61.

Dropped: 61 (mocks, patches, or I/O).

- `test_auto_math_alias_resolves_before_routing_and_counts_each_hit` (12 lines) — mocks, patches, or I/O
- `test_chat_workspace_aliases_resolve_to_daily_variants` (13 lines) — mocks, patches, or I/O
- `test_family_merge_aliases_resolve_to_preserved_variants` (18 lines) — mocks, patches, or I/O
- `TestBackendRegistry.test_load_config` (17 lines) — mocks, patches, or I/O
- `TestBackendRegistry.test_get_backend_for_workspace` (18 lines) — mocks, patches, or I/O
- `TestBackendRegistry.test_unhealthy_backend_not_selected` (24 lines) — mocks, patches, or I/O
- `TestBackendRegistry.test_no_healthy_backends_returns_none` (17 lines) — mocks, patches, or I/O
- `TestTimeoutConfiguration.test_request_timeout_read_from_yaml` (24 lines) — mocks, patches, or I/O
- `TestTimeoutConfiguration.test_default_timeout_when_not_in_yaml` (17 lines) — mocks, patches, or I/O
- `TestPipelineAPI.test_health_endpoint` (7 lines) — mocks, patches, or I/O
- `TestPipelineAPI.test_models_requires_auth` (3 lines) — mocks, patches, or I/O
- `TestPipelineAPI.test_models_returns_workspaces` (27 lines) — mocks, patches, or I/O
- `TestPipelineAPI.test_models_includes_ide_curated_personas` (8 lines) — mocks, patches, or I/O
- `TestPipelineAPI.test_chat_requires_auth` (3 lines) — mocks, patches, or I/O
- `TestPipelineAPI.test_chat_no_backends_returns_503_or_502` (20 lines) — mocks, patches, or I/O
- `TestPipelineAPI.test_anthropic_non_streaming_success_returns_message` (43 lines) — mocks, patches, or I/O
- `TestStrictSeatEnforcement.test_unknown_model_with_strict_seat_returns_404` (13 lines) — mocks, patches, or I/O
- `TestStrictSeatEnforcement.test_unknown_model_without_strict_seat_is_not_rejected_by_the_gate` (14 lines) — mocks, patches, or I/O
- `TestStrictSeatEnforcement.test_known_workspace_with_strict_seat_is_not_rejected` (33 lines) — mocks, patches, or I/O
- `TestBackendPin.test_pin_selects_the_named_backend_and_pops_the_field` (15 lines) — mocks, patches, or I/O
- `TestBackendPin.test_unknown_pin_is_a_400_naming_the_id_and_the_candidates` (6 lines) — mocks, patches, or I/O
- `TestBackendPin.test_pin_holds_on_the_streaming_path_too` (13 lines) — mocks, patches, or I/O
- `TestBackendPin.test_pin_that_does_not_serve_the_hint_is_a_400` (11 lines) — mocks, patches, or I/O
- `TestBackendPin.test_unpinned_request_is_unchanged_when_the_hint_does_not_resolve` (15 lines) — mocks, patches, or I/O
- `TestBackendPin.test_no_pin_leaves_the_ladder_untouched` (14 lines) — mocks, patches, or I/O
- `TestBackendPin.test_a_registered_pin_this_worker_has_not_probed_is_rechecked` (34 lines) — mocks, patches, or I/O
- `TestBackendPin.test_a_recheck_that_still_fails_keeps_the_400` (20 lines) — mocks, patches, or I/O
- `TestMetricsEndpoint.test_metrics_endpoint_returns_200` (3 lines) — mocks, patches, or I/O
- `TestMetricsEndpoint.test_metrics_contains_required_gauges` (6 lines) — mocks, patches, or I/O
- `TestMetricsEndpoint.test_metrics_workspace_count_correct` (3 lines) — mocks, patches, or I/O
- `TestComplianceWorkspace.test_compliance_workspace_json_exists_and_valid` (10 lines) — mocks, patches, or I/O
- `TestComplianceWorkspace.test_compliance_personas_exist_with_workspace_model` (14 lines) — mocks, patches, or I/O
- `TestComplianceWorkspace.test_eval_gate_reads_the_eval_module_workspaces` (14 lines) — mocks, patches, or I/O
- `TestR18ModelCompleteness.test_every_workspace_seat_resolves_in_the_catalog` (17 lines) — mocks, patches, or I/O
- `TestR18ModelCompleteness.test_key_lane_seats_are_served_by_their_routing_groups` (15 lines) — mocks, patches, or I/O
- `TestR18ModelCompleteness.test_env_example_has_pull_heavy` (4 lines) — mocks, patches, or I/O
- `TestR20NativeOllama.test_backends_yaml_uses_ollama_url_env_var` (9 lines) — mocks, patches, or I/O
- `TestR20NativeOllama.test_compose_ollama_behind_profile` (6 lines) — mocks, patches, or I/O
- `TestR20NativeOllama.test_compose_admin_email_has_default` (6 lines) — mocks, patches, or I/O
- `TestR20NativeOllama.test_mcp_ports_configurable` (5 lines) — mocks, patches, or I/O
- `TestR20NativeOllama.test_launch_sh_has_install_ollama` (4 lines) — mocks, patches, or I/O
- `TestR20NativeOllama.test_pull_models_supports_native_ollama` (12 lines) — mocks, patches, or I/O
- `TestRecordUsageMetrics.test_metrics_endpoint_contains_prometheus_output` (17 lines) — mocks, patches, or I/O
- `TestRecordUsageMetrics.test_metrics_ignore_a_multiproc_dir_when_prometheus_is_in_process` (23 lines) — mocks, patches, or I/O
- `TestSPLWorkspace.test_auto_spl_seats_a_served_model_and_keeps_its_toolset` (9 lines) — mocks, patches, or I/O
- `TestSPLWorkspace.test_spl_persona_yaml_has_required_fields` (8 lines) — mocks, patches, or I/O
- `TestSPLWorkspace.test_spl_persona_workspace_model_is_auto_spl` (8 lines) — mocks, patches, or I/O
- `TestSPLWorkspace.test_workspace_json_has_correct_id` (8 lines) — mocks, patches, or I/O
- `TestSPLWorkspace.test_workspaces_all_json_includes_spl` (9 lines) — mocks, patches, or I/O
- `TestSPLWorkspace.test_auto_spl_routing_consistent_across_files` (31 lines) — mocks, patches, or I/O
- `TestAgenticWorkspace.test_agentic_workspace_bakes_its_window_into_the_seat_tag` (34 lines) — mocks, patches, or I/O
- `TestAgenticWorkspace.test_agentic_routing_consistent_across_files` (38 lines) — mocks, patches, or I/O
- `TestCodeHygiene.test_no_duplicate_mlx_proxy_url` (12 lines) — mocks, patches, or I/O
- `TestCodeHygiene.test_claude_md_has_no_hardcoded_persona_count` (13 lines) — mocks, patches, or I/O
- `TestDispatchToolCall.test_tool_name_envelope_is_unwrapped` (32 lines) — mocks, patches, or I/O
- `TestModelSupportsToolsRealBackend.test_real_backend_tool_lookup_does_not_raise` (12 lines) — mocks, patches, or I/O
- `TestInjectOllamaOptions.test_bench_workspace_uses_5m_keep_alive` (24 lines) — mocks, patches, or I/O
- `TestThinkProfileResolution.test_thinking_profile_wins_over_flat_fields` (22 lines) — mocks, patches, or I/O
- `TestThinkProfileResolution.test_instruct_profile_selected_when_think_false` (20 lines) — mocks, patches, or I/O
- `TestThinkProfileResolution.test_no_think_set_falls_back_to_flat_fields` (18 lines) — mocks, patches, or I/O
- `TestThinkProfileResolution.test_caller_value_wins_over_think_profile` (11 lines) — mocks, patches, or I/O

Kept under: rule 1: names a live bug or dated observation; rule 3: values in, values out, no mocks.

Kept tests: `test_workspace_aliases_have_not_passed_their_removal_date`, `test_mathreasoner_presets_the_reasoning_math_variant`, `test_synthetic_math_workspace_resolves_through_variant_merger`, `test_math_alias_is_removed_from_router_labels`, `test_nemotron_persona_presets_the_chat_variant`, `TestWorkspaceModelHintUpdated.test_security_lane_keeps_its_toolset_and_gating`, `TestWorkspaceModelHintUpdated.test_coding_lane_keeps_its_sandbox_toolset`, `TestWorkspaceModelHintUpdated.test_reasoning_seats_a_thinking_model`, `TestComplianceWorkspace.test_workspace_set_matches_enabled_modules`, `TestR22CodingModelUpdates.test_coding_model_updates_r22`, `TestRecordUsageMetrics.test_record_usage_full_response`, `TestRecordUsageMetrics.test_record_usage_missing_fields`, `TestRecordUsageMetrics.test_record_usage_none_values`, `TestRecordUsageMetrics.test_record_usage_tps_calculation`, `TestSPLWorkspace.test_splunk_not_in_coding_keywords`, `TestSPLWorkspace.test_spl_query_not_in_coding_keywords`, `TestSPLWorkspace.test_spl_keywords_weighted_dict_exists`, `TestSPLWorkspace.test_spl_detect_workspace_routes_splunk_query`, `TestSPLWorkspace.test_spl_detect_workspace_routes_tstats_query`, `TestAgenticWorkspace.test_agentic_workspace_not_a_top_level_key`, `TestAgenticWorkspace.test_auto_coding_workspace_json_exists`, `TestAgenticWorkspace.test_agentic_detect_workspace_routes_agentic_query`, `TestAgenticWorkspace.test_agentic_detect_workspace_routes_swe_agent_query`, `TestAgenticWorkspace.test_agentic_does_not_route_simple_code`, `TestCodeHygiene.test_no_default_api_key_fallback`, `TestCodeHygiene.test_no_unreferenced_complete_from_backend`, `TestCodeHygiene.test_mcp_server_no_warning_suppression`, `TestCodeHygiene.test_only_dind_is_privileged`, `TestToolRegistry.test_tool_definition_to_openai`, `TestToolRegistry.test_tool_registry_list_names`, `TestToolRegistry.test_tool_registry_get_openai_tools_filters`, `TestPersonaToolResolution.test_workspace_defaults`, `TestPersonaToolResolution.test_persona_deny_strips_tool`, `TestPersonaToolResolution.test_persona_allow_overrides_workspace`, `TestPersonaToolResolution.test_persona_deny_overrides_allow`, `TestPersonaToolResolution.test_empty_workspace_no_tools`, `TestPersonaToolResolution.test_workspace_tools_helper`, `TestResolvePersonaWorkspace.test_resolves_real_persona_slug_to_its_workspace`, `TestResolvePersonaWorkspace.test_passes_through_known_workspace_id_unchanged`, `TestResolvePersonaWorkspace.test_passes_through_unknown_id_unchanged`, `TestResolveModelOverride.test_known_model_overrides_hint`, `TestResolveModelOverride.test_unknown_model_is_silent_noop`, `TestResolveModelOverride.test_no_param_is_noop`, `TestStreamingBackendHintPriority.test_hinted_backend_moves_ahead_of_group_default`, `TestStreamingBackendHintPriority.test_unknown_hint_preserves_group_priority`, `TestWorkspaceToolsConsistency.test_all_workspaces_have_tools_field`, `TestWorkspaceToolsConsistency.test_auto_agentic_has_comprehensive_tools`, `TestDispatchToolCall.test_invalid_json_arguments`, `TestDispatchToolCall.test_tool_not_in_whitelist`, `TestExplicitRequiredToolSelection.test_selects_single_explicit_tool`, `TestExplicitRequiredToolSelection.test_leaves_non_side_effect_requests_on_auto`, `TestExplicitRequiredToolSelection.test_never_selects_tool_outside_whitelist`, `TestExplicitRequiredToolSelection.test_does_not_narrow_nerc_cip_requirement_lookups`, `TestPersonasHaveToolFields.test_agentorchestrator_has_tools`, `TestPersonasHaveToolFields.test_webresearcher_has_web_tools`, `TestPersonasHaveToolFields.test_personalassistant_has_memory_tools`, `TestPersonasHaveToolFields.test_kbnavigator_has_rag_tools`, `TestModelSupportsToolsRealBackend.test_backend_has_no_mlx_metadata_field`, `TestInjectOllamaOptions.test_quality_lane_uses_10m_keep_alive`, `TestInjectOllamaOptions.test_caller_supplied_keep_alive_wins`, `TestRouterWarmupContext.test_warmup_sets_same_num_ctx_as_routing_call`, `TestRouterWarmupContext.test_auto_model_warmup_caps_num_ctx`, `TestPreferredResident.test_queued_backend_stream_sends_progress_comments`, `TestPreferredResident.test_eviction_quiet_period_uses_the_measured_load_time`, `TestPreferredResident.test_four_pipeline_workers_elect_one_preferred_resident_keeper`, `TestPreferredResident.test_the_daily_driver_loads_with_keep_alive_when_the_host_has_room`, `TestPreferredResident.test_a_busy_host_is_never_made_to_wait_for_the_warm_up`, `TestPreferredResident.test_a_model_that_does_not_fit_the_headroom_is_left_for_later`, `TestPreferredResident.test_an_unbaked_hint_caps_num_ctx`, `TestPreferredResident.test_an_omlx_preferred_resident_still_goes_through_admission`, `TestPreferredResident.test_the_target_is_the_backend_that_serves_the_hint_not_the_group_head`, `TestPreferredResident.test_the_shipped_config_resolves_the_daily_driver_to_ollama`, `TestPreferredResident.test_a_workspace_whose_hint_no_backend_serves_is_skipped`, `TestPreferredResident.test_the_keeper_protects_the_seat_and_stops_at_shutdown`, `TestPreferredResident.test_the_keeper_says_when_it_is_resident_and_logs_a_failure_once`, `TestPreferredResident.test_the_keeper_announces_residency`.

### `tests/unit/test_platform_embedding.py`

Was 223 lines. Now 117. Kept 7, dropped 6.

Dropped: 6 (mocks, patches, or I/O).

- `test_client_embeds_with_server_side_prefix` (6 lines) — mocks, patches, or I/O
- `test_client_splits_large_requests_and_keeps_order` (13 lines) — mocks, patches, or I/O
- `test_client_rejects_wrong_model_and_wrong_dim` (13 lines) — mocks, patches, or I/O
- `test_client_rejects_untrained_dim_before_network` (4 lines) — mocks, patches, or I/O
- `test_client_unreachable_maps_to_unavailable` (7 lines) — mocks, patches, or I/O
- `test_load_anchor_set_validates` (13 lines) — mocks, patches, or I/O

Kept under: rule 3: values in, values out, no mocks.

Kept tests: `test_prefixes_match_model_card`, `test_parse_task_and_role`, `test_truncate_renormalizes_and_rejects_untrained_dims`, `test_identity_version_tag_roundtrip`, `test_has_nan`, `test_anchor_classifier_picks_label_and_abstains`, `test_leakage_detects_normalized_overlap`.

### `tests/unit/test_portal_cli.py`

Was 144 lines. Now 89. Kept 3, dropped 5.

Dropped: 5 (mocks, patches, or I/O).

- `test_portal_help` (4 lines) — mocks, patches, or I/O
- `test_portal_config_show_exits_0` (3 lines) — mocks, patches, or I/O
- `test_portal_config_show_valid_json` (7 lines) — mocks, patches, or I/O
- `test_portal_config_show_workspace_count` (5 lines) — mocks, patches, or I/O
- `test_portal_config_show_mcp_fleet` (11 lines) — mocks, patches, or I/O

Kept under: rule 3: values in, values out, no mocks.

Kept tests: `test_models_pull_reads_from_config_not_hardcoded`, `test_models_pull_default_excludes_retired`, `test_models_pull_explicit_id_overrides_retired_filter`.

### `tests/unit/test_provenance_ledger.py`

Was 131 lines. Now 32. Kept 1, dropped 5.

Dropped: 5 (mocks, patches, or I/O).

- `TestProvenanceLedger.test_append_and_read` (25 lines) — mocks, patches, or I/O
- `TestProvenanceLedger.test_append_only_never_overwrites` (12 lines) — mocks, patches, or I/O
- `TestProvenanceLedger.test_read_ledger_empty_when_no_file` (6 lines) — mocks, patches, or I/O
- `TestProvenanceLedger.test_skips_malformed_lines` (14 lines) — mocks, patches, or I/O
- `TestProvenanceLedger.test_confirm_unit_appends_ledger_entry` (33 lines) — mocks, patches, or I/O

Kept under: rule 3: values in, values out, no mocks.

Kept tests: `test_scratch_ledger_fixture_keeps_the_real_ledger_byte_identical`.

### `tests/unit/test_rag.py`

Was 162 lines. Now 75. Kept 7, dropped 8.

Dropped: 8 (mocks, patches, or I/O).

- `TestReadFile.test_read_markdown` (5 lines) — mocks, patches, or I/O
- `TestReadFile.test_read_text` (4 lines) — mocks, patches, or I/O
- `TestReadFile.test_docling_pdf_success` (10 lines) — mocks, patches, or I/O
- `TestReadFile.test_docling_pptx_supported` (7 lines) — mocks, patches, or I/O
- `TestReadFile.test_docling_failure_falls_back_to_pypdf` (10 lines) — mocks, patches, or I/O
- `TestReadFile.test_docling_short_result_falls_back` (6 lines) — mocks, patches, or I/O
- `TestReadFile.test_docling_failure_falls_back_to_docx` (10 lines) — mocks, patches, or I/O
- `TestReadFile.test_unsupported_format_returns_empty` (4 lines) — mocks, patches, or I/O

Kept under: rule 3: values in, values out, no mocks.

Kept tests: `TestManifestParams.test_kb_search_has_query_type`, `TestManifestParams.test_kb_search_all_has_query_type`, `TestManifestParams.test_kb_ingest_has_fts_param`, `TestManifest.test_all_tools_present`, `TestManifest.test_kb_versions_manifest`, `TestManifest.test_kb_restore_manifest`, `TestManifest.test_endpoint_functions_exist`.

### `tests/unit/test_rag_multimodal.py`

Was 456 lines. Now 210. Kept 5, dropped 11.

Dropped: 11 (mocks, patches, or I/O).

- `test_page_transcription_uses_authenticated_pipeline_passthrough` (15 lines) — mocks, patches, or I/O
- `test_vl_embed_batch_caps_request_size` (7 lines) — mocks, patches, or I/O
- `test_vl_embed_batch_empty_is_noop` (5 lines) — mocks, patches, or I/O
- `test_write_then_read_stamp_roundtrips` (7 lines) — mocks, patches, or I/O
- `test_assert_embedding_space_rejects_same_dim_different_model` (8 lines) — mocks, patches, or I/O
- `test_vl_model_id_reads_health_and_caches` (14 lines) — mocks, patches, or I/O
- `test_c1_weak_text_promotes_the_figure` (8 lines) — mocks, patches, or I/O
- `test_c1_strong_text_keeps_text_first` (6 lines) — mocks, patches, or I/O
- `test_unified_ranks_purely_on_the_shared_reranker_score` (10 lines) — mocks, patches, or I/O
- `test_retrieval_eval_baseline_still_matches_the_declared_dependency_pins` (24 lines) — mocks, patches, or I/O
- `test_retrieval_eval_baseline_still_matches_the_configured_pipeline` (30 lines) — mocks, patches, or I/O

Kept under: rule 1: names a live bug or dated observation; rule 3: values in, values out, no mocks.

Kept tests: `test_unified_is_immune_to_text_arm_richness`, `test_uv_lock_docling_matches_the_dockerfile_mcp_pin`, `test_shipped_tau_is_the_knee_of_the_recorded_sweep`, `test_gate_endpoints_prove_both_halves_are_load_bearing`, `test_relative_gate_mode_is_not_the_default`.

### `tests/unit/test_realuse_fixture_paths.py`

Was 245 lines. Now 22. Kept 1, dropped 7.

Dropped: 6 (mocks, patches, or I/O); 1 (tooling script off the product path).

- `test_prepare_stages_the_upload_tree_and_the_bare_name` (16 lines) — mocks, patches, or I/O
- `test_sandbox_file_read_opens_the_prompt_path` (48 lines) — tooling script off the product path
- `test_read_pdf_and_read_word_resolve_inside_the_row` (24 lines) — mocks, patches, or I/O
- `test_attach_source_and_run_sql_read_the_prompt_file` (27 lines) — mocks, patches, or I/O
- `test_preflight_stages_the_selected_task_and_refuses_a_missing_one` (44 lines) — mocks, patches, or I/O
- `test_audit_names_an_unreadable_path_and_does_not_escape` (18 lines) — mocks, patches, or I/O
- `test_laguna_repo_paths_stay_in_the_checkout` (5 lines) — mocks, patches, or I/O

Kept under: rule 3: values in, values out, no mocks.

Kept tests: `test_named_paths_cover_upload_and_repo_fixtures`.

### `tests/unit/test_reasoning_effort.py`

Was 185 lines. Now 53. Kept 5, dropped 11.

Dropped: 11 (mocks, patches, or I/O).

- `test_ollama_injector_effort_overrides_predict_limit` (8 lines) — mocks, patches, or I/O
- `test_omlx_injector_effort_overrides_and_hints` (8 lines) — mocks, patches, or I/O
- `test_no_effort_falls_back_to_predict_limit` (5 lines) — mocks, patches, or I/O
- `test_omlx_injector_applies_workspace_budget_and_client_override` (8 lines) — mocks, patches, or I/O
- `test_ollama_injector_maps_client_budget_using_card_and_preserves_it_for_chain` (19 lines) — mocks, patches, or I/O
- `test_ollama_ignores_budget_without_card_mapping_and_logs` (10 lines) — mocks, patches, or I/O
- `test_streaming_request_injects_workspace_budget` (13 lines) — mocks, patches, or I/O
- `test_think_false_emits_reasoning_effort_none` (5 lines) — mocks, patches, or I/O
- `test_think_true_emits_no_reasoning_effort` (7 lines) — mocks, patches, or I/O
- `test_think_unset_emits_neither_key` (5 lines) — mocks, patches, or I/O
- `test_think_false_suppression_survives_caller_effort` (9 lines) — mocks, patches, or I/O

Kept under: rule 3: values in, values out, no mocks.

Kept tests: `test_apply_helper_maps_and_strips`, `test_apply_helper_unknown_is_noop_but_strips`, `test_apply_helper_none_turns_thinking_off`, `test_apply_helper_absent_is_noop`, `test_card_thinking_level_uses_nearest_documented_token_limit`.

### `tests/unit/test_router_placement.py`

Was 348 lines. Now 255. Kept 20, dropped 7.

Dropped: 7 (mocks, patches, or I/O).

- `TestHotSeatTracker.test_note_omlx_activity_records_on_the_module_tracker` (5 lines) — mocks, patches, or I/O
- `TestParallelSeatPrefersBatching.test_hot_other_model_does_not_steer_a_parallel_seat_to_ollama` (15 lines) — mocks, patches, or I/O
- `TestParallelSeatPrefersBatching.test_a_non_parallel_seat_keeps_the_ollama_promotion` (12 lines) — mocks, patches, or I/O
- `TestParallelSeatPrefersBatching.test_ollama_stays_first_when_omlx_cannot_serve_the_hint` (15 lines) — mocks, patches, or I/O
- `TestKnobWiring.test_registry_defaults_to_off` (3 lines) — mocks, patches, or I/O
- `TestKnobWiring.test_registry_reads_configured_window` (5 lines) — mocks, patches, or I/O
- `TestKnobWiring.test_registry_candidates_and_knob_drive_the_policy` (16 lines) — mocks, patches, or I/O

Kept under: rule 1: names a live bug or dated observation; rule 3: values in, values out, no mocks.

Kept tests: `TestEngineKey.test_normalizes_to_scheme_and_netloc`, `TestEngineKey.test_different_ports_are_different_engines`, `TestHotSeatTracker.test_hot_within_window`, `TestHotSeatTracker.test_cold_after_window`, `TestHotSeatTracker.test_window_of_zero_disables_tracking`, `TestHotSeatTracker.test_unknown_engine_is_cold`, `TestHotSeatTracker.test_latest_model_wins`, `TestProtectHotSeat.test_knob_off_keeps_order`, `TestProtectHotSeat.test_unreadable_knob_means_off`, `TestProtectHotSeat.test_single_candidate_unchanged`, `TestProtectHotSeat.test_promotes_candidate_that_spares_the_hot_engine`, `TestProtectHotSeat.test_hot_seats_own_request_unchanged`, `TestProtectHotSeat.test_after_the_window_order_is_normal`, `TestProtectHotSeat.test_pinned_model_hint_unchanged`, `TestProtectHotSeat.test_alternative_that_cannot_serve_the_hint_is_skipped`, `TestProtectHotSeat.test_no_alternative_never_denies_service`, `TestProtectHotSeat.test_hintless_workspace_uses_the_heads_first_model`, `TestProtectHotSeat.test_hintless_workspace_already_on_the_hot_model_unchanged`, `TestProtectHotSeat.test_input_order_is_not_mutated`, `TestKnobWiring.test_production_config_enables_a_bounded_window`.

### `tests/unit/test_routing.py`

Was 511 lines. Now 325. Kept 28, dropped 13.

Dropped: 13 (mocks, patches, or I/O).

- `TestRouteWithLLM.test_returns_workspace_on_high_confidence` (10 lines) — mocks, patches, or I/O
- `TestRouteWithLLM.test_returns_none_on_low_confidence` (10 lines) — mocks, patches, or I/O
- `TestRouteWithLLM.test_returns_none_on_unknown_workspace` (10 lines) — mocks, patches, or I/O
- `TestRouteWithLLM.test_returns_none_on_timeout` (11 lines) — mocks, patches, or I/O
- `TestRouteWithLLM.test_returns_none_on_network_error` (11 lines) — mocks, patches, or I/O
- `TestRouteWithLLM.test_returns_none_for_auto_workspace` (11 lines) — mocks, patches, or I/O
- `TestRouteWithLLM.test_returns_none_on_malformed_json` (12 lines) — mocks, patches, or I/O
- `TestRouteWithLLM.test_spl_routing_via_llm` (14 lines) — mocks, patches, or I/O
- `TestRouteWithLLM.test_router_excluded_label_is_rejected` (15 lines) — mocks, patches, or I/O
- `TestRouteWithLLM.test_llm_router_payload_includes_keep_alive` (16 lines) — mocks, patches, or I/O
- `TestPersonaCatalogAudit.test_no_stale_empty_tools_allow_without_comment` (22 lines) — mocks, patches, or I/O
- `TestHarmfulIntentGate.test_llm_router_harmful_posture_diverts` (16 lines) — mocks, patches, or I/O
- `TestHarmfulIntentGate.test_llm_router_standard_posture_routes_normally` (11 lines) — mocks, patches, or I/O

Kept under: rule 3: values in, values out, no mocks.

Kept tests: `TestBuildRouterPrompt.test_returns_string`, `TestBuildRouterPrompt.test_includes_user_message`, `TestBuildRouterPrompt.test_includes_workspace_ids`, `TestBuildRouterPrompt.test_excludes_router_excluded_workspaces`, `TestBuildRouterPrompt.test_capped_at_reasonable_length`, `TestRouteWithLLM.test_returns_none_when_disabled`, `TestRouteWithLLM.test_empty_messages_returns_none`, `TestRouteWithLLM.test_keyword_fallback_still_works`, `TestRouteWithLLM.test_keyword_fallback_coding`, `TestRouteWithLLM.test_keyword_layer_never_returns_router_excluded`, `TestRouteWithLLM.test_security_work_hands_off_instead_of_scattering`, `TestRouteWithLLM.test_valid_workspace_ids_covers_all_workspaces`, `TestLastUserText.test_string_content_truncation`, `TestLastUserText.test_list_content_extraction`, `TestLastUserText.test_list_content_truncation`, `TestLastUserText.test_finds_last_user_message`, `TestLastUserText.test_returns_empty_for_no_user`, `TestResolvePersonaTools.test_absent_tools_allow_uses_workspace_default`, `TestResolvePersonaTools.test_null_tools_allow_uses_workspace_default`, `TestResolvePersonaTools.test_empty_tools_allow_means_no_tools`, `TestResolvePersonaTools.test_nonempty_tools_allow_replaces_workspace_default`, `TestResolvePersonaTools.test_deny_still_subtracts`, `TestResolvePersonaTools.test_deny_works_on_workspace_default`, `TestHarmfulIntentGate.test_detect_harmful_intent_fires_on_doxxing`, `TestHarmfulIntentGate.test_detect_harmful_intent_ignores_benign`, `TestHarmfulIntentGate.test_detect_harmful_intent_ignores_authorized_security`, `TestHarmfulIntentGate.test_auto_routing_diverts_harmful_to_standard_lane`, `TestHarmfulIntentGate.test_auto_routing_leaves_non_auto_untouched`.

### `tests/unit/test_seat_fit.py`

Was 130 lines. Now 112. Kept 8, dropped 1.

Dropped: 1 (mocks, patches, or I/O).

- `test_seat_that_can_never_fit_is_flagged_against_a_fixed_budget` (16 lines) — mocks, patches, or I/O

Kept under: rule 3: values in, values out, no mocks.

Kept tests: `test_seat_over_the_live_budget_is_flagged_but_not_never_fit`, `test_protected_idle_counts_toward_the_fit_budget`, `test_omlx_seat_fits_via_its_estimated_size`, `test_resident_seat_fits_and_is_marked_resident`, `test_unserved_seat_is_reported_not_flagged_never_fit`, `test_undeclared_over_budget_is_cross_checked`, `test_production_seats_enumerates_bases_and_variants_not_bench`, `test_seat_fit_route_is_registered`.

### `tests/unit/test_seat_screen_intake_s8.py`

Was 364 lines. Now 30. Kept 1, dropped 17.

Dropped: 17 (mocks, patches, or I/O).

- `test_queue_parses_and_every_item_is_complete` (19 lines) — mocks, patches, or I/O
- `test_repo_ids_and_sizes_come_from_the_freshness_doc` (23 lines) — mocks, patches, or I/O
- `test_incumbents_are_registered_and_are_the_seated_hint` (15 lines) — mocks, patches, or I/O
- `test_maintenance_tags_are_registered_in_backends` (5 lines) — mocks, patches, or I/O
- `test_context_windows_cover_each_role` (11 lines) — mocks, patches, or I/O
- `test_plans_match_the_queue_and_expand` (23 lines) — mocks, patches, or I/O
- `test_the_fast_seats_allowlist_parses_and_covers_the_suite` (7 lines) — mocks, patches, or I/O
- `test_unauthorized_production_modes_are_declared_as_prerequisites` (11 lines) — mocks, patches, or I/O
- `test_pass_bar_matches_the_decision_module` (7 lines) — mocks, patches, or I/O
- `test_every_suite_carries_the_screen_and_confirm_floor` (6 lines) — mocks, patches, or I/O
- `test_disk_plan_arithmetic` (17 lines) — mocks, patches, or I/O
- `test_conditional_item_waits_for_a_queued_predecessor` (10 lines) — mocks, patches, or I/O
- `test_sha_check_current_and_stale` (10 lines) — mocks, patches, or I/O
- `test_sha_check_falls_back_to_the_manifest_digest_without_a_model_layer` (7 lines) — mocks, patches, or I/O
- `test_sha_check_unknown_when_not_installed_or_upstream_is_down` (8 lines) — mocks, patches, or I/O
- `test_sha_check_item_reports_upstream_and_the_worst_tag` (15 lines) — mocks, patches, or I/O
- `test_sha_check_cli_reads_the_real_queue_offline` (7 lines) — mocks, patches, or I/O

Kept under: rule 3: values in, values out, no mocks.

Kept tests: `test_both_fast_seat_plans_expand_to_rows`.

### `tests/unit/test_spine_drift.py`

Was 346 lines. Now 183. Kept 19, dropped 8.

Dropped: 6 (mocks, patches, or I/O); 2 (tooling script off the product path).

- `test_workspace_names_rejects_an_unexpected_config_shape` (11 lines) — mocks, patches, or I/O
- `test_bs_check_hard_fails_a_deliberately_wrong_declared_number` (25 lines) — tooling script off the product path
- `test_bs_check_passes_when_declared_number_is_correct` (23 lines) — tooling script off the product path
- `test_fact_unit_derivation_does_not_write_canonical_store` (14 lines) — mocks, patches, or I/O
- `test_probe_names_a_stat_that_takes_the_rate_of_a_lifetime_counter` (12 lines) — mocks, patches, or I/O
- `test_probe_exempts_a_timeseries_because_movement_is_what_a_rate_is_for` (12 lines) — mocks, patches, or I/O
- `test_probe_accepts_a_stat_reading_the_windowed_gauge` (12 lines) — mocks, patches, or I/O
- `test_probe_reports_unparseable_dashboard_rather_than_passing` (5 lines) — mocks, patches, or I/O

Kept under: rule 3: values in, values out, no mocks.

Kept tests: `test_claims_survive_frontmatter_round_trip`, `test_unit_without_claims_round_trips_to_empty_list`, `test_every_probe_returns_a_value_on_this_repo`, `test_workspace_probes_are_internally_consistent`, `test_unknown_probe_raises_rather_than_passing_quietly`, `test_workspace_names_returns_ids_not_display_labels`, `test_pattern_claim_holds_when_body_carries_live_value`, `test_pattern_claim_catches_a_body_that_fell_behind_code`, `test_pattern_without_value_placeholder_is_itself_a_violation`, `test_equals_claim_on_structural_invariant`, `test_contains_claim`, `test_unknown_probe_in_frontmatter_is_a_violation_not_a_pass`, `test_claim_with_no_operator_is_a_violation`, `test_served_model_ids_are_not_treated_as_filesystem_paths`, `test_broken_path_refs_are_reported_as_doc_and_path`, `test_pin_axis_is_fully_removed`, `test_census_is_read_only_and_self_consistent`, `test_undeclared_numeric_census_skips_units_that_declare_a_claim`, `test_live_dashboard_states_no_total_as_a_rate`.

### `tests/unit/test_stream_fallback.py`

Was 680 lines. Now 72. Kept 4, dropped 11.

Dropped: 11 (mocks, patches, or I/O).

- `TestStreamFallbackPlainContent.test_omlx_usage_frame_passes_engine_timings_to_usage_metrics` (49 lines) — mocks, patches, or I/O
- `TestStreamFallbackPlainContent.test_plain_content_output` (29 lines) — mocks, patches, or I/O
- `TestStreamFallbackPlainContent.test_plain_content_no_ollama_native_translation` (29 lines) — mocks, patches, or I/O
- `TestStreamFallbackReasoningSeparation.test_reasoning_only_is_not_answer_content` (49 lines) — mocks, patches, or I/O
- `TestStreamFallbackReasoningSeparation.test_reasoning_not_promoted_when_content_present` (38 lines) — mocks, patches, or I/O
- `TestStreamFallbackToolCalls.test_tool_calls_delta_passed_through` (49 lines) — mocks, patches, or I/O
- `TestStreamFallbackToolCalls.test_finish_reason_tool_calls_passed_through` (36 lines) — mocks, patches, or I/O
- `TestStreamFallbackErrorHandling.test_non_200_yields_well_formed_error_frames` (24 lines) — mocks, patches, or I/O
- `TestStreamFallbackDoneTermination.test_done_terminator_preserved` (27 lines) — mocks, patches, or I/O
- `TestStreamContractRegression.test_stream_survives_real_aiter_lines_str_contract` (69 lines) — mocks, patches, or I/O
- `TestStreamContractRegression.test_reasoning_separation_with_str_contract` (49 lines) — mocks, patches, or I/O

Kept under: rule 3: values in, values out, no mocks.

Kept tests: `test_indexed_tool_calls_numbers_each_call`, `test_json_to_sse_fallback_indexes_parallel_tool_calls`, `test_json_to_sse_fallback_emits_requested_usage`, `test_json_to_sse_fallback_zero_fills_a_completion_without_usage`.

### `tests/unit/test_telegram_jarvis_control.py`

Was 584 lines. Now 50. Kept 4, dropped 38.

Dropped: 38 (mocks, patches, or I/O).

- `test_jarvis_help_is_answered_without_a_row` (8 lines) — mocks, patches, or I/O
- `test_empty_allowlist_refuses_control_but_chat_still_works` (9 lines) — mocks, patches, or I/O
- `test_unknown_user_is_refused_without_a_row` (7 lines) — mocks, patches, or I/O
- `test_callback_refuses_unknown_user` (9 lines) — mocks, patches, or I/O
- `test_the_shipped_config_declares_the_control_flag` (5 lines) — mocks, patches, or I/O
- `test_flag_off_bot_answers_not_enabled_and_never_opens_the_store` (8 lines) — mocks, patches, or I/O
- `test_flag_off_runner_never_builds_a_poller` (8 lines) — mocks, patches, or I/O
- `test_non_destructive_verb_queues_a_row` (8 lines) — mocks, patches, or I/O
- `test_read_only_verbs_are_answered_at_once_without_the_runner` (12 lines) — mocks, patches, or I/O
- `test_destructive_verb_waits_for_confirm_then_queues` (14 lines) — mocks, patches, or I/O
- `test_abort_refuses_a_pending_request` (9 lines) — mocks, patches, or I/O
- `test_confirm_callback_moves_the_row_to_queued` (8 lines) — mocks, patches, or I/O
- `test_ask_callback_on_destructive_notice_swaps_in_confirm_buttons` (9 lines) — mocks, patches, or I/O
- `test_closed_or_expired_callback_is_rejected` (9 lines) — mocks, patches, or I/O
- `test_expired_queued_requests_never_run` (12 lines) — mocks, patches, or I/O
- `test_expired_pending_requests_cannot_be_confirmed` (9 lines) — mocks, patches, or I/O
- `test_runner_executes_via_shared_helpers_and_writes_result_and_notice` (18 lines) — mocks, patches, or I/O
- `test_runner_marks_unknown_verb_refused` (6 lines) — mocks, patches, or I/O
- `test_runner_turns_a_helper_fault_into_a_failed_result` (7 lines) — mocks, patches, or I/O
- `test_pause_and_resume_round_trip` (5 lines) — mocks, patches, or I/O
- `test_a_control_poll_fault_does_not_kill_the_runner` (13 lines) — mocks, patches, or I/O
- `test_status_reports_the_queue_ledger` (9 lines) — mocks, patches, or I/O
- `test_queue_status_lists_the_last_ten_control_requests` (14 lines) — mocks, patches, or I/O
- `test_held_escalation_notice_creates_merge_keep_diff_buttons` (11 lines) — mocks, patches, or I/O
- `test_blocked_job_notice_creates_requeue_escalate_cancel_buttons` (8 lines) — mocks, patches, or I/O
- `test_quota_notice_creates_a_resume_button` (4 lines) — mocks, patches, or I/O
- `test_outbox_attaches_the_control_keyboard_to_a_notice` (21 lines) — mocks, patches, or I/O
- `test_notice_buttons_pass_user_rows_by_are_not_shown` (3 lines) — mocks, patches, or I/O
- `test_callback_data_fits_the_64_byte_limit` (8 lines) — mocks, patches, or I/O
- `test_merge_refuses_a_held_portal_path_with_the_reason` (6 lines) — mocks, patches, or I/O
- `test_merge_refuses_when_no_held_lane_exists` (3 lines) — mocks, patches, or I/O
- `test_keep_held_records_the_decision_and_clears_the_held_list` (8 lines) — mocks, patches, or I/O
- `test_held_lists_a_job_whose_latest_decision_is_held` (8 lines) — mocks, patches, or I/O
- `test_diff_reports_a_held_lane_diffstat` (7 lines) — mocks, patches, or I/O
- `test_canary_reports_one_line_setup_model_counts` (20 lines) — mocks, patches, or I/O
- `test_canary_reports_missing_pieces` (8 lines) — mocks, patches, or I/O
- `test_build_app_registers_jarvis_routing` (14 lines) — mocks, patches, or I/O
- `test_disabled_orchestration_registers_no_jv_callbacks` (8 lines) — mocks, patches, or I/O

Kept under: rule 3: values in, values out, no mocks.

Kept tests: `test_parse_is_deterministic`, `test_every_control_verb_has_a_host_executor`, `test_plain_jarvis_text_is_a_control_request_not_chat`, `test_long_notices_are_split_under_the_telegram_cap`.

### `tests/unit/test_thinking_channels.py`

Was 456 lines. Now 201. Kept 13, dropped 6.

Dropped: 6 (mocks, patches, or I/O).

- `test_guarded_stream_keeps_reasoning_separate_and_classifies_empty_terminal` (37 lines) — mocks, patches, or I/O
- `test_non_streaming_reasoning_only_is_an_explicit_incomplete_answer` (23 lines) — mocks, patches, or I/O
- `test_streamed_inline_think_never_closed_is_reasoning_only` (31 lines) — mocks, patches, or I/O
- `test_streamed_inline_think_split_across_chunks_releases_the_answer` (26 lines) — mocks, patches, or I/O
- `test_inline_think_turn_grades_reasoning_only_in_the_trace` (53 lines) — mocks, patches, or I/O
- `test_tool_loop_inline_think_never_closed_is_reasoning_only` (25 lines) — mocks, patches, or I/O

Kept under: rule 3: values in, values out, no mocks.

Kept tests: `test_inline_think_filter_is_chunk_boundary_safe_and_byte_preserving`, `test_unterminated_protocol_block_is_discarded_at_terminal_boundary`, `test_incomplete_tag_prefix_and_legitimate_answer_whitespace_are_preserved`, `test_non_streaming_normalization_never_promotes_reasoning`, `test_non_streaming_normalization_filters_inline_blocks_but_preserves_literal_markup`, `test_effective_thinking_flag_reads_engine_specific_request_fields`, `test_json_to_sse_fallback_does_not_promote_thoughts`, `test_inline_think_is_reasoning_at_every_chunk_split`, `test_quoted_literal_think_markup_stays_content_and_is_not_reasoning`, `test_non_streaming_inline_think_becomes_reasoning_content`, `test_non_streaming_inline_think_is_hidden_when_thinking_is_off`, `test_non_streaming_inline_think_does_not_swallow_the_answer`, `test_json_to_sse_fallback_carries_inline_think_as_reasoning`.

### `tests/unit/test_timing_instrument.py`

Was 663 lines. Now 244. Kept 9, dropped 5.

Dropped: 5 (mocks, patches, or I/O).

- `test_stream_measurement_fills_missing_engine_timings` (34 lines) — mocks, patches, or I/O
- `test_pipeline_nonstream_body_carries_measured_timings_without_changing_content` (23 lines) — mocks, patches, or I/O
- `test_pipeline_nonstream_passes_engine_timings_to_usage_metrics` (32 lines) — mocks, patches, or I/O
- `test_stream_tool_loop_accumulates_each_round_and_records_timing_metrics` (95 lines) — mocks, patches, or I/O
- `test_nonstream_tool_loop_accumulates_each_round_and_records_timing_metrics` (90 lines) — mocks, patches, or I/O

Kept under: rule 3: values in, values out, no mocks.

Kept tests: `test_ollama_native_completion_surfaces_engine_timings_without_changing_message`, `test_ollama_native_stream_has_engine_timings_on_terminal_frames`, `test_engine_shapes_and_measured_fallback_normalize_to_same_fields`, `test_engine_total_with_legacy_delta_split_is_repaired_by_character_evidence`, `test_final_timing_frame_is_inserted_before_done_and_keeps_content`, `test_trace_record_exposes_timing_metadata`, `test_portal_timings_appends_terminal_usage_when_requested_and_missing`, `test_portal_timings_keeps_engine_usage_and_skips_the_zero_fill`, `test_portal_timings_without_a_usage_request_adds_no_usage_frame`.

### `tests/unit/test_tool_backoff.py`

Was 443 lines. Now 97. Kept 4, dropped 12.

Dropped: 12 (mocks, patches, or I/O).

- `test_success_resets_backoff` (25 lines) — mocks, patches, or I/O
- `test_single_failure_schedules_30s` (23 lines) — mocks, patches, or I/O
- `test_three_failures_schedules_5m` (24 lines) — mocks, patches, or I/O
- `test_allowed_after_backoff_window` (23 lines) — mocks, patches, or I/O
- `test_caller_fault_is_error_does_not_trip_backoff` (29 lines) — mocks, patches, or I/O
- `test_validation_errors_then_a_good_call_still_runs` (20 lines) — mocks, patches, or I/O
- `test_mcp_crash_text_still_trips_backoff` (15 lines) — mocks, patches, or I/O
- `test_three_connection_failures_still_open_backoff` (23 lines) — mocks, patches, or I/O
- `test_http_4xx_does_not_trip_backoff` (13 lines) — mocks, patches, or I/O
- `test_execute_bash_command_alias_reaches_the_server_as_code` (23 lines) — mocks, patches, or I/O
- `test_command_alias_is_execute_bash_only` (23 lines) — mocks, patches, or I/O
- `test_execute_bash_against_the_live_manifest_schema_reaches_the_server_as_code` (19 lines) — mocks, patches, or I/O

Kept under: rule 3: values in, values out, no mocks.

Kept tests: `test_backoff_schedule`, `test_blocked_inside_backoff_window`, `test_get_openai_tools_excludes_in_backoff`, `test_crash_line_is_infra_and_validation_text_is_not`.

### `tests/unit/test_tool_loop_byte_budget.py`

Was 475 lines. Now 56. Kept 2, dropped 10.

Dropped: 10 (mocks, patches, or I/O).

- `test_streaming_budget_truncates_results_and_keeps_tools_available` (24 lines) — mocks, patches, or I/O
- `test_streaming_document_under_budget_passes_through_whole` (12 lines) — mocks, patches, or I/O
- `test_streaming_no_tool_and_small_tool_turns_match_an_unbudgeted_request` (22 lines) — mocks, patches, or I/O
- `test_streaming_oversized_result_is_truncated_and_tools_remain_available` (17 lines) — mocks, patches, or I/O
- `test_streaming_budget_cap_finalizer_keeps_the_system_prompt` (25 lines) — mocks, patches, or I/O
- `test_nonstreaming_oversized_result_is_truncated_and_tools_remain_available` (22 lines) — mocks, patches, or I/O
- `test_nonstreaming_hop_limit_finalizer_keeps_the_system_prompt` (18 lines) — mocks, patches, or I/O
- `test_nonstreaming_budget_truncates_results_and_keeps_tools_available` (25 lines) — mocks, patches, or I/O
- `test_nonstreaming_document_under_budget_passes_through_whole` (16 lines) — mocks, patches, or I/O
- `test_nonstreaming_no_tool_and_small_tool_turns_match_an_unbudgeted_request` (23 lines) — mocks, patches, or I/O

Kept under: rule 3: values in, values out, no mocks.

Kept tests: `test_budget_is_half_the_window_at_two_bytes_per_token`, `test_budget_truncates_new_tool_results_to_remaining_bytes`.

### `tests/unit/test_tps_metrics.py`

Was 644 lines. Now 597. Kept 17, dropped 1.

Dropped: 1 (mocks, patches, or I/O).

- `TestOverviewDashboard.test_tps_panels_are_windowed_ratios` (41 lines) — mocks, patches, or I/O

Kept under: rule 3: values in, values out, no mocks.

Kept tests: `TestRecordTimingSeries.test_engine_eval_duration_is_decode_time`, `TestRecordTimingSeries.test_measured_kwargs_do_not_use_wall_clock`, `TestRecordTimingSeries.test_answer_rate_requires_at_least_32_answer_tokens`, `TestRecordTimingSeries.test_omlx_stream_usage_records_engine_sourced_timings`, `TestRecordTimingSeries.test_ollama_stream_eval_duration_stays_engine_decode_time`, `TestRecordTimingSeries.test_tool_loop_model_metrics_exclude_tool_dispatch_time`, `TestRecordTimingSeries.test_nonstream_omlx_reply_uses_engine_usage_timings`, `TestRecordTimingSeries.test_answer_tokens_default_to_completion_minus_reasoning`, `TestRecordTimingSeries.test_absent_decode_time_is_unmeasured_not_wall_clock`, `TestRecordTimingSeries.test_no_tokens_does_not_count_as_unmeasured`, `TestRecordTimingSeries.test_new_timings_are_keyword_only`, `TestRecordTimingSeries.test_bench_workspace_skips_digest_accumulators`, `TestRecordTimingSeries.test_non_bench_updates_digest_accumulators`, `TestRecordTimingSeries.test_exposition_names_the_series_and_marks_the_histogram_deprecated`, `TestDigestMath.test_weighted_rate_and_median`, `TestDigestMath.test_sample_delta_uses_the_appended_tail`, `TestDigestMath.test_top_models_rank_by_answer_tokens`.

### `tests/unit/test_trace_sections.py`

Was 1009 lines. Now 655. Kept 52, dropped 17.

Dropped: 17 (mocks, patches, or I/O).

- `test_host_url_rewrites_container_hostnames_for_the_host` (14 lines) — mocks, patches, or I/O
- `test_program_paths_and_missing_paths` (6 lines) — mocks, patches, or I/O
- `test_installed_hop_fails_a_missing_program_and_warns_on_stale_args` (19 lines) — mocks, patches, or I/O
- `test_stale_powermetrics_hint_uses_the_passwordless_dispatcher` (14 lines) — mocks, patches, or I/O
- `test_unsubstituted_omlx_hint_names_its_installer` (10 lines) — mocks, patches, or I/O
- `test_label_commit_that_contains_a_merged_branch_commit_is_current` (18 lines) — mocks, patches, or I/O
- `test_label_commit_reads_the_pickaxe_result` (8 lines) — mocks, patches, or I/O
- `test_config_hop_lists_baked_files_that_differ_from_the_repo` (12 lines) — mocks, patches, or I/O
- `test_config_hop_skips_bind_mounted_files` (9 lines) — mocks, patches, or I/O
- `test_disabled_seat_skips_a_disabled_module_variant` (15 lines) — mocks, patches, or I/O
- `test_run_skips_disabled_seats_without_streaming` (46 lines) — mocks, patches, or I/O
- `test_discover_pins_reads_module_literals_and_skips_prompts` (7 lines) — mocks, patches, or I/O
- `test_load_backends_expands_urls_and_keeps_aliases` (14 lines) — mocks, patches, or I/O
- `test_load_lab_env_exports_the_splunk_endpoint` (10 lines) — mocks, patches, or I/O
- `test_hunt_query_hop_runs_the_engine_with_the_lab_search` (19 lines) — mocks, patches, or I/O
- `test_labelled_event_hop_falls_back_to_the_corpus_window` (13 lines) — mocks, patches, or I/O
- `test_labelled_event_hop_fails_with_every_empty_window` (5 lines) — mocks, patches, or I/O

Kept under: rule 1: names a live bug or dated observation; rule 3: values in, values out, no mocks.

Kept tests: `test_plist_helpers_default_and_read_declared_values`, `test_schedule_separates_resident_from_periodic_jobs`, `test_install_dir_sends_root_daemons_to_the_system_domain`, `test_parse_job_state_reads_runs_pid_and_last_exit`, `test_parse_priority_takes_the_first_number`, `test_priority_hop_fails_engines_at_background_priority`, `test_priority_hop_allows_a_scheduled_helper_above_background`, `test_installed_hop_reports_a_missing_plist`, `test_installed_hop_compares_process_type_and_env_keys`, `test_installed_hop_warns_on_unsubstituted_placeholders`, `test_parse_arguments_reads_the_loaded_job_block`, `test_installed_hop_skips_argument_drift_for_templated_plists`, `test_process_hop_requires_a_resident_job_to_have_a_pid`, `test_process_hop_passes_a_periodic_job_on_its_last_run`, `test_parse_iso_handles_docker_nanoseconds`, `test_same_image_matches_short_and_full_ids`, `test_image_freshness_compares_the_container_with_its_own_reference`, `test_open_webui_rollback_tag_does_not_make_the_container_stale`, `test_copied_paths_ignores_multistage_sources`, `test_parse_container_reads_the_compose_labels`, `test_image_freshness_fails_when_a_newer_build_exists`, `test_start_hop_fails_when_the_container_predates_its_image`, `test_revision_hop_warns_before_the_label_existed_and_fails_after`, `test_parse_hash_lines_accepts_either_column_order`, `test_production_seats_covers_variants_and_excludes_bench`, `test_parse_sse_ignores_noise_and_the_terminator`, `test_summarize_turn_derives_ttft_rate_and_usage`, `test_summarize_turn_counts_reasoning_apart_from_answer_content`, `test_summarize_turn_treats_inline_think_as_reasoning_not_answer`, `test_seat_hop_tells_a_reasoning_only_turn_from_an_empty_one`, `test_seat_hop_fails_a_refusal_and_an_empty_stream`, `test_seat_hop_fails_a_turn_without_usage`, `test_seat_hop_passes_a_healthy_turn_and_warns_on_substitution`, `test_classify_splits_backends_from_seats_and_models`, `test_alias_hop_verdict_follows_the_engine_model_list`, `test_backend_hops_fails_once_when_its_engine_did_not_answer`, `test_model_ids_reads_openai_and_status_shapes`, `test_parse_omlx_status_reports_ceiling_and_loaded`, `test_parse_ollama_ps_sizes_residents`, `test_parse_seat_fit_keeps_the_verdict_lists`, `test_seat_fit_verdict_fails_never_fit_and_warns_over_budget`, `test_seat_fit_basis_names_the_budget_the_verdicts_used`, `test_parse_nvidia_smi_and_nice_rows`, `test_parse_server_info_reads_version_and_name`, `test_lab_section_adapts_contributed_hops`, `test_lab_section_fails_when_no_module_contributes_it`, `test_lab_section_fails_when_the_module_raises_or_returns_junk`, `test_section_selection_accepts_keys_numbers_and_prefixes`, `test_hops_render_without_a_trailing_space`, `test_seat_hop_accepts_the_resolved_router_lane`, `test_seat_hop_still_warns_when_the_resolved_lane_leaves_its_seat`, `test_seat_hop_keeps_the_seat_hint_for_an_unknown_resolved_lane`.

### `tests/unit/test_transport_pipeline_dialect.py`

Was 499 lines. Now 316. Kept 20, dropped 10.

Dropped: 10 (mocks, patches, or I/O).

- `test_native_rollback_uses_guarded_passthrough_and_auth` (13 lines) — mocks, patches, or I/O
- `test_native_applied_context_reads_ps_with_auth` (14 lines) — mocks, patches, or I/O
- `test_post_translates_http_status_error` (11 lines) — mocks, patches, or I/O
- `test_post_translates_stall_to_urlerror` (7 lines) — mocks, patches, or I/O
- `test_post_synthesizes_body_and_carries_trace` (30 lines) — mocks, patches, or I/O
- `test_seat_window_pipeline_reads_workspace_context_limit` (4 lines) — mocks, patches, or I/O
- `test_seat_window_native_is_zero_because_the_request_can_raise_it` (6 lines) — mocks, patches, or I/O
- `test_trace_lifts_applied_options_when_recorded` (26 lines) — mocks, patches, or I/O
- `test_trace_records_applied_options_absence_as_none` (7 lines) — mocks, patches, or I/O
- `test_a_workspace_without_predict_limit_still_gets_an_output_cap` (14 lines) — mocks, patches, or I/O

Kept under: rule 1: names a live bug or dated observation; rule 3: values in, values out, no mocks.

Kept tests: `test_workspace_passthrough_for_known_workspace`, `test_workspace_mapping_for_registered_hint`, `test_unknown_tag_passes_through`, `test_context_limit_declared_and_absent`, `test_pipeline_dialect_omits_workspace_owned_output_settings`, `test_resolve_dialect_defaults_to_pipeline`, `test_resolve_dialect_explicit_still_works`, `test_build_resolves_tag_to_workspace_on_the_wire`, `test_build_keeps_client_tools_and_marks_them_client_only`, `test_build_without_tools_refuses_workspace_tools`, `test_build_drops_direct_call_fields`, `test_build_maps_json_format`, `test_classify_400_reads_the_prefill_guard_as_capacity`, `test_a_capacity_refusal_is_named_and_never_poisons_the_think_cache`, `test_chat_receipt_stamps_pipeline_attribution`, `test_build_refuses_unmapped_tag`, `test_build_accepts_variant_workspace_ids`, `test_chat_receipt_carries_applied_options`, `test_note_applied_options_records_post_injection_body`, `test_applied_options_read_ollama_seat_sampling_from_options`.

### `tests/unit/test_turn_trace.py`

Was 228 lines. Now 23. Kept 1, dropped 12.

Dropped: 12 (mocks, patches, or I/O).

- `test_record_round_trips` (6 lines) — mocks, patches, or I/O
- `test_env_and_value_integer_helpers_keep_their_semantics` (8 lines) — mocks, patches, or I/O
- `test_credentials_are_redacted` (10 lines) — mocks, patches, or I/O
- `test_finalize_overwrites_so_the_later_writer_wins` (8 lines) — mocks, patches, or I/O
- `test_ring_is_bounded` (6 lines) — mocks, patches, or I/O
- `test_correlation_id_cannot_escape_the_directory` (3 lines) — mocks, patches, or I/O
- `test_disabled_is_inert` (11 lines) — mocks, patches, or I/O
- `test_bodies_are_opt_in_and_nested_credentials_are_redacted` (30 lines) — mocks, patches, or I/O
- `test_tool_loop_hops_keep_their_bodies_within_the_cap` (37 lines) — mocks, patches, or I/O
- `test_oversized_bodies_are_dropped_with_a_marker_not_silently` (16 lines) — mocks, patches, or I/O
- `test_oversized_records_remain_bounded_valid_json` (18 lines) — mocks, patches, or I/O
- `test_helpers_never_raise_without_a_current_trace` (4 lines) — mocks, patches, or I/O

Kept under: rule 3: values in, values out, no mocks.

Kept tests: `test_redaction_spares_token_counts_but_not_credentials`.

### `tests/unit/test_uat_security.py`

Was 356 lines. Now 130. Kept 9, dropped 12.

Dropped: 12 (mocks, patches, or I/O).

- `test_request_success_parses_route_and_content` (20 lines) — mocks, patches, or I/O
- `test_request_disabled_workspace_returns_detail_as_error` (14 lines) — mocks, patches, or I/O
- `test_request_transport_error_is_caught` (11 lines) — mocks, patches, or I/O
- `test_request_timeout_reports_its_budget` (11 lines) — mocks, patches, or I/O
- `test_run_shots_respects_only_filter` (9 lines) — mocks, patches, or I/O
- `test_run_design_checks_auto_security_isolation_pass_and_fail` (14 lines) — mocks, patches, or I/O
- `test_run_design_checks_flags_auto_security_leak` (14 lines) — mocks, patches, or I/O
- `test_run_design_checks_alias_mismatch_fails` (28 lines) — mocks, patches, or I/O
- `test_main_dry_run_lists_ids_without_network` (7 lines) — mocks, patches, or I/O
- `test_main_dry_run_only_filters_to_one_id` (8 lines) — mocks, patches, or I/O
- `test_main_refuses_busy_host_and_writes_start_end_snapshots` (25 lines) — mocks, patches, or I/O
- `test_wait_for_quiet_flag_reaches_the_shared_helper` (29 lines) — mocks, patches, or I/O

Kept under: rule 3: values in, values out, no mocks.

Kept tests: `test_security_ids_finds_base_and_variants_with_enabled_state`, `test_security_ids_sorted_base_then_variants`, `test_security_aliases_only_includes_security_targets`, `test_split_id_splits_variant`, `test_chain_shot_gets_the_declared_chain_budget`, `test_scrape_counter_sums_matching_labels`, `test_scrape_counter_no_match_is_zero`, `test_shot_ok_for_enabled_requires_200_and_nonempty`, `test_shot_ok_for_disabled_requires_404_with_disabled_message`.

### `tests/unit/test_variant_module_gate.py`

Was 226 lines. Now 22. Kept 1, dropped 9.

Dropped: 9 (mocks, patches, or I/O).

- `test_each_toggle_flips_only_its_variant` (21 lines) — mocks, patches, or I/O
- `test_disabled_variants_are_not_served_on_the_fixture` (7 lines) — mocks, patches, or I/O
- `test_enabling_image_brings_only_that_variant_back` (9 lines) — mocks, patches, or I/O
- `test_variant_without_module_inherits_and_does_not_add_tools` (24 lines) — mocks, patches, or I/O
- `test_variant_tools_stay_on_variant_without_base_tools` (17 lines) — mocks, patches, or I/O
- `test_disabled_variant_request_is_module_disabled_404` (16 lines) — mocks, patches, or I/O
- `test_resolve_does_not_cache_a_disabled_variant` (20 lines) — mocks, patches, or I/O
- `test_router_offer_drops_only_the_disabled_variant` (10 lines) — mocks, patches, or I/O
- `test_production_catalog_keeps_base_workspaces_and_math` (20 lines) — mocks, patches, or I/O

Kept under: rule 3: values in, values out, no mocks.

Kept tests: `test_unknown_variant_module_is_rejected`.

### `tests/unit/test_web_search_fallback.py`

Was 158 lines. Now 55. Kept 5, dropped 8.

Dropped: 8 (mocks, patches, or I/O).

- `TestSearchFallbackOrder.test_brave_primary_uses_brave` (4 lines) — mocks, patches, or I/O
- `TestSearchFallbackOrder.test_falls_back_when_primary_weak` (4 lines) — mocks, patches, or I/O
- `TestSearchFallbackOrder.test_no_brave_key_stays_on_searxng` (4 lines) — mocks, patches, or I/O
- `TestSearchFallbackOrder.test_primary_good_result_wins_without_fallback` (19 lines) — mocks, patches, or I/O
- `TestSearchCache.test_repeat_query_served_from_cache` (17 lines) — mocks, patches, or I/O
- `TestSearchCache.test_empty_result_not_cached` (14 lines) — mocks, patches, or I/O
- `TestSearchCache.test_cache_ttl_expiry` (5 lines) — mocks, patches, or I/O
- `TestSearchCache.test_cache_bound_evicts_oldest` (7 lines) — mocks, patches, or I/O

Kept under: rule 3: values in, values out, no mocks.

Kept tests: `TestResultsAreWeak.test_empty_is_weak`, `TestResultsAreWeak.test_all_root_urls_is_weak`, `TestResultsAreWeak.test_no_snippets_is_weak`, `TestResultsAreWeak.test_wikipedia_and_root_dominated_is_weak`, `TestResultsAreWeak.test_substantive_results_not_weak`.

### `tests/unit/test_weekly_rebuild.py`

Was 117 lines. Now 49. Kept 1, dropped 9.

Dropped: 9 (tooling script off the product path).

- `test_failed_build_never_takes_the_stack_down` (5 lines) — tooling script off the product path
- `test_failed_pull_never_takes_the_stack_down` (5 lines) — tooling script off the product path
- `test_happy_path_builds_fresh_then_down_then_up` (10 lines) — tooling script off the product path
- `test_defers_while_a_sweep_runs` (6 lines) — tooling script off the product path
- `test_unhealthy_up_keeps_previous_images_for_rollback` (5 lines) — tooling script off the product path
- `test_healthy_up_prunes_dangling_images` (5 lines) — tooling script off the product path
- `test_bulk_pull_never_includes_open_webui` (6 lines) — tooling script off the product path
- `test_pull_services_failure_never_falls_back_to_pulling_everything` (6 lines) — tooling script off the product path
- `test_rolled_back_open_webui_update_is_reported_as_a_problem` (5 lines) — tooling script off the product path

Kept under: rule 1: names a live bug or dated observation.

Kept tests: `test_build_carries_the_provenance_args`.

### `tests/unit/test_wfe_production_smoke_cleanup.py`

Was 137 lines. Now 13. Kept 1, dropped 6.

Dropped: 6 (mocks, patches, or I/O).

- `test_cleanup_forgets_echoed_id_and_still_sweeps` (15 lines) — mocks, patches, or I/O
- `test_cleanup_sweep_forgets_note_when_id_was_not_echoed` (11 lines) — mocks, patches, or I/O
- `test_cleanup_sweep_warns_when_recall_fails` (9 lines) — mocks, patches, or I/O
- `test_cleanup_sweep_never_forgets_an_unrelated_memory` (7 lines) — mocks, patches, or I/O
- `test_cleanup_prints_warning_if_forget_fails` (6 lines) — mocks, patches, or I/O
- `test_cleanup_warns_when_successful_remember_has_no_returned_id` (6 lines) — mocks, patches, or I/O

Kept under: rule 3: values in, values out, no mocks.

Kept tests: `test_remember_result_id_is_captured_from_answer_text`.

### `tests/unit/test_wfe_production_smoke_kb.py`

Was 87 lines. Now 14. Kept 1, dropped 4.

Dropped: 4 (mocks, patches, or I/O).

- `test_kb_row_accepted_when_model_lists_the_empty_store` (15 lines) — mocks, patches, or I/O
- `test_kb_row_still_flagged_when_kb_list_failed` (13 lines) — mocks, patches, or I/O
- `test_kb_row_still_flagged_when_no_kb_tool_was_called` (7 lines) — mocks, patches, or I/O
- `test_kb_row_still_flagged_when_answer_is_a_refusal` (14 lines) — mocks, patches, or I/O

Kept under: rule 3: values in, values out, no mocks.

Kept tests: `test_kb_search_cases_expect_the_empty_production_kb`.

### `tests/unit/test_wfe_surface_audit.py`

Was 173 lines. Now 57. Kept 5, dropped 2.

Dropped: 2 (mocks, patches, or I/O).

- `test_class3_pipeline_rejects_unknown_key_before_the_call` (67 lines) — mocks, patches, or I/O
- `test_class3_direct_reports_server_behaviour` (35 lines) — mocks, patches, or I/O

Kept under: rule 3: values in, values out, no mocks.

Kept tests: `test_signature_rows_flag_undefined_extra_and_missing_required`, `test_shape_rows_flag_arrays_and_objects_with_no_keys`, `test_filtering_dispatcher_pattern_matches_the_whisper_shape`, `test_no_dispatcher_silently_filters_unknown_arguments`, `test_manifests_pass_the_integrity_classes_the_audit_closed`.

### `tests/unit/test_wiki_core.py`

Was 595 lines. Now 183. Kept 13, dropped 22.

Dropped: 22 (mocks, patches, or I/O).

- `TestWikiIntegrity.test_rejects_truncated_canonical_body` (15 lines) — mocks, patches, or I/O
- `TestWikiIntegrity.test_intent_seeder_preserves_sections_over_legacy_cap` (15 lines) — mocks, patches, or I/O
- `TestWikiIntegrity.test_resolves_exact_glob_and_bare_filename_sources` (10 lines) — mocks, patches, or I/O
- `TestWikiIntegrity.test_missing_local_source_is_an_issue` (13 lines) — mocks, patches, or I/O
- `TestWikiIntegrity.test_existing_but_untracked_source_is_an_issue` (16 lines) — mocks, patches, or I/O
- `TestWikiIntegrity.test_tracked_directory_source_accepts_tracked_descendant` (18 lines) — mocks, patches, or I/O
- `TestWikiIntegrity.test_code_seeder_excludes_gitignored_python` (15 lines) — mocks, patches, or I/O
- `TestWikiIntegrity.test_ephemeral_source_is_an_issue` (12 lines) — mocks, patches, or I/O
- `TestWikiIntegrity.test_authored_doc_unit_is_not_stale_just_because_head_advanced` (10 lines) — mocks, patches, or I/O
- `TestWikiIntegrity.test_changed_derived_body_marks_generated_unit_stale` (24 lines) — mocks, patches, or I/O
- `TestStore.test_save_and_load` (17 lines) — mocks, patches, or I/O
- `TestStore.test_load_nonexistent` (6 lines) — mocks, patches, or I/O
- `TestStore.test_load_all` (17 lines) — mocks, patches, or I/O
- `TestStore.test_list_ids` (15 lines) — mocks, patches, or I/O
- `TestStore.test_delete_unit` (16 lines) — mocks, patches, or I/O
- `TestCoreImportClean.test_core_no_portal_imports` (17 lines) — mocks, patches, or I/O
- `TestMCPTools.test_wiki_search` (20 lines) — mocks, patches, or I/O
- `TestMCPTools.test_wiki_get_unit` (20 lines) — mocks, patches, or I/O
- `TestMCPTools.test_fact_unit_is_live_and_searchable_without_storage` (35 lines) — mocks, patches, or I/O
- `TestMCPTools.test_wiki_get_unit_not_found` (9 lines) — mocks, patches, or I/O
- `TestMCPTools.test_wiki_explain` (21 lines) — mocks, patches, or I/O
- `TestMCPTools.test_wiki_explain_no_results` (13 lines) — mocks, patches, or I/O

Kept under: rule 3: values in, values out, no mocks.

Kept tests: `TestSourceRef.test_to_dict`, `TestSourceRef.test_from_dict`, `TestSourceRef.test_optional_fields`, `TestWikiIntegrity.test_non_file_identifiers_are_not_local_paths`, `TestKnowledgeUnit.test_create_with_sources`, `TestKnowledgeUnit.test_reject_no_sources`, `TestKnowledgeUnit.test_reject_invalid_kind`, `TestKnowledgeUnit.test_valid_kinds`, `TestKnowledgeUnit.test_reject_invalid_confidence`, `TestKnowledgeUnit.test_valid_confidences`, `TestKnowledgeUnit.test_to_frontmatter`, `TestKnowledgeUnit.test_to_markdown_roundtrip`, `TestKnowledgeUnit.test_content_hash_deterministic`.

### `tests/unit/test_wiki_search_ranking.py`

Was 73 lines. Now 18. Kept 1, dropped 2.

Dropped: 2 (mocks, patches, or I/O).

- `test_all_baseline_queries_return_expected_top_hit` (14 lines) — mocks, patches, or I/O
- `test_fixture_is_fresh_against_store` (10 lines) — mocks, patches, or I/O

Kept under: rule 3: values in, values out, no mocks.

Kept tests: `test_workspace_routing_demotes_test_section_unit`.

### `tests/unit/test_workspace.py`

Was 171 lines. Now 29. Kept 4, dropped 15.

Dropped: 15 (mocks, patches, or I/O).

- `test_get_workspace_root_uses_workspace_dir` (2 lines) — mocks, patches, or I/O
- `test_get_workspace_root_falls_back_to_ai_output_dir` (6 lines) — mocks, patches, or I/O
- `test_get_uploads_dir_creates_directory` (4 lines) — mocks, patches, or I/O
- `test_get_generated_dir_validates_category` (3 lines) — mocks, patches, or I/O
- `test_get_generated_dir_creates_each_category` (5 lines) — mocks, patches, or I/O
- `test_resolve_upload_path_direct_match` (7 lines) — mocks, patches, or I/O
- `test_resolve_upload_path_prefix_match` (7 lines) — mocks, patches, or I/O
- `test_resolve_upload_path_returns_none_for_missing` (3 lines) — mocks, patches, or I/O
- `test_resolve_upload_path_picks_most_recent_on_ambiguity` (14 lines) — mocks, patches, or I/O
- `test_resolve_upload_path_rejects_absolute_path_escape` (12 lines) — mocks, patches, or I/O
- `test_resolve_upload_path_rejects_traversal` (4 lines) — mocks, patches, or I/O
- `test_assert_public_http_url_accepts_public_host` (3 lines) — mocks, patches, or I/O
- `test_assert_public_http_url_rejects_localhost` (4 lines) — mocks, patches, or I/O
- `test_assert_public_http_url_rejects_hostname_resolving_to_private_range` (6 lines) — mocks, patches, or I/O
- `test_assert_public_http_url_rejects_unresolvable_host` (9 lines) — mocks, patches, or I/O

Kept under: rule 3: values in, values out, no mocks.

Kept tests: `test_assert_public_http_url_rejects_loopback_ip_literal`, `test_assert_public_http_url_rejects_link_local_metadata_ip_literal`, `test_assert_public_http_url_rejects_private_range_ip_literal`, `test_assert_public_http_url_rejects_non_http_scheme`.

## Kept whole

| path | lines at decision | keep rule |
| --- | ---: | --- |
| `tests/unit/router/test_correlation.py` | 32 | rule 3: correlation id formatter |
| `tests/unit/test_mawa_join.py` | 103 | rule 3: join logic on values |
| `tests/unit/test_mawa_join_guard.py` | 69 | rule 3: join refuses ground-truth columns |
| `tests/unit/test_mawa_join_reader.py` | 82 | rule 3: apache/syslog parser |
| `tests/unit/test_mawa_join_scorer.py` | 297 | rule 3: scorer math |
| `tests/unit/test_mcp_fleet_single_source.py` | 377 | rule 2: portal.yaml mcp_fleet is the single port/id source |
| `tests/unit/test_mesh_printability.py` | 64 | rule 3: printability math |
| `tests/unit/test_mlx_speech_asr_gate.py` | 77 | rule 1: uncached ASR model 500'd under HF_HUB_OFFLINE, live 2026-11-07 |
| `tests/unit/test_mlx_transcribe_openai_stt.py` | 150 | rule 1: absent Parakeet turned :8924 STT into a bare 500 |
| `tests/unit/test_model_catalog_parity.py` | 202 | rule 2: backends.yaml model ids match the catalog contract |
| `tests/unit/test_model_cleanup_audit.py` | 72 | rule 2: live seating config rejects REMOVED_CLOSED identities |
| `tests/unit/test_no_answer.py` | 613 | rule 1: a 502 on an unloadable pinned model left the chat with no turn |
| `tests/unit/test_ollama_native.py` | 632 | rule 1: Ollama /v1 dropped sampling, measured 2026-09-25 |
| `tests/unit/test_orchestration_detection_discipline.py` | 202 | rule 3: detection checkers take values and return pass/fail |
| `tests/unit/test_owui_eg2_prefixes.py` | 32 | rule 2: Open WebUI embedding prefixes match the EG2 contract |
| `tests/unit/test_owui_preset_drift.py` | 83 | rule 2: seeded persona/workspace preset drift |
| `tests/unit/test_part4_production_defects.py` | 173 | rule 1: production defects P-3, N-22, N-23, N-28, N-12 |
| `tests/unit/test_pending_verdicts_evidence.py` | 40 | rule 1: retracted-verdict bug fixed bca0955f |
| `tests/unit/test_pipeline_hardening.py` | 2482 | rule 1: each test pins a defect reproduced live 2026-09-25 |
| `tests/unit/test_pipeline_image_personas.py` | 124 | rule 2: image ships every persona prompt file (2026-10-22 miss) |
| `tests/unit/test_portal_mitre_mcp.py` | 199 | rule 3: MITRE/SPL lookup on bundled data, no mocks |
| `tests/unit/test_portal_yaml_consistency.py` | 33 | rule 2: portal.yaml workspace/model cross-reference |
| `tests/unit/test_powermetrics_daemon.py` | 173 | rule 1: module docstring names the live bug these tests pin |
| `tests/unit/test_prompt_signal_overlap.py` | 57 | rule 2: workspace and persona prompt signals |
| `tests/unit/test_prompt_truncation_detect.py` | 45 | rule 3: context-window truncation detector |
| `tests/unit/test_recall_scorer.py` | 125 | rule 3: recall scorer |
| `tests/unit/test_request_no_tools.py` | 101 | rule 1: tools:[] was ignored and swallowed a JSON answer, live 2026-11-12 |
| `tests/unit/test_require_tool_before_answer.py` | 328 | rule 1: auto-research answered with no query, measured on Qwen3.6 |
| `tests/unit/test_required_tool_choice_retry.py` | 478 | rule 1: tool_choice=required was ignored, measured live 2026-11-05 |
| `tests/unit/test_retrieval_payload.py` | 81 | rule 3: retrieval payload builder |
| `tests/unit/test_review_event_time.py` | 162 | rule 1: live windows:security run-c966ec5292b3 stamped one instant |
| `tests/unit/test_scad_emitter.py` | 328 | rule 3: SCAD emitter, values in, text out |
| `tests/unit/test_seat_primary_matches_production.py` | 57 | rule 2: seat_primary matches BackendRegistry on backends.yaml |
| `tests/unit/test_security_corpus_contract.py` | 21 | rule 2: config/security_corpus.yaml source/answer-key contract |
| `tests/unit/test_seed_facts.py` | 51 | rule 3: model-group union |
| `tests/unit/test_self_index_validator_spawn.py` | 67 | rule 1: X and AA spawned validate_system and always got None |
| `tests/unit/test_siem_collect_normalize.py` | 323 | rule 1: live 2026-11-07 events lost their own clock |
| `tests/unit/test_spine_gates.py` | 41 | rule 2: routing, wiki, and spine gates against the loaded repo |
| `tests/unit/test_stream_inband_error.py` | 332 | rule 1: ollama#18563 in-band error left the stream without finish_reason |
| `tests/unit/test_stream_pipeline_errors.py` | 887 | rule 1: bare error frame killed the session, seen live 2026-10-21 |
| `tests/unit/test_streaming_client.py` | 56 | rule 3: stream aggregation of values |
| `tests/unit/test_text_tool_call_salvage.py` | 367 | rule 1: P5-OMLX-QWEN3CODER-TOOLTEXT-001 text tool calls |
| `tests/unit/test_tool_dispatch_order.py` | 41 | rule 1: batched tool calls raced, operator 2026-10-18 |
| `tests/unit/test_tool_repeat_guard.py` | 390 | rule 1: compliance seat repeated one call 19 times, 2026-10-16 |
| `tests/unit/test_trace_report.py` | 73 | rule 3: trace report formatter, no I/O |
| `tests/unit/test_uat_dispatch_url.py` | 87 | rule 1: 31 via_dispatcher cases never ran on the host |
| `tests/unit/test_uat_grading.py` | 275 | rule 1: inverted-critical grading bug and the word-boundary mismatch; mock and tmp_path tests removed afterward (see corrections) |
| `tests/unit/test_uat_metrics_url.py` | 76 | rule 1: metrics URL kept the compose hostname and reported 0 tool calls |
| `tests/unit/test_update_workspace_tools_dead.py` | 28 | rule 3: dead-tool predicate |
| `tests/unit/test_validation_ae_launcher.py` | 65 | rule 1: fresh worktree false-failed the gitignored launcher check |
| `tests/unit/test_validation_fleet_fallback.py` | 316 | rule 2: backends.yaml oMLX+Ollama family fallback |
| `tests/unit/test_validation_mtp_intake.py` | 143 | rule 2: backends.yaml MTP-twin seat contract |
| `tests/unit/test_validation_test_hygiene.py` | 149 | rule 1: a coding_task path made main red outside one worktree, 2026-10-22 |
| `tests/unit/test_wfe_exec_audit.py` | 125 | rule 1: tool_grounded treated an unresolved id as grounded, live 2026-10-15 |
| `tests/unit/test_wfe_garble_probe.py` | 56 | rule 1: U+200B and mangled tool names on the granite-8b shadow |
| `tests/unit/test_wiki_quality.py` | 191 | rule 3: values in, values out, no mocks |

## Open

- `tests/unit/test_powermetrics_daemon.py` stayed whole because the module docstring names the buffer-leak regression. It also contains launchd and subprocess tests that are not that bug.
- `tests/unit/test_seat_fit.py` stayed because its bodies do not contain the dirty-token list and the file imports `portal`. Several tests build a fake engine via `tests.unit.test_load_guard` (`Engines`, `guard`). `test_load_guard.py` is outside this lane (`test_l`). `test_production_seats_enumerates_bases_and_variants_not_bench` also reads seating config.
- `scripts/rotate_logs.py` and `scripts/speed_bench.py` are now unwired. Raising `unwired_scripts` in `config/complexity_budget.yaml` was not done.
- Historical reports still name deleted tests (`reports/retrieval/SUBSTRATE_MIGRATION_V1.md`, `reports/host_memory_safety/W4.md`, `reports/cad/TASK_CAD_ARM_REDEVELOP_V1_REPORT.md`, `docs/archive/KNOWN_LIMITATIONS_RESOLVED_20261019.md`). `broken_path_refs` did not flag them. `scripts/validation/rag_runtime.py` still names `tests/unit/test_retrieval_contextualize_gate.py` in a docstring.
