# PORTAL5_ACCEPTANCE_EXECUTE_V9 — Claude Code Prompt

> **Supersedes** `PORTAL5_ACCEPTANCE_EXECUTE_V8.md` (archive to
> `docs/_archive_execdocs/`). V9 updates for the post-collapse / post-alias-
> retirement / post-routing-integrity codebase (HEAD `87b19bf`).

**V9 changes from V8:**
- **Workspace count corrected: 21 production workspaces** (V8 said 35 — that was
  pre-collapse). The collapse folded 104→21; counts are config-driven, so the
  preflight prints the live number.
- **Retired-alias S6 references removed.** V8 said "S6 adds auto-redteam-deep/
  auto-pentest/auto-purpleteam/…". Those ids are **retired**; S6 now tests
  `auto-security` with variant awareness (the section code was already migrated
  in the alias-finish work — s06 asserts routing to `auto-security` for
  redteam/blueteam/etc. intents).
- **New:** routing-integrity baseline (`tests/routing/baseline.json`) and
  served-model correctness (`model_pin`) are now assertable — S3/S21 tie into
  the routing regression; S10 personas can be served-model-checked.
- bench-* workspaces remain **out of acceptance scope by design** — full-catalog
  routing + TPS is `bench_tps.py`'s job.

**Scale is config-driven — run the preflight; don't trust baked numbers:**
```bash
python3 scripts/execute_preflight.py     # 21 production workspaces, 138 personas
```

The acceptance suite is not a benchmark and asserts no TPS/perf numbers.

---

## Your Role

You are the **acceptance execution agent**. Run the section suite against a live
stack, diagnose failures, retry intelligently, produce a pass/fail report with
evidence. **You do NOT modify product code** (`portal/**` is protected).

---

## Phase 0 — Preflight (required)

```bash
python3 scripts/execute_preflight.py                 # must end "OK to run"
ps aux | grep portal5_acceptance | grep -v grep      # nothing already running
curl -s localhost:9099/health >/dev/null && echo "pipeline ok"
```

`PORTAL_ENABLE_EVAL` should be **unset** for acceptance — the suite covers the
21 production workspaces, not the eval/bench set. If the preflight shows a
retired-alias leak, STOP (surface regression).

---

## Autonomous Monitoring Loop — required default

Full suite is ~82 min (S10c compliance personas ~50 min alone). Establish a
`ScheduleWakeup` loop immediately after launching; check liveness + section
progress every ~15 min; diagnose stalls; halt with evidence if hung.

---

## Running

Entry point is `tests/portal5_acceptance_v6.py` (confirm it's still the current
runner via `ls tests/portal5_acceptance_v*.py`; if a higher version exists, use
it):

```bash
python3 tests/portal5_acceptance_v6.py --section ALL          # full suite
python3 tests/portal5_acceptance_v6.py --section S3,S10,S60    # routing + personas + tools
python3 tests/portal5_acceptance_v6.py --section S0-S5         # inclusive range
python3 tests/portal5_acceptance_v6.py --section S6            # security workspaces
```

The 28 section files on disk (`tests/acceptance/s*.py`) are the authoritative
section list. Key sections for the current surface:
- **S3 (routing)** — production-workspace routing. Ties to the routing baseline
  (below).
- **S6 (security workspaces)** — `auto-security` + variant routing. Asserts
  redteam/blueteam/purpleteam/pentest *intents* route to `auto-security`; the
  retired standalone ids are gone.
- **S10 / S10c (personas)** — persona resolution; now served-model-checkable.
- **S17 (cad)**, **S21 (llm router)**, **S23 (model diversity)**.

---

## Coverage (current)

S3 covers the production workspaces via `WORKSPACE_PROMPTS` (derived live from
`WORKSPACES` in `_common.py` — no hardcoded list to drift). S6 covers
`auto-security` and its variants. S17 covers `auto-cad`. All 21 production
workspaces should have routing coverage across S3+S6+S17 — confirm with the
preflight list against the section coverage; report any production workspace
with no covering section.

---

## New in V9 — routing + served-model verification

The recent routing-integrity work added a versioned baseline and a served-model
regression gate. Acceptance should confirm these hold end-to-end:

**1. Routing baseline still green (before the suite):**
```bash
python3 scripts/routing_regression.py --assert-baseline    # matches tests/routing/baseline.json
```
If this fails, routing has drifted from its proven baseline — that's a product
regression; report it and do NOT mask it by adjusting acceptance expectations.

**2. Served-model correctness (during S10 persona tests):**
For any `model_pin` persona the preflight lists, confirm the acceptance run
recorded it being served its pinned model. A persona resolving to the right
workspace but served the wrong model is the exact bug class recently fixed —
S10 should catch a regression. If a persona test passes routing but the served
model ≠ its pin, that's a `{sec}-WARN`/fail worth flagging.

---

## Results + dashboard

```bash
python3 scripts/update_grafana_acceptance.py --input ACCEPTANCE_RESULTS.md
git add ACCEPTANCE_RESULTS.md config/grafana/dashboards/portal5_acceptance.json
git commit -m "acceptance: run <date> — <N> sections, <pass>/<total>, <notable>"
```

---

## Failure playbook

- **`{sec}-ERR` NameError row** — stale checkout (missing-import defects in
  decomposed section files were fixed); re-clone at HEAD.
- **S6 asserts on a retired id** — you're on a stale section file or stale doc;
  S6 should assert `auto-security`, not `auto-redteam`. Confirm HEAD.
- **Routing baseline assertion fails** — product routing regression; report,
  don't mask.
- **A production workspace has no covering section** — coverage gap; report it
  (don't invent a test in product-protected code; note for the implementation
  agent).
- **Persona served wrong model** — served-model regression; report with the
  persona slug + expected pin + actual served model.

## Non-negotiables
- Preflight first; 21 production workspaces is the current truth, printed live.
- `PORTAL_ENABLE_EVAL` unset for acceptance.
- Product code read-only; regressions get reported, never masked by loosening
  acceptance expectations.
- Routing baseline + served-model checks are pass/fail signal, not advisory.
