# Blue Orchestration V5A Attribution — 2026-07-25

## Measurement boundary

This eval-only instrument selected each cell's labeled technique, loaded that technique's read-only discriminator data from `spl_detections.yaml`, and searched only the retriever `content` persisted in the cell trace. It did not query fresh corpus data and did not inspect model prose when deciding PRESENT/ABSENT.

Checkpoint SHA-256: `8bfb406544a903f11def43ecb3c65e4ac66149671ef032e6b8fb507eb1bcbad0`.

## World A / World B rollup

| Arm | A: evidence-present miss | B: honest negative | Honest anomaly | I: unscorable | M: misattribution | True positive | Cells |
|---|---:|---:|---:|---:|---:|---:|---:|
| `council_strong` | 5 | 5 | 6 | 0 | 0 | 1 | 17 |
| `strong_full_v3` | 2 | 6 | 6 | 0 | 0 | 3 | 17 |
| `weak_mentor_validation` | 6 | 4 | 5 | 1 | 1 | 0 | 17 |

V5B routes on the promotion-relevant `strong_full_v3` arm. Its observed branch inputs are **A=2, B=6, I=0, M=0**. HONEST_ANOMALY is reported separately because discovery is not punished (I8) and V5B's rule defines B specifically as HONEST_NEGATIVE.

## Per-technique attribution

| Arm | Expected | Verdict / reported IDs | Oracle | Attribution | Matched discriminator |
|---|---|---|---|---|---|
| `council_strong` | `T1003.003` | CONFIRMED / T1003.003 | PRESENT | TRUE_POSITIVE | NewProcessName=*ntdsutil*, ntdsutil |
| `council_strong` | `T1047` | RULED_OUT / — | PRESENT | FALSE_NEGATIVE | EventCode=4688, NewProcessName=*WmiPrvSE* |
| `council_strong` | `T1053.005` | RULED_OUT / — | ABSENT | HONEST_NEGATIVE | — |
| `council_strong` | `T1078` | ANOMALOUS_UNCLASSIFIED / — | ABSENT | HONEST_ANOMALY | — |
| `council_strong` | `T1083` | ANOMALOUS_UNCLASSIFIED / — | ABSENT | HONEST_ANOMALY | — |
| `council_strong` | `T1110.003` | ANOMALOUS_UNCLASSIFIED / — | ABSENT | HONEST_ANOMALY | — |
| `council_strong` | `T1189` | RULED_OUT / — | ABSENT | HONEST_NEGATIVE | — |
| `council_strong` | `T1190` | ANOMALOUS_UNCLASSIFIED / — | ABSENT | HONEST_ANOMALY | — |
| `council_strong` | `T1550.002` | RULED_OUT / — | PRESENT | FALSE_NEGATIVE | EventCode=4624, LogonType=3, AuthenticationPackageName=NTLM |
| `council_strong` | `T1552` | ANOMALOUS_UNCLASSIFIED / — | PRESENT | EVIDENCE_PRESENT_MISS | .env, password= |
| `council_strong` | `T1552.005` | ANOMALOUS_UNCLASSIFIED / — | ABSENT | HONEST_ANOMALY | — |
| `council_strong` | `T1557` | RULED_OUT / T1557 | PRESENT | FALSE_NEGATIVE | EventCode=4624, LogonType=3 |
| `council_strong` | `T1557.001` | RULED_OUT / — | ABSENT | HONEST_NEGATIVE | — |
| `council_strong` | `T1558.003` | RULED_OUT / — | ABSENT | HONEST_NEGATIVE | — |
| `council_strong` | `T1558.004` | RULED_OUT / — | ABSENT | HONEST_NEGATIVE | — |
| `council_strong` | `T1595` | RULED_OUT / — | PRESENT | FALSE_NEGATIVE | status=404 |
| `council_strong` | `T1611` | ANOMALOUS_UNCLASSIFIED / — | ABSENT | HONEST_ANOMALY | — |
| `strong_full_v3` | `T1003.003` | CONFIRMED / T1003.003 | PRESENT | TRUE_POSITIVE | NewProcessName=*ntdsutil*, ntdsutil |
| `strong_full_v3` | `T1047` | RULED_OUT / — | ABSENT | HONEST_NEGATIVE | — |
| `strong_full_v3` | `T1053.005` | RULED_OUT / — | ABSENT | HONEST_NEGATIVE | — |
| `strong_full_v3` | `T1078` | ANOMALOUS_UNCLASSIFIED / — | ABSENT | HONEST_ANOMALY | — |
| `strong_full_v3` | `T1083` | ANOMALOUS_UNCLASSIFIED / — | PRESENT | EVIDENCE_PRESENT_MISS | ../, etc/passwd |
| `strong_full_v3` | `T1110.003` | ANOMALOUS_UNCLASSIFIED / — | ABSENT | HONEST_ANOMALY | — |
| `strong_full_v3` | `T1189` | RULED_OUT / — | ABSENT | HONEST_NEGATIVE | — |
| `strong_full_v3` | `T1190` | ANOMALOUS_UNCLASSIFIED / — | ABSENT | HONEST_ANOMALY | — |
| `strong_full_v3` | `T1550.002` | RULED_OUT / — | ABSENT | HONEST_NEGATIVE | — |
| `strong_full_v3` | `T1552` | ANOMALOUS_UNCLASSIFIED / — | PRESENT | EVIDENCE_PRESENT_MISS | .env, credentials, password= |
| `strong_full_v3` | `T1552.005` | ANOMALOUS_UNCLASSIFIED / — | ABSENT | HONEST_ANOMALY | — |
| `strong_full_v3` | `T1557` | CONFIRMED / T1557 | PRESENT | TRUE_POSITIVE | EventCode=4624, LogonType=3 |
| `strong_full_v3` | `T1557.001` | ANOMALOUS_UNCLASSIFIED / — | ABSENT | HONEST_ANOMALY | — |
| `strong_full_v3` | `T1558.003` | RULED_OUT / — | ABSENT | HONEST_NEGATIVE | — |
| `strong_full_v3` | `T1558.004` | ANOMALOUS_UNCLASSIFIED / — | ABSENT | HONEST_ANOMALY | — |
| `strong_full_v3` | `T1595` | CONFIRMED / T1595 | PRESENT | TRUE_POSITIVE | status=404 |
| `strong_full_v3` | `T1611` | RULED_OUT / — | ABSENT | HONEST_NEGATIVE | — |
| `weak_mentor_validation` | `T1003.003` | CONFIRMED / T1003, T1486 | PRESENT | MISATTRIBUTION | NewProcessName=*ntdsutil*, ntdsutil |
| `weak_mentor_validation` | `T1047` | ANOMALOUS_UNCLASSIFIED / — | PRESENT | EVIDENCE_PRESENT_MISS | EventCode=4688, NewProcessName=*WmiPrvSE* |
| `weak_mentor_validation` | `T1053.005` | RULED_OUT / — | INDETERMINATE | UNSCORABLE_BY_ORACLE | — |
| `weak_mentor_validation` | `T1078` | RULED_OUT / — | ABSENT | HONEST_NEGATIVE | — |
| `weak_mentor_validation` | `T1083` | RULED_OUT / — | ABSENT | HONEST_NEGATIVE | — |
| `weak_mentor_validation` | `T1110.003` | ANOMALOUS_UNCLASSIFIED / — | ABSENT | HONEST_ANOMALY | — |
| `weak_mentor_validation` | `T1189` | ANOMALOUS_UNCLASSIFIED / — | ABSENT | HONEST_ANOMALY | — |
| `weak_mentor_validation` | `T1190` | RULED_OUT / — | ABSENT | HONEST_NEGATIVE | — |
| `weak_mentor_validation` | `T1550.002` | ANOMALOUS_UNCLASSIFIED / — | ABSENT | HONEST_ANOMALY | — |
| `weak_mentor_validation` | `T1552` | RULED_OUT / — | PRESENT | FALSE_NEGATIVE | credentials |
| `weak_mentor_validation` | `T1552.005` | RULED_OUT / — | PRESENT | FALSE_NEGATIVE | 169.254.169.254 |
| `weak_mentor_validation` | `T1557` | ANOMALOUS_UNCLASSIFIED / — | PRESENT | EVIDENCE_PRESENT_MISS | EventCode=4624, LogonType=3 |
| `weak_mentor_validation` | `T1557.001` | RULED_OUT / T1087 | PRESENT | FALSE_NEGATIVE | EventCode=4697 |
| `weak_mentor_validation` | `T1558.003` | RULED_OUT / — | ABSENT | HONEST_NEGATIVE | — |
| `weak_mentor_validation` | `T1558.004` | ANOMALOUS_UNCLASSIFIED / — | ABSENT | HONEST_ANOMALY | — |
| `weak_mentor_validation` | `T1595` | ANOMALOUS_UNCLASSIFIED / — | ABSENT | HONEST_ANOMALY | — |
| `weak_mentor_validation` | `T1611` | RULED_OUT / T1610, T1087 | PRESENT | FALSE_NEGATIVE | mount |

## Interpretation limits

- PRESENT means a detection-library discriminator was in the exact retrieval text shown to the model; it does not prove the model noticed it.
- ABSENT means that discriminator was not in model-visible retrieval text. Evidence may exist elsewhere in the labeled corpus, but fresh corpus queries are deliberately excluded.
- INDETERMINATE means either the library has no machine-checkable declared/SPL `field=value` discriminator or a legacy cell did not capture model-visible retrieval content.
- A CONFIRMED cell is a TRUE_POSITIVE only for the exact expected ID. Parent/tactic credit retained by the promotion scorer is recorded in `promotion_recall`, but a different emitted ID remains MISATTRIBUTION for this precision instrument.
