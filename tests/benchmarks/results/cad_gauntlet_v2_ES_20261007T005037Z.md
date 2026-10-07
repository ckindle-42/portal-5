# CAD gauntlet v2 — ES

Generated: 20261007T005037Z  
Reps: 2  Tasks: 8

| arm | workspace | model | mean score | PASS rate | validity | median s |
|---|---|---|---|---|---|---|
| es | auto-cad | `qwen3-coder:30b-a3b-q4_K_M-ctx32k` | 0.469 | 0.125 | 0.625 | 92.2 |

## Per task (PASS count / reps)

| task | es |
|---|---|
| plate_4holes | 1/2 |
| grommet_plate | 1/2 |
| enclosure | 0/2 |
| l_bracket | 0/2 |
| flanged_bushing | 0/2 |
| countersunk_plate | 0/2 |
| hex_standoff | 0/2 |
| spur_gear | 0/2 |

Grader: tests/benchmarks/cad_grader.py (sealed, spec-derived; tool self-reports are not scored).
