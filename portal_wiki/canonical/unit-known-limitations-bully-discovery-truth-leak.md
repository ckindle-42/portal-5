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

### Bully discovery scored its own answer key; blind, it rarely finds cross-source cousins (NARROWED)

- **ID**: BULLY-DISCOVERY-TRUTH-LEAK-001
- **Status**: NARROWED (2026-10-08). The leak is fixed, the value-less corpus is fixed, the
  source-dominated composite weighting is fixed (cousin-v2, B1; unit-mass cousin-v3, F1), and the thresholds are re-fit
  to the adopted space (B1.4). Still open: the retrieval axes surface a truth-related candidate
  for only 430/988 probes.
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
- **Weighting (fixed 2026-10-08, B1)**: the composite gave `telemetry` (0.20) + `context` (0.10)
  as much pull as `behavior` (0.30), so a same-log-source record beat a cross-source cousin that
  shared the behavior — 965–981 of 988 chosen references were same-source, cross-source
  discovery 1/988. cousin-v2 moves the mass to `behavior` (0.40) + `semantic` (0.40)
  (`telemetry`/`context` 0.10 each) and computes the behavior channel on
  `artifacts.behavior_values` value terms (Jaccard) with an action-sequence fallback for
  signatures that predate the values capture. Measured on the same 988 probes over the same
  seeded EG2 projection (`reports/bully_b1/20261008T195439Z`, paired exact McNemar vs v1):
  related 154 -> 241 (p<1e-4), cross-source related 1 -> 16 (p=6e-5). Corrected 2026-10-09
  (review F1, `reports/bully_b1/20261009T010139Z`): the v2 proportions summed to 1.15, not 1.00,
  so `confidence` could exceed 1 and the 0.6 classification gate was loosened; v2's
  "0 ANOMALOUS" rested on that. cousin-v3 divides v2 by its total — identical ranking (related
  240 vs 241, cross-source 16 vs 16, paired p=1.0); the 90 chosen pairs with semantic and attack
  both absent (present mass 0.52) now abstain as ANOMALOUS, and 89 of them were not
  truth-related. Twins
  (identical evidence under two labels: identical event streams or identical value sets) are
  reported separately, 97 of the 241; a hand-checked sample of the cross-source hits is genuine
  (gacutil IIS dll install, appcmd log-disable, netsh firewall allow, WMI account manipulation,
  certutil -backupdb — each seen through two log sources). The five SA2 fixture tests asserting
  a cross-class discovery run unmarked since this change; the sixth (`test_all_p74_style_controls`)
  stays strict-xfail on the identity control's frozen `same_max_distance` scale, not on
  discovery (B1.4 re-derives it).
- **Instrumentation (B1.1)**: per probe, the chosen reference's channel decomposition vs the best
  truth-related candidate's (`reports/bully_b1/20261008T195439Z/b1_instrumentation.json`):
  154 chosen truth-related, 276 probes retrieved a truth-related candidate but outranked it
  (best-truth rank 1–6 for 237 of them), 558 never retrieved one — retrieval-axis coverage, not
  grading, is now the binding constraint. Cross-class truth candidates in the candidate set have
  near-identical semantic distance to the chosen same-source records (0.069 vs 0.061) while the
  action-sequence channel differs hugely (0.849 vs 0.249) — the values channel is what carries
  them.
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
- **Thresholds (re-fit 2026-10-08, B1.4; rescaled 2026-10-09, F1)**: `same_max_distance` 0.05 -> 0.063
  (v2 scale) -> 0.055 under cousin-v3's unit-mass weights (composites scale by 1/1.15; measured
  identity max 0.0621 -> 0.0540; `bully-cousin-thresholds-v3`) — under v2 weights
  the true self-pair composite carries the truth-strip's context asymmetry (~0.033; the probe's
  `family` is stripped, the indexed record keeps it) and measured 0.0387 median / 0.0621 max
  over 100 real probes, so the frozen 0.05 failed 2/100 identity checks. On the same 988 probes
  the raise leaves ranking untouched (241 related) and moves 4 chosen pairs into the SAME band
  (DISCOVERY -> REGRESSION). The reference constants in `embedding_spaces` are re-measured on
  EG2+V3 (self 0 / near 0.1336 / far 0.1630); the upward-only clamp stays — EG2+V3 sits above
  the retired harrier constants on every band, so the clamp never binds for the primary space
  and remains the anti-tuning guard for tighter future spaces
  (`reports/bully_b1/20261008T195439Z/THRESHOLDS_B1_4.md`).
- **Thresholds T1 check (2026-10-08, TASK_BULLY_V3_THRESHOLD_VALIDATION_V1)**: `same_max_distance`
  stays 0.055 (`bully-cousin-thresholds-v3`). With `family` removed from both sides, the self-pair
  composite is max 0.0250 (p95 0.0142), and 0.026 would be the right band in isolation. But the blind
  path (`probe_signature`) keeps the truth-strip asymmetry, so 68/100 blind self-pairs compose above
  0.026 and fail the identity control. Lowering the band is valid only after the blind path is
  symmetric. Evidence: `reports/bully_v3_threshold_validation/t1_same_band/t1_summary.json`.
  SAME-band precision is ~26% at every cut-off; 43 of the 45 not-related SAME pairs at 0.026 are
  evidence twins, so the false-SAME rate is label noise, not the threshold.
- **Still open**: 558/988 probes retrieve no truth-related candidate at all (the semantic axis's
  k=8 pool and the family axis, which is dead for probes because the probe's family is stripped
  to its source-class fallback, cap cross-source reach).
## Why

A scorer that shares its inputs with the thing it scores stops measuring the engine and measures
the overlap. Here the embedder's job became string-matching the answer key, which is why the
leaky numbers looked strong and why they picked the wrong embedder. Recording the blind numbers
and pinning the cross-class tests as strict-xfail keeps the real gap visible until a corpus with
field values gives the engine actual behavior to compare.
