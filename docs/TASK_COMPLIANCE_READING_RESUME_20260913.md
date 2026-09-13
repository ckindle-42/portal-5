# RESUME — compliance reading architecture (one authoritative assessment path)

**Status:** implementation complete, fast acceptance green, live real-model
acceptance NOT yet green. **Branch:** `main`. **Spec:**
`docs/IMPLEMENTATION_BRIEF_COMPLIANCE_READING_20260912.md` (rev 2).
**Baseline commit:** `2ef55701` (the design brief's snapshot).

This is the pickup document. Read it with the spec; the spec is the authority on
*what correct means*, this file records *what is done, what is known, what
failed, and how to finish*.

---

## 1. What is done

One authoritative service now owns every substantive verdict; every projection
derives from its `AssessmentResult`.

| File | State |
|---|---|
| `core/determination.py` | new records (`AssessmentRequest/Result`, `GoverningBundle`, `SourceSlice`, `CandidateSet`, `AlignmentResult`, `CoverageExplanation`, `ScenarioOverlay`, `ConstraintBinding`, `AlignmentRecord`, …); codes U09–U13 |
| `core/migrations/schema.py` | migration 7: `assessment_results` + run lifecycle columns |
| `core/repository.py` | `record_assessment`, `get_assessment`, `assessments_for_run`, `create_run`/`update_run`/`get_run`/`mark_interrupted_runs` |
| `core/assessment_source.py` | governing bundle (complete Part + lead-in + references), `CorpusSnapshot`, full-text `CandidateSet`, exact `materialize_overlay` |
| `core/obligation_alignment.py` | `align_part` — categorical SAME/DIFFERENT/UNKNOWN quorum; every candidate must appear or `valid=False`; constraint bindings with literal validation |
| `core/gate.py` | `compare_aligned` (SAME only; unchanged `compare_constraint`), `run_aligned_gate` (authoritative full governing text; no `"or delegate."`) |
| `core/assessment_report.py` | `explain` — one source-linked report call, IDs only, closed consistency rules |
| `core/assessment.py` | `assess_part(request, context) -> AssessmentResult`; U03/U04/U09/U10/U11/U12 emitted |
| `core/assessment_service.py` | `assess_requirement`/`build_requests` |
| `core/assessment_runs.py` | `start_run`/`run_status`/`run_result`/`cancel_run`; one worker; durable states |
| `core/coverage.py` | `coverage_matrix(context=…)` classifies via `assess_part` |
| `tools/compliance_mcp.py` | gaps/analyze default to `operation=start|status|result|cancel`; trace resolves assessment IDs; exact overlays |
| `core/operations.py`, `scenarios.py`, `change_pipeline.py`, `scripts/materialize_compliance_v3.py` | route through `assess_part`; scenarios use pinned before/overlay-after; no hardcoded SUPPORTED; materialization emits no verdict by default |
| acceptance | `tests/data/compliance_reading_acceptance.json`, `tests/unit/test_compliance_reading_acceptance.py`, `scripts/verify_compliance_reading_acceptance.py` |

## 2. Verified

- **Fast acceptance: 26/26 PASS** (`uv run python scripts/verify_compliance_reading_acceptance.py`) plus H1–H4 and A01–A11 contract checks (85 focused pytest tests; full unit suite earlier **1796 passed, 4 skipped**).
- `ruff check .` / `ruff format --check .` clean.
- Spine gates pass: `check_spine_code_coverage`, `check_wiki_core`, `check_spine_drift` (new modules registered in `portal_wiki/canonical/unit-compliance-engine.md`; `config/spine_surfaces.yaml` regenerated).
- **Live real-model, routed `compliance_gaps`, controlled case 02: `documentary=FULL`, council `SUPPORTED 3/3`, cited 35-day witnesses, no gaps** (≈570 s/Part). This is the product goal met end-to-end.

## 3. What failed live, and what was fixed

A full `--live --runs 1` pass over all 26 cases ran ~2h51m and returned **26/26 FAIL**. Two defects in *our layer* (not the models) dominated:

1. **Council cite-or-drop rejected real citations.** Seats reasoned correctly but cited the human document names (`B21.txt`, `A22.txt`, `L22.txt`); the packet allowlist only held the opaque chunk hash as `commitment_id`, so a correct seat was dropped as "off-packet" (case 07: 2/3 seats dropped; case 02: 1/3). **Fixed:** `gate._build_aligned_candidate` now sets `commitment_id` to the human document name (plus the stable id), and `obligation_alignment` carries `document_id` on every `AlignmentRecord` so `assessment_report._matches_consensus` matches document-name citations. `council.py` internals untouched.
2. **One shared fixture KB leaked decoys.** Every case retrieved top-15 across all 22 fixture docs, so case 02 (A22+B22+V) also saw L22/S22/M22. **Fixed:** the live runner ingests only each case's declared candidate documents into an isolated per-case KB (`<kb>-c<id>`).

Two live defects found earlier and already fixed:
- alignment output truncated at the council's 900-token cap → dedicated 4096-token alignment transport (`obligation_alignment._ollama_alignment_seat`, routed in `assessment_runs._guarded_seat`);
- the reader returned correct relations but omitted the single unambiguous selectable slice ids → `_resolve_slices` fills the system-owned candidate/primary-governing slice (off-packet ids still rejected).

Live case 02 re-run after the fixes passed: **`got=FULL`**.

## 4. What is expected (acceptance, from spec §7/§7.1)

- The 26 cases must pass **live**, with real configured models, per-run receipts, and the exact required citations / excluded decoys / gap ids / resolution flags.
- Cases 02–20 and 25–26 via the routed async `compliance_gaps`; 21–24 via controlled failures on the real route; 01 against the pinned operator corpus (actual derived scope stays UNKNOWN; conditional documentary FULL reported separately).
- Run the positive + three supply-chain decoy cases **three times each**; do not average away a false PARTIAL.
- **No architecture-wide completion claim** until the live suite is green (spec §9).

## 5. How to continue

1. **Re-baseline before commit/push** (the reason this was paused):
   - `python3 -m portal.platform.wiki.coverage --write-manifest` (already done once; re-run after any new module).
   - Run `python3 scripts/validate_system.py` (the pre-push lettered suite) and reconcile anything it flags (generated docs/fact-unit currency, complexity budget).
   - `uv run mypy portal/` is **already non-zero at baseline** (pre-existing debt in `policy_graph.py`, `org_graph.py`, `platform/inference/router/tools.py`, `platform/wiki/render.py`, `operations.py` ~5, `tests/test_render.py`); our new modules are clean. Do not attribute those to this work.
2. **Run the live suite and watch it** (do not fire-and-forget):
   ```
   nohup uv run python scripts/verify_compliance_reading_acceptance.py --live --runs 1 \
     > /tmp/compliance_acceptance_live.log 2>&1 &
   ```
   Poll every ~15 min: `grep -ac '^case ' log`, `ls .../reading_acceptance/<ts>/case-*`,
   and confirm `HTTP/1.1 200` lines are advancing and no tracebacks. Roughly
   ~10 min/Part; a 1-run pass is ~3h, `--runs 3` ~8–9h. Receipts:
   `coding_task/v9_compliance/private/reading_acceptance/<ts>/` (gitignored;
   never force-add).
3. **Triage any live FAIL** against the case's `expected` block in
   `tests/data/compliance_reading_acceptance.json`; the runner retains the raw
   council/alignment/report trace per case. Likely remaining classes:
   model nondeterminism on the council (ESCALATE on split votes), residual
   cite-or-drop on odd citation forms, and U09 on alignment JSON shape.
4. **Close out** with per-run IDs/fingerprints, elapsed/model-call counts, and
   every unresolved failure (spec §9).

## 6. Known deviations / limits

- `coverage.py` keeps the legacy context-less `_shares_topic`/`detect_conflicts`
  path for pre-existing component tests; the product path (`context=`) never
  uses it. Removing it means migrating those legacy tests.
- `assessment_runs.build_requests_for` duplicates the argument composition now
  in `assessment_service.build_requests`; both call the same primitives.
- Real absence claims stay UNRESOLVED until a completed-boundary receipt exists;
  retrieval success alone is not absence (spec §5).
- Operator corpus / private PDFs are never copied into `tests/data/`.
- The architecture brief itself (`docs/IMPLEMENTATION_BRIEF_COMPLIANCE_READING_20260912.md`)
  is the contract; do not weaken it to make a live run pass.

## 7. Fast reference

```
# fast acceptance (hermetic)
uv run pytest tests/unit/test_compliance_reading_acceptance.py -q
uv run python scripts/verify_compliance_reading_acceptance.py        # 26/26

# live acceptance (real models; hours)
uv run python scripts/verify_compliance_reading_acceptance.py --live --runs 1
uv run python scripts/verify_compliance_reading_acceptance.py --live --cases 02,10 --runs 1

# per-commit gate
uv run ruff check . && uv run ruff format --check .
uv run pytest tests/unit/ -q
```
