---
id: D-T3-PANEL
question: Does the configured three-seat panel improve truth recall over the winning single reader at the same workload budget?
stage: raised
why_not_binding: "the reader is the workload lever: it moves the budget-limited frontier rather than one stage's loss"
arms:
  - winning_single_reader
  - three_seat_panel
metric: recall of truth items at workload B by paired exact McNemar, with panel verdict, dissent, grounding, tokens, and p95 concern latency reported.
adopt_if: paired exact McNemar p < 0.05 in favour at B, no control-favouring regression at raised for p < 0.10, all known-answer and report-validator gates pass, every kept claim resolves, every panel seat passes its reasoning probe, and measured R times p95 concern latency fits the window duration.
anti_goals:
  - tune no threshold, weight, cutoff, or prompt against the headline metric
  - run no attack, chain, target tool, or emulation operation
  - infer a winning single reader or panel consensus from unmeasured truth slices
status: PREREGISTERED
---
The candidate uses the three-seat roster from `resolve_council_models()` in `bully/config.py`, which reads `hunt.yaml` and `config/portal.yaml` only. The roster snapshot is `auto-security::security-council-granite41-30b`, `auto-security::security-council-mistral-small32-24b`, and `auto-security::security-council-qwen36-27b`, aggregated with `panel.panel_verdict`. The single-reader control is selected by D-T3-READER; neither arm runs without alpha_open, eligible truth slices, and workload B.
