# bench_repair — one-shot vs +1-repair matrix

**Generated:** 2026-08-12T05:43:37Z
**Exam fingerprint (gsha):** `6a1cf4a3f706`
**Corpus size:** 10 problems (`bench_capability_c2_problems.json`)

```
corpus_sha     : ce8fcc7b0dc52f44
prompts_sha    : 5e7e4919a9fe9d11
ollama_version : 0.32.7
gsha           : 6a1cf4a3f706
```

**Arms:** one-shot n=5, +1-repair n=2, temperature=1.0. PROMOTE_POLICY: confirm — no auto-promotion.

## Matrix

| Workspace | Arch | model_hint | one-shot | +1-repair | Δ | notes |
|---|---|---|---:|---:|---:|---|
| `auto-coding` | MoE | `qwen3-coder:30b-a3b-q4_K_M-ctx16k` | 90.0% (50) | 95.0% (20) | +5.0 |  |
| `bench-devstral` | dense | `devstral:24b` | 76.0% (50) | 90.0% (20) | +14.0 |  |
| `bench-devstral-small-2` | dense | `devstral-small-2:latest` | 66.0% (50) | 85.0% (20) | +19.0 |  |

## Arch summary (mean pass rate, mean delta)

| Arch | mean one-shot | mean +1-repair | mean Δ | workspaces |
|---|---:|---:|---:|---|
| dense | 71.0% | 87.5% | +16.5 | bench-devstral, bench-devstral-small-2 |
| MoE | 90.0% | 95.0% | +5.0 | auto-coding |

## Per-sample detail

- `auto-coding` `one_repair` `c2_1` #0: **PASS** (7.3s) — pass_first_try
- `auto-coding` `one_repair` `c2_1` #1: **PASS** (3.5s) — pass_first_try
- `auto-coding` `one_repair` `c2_10` #0: **PASS** (8.8s) — pass_first_try
- `auto-coding` `one_repair` `c2_10` #1: **PASS** (5.8s) — pass_first_try
- `auto-coding` `one_repair` `c2_2` #0: **PASS** (5.6s) — pass_first_try
- `auto-coding` `one_repair` `c2_2` #1: **PASS** (4.8s) — pass_first_try
- `auto-coding` `one_repair` `c2_3` #0: **PASS** (4.1s) — pass_first_try
- `auto-coding` `one_repair` `c2_3` #1: **PASS** (3.7s) — pass_first_try
- `auto-coding` `one_repair` `c2_4` #0: **PASS** (2.0s) — pass_first_try
- `auto-coding` `one_repair` `c2_4` #1: **PASS** (2.0s) — pass_first_try
- `auto-coding` `one_repair` `c2_5` #0: **PASS** (6.3s) — pass_first_try
- `auto-coding` `one_repair` `c2_5` #1: **PASS** (4.7s) — pass_first_try
- `auto-coding` `one_repair` `c2_6` #0: **PASS** (5.9s) — pass_first_try
- `auto-coding` `one_repair` `c2_6` #1: **PASS** (5.5s) — pass_first_try
- `auto-coding` `one_repair` `c2_7` #0: **PASS** (3.0s) — pass_first_try
- `auto-coding` `one_repair` `c2_7` #1: **PASS** (3.3s) — pass_first_try
- `auto-coding` `one_repair` `c2_8` #0: **PASS** (2.8s) — pass_first_try
- `auto-coding` `one_repair` `c2_8` #1: **PASS** (2.3s) — pass_first_try
- `auto-coding` `one_repair` `c2_9` #0: **FAIL** (24.0s) — fail_after_repair
- `auto-coding` `one_repair` `c2_9` #1: **PASS** (8.1s) — pass_first_try
- `auto-coding` `one_shot` `c2_1` #0: **PASS** (11.6s) — pass
- `auto-coding` `one_shot` `c2_1` #1: **PASS** (2.4s) — pass
- `auto-coding` `one_shot` `c2_1` #2: **PASS** (2.3s) — pass
- `auto-coding` `one_shot` `c2_1` #3: **PASS** (3.5s) — pass
- `auto-coding` `one_shot` `c2_1` #4: **PASS** (2.3s) — pass
- `auto-coding` `one_shot` `c2_10` #0: **PASS** (4.9s) — pass
- `auto-coding` `one_shot` `c2_10` #1: **PASS** (8.6s) — pass
- `auto-coding` `one_shot` `c2_10` #2: **PASS** (8.6s) — pass
- `auto-coding` `one_shot` `c2_10` #3: **PASS** (5.9s) — pass
- `auto-coding` `one_shot` `c2_10` #4: **PASS** (7.8s) — pass
- `auto-coding` `one_shot` `c2_2` #0: **PASS** (4.8s) — pass
- `auto-coding` `one_shot` `c2_2` #1: **PASS** (8.2s) — pass
- `auto-coding` `one_shot` `c2_2` #2: **PASS** (4.7s) — pass
- `auto-coding` `one_shot` `c2_2` #3: **PASS** (4.6s) — pass
- `auto-coding` `one_shot` `c2_2` #4: **PASS** (2.5s) — pass
- `auto-coding` `one_shot` `c2_3` #0: **PASS** (3.7s) — pass
- `auto-coding` `one_shot` `c2_3` #1: **PASS** (6.7s) — pass
- `auto-coding` `one_shot` `c2_3` #2: **PASS** (5.1s) — pass
- `auto-coding` `one_shot` `c2_3` #3: **PASS** (3.5s) — pass
- `auto-coding` `one_shot` `c2_3` #4: **PASS** (4.2s) — pass
- `auto-coding` `one_shot` `c2_4` #0: **PASS** (2.2s) — pass
- `auto-coding` `one_shot` `c2_4` #1: **PASS** (3.0s) — pass
- `auto-coding` `one_shot` `c2_4` #2: **PASS** (2.2s) — pass
- `auto-coding` `one_shot` `c2_4` #3: **PASS** (2.0s) — pass
- `auto-coding` `one_shot` `c2_4` #4: **PASS** (2.0s) — pass
- `auto-coding` `one_shot` `c2_5` #0: **PASS** (6.0s) — pass
- `auto-coding` `one_shot` `c2_5` #1: **PASS** (6.5s) — pass
- `auto-coding` `one_shot` `c2_5` #2: **PASS** (6.6s) — pass
- `auto-coding` `one_shot` `c2_5` #3: **PASS** (5.8s) — pass
- `auto-coding` `one_shot` `c2_5` #4: **PASS** (6.5s) — pass
- `auto-coding` `one_shot` `c2_6` #0: **PASS** (3.5s) — pass
- `auto-coding` `one_shot` `c2_6` #1: **FAIL** (6.8s) — fail
- `auto-coding` `one_shot` `c2_6` #2: **FAIL** (5.0s) — fail
- `auto-coding` `one_shot` `c2_6` #3: **PASS** (5.3s) — pass
- `auto-coding` `one_shot` `c2_6` #4: **PASS** (3.7s) — pass
- `auto-coding` `one_shot` `c2_7` #0: **PASS** (2.7s) — pass
- `auto-coding` `one_shot` `c2_7` #1: **PASS** (2.1s) — pass
- `auto-coding` `one_shot` `c2_7` #2: **PASS** (3.3s) — pass
- `auto-coding` `one_shot` `c2_7` #3: **PASS** (2.1s) — pass
- `auto-coding` `one_shot` `c2_7` #4: **PASS** (2.7s) — pass
- `auto-coding` `one_shot` `c2_8` #0: **PASS** (2.1s) — pass
- `auto-coding` `one_shot` `c2_8` #1: **PASS** (2.8s) — pass
- `auto-coding` `one_shot` `c2_8` #2: **PASS** (2.6s) — pass
- `auto-coding` `one_shot` `c2_8` #3: **PASS** (2.4s) — pass
- `auto-coding` `one_shot` `c2_8` #4: **PASS** (2.4s) — pass
- `auto-coding` `one_shot` `c2_9` #0: **PASS** (3.8s) — pass
- `auto-coding` `one_shot` `c2_9` #1: **FAIL** (6.2s) — fail
- `auto-coding` `one_shot` `c2_9` #2: **FAIL** (6.6s) — fail
- `auto-coding` `one_shot` `c2_9` #3: **FAIL** (7.9s) — fail
- `auto-coding` `one_shot` `c2_9` #4: **PASS** (5.9s) — pass
- `bench-devstral` `one_repair` `c2_1` #0: **PASS** (13.1s) — pass_first_try
- `bench-devstral` `one_repair` `c2_1` #1: **PASS** (10.9s) — pass_first_try
- `bench-devstral` `one_repair` `c2_10` #0: **PASS** (8.6s) — pass_first_try
- `bench-devstral` `one_repair` `c2_10` #1: **PASS** (15.6s) — pass_first_try
- `bench-devstral` `one_repair` `c2_2` #0: **PASS** (13.4s) — pass_first_try
- `bench-devstral` `one_repair` `c2_2` #1: **PASS** (17.3s) — pass_first_try
- `bench-devstral` `one_repair` `c2_3` #0: **PASS** (34.2s) — pass_after_repair
- `bench-devstral` `one_repair` `c2_3` #1: **PASS** (21.2s) — pass_first_try
- `bench-devstral` `one_repair` `c2_4` #0: **PASS** (10.1s) — pass_first_try
- `bench-devstral` `one_repair` `c2_4` #1: **PASS** (7.1s) — pass_first_try
- `bench-devstral` `one_repair` `c2_5` #0: **PASS** (18.1s) — pass_first_try
- `bench-devstral` `one_repair` `c2_5` #1: **PASS** (15.0s) — pass_first_try
- `bench-devstral` `one_repair` `c2_6` #0: **FAIL** (41.6s) — fail_after_repair
- `bench-devstral` `one_repair` `c2_6` #1: **FAIL** (55.1s) — fail_after_repair
- `bench-devstral` `one_repair` `c2_7` #0: **PASS** (5.7s) — pass_first_try
- `bench-devstral` `one_repair` `c2_7` #1: **PASS** (14.4s) — pass_first_try
- `bench-devstral` `one_repair` `c2_8` #0: **PASS** (35.0s) — pass_after_repair
- `bench-devstral` `one_repair` `c2_8` #1: **PASS** (47.9s) — pass_after_repair
- `bench-devstral` `one_repair` `c2_9` #0: **PASS** (36.4s) — pass_first_try
- `bench-devstral` `one_repair` `c2_9` #1: **PASS** (25.2s) — pass_first_try
- `bench-devstral` `one_shot` `c2_1` #0: **PASS** (27.8s) — pass
- `bench-devstral` `one_shot` `c2_1` #1: **PASS** (17.9s) — pass
- `bench-devstral` `one_shot` `c2_1` #2: **PASS** (12.0s) — pass
- `bench-devstral` `one_shot` `c2_1` #3: **PASS** (17.4s) — pass
- `bench-devstral` `one_shot` `c2_1` #4: **PASS** (17.7s) — pass
- `bench-devstral` `one_shot` `c2_10` #0: **PASS** (10.4s) — pass
- `bench-devstral` `one_shot` `c2_10` #1: **PASS** (9.9s) — pass
- `bench-devstral` `one_shot` `c2_10` #2: **PASS** (13.9s) — pass
- `bench-devstral` `one_shot` `c2_10` #3: **PASS** (14.4s) — pass
- `bench-devstral` `one_shot` `c2_10` #4: **PASS** (8.1s) — pass
- `bench-devstral` `one_shot` `c2_2` #0: **PASS** (23.9s) — pass
- `bench-devstral` `one_shot` `c2_2` #1: **PASS** (10.0s) — pass
- `bench-devstral` `one_shot` `c2_2` #2: **PASS** (8.5s) — pass
- `bench-devstral` `one_shot` `c2_2` #3: **FAIL** (22.3s) — fail
- `bench-devstral` `one_shot` `c2_2` #4: **PASS** (12.0s) — pass
- `bench-devstral` `one_shot` `c2_3` #0: **PASS** (25.3s) — pass
- `bench-devstral` `one_shot` `c2_3` #1: **PASS** (24.1s) — pass
- `bench-devstral` `one_shot` `c2_3` #2: **PASS** (9.6s) — pass
- `bench-devstral` `one_shot` `c2_3` #3: **PASS** (18.9s) — pass
- `bench-devstral` `one_shot` `c2_3` #4: **PASS** (19.6s) — pass
- `bench-devstral` `one_shot` `c2_4` #0: **PASS** (12.5s) — pass
- `bench-devstral` `one_shot` `c2_4` #1: **PASS** (10.5s) — pass
- `bench-devstral` `one_shot` `c2_4` #2: **PASS** (9.9s) — pass
- `bench-devstral` `one_shot` `c2_4` #3: **PASS** (8.6s) — pass
- `bench-devstral` `one_shot` `c2_4` #4: **PASS** (4.6s) — pass
- `bench-devstral` `one_shot` `c2_5` #0: **PASS** (20.9s) — pass
- `bench-devstral` `one_shot` `c2_5` #1: **PASS** (10.1s) — pass
- `bench-devstral` `one_shot` `c2_5` #2: **PASS** (13.7s) — pass
- `bench-devstral` `one_shot` `c2_5` #3: **PASS** (15.8s) — pass
- `bench-devstral` `one_shot` `c2_5` #4: **PASS** (13.8s) — pass
- `bench-devstral` `one_shot` `c2_6` #0: **FAIL** (23.6s) — fail
- `bench-devstral` `one_shot` `c2_6` #1: **FAIL** (27.7s) — fail
- `bench-devstral` `one_shot` `c2_6` #2: **FAIL** (28.2s) — fail
- `bench-devstral` `one_shot` `c2_6` #3: **FAIL** (31.5s) — fail
- `bench-devstral` `one_shot` `c2_6` #4: **FAIL** (28.9s) — fail
- `bench-devstral` `one_shot` `c2_7` #0: **PASS** (19.3s) — pass
- `bench-devstral` `one_shot` `c2_7` #1: **PASS** (14.6s) — pass
- `bench-devstral` `one_shot` `c2_7` #2: **PASS** (12.6s) — pass
- `bench-devstral` `one_shot` `c2_7` #3: **PASS** (14.1s) — pass
- `bench-devstral` `one_shot` `c2_7` #4: **PASS** (15.4s) — pass
- `bench-devstral` `one_shot` `c2_8` #0: **FAIL** (6.0s) — fail
- `bench-devstral` `one_shot` `c2_8` #1: **FAIL** (10.0s) — fail
- `bench-devstral` `one_shot` `c2_8` #2: **FAIL** (10.4s) — fail
- `bench-devstral` `one_shot` `c2_8` #3: **PASS** (17.3s) — pass
- `bench-devstral` `one_shot` `c2_8` #4: **FAIL** (5.0s) — fail
- `bench-devstral` `one_shot` `c2_9` #0: **PASS** (34.0s) — pass
- `bench-devstral` `one_shot` `c2_9` #1: **FAIL** (20.9s) — fail
- `bench-devstral` `one_shot` `c2_9` #2: **PASS** (19.1s) — pass
- `bench-devstral` `one_shot` `c2_9` #3: **FAIL** (25.9s) — fail
- `bench-devstral` `one_shot` `c2_9` #4: **PASS** (24.4s) — pass
- `bench-devstral-small-2` `one_repair` `c2_1` #0: **PASS** (18.8s) — pass_first_try
- `bench-devstral-small-2` `one_repair` `c2_1` #1: **PASS** (18.5s) — pass_first_try
- `bench-devstral-small-2` `one_repair` `c2_10` #0: **FAIL** (138.4s) — fail_after_repair
- `bench-devstral-small-2` `one_repair` `c2_10` #1: **PASS** (18.3s) — pass_first_try
- `bench-devstral-small-2` `one_repair` `c2_2` #0: **PASS** (21.4s) — pass_first_try
- `bench-devstral-small-2` `one_repair` `c2_2` #1: **PASS** (32.4s) — pass_after_repair
- `bench-devstral-small-2` `one_repair` `c2_3` #0: **PASS** (21.4s) — pass_first_try
- `bench-devstral-small-2` `one_repair` `c2_3` #1: **PASS** (9.7s) — pass_first_try
- `bench-devstral-small-2` `one_repair` `c2_4` #0: **PASS** (10.1s) — pass_first_try
- `bench-devstral-small-2` `one_repair` `c2_4` #1: **PASS** (15.7s) — pass_first_try
- `bench-devstral-small-2` `one_repair` `c2_5` #0: **PASS** (11.6s) — pass_first_try
- `bench-devstral-small-2` `one_repair` `c2_5` #1: **PASS** (22.6s) — pass_first_try
- `bench-devstral-small-2` `one_repair` `c2_6` #0: **FAIL** (80.8s) — fail_after_repair
- `bench-devstral-small-2` `one_repair` `c2_6` #1: **FAIL** (72.6s) — fail_after_repair
- `bench-devstral-small-2` `one_repair` `c2_7` #0: **PASS** (14.3s) — pass_first_try
- `bench-devstral-small-2` `one_repair` `c2_7` #1: **PASS** (21.6s) — pass_first_try
- `bench-devstral-small-2` `one_repair` `c2_8` #0: **PASS** (19.5s) — pass_first_try
- `bench-devstral-small-2` `one_repair` `c2_8` #1: **PASS** (15.3s) — pass_first_try
- `bench-devstral-small-2` `one_repair` `c2_9` #0: **PASS** (30.8s) — pass_first_try
- `bench-devstral-small-2` `one_repair` `c2_9` #1: **PASS** (30.3s) — pass_first_try
- `bench-devstral-small-2` `one_shot` `c2_1` #0: **PASS** (32.5s) — pass
- `bench-devstral-small-2` `one_shot` `c2_1` #1: **PASS** (23.1s) — pass
- `bench-devstral-small-2` `one_shot` `c2_1` #2: **PASS** (20.2s) — pass
- `bench-devstral-small-2` `one_shot` `c2_1` #3: **PASS** (24.5s) — pass
- `bench-devstral-small-2` `one_shot` `c2_1` #4: **PASS** (24.8s) — pass
- `bench-devstral-small-2` `one_shot` `c2_10` #0: **FAIL** (22.8s) — fail
- `bench-devstral-small-2` `one_shot` `c2_10` #1: **PASS** (12.4s) — pass
- `bench-devstral-small-2` `one_shot` `c2_10` #2: **PASS** (14.6s) — pass
- `bench-devstral-small-2` `one_shot` `c2_10` #3: **FAIL** (34.8s) — fail
- `bench-devstral-small-2` `one_shot` `c2_10` #4: **FAIL** (3.5s) — fail
- `bench-devstral-small-2` `one_shot` `c2_2` #0: **FAIL** (26.1s) — fail
- `bench-devstral-small-2` `one_shot` `c2_2` #1: **PASS** (30.5s) — pass
- `bench-devstral-small-2` `one_shot` `c2_2` #2: **PASS** (20.3s) — pass
- `bench-devstral-small-2` `one_shot` `c2_2` #3: **PASS** (25.0s) — pass
- `bench-devstral-small-2` `one_shot` `c2_2` #4: **FAIL** (13.9s) — fail
- `bench-devstral-small-2` `one_shot` `c2_3` #0: **FAIL** (18.3s) — fail
- `bench-devstral-small-2` `one_shot` `c2_3` #1: **FAIL** (21.2s) — fail
- `bench-devstral-small-2` `one_shot` `c2_3` #2: **PASS** (37.2s) — pass
- `bench-devstral-small-2` `one_shot` `c2_3` #3: **PASS** (28.2s) — pass
- `bench-devstral-small-2` `one_shot` `c2_3` #4: **PASS** (13.6s) — pass
- `bench-devstral-small-2` `one_shot` `c2_4` #0: **PASS** (15.4s) — pass
- `bench-devstral-small-2` `one_shot` `c2_4` #1: **PASS** (14.4s) — pass
- `bench-devstral-small-2` `one_shot` `c2_4` #2: **PASS** (15.3s) — pass
- `bench-devstral-small-2` `one_shot` `c2_4` #3: **PASS** (11.9s) — pass
- `bench-devstral-small-2` `one_shot` `c2_4` #4: **PASS** (3.5s) — pass
- `bench-devstral-small-2` `one_shot` `c2_5` #0: **PASS** (9.7s) — pass
- `bench-devstral-small-2` `one_shot` `c2_5` #1: **FAIL** (37.5s) — fail
- `bench-devstral-small-2` `one_shot` `c2_5` #2: **PASS** (26.8s) — pass
- `bench-devstral-small-2` `one_shot` `c2_5` #3: **PASS** (22.5s) — pass
- `bench-devstral-small-2` `one_shot` `c2_5` #4: **PASS** (19.9s) — pass
- `bench-devstral-small-2` `one_shot` `c2_6` #0: **FAIL** (30.1s) — fail
- `bench-devstral-small-2` `one_shot` `c2_6` #1: **FAIL** (24.6s) — fail
- `bench-devstral-small-2` `one_shot` `c2_6` #2: **FAIL** (29.9s) — fail
- `bench-devstral-small-2` `one_shot` `c2_6` #3: **FAIL** (37.8s) — fail
- `bench-devstral-small-2` `one_shot` `c2_6` #4: **FAIL** (27.3s) — fail
- `bench-devstral-small-2` `one_shot` `c2_7` #0: **PASS** (9.4s) — pass
- `bench-devstral-small-2` `one_shot` `c2_7` #1: **PASS** (18.1s) — pass
- `bench-devstral-small-2` `one_shot` `c2_7` #2: **FAIL** (12.1s) — fail
- `bench-devstral-small-2` `one_shot` `c2_7` #3: **PASS** (15.0s) — pass
- `bench-devstral-small-2` `one_shot` `c2_7` #4: **PASS** (12.4s) — pass
- `bench-devstral-small-2` `one_shot` `c2_8` #0: **PASS** (26.9s) — pass
- `bench-devstral-small-2` `one_shot` `c2_8` #1: **PASS** (19.6s) — pass
- `bench-devstral-small-2` `one_shot` `c2_8` #2: **FAIL** (18.6s) — fail
- `bench-devstral-small-2` `one_shot` `c2_8` #3: **PASS** (13.0s) — pass
- `bench-devstral-small-2` `one_shot` `c2_8` #4: **PASS** (24.5s) — pass
- `bench-devstral-small-2` `one_shot` `c2_9` #0: **FAIL** (47.6s) — fail
- `bench-devstral-small-2` `one_shot` `c2_9` #1: **PASS** (30.8s) — pass
- `bench-devstral-small-2` `one_shot` `c2_9` #2: **PASS** (15.0s) — pass
- `bench-devstral-small-2` `one_shot` `c2_9` #3: **PASS** (29.8s) — pass
- `bench-devstral-small-2` `one_shot` `c2_9` #4: **FAIL** (26.5s) — fail
