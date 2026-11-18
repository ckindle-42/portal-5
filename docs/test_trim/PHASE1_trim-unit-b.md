# Phase 1 test trim — trim-unit-b

Scope: `tests/unit/test_[m-z]*.py` plus `tests/unit/**` subdirectories (189 files, the `router/` package). Twenty test functions removed from six files. No whole file removed. The `router/` tests stayed.

| path | category | proof |
| --- | --- | --- |
| `tests/unit/test_portal_yaml_consistency.py::test_no_unused_non_retired_models` | skipped-dead | Unconditional `@pytest.mark.skip` ("pending operator review — some non-retired entries intentionally un-wired"). Nothing in the tree turns the skip off. |
| `tests/unit/test_pipeline.py::TestR17bModelExpansion` (class, both methods) | mock-only + duplicate | `test_new_llm_models_in_backends_yaml` loops `required = []` (every model name is a comment), so the assert never checks a product value. `test_documents_seat_is_served_by_its_lane` calls the same `_seat_is_lane_served(WORKSPACES["auto-documents"], "auto-documents", backends)` as `TestR18ModelCompleteness.test_key_lane_seats_are_served_by_their_routing_groups`. |
| `tests/unit/test_pipeline.py::test_launch_sh_pull_models_has_r22_updates` | duplicate | Asserts `portal.platform.inference.cli models pull` is in `launch.sh`. Kept `TestR20NativeOllama.test_pull_models_supports_native_ollama`, which asserts `exec python3 -m portal.platform.inference.cli models pull`. |
| `tests/unit/test_pipeline.py::test_auto_spl_in_workspaces_dict` | duplicate | `auto-spl in WORKSPACES` is also asserted by kept `test_auto_spl_routing_consistent_across_files`. |
| `tests/unit/test_pipeline.py::test_auto_spl_in_backends_yaml` | duplicate | `auto-spl in workspace_routing` is also asserted by kept `test_auto_spl_routing_consistent_across_files`. |
| `tests/unit/test_pipeline.py::test_spl_workspace_set_matches_enabled_modules` | duplicate | Same body as kept `TestComplianceWorkspace.test_workspace_set_matches_enabled_modules`. |
| `tests/unit/test_pipeline.py::test_spl_persona_yaml_exists` | duplicate | Only `Path("config/personas/splunksplgineer.yaml").exists()`. Kept `test_spl_persona_yaml_has_required_fields` and `test_spl_persona_workspace_model_is_auto_spl` read that file. |
| `tests/unit/test_pipeline.py::test_workspace_json_exists` | duplicate | Only `workspace_auto_spl.json` exists. Kept `test_workspace_json_has_correct_id` reads it. |
| `tests/unit/test_pipeline.py::test_spl_does_not_route_generic_coding` | duplicate | `_detect_workspace` lowercases the message. "Write a Python function to parse JSON logs" is the same input as kept `tests/unit/test_routing.py::test_keyword_fallback_coding`, which asserts `== "auto-coding"`. |
| `tests/unit/test_pipeline.py::test_agentic_workspace_has_model_hint` | duplicate | Resolves `auto-coding::heavy` and asserts the hint is non-empty. Kept `test_agentic_workspace_bakes_its_window_into_the_seat_tag` does that, then checks the window. |
| `tests/unit/test_pipeline.py::test_compliance_workspace_exists_in_router` | duplicate | `auto-compliance in WORKSPACES`. Kept `test_workspace_set_matches_enabled_modules` requires every enabled non-eval workspace; `config/portal.yaml` has `compliance.enabled: true`. |
| `tests/unit/test_pipeline.py::test_compliance_workspace_in_backends_yaml` | duplicate | `auto-compliance in workspace_routing`. Kept `test_auto_spl_routing_consistent_across_files` asserts routing keys equal every `portal.yaml` workspace id. |
| `tests/unit/test_triage_layer2.py::test_propose_keyboard_interrupt_aborts` | mock-only | Stubs `diagnose`, suppresses `SystemExit`, and never reads `state` or the return value. |
| `tests/unit/test_triage_layer2.py::test_auto_rejects_low_confidence` | mock-only | Same shape: stubbed `diagnose`, `SystemExit` and `EOFError` suppressed, no assertion. |
| `tests/unit/test_triage_layer2.py::test_auto_rejects_disallowed_action` | mock-only | Same shape as the low-confidence test. Kept `test_auto_executes_allowlisted_above_floor`, which does assert `execute_action` and the return value. |
| `tests/unit/test_native_mcp_service.py::test_a_launch_outside_a_git_checkout_still_starts_and_says_unknown` | duplicate | Body is the same call as kept `test_data_mcp_root_follows_ai_output_dir`: `_run_data_mcp(tmp_path, "AI_OUTPUT_DIR=/srv/ai\n") == "DATA_MCP_ROOT=/srv/ai"`. |
| `tests/unit/test_uat_security.py::test_request_forwards_variant_as_query_param` | mock-only | Passes `variant="redteam"` and asserts the mock `post` was called with `params == {"variant": "redteam"}`. |
| `tests/unit/test_semaphore.py::test_chat_endpoint_requires_auth` | duplicate | Unauthenticated `POST /v1/chat/completions` expects 401. Kept `tests/unit/test_pipeline.py::TestPipelineAPI.test_chat_requires_auth`. |
| `tests/unit/test_semaphore.py::test_semaphore_max_concurrent_configurable` | duplicate | Same assertion as kept `test_semaphore_limit_in_env`: `router_pipe._MAX_CONCURRENT >= 1`. |

## Counts

| measure | before | after |
| --- | --- | --- |
| Scope Python lines (`find tests/unit -maxdepth 1 -name 'test_[m-z]*.py'` plus `tests/unit` below depth 1) | 55737 | 55472 |
| Lines removed (git diff) | | 265 across 6 files, 0 files deleted |
| `uv run pytest tests/unit/ tests/wfe -q -n auto --cov=portal` | 7480 passed, 128 skipped, 309.73s | 7461 passed, 127 skipped, 318.88s |
| `portal/` line coverage | 49385/96848 = 50.992277% (`/tmp/trim-unit-b_cov_before.json`) | 49380/96848 = 50.987114% (`/tmp/trim-unit-b_cov_after.json`) |
| Coverage delta | | −0.005163 pp. No `portal/` file fell from >0 covered lines to 0. |
| `uv run ruff check .` and `uv run ruff format --check .` | | clean |
| `python3 scripts/complexity_report.py --gate` | | GATE OK (see the run after this file was added) |
