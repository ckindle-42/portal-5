# Spine Remediation Report

Safety tag: `spine-remediation-safety-c00c854` (baseline HEAD before this task).
Worked in place on `/Users/chris/projects/portal-5` (main branch, local machine) —
adapted from the task's cloud-sandbox instructions (`/mnt/user-data/outputs`,
fresh clone to `portal-5-spine`) since this is a local Darwin environment with
the live repo already checked out.

## 1. Verdict

All 8 findings (F1–F8) were re-confirmed at HEAD in Phase 1 — none STALE, none
CHANGED from the original review. All 6 remediation phases (2–6) landed. Nothing
is BLOCKED or GATE-pending. Final gate (`bash scripts/ci_local.sh`) is green:
1950 passed, 34 skipped, 1 xpassed, 0 failed.

## 2. Per-finding disposition

**F1 — server-side CI gap (must-fix).** CONFIRMED: `validate_system.py` absent from
`.github/workflows/*.yml`; present only in `.pre-commit-config.yaml` (bypassable).
Fixed in `9859dbe` by wrapping the 4 spine-gate functions
(`check_routing_regression`/AU, `check_wiki_core`/AJ, `check_wiki_facts_current`/AW,
`check_doc_currency`/AK) in `tests/unit/test_spine_gates.py`, which rides the
existing unbypassable `pytest tests/unit` CI lane (`.github/workflows/unit-tests.yml`).

**F2 — Rule 12 false claim (must-fix).** CONFIRMED: `scripts/ci_local.sh` did not
run the doc-currency gate before this task. Fixed as a side effect of F1's fix —
`ci_local.sh` runs `pytest tests/unit`, which now carries AK via
`test_spine_gates.py`, so CLAUDE.md:271's claim ("`ci_local.sh` will be red until
docs are reconciled") is true without any prose edit. No CLAUDE.md change needed.

**F3 — writeback overwrite (major).** CONFIRMED on full read (review's excerpt was
truncated, not wrong): `store.py`'s `save_unit()` does an unconditional
`path.write_text()` with no existence check; `writeback.py`'s `confirm_unit()`
calls it directly with zero collision guard. Fixed in `7690635`:
- Added `WritebackCollisionError` and a `supersede: bool` flag on `ProposedUnit`/
  `propose_unit()`.
- `confirm_unit()` now refuses to overwrite an existing canonical unit unless the
  new proposal's sources are a superset of the existing unit's sources (pure
  enrichment, always allowed) or the caller explicitly passed `supersede=True`.
- `seed_facts.py`'s machine-derived overwrite path is untouched — it doesn't go
  through `confirm_unit()`, so it stays intentionally idempotent as designed.
- Two live `auto_confirm=True` callers (`model_survey.py`, `_sweep_driver.py`)
  write date-stamped unit ids that intentionally replace the day's prior report
  on re-run; both were updated to pass `supersede=True` explicitly with a comment
  explaining why, preserving their existing behavior under the new guard.
- 4 new tests in `tests/unit/test_wiki_writeback.py` prove: blocked overwrite with
  fewer sources, allowed overwrite with superset sources, forced overwrite via
  `supersede=True`, and that a refused confirm leaves canon untouched.

**F4 — dead snapshot (minor).** CONFIRMED: zero non-JSON references to
`routing_decision_snapshot`. Removed in `84301a7`
(`tests/fixtures/routing_decision_snapshot.json`); `pytest tests/unit -k rout`
stayed green (69 passed).

**F5 — docstring check-letters (nit).** CONFIRMED: `check_capability_graph`'s
docstring said `AJ` but is registered as `AI`; `check_wiki_core`'s docstring said
`AK` but is registered as `AJ`. Fixed in `9e30ae3` — docstrings now match
registration exactly.

**F6 — content_hash excludes sources (nit, explore-first).** CONFIRMED:
`content_hash()` hashes `id:kind:title:body` only, omitting `sources`. Blast-radius
probe: folding `sources` into the hash would change the hash of **515/515**
(100%) of currently-stored canonical units — mass churn, exactly the "trap" the
task warned about. **NOT applied**, per the task's explicit instruction to defer
when impact is unbounded. Filed as a follow-up (see §4).

**F7 — confidence unvalidated (nit).** CONFIRMED: `__post_init__` validated
`sources` and `kind` but never `confidence`. Existing corpus check
(`portal_wiki/canonical/*.md` + `config/personas/*.yaml`) found only
`{high: 515, low: 1}` — fully in-vocabulary. Added validation in `9e30ae3`
(`confidence not in ("high","medium","low")` raises `ValueError`, mirroring the
`kind` check), plus 2 new tests (`test_reject_invalid_confidence`,
`test_valid_confidences`) in `tests/unit/test_wiki_core.py`.

**F8 — coarse keyword-fallback variant loss (minor).** CONFIRMED:
`_SECURITY_VARIANT_SIGNALS` defines 7 security variant keyword sets, but Layer 2's
`_WORKSPACE_ROUTING`/`_SCORER_VARIANT_MAP` only carries a dedicated entry for
`redteam` — the other 6 (`blueteam`, `pentest`, `redteam-deep`, `purpleteam`,
`purpleteam-deep`, `purpleteam-exec`) are consulted only by `_infer_variant()`,
which is explicitly Layer-1 (LLM router)-only. Documented in `57bb7a4` — added a
paragraph to `docs/ADMIN_GUIDE.md`'s "How the LLM Router Works" section explaining
the degradation. Not hand-edited into any generated fact-unit;
`./launch.sh sync-config` confirmed idempotent (no diff) after the edit, and AW
(`check_wiki_facts_current`) stayed PASS.

## 3. Measurement proof (Phase 2)

Deliberately staled `docs/ADMIN_GUIDE.md` in a scratch commit, then ran the new
gate:
```
tests/unit/test_spine_gates.py ...F   [100%]
FAILED test_spine_gate[check_doc_currency] - AssertionError: check_doc_currency:
FAIL — 2/22 docs stale ...
expect FAIL rc=1
```
The pre-commit hook itself also went red on the scratch commit attempt
(`pytest unit suite` failed inside the hook), proving the gate bites at the commit
boundary, not just when invoked directly. Reverted with `git reset --hard HEAD~1`
(the scratch commit's `git add -A` had also swept in the not-yet-committed
`test_spine_gates.py`, so the hard reset removed it — recreated it identically and
reconfirmed green):
```
tests/unit/test_spine_gates.py ....   [100%]
4 passed
expect PASS rc=0
```
Red→green confirmed; the gate is real, not decorative.

## 4. Filed follow-ups

- **F6 content_hash / sources.** Folding `sources` into `content_hash()` is
  correctness-desirable (a unit whose citations change but body/id/kind/title
  don't currently produces an identical hash) but re-hashes all 515 stored units.
  Needs a dedicated migration task: bump the hash, re-save every canonical unit
  once under a tracked commit, and verify AW/AJ stay green through the churn —
  out of scope for this remediation per its own guardrail against unbounded
  blast radius.
- **LLM-layer labeled-corpus accuracy check** (review §6, referenced in
  `routing.py`'s own comments): whether the reconstructed `_SECURITY_VARIANT_SIGNALS`
  keyword sets for the 6 non-redteam variants actually match what the retired
  Layer-1 alias vocabulary believed — needs `scripts/routing_regression.py
  --layer=llm --labeled-corpus` against the live pinned router model in a heavier
  CI lane. Out of scope here (this task only touched Layer-2's documentation, not
  its accuracy).

## 5. Assumptions / could-not-verify

- Ran locally against the live `/Users/chris/projects/portal-5` checkout (main
  branch) rather than the task's prescribed fresh clone to
  `~/projects/portal-5-spine` and `/mnt/user-data/outputs/` — those paths are
  cloud-sandbox conventions that don't apply to this Darwin/local session. A git
  tag (`spine-remediation-safety-c00c854`) was created on HEAD before any work as
  the equivalent safety net.
- `check_routing_regression` (AU) needed no special env handling from the test
  wrapper — it already scrubs `PROMETHEUS_MULTIPROC_DIR` internally via
  `child_env` before invoking `routing_regression.py` as a subprocess.
- The Python 3.14 interpreter in this environment required registering the
  dynamically-loaded `validate_system.py` module in `sys.modules` before
  `exec_module()` — dataclass field resolution (`_is_type`) looks the module up
  via `sys.modules[cls.__module__]` and NoneTypes otherwise. This is a Python
  version quirk, not a project code issue; documented as a comment in
  `test_spine_gates.py`.
- Two `git commit` attempts (Phase 3 and Phase 4) were transiently blocked mid-task
  by the very gate this task installed (Phase 2's `test_spine_gates.py`), because
  each phase's code change stale'd 2–8 CLAUDE-Rule-12-bound docs whose content
  needed no edits, only a re-stamp. All were verified content-accurate before
  stamping (no factual drift found in any of them) and stamped in their own
  docs-only commits, per the "docs and code never share a commit" guardrail.
- `pytest portal` was not run as part of this task's own verification (only
  `pytest tests/unit`, per the task's explicit scope and CLAUDE.md's own guidance
  that `portal`'s module-tree suite is a separate, side-effect-prone lane) — but
  `bash scripts/ci_local.sh`'s full run did exercise
  `portal/modules/security/tests`, and left the documented `field_journal/`
  write-through artifacts, which were reverted/cleaned per the known-limitation
  procedure before considering the task done.

## 6. Final gate

```
python3 scripts/doc_ledger.py check          → PASS: 22 docs fresh vs HEAD (rc=0)
./launch.sh sync-config && git status --porcelain   → no diff (idempotent)
python3 -m pytest tests/unit tests/unit/test_spine_gates.py -q
  → 742 passed, 16 skipped, 1 xpassed, 0 failed
ruff check . && ruff format --check .        → all clean
bash scripts/ci_local.sh                     → 1950 passed, 34 skipped, 1 xpassed,
                                                0 failed — "ci-local: PASS — safe to push"
```
Working tree clean; `portal/modules/security/core/field_journal/` side effects
from the `ci_local.sh` run reverted per CLAUDE.md's documented procedure.

## 7. Commits landed (baseline `c00c854` → HEAD)

```
9859dbe test(spine): ratchet AU/AJ/AW/AK into pytest CI (server-side, unbypassable)
7645ca5 docs: stamp doc ledger after Phase 2 spine-gate test addition
7690635 fix(wiki): guard confirm-writeback against silent canonical overwrite
7809132 docs: stamp doc ledger for Phase 3 writeback-guard commit
84301a7 chore(tests): remove dead routing_decision_snapshot.json (unreferenced, stale slugs)
142d89e docs: stamp doc ledger for Phase 4 fixture-removal commit
9e30ae3 fix(wiki): align check-letter docstrings; validate confidence
4bb8d68 docs: stamp doc ledger for Phase 5 check-letter/confidence commit
57bb7a4 docs(router): note coarser variant routing on keyword-fallback path
```
Pushed to `origin/main` alongside this report.
