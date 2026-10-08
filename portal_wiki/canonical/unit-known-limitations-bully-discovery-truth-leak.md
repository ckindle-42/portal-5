---
id: unit-known-limitations-bully-discovery-truth-leak
kind: what
title: "KNOWN_LIMITATIONS — Bully discovery scored its own answer key; blind, it rarely finds cross-source cousins"
sources:
- type: code
  path: portal/modules/security/core/bully/discovery_bench.py
- type: code
  path: portal/modules/security/core/bully/cousin_engine.py
- type: code
  path: tests/security/bully/_discovery_fixtures.py
claims: []
confidence: high
tags:
- docs
- security
- bully
---

### Bully discovery scored its own answer key; blind, it rarely finds cross-source cousins (OPEN)

- **ID**: BULLY-DISCOVERY-TRUTH-LEAK-001
- **Status**: OPEN. The leak is fixed (2026-10-08). The engine weakness it was hiding is open,
  pending a specimen corpus that carries field values.
- **Leak**: `independent_truth_related` judges a discovery correct when probe and reference share
  a `data.yml` ATT&CK technique or a scenario family. Both of those labels sat in the probe's
  `engine_view.telemetry_view` (`attack_mappings`, `context_topology.family`, which is
  `attack:<technique>` on 672 of 988 probes), and the engine read them through its ATT&CK and
  family retrieval axes and its `attack` distance channel. The module docstring said the engine
  "never touches" them. `discovery_bench.probe_signature` now strips both before the engine
  sees the probe.
- **Effect on reported numbers**: on SPECIMEN_CORPUS_V2, every discovery precision before
  2026-10-08 is inflated: 0.72 with the leak, about 4–6% related across all 988 probes once
  blind (chance is about 1%). The leak also reversed the EG2 embedder comparison. Leaky: Qwen3
  33/46 vs EG2 26/46 (p=0.039). Blind: Qwen3 43/988 vs EG2 63/988 (paired 17 vs 37, p=0.009).
- **Open weakness**: the composite distance gives `telemetry` (source shape, 0.20) and
  `context` (0.10) as much pull as `behavior` (0.30), so a same-log-source record beats a
  cross-source cousin even when the cousin shares the behavior. Blind, 965–981 of 988 chosen
  references are same-source. The six SA2 fixture tests that assert a cross-class discovery are
  marked strict-xfail against this entry, and they will pass when the engine finds cousins on
  behavior alone.
- **Data limit**: SPECIMEN_CORPUS_V2 carries no field values (`artifacts.observed_fields` is
  empty): field names and event codes only. Re-capturing specimens with values is the next step,
  before any engine re-weighting.

## Why

A scorer that shares its inputs with the thing it scores stops measuring the engine and measures
the overlap. Here the embedder's job became string-matching the answer key, which is why the
leaky numbers looked strong and why they picked the wrong embedder. Recording the blind numbers
and pinning the cross-class tests as strict-xfail keeps the real gap visible until a corpus with
field values gives the engine actual behavior to compare.
