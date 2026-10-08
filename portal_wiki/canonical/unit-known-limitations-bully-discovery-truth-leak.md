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
- type: code
  path: portal/modules/security/core/bully/behavior_values.py
- type: code
  path: scripts/build_specimen_corpus_v3.py
claims: []
confidence: high
tags:
- docs
- security
- bully
---

### Bully discovery scored its own answer key; blind, it rarely finds cross-source cousins (OPEN)

- **ID**: BULLY-DISCOVERY-TRUTH-LEAK-001
- **Status**: OPEN. The leak and the value-less corpus are fixed (2026-10-08). The engine's
  source-dominated weighting is open.
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
- **Data limit (fixed 2026-10-08)**: SPECIMEN_CORPUS_V2 kept no field values (`observed_fields`
  only) and only the first 32 events of each dataset. `bully.behavior_values` now extracts the
  behavior-bearing values (process lineage, command lines, files, registry, services, syscalls,
  URIs, identity events), masking ids, hashes, IPs, generated names and lab host names, and every
  adapter emits them as `artifacts.behavior_values`, which leads `semantic_query` as `content:`.
  `scripts/build_specimen_corpus_v3.py` rebuilt the corpus (SPECIMEN_CORPUS_V3) from the source
  datasets without a SIEM query. Blind, related references over 988 probes went from
  43/66/99 (Qwen3/EG2/TF-IDF, V2) to 139/154/148 (paired gain p≈0 for every arm); masking lab
  identity changes none of it (p≥0.29), and 10–22 hits per arm are evidence twins (one log
  published under two techniques). A hand-checked sample of the rest is genuinely related
  (plink tunnels, gdrive exfiltration across OSes, sudo GTFOBins, `[adsisearcher]` ≈ `Get-ADGroup`).
- **Still open**: cross-source discovery is 0–1 of 988 in every arm, because the composite's
  `telemetry` + `context` weight outranks behavior across log sources; the engine weights and
  the per-space thresholds (`embedding_spaces.derive_thresholds` only shifts upward, so every
  space inherits the incumbent's) were set before any of this and are the next revisit.
## Why

A scorer that shares its inputs with the thing it scores stops measuring the engine and measures
the overlap. Here the embedder's job became string-matching the answer key, which is why the
leaky numbers looked strong and why they picked the wrong embedder. Recording the blind numbers
and pinning the cross-class tests as strict-xfail keeps the real gap visible until a corpus with
field values gives the engine actual behavior to compare.
