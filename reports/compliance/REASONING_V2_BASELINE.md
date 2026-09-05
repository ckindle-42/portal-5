# REASONING_V2_BASELINE

**Task:** `coding_task/v9_compliance/TASK_COMPLIANCE_REASONING_V2.md`
**Baseline commit inspected:** `9006ae6c` (design/reuse docs), September 4-5, 2026.
**This report's commit:** written against a working tree at `9006ae6c` + the P0/P1
changes described below (not yet committed at time of writing; see the task's
final commit for the exact SHA).

## P0.1 — What was read

- `DESIGN_COMPLIANCE_REASONING_V2.md`, `RESEARCH_COMPLIANCE_REUSE_V2.md`,
  `TASK_COMPLIANCE_REASONING_V2.md`, `TASK_COMPLIANCE_ARCHITECTURE_CLOSEOUT_V1.md`,
  `TASK_COMPLIANCE_ENGINE_LANDING_V1.md`.
- Current core: `portal/modules/compliance/core/{engine,coverage,propose,tiers,
  register_diff,change_pipeline,cip_register,cip_extract,mapping_store,
  review_queue,ingest,applicability,scope_derive,planted,text_signals}.py`
  and `portal/modules/compliance/tools/{compliance_mcp,compliance_retrieval}.py`.
- Runtime/data: no local diff pre-existing (working tree clean at `9006ae6c`
  except `tests/uat_corpus/`, already untracked and preserved untouched).
  Real operator corpus present at `coding_task/v9_compliance/LSPG-CIP/` (14
  CIP-standard subfolders, ~65 PDFs) — not yet ingested by this task's work
  (see P8-L status below).
- No Docker/live-stack rebuild was performed in this session; no live
  retrieval/rerank service was reachable, so the P0.4 live-retrieval baseline
  was not captured. This does not block P1 (semantic-defect correction),
  per the task's explicit early-baseline allowance.

## P0.2/P0.3 — Existing targeted suite

Baseline command (from the design doc F12):
```
.venv/bin/python -m pytest tests/unit/test_compliance_engine.py \
  tests/unit/test_compliance_tiers.py tests/unit/test_compliance_change_pipeline.py \
  tests/unit/test_cip_register.py -q --tb=short
```
Reproduced 60/60 passing at `9006ae6c`, consistent with F12 — the suite passed
while F01-F10 all independently reproduced against the same code (see below).
This confirms F12's finding: passing tests were not evidence of correct
semantics.

## F01-F12 disposition

| Finding | Reproduced at 9006ae6c? | Disposition after this task's P1 | Owner (file / test) |
|---|---|---|---|
| F01 bitemporal validity | Yes — reproduced via the design doc's exact probe (39 retired CIP-003-8 nodes covering 2023-01-01 returned 0; a synthetic FUTURE_EFFECTIVE node stayed in `future_effective_parts` after its date). | **FIXED_P1.** `engine.py` now selects by validity INTERVAL, not lifecycle label. | `core/engine.py`; `tests/unit/test_compliance_reasoning_v2_regressions.py::test_f01_*` |
| F02 current dates not sourced | Yes — `cip_register.py` defaulted an unrecognized version to `EFFECTIVE` with no dates. The CIP-003-9/CIP-012-2 date-vs-bulletin discrepancy itself is a P3 catalog-reconciliation item, NOT fixed here — flagged UNVERIFIED. | **PARTIALLY FIXED_P1** (unsafe default removed); **UNRESOLVED_P3** (actual date reconciliation against the NERC bulletins, and new-family/decimal-revision discovery, is P3 catalog work, not attempted this session). | `core/cip_register.py`; `test_f02_unrecognized_version_is_unknown_not_defaulted_effective` |
| F03 coverage measures presence | Yes — reproduced: two locatable spans (no obligation checked) returned `FULL`; three empty candidate lists returned `NONE, substantively_resolved=True`. | **DISABLED_P1 pending P5.** The automated classifier can no longer emit `FULL` from presence or a resolved `NONE` from absence — both are structurally impossible now (`coverage.py::_classify` only emits `UNRESOLVED`/`NEEDS_REVIEW`/`NOT_APPLICABLE`). Full obligation-atom comparison (P5) is NOT implemented. | `core/coverage.py`; `tests/unit/test_compliance_engine.py`, `test_compliance_planted.py`, `test_compliance_propose.py` |
| F04 approval bypass | Yes — an approved mapping to a nonexistent document/section returned `FULL` with zero proposer calls. | **FIXED_P1.** `_apply_approved_mappings` now resolves every approved mapping's document endpoint against the ingest sidecar, collects ALL approved mappings (not `[0]`), and surfaces disagreement/unresolved-endpoint as `UNRESOLVED`/`NEEDS_REVIEW` instead of a silent `FULL`. | `core/coverage.py`; `test_approved_mapping_requires_resolved_endpoint_and_agreement` |
| F05 scoping/time units | Yes — `_quant_claims` converted "1 calendar month" / "30 calendar days" / "30 business days" all to `30`; same-tier pairs were skipped entirely. | **FIXED_P1.** No cross-unit conversion; only same-(unit, business/calendar) claims are compared. Different units/qualifiers emit `comparison_uncertainty` (abstain), never silent equality. Same-tier disagreement now detected as its own `same_tier_disagreement` kind. Conflict resolution text no longer universally blames the lower tier. | `core/tiers.py`; `test_compliance_tiers.py`, `test_f05_*` |
| F06 semantic change erased | Yes — `Perform A; and` / `Perform A; or` compared cosmetically equal. | **FIXED_P1.** `_cosmetic_equal` only strips a trailing connector when BOTH sides carry the SAME one; a genuine AND<->OR swap on an otherwise-unchanged item is classified `LANGUAGE_CHANGED`/`logic` (never cosmetic). `diff_standard` now validates exactly one standard-version per side. | `core/register_diff.py`; `test_f06_*` |
| F07 applicability not verified | Yes (by code inspection; not independently re-probed this session). | **NOT ADDRESSED_P1 — P3 work.** Scope-derivation (`scope_derive.py`) and default-high/medium BCS applicability (`applicability.py`) are unchanged; still union policy-keyword presence into declared scope. Explicitly deferred to P3 §8. | `core/scope_derive.py`, `core/applicability.py` (untouched) |
| F08 retrieval eligibility hides dependencies | Yes (by code inspection). | **NOT ADDRESSED_P1 — P4 work.** Folder-based procedure exclusion, disabled FTS, and fusion-arm predicate ordering are unchanged. | `core/propose.py`, `tools/compliance_retrieval.py` (untouched beyond the F03/F04-driven anchor/relevance split) |
| F09 review/effective divergence | Yes — `compliance_review_decide` swallowed a `KeyError` on approve, and a rejection never revoked a prior approval. | **FIXED_P1** for the two specific defects named: `MappingStore.revoke()` added; `compliance_review_decide` now calls it on `REJECTED` and surfaces (rather than swallows) a missing-target error via `mapping_error` in the response. Full authenticated-reviewer identity enforcement remains **P7 work** (`decided_by` is still caller-supplied text). | `core/mapping_store.py`, `tools/compliance_mcp.py`; `test_f09_*` |
| F10 unreliable citations | Yes — a citation of current `CIP-003-9` matched the `CIP-003` prefix derived from superseded `CIP-003-8` and was flagged stale. | **PARTIALLY FIXED_P1.** Stale-citation matching in `coverage.py` now uses an exact, word-boundary identifier match instead of substring/prefix. `nerc_cip_requirement`'s missing as-of parameter and prefix-rollup API shape are **P3/P7 work**, not changed this session. | `core/coverage.py`; `test_f10_*` |
| F11 completeness not established | Not independently re-probed (register inventory unchanged). | **NOT ADDRESSED — P3 work** (independent completeness manifests, catalog-vs-corpus reconciliation). | — |
| F12 tests validated the wrong thing | Confirmed: 60/60 passing while F01-F10 reproduced. | **CLOSED.** The existing suite (`test_compliance_engine.py`, `test_compliance_tiers.py`, `test_compliance_change_pipeline.py`, `test_compliance_planted.py`, `test_compliance_propose.py`) has been updated in place to assert V2-safe behavior — every assertion that encoded a since-fixed unsafe verdict (`FULL`/`NONE` from an automated classifier, same-tier skip, prefix-match staleness, `full_gaps` implying confirmed absence) was rewritten, not deleted. A new `tests/unit/test_compliance_reasoning_v2_regressions.py` gives each F01-F12 finding above a direct, named regression test. | all files listed above |

## Test suite state after P1

```
uv run pytest tests/unit/ -k compliance -q
```
152 passed, 1 skipped (an environment-gated currency-network test), 0 failed —
up from the pre-existing 60-test targeted subset; the increase is from
updating/extending the existing files, not adding a parallel suite. Full
`tests/unit/` run and `ruff check`/`ruff format --check` status are recorded
in `reports/compliance/REASONING_V2_ACCEPTANCE.md` (P9) once that phase runs.

## Exit criterion check (P0)

Every F01-F12 finding above has a disposition (FIXED_P1 / PARTIALLY FIXED_P1 /
DISABLED_P1 pending P5 / NOT ADDRESSED — P3/P4/P7/P8 work) and a named
file/test owner. None are marked "already repaired with evidence" from before
this task — all twelve were independently reproduced or inspected fresh
against `9006ae6c`.

## Honest scope statement (read before treating this as a closeout)

This report and its companion `REASONING_V2_REUSE_DECISIONS.md` close **P0 and
P0-R only**, and this session additionally completed **P1** (the dangerous
verdict/selection-behavior corrections). **P2 through P9 — the versioned
bitemporal store, OSCAL/Utopia-pattern persistence, obligation-atom extraction,
hybrid traceability, the comparison/assessment engine, change propagation,
authenticated review workflow, the 30-case acceptance matrix, the live-corpus
P8-L rerun, and the SME packet — are NOT implemented in this session.** The
module's engineering status is **ENGINEERING_INCOMPLETE**, not
`ENGINEERING_COMPLETE_READY_FOR_SME_REVIEW`. See the task's final chat summary
for the exact remaining-phase breakdown and rationale.
