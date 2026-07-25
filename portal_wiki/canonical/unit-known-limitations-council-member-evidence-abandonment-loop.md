---
id: unit-known-limitations-council-member-evidence-abandonment-loop
kind: what
title: "KNOWN_LIMITATIONS — Council Member Evidence-Abandonment Loop (hf.co/HeYujie/Qwen3.5-27B-abliterated-GGUF)"
sources:
- type: code
  path: portal/modules/security/core/blue_orchestrate.py
  commit: bb814221
  section: _COUNCIL_UNFIT_MODELS
- type: code
  path: portal/modules/security/core/corpus_replay_bench.py
  commit: bb814221
last_generated_commit: 89885284
confidence: high
tags:
- docs
- security
created_at: 1784952000.0
updated_at: 1784952000.0
---

- **ID**: P5-SEC-COUNCIL-001
- **Description**: Found live 2026-07-25 during the corpus-replay Council of Agreement
  validation bench (real BOTS/ATT&CK corpus telemetry, `T1558.003` Kerberoasting subset —
  `EventCode=4769`, `TicketEncryptionType=0x17` across multiple service accounts). As a
  council member, `hf.co/HeYujie/Qwen3.5-27B-abliterated-GGUF:Q4_K_M` abandoned evidence
  grounding entirely and spiraled into an ~8000-token self-doubting loop trying to
  re-derive MITRE ATT&CK technique ID numbering from training-data recall ("Wait...
  actually T1558 is... no wait, let me check v13/v14/v15 mappings...") instead of reading
  the telemetry it was actually given. It never emitted a verdict — the council still
  reached the correct `CONFIRMED T1558.003` via the other member (`granite4.1:30b`) and
  the lead hunter, but this member's vote slot was entirely wasted.
- **Impact**: In a council roster, a wasted vote slot changes the effective quorum
  fraction — with a 2-member roster and one member failing to vote, `compute_agreement`
  effectively degrades to a single-model decision without the quorum's intended
  cross-check. This is worse in council mode than in a solo orchestrated run, because the
  operator configuring `--council-models` may reasonably assume every named model
  contributes a real, evidence-grounded vote.
- **Operator action**: `blue_orchestrate._COUNCIL_UNFIT_MODELS` is a standing, data-driven
  list (not a hard block — see its docstring) that `_warn_if_council_unfit_models` checks
  against every `_run_council` call, printing a warning to stderr if a roster includes a
  known-unfit model. `portal/modules/security/core/corpus_replay_bench.py`'s
  `COUNCIL_MODELS` roster is filtered against this list. Before adding a new model to a
  council roster, sanity-check it against a real evidence-grounded scenario first (not
  just a tool-call/format check) — a model can pass basic capability probes and still
  fail this specific "reason honestly from the evidence in front of you, don't recall
  from memory" failure mode.
