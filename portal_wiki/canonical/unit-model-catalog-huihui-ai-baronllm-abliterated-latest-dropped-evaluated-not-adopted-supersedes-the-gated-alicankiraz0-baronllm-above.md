---
id: unit-model-catalog-huihui-ai-baronllm-abliterated-latest-dropped-evaluated-not-adopted-supersedes-the-gated-alicankiraz0-baronllm-above
kind: what
title: "MODEL_CATALOG \u2014 `huihui_ai/baronllm-abliterated:latest` \u2014 DROPPED\
  \ (evaluated, not adopted; supersedes the gated AlicanKiraz0 BaronLLM above)"
sources:
- type: doc
  path: config/MODEL_CATALOG.md
  commit: 05e42ec2
  section: "`huihui_ai/baronllm-abliterated:latest` \u2014 DROPPED (evaluated, not\
    \ adopted; supersedes the gated AlicanKiraz0 BaronLLM above)"
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.628695
updated_at: 1784946220.628695
---

Red EXPLOIT-slot candidate — the properly-abliterated BaronLLM (Llama 3.1 8B lineage, huihui-ai
abliteration, MIT), the working alternative to the gated original above. Preflight passed clean: non-blank,
zero refusals, real tool-calls confirmed via direct API probe (correct `run_nmap_scan` arguments). candidate-eval
vs `huihui_ai/gemma-4-abliterated:E2b-qat-ctx8k` incumbent, EXPLOIT slot, 6-scenario gauntlet (1 scenario,
meta3_full_chain, skipped as target-unrecoverable even in synthetic mode for both candidate and incumbent
runs — pre-existing gauntlet issue, not a candidate defect): aggregate -0.083 unique_coverage, +0.000
lab_success — WORSE, driven entirely by kerberoast_to_da (depth 4/8 vs incumbent-alone 8/8): the model
correctly executed its assigned `exploit_service` step (tool-call clean, real arguments) but the chain
stalled on handoff to the next step afterward. Tied on ctf_multi_service (depth 7/7 both) and beat the
incumbent on web_ssrf (depth 2/2 vs 1/2). Net: real capability, no refusal wall, but a handoff-stability
regression on the AD chain outweighs the wins elsewhere.
