# bench_repair — one-shot vs +1-repair matrix

**Generated:** 2026-08-27T07:05:17Z
**Exam fingerprint (gsha):** `066355de23d5`
**Corpus size:** 10 problems (`bench_capability_c2_problems.json`)

```
corpus_sha     : ce8fcc7b0dc52f44
prompts_sha    : 5e7e4919a9fe9d11
ollama_version : 0.32.15
gsha           : 066355de23d5
```

**Arms:** one-shot n=5, +1-repair n=2, temperature=1.0. PROMOTE_POLICY: confirm — no auto-promotion.

## Matrix

| Workspace | Arch | model_hint | one-shot | +1-repair | Δ | notes |
|---|---|---|---:|---:|---:|---|
| `bench-gemma4-heretic-coder` | MoE | `hf.co/mradermacher/gemma-4-26B-A4B-it-heretic-GGUF:Q4_K_M` | 100.0% (50) | 100.0% (20) | +0.0 |  |
| `bench-hauhaucs-coder` | MoE | `hf.co/HauhauCS/Qwen3.6-35B-A3B-Uncensored-HauhauCS-Aggressive:Q4_K_M` | 56.0% (50) | 70.0% (20) | +14.0 |  |
| `bench-ornith15-coder` | MoE | `hf.co/mradermacher/Ornith-1.5-35B-A3B-Uncensored-GGUF:Q4_K_M` | 86.0% (50) | 95.0% (20) | +9.0 |  |

## Arch summary (mean pass rate, mean delta)

| Arch | mean one-shot | mean +1-repair | mean Δ | workspaces |
|---|---:|---:|---:|---|
| MoE | 80.7% | 88.3% | +7.7 | bench-gemma4-heretic-coder, bench-hauhaucs-coder, bench-ornith15-coder |

## Per-sample detail

- `bench-gemma4-heretic-coder` `one_repair` `c2_1` #0: **PASS** (25.6s) — pass_first_try
- `bench-gemma4-heretic-coder` `one_repair` `c2_1` #1: **PASS** (25.9s) — pass_first_try
- `bench-gemma4-heretic-coder` `one_repair` `c2_10` #0: **PASS** (16.6s) — pass_first_try
- `bench-gemma4-heretic-coder` `one_repair` `c2_10` #1: **PASS** (16.5s) — pass_first_try
- `bench-gemma4-heretic-coder` `one_repair` `c2_2` #0: **PASS** (22.5s) — pass_first_try
- `bench-gemma4-heretic-coder` `one_repair` `c2_2` #1: **PASS** (21.9s) — pass_first_try
- `bench-gemma4-heretic-coder` `one_repair` `c2_3` #0: **PASS** (23.5s) — pass_first_try
- `bench-gemma4-heretic-coder` `one_repair` `c2_3` #1: **PASS** (33.3s) — pass_first_try
- `bench-gemma4-heretic-coder` `one_repair` `c2_4` #0: **PASS** (24.3s) — pass_first_try
- `bench-gemma4-heretic-coder` `one_repair` `c2_4` #1: **PASS** (21.4s) — pass_first_try
- `bench-gemma4-heretic-coder` `one_repair` `c2_5` #0: **PASS** (38.7s) — pass_first_try
- `bench-gemma4-heretic-coder` `one_repair` `c2_5` #1: **PASS** (31.2s) — pass_first_try
- `bench-gemma4-heretic-coder` `one_repair` `c2_6` #0: **PASS** (59.4s) — pass_first_try
- `bench-gemma4-heretic-coder` `one_repair` `c2_6` #1: **PASS** (61.2s) — pass_first_try
- `bench-gemma4-heretic-coder` `one_repair` `c2_7` #0: **PASS** (44.4s) — pass_first_try
- `bench-gemma4-heretic-coder` `one_repair` `c2_7` #1: **PASS** (34.1s) — pass_first_try
- `bench-gemma4-heretic-coder` `one_repair` `c2_8` #0: **PASS** (36.6s) — pass_first_try
- `bench-gemma4-heretic-coder` `one_repair` `c2_8` #1: **PASS** (25.0s) — pass_first_try
- `bench-gemma4-heretic-coder` `one_repair` `c2_9` #0: **PASS** (44.9s) — pass_first_try
- `bench-gemma4-heretic-coder` `one_repair` `c2_9` #1: **PASS** (55.0s) — pass_first_try
- `bench-gemma4-heretic-coder` `one_shot` `c2_1` #0: **PASS** (40.2s) — pass
- `bench-gemma4-heretic-coder` `one_shot` `c2_1` #1: **PASS** (26.0s) — pass
- `bench-gemma4-heretic-coder` `one_shot` `c2_1` #2: **PASS** (23.6s) — pass
- `bench-gemma4-heretic-coder` `one_shot` `c2_1` #3: **PASS** (26.1s) — pass
- `bench-gemma4-heretic-coder` `one_shot` `c2_1` #4: **PASS** (26.3s) — pass
- `bench-gemma4-heretic-coder` `one_shot` `c2_10` #0: **PASS** (16.3s) — pass
- `bench-gemma4-heretic-coder` `one_shot` `c2_10` #1: **PASS** (16.0s) — pass
- `bench-gemma4-heretic-coder` `one_shot` `c2_10` #2: **PASS** (16.1s) — pass
- `bench-gemma4-heretic-coder` `one_shot` `c2_10` #3: **PASS** (16.8s) — pass
- `bench-gemma4-heretic-coder` `one_shot` `c2_10` #4: **PASS** (15.0s) — pass
- `bench-gemma4-heretic-coder` `one_shot` `c2_2` #0: **PASS** (37.7s) — pass
- `bench-gemma4-heretic-coder` `one_shot` `c2_2` #1: **PASS** (49.0s) — pass
- `bench-gemma4-heretic-coder` `one_shot` `c2_2` #2: **PASS** (26.0s) — pass
- `bench-gemma4-heretic-coder` `one_shot` `c2_2` #3: **PASS** (26.6s) — pass
- `bench-gemma4-heretic-coder` `one_shot` `c2_2` #4: **PASS** (25.5s) — pass
- `bench-gemma4-heretic-coder` `one_shot` `c2_3` #0: **PASS** (23.4s) — pass
- `bench-gemma4-heretic-coder` `one_shot` `c2_3` #1: **PASS** (30.8s) — pass
- `bench-gemma4-heretic-coder` `one_shot` `c2_3` #2: **PASS** (34.2s) — pass
- `bench-gemma4-heretic-coder` `one_shot` `c2_3` #3: **PASS** (26.2s) — pass
- `bench-gemma4-heretic-coder` `one_shot` `c2_3` #4: **PASS** (38.3s) — pass
- `bench-gemma4-heretic-coder` `one_shot` `c2_4` #0: **PASS** (23.1s) — pass
- `bench-gemma4-heretic-coder` `one_shot` `c2_4` #1: **PASS** (18.8s) — pass
- `bench-gemma4-heretic-coder` `one_shot` `c2_4` #2: **PASS** (23.3s) — pass
- `bench-gemma4-heretic-coder` `one_shot` `c2_4` #3: **PASS** (25.7s) — pass
- `bench-gemma4-heretic-coder` `one_shot` `c2_4` #4: **PASS** (22.2s) — pass
- `bench-gemma4-heretic-coder` `one_shot` `c2_5` #0: **PASS** (49.9s) — pass
- `bench-gemma4-heretic-coder` `one_shot` `c2_5` #1: **PASS** (41.7s) — pass
- `bench-gemma4-heretic-coder` `one_shot` `c2_5` #2: **PASS** (37.2s) — pass
- `bench-gemma4-heretic-coder` `one_shot` `c2_5` #3: **PASS** (38.1s) — pass
- `bench-gemma4-heretic-coder` `one_shot` `c2_5` #4: **PASS** (39.7s) — pass
- `bench-gemma4-heretic-coder` `one_shot` `c2_6` #0: **PASS** (55.6s) — pass
- `bench-gemma4-heretic-coder` `one_shot` `c2_6` #1: **PASS** (49.8s) — pass
- `bench-gemma4-heretic-coder` `one_shot` `c2_6` #2: **PASS** (51.5s) — pass
- `bench-gemma4-heretic-coder` `one_shot` `c2_6` #3: **PASS** (76.1s) — pass
- `bench-gemma4-heretic-coder` `one_shot` `c2_6` #4: **PASS** (52.0s) — pass
- `bench-gemma4-heretic-coder` `one_shot` `c2_7` #0: **PASS** (50.8s) — pass
- `bench-gemma4-heretic-coder` `one_shot` `c2_7` #1: **PASS** (32.7s) — pass
- `bench-gemma4-heretic-coder` `one_shot` `c2_7` #2: **PASS** (44.0s) — pass
- `bench-gemma4-heretic-coder` `one_shot` `c2_7` #3: **PASS** (61.1s) — pass
- `bench-gemma4-heretic-coder` `one_shot` `c2_7` #4: **PASS** (49.4s) — pass
- `bench-gemma4-heretic-coder` `one_shot` `c2_8` #0: **PASS** (27.8s) — pass
- `bench-gemma4-heretic-coder` `one_shot` `c2_8` #1: **PASS** (32.6s) — pass
- `bench-gemma4-heretic-coder` `one_shot` `c2_8` #2: **PASS** (31.1s) — pass
- `bench-gemma4-heretic-coder` `one_shot` `c2_8` #3: **PASS** (26.7s) — pass
- `bench-gemma4-heretic-coder` `one_shot` `c2_8` #4: **PASS** (28.4s) — pass
- `bench-gemma4-heretic-coder` `one_shot` `c2_9` #0: **PASS** (43.0s) — pass
- `bench-gemma4-heretic-coder` `one_shot` `c2_9` #1: **PASS** (45.7s) — pass
- `bench-gemma4-heretic-coder` `one_shot` `c2_9` #2: **PASS** (55.1s) — pass
- `bench-gemma4-heretic-coder` `one_shot` `c2_9` #3: **PASS** (42.7s) — pass
- `bench-gemma4-heretic-coder` `one_shot` `c2_9` #4: **PASS** (50.8s) — pass
- `bench-hauhaucs-coder` `one_repair` `c2_1` #0: **PASS** (135.3s) — pass_first_try
- `bench-hauhaucs-coder` `one_repair` `c2_1` #1: **PASS** (74.8s) — pass_first_try
- `bench-hauhaucs-coder` `one_repair` `c2_10` #0: **PASS** (125.5s) — pass_first_try
- `bench-hauhaucs-coder` `one_repair` `c2_10` #1: **PASS** (41.9s) — pass_first_try
- `bench-hauhaucs-coder` `one_repair` `c2_2` #0: **PASS** (115.5s) — pass_first_try
- `bench-hauhaucs-coder` `one_repair` `c2_2` #1: **PASS** (318.5s) — pass_after_repair
- `bench-hauhaucs-coder` `one_repair` `c2_3` #0: **PASS** (78.2s) — pass_first_try
- `bench-hauhaucs-coder` `one_repair` `c2_3` #1: **PASS** (59.4s) — pass_first_try
- `bench-hauhaucs-coder` `one_repair` `c2_4` #0: **PASS** (166.6s) — pass_first_try
- `bench-hauhaucs-coder` `one_repair` `c2_4` #1: **PASS** (115.1s) — pass_first_try
- `bench-hauhaucs-coder` `one_repair` `c2_5` #0: **PASS** (154.0s) — pass_first_try
- `bench-hauhaucs-coder` `one_repair` `c2_5` #1: **PASS** (161.2s) — pass_first_try
- `bench-hauhaucs-coder` `one_repair` `c2_6` #0: **FAIL** (416.8s) — fail_after_repair
- `bench-hauhaucs-coder` `one_repair` `c2_6` #1: **FAIL** (417.2s) — fail_after_repair
- `bench-hauhaucs-coder` `one_repair` `c2_7` #0: **FAIL** (416.0s) — fail_after_repair
- `bench-hauhaucs-coder` `one_repair` `c2_7` #1: **FAIL** (416.5s) — fail_after_repair
- `bench-hauhaucs-coder` `one_repair` `c2_8` #0: **FAIL** (417.4s) — fail_after_repair
- `bench-hauhaucs-coder` `one_repair` `c2_8` #1: **FAIL** (418.0s) — fail_after_repair
- `bench-hauhaucs-coder` `one_repair` `c2_9` #0: **PASS** (121.4s) — pass_first_try
- `bench-hauhaucs-coder` `one_repair` `c2_9` #1: **PASS** (88.4s) — pass_first_try
- `bench-hauhaucs-coder` `one_shot` `c2_1` #0: **PASS** (114.2s) — pass
- `bench-hauhaucs-coder` `one_shot` `c2_1` #1: **PASS** (142.7s) — pass
- `bench-hauhaucs-coder` `one_shot` `c2_1` #2: **PASS** (158.7s) — pass
- `bench-hauhaucs-coder` `one_shot` `c2_1` #3: **FAIL** (195.0s) — fail
- `bench-hauhaucs-coder` `one_shot` `c2_1` #4: **PASS** (185.7s) — pass
- `bench-hauhaucs-coder` `one_shot` `c2_10` #0: **PASS** (59.4s) — pass
- `bench-hauhaucs-coder` `one_shot` `c2_10` #1: **PASS** (64.4s) — pass
- `bench-hauhaucs-coder` `one_shot` `c2_10` #2: **PASS** (94.1s) — pass
- `bench-hauhaucs-coder` `one_shot` `c2_10` #3: **PASS** (66.2s) — pass
- `bench-hauhaucs-coder` `one_shot` `c2_10` #4: **PASS** (91.7s) — pass
- `bench-hauhaucs-coder` `one_shot` `c2_2` #0: **PASS** (182.5s) — pass
- `bench-hauhaucs-coder` `one_shot` `c2_2` #1: **PASS** (147.9s) — pass
- `bench-hauhaucs-coder` `one_shot` `c2_2` #2: **FAIL** (207.9s) — fail
- `bench-hauhaucs-coder` `one_shot` `c2_2` #3: **PASS** (186.8s) — pass
- `bench-hauhaucs-coder` `one_shot` `c2_2` #4: **FAIL** (207.6s) — fail
- `bench-hauhaucs-coder` `one_shot` `c2_3` #0: **FAIL** (208.7s) — fail
- `bench-hauhaucs-coder` `one_shot` `c2_3` #1: **PASS** (76.0s) — pass
- `bench-hauhaucs-coder` `one_shot` `c2_3` #2: **FAIL** (208.3s) — fail
- `bench-hauhaucs-coder` `one_shot` `c2_3` #3: **PASS** (76.9s) — pass
- `bench-hauhaucs-coder` `one_shot` `c2_3` #4: **PASS** (78.1s) — pass
- `bench-hauhaucs-coder` `one_shot` `c2_4` #0: **PASS** (141.7s) — pass
- `bench-hauhaucs-coder` `one_shot` `c2_4` #1: **FAIL** (208.3s) — fail
- `bench-hauhaucs-coder` `one_shot` `c2_4` #2: **PASS** (101.2s) — pass
- `bench-hauhaucs-coder` `one_shot` `c2_4` #3: **FAIL** (208.2s) — fail
- `bench-hauhaucs-coder` `one_shot` `c2_4` #4: **PASS** (180.5s) — pass
- `bench-hauhaucs-coder` `one_shot` `c2_5` #0: **PASS** (162.0s) — pass
- `bench-hauhaucs-coder` `one_shot` `c2_5` #1: **FAIL** (207.6s) — fail
- `bench-hauhaucs-coder` `one_shot` `c2_5` #2: **PASS** (165.7s) — pass
- `bench-hauhaucs-coder` `one_shot` `c2_5` #3: **FAIL** (208.0s) — fail
- `bench-hauhaucs-coder` `one_shot` `c2_5` #4: **PASS** (188.0s) — pass
- `bench-hauhaucs-coder` `one_shot` `c2_6` #0: **FAIL** (208.6s) — fail
- `bench-hauhaucs-coder` `one_shot` `c2_6` #1: **FAIL** (208.1s) — fail
- `bench-hauhaucs-coder` `one_shot` `c2_6` #2: **FAIL** (208.6s) — fail
- `bench-hauhaucs-coder` `one_shot` `c2_6` #3: **FAIL** (208.4s) — fail
- `bench-hauhaucs-coder` `one_shot` `c2_6` #4: **FAIL** (208.0s) — fail
- `bench-hauhaucs-coder` `one_shot` `c2_7` #0: **PASS** (126.7s) — pass
- `bench-hauhaucs-coder` `one_shot` `c2_7` #1: **FAIL** (208.1s) — fail
- `bench-hauhaucs-coder` `one_shot` `c2_7` #2: **FAIL** (207.9s) — fail
- `bench-hauhaucs-coder` `one_shot` `c2_7` #3: **FAIL** (207.7s) — fail
- `bench-hauhaucs-coder` `one_shot` `c2_7` #4: **FAIL** (208.0s) — fail
- `bench-hauhaucs-coder` `one_shot` `c2_8` #0: **FAIL** (208.6s) — fail
- `bench-hauhaucs-coder` `one_shot` `c2_8` #1: **FAIL** (208.4s) — fail
- `bench-hauhaucs-coder` `one_shot` `c2_8` #2: **PASS** (196.5s) — pass
- `bench-hauhaucs-coder` `one_shot` `c2_8` #3: **FAIL** (208.1s) — fail
- `bench-hauhaucs-coder` `one_shot` `c2_8` #4: **FAIL** (208.5s) — fail
- `bench-hauhaucs-coder` `one_shot` `c2_9` #0: **PASS** (106.9s) — pass
- `bench-hauhaucs-coder` `one_shot` `c2_9` #1: **PASS** (94.9s) — pass
- `bench-hauhaucs-coder` `one_shot` `c2_9` #2: **PASS** (103.3s) — pass
- `bench-hauhaucs-coder` `one_shot` `c2_9` #3: **PASS** (108.3s) — pass
- `bench-hauhaucs-coder` `one_shot` `c2_9` #4: **PASS** (86.8s) — pass
- `bench-ornith15-coder` `one_repair` `c2_1` #0: **PASS** (19.2s) — pass_first_try
- `bench-ornith15-coder` `one_repair` `c2_1` #1: **PASS** (21.3s) — pass_first_try
- `bench-ornith15-coder` `one_repair` `c2_10` #0: **PASS** (39.8s) — pass_first_try
- `bench-ornith15-coder` `one_repair` `c2_10` #1: **PASS** (44.9s) — pass_first_try
- `bench-ornith15-coder` `one_repair` `c2_2` #0: **PASS** (40.8s) — pass_first_try
- `bench-ornith15-coder` `one_repair` `c2_2` #1: **PASS** (38.8s) — pass_first_try
- `bench-ornith15-coder` `one_repair` `c2_3` #0: **PASS** (35.0s) — pass_first_try
- `bench-ornith15-coder` `one_repair` `c2_3` #1: **PASS** (65.6s) — pass_first_try
- `bench-ornith15-coder` `one_repair` `c2_4` #0: **PASS** (19.0s) — pass_first_try
- `bench-ornith15-coder` `one_repair` `c2_4` #1: **PASS** (18.4s) — pass_first_try
- `bench-ornith15-coder` `one_repair` `c2_5` #0: **PASS** (44.9s) — pass_first_try
- `bench-ornith15-coder` `one_repair` `c2_5` #1: **FAIL** (243.3s) — fail_after_repair
- `bench-ornith15-coder` `one_repair` `c2_6` #0: **PASS** (172.0s) — pass_first_try
- `bench-ornith15-coder` `one_repair` `c2_6` #1: **PASS** (166.8s) — pass_first_try
- `bench-ornith15-coder` `one_repair` `c2_7` #0: **PASS** (60.9s) — pass_first_try
- `bench-ornith15-coder` `one_repair` `c2_7` #1: **PASS** (72.7s) — pass_first_try
- `bench-ornith15-coder` `one_repair` `c2_8` #0: **PASS** (37.5s) — pass_first_try
- `bench-ornith15-coder` `one_repair` `c2_8` #1: **PASS** (47.8s) — pass_first_try
- `bench-ornith15-coder` `one_repair` `c2_9` #0: **PASS** (75.1s) — pass_first_try
- `bench-ornith15-coder` `one_repair` `c2_9` #1: **PASS** (121.9s) — pass_first_try
- `bench-ornith15-coder` `one_shot` `c2_1` #0: **PASS** (32.4s) — pass
- `bench-ornith15-coder` `one_shot` `c2_1` #1: **PASS** (21.0s) — pass
- `bench-ornith15-coder` `one_shot` `c2_1` #2: **FAIL** (20.1s) — fail
- `bench-ornith15-coder` `one_shot` `c2_1` #3: **PASS** (18.1s) — pass
- `bench-ornith15-coder` `one_shot` `c2_1` #4: **FAIL** (16.5s) — fail
- `bench-ornith15-coder` `one_shot` `c2_10` #0: **PASS** (41.8s) — pass
- `bench-ornith15-coder` `one_shot` `c2_10` #1: **PASS** (49.2s) — pass
- `bench-ornith15-coder` `one_shot` `c2_10` #2: **PASS** (42.4s) — pass
- `bench-ornith15-coder` `one_shot` `c2_10` #3: **PASS** (58.2s) — pass
- `bench-ornith15-coder` `one_shot` `c2_10` #4: **PASS** (50.0s) — pass
- `bench-ornith15-coder` `one_shot` `c2_2` #0: **PASS** (42.9s) — pass
- `bench-ornith15-coder` `one_shot` `c2_2` #1: **PASS** (39.8s) — pass
- `bench-ornith15-coder` `one_shot` `c2_2` #2: **PASS** (37.3s) — pass
- `bench-ornith15-coder` `one_shot` `c2_2` #3: **PASS** (55.7s) — pass
- `bench-ornith15-coder` `one_shot` `c2_2` #4: **PASS** (45.1s) — pass
- `bench-ornith15-coder` `one_shot` `c2_3` #0: **PASS** (30.8s) — pass
- `bench-ornith15-coder` `one_shot` `c2_3` #1: **PASS** (28.4s) — pass
- `bench-ornith15-coder` `one_shot` `c2_3` #2: **PASS** (31.3s) — pass
- `bench-ornith15-coder` `one_shot` `c2_3` #3: **PASS** (31.4s) — pass
- `bench-ornith15-coder` `one_shot` `c2_3` #4: **FAIL** (208.6s) — fail
- `bench-ornith15-coder` `one_shot` `c2_4` #0: **PASS** (22.0s) — pass
- `bench-ornith15-coder` `one_shot` `c2_4` #1: **PASS** (22.0s) — pass
- `bench-ornith15-coder` `one_shot` `c2_4` #2: **PASS** (16.8s) — pass
- `bench-ornith15-coder` `one_shot` `c2_4` #3: **PASS** (17.8s) — pass
- `bench-ornith15-coder` `one_shot` `c2_4` #4: **PASS** (21.0s) — pass
- `bench-ornith15-coder` `one_shot` `c2_5` #0: **PASS** (37.7s) — pass
- `bench-ornith15-coder` `one_shot` `c2_5` #1: **FAIL** (32.3s) — fail
- `bench-ornith15-coder` `one_shot` `c2_5` #2: **PASS** (29.7s) — pass
- `bench-ornith15-coder` `one_shot` `c2_5` #3: **PASS** (28.6s) — pass
- `bench-ornith15-coder` `one_shot` `c2_5` #4: **PASS** (30.7s) — pass
- `bench-ornith15-coder` `one_shot` `c2_6` #0: **PASS** (104.5s) — pass
- `bench-ornith15-coder` `one_shot` `c2_6` #1: **PASS** (208.0s) — pass
- `bench-ornith15-coder` `one_shot` `c2_6` #2: **FAIL** (208.4s) — fail
- `bench-ornith15-coder` `one_shot` `c2_6` #3: **FAIL** (208.6s) — fail
- `bench-ornith15-coder` `one_shot` `c2_6` #4: **FAIL** (207.4s) — fail
- `bench-ornith15-coder` `one_shot` `c2_7` #0: **PASS** (56.4s) — pass
- `bench-ornith15-coder` `one_shot` `c2_7` #1: **PASS** (178.1s) — pass
- `bench-ornith15-coder` `one_shot` `c2_7` #2: **PASS** (52.4s) — pass
- `bench-ornith15-coder` `one_shot` `c2_7` #3: **PASS** (61.3s) — pass
- `bench-ornith15-coder` `one_shot` `c2_7` #4: **PASS** (42.4s) — pass
- `bench-ornith15-coder` `one_shot` `c2_8` #0: **PASS** (42.1s) — pass
- `bench-ornith15-coder` `one_shot` `c2_8` #1: **PASS** (38.1s) — pass
- `bench-ornith15-coder` `one_shot` `c2_8` #2: **PASS** (45.1s) — pass
- `bench-ornith15-coder` `one_shot` `c2_8` #3: **PASS** (41.8s) — pass
- `bench-ornith15-coder` `one_shot` `c2_8` #4: **PASS** (58.0s) — pass
- `bench-ornith15-coder` `one_shot` `c2_9` #0: **PASS** (83.1s) — pass
- `bench-ornith15-coder` `one_shot` `c2_9` #1: **PASS** (120.9s) — pass
- `bench-ornith15-coder` `one_shot` `c2_9` #2: **PASS** (73.4s) — pass
- `bench-ornith15-coder` `one_shot` `c2_9` #3: **PASS** (77.7s) — pass
- `bench-ornith15-coder` `one_shot` `c2_9` #4: **PASS** (75.1s) — pass
