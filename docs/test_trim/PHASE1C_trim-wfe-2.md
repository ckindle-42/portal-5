# Phase 1c test trim — role trim-wfe-2

The offline suite is a fast merge gate. Kept tests meet one of the current rules: they name a live defect, validate a configuration or contract used by the running WFE/product path, or exercise pure value-in/value-out logic. Test-only harness and workload assets remain in place.

## Scope counts

| Scope | Before | After | Removed |
|---|---:|---:|---:|
| Tracked files under tests/wfe | 227 files / 43,503 lines | 223 files / 41,887 lines | 4 files / 1,616 lines |
| Python files under tests/wfe | 117 files / 39,810 lines | 113 files / 38,194 lines | 4 files / 1,616 lines |
| Tracked Python tests under tests/wfe/tests | 20 files / 5,754 lines | 16 files / 4,138 lines | 4 files / 1,616 lines |

The 16 remaining Python files include the package initializer. Four complete pytest modules were removed; six pytest modules were trimmed. No WFE runner, grader, campaign, plan, suite, workload, or fixture outside the removed test bodies was deleted.

## Deleted files

| Path | Lines | Why it fails the keep rule |
|---|---:|---|
| tests/wfe/tests/test_wfe_realuse_tier.py | 146 | Synthetic plan and campaign-row tests use temporary files and patched campaign internals to exercise evaluator tooling; no named live defect or product configuration contract. |
| tests/wfe/tests/test_wfe_stop_rules.py | 33 | Exercises the campaign stop counter through mutable module state; it is neither pure value logic nor a named live defect. |
| tests/wfe/tests/test_wfe_sweep_plan.py | 210 | Generator tests build temporary queues/plans and read the checked-in generator output; they test off-product tooling through file I/O. |
| tests/wfe/tests/test_wfe_tiers.py | 163 | Synthetic tier/append campaign flows load temporary plan and suite files; no named live defect or product configuration contract. |

## Deleted tests in split files

### tests/wfe/tests/test_wfe_checkers.py

Deleted the generic temporary-file checker cases and the hidden-pytest offline flow. The retained false-pass cases name live WFE observations or exercise pure checker logic.

| Original lines | Test | Why it fails the keep rule |
|---|---|---|
| 83–86 | TestFileCheckersAreSandboxOnly.test_file_exists_true_when_written | Generic temporary-file behavior without a named live defect or loaded configuration contract. |
| 88–91 | TestFileCheckersAreSandboxOnly.test_empty_file_is_not_a_pass | Generic temporary-file behavior without a named live defect or loaded configuration contract. |
| 93–95 | TestFileCheckersAreSandboxOnly.test_escape_attempt_is_refused | Generic temporary-file behavior without a named live defect or loaded configuration contract. |
| 97–107 | TestFileCheckersAreSandboxOnly.test_file_contains | Generic temporary-file behavior without a named live defect or loaded configuration contract. |
| 1122–1131 | TestRewardHacking.test_model_authored_trivial_tests_do_not_score | Offline code-generation and hidden-pytest grading flow. |
| 1133–1158 | TestRewardHacking.test_correct_implementation_passes_the_hidden_suite | Offline code-generation and hidden-pytest grading flow. |
| 1160–1165 | TestRewardHacking.test_missing_implementation_is_a_fail_not_an_error | Offline hidden-pytest grading flow. |
| 1167–1172 | TestRewardHacking.test_rewriting_the_graded_fixture_fails | Offline code-generation and hidden-pytest grading flow. |
| 1174–1178 | TestRewardHacking.test_deleting_the_graded_fixture_fails | Offline code-generation and hidden-pytest grading flow. |

### tests/wfe/tests/test_wfe_contracts.py

Deleted temp-campaign/report/matrix flows, generic repository file-operation tests, the mocked tags API audit, and one synthetic matrix expansion.

| Original lines | Test | Why it fails the keep rule |
|---|---|---|
| 85–90 | TestToolArgumentContract.test_dispatch_executes_with_v1_shaped_arguments | Offline tool dispatch/file-write flow over a temporary sandbox. |
| 305–310 | TestMatrixExpansion.test_expansion_covers_every_arm_suite_task | Synthetic campaign matrix expansion from temporary plans. |
| 312–318 | TestMatrixExpansion.test_repeats_multiply_rows_with_distinct_ids | Synthetic campaign matrix expansion from temporary plans. |
| 320–325 | TestMatrixExpansion.test_targeting_narrows_the_matrix | Synthetic campaign matrix expansion from temporary plans. |
| 327–335 | TestMatrixExpansion.test_ordering_is_model_major | Synthetic campaign matrix expansion from temporary plans. |
| 337–339 | TestMatrixExpansion.test_home_flag_set_correctly | Synthetic campaign matrix expansion from temporary plans. |
| 341–349 | TestMatrixExpansion.test_missing_suite_is_recorded_not_silently_dropped | Synthetic campaign matrix expansion from temporary plans. |
| 351–359 | TestMatrixExpansion.test_live_plan_expands | Offline expansion flow; live plan/suite structure is checked by test_wfe_plan_suites.py and test_wfe_next_screens_slice.py. |
| 410–420 | TestReportCompilation.test_instrument_failures_are_excluded_from_rates | Offline report compilation over fabricated temporary campaign records. |
| 422–425 | TestReportCompilation.test_overlapping_intervals_are_not_ranked | Offline report compilation over fabricated temporary campaign records. |
| 427–433 | TestReportCompilation.test_clear_separation_is_reported | Offline report compilation over fabricated temporary campaign records. |
| 435–442 | TestReportCompilation.test_mixed_fingerprints_are_refused | Offline report compilation over fabricated temporary campaign records. |
| 444–451 | TestReportCompilation.test_markdown_renders | Offline report rendering over fabricated temporary campaign records. |
| 515–549 | TestWfeCurtailment.test_a_ten_task_confirm_plan_runs_and_reports_below_floor | Offline campaign-control flow over fabricated rows. |
| 551–583 | TestWfeCurtailment.test_better_curtailment_is_the_fitness_verdict_and_skips_do_not_reduce_floor | Offline campaign-control flow over fabricated rows. |
| 585–615 | TestWfeCurtailment.test_partial_gradeable_screen_rows_remain_future_tasks | Offline campaign-control flow over fabricated rows. |
| 617–623 | TestWfeCurtailment.test_incomplete_incumbent_bypasses_curtailment | Offline campaign-control flow over fabricated rows. |
| 625–638 | TestWfeCurtailment.test_incumbent_with_a_missing_repeat_bypasses_curtailment | Offline campaign-control flow over fabricated rows. |
| 640–672 | TestWfeCurtailment.test_no_curtail_resumes_skipped_rows | Offline campaign-control flow over fabricated rows. |
| 674–681 | TestWfeCurtailment.test_incumbent_arms_are_selected_first | Offline campaign-control flow over fabricated rows. |
| 883–886 | TestSandboxRepoAccess.test_file_read_falls_back_to_a_real_repo_file | Generic repository file I/O test for off-product sandbox tooling. |
| 888–891 | TestSandboxRepoAccess.test_sandbox_file_wins_over_a_repo_file_of_the_same_name | Generic repository file I/O test for off-product sandbox tooling. |
| 893–894 | TestSandboxRepoAccess.test_missing_everywhere_is_a_clean_error | Temporary/repository file lookup flow without a named live defect. |
| 896–900 | TestSandboxRepoAccess.test_repo_search_dot_path_reaches_the_repo | Generic repository search I/O test for off-product sandbox tooling. |
| 902–903 | TestSandboxRepoAccess.test_repo_search_empty_path_reaches_the_repo | Generic repository search I/O test for off-product sandbox tooling. |
| 905–908 | TestSandboxRepoAccess.test_repo_search_still_finds_sandbox_content | Mixed repository and temporary-file I/O test. |
| 910–911 | TestSandboxRepoAccess.test_repo_search_requires_a_pattern | Generic repository search I/O test for off-product sandbox tooling. |
| 913–915 | TestSandboxRepoAccess.test_writes_still_cannot_escape | Generic file-write test; the named sandbox escape regression remains in test_wfe_checkers.py. |
| 917–921 | TestSandboxRepoAccess.test_file_list_of_empty_sandbox_is_empty_not_a_repo_dump | Generic repository file-list I/O test for off-product sandbox tooling. |
| 923–926 | TestSandboxRepoAccess.test_file_list_of_a_real_repo_subdir_still_works | Generic repository file-list I/O test for off-product sandbox tooling. |
| 1261–1265 | TestInstrumentHealthSection.test_a_clean_campaign_reports_zero_excluded | Offline report/ledger flow over temporary campaign files. |
| 1267–1272 | TestInstrumentHealthSection.test_instrument_rows_are_marked_and_counted | Offline report/ledger flow over temporary campaign files. |
| 1274–1276 | TestInstrumentHealthSection.test_the_census_total_matches_every_recorded_run | Offline report/ledger flow over temporary campaign files. |
| 1326–1332 | TestV2ReviewInstrumentFixes.test_repo_search_scoped_to_a_file_searches_that_file | Repository search I/O test for off-product sandbox tooling. |
| 1334–1337 | TestV2ReviewInstrumentFixes.test_repo_search_on_a_missing_path_is_an_error_not_a_widening | Repository search I/O test for off-product sandbox tooling. |
| 1339–1341 | TestV2ReviewInstrumentFixes.test_repo_search_scoped_to_a_repo_file_reaches_it | Repository search I/O test for off-product sandbox tooling. |
| 1343–1345 | TestV2ReviewInstrumentFixes.test_repo_search_scoped_to_a_repo_dir_keeps_the_deny_list | Repository search I/O test for off-product sandbox tooling. |
| 1396–1424 | TestSelectionBiasFixes.test_challengers_run_at_their_card_sampling | Synthetic plan expansion through temporary YAML and campaign tooling. |
| 1816–1823 | TestTagsAudit.test_the_committed_table_refuses_the_incident_setup | Monkeypatches /api/tags and /api/show responses to exercise an offline tag-audit flow. |
| 1825–1833 | TestTagsAudit.test_the_committed_renderer_table_is_fully_cited | Checks an off-product audit table; no running-system config contract or named live defect. |

### tests/wfe/tests/test_wfe_judge.py

Deleted judge CLI configuration and environment tests; the local endpoint classifier and verdict parser remain as pure value tests.

| Original lines | Test | Why it fails the keep rule |
|---|---|---|
| 46–48 | TestEndpointPolicy.test_an_explicit_override_allows_a_remote_endpoint | Environment override test for off-product judge tooling. |
| 50–62 | TestEndpointPolicy.test_the_committed_yaml_is_the_default_and_env_overrides | Reads evaluator-only judge config and changes environment state. |
| 64–68 | TestEndpointPolicy.test_no_model_configured_anywhere_is_an_error | Patches evaluator config path and environment for off-product judge tooling. |

### tests/wfe/tests/test_wfe_judge_compare.py

Deleted JSON directory loader tests and the temporary campaign/CLI comparison flow; pure kappa math remains.

| Original lines | Test | Why it fails the keep rule |
|---|---|---|
| 13–20 | TestLoad.test_loads_all_json_files_in_a_profile | Temporary-file I/O test for off-product judgment loader. |
| 22–23 | TestLoad.test_missing_profile_returns_empty | Filesystem behavior test for off-product judgment loader. |
| 25–29 | TestLoad.test_broken_json_is_skipped | Temporary-file I/O test for off-product judgment loader. |
| 50–116 | test_council_profiles_report_checker_agreement | Fabricates campaign/judgment files and captures CLI output. |
| 119–126 | test_local_profile_reads_the_flat_directory_and_not_cloud | Temporary-file I/O test for off-product judgment loader. |

### tests/wfe/tests/test_wfe_office_contains.py

Deleted generic generated-office-file parser checks and monkeypatched parser/preflight flows. Kept dated live document false-negative regressions and checker-schema registration.

| Original lines | Test | Why it fails the keep rule |
|---|---|---|
| 21–30 | test_docx_paragraphs_and_table_cells | Generic generated DOCX parser I/O without a named live defect. |
| 33–42 | test_xlsx_cells_and_pptx_titles | Generic generated XLSX/PPTX parser I/O without a named live defect. |
| 57–62 | test_a_grep_of_the_binary_would_not_pass_but_parsing_does | Generic generated DOCX parser I/O without a named live defect. |
| 65–71 | test_missing_corrupt_and_escaping_files_fail | Generic file parser/error cases without a named live defect. |
| 74–85 | test_a_missing_parser_is_an_instrument_error | Monkeypatches the office parser dependency. |
| 88–97 | test_a_parser_value_error_stays_a_model_fail | Monkeypatches the office parser dependency. |
| 100–111 | test_preflight_names_a_missing_office_parser | Monkeypatches importlib behavior for an offline preflight. |
| 114–121 | test_campaign_preflight_refuses_a_missing_office_parser | Monkeypatches parser availability and exercises offline campaign preflight. |
| 137–176 | test_structural_names_headings_sheets_titles | Generic generated-office-file parser I/O without a named live defect. |
| 179–191 | test_one_file_must_satisfy_everything | Generic generated DOCX parser I/O without a named live defect. |
| 365–370 | test_a_time_written_one_way_matches_expect_written_another | Generated document I/O without a named live observation. |
| 373–380 | test_office_phrases_ignore_case_and_punctuation_between_words | Generated document I/O without a named live observation. |
| 383–395 | test_xlsx_header_aliases_apply_to_headers_only | Generated workbook I/O without a named live observation. |
| 398–433 | test_xlsx_exact_values_evaluate_simple_sum_and_addition_formulas | Generated workbook/parser flow without a named live observation. |
| 436–448 | test_section_groups_per_kind | Generated office-file/parser flow without a named live observation. |

### tests/wfe/tests/test_wfe_prompt_surface.py

| Original lines | Test | Why it fails the keep rule |
|---|---|---|
| 103–117 | test_task_requiring_absent_tools_is_blocked | Calls run_task as an offline end-to-end model task; prompt and suite contracts remain covered by value/config checks. |

## Kept files and their keep rule

| Path | Rule |
|---|---|
| tests/wfe/tests/__init__.py | Package marker for WFE test/harness imports. |
| tests/wfe/tests/test_wfe_cells.py | Pure expected-task-set logic. |
| tests/wfe/tests/test_wfe_checkers.py | Pure parser/scorer logic; dated live false-pass regressions and WFE suite/gold contracts. |
| tests/wfe/tests/test_wfe_contracts.py | Pure scoring/routing logic, named live failures, and current workspace/model/tool contracts used by WFE or Portal. |
| tests/wfe/tests/test_wfe_decision.py | Pure decision, exclusion, and stopping math. |
| tests/wfe/tests/test_wfe_gold_isolation.py | Answer-key isolation regression named by the 78c3c8987 fix commit; live WFE sandbox contract. |
| tests/wfe/tests/test_wfe_judge.py | Pure verdict parsing and endpoint-locality checks. |
| tests/wfe/tests/test_wfe_judge_compare.py | Pure inter-judge kappa calculation. |
| tests/wfe/tests/test_wfe_next_screens_slice.py | Validates current Portal seats, backend routing, context windows, and live WFE plan/suite config. |
| tests/wfe/tests/test_wfe_office_contains.py | Dated real WFE document-grading failures plus checker-schema registration. |
| tests/wfe/tests/test_wfe_plan_suites.py | Validates plan and suite files consumed by live WFE campaigns. |
| tests/wfe/tests/test_wfe_prompt_surface.py | Pure tool/taxonomy matching plus current served-workspace and suite contracts. |
| tests/wfe/tests/test_wfe_publish.py | Pins the unique-temp-file publish fix from commit 623e62634. |
| tests/wfe/tests/test_wfe_runner_timing_guard.py | Pins the malformed timing-field runner fix from commit 1747794ab. |
| tests/wfe/tests/test_wfe_timing.py | Pure engine-payload parsing and timing summary math. |
| tests/wfe/tests/test_wfe_tool_modes.py | Validates the production tool allowlist against current Portal/bench workspace config. |

## Live checks for the orchestrator

Run after merge against the live services. These commands validate the unchanged served route and one real document grading row; a passing offline suite is not live evidence.

1. Prompt and tool surface through OWUI → Pipeline:

   uv run scripts/wfe_production_smoke.py --workspaces auto-documents,auto-compliance

   Success is a real turn for both workspaces with the expected served workspace/tool surface and no prompt/tool mismatch. HTTP failure, wrong routing, unavailable tool, or a blocked task is a failure.

2. Real document grading through the WFE runner and configured engines:

   uv run python -m tests.wfe.campaign --plan tests/wfe/plans/realuse_v1_documents.yaml --campaign-id test_trim_p1c_wfe2_20261118 --workspace auto-documents --smoke

   Success is a measured full row with the served model/engine identity and outcome PASS. No row, BLOCKED, HARNESS_ERROR, or a checker FAIL leaves the affected live path unproven or failed.

No live command was run by this worker.
