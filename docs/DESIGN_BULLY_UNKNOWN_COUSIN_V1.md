# DESIGN_BULLY_UNKNOWN_COUSIN_V1

> **2026-08-20 — wired into the loop.** The organ this doc designs is no longer
> a standalone script: it is wired into the orchestrator via
> `bully/loop_grader.py`, which the orchestrator's `_analyzing` calls in place
> of `cousin_engine.grade`. The flat distance metric this doc's grader used to
> decide `EXACT`/`SIMILAR` lacked an axis for *how robust* a match is; that axis
> is pyramid level (`bully/pyramid.py`) — a match is now decided level-first
> (does it hold at the L3 behavioural choke point, or only at L1/L2 evadable
> detail) and distance refines within that level. See
> `DESIGN_BULLY_LOOP_REINTEGRATION_V1.md` for the full reintegration design.

Full-scope design doc for `TASK_BULLY_UNKNOWN_COUSIN_V1`. Companion to
`BULLY_RELATE_INVESTIGATE_RUN_M3_V1.md` and `BULLY_COUSIN_RELATION_RUN_C7_V1.md`,
both of which stay in the repo as the honest record of what each prior pass
actually measured.

## The thesis, and what it forbids

We are not building a system that guards against a defined list of known
things. Detection content, IOC lists and signature matching already do that
well, and they are the floor. The product is **finding things that are not
known, which are the same as or similar to something we know, and raising
that as a concern an analyst can act on.**

"Same" does not mean "on the list." An artifact set can be behaviourally the
*same* as a known type while being an entirely unknown *instance* -- same
shape, new tooling, new vocabulary, never-before-seen indicators. `EXACT`
and `SIMILAR` describe the relation to a known **type**; they say nothing
about whether the **instance** was known. Conflating the two is what let the
last three passes each report a healthy-looking number while the product
capability underneath did not exist.

Consequently, accuracy against the legend's technique list is the wrong
headline measurement -- it measures matching, which is the floor, not the
product. The product test is leave-one-family-out (T.4): remove a technique
family from the type library entirely so the system genuinely does not know
it, then ask whether its instances still raise concern as same-or-similar to
what remains.

## Why the last three passes each missed

Each fixed the layer it was looking at while the layer beneath was wrong:
the embedding bake-off assumed a valid corpus; RELATE assumed valid grading;
COUSIN_RELATION (C.1-C.8) assumed the right unit of analysis -- its five
inversions are correct and carry forward unchanged, they were simply applied
to the wrong thing.

The concrete defect inherited from C.7: `_signature_from_scope` makes one
`build_signature` call per scope, flattening every record in the window
into a single `action_sequence[:32]` token bag. The individual level does
not exist, and the combination level is reduced to vocabulary -- discarding
co-occurrence, ordering and entity linkage, which is precisely the signal
that survives when an adversary changes tooling. `event_graph` is declared
in `signatures.py` but never populated anywhere on the observed path.

## The unit of analysis: structural grouping, not subset enumeration

The primitive: for the artifacts present in a window of time, do they --
individually and in combination -- look like a known type: exactly,
similarly, or not at all.

An arbitrary k-subset of a window has no operational meaning and there are
`2^n` of them; no analyst can act on one. The gradeable units are the ones
the data's own structure produces -- the same ones an analyst would actually
pivot to:

- `L1_ARTIFACT` -- one artifact alone.
- `L2_ENTITY` -- every artifact touching one identity/host/key.
- `L3_CHAIN` -- a connected component of the artifact graph: artifacts
  linked by shared entity, causal parent, or tight temporal adjacency
  (adjacency only ever reinforces an existing entity link -- a bare
  temporal edge chains an entire steady stream into one component and
  silently collapses L3 into L4).
- `L4_WINDOW` -- the whole window, the maximal case.

This is `O(n*k)` units, not `O(2^n)`. `artifact_graph.py` (U.1) builds this
graph and enumerates the units; `U.2` splits every unit's signature into a
`structural_signature` (shape: ordered action classes, edge-type multiset,
entity-role pattern, degree profile) and `vocabulary` (literal tokens),
deliberately kept in separate channels so a combination can be matched on
shape even when every literal token differs -- vocabulary is what an
adversary changes, shape is what survives.

The flagship finding this unlocks: a combination-level cousin where every
individual artifact is unremarkable. That capability is unreachable under
the one-signature-per-scope design and does not exist prior to this task.

### The verb-to-class seam (U.3)

`_action_class` maps an action verb to a coarse behavioural class via a
hand-written substring table. This is the known weak point of the whole
design: shape-matching across sources only works if two different verbs for
the same behaviour map to the same class, and a substring table cannot do
that in general -- it fails the moment a source uses vocabulary its author
did not anticipate (`Add-LocalGroupMember` is an escalation; no substring
here says so, while `AttachUserPolicy` for the equivalent AWS action does
match). U.3 puts this behind an injectable `ActionClassifier` protocol with
the deterministic table as the default, so the eventual swap to a learned
classifier is measurable in isolation rather than smuggled in under a grader
that cannot yet measure its effect. M.1's cross-vocabulary ladder rung is
the number that sizes that future work; this task does not attempt it.

## Known types and the normal baseline are different objects

- **Known types** (benign and malicious, one mechanism -- `anchors.py`
  N.1) are patterns you can *match*. Malice is a property of the matched
  type, never a separate pipeline. Known-benign types make "this is exactly
  a known benign type" sayable, which turns `BENIGN_CLOSE` write-back from
  dead wiring (L.1) into live suppression.
- **The normal baseline** (`baseline.py`, N.2) is a frequency model over
  unit-level features, fitted from observed data -- never from the type
  library -- that you can only *score against*. You cannot match a
  distribution; you cannot score against a pattern set.

Conflating them produced C.7's 79% `NOVEL_NOTABLE`: with no baseline, every
ordinary record was reported as notable novelty. Worse,
`build_discriminative_index` computed IDF over the anchor corpus only --
rarity *among attacks* -- so junk was maximally "distinctive" and the
novelty signal was maximised by exactly the data it should have ignored.
N.3 replaces that IDF with a likelihood ratio, `P(feature | known types) /
P(feature | baseline)`, which is the correct object for "is this
distinctive of attacks specifically, or just rare."

## The outcome space

| type relation | baseline | outcome | disposition |
|---|---|---|---|
| EXACT to malicious type, known instance | — | `KNOWN_INSTANCE` | floor; existing detection owns it |
| EXACT to malicious type, unknown instance | — | `UNKNOWN_SAME` | **concern** |
| SIMILAR to malicious type | — | `COUSIN` | **concern** |
| EXACT/SIMILAR to benign type | — | `RECOGNIZED_NORMAL` | suppress |
| none | unremarkable | `NORMAL` | silent |
| none | remarkable | `NOVEL` | **concern** |
| uncomputable | — | `INSUFFICIENT_VIEW` | instrument finding, never a discovery |

Rows 5-6 are impossible without the baseline; row 4 is impossible without
benign types. `KNOWN_INSTANCE` is deliberately the least interesting row
and must never headline a report or outrank a `COUSIN`/`NOVEL` row in
report ordering (P1, M.2 invariant #4).

## The ConcernBrief

The output object is a concern, not a verdict. Every concern-raising outcome
(`UNKNOWN_SAME`, `COUSIN`, `NOVEL`) emits a `ConcernBrief`: the specific
artifacts, entity and timespan; what it resembles and how (shared /
diverging / axis of divergence, on both shape and vocabulary channels); why
it is concerning (salience against baseline); honest confidence; and what
could not be seen. A verdict label with no brief is not actionable and does
not ship (M.2 invariant #3).

## Grading (V.1-V.2)

Every `GradeableUnit` is graded against every known type -> `EXACT` /
`SIMILAR` / `NOT_AT_ALL`, on both channels, each with normalized distance
and a mandatory delta. C.1's five inversions carry forward unchanged:
normalized distance over shared axes, coverage as annotation never a gate,
directional/asymmetric axes, mandatory delta, divergence-can-raise-interest.
The subject of grading becomes a `GradeableUnit` rather than a flattened
per-scope signature. The report keeps the smallest matching unit -- the
most specific claim available -- when a unit at more than one level matches
the same type.

## Measurement (T.1-T.4)

- **T.1** binds the sealed manifest legend to the arriving side, on the
  grading plane only. The hard wall holds: the grader itself never receives
  lineage or technique tags. Before this, `"scored"` meant "reachable via
  `ranked_external_cousins`", not "correct" -- `ground_truth` never appeared
  in the run script.
- **T.2** splits datasets into type-library and evaluation halves so no
  evaluation artifact originates from a dataset that contributed a type.
  Without this, attack_data seeds drawn from the same root that built the
  anchors are already "in the library" before evaluation starts.
- **T.3** reports precision/recall per unit level and per outcome class
  against the legend -- the floor metric, `KNOWN_INSTANCE` labelled
  explicitly as such (P1).
- **T.4 is the headline.** Leave-one-family-out: for >= 8 technique
  families, remove every type of that family from the library, refit the
  baseline, re-run evaluation artifacts of that family, and measure what
  fraction still raise a concern with a brief naming a plausibly-related
  surviving type. `unknown_cousin_recall` is the product number.
  `concern_precision` over benign held-out data is reported beside it.
  Controls: shuffled type labels must collapse recall; a benign held-out
  family must not raise concern at the same rate; either failing marks the
  report INVALID. The full-library number is published alongside --
  full-library >> leave-one-out states plainly that the system is a
  matcher, not smoothed away.

## Suppression goes live (L.1)

Today write-back only ever emits `ESCALATE`/`NO_RELATION`, so no benign
type is ever created and `compounding.should_escalate`'s suppression path
is dead wiring. L.1 writes outcomes back as typed anchors with malice
carried (`BENIGN_CLOSE` -> `benign_pattern`), so a repeated benign-closed
unit is suppressed on its second appearance while a malicious cousin never
is. G.2 provenance tiers and depth caps carry over unchanged.

## The verb-to-class seam as the known weak point

Restated because it is the single largest source of under-recovery this
task ships with open: shape-matching across genuinely disjoint vocabularies
depends entirely on the action classifier bridging them correctly. The
deterministic substring table is a floor, not a solution. M.1's
cross-vocabulary ladder rung measures the gap directly rather than papering
over it, and that number is published as-is in M.3.

## Residual risks, carried openly

- The verb-to-class seam is deliberately unlearned in this task; until a
  learned classifier lands, shape-matching across genuinely disjoint
  vocabularies will under-recover.
- The normal baseline can be poisoned by an adversary present throughout
  the fitting window; fit from held-out-clean data where the legend allows,
  and report the assumption made.
- Structural grouping can miss a combination the graph does not connect --
  an attack spread across entities with no shared key and no causal link.
  The unconnected-artifact rate is reported every run as the honest bound
  on this approach.
- Thresholds (`COUSIN_MAX_DISTANCE`, `NOVELTY_MIN_DISTINCTIVENESS`, the
  baseline's remarkability cutoff) are judgement calls, recorded on every
  relation; changing one is a re-baseline, not a silent tune.
- Leave-one-family-out is optimistic where families share technique
  lineage; M.3 reports which surviving family carried each recovery so
  lineage leakage stays visible rather than inflating the headline number.

## What this task does not touch

`cousin_engine.py` and `relation.py` (the provoked-path grader and its
invariant, I-6) are untouched -- observed mode remains a separate grader for
the reasons `cousin_relation.py`'s module docstring already states. COLD
throughout: no training, no model calls in the verification run.
