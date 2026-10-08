# B1 — Bully engine weighting variants, paired on the EG2 cutover projection

TASK_EG2_FOLLOWUPS_AND_BULLY_ENGINE_V1 B1, 2026-10-08. Corpus SPECIMEN_CORPUS_V3 final
(`specimen_corpus_v3_final.json`), 988 blind probes. One retrieval pass per probe over the
cutover's seeded arm-d-sim projection (`/Volumes/data01/portal5_scratch_eg2/bully/arm-d-sim`,
backed up to `arm-d-sim_bak_20261008_b1`), every variant graded on that identical candidate set.
Harness: `scripts/bully_b1_engine_variants.py`; the base variant reproduces the cutover's
`bully_projection` primary exactly (154 related, run `20261008T164221Z`).

## Verdict per variant (paired exact McNemar vs base)

| variant | related | cross-source | twins | ANOMALOUS | p (related) | p (cross) |
|---|---|---|---|---|---|---|
| base (v1 weights, action-sequence) | 154 | 1 | 87 | 0 | — | — |
| down_tele_ctx (0.05/0.05, mass 0.40) | 159 | 1 | 90 | 100 | 0.180 | 1.0 |
| behavior_values (strict, mass drops) | 177 | 4 | 94 | 261 | 0.058 | 0.25 |
| mass_preserving_down | 160 | 1 | 90 | 0 | 0.070 | 1.0 |
| down_plus_values (mass 0.40) | 207 | 9 | 86 | 292 | 7e-5 | 0.0078 |
| values_mass_preserving (strict) | 200 | 9 | 88 | 204 | 0.0004 | 0.0078 |
| values_fallback_base (v1 weights) | 215 | 6 | 113 | 0 | ~0 | 0.0625 |
| **values_fallback_mass_preserving (ADOPTED)** | **241** | **16** | 97 | **0** | **<1e-4** | **6e-5** |

Adopted = weights {behavior 0.40, semantic 0.40, telemetry 0.10, context 0.10, attack 0.15} +
behavior channel on `artifacts.behavior_values` value-term Jaccard with an action-sequence
fallback. Meets the gate: not worse on all-probes related (better, p<1e-4), better on
cross-source (1 -> 16, p=6e-5), classification ladder intact (0 ANOMALOUS — the raw down-weight
variants push total mass to 0.40, under MIN_CONFIDENCE_FOR_CLASSIFICATION, and classify
everything ANOMALOUS regardless of ranking — rejected for that reason).

## Instrumentation (B1.1, `b1_instrumentation.json`)

* 154 probes choose a truth-related reference; 276 retrieve a truth-related candidate but
  outrank it (best-truth rank 1–6 for 237); 558 retrieve none — retrieval coverage, not
  grading, is the next binding constraint.
* Chosen same-source mean decomposition: behavior 0.249, telemetry 0.144, semantic 0.061,
  context 0.232. Best cross-class truth candidate in set (n=33): behavior 0.849, telemetry
  0.879, semantic 0.069, context 0.717 — the embedding already sees the cousin; the
  action-sequence channel cannot.

## Hand-check

The 15 new cross-source hits were inspected against raw corpus evidence; five sampled in the
commit message are genuine shared behavior through two log sources (gacutil IIS dll install,
appcmd log-disable, netsh firewall allow, WMI T1098 account manipulation, certutil -backupdb).

Twins use an explicit operational rule: identical raw event streams OR identical masked value
sets (broader than the cutover's 10–22 count, which used a different rule).
