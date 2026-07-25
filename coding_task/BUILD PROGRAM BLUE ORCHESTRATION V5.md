# BUILD_PROGRAM_BLUE_ORCHESTRATION_V5

Maturation program. V3 built the reasoning-first machinery; V4 fixed the three
defects that machinery exposed. The V4 close-out then delivered the real
finding: **the machinery is correct and recall did not move** (strong solo
confirm-only recall 3/17 ≈ 17.6%, flat V3→V4; council 1/17, down). V5 stops
guessing at *why* and builds the instrument that answers it, then routes the
build on what the instrument finds.

**Reference commit:** HEAD `0cefb41` (2026-07-25). This is a *starting*
reference only. Every task below requires the agent to re-verify HEAD and
gather its own facts against live code — no line numbers, function bodies, or
counts in this program are authoritative. Where this doc states a number
(e.g. "3/17", "16/17 cogito non-votes"), it is quoting the V4 close-out report
as the *motivation*; the agent re-derives it from the checkpoint or a fresh
run before treating it as fact.

**Predecessors:** `BUILD_PROGRAM_BLUE_ORCHESTRATION_V3` (Mentor/Budgets/
Barrier-tools), `BUILD_PROGRAM_BLUE_ORCHESTRATION_V4` (three-defect
remediation). Both fully landed. The V4 close-out report
(`reports/BLUE_ORCHESTRATION_V4_CLOSEOUT_20260725.md`) is the input to V5.

---

## The governing principle for this program

**Measure before acting. Fix measurement before acting on it.** The V4
close-out reports recall as a single confirm-only fraction. That number cannot
distinguish two completely different worlds:

- **World A** — the corpus telemetry *contains* the discriminating evidence
  for the missed techniques, and the model failed to connect it. This is a
  reasoning/prompt/model problem, fixable in the blue lane.
- **World B** — the corpus telemetry genuinely *lacks* discriminating evidence
  for those techniques, so a non-confirm is the honest answer. This is a
  corpus-coverage problem, and 17.6% is closer to the true signal ceiling.

Every downstream build decision depends on which world we're in, per technique.
V5 refuses to build a recall fix until the instrument says where the misses
actually are. A task that "improves recall" before this measurement exists is
building blind and is out of scope until Phase A lands.

---

## Sequence

| Phase | Task file | Purpose | Type |
|-------|-----------|---------|------|
| V5A | `TASK_BLUE_V5_ATTRIBUTION_INSTRUMENT.md` | Per-technique, per-arm recall attribution: split every non-confirm into evidence-present-miss vs honest-negative, using the detection library's own discriminators as a label-blind evidence oracle | **Measure** — standing instrument, no behavior change |
| V5B | `TASK_BLUE_V5_ROUTED_REMEDIATION.md` | Data-routed fix: the instrument's output selects the branch (reasoning-path fix vs corpus-coverage expansion vs model-swap experiment). Branches are specified; which one executes is decided by V5A's data, not by this doc | **Build** — conditional on V5A |
| V5C | `TASK_BLUE_V5_COUNCIL_ROSTER.md` | Close the council thread: track the second non-voting model with evidence, and make an explicit, data-grounded decision on whether council mode is a supported path with the current roster | **Decide + track** |
| V5D | `TASK_BLUE_V5_V2_BASELINE.md` | Establish the missing corpus-matched pre-orchestration (V2) baseline so the V3+V4 program's actual contribution is measurable, not just V4-vs-V3 | **Measure** — retrospective, non-blocking |

**Order and dependency:**
- **V5A is the gate.** V5B cannot start until V5A's attribution table exists —
  V5B's branch selection *is* V5A's output. This is a hard dependency.
- **V5C and V5D are independent** of V5A/V5B and of each other. They can run in
  parallel or in any order. V5C is small and concrete; V5D is a bench-run.
- The agent may land V5A, V5C, V5D in any order, but **must complete V5A before
  designing V5B's actual change** — reading the attribution data is step one of
  V5B.

---

## What each task must gather for itself (grounding contract)

This program gives direction. Each task file states *what to establish* and
*how to verify it*, and forbids acting on any fact the agent has not
independently confirmed against HEAD. Non-negotiable per task:

1. **Re-verify HEAD** and `git log` before treating any predecessor claim as
   current.
2. **Rediscover every symbol** referenced by name (functions, files, config
   keys) — confirm it exists, read it live, never trust a line number or a
   quoted body from this doc or the close-out report.
3. **Re-derive every motivating number** before building on it. If this doc or
   the close-out says "3/17" or "16/17", the agent recomputes it from the
   checkpoint (if present) or a fresh replay run, and proceeds from the number
   it actually observes — which may differ, and if it does, that discrepancy is
   itself a finding to record, not to paper over.
4. **Stop-the-line on absent ground truth.** Any instrument or check that would
   need the answer key to function in production is an eval-only artifact and
   must be flagged as such (the `_cite_or_drop` label-blindness discipline
   applies to every new measurement too).

---

## Invariants across V5

- **I8** — Discovery is not punished. Nothing in V5 reclassifies a correct
  ANOMALOUS_UNCLASSIFIED as a failure. The attribution instrument counts an
  honest-negative as a *success of judgment*, not a recall miss.
- **Label-blindness in production paths** — The attribution instrument reads
  ground truth because it is an *eval instrument scoring a labeled corpus*
  (explicitly allowed — it never runs in production). But any code path it
  shares with production (e.g. the discriminator token extraction) must remain
  label-blind on the production side. The instrument may *import* the
  label-blind machinery; it may not *push* label-awareness into it.
- **Additive-only** — V5A/C/D add instruments, lists, and reports. They change
  no verdict behavior. Only V5B changes behavior, and only along the branch the
  data selects.
- **Honest-BLOCKED over faked-green** — If V5A shows the misses are honest
  negatives (World B), the correct V5B outcome is "do not attempt a recall fix
  in the blue lane; the corpus is the constraint" — a legitimate, documented
  non-build. A forced recall improvement against a corpus that lacks the
  evidence would be faked-green.

---

## Success criteria for the program

V5 is complete when:

1. **V5A** produces a committed, reproducible per-technique/per-arm attribution
   table splitting every non-confirm into evidence-present-miss vs
   honest-negative, with the evidence-oracle logic under test and a validate
   check guarding its label-blind/production-blind boundary.
2. **V5B** has executed the branch the V5A data selected — *or* has documented,
   with the data, why the correct action was a non-build.
3. **V5C** has an evidence-backed disposition for the second non-voting model
   and an explicit recorded decision on council mode's status.
4. **V5D** has either produced the V2 baseline number or documented precisely
   why it can't be produced from available artifacts (and what a clean run
   would require).

The recall number itself is **not** a success criterion. V5 succeeds by making
the recall number *legible and correctly attributed*, and by acting truthfully
on what it reveals — even if the truthful action is "the ceiling is the corpus,
not the model."

---

## Status

- [x] V5A — Attribution instrument  (commit d31da27a at HEAD d31da27a)
      Rollup (strong arm): A=0 ; B=4 ; INDETERMINATE=6 ; MISATTRIBUTION=0
- [x] V5B — R1 discriminator expansion → R3 documented non-build
      (commit 2ff39da5 at HEAD 2ff39da5)
      Initial A=0/B=4/I=6/M=0; post-R1 A=2/B=6/I=0/M=0;
      targeted I 6→0, then B-dominant R3; production routing held
- [x] V5C — Council roster decision  (commit d1beead0 at HEAD d1beead0)
      Second non-voter tracked: cogito:32b @ 1/17; council disposition:
      retained-but-experimental
- [x] V5D — V2 baseline  (commit 3b30fbb1 at HEAD 3b30fbb1)
      V2→V3→V4 confirm-only (strong solo): 4/17 → 3/17 → 3/17

Agent records the V5B branch selection in the status line above once V5A data
is in hand, and appends `[x]` + commit sha + HEAD per phase.

---

## After V5

Whatever V5B's branch, the loop closes the same way it has each round: a fresh
corpus-replay sweep, an honest close-out report, and a `KNOWN_LIMITATIONS.md`
reconciliation (resolved items removed, new findings recorded as canonical
wiki units). If V5A reveals World B for most techniques, the natural successor
program is corpus-coverage expansion (the meta3 scenario/SPL gaps already in
KNOWN_LIMITATIONS are the same shape) — but that is a V6 question, decided by
V5's data, not pre-committed here.
