# Phase-1 test trim — lane `trim-bench-sec`

Scope: `tests/benchmarks/`, `tests/security/`, and the `tests/` top-level leftovers
(`tests/_archive`, `tests/_archive_execdocs`, `tests/comfyui`, `*.bak`).

Role note up front: this lane found **no bulk retirement** in `tests/security/` or the
`tests/benchmarks/` drivers. Every `portal.*` module *and* symbol those files import still
resolves against HEAD (see Evidence, check E5), and `pytest tests/security --collect-only`
collects 1 080 tests with zero errors. Most of `tests/benchmarks/` is not tests at all but
live exercisers (`bench_*_probe.py` driven by `scripts/rebench_plan.py`), several of which
`portal/` product code imports at runtime (`capability_lib`, `bench/notify`, `bench_repair`).
Those were kept. The deletions below are the ones with a mechanical, re-checkable proof.

## Deletions (18 files: 1 Python test file + 17 stale documents)

| path | category | proof |
| --- | --- | --- |
| `tests/benchmarks/test_empty_retry.py` (67 lines) | mock-only | The file re-implements the guard it claims to test: its own docstring says "`_stream_one_run` is a closure inside `bench_tps()`, not a module-level attribute, so these tests replicate the `_run_with_empty_retry` logic inline". It imports nothing from `portal/`, feeds a `_make_stub` queue it built itself, and asserts on that stub's call counter. No product branch is decided by any asserted value. |
| `tests/benchmarks/COVERAGE_AUDIT_2026-06-26.md` | retired | Point-in-time snapshot against HEAD `be20f14` (2026-06-26); self-declared superseded ("supersedes prior date-stamped audits"). Its counts (90 workspaces, 21 MCP servers, 130 personas) are now derived live by `portal config show` / computed fact-units, so a frozen copy is stale by construction. Zero references anywhere in the repo. |
| `tests/_archive/PORTAL5_UAT_EXECUTE_V1.md` | retired | Archived copy of the execute prompt; `CHANGELOG.md:517` records the archival, and the live document is `tests/PORTAL5_UAT_EXECUTE_V5.md`. Zero references in code, docs or canonical wiki units. |
| `tests/_archive_execdocs/PORTAL5_BENCH_EXECUTE_V1.md` | retired | Superseded by the live `tests/PORTAL5_BENCH_EXECUTE_V4.md`. Zero references. |
| `tests/_archive_execdocs/PORTAL5_BENCH_EXECUTE_V2.md` | retired | Same supersession as V1. Zero references. |
| `tests/_archive_execdocs/PORTAL5_UAT_EXECUTE_V2.md` | retired | Superseded by `tests/PORTAL5_UAT_EXECUTE_V5.md`. Zero references. |
| `tests/_archive_execdocs/PORTAL5_UAT_EXECUTE_V3.md` | retired | Same supersession as V2. Zero references. |
| `tests/_archive_execdocs/PORTAL5_UAT_EXECUTE_V4.md` | retired | Same supersession as V2. Zero references. |
| `tests/_archive_execdocs/PORTAL5_ACCEPTANCE_EXECUTE_V6.md` | retired | Superseded by `tests/PORTAL5_ACCEPTANCE_EXECUTE_V9.md`. Zero references. |
| `tests/_archive_execdocs/PORTAL5_ACCEPTANCE_EXECUTE_V7.md` | retired | Same supersession as V6. Zero references. |
| `tests/_archive_execdocs/PORTAL5_PROMPT_V6.md` | retired | Superseded generation of the acceptance prompt set (V9 is live). Zero references. |
| `tests/_archive_execdocs/ACCEPTANCE_TEST_GUIDE.md` | retired | Guide for the archived acceptance generations; V9 is the live doc. Zero references. |
| `tests/_archive_execdocs/TASK_BENCH_EXECUTE_V7_UPDATE.md` | retired | Task doc for a bench-execute generation that no longer exists (V7 of the bench prompt is absent from `tests/`). Zero references. |
| `tests/_archive_execdocs/ROUTING_FALLBACK_ANALYSIS.md` | retired | Archived point-in-time analysis inside an explicitly archived directory; the routing fallback it measures is pinned by live unit tests instead. Zero references. |
| `tests/_archive_execdocs/README.md` | retired | README *of the archive directory itself* — travels with the directory it documents. |
| `tests/UAT_RESULTS_20260726_partial.md.bak` | retired | July-2026 UAT result snapshot superseded by `tests/UAT_RESULTS.md` + `tests/UAT_RUN_LOG.md`; `grep -rn "UAT_RESULTS_2026072"` across the repo returns nothing but the three files themselves. |
| `tests/UAT_RESULTS_20260727_pre_rerun_failed.md.bak` | retired | Same supersession and same zero-reference check as above. |
| `tests/UAT_RESULTS_20260728_pre_rerun2.md.bak` | retired | Same supersession and same zero-reference check as above. |

Note on `tests/comfyui`: named in the lane scope, but the directory **does not exist at HEAD**
— the only ComfyUI references left are archived wiki units under `portal_wiki/archive/`
(`unit-comfyui-c*`, `unit-comfyui-runner`). Nothing to delete.

## Numbers

| property | before | after |
| --- | --- | --- |
| `.py` files in scope (`find tests/benchmarks tests/security -name '*.py'`) | 249 | 248 |
| `.py` lines in scope (`… \| xargs cat \| wc -l`) | 48 504 | 48 437 |
| non-Python lines deleted (documents) | — | 6 057 |
| `portal/` total line coverage (`tests/unit/ tests/wfe`, `-n auto`) | 51.003 % (49 395 / 96 848) | 50.998 % (49 391 / 96 848) |
| `portal/` files falling from >0 covered lines to 0 | — | 0 |

Coverage delta: **−0.005 pp**, well inside the 0.5 pp ceiling. The four-line difference is
attributable to one WFE test that failed in the first "after" run (see Open), not to any deletion.

## Kept deliberately (with reason)

- All `tests/benchmarks/bench_*_probe.py`, `bench_tps.py`, `bench_router*.py`, `bench_lab_exec.py`
  and friends — live exercisers; `scripts/rebench_plan.py` names them as the re-bench commands.
- `tests/benchmarks/capability_lib.py`, `tests/benchmarks/bench/notify.py`, `bench_repair/`,
  `compliance_judgment_r1_experiment{,_v2}.py`, `bench_cad_gauntlet.py`, `prismml_mlx_server.py`,
  `bench_capability.py`, `bench/discovery.py` — imported by `portal/` product code at runtime
  (`_data.py`, `capsules.py`, `field_journal.py`, `loop.py`) or by `tests/unit/` tests. Deleting
  them would break product code, not just tests.
- `tests/benchmarks/embedding_consumers/` (5 057 lines) — the strongest "closed campaign"
  candidate in this scope (EmbeddingGemma 2 is now the single platform embedder per CLAUDE.md,
  and `KNOWN_LIMITATIONS.md` retires the `:8917` embedder), **but** the canonical wiki unit
  `unit-design-embedding-consumers-harness.md` declares every file in it as a live `path:`
  claim, so deleting it would hard-fail the drift census (`BS`) unless that unit is re-grounded
  first. Re-grounding canonical units is outside this brief — flagged for the orchestrator.
- `tests/security/**` (22 376 lines, 157 test files) — nothing in it qualifies. Every imported
  product symbol resolves; nothing is permanently skipped (the two `pytest.skip("mutation.py not
  landed yet")` branches in `test_boundaries.py` are guarded by `if not path.exists()` and
  `portal/modules/security/core/bully/mutation.py` exists, so they run); duplicate test-function
  names across files number 4 and each pair targets different check families.
- `tests/security/review/` and `tests/security/review_eval/` are executed by
  `scripts/validation/review_program.py` (validation check HO), so they gate something real.
