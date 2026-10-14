# WFE root-fix acceptance ledger

| id | status | evidence | utc |
|---|---|---|---|
| P1-0 | PASS | origin ckindle-42/portal-5, branch main, tree clean; `git log --oneline 2dcc459e..origin/main` = 8b30a35b (scripts/engine_autoupdate.py only, no WFE overlap); ledger generator printed `90 ids`; HEAD before = 8b30a35b | 2026-10-14T02:59:28Z |
| P1-1.1 | PASS | `git am --3way /tmp/p5rf1/0001.patch` clean, no conflict -> commit 35f73749 (8 files, +225/-5); tests/_netguard/{netguard,sitecustomize}.py, tests/wfe/tests/conftest.py, sync_config PORTAL_SYNC_SKIP_PIPELINE_CHECK, supervisor test stubs the lab | 2026-10-14T02:59:28Z |
| P1-1.2 | PASS | `uv run pytest tests/unit/ tests/wfe/tests -q` -> 3328 passed, 6 skipped, 0 failed, 0 errors (207.27s); cited subset `tests/wfe/tests tests/unit/test_netguard.py tests/unit/test_bench_supervisor.py tests/unit/test_generated_artifacts_fresh.py` -> 293 passed, matching the authoring dry run | 2026-10-14T02:59:28Z |
| P1-1.3 | PASS | boundary found 3 live reaches and they were stubbed, not loosened -> 6719a770; `docker logs portal5-mcp-proxmox --since 90m | grep -icE 'container_start|snapshot|rollback|vzdump|start_vm|lxc'` = 0; supervisor test re-run with LAB_TARGET_*/LAB_*_VMID exported and SANDBOX_LAB_EXEC=true -> 36 passed; netguard refuses 127.0.0.1:11434 in-process and in a Python subprocess | 2026-10-14T02:59:28Z |
| P1-1.4 | PASS | docs/WFE_ROOT_CAUSES_20261013.md + WFE_ROOT_FIX_PROGRAM.md + ledger committed; registered in portal_wiki/canonical/unit-wfe-workspace-fitness.md; check BR (spine_code_coverage) PASS after the surface manifest was regenerated for the new files; Phase 1 re-baseline of config/complexity_budget.yaml prose 56826 -> 56841 (+15) | 2026-10-14T02:59:28Z |
| P1-2.1 | PENDING | | |
| P1-2.2 | PENDING | | |
| P1-2.3 | PENDING | | |
| P1-2.4 | PENDING | | |
| P1-2.5 | PENDING | | |
| P1-2.6 | PENDING | | |
| P1-2.7 | PENDING | | |
| P1-3.1 | PENDING | | |
| P1-3.2 | PENDING | | |
| P1-3.3 | PENDING | | |
| P1-3.4 | PENDING | | |
| P1-3.5 | PENDING | | |
| P1-3.6 | PENDING | | |
| P1-3.7 | PENDING | | |
| P1-3.8 | PENDING | | |
| P1-3.9 | PENDING | | |
| P1-3.10 | PENDING | | |
| P1-3.11 | PENDING | | |
| P1-X | PENDING | | |
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
