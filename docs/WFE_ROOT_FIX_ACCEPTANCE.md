# WFE root-fix acceptance ledger

| id | status | evidence | utc |
|---|---|---|---|
| P1-0 | PASS | origin ckindle-42/portal-5, branch main, tree clean; `git log --oneline 2dcc459e..origin/main` = 8b30a35b (scripts/engine_autoupdate.py only, no WFE overlap); ledger generator printed `90 ids`; HEAD before = 8b30a35b | 2026-10-14T02:59:28Z |
| P1-1.1 | PASS | `git am --3way /tmp/p5rf1/0001.patch` clean, no conflict -> commit 35f73749 (8 files, +225/-5); tests/_netguard/{netguard,sitecustomize}.py, tests/wfe/tests/conftest.py, sync_config PORTAL_SYNC_SKIP_PIPELINE_CHECK, supervisor test stubs the lab | 2026-10-14T02:59:28Z |
| P1-1.2 | PASS | `uv run pytest tests/unit/ tests/wfe/tests -q` -> 3328 passed, 6 skipped, 0 failed, 0 errors (207.27s); cited subset `tests/wfe/tests tests/unit/test_netguard.py tests/unit/test_bench_supervisor.py tests/unit/test_generated_artifacts_fresh.py` -> 293 passed, matching the authoring dry run; `uv run python scripts/validate_system.py` -> 220 pass, 0 fail, 3 warn, 3 skip (exit 0) | 2026-10-14T04:20:00Z |
| P1-1.3 | PASS | boundary found 3 live reaches and they were stubbed, not loosened -> 6719a770; `docker logs portal5-mcp-proxmox --since 90m | grep -icE 'container_start|snapshot|rollback|vzdump|start_vm|lxc'` = 0; supervisor test re-run with LAB_TARGET_*/LAB_*_VMID exported and SANDBOX_LAB_EXEC=true -> 36 passed; netguard refuses 127.0.0.1:11434 in-process and in a Python subprocess | 2026-10-14T02:59:28Z |
| P1-1.4 | PASS | docs/WFE_ROOT_CAUSES_20261013.md + WFE_ROOT_FIX_PROGRAM.md + ledger committed; registered in portal_wiki/canonical/unit-wfe-workspace-fitness.md; check BR (spine_code_coverage) PASS after the surface manifest was regenerated for the new files; Phase 1 re-baseline of config/complexity_budget.yaml prose 56826 -> 56841 (+15) | 2026-10-14T02:59:28Z |
| P1-2.1 | PASS | `git am --3way` clean on 0002/0003/0004 -> C1 e31e17be, C2 203cd2d2 (suites amended in), C3 29fa6385; suite sha256 prefixes match the task's table exactly: compliance_agentic 2eda624322eed502, compliance_agentic_full 28bf1259fcca21f0, compliance_agentic_loopset 13e2de5cc7cfc7ce, compliance_agentic_loopset_noformat a411a3cb40c4ad86, research 6a5a983746be51c7, compliance_reading_contract ee4789d2ded7f4a6; plan f7a0f015; Phase 1 test set after patch 4 = 332 passed (authoring dry run: 332) | 2026-10-14T04:20:00Z |
| P1-2.2 | PASS | 0c9dfb9e. `chat()` attaches the request's correlation id to whatever the call raises and the turn loop records it; direct-engine rows record no empty id. TestFailedTurnTrace, 4 tests (refused request, stall, the loop records it, no empty id off pipeline). | 2026-10-14T04:20:00Z |
| P1-2.3 | PASS | 002eec30. A rescored row keeps `original: {outcome, notes, instrument}`, written once so a second pass cannot bury the run's verdict, and records `rescore: {outcome, grader: instrument_fingerprint()}`; `report._grader_check` refuses mixed graders unless --allow-mixed. TestOfflineRescore + TestGraderComparison, 25 tests. | 2026-10-14T04:20:00Z |
| P1-2.4 | PASS | d9423d62; rig S2/I1/I2/I3 pass (16/16); live L1 ids 7228ad7f/bd434c62, L2 id changed on rebuild, L3, L4 exit 6; receipt /tmp/p1r_live_20261014T203448Z/receipt.json | 2026-10-14T20:40:04Z |
| P1-2.5 | PASS | `./launch.sh rebuild` exit 0; `curl -s localhost:9099/health | jq -r .build_sha` = bb50fac84c7d44e81bf20082b99d96dd55089789 = `git rev-parse HEAD`; backends 12/12 healthy, 58 workspaces | 2026-10-14T04:20:00Z |
| P1-2.6 | PASS | Both arms via `WFE_ENGINE=pipeline uv run python -m tests.wfe.campaign --plan tests/wfe/plans/decision_run_v1.yaml --smoke --arm <tag>`, preflight verdict OK for each. Incumbent: model hf.co/unsloth/Qwen3.8-27B-GGUF:Q4_K_M-ctx32k, served_models ['Qwen3.8-27B-oQ4e-mtp'], identity {omlx-reasoning, Qwen3.8-27B-oQ4e-mtp}, harness think native, instrument.deployed bb50fac8, PASS. Challenger: arm granite4.1:30b-ctx64k@card-c1832928, served_models ['granite-4.1-30b-4bit'], identity {omlx-reasoning, granite-4.1-30b-4bit}, harness think native, card sampling carried as a caller value (overrides.sampling temperature 0.0, row sampling temperature 0.0), instrument.deployed bb50fac8, PASS. | 2026-10-14T04:20:00Z |
| P1-2.7 | PASS | bb50fac8. Phase floor after the rebuild: `uv run pytest tests/unit/ tests/wfe/tests -q` -> 3384 passed, 6 skipped, exit 0 (225.69s). Complexity re-baseline: prose 56841 -> 56902 (+61; the program budgets the three patches at +23, the rest is the three specified build steps and their tests), god_lines 64841 -> 64767 (-74) and god_funcs 520 -> 519 from splitting the re-grade; `--gate` exits 0. | 2026-10-14T04:20:00Z |
| P1-3.1 | PASS | `git am --3way` on 0005-0012: 0005 d220c845, 0006 57dec7b8, 0007 71f91398, 0008 980c8625, 0009 58c80e9d, 0010 622ec06e, 0011 824faa02, 0012 987e2746. CONFLICT on 0009: `git am --3way` failed with `sha1 information is lacking or useless (tests/wfe/campaign.py)` — its pre-image blob is the authoring tree's, which the Phase 2 identity work moved. Resolution per the program contract: re-implemented every hunk's intent on HEAD (EXIT_GATE/GateRefused, the four gate refusals, pipeline-aware preflight, the `_cli()` wrapper, and both new tests), merging the preflight hunk with Phase 2's identity freeze rather than reverting it. No newer HEAD logic was reverted. 0010-0012 then applied cleanly. | 2026-10-14T14:50:00Z |
| P1-3.2 | PASS | 96a3296f. `expand_matrix(tier=...)`; run_id unchanged; `tier` on every manifest row; `--tier`/`--advance`; `load_advance`. test_wfe_tiers.py, 9 tests: screen is repeat 0 of the marked tasks; confirm is every task at repeats 0..2; the confirm append leaves no duplicate run_id and re-runs no row; a 10-task screen then a 30-task three-repeat confirm gives 30 compared tasks, while filtering the cell by tier would leave 20 (the screened tasks hold repeats 1-2 but not 0). | 2026-10-14T14:50:00Z |
| P1-3.3 | PASS | c849566e. `expected_sets`/`screen_expected`/`cell_expected` in report.py: the compared set comes from the manifest matrix, and two arms that expect different tasks error instead of comparing. test_wfe_cells.py, 5 tests. | 2026-10-14T14:50:00Z |
| P1-3.4 | PASS | 35bdd76a. `campaign_suite_digests` + `baseline_reusable`: another campaign's incumbent rows are reusable only under an identical instrument fingerprint and identical suite content. test_wfe_baseline.py, 4 tests (same instrument and suites allow reuse; a different fingerprint, changed suite content, or an unrecorded instrument each force a re-run). | 2026-10-14T14:50:00Z |
| P1-3.5 | PASS | 08402601. `report --screen-out` writes the advance list in exactly the form `--advance` reads, always advancing an intended workspace; `--fitness` computes confirm() per cell and dispose() per model from candidate_queue.yaml. Wilson intervals remain display-only. test_wfe_fitness_report.py, 15 tests including the round-trip from --screen-out into expand_matrix. | 2026-10-14T14:50:00Z |
| P1-3.6 | PASS | 10bff726; rig I4; live L5b record carries both identities + incumbent; receipt /tmp/p1r_live_20261014T203448Z/receipt.json | 2026-10-14T20:40:05Z |
| P1-3.7 | PASS | fe031be3; HP tests pass in the 3534 floor; live L5b HP PASS/PASS covers auto-compliance, STALE after rebuild | 2026-10-14T20:40:05Z |
| P1-3.8 | PASS | component test passes in the floor: 3534 passed 6 skipped | 2026-10-14T20:40:05Z |
| P1-3.9 | PASS | 492d51b8; live L6a controls found (gpt-oss:20b, hf.co Foundation-Sec-8B), portal5 absent; L6b rc=0 verified 53 differs 6 n/a 90 unrecorded 26 unrestorable 28; at-risk: command-r verified, granite4.1:8b-q8_0 verified, granite4.2:30b verified, Qwen3.6-27B bartowski differs, xyz-aquila-mini unrestorable; receipt /tmp/p1r_live_20261014T203825Z/receipt.json | 2026-10-14T20:40:05Z |
| P1-3.10 | PASS | arguable in 83458174: comp-p6j-09, comp-p6j-18 and comp-p6j-24 carry `"arguable": true` in every compliance suite that holds them (compliance_agentic 2, compliance_agentic_full 3, loopset 1, loopset_noformat 1), and the suites still pass their controls (test_wfe_controls.py 23 passed). Re-baseline in 27a0a67b: prose 56902 -> 57108, data_lines 11402 -> 11455 (patch 5's _ELIGIBILITY table), god_lines 64767 -> 64792, god_funcs 520 -> 519; `--gate` exits 0. | 2026-10-14T14:50:00Z |
| P1-3.11 | PASS | 804fab1b; rig: 16/16 PASS; receipt /var/folders/1r/140k52_x789f31ybwq9bt2300000gn/T/wfe-rig-gng86uvs/receipt.json | 2026-10-14T20:40:06Z |
| P1-X | FAIL | REOPENED by P1R: the hand-off HEAD moves to P1R's. Was PASS: Part 1 pushed to main; `git log origin/main..HEAD` empty after the push. Hand-off HEAD for Parts 2 and 4 is 27a0a67b (the last code commit; the ledger commit that follows it carries docs only), standing floor 3503 passed / validator 220 pas | 2026-10-14T20:05:34Z |
| P2-A | PENDING | | |
| P2-B | PENDING | | |
| P2-C1 | PENDING | | |
| P2-C2 | PENDING | | |
| P2-C3 | PENDING | | |
| P2-C4 | PENDING | | |
| P2-C5 | PENDING | | |
| P2-C6 | PENDING | | |
| P2-C7 | PENDING | | |
| P2-C8 | PENDING | | |
| P2-D | PENDING | | |
| P2-E1 | PENDING | | |
| P2-E2 | PENDING | | |
| P2-E3 | PENDING | | |
| P2-E4 | PENDING | | |
| P2-E5 | PENDING | | |
| P2-E6 | PENDING | | |
| P2-E7 | PENDING | | |
| P2-X | PENDING | | |
| P3-A | PENDING | | |
| P3-B | PENDING | | |
| P3-C | PENDING | | |
| P3-D1 | PENDING | | |
| P3-D2 | PENDING | | |
| P3-D3 | PENDING | | |
| P3-D4 | PENDING | | |
| P3-D5 | PENDING | | |
| P3-D6 | PENDING | | |
| P3-D7 | PENDING | | |
| P3-D8 | PENDING | | |
| P3-D9 | PENDING | | |
| P3-E | PENDING | | |
| P3-F | PENDING | | |
| P3-X | PENDING | | |
| P4-P1 | PENDING | | |
| P4-P2 | PENDING | | |
| P4-P3 | PENDING | | |
| P4-P4 | PENDING | | |
| P4-N1 | PENDING | | |
| P4-N2 | PENDING | | |
| P4-N3 | PENDING | | |
| P4-N4 | PENDING | | |
| P4-N5 | PENDING | | |
| P4-N6 | PENDING | | |
| P4-N7 | PENDING | | |
| P4-N8 | PENDING | | |
| P4-N9 | PENDING | | |
| P4-N10 | PENDING | | |
| P4-N11 | PENDING | | |
| P4-N12 | PENDING | | |
| P4-F | PENDING | | |
| P4-X | PENDING | | |
| P5-A1 | PENDING | | |
| P5-A2 | PENDING | | |
| P5-A3 | PENDING | | |
| P5-A4 | PENDING | | |
| P5-A5 | PENDING | | |
| P5-A6 | PENDING | | |
| P5-A7 | PENDING | | |
| P5-A8 | PENDING | | |
| P5-A9 | PENDING | | |
| P5-B1 | PENDING | | |
| P5-B2 | PENDING | | |
| P5-C1 | PENDING | | |
| P5-C2 | PENDING | | |
| P5-C3 | PENDING | | |
