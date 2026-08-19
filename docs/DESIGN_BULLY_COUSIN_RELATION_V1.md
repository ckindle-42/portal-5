# DESIGN_BULLY_COUSIN_RELATION_V1.md

Reference document for `TASK_BULLY_COUSIN_RELATION_V1`. Written before the
implementation phases (C.1-C.8); those phases implement what is decided here,
not the other way around.

## 1. The M.3 misattribution, and its disproof from the run's own JSON

`docs/BULLY_RELATE_INVESTIGATE_RUN_M3_V1.{md,json}` (HEAD `bbf3c385`) reported
100/100 real seeds classified `ANOMALOUS_UNCLASSIFIED` and attributed this to
anchor/adapter coverage gaps — implying the fix was more anchors, better
adapters, or retuned thresholds.

**That attribution does not survive reading the raw rows.** Across the 100
seeds, `confidence` takes exactly three distinct values: `0.35`, `0.55`,
`0.85` — one value per seed *source*, invariant within a source regardless of
seed content. The cause is mechanical, not statistical:

- `cousin_engine._weighted_composite` sets `confidence = mass`, the summed
  weight of dimensions *present* on both sides of the comparison — a
  schema-shape constant. It carries no information about the arriving
  content, only about which fields that source's connector happens to
  populate.
- `cousin_engine._classify_relationship` opens with
  `if confidence < MIN_CONFIDENCE_FOR_CLASSIFICATION: return
  "ANOMALOUS_UNCLASSIFIED"` (threshold `0.6`) — evaluated **before** any
  distance between the arrival and a known anchor is examined.

Consequence: of the 100 verdicts, 80 were decided by the schema-completeness
gate (mass < 0.6, three of five sources structurally cannot reach it) and the
other 20 by the far-anchor density guard (G.4) after mass cleared 0.6.
**Zero of the 100 verdicts came from comparing the arriving thing to a known
thing.** No adapter change, embedding change, threshold retune, or anchor
acquisition changes this outcome, because the ceiling is set upstream of all
of them — by which fields an arrival can *ever* carry from a given source.

## 2. The provoked-vs-observed invariant collision

`cousin_engine` was built for the **provoked** world: a parent episode
against a mutated child, both expressed in one shared feature space by
construction. There, invariant I-6 — "a missing dimension is a failure,
never renormalize" — is correct: if the harness that produced the mutation
dropped a dimension, that is an instrument fault, and folding the gap into
the score would hide it.

Observed mode compares a sparse, heterogeneous **arrival** (whatever fields
its connector happened to populate) against a richly-labelled **anchor**
(hand-curated or corpus-derived, typically far more complete). Here a missing
dimension does not mean the harness failed — it means the arrival's source
does not observe that axis at all, or observes it under a form the anchor
did not. That is a partial view, not a fault.

These are opposite semantics carried by the same word ("missing dimension"),
and `cousin_engine.available()` was overloaded to mean both. That overload —
not a coverage or anchor deficiency — is the defect. The fix is not to
retrofit `cousin_engine`; it is to give observed mode its own grader that
encodes the correct invariant for its own world, and to leave the provoked
grader exactly as it is, because it is correct for what it does.

## 3. The five inversions

1. **Normalized distance.** `D = sum(w_i * d_i) / sum(w_i)` over the axes
   the two sides actually share. The provoked composite is deliberately
   unnormalized (`composite in [0, mass]`) so a partial match cannot look
   as good as a complete one within one comparison — correct there. In
   observed mode, leaving it unnormalized makes a sparse source's distance
   silently incomparable with a rich source's, which is exactly the defect
   that produced the three-constant confidence.
2. **Coverage is an annotation, never a gate.** The shared weight-mass is
   reported as `coverage` and only dampens `confidence`; it never refuses a
   classification (S1: annotate and degrade honestly, never deny use — N2
   restates this as a hard rule for this task).
3. **Directional and asymmetric.** An axis the arrival cannot speak to is
   `unobservable` — excluded from the distance and itemised, never charged
   as distance or as a penalty. The `attack` axis specifically is never
   required of the arrival: technique identity is what relating is meant to
   *produce*. Requiring it as an input to compute a relation is circular.
   It becomes `hypothesized_techniques`, an output taken from a
   technique-labelled anchor when the arrival relates closely enough to
   claim one.
4. **The delta is mandatory.** Every emitted cousin states what is shared,
   what diverges, and on which axis. A relation without a delta is a number
   with no content an analyst can act on.
5. **Divergence can raise interest.** Shared features are weighted by
   discriminative power (IDF over the anchor corpus, `DiscriminativeIndex`),
   so a rare motif held in common amid otherwise broad divergence scores as
   a strong cousin. Fixed global axis weights cannot express this — they
   only say how much an axis matters in general, not how much a specific
   shared token matters given how common it is across the corpus.

## 4. The bin split

`INSUFFICIENT_VIEW` ("we could not compute a relation at all — no anchor
shares a single dimension with the arrival") is kept separate from
`NOVEL_NOTABLE` ("we computed a relation, it matches nothing well, but the
arrival is positively distinctive"). Collapsing the two into one
`ANOMALOUS_UNCLASSIFIED` label — as the provoked-derived observed path did —
hides an instrument failure (we cannot see enough to say anything) inside
what reads as a discovery (we saw something novel). `NOVEL_NOTABLE` requires
a positive distinctiveness signal computed from the arrival's own salience;
mere absence of a match can never produce it on its own, which is the
anti-inflation property the C.1 tests pin (`test_novel_notable_requires_positive_distinctiveness`).

## 5. Residual risks, carried openly

- **Anchor coverage still bounds recognition.** Removing the gate turns this
  from a hidden assumption into a *measurable* claim: every run must report
  the unrelatable rate (arrivals that reach `INSUFFICIENT_VIEW`) and the
  anchor-density map, rather than let a gate quietly absorb the gap.
- **Thresholds are judgement.** `COUSIN_MAX_DISTANCE`,
  `NOVELTY_MIN_DISTINCTIVENESS`, and the advisory label bands are recorded on
  every relation. Changing any of them is a re-baseline, to be called out as
  such, not a silent tuning pass.
- **Salience-weighted Jaccard is still a lexical instrument.** It is a
  comparable and honest one — which the mass-gated composite was not — but a
  genuine cross-vocabulary bridge (e.g. CloudTrail `AssumeRole` as a cousin
  of Windows token theft, sharing no literal tokens at all) needs a shared
  behavioural embedding space. That is deliberately out of scope here: C.6's
  L3 cross-space recovery rate is the number that will justify and size that
  next task. An embedding swapped in under an ungraded, unmeasurable
  instrument is what produced the three prior inconclusive passes this task
  supersedes; measure first, then decide whether to invest in an embedding.
- **Guards can themselves degenerate.** Every guard in this task ships with
  a seeded-violation test (N4) — a guard that cannot be made to fail on a
  constructed violation is treated as a defect, not as evidence of
  correctness.

## 6. What this document is not

This is the design correction, not a summary of work already done. Phases
C.1-C.8 implement the module (`cousin_relation.py`), rewire observed mode to
use it, correct measurement/degeneracy to read the true quantity instead of
the schema-shape constant, fix the adjacent seed-scope confound, add CI
invariants, build a falsification instrument with INVALID conditions (N5),
run the live verification, and reconcile the fact-units and the M.3 record
(annotated with errata, never rewritten) that this document supersedes the
reading of.
