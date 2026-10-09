---
id: D-T3-READER
question: Does a reasoning-capable reader improve truth recall at workload B over the deterministic top-B control?
stage: raised
why_not_binding: "the reader is the workload lever: it moves the budget-limited frontier rather than one stage's loss"
arms:
  - no_reader
  - "single:auto-security::security-council-granite41-30b"
  - "single:hf.co/unsloth/Qwen3.8-27B-GGUF:Q4_K_M-ctx96k"
  - "single:hf.co/unsloth/Qwen3.6-35B-A3B-GGUF:UD-Q4_K_XL-ctx96k"
  - "single:auto-security::security-expert-foundation-sec-8b"
metric: recall of truth items at workload B by paired exact McNemar; also report false-raise per 1,000 benign units and reader receipts.
adopt_if: paired exact McNemar p < 0.05 in favour at B, no control-favouring regression at raised for p < 0.10, all known-answer and report-validator gates pass, every kept claim resolves, the reasoning probe passes, and R times measured p95 concern latency fits the window duration.
anti_goals:
  - tune no threshold, weight, cutoff, or prompt against the headline metric
  - run no attack, chain, target tool, or emulation operation
  - infer alpha_open, workload B, or missing truth from an unmeasured slice
status: PREREGISTERED
---
The control is the deterministic `no_reader` arm. Each configured T3 candidate is represented as a single-reader arm; candidates failing the reasoning capability probe are excluded from adoption. Reader arms would open the funnel to alpha_open, read the top-R candidates by p, keep `something` and `unsure`, drop `nothing`, append unread candidates by p, and take top-B. R is computed from the measured p95 latency per concern and the evaluation window duration.
