---
id: D-T3-CHALLENGER
question: Does an independently seated reasoning model improve the reader's challenge without reducing truth recall at workload B?
stage: raised
why_not_binding: "the reader is the workload lever: it moves the budget-limited frontier rather than one stage's loss"
arms:
  - same_model_challenger
  - different_seat_challenger
metric: recall of truth items at workload B by paired exact McNemar, with grounded challenger stances and latency reported.
adopt_if: paired exact McNemar p < 0.05 in favour at B, no control-favouring regression at raised for p < 0.10, all known-answer and report-validator gates pass, every kept claim resolves, and both challenger models pass reasoning probes.
anti_goals:
  - tune no threshold, weight, cutoff, or prompt against the headline metric
  - run no attack, chain, target tool, or emulation operation
  - select a winning single reader without a measured reader comparison
status: PREREGISTERED
---
The control assigns the same model to read and challenge. The candidate assigns the challenger to a different configured seat whose reasoning probe passes; the current roster comes from `resolve_council_models()` in `bully/config.py`. The comparison is not executable until the truth slices and workload B are available and a single-reader model has been selected by the reader decision.
