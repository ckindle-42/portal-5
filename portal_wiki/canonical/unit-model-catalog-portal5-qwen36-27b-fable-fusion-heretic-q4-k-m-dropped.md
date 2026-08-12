---
id: unit-model-catalog-portal5-qwen36-27b-fable-fusion-heretic-q4-k-m-dropped
kind: what
title: "MODEL_CATALOG \u2014 `portal5/qwen36-27b-fable-fusion-heretic:q4_k_m` (DROPPED)"
sources:
- type: code
  path: portal/modules/security/core/candidate_eval.py
last_generated_commit: a23f47b3e687df1693600eeea5b4f3f381b9da20
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1786307600.0
updated_at: 1786307600.0
---

`portal5/qwen36-27b-fable-fusion-heretic:q4_k_m` was evaluated as a TASK-BATCH-BENCH-001 Part B RBP red-corpus / EXPLOIT-slot candidate (DavidAU's ARA-abliterated Qwen3.6-27B "Fable-Fusion-711" GGUF, 4/100-refusal-rated on its model card) and dropped. It is not registered in `config/backends.yaml` — the entire evaluation ran isolated through `python3 -m portal.modules.security.core candidate-eval --candidate portal5/qwen36-27b-fable-fusion-heretic:q4_k_m --slot exploit --skip-pull --force` (the correct dispatcher; note `portal/modules/security/core/__main__.py` routes the `candidate-eval` subcommand — `python3 -m bench_security candidate-eval` and `python3 -m tests.benchmarks.bench_security candidate-eval` do NOT work, those modules are backward-compat re-export shims with no subcommand dispatch), never touching fleet config. Same import method as the Part A Aquila-mini candidate: `huggingface_hub.hf_hub_download` + `ollama create` (the direct Ollama `hf.co` pull hit no issue here, but the download was done directly out of caution after Part A's 21GB-blob timeout finding). Intake: TPS 11.4 t/s (below the 20 t/s floor — scored anyway via `--force`, the deliberate quality-over-speed path), clean single tool-call emission confirmed. Slotted as the `exploit` step against the fleet's auto-resolved incumbent (`fredrezones55/Qwen3.6-35B-A3B-Uncensored-HauhauCS-Aggressive:Q4-ctx8k`) across the 6 fixed candidate-eval scenarios (one scenario, `meta3_full_chain`, skipped both arms as target-unrecoverable). Result: aggregate `+0.000` unique_coverage delta, `+0.042` accuracy delta (a `+0.25` accuracy gain on `web_sqli_dump` alone, zero elsewhere), `+0` lab_success delta — verdict **NEUTRAL**. The candidate does not out-generate the incumbent red generator enough to warrant a corpus-lane slot at this size/quant; results are isolated to `portal/modules/security/core/results/candidates/` (gitignored, self-index unaffected — verified by direct check).

## Why

This unit exists because the model has zero `config/backends.yaml` footprint (candidate-eval by design never writes to fleet config), so nothing else in the repo records that this evaluation happened, what verdict it reached, or the two real gotchas hit along the way: the correct CLI entry point (three module paths look plausible; only one dispatches `candidate-eval`) and the established `hf_hub_download` fallback pattern for large GGUF blobs. Recording the NEUTRAL verdict here — rather than letting the isolated JSON result be the only trace — stops a future session from re-pulling and re-benching the same candidate without first checking whether anything about the incumbent or the candidate's quant has changed.
