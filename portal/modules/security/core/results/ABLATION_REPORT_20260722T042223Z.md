# Blue-Orchestration Ablation Report (2026-07-22T04:22:23.069121+00:00)

HEAD: `abef7f69`  reps=3  corpus_n=89  error_rate=0.006

## Per-arm summary

| arm | n | hits | novelty | real_recall | hallucination_rate | nonconv_rate |
|---|---|---|---|---|---|---|
| 1section | 262 | 17 | 0 | 0.065 | 0.0 | 0.0 |
| 2section | 267 | 24 | 28 | 0.195 | 0.0 | 0.139 |
| 3section | 267 | 47 | 46 | 0.348 | 0.0 | 0.056 |

## Miss histograms (fraction of misses)

- **1section**: {'HUNTER_MISS': 0.996, 'HANDOFF_LOSS': 0.004, 'HALLUCINATION': 0.0, 'NON_CONVERGENCE': 0.0}
- **2section**: {'HUNTER_MISS': 0.0, 'HANDOFF_LOSS': 0.828, 'HALLUCINATION': 0.0, 'NON_CONVERGENCE': 0.172}
- **3section**: {'HUNTER_MISS': 0.0, 'HANDOFF_LOSS': 0.914, 'HALLUCINATION': 0.0, 'NON_CONVERGENCE': 0.086}

**best_multi_arm**: 3section  
**split_proven** (3section beats 1section by >= 0.1 AND novelty > 0): True  
**honest_blocked**: False
