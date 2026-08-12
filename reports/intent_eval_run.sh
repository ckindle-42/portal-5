#!/usr/bin/env bash
set -uo pipefail
# NOTE: -e removed (was set -euo pipefail). Two lanes below (coding, general) needed
# hand-fixing after the literal plan failed on the FIRST command:
#   "workspace not found in portal.yaml: devstral-small-2:latest-ctx8k"
# Root cause (verified by reading the actual probe source, not guessed):
#   - bench_repair.py's --models flag takes existing portal.yaml WORKSPACE SLUGS
#     (it calls _resolve_model_hint(workspace) via portal.yaml), not raw Ollama
#     tags. intent_eval.py's plan generator emitted raw tags for every probe
#     uniformly, which happens to match the --model contract of
#     bench_{reasoning,vision,mtp,long_context}_probe.py but NOT bench_repair.py.
#   - bench_capability.py (bound to "general") has NO --model flag at all —only
#     --workspace/--all (mutually exclusive, required) — and writes
#     results/v11_capability_<workspace>_<ts>.json in a payload shape
#     ({"results":[{"role":...,"workspace":...,"results":[...]}]}) that doesn't
#     match intent_eval.py cmd_analyze()'s expected flat {"results":[{"model":,
#     "quality_score":}]} shape or its "capability_*.json" glob prefix.
# Fix applied: rewritten below to call each probe through its REAL CLI contract,
# using pre-existing bench-* workspaces where they exist. Per ground rules for
# this task run, config/portal.yaml may NOT be edited to add missing workspace
# slots, so candidates with no existing workspace are left as documented BLOCKED
# (see reports/INTENT_EVAL_DECISION.* / final report) rather than faked.
# intent_eval.py analyze() will still show "no repair_*.json"/"no capability_*.json"
# results for these two intents (filename/shape mismatch persists there); the
# real per-candidate numbers gathered here are reported by hand alongside it.

# ===== intent: coding  (incumbent workspace auto-coding -> qwen3-coder:30b-a3b-q4_K_M-ctx16k) =====
# ALREADY COMPLETE (real, pytest-fixed data) -> reports/CODING_BENCH_REPAIR.md, see
# reports/coding_lane_manual.log. Not rerun on this resume pass.
# devstral-small-2:latest-ctx8k has NO matching portal.yaml workspace -> BLOCKED, not run.
# python3 tests/benchmarks/bench_repair.py --models bench-devstral-small-2,bench-devstral,auto-coding --output reports/CODING_BENCH_REPAIR.md 2>&1 | tee -a reports/coding_lane_manual.log || true

# ===== intent: general  (incumbent workspace auto-daily -> gemma4:26b-a4b-it-qat-ctx8k) =====
# ALREADY COMPLETE (real, post-C1-bugfix data) -> 11x tests/benchmarks/results/v11_capability_*_20260812T0[6-9]*.json,
# see reports/general_lane_manual.log. Sanity-checked live as each of the 11 workspaces
# finished (varied, plausible C1-C5 scores throughout) — NOT rerun on this resume pass.
# 6 of 17 candidates have NO matching portal.yaml workspace -> BLOCKED, not run:
#   portal5/deepwen-3.6:q4.5-moq ; hf.co/bartowski/THUDM_GLM-Z1-Rumination-32B-0414-GGUF:...
#   mistral-small3.2:24b ; portal5/gemma4-12b:q4_K_M-ctx8k ; llama3.2:3b-instruct-q8_0-ctx8k ; llama3.2:3b
# for ws in bench-aquila-mini-35b-a3b bench-aquila-research bench-deepwen-cad bench-qwable-3.6-35b \
#           bench-glm bench-gemma4-31b-crack bench-dolphin-llama3 bench-fastcontext \
#           bench-lfm-micro-1p2b bench-lfm-micro-350m bench-lfm-micro-230m; do
#   python3 tests/benchmarks/bench_capability.py --workspace "$ws" --compare-baseline auto-daily 2>&1 | tee -a reports/general_lane_manual.log || true
# done

# ===== intent: long-context  (incumbent workspace auto-research -> huihui_ai/tongyi-deepresearch-abliterated:latest-ctx64k) =====
# ALREADY COMPLETE -> tests/benchmarks/results/long_context_probe_20260812T105740Z.json
# NOTE: phi4:14b-q8_0 came back quality=0.0/avg_tps=None (instant HTTP 500 on both
# cases, 0.3s) — flagged for a standalone single-model retry after the sweep, NOT
# a PIPELINE_API_KEY issue (this probe calls Ollama directly, unaffected by that bug).
# python3 tests/benchmarks/bench_long_context_probe.py --model 'sylink/sylink:8b' --model 'sylink/sylink:8b-ctx8k' --model 'phi4:14b-q8_0' --model 'huihui_ai/tongyi-deepresearch-abliterated:latest-ctx64k'

# ===== intent: mtp-speculative  (incumbent workspace auto-reasoning -> hf.co/unsloth/DeepSeek-R1-0528-Qwen3-8B-GGUF:Q4_K_XL-ctx64k) =====
# ALREADY COMPLETE -> tests/benchmarks/results/mtp_probe_20260812T110332Z.json
# python3 tests/benchmarks/bench_mtp_probe.py --model 'portal5/qwen3.6-27b-mtp:q8_0-drafted' --model 'hf.co/Jackrong/Qwopus3.6-27B-v2-MTP-GGUF:Qwopus3.6-27B-v2-MTP-Q5_K_M.gguf' --model 'hf.co/bartowski/Qwen_Qwen3.6-27B-GGUF:Q4_K_M' --model 'qwen3.6:27b-mtp-q4_K_M' --model 'hf.co/yuxinlu1/gemma-4-12B-agentic-fable5-composer2.5-v2-3.5x-tau2-GGUF:Q4_K_M' --model 'hf.co/Jackrong/DeepSeek-V4-Pro-Qwen3.5-4B-MTP-GGUF:Q4_K_M' --model 'hf.co/unsloth/DeepSeek-R1-0528-Qwen3-8B-GGUF:Q4_K_XL-ctx64k'

# ===== intent: reasoning  (incumbent workspace auto-reasoning -> hf.co/unsloth/DeepSeek-R1-0528-Qwen3-8B-GGUF:Q4_K_XL-ctx64k) =====
# ALREADY COMPLETE -> tests/benchmarks/results/reasoning_probe_20260812T114518Z.json
# NOTE: hf.co/Abiray/Agents-A1-Q4_K_M-GGUF came back quality=0.0/tps=None — flagged
# for a standalone single-model retry after the sweep (this probe also calls Ollama
# directly, unaffected by the PIPELINE_API_KEY bug fixed below).
# python3 tests/benchmarks/bench_reasoning_probe.py --model 'qwen3.6:27b-q8_0' --model 'qwen3.6:35b-a3b-q4_K_M' --model 'hf.co/Abiray/Agents-A1-Q4_K_M-GGUF:Q4_K_M' --model 'deepseek-r1:32b-q4_k_m' --model 'hf.co/unsloth/GLM-4.7-Flash-REAP-23B-A3B-GGUF:UD-Q4_K_XL-ctx64k' --model 'gpt-oss:20b' --model 'hermes3:8b' --model 'hf.co/Nguuma/security-slm-unsloth-1.5b:latest'

# ===== intent: security  (incumbent workspace auto-security -> hf.co/mradermacher/VulnLLM-R-7B-GGUF:q4_K_M-ctx8k) =====
# ROOT-CAUSE FIX (this resume pass): ~/portal-5 had NO .env file at all (fresh
# clone from Phase 0 never ran ./launch.sh up). candidate-eval's lab-exec chains
# route through the pipeline (:9099) by design (_is_pipeline_model() always True
# unless CHAIN_DIRECT_OLLAMA=true) and send Authorization: Bearer $PIPELINE_API_KEY.
# With no .env, that env var was empty -> no auth header sent -> pipeline (which
# DOES enforce a real key, confirmed via docker exec portal5-pipeline env) rejected
# every single chain call with 401, 0s elapsed, before any real inference happened.
# First candidate (BugTraceAI-CORE-Ultra-27B) confirmed 100% contaminated (all 6
# scenarios x candidate+incumbent = 12/12 chains, all instant 401) and was killed
# before it wrote any results file — nothing to back up. Fixed by creating
# ~/portal-5/.env (copied from .env.example, gitignored) with the real
# PIPELINE_API_KEY read from `docker exec portal5-pipeline env`. Verified via curl:
# 401 without the key, 200 with it. All 13 candidates below run fresh under the fix.
python3 -m portal.modules.security.core candidate-eval --candidate 'hf.co/BugTraceAI/BugTraceAI-CORE-Ultra-27B-Q6:Q6_K' --slot solo --force --lab-exec
python3 -m portal.modules.security.core candidate-eval --candidate 'hf.co/mradermacher/Huihui-Qwen3.6-35B-A3B-abliterated-GGUF:Q4_K_M' --slot solo --force --lab-exec
python3 -m portal.modules.security.core candidate-eval --candidate 'hf.co/Jiunsong/SuperQwen-AgentWorld-35B-A3B-abliterated-gguf-4bit:Q4_K_M' --slot solo --force --lab-exec
python3 -m portal.modules.security.core candidate-eval --candidate 'hf.co/mradermacher/gemma-4-26B-A4B-it-uncensored-heretic-GGUF:gemma-4-26B-A4B-it-uncensored-heretic.Q4_K_M.gguf' --slot solo --force --lab-exec
python3 -m portal.modules.security.core candidate-eval --candidate 'huihui_ai/qwen3-abliterated:14b-v2' --slot solo --force --lab-exec
python3 -m portal.modules.security.core candidate-eval --candidate 'hf.co/fdtn-ai/Foundation-Sec-8B-Reasoning-Q8_0-GGUF:Q8_0' --slot solo --force --lab-exec
python3 -m portal.modules.security.core candidate-eval --candidate 'hf.co/mradermacher/Qwen3.5-9B-Claude-4.6-HighIQ-THINKING-HERETIC-UNCENSORED-GGUF:Q4_K_M' --slot solo --force --lab-exec
python3 -m portal.modules.security.core candidate-eval --candidate 'meta-secalign-8b-q4_k_m:latest' --slot solo --force --lab-exec
python3 -m portal.modules.security.core candidate-eval --candidate 'huihui_ai/gemma-4-abliterated:E2b-qat-ctx8k' --slot solo --force --lab-exec
python3 -m portal.modules.security.core candidate-eval --candidate 'huihui_ai/gemma-4-abliterated:E2b-qat' --slot solo --force --lab-exec
python3 -m portal.modules.security.core candidate-eval --candidate 'hf.co/Andycurrent/Mistral-7B-Uncensored-GGUF:Q4_K_M' --slot solo --force --lab-exec
python3 -m portal.modules.security.core candidate-eval --candidate 'cybersecqwen-4b-toolfix:latest' --slot solo --force --lab-exec
python3 -m portal.modules.security.core candidate-eval --candidate 'hf.co/QuantFactory/Llama-3.2-3B-Instruct-abliterated-GGUF:latest' --slot solo --force --lab-exec
# ===== intent: vision  (incumbent workspace auto-vision -> qwen3-vl:32b-ctx8k) =====
python3 tests/benchmarks/bench_vision_probe.py --model 'hf.co/unsloth/Magistral-Small-2509-GGUF:Q8_0-ctx64k' --model 'hf.co/unsloth/Qwen3.6-35B-A3B-GGUF:UD-Q4_K_XL' --model 'hf.co/sjakek/Nex-N2-mini-GGUF:UD-Q4_K_M' --model 'muse-glimmer:30b-mlx' --model 'gemma4:31b-it-qat-ctx8k' --model 'gemma4:31b-it-qat' --model 'gemma4:26b-a4b-it-q4_K_M' --model 'hf.co/Jackrong/DeepSeek-V4-Pro-Qwen3.5-9B-MTP-GGUF:Q4_K_M' --model 'gemma4:e4b-it-qat-ctx8k' --model 'gemma4:e4b-it-qat' --model 'gemma4:e2b-it-qat-ctx8k' --model 'gemma4:e2b-it-qat' --model 'qwen3-vl:32b-ctx8k'

