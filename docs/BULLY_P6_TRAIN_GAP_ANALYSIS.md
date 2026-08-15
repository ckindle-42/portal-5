# P6 TRAIN acceptance gate — gap analysis (frozen five-arm cousin-suite)

Written 2026-08-15 after independent re-verification of the merged
`bully/P6-flywheel` branch (`03e24a05`) surfaced that the acceptance gate's
core measurement — not just a live-demo nicety — was left as a permanent
stub. This doc traces exactly what's real, what's missing, why it's missing
(a genuine unresolved design question, not an oversight), and what
building it actually requires. Written before scoping a follow-up task so
the follow-up starts from a correct premise instead of re-deriving all of
this.

## 1. The confirmed gap

`portal/modules/security/core/bully/training.py::_default_five_arm_eval`
always returns `macro_f1_delta_vs_full_stack: None`. `evaluate_acceptance`
treats `None` as "below the +5pt threshold" unconditionally, so **every**
TRAIN run is structurally blocked from ever passing, regardless of the
trained model's actual quality. The `declined_no_gain` verdict produced by
P6's own live demonstration run was not a real measurement — it was the
one guaranteed outcome of calling a stub.

A second, smaller gap sits next to it: `incumbent_delta_pt` (the "no
regression vs incumbent on the general security bench" leg) defaults to
`None` too, but `evaluate_acceptance` treats `None` there as **pass**, not
fail — the opposite failure mode. `scripts/defensive_bully_train.py`'s
`cmd_run` never computes or passes this value, so that leg silently no-ops
in the one CLI path an operator would actually run, rather than blocking as
the spec intends ("no regression vs incumbent" is listed as a real PASS
condition, not an optional one).

Both are real per `FINAL_ARCHITECTURE_DEFENSIVE_BULLY.md` §4.3, which
places "acceptance: frozen five-arm suite + intake floors + candidate delta
+ model-canary" entirely inside `bully/training.py::run(role)` — i.e. P6.4
owned this, not a later phase. `FINAL_BUILD_PROGRAM_DEFENSIVE_BULLY.md`'s
checklist lists "training (toolchain, five-arm gate, canary, atomic alias)"
as one line item, confirming the five-arm gate was scoped as part of
TRAIN's own deliverable, not external infra TRAIN was meant to consume
pre-built.

## 2. What's already real and reusable

This is better-resourced than it first looks — most of the hard
infrastructure already exists, tested, and correct:

- **Held-out, leakage-safe test split with real labels.** HARV
  (`harvest.py::_assign_split`) already does a deterministic ~70/20/10
  train/val/test split keyed on `group_family`, so no family straddles
  train/test — exactly the "test set frozen before the harvest window"
  requirement (L1). The `cousin_smeller` role's `test` split is sitting in
  `PORTAL5_HUNT_DIR/corpus/cousin_smeller/<dv>.jsonl` today with real
  examples harvested from actual `grade`/`objection`/`council_block`
  decision events.
- **Label-blind oracle, already built and BM-boundary-enforced.**
  `recall_attribution.py::evidence_presence` / `attribute_cell` computes
  honest-miss ground truth (PRESENT/ABSENT/INDETERMINATE, then
  TRUE_POSITIVE/MISATTRIBUTION/FALSE_NEGATIVE/HONEST_ANOMALY/etc.) from
  telemetry the model actually saw, with zero access to expected labels —
  this is exactly the oracle a five-arm harness needs, and it's
  intentionally eval-side-only (production `bully/` code is barred from
  importing it, verified by import-scan tests already in place).
- **Bootstrap CI, already implemented.** `_sweep_driver.py::_bootstrap_ci`
  computes a 95% bootstrap CI over paired deltas — the exact statistic
  the L2 claim needs ("bootstrap 95% CI above zero"). Reusable directly or
  as a very close template.
- **Retrieval mechanism, already built.** `cousin_engine.candidate_set` +
  `Organ.knn` (used in `orchestrator._do_analyze`) produce the
  nearest-neighbor cousin candidates that a "+retrieval" arm would inject.
- **Playbook mechanism, already built and already wired into the
  investigation call.** `playbooks.for_hunt` +
  `investigation._apply_playbook_context` are live in
  `orchestrator._do_analyze` today via the `playbook` kwarg P6.3 added —
  a "+playbook" arm is a matter of toggling that kwarg, not building
  anything new.
- **Per-role model resolution, already built.** `bully.config.resolve_role_model`
  resolves the `tool`/`reasoning`/`expert` roles to concrete Ollama tags
  from `config/portal.yaml` at call time — a "specialist" arm swaps one of
  these role tags for the trained LoRA alias; the resolution machinery
  doesn't need new code, just a new call site.
- **Intake and model-canary legs are real, not stubbed.**
  `_default_intake_eval` calls the actual `intake.run_candidate_intake`;
  `_default_canary_eval` calls the actual `drift_gate.check_model_canary`.
  Only the five-arm leg (and the unwired incumbent-delta leg) are gaps.

## 3. The real unresolved question: what does "cousin-judgment" mean operationally?

This is why the harness wasn't a quick add, and why P6's agent flagged it
rather than building something wrong under time pressure — worth
preserving as the reason, not just noting the gap:

`cousin_engine.grade()` (the function that actually produces the
`SAME`/`SIMILAR`/`NEW`/`DIFFERENT`/`ANOMALOUS_UNCLASSIFIED` relationship
label) is **100% deterministic** — Jaccard-distance decomposition +
fixed-weight composite + threshold table, verified by direct code
inspection (`_decompose`, `_weighted_composite`, `_classify_relationship`).
No model call happens anywhere inside it, and
`orchestrator._do_analyze` calls it directly with no LLM output threaded
through `coverage` or `candidates`. **An LLM cannot improve macro-F1 on a
task it was never doing.** A five-arm suite that literally re-ran
`grade()` five times would show zero variance across arms — there is
nothing for "base" vs "specialist" to differ on.

The coherent resolution, and the one this analysis recommends: "cousin-
judgment macro-F1" refers to the **investigation verdict**
(`inv_result.verdict`, produced by the real LLM call in
`investigation.run_arm` → `blue_orchestrate._run_three_section`) — the
same three-way axis (`CONFIRMED`/`RULED_OUT`/`ANOMALOUS_UNCLASSIFIED`)
`recall_attribution` already scores elsewhere in this codebase (e.g. the
AZ emergent-miss-corpus lane). Under this reading, the five arms differ in
exactly the ways the spec names — retrieval on/off, playbook on/off,
specialist model vs base — because all three levers already exist and
already point at the one real LLM call site in the pipeline. This is a
judgment call, not something pinned down verbatim in
`FINAL_INTERFACES`/`FINAL_VALIDATION` — worth a operator/architect
confirmation before building, since it's the one design decision the
harness's shape depends on.

## 4. What's genuinely left to build

1. **Retrieval injection into the investigation call.** Today
   `organ.knn`/`candidate_set` run *after* `investigation_arm` in
   `_do_analyze`, not before/into it — there's no existing code path that
   feeds retrieved candidates into the LLM's context the way `playbook`
   already does. This needs the same shape of change P6.3 made for
   playbooks: an optional kwarg threaded through `investigation.run_arm`.
2. **The five-arm harness itself** (new module, e.g.
   `bully/five_arm_eval.py`, eval-side — allowed to import
   `recall_attribution`, unlike production `bully/` modules): given the
   frozen `cousin_smeller` test split, run each held-out episode through
   `investigation.run_arm` five times (retrieval off/on × playbook off/on,
   plus the specialist-model variant with both on), score each arm's
   verdict against the `recall_attribution` oracle, compute per-arm
   macro-F1, and the arm5-vs-arm4 bootstrap 95% CI via `_bootstrap_ci` (or
   a close adaptation).
3. **Wire it into `training.py`**: replace `_default_five_arm_eval`'s
   `five_arm_eval_fn` default with a real one that calls the new harness;
   keep the injectable-callable pattern already in place so tests stay
   hermetic.
4. **Wire `incumbent_delta_pt` for real** in
   `scripts/defensive_bully_train.py::cmd_run` — call `candidate_eval`'s
   existing delta computation (or expose it as a callable the same way
   intake/canary already are) instead of leaving the parameter
   permanently `None` (which silently no-ops the regression-vs-incumbent
   check instead of blocking on missing evidence, the opposite of every
   other leg's fail-closed default in this module).
5. **A frozen policy-version stamp** for the five-arm thresholds
   (`+5 macro-F1`, `CI95 lower > 0`, `≤2pt regression`) per the "frozen
   before eval, no post-hoc tuning" rule — these are already hardcoded as
   module constants (`_FIVE_ARM_MIN_MACRO_F1_DELTA`,
   `_MAX_ARM_REGRESSION_PT`) in `training.py`, so this is really just
   confirming they stay frozen once the harness starts producing real
   numbers, not new work.

## 5. Sizing

This is a real, scoped chunk of work — not a one-line fix, but also not a
from-scratch buildout given how much of items 2-3's dependencies (§2) are
already sitting there proven. Rough shape: item 1 (retrieval kwarg) is a
small, P6.3-shaped change; item 2 (the harness) is the bulk of the work —
comparable in size to one of P6's five sub-phases (HARV/PLAY/TRAIN/ROSTER
each ran a few hundred lines + tests); items 3-4 are wiring; item 5 is a
documentation/confirmation step. A single focused build phase (call it
P6.6, or fold into the start of P7 before any real cutover work) is the
right scope — not urgent enough to block P0-P6's already-verified,
already-pushed work, but it does block any *genuine* (non-stub) TRAIN
acceptance run, and therefore blocks P7's release-acceptance checklist
item requiring "a frozen five-arm training comparison runs to a recorded
verdict."

## 6. Recommendation

Scope a dedicated follow-up task (`TASK_BULLY_P6_6_FIVE_ARM_HARNESS_V1.md`
or similar) before attempting P7's final E2E proof. It should:
- Open with the §3 design question as an explicit decision to confirm
  (recommend the investigation-verdict reading above, but don't treat it
  as settled without sign-off — it changes what "ground truth" means).
- Build items 1-4 above.
- Re-run TRAIN's live demonstration once the harness is real and confirm
  whether a genuine `serve` or a genuine (non-stub) `declined_no_gain`
  comes out the other end — either is an acceptable, honest outcome; a
  structurally-forced stub result is not.
