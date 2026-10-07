# CAD gauntlet v2 — EB

Generated: 20261007T011246Z  
Reps: 2  Tasks: 8

| arm | workspace | model | mean score | PASS rate | validity | median s |
|---|---|---|---|---|---|---|
| eb | auto-cad | `qwen3-coder:30b-a3b-q4_K_M-ctx32k` | 0.719 | 0.375 | 0.938 | 36.6 |

## Per task (PASS count / reps)

| task | eb |
|---|---|
| plate_4holes | 2/2 |
| grommet_plate | 2/2 |
| enclosure | 0/2 |
| l_bracket | 0/2 |
| flanged_bushing | 0/2 |
| countersunk_plate | 2/2 |
| hex_standoff | 0/2 |
| spur_gear | 0/2 |

Grader: tests/benchmarks/cad_grader.py (sealed, spec-derived; tool self-reports are not scored).
