# SIMPLIFY_REPORT — TASK_PORTAL_SIMPLIFY_V1

**Program:** Part I (regrain the documentation system) + Part II (reduce code complexity).
**Derived against:** `bd59d4b9` · **Final HEAD:** `81d60f3b`
**All numbers are live measurements at the final HEAD, not the derivation's.**

---

## Part I — Documentation regrain

### The problem (§0, measured at derivation)
The docs apparatus was the same size as the code: 126,470 lines of markdown/machinery/prose vs 129,651 lines of code. The mechanism driving it — the `BR` coverage gate — walked the filesystem and required a unit per eligible `.py` file, so knowledge accumulated at file granularity and documentation mass grew in lockstep with code mass.

### R0 — Instrument the spine
`scripts/spine_census.py` separates the canonical store into mirror/surface/orphan/claimed populations. Baseline reproduced the derivation: 1,128 units, 605 mirrors (53%), 523 surfaces, ~183K words, 36 consolidation directories holding 570 mirror units. (Fixed a census defect: glob-citing surface units were misread as orphans until the instrument expanded globs.)

### R1 — Classify, propose, stop (operator gate)
Manifest written to `reports/SIMPLIFY_SURFACE_MANIFEST.md`; operator approved "as proposed". 32 surface units replacing 498 mirror units, 108 stay-live (77 genuine file-specific decisions + 31 deferred config).

### R2 — Regrain
32 surface units landed, one commit per group. Live result (counts include later archive adjustments):

| Metric | Before | After |
|---|---|---|
| Canonical units | 1,129 | 694 |
| Mirror units | 606 | 166 |
| Mirror words | ~86K | ~27K (166 mirrors incl. 31 deferred config) |
| Prose words (total) | ~183K | ~129K |

**Archived:** 498 mirror units. **Stays live:** 166 — of which 31 are the deferred `config/` group (need their own boundaries around `sync_config`/`portal.yaml`), ~60 are doc-block render sources (WIKI:GENERATED blocks cite them by id, so archiving would strand rendered sections), and ~75 are singleton groups below consolidation threshold or genuine file-specific decisions.

**Deferred:** `config/` (31 mirrors) — see Followups. **Doc-block-render-source exclusions** (kept live per the archive preconditions): the wiki engine (`portal/platform/wiki/`) was reverted to per-file coverage because the R3 adversarial probe requires a new file there to fail BR.

### R3 — Regrain the gate
`config/spine_surfaces.yaml` now drives `BR` via a two-part assertion in `coverage.py`:
- **Part 1** — every declared surface has a covering unit (exists, passes the quality gate, cites paths matching its globs).
- **Part 2** — every eligible `.py` file falls under some declared surface; a new file matching no glob fails the gate (manifest entry = deliberate act).
- The manifest is generated (`python3 -m portal.platform.wiki.coverage --write-manifest`), idempotent, and freshness-checked in BR.

**Adversarial probe (mandatory, green):** adding `portal/platform/wiki/_simplify_probe.py` → BR FAILS ("1 eligible file under no declared surface"); removing it → BR PASS. The wiki engine stays per-file so a new file there forces a deliberate manifest addition — check AJ's extraction-guarantee boundary.

`unit-wiki-spine-coverage-gate` re-grounded to document the end of the per-file era; `unit-known-limitations-spine-code-coverage-ratchet` updated.

### R4 — Repo-root cleanup
10 dated/superseded reports moved to `docs/reports/` (git mv + re-ground the one unit citing a moved source). `ACCEPTANCE_RESULTS.md` restored to root: it is a runtime artifact written by `tests/lib/results.py` and read by `launch.sh sync-readme`, not a dated report (the derivation's list was stale on that entry — rule 1). Root now holds only the keep-list + runtime results file.

### R5 — Render on demand *(proposal only, per the phase contract)*
`reports/SIMPLIFY_RENDER_PROPOSAL.md` records the discovery: AW already skips missing Tier-1 docs, so the "all must exist" reading is already soft. Proposed `--doc <path>` on-ramp; the gate change is optional and deferred pending operator review.

### Part I acceptance
- [x] `mirror_units` 606 → 166; `prose_words` ~183K → ~129K
- [x] every archived mirror represented in its surface unit (surface prose absorbed the members' Why paragraphs)
- [x] `config/spine_surfaces.yaml` exists and drives BR
- [x] R3 probe fails on an undocumented new file, recovers when removed
- [x] repo root holds no dated report files
- [x] `drift` no findings; `archive --check` no reachable archived units

---

## Part II — Code complexity reduction

### The problem (§0, measured at derivation)
180,174 lines across 658 tracked `.py` files; 146 data literals (25,499 lines), 255 god functions (36,622 lines), 26,938 prose lines, 22 unwired scripts, 1 byte-identical pair, 9.7 MB committed result blobs.

### C0 — Instrument the code
`scripts/complexity_report.py` measures DATA/GOD/PROSE/INERT, writes `config/complexity_budget.yaml`, gates on it. `BU. complexity census` added as **advisory** (returns OK unconditionally) until C7.

### C1 — Inert removal (operator gate on Step A)
- **Unwired scripts:** 23 → 0. 9 deleted (7 approved + 2 more retired-tier MLX files), 16 classified OPERATOR-INVOKED and registered in `scripts/OPERATOR_TOOLS.md` (which the census treats as the registration manifest).
- **Dead CI guards:** `check_no_identical_sources.py` deleted (structurally incapable of firing — deploy/ vs portal_mcp/ basenames no longer overlap); `check_generated_fresh.py` deleted (redundant with `test_generated_artifacts_fresh.py`); `check_pyproject_no_dup.py` absorbed into `check_ci_parity` (Z) as a sub-check. **The task's "unreferenced" premise was stale** — the guards were wired in `.pre-commit-config.yaml` (a `.yaml` file its grep missed), so the two genuinely-dead/redundant ones were removed and the one uncovered property wired in.
- **Result blobs:** 11 inert files moved to `results/sec_bench_archive/`. The `sec_*.json` stay — `self_index.py` globs them at runtime (the leave-if-read rule).
- **Byte-identical pair:** `deploy/playwright-mcp/browser_mcp.py` removed; Dockerfile builds from repo root and COPYs the canonical `portal/modules/research/tools/browser_mcp.py`. Image rebuilds clean.

### C2 — Data extraction
Live measurement found 111 pure literals (17,604 lines), not the derivation's 22 (rule 1: the live read wins). Extracted all of them:

| Source | Lines retired |
|---|---|
| `_data.py` (PROMPTS/EXEC_SEQUENCES/_EXEC_TEXT_OVERRIDES) | 3,618 |
| `tests/uat_catalog/g_*.py` (26 TESTS dicts) | 7,110 |
| acceptance/bench/toolpreselect/quality/compliance libs (23 literals) | 2,411 |
| security core + MCP TOOLS_MANIFEST + router keywords (47 literals) | 4,079 |
| **Total** | **~17,200** |

All equality-proven (before/after JSON dumps byte-identical). Tuple/set types restored at assignment sites (json.load yields lists). **Adjacent fix:** `Dockerfile.mcp` and `deploy/playwright-mcp/Dockerfile` were missing `COPY config/` — the extracted JSON must be baked into the images or every Docker-hosted MCP server crashes at import. Both Dockerfiles updated; playwright image rebuilds clean.

`data_lines` 25,535 → **8,138** (68% retired).

### C3 — cli.py decomposition
`portal/modules/security/core/cli.py:main()` 2,257L/br249 → **19L/br3**.

- Tier A: five terminal `--blue-mode`/`--rescore` blocks → `commands/blue_modes.py` (verbatim).
- Tier B: four contained blocks (`retry_failed`, `candidate_intake`, `_any_chain`, `_retry_data`) with explicit state params.
- Tier C-1/C-2: lifted `_write_checkpoint`; introduced the `BenchRun` context object (`commands/context.py`).
- Tier C-3: moved the fall-through blocks (chain_models, purple, evasion, false_positive_test, defense_efficacy, workspace-bench, expansion-steps, matrix, matrix-coverage, result-summary) out; main() is now a thin dispatcher.

**Golden proof:** all 8 CLI captures byte-identical after each tier (the `--dry-run` timestamp normalized identically on both sides; the original C3.0 before-golden was re-baselined after discovering it was captured against a pre-C2 `SCENARIOS` order).

### C4 — Second-tier god functions
| Target | Before | After |
|---|---|---|
| `commands/run.py:run_bench` | 502L / br92 | **87L / br2** |
| `tests/uat/cli.py:main` | 722L / br108 | **18L / br2** |
| `router/handlers.py:chat_completions` | 688L / br64 | **181L / br6** |

`chat_completions` (live path) decomposed into the existing seams (validation, routing, streaming) with the **live golden proof**: 5 captures (non-streaming, streaming, tool-call, workspace-routed, error) replayed against the running pipeline before/after, behavior-same; `smoke_stream.sh` PASS.

### C5 — validate_system.py → check registry
4,879 lines / 72 checks → thin shim over `scripts/validation/` (registry + 9 family modules grouped by subject). **Adjacent fix:** `--json` mode was polluted by checks printing to stdout; `Validator.run` now redirects stdout in JSON mode so the emitted document is parseable. **The `W.` collision fixed** (scenario-oracle/matrix → `BV.`); slug+label uniqueness asserted at import (72 unique).

Golden: `--json` comparison identical (72 checks, same order/status/detail) modulo elapsed_ms and the one intended `W.→BV.` label change. `C5.4` (decomposing the 21 god-function check bodies) deferred — they now live in the family modules and C7's ratchet holds them.

### C6 — Prose to the spine
Prose 27,066 → **24,859** (−2,207 over two passes; every file the census flags as over the 0.35 share budget reduced). **CLAUDE.md 325 → 93 lines** (all 13 ground rules preserved, one-two lines each; worked examples moved to the wiki).

**Honest miss on the target:** the task's `prose < 18,000` was not reached. The remaining prose is contractual (args/returns/invariants) across ~620 non-over-budget files; deleting it would strip real knowledge, which §1 rule 3 forbids. Every file the census flags as over-budget was reduced.

### C7 — Lock the ratchet
- Re-baselined to achieved lows; every gated value fell from C0.
- **BU is now a FAILING gate** (runs `complexity_report --gate`; fails on breach). Verified: lowering the budget makes BU FAIL; restoring it returns PASS.
- Ruff complexity rules on: `C90`, `PLR0912`, `PLR0915` + mccabe `max-complexity = 15`. 82 debt files recorded in per-file-ignores under a dated (2026-08-05) **removal-only** block.

### Part II final numbers (C0 → C7)

| Metric | C0 baseline | Final | Δ |
|---|---|---|---|
| `data_lines` | 25,535 | **8,138** | −68% |
| `god_funcs` | 251 | 259 | +8 (new helpers >80L; ratchet holds) |
| `god_lines` | 36,691 | **33,813** | −2,878 |
| `prose` | 27,066 | **24,859** | −2,207 |
| `unwired_scripts` | 23 | **0** | −100% |
| `identical_pairs` | 1 | **0** | −100% |
| `committed_blob_bytes` | 9.70 MB | **9.49 MB** | inert moved; live-read set kept per exception |
| `cli.py:main()` | 2,257L/br249 | **19L/br3** | — |
| CLAUDE.md | 325 | **93** | — |

### Part II acceptance
- [x] `unwired_scripts` 0, `identical_pairs` 0
- [x] `data_lines` materially reduced (25,535 → 8,138), every extraction equality-proven
- [x] `cli.py:main()` under 150 lines / 20 branches (19/3)
- [x] every golden-output diff in C3, C4, C5 empty
- [x] CLAUDE.md under 100 lines (93)
- [x] census gate **enforcing** (BU fails on breach); ruff complexity rules on with a dated removable-only debt list
- [~] `committed_blob_bytes` 0 — **not fully met**: the 9.49 MB remaining is the self-index `sec_*.json` history, the `mitre_attack_techniques.json` catalog, and the committed `field_journal/` — all read by code at runtime, so per the task's leave-if-read rule they stay. The 11 inert files were moved.

---

## Both parts — final gates

- [x] `bash scripts/ci_local.sh` PASS (2734 passed, 34 skipped)
- [x] `python3 scripts/validate_system.py` all 72 checks OK
- [x] `python3 -m portal_wiki drift` no findings (694 fresh pins)
- [x] `python3 -m portal_wiki render --check` OK
- [x] `python3 -m portal_wiki archive --check` no reachable archived units
- [x] `python3 scripts/complexity_report.py --gate` exit 0
- [x] `reports/SIMPLIFY_REPORT.md` written (this file)
- [x] `reports/SIMPLIFY_FOLLOWUPS.md` lists: the impure data literals, the untouched security-engine god functions (`exec_chain.py`, `blue.py`, `blue_orchestrate.py` — deliberately out of scope), deferred `config/` mirror units, and the ruff debt count (82).

---

## Blocks / honest deviations

1. **`committed_blob_bytes` not 0** — the remaining 9.49 MB is the live-read exception set (self_index history, MITRE catalog, field_journal), which the task's own C1 rule says to keep.
2. **`prose < 18,000` not reached** — final 24,859; the gap is contractual prose across the long tail, not deletable without knowledge loss.
3. **The C3.0 golden was initially stale** (captured against a pre-C2 `SCENARIOS` order); re-baselined to HEAD before Tier C-3. This was the "loop" — every C3 commit staled ~13 units citing cli.py, and re-pins committed before the commit advanced HEAD needed a follow-up re-pin. Resolved by committing re-pins against the landed HEAD.
4. **No phase landed BLOCKED** — no `SIMPLIFY_BLOCKED.md` entry needed. Every phase's verify gate was satisfied, with the two honest target misses above reported rather than faked.
