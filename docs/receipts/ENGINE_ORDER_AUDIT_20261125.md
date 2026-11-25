# Engine order audit — 2026-11-25

Baseline: lane started at `5d2b444470f0b5ca64ecc823fbbfba56c8574b67`. The table executes `BackendRegistry.get_backend_candidates`, the HEAD implementation of `placement.protect_hot_seat`, `parallel_seat.prefer_batching_engine`, and `streaming._prioritize_hinted_backend` against production config and all declared non-bench workspace variants. The HEAD `protect_hot_seat` function is loaded from `git show HEAD:portal/platform/inference/router/placement.py` and called directly with the audit tracker; no ordering logic is reimplemented. Equal-priority ties are deterministic with `random.seed(0)`. Backend health uses the code default (`healthy=True`); no health probes or engine calls ran.

The idle case uses an empty hot-seat tracker. The hot case records `__audit_other_model__` on the configured oMLX URL at monotonic time 1000 and evaluates at 1001, so the workspace hint differs from the recently active model. This is an offline state simulation of candidate ordering, not a live engine observation.

Intended engine follows configured candidate priority for ordinary seats: priority-10 oMLX aliases are the preferred route, with Ollama as the same-hint fallback. Direct Ollama-only hints remain Ollama. The three `compliance-council-*` workspaces are the explicit Ollama-first exception from the task brief's council co-residency requirement. Bench workspaces are excluded.

Rows: 77; idle first: oMLX 39, Ollama 38; hot-on-other-model first: oMLX 11, Ollama 66; mismatches: idle 3, hot 25, total scenario mismatches 28.

| Workspace | Hint | Native engine | Idle first candidate | oMLX hot on another model | Intended | Idle | Hot |
|---|---|---|---|---|---|---|---|
| `auto` | `huihui_ai/qwen3.5-abliterated:9b-ctx8k` | Ollama | `omlx-security` (omlx) | `ollama-security` (ollama) | omlx | match | mismatch |
| `auto-audio` | `gemma4:12b-it-qat-ctx16k` | Ollama | `ollama-vision` (ollama) | `ollama-vision` (ollama) | ollama | match | match |
| `auto-audio::image` | `granite4.1:8b-ctx16k` | Ollama | `ollama-general` (ollama) | `ollama-general` (ollama) | ollama | match | match |
| `auto-audio::music` | `lfm2.5:8b-ctx16k` | Ollama | `ollama-general` (ollama) | `ollama-general` (ollama) | ollama | match | match |
| `auto-audio::video` | `granite4.1:8b-ctx16k` | Ollama | `ollama-general` (ollama) | `ollama-general` (ollama) | ollama | match | match |
| `auto-coding` | `hf.co/unsloth/Qwen3.8-27B-GGUF:Q4_K_M-ctx96k` | Ollama | `omlx-general` (omlx) | `ollama-general` (ollama) | omlx | match | mismatch |
| `auto-coding::bigfix` | `qwen3-coder:30b-a3b-q4_K_M-ctx16k` | Ollama | `omlx-coding` (omlx) | `ollama-coding` (ollama) | omlx | match | mismatch |
| `auto-coding::cad` | `qwen3-coder:30b-a3b-q4_K_M-ctx32k` | Ollama | `omlx-coding` (omlx) | `ollama-coding` (ollama) | omlx | match | mismatch |
| `auto-coding::devstral_coder` | `devstral-small-2:latest-ctx8k` | Ollama | `ollama-coding` (ollama) | `ollama-coding` (ollama) | ollama | match | match |
| `auto-coding::fast-repair` | `kat-coder-v2.5-dev:Q4_K_M-ctx32k` | Ollama | `ollama-coding` (ollama) | `ollama-coding` (ollama) | ollama | match | match |
| `auto-coding::gemma4-heretic-coder` | `portal5/gemma4-26b-heretic:q4_K_M-ctx256k` | Ollama | `ollama-coding` (ollama) | `ollama-coding` (ollama) | ollama | match | match |
| `auto-coding::glm-coder` | `glm-4.7-flash:Q4_K_M-ctx24k-agentic` | Ollama | `ollama-coding` (ollama) | `ollama-coding` (ollama) | ollama | match | match |
| `auto-coding::hauhaucs-coder` | `portal5/hauhaucs-qwen36-35b:q4_K_M-ctx256k` | Ollama | `ollama-coding` (ollama) | `ollama-coding` (ollama) | ollama | match | match |
| `auto-coding::heavy` | `Qwen3.8-27B-oQ4e-mtp` | oMLX | `omlx-coding` (omlx) | `omlx-coding` (omlx) | omlx | match | match |
| `auto-coding::laguna` | `portal5/laguna-xs21:q4_K_M-ctx128k` | Ollama | `omlx-coding` (omlx) | `ollama-coding` (ollama) | omlx | match | mismatch |
| `auto-coding::lite` | `portal5/agentworld-35b:ud-q4_K_XL-ctx256k` | Ollama | `ollama-coding` (ollama) | `ollama-coding` (ollama) | ollama | match | match |
| `auto-coding::northmini` | `hf.co/coder543/North-Mini-Code-1.0-QAD-GGUF:NVFP4-ctx8k` | Ollama | `ollama-coding` (ollama) | `ollama-coding` (ollama) | ollama | match | match |
| `auto-coding::ornith` | `hf.co/deepreinforce-ai/Ornith-1.0-35B-GGUF:Q4_K_M-ctx64k` | Ollama | `ollama-coding` (ollama) | `ollama-coding` (ollama) | ollama | match | match |
| `auto-coding::ornith15-coder` | `portal5/ornith15-35b:q4_K_M-ctx256k` | Ollama | `ollama-coding` (ollama) | `ollama-coding` (ollama) | ollama | match | match |
| `auto-coding::qwen38coder` | `hf.co/unsloth/Qwen3.8-27B-GGUF:Q4_K_M` | Ollama | `omlx-coding` (omlx) | `ollama-coding` (ollama) | omlx | match | mismatch |
| `auto-coding::qwen38coder-dflash` | `Qwen3.8-27B-4bit` | oMLX | `omlx-coding` (omlx) | `omlx-coding` (omlx) | omlx | match | match |
| `auto-coding::uncensored` | `portal5/omnicoder2-9b:q4_K_M-ctx256k` | Ollama | `ollama-coding` (ollama) | `ollama-coding` (ollama) | ollama | match | match |
| `auto-coding::uncensored-agentic` | `Huihui-Qwen3.6-27B-abliterated-MLX-4bit` | oMLX | `omlx-coding` (omlx) | `omlx-coding` (omlx) | omlx | match | match |
| `auto-compliance` | `hf.co/unsloth/Qwen3.8-27B-GGUF:Q4_K_M-ctx96k` | Ollama | `omlx-reasoning` (omlx) | `ollama-general` (ollama) | omlx | match | mismatch |
| `auto-compliance::reading` | `gemma4:26b-a4b-it-q4_K_M-ctx128k` | Ollama | `omlx-general` (omlx) | `ollama-general` (ollama) | omlx | match | mismatch |
| `auto-council` | `gemma-4-26b-a4b-it-QAT-4bit` | oMLX | `omlx-general` (omlx) | `omlx-general` (omlx) | omlx | match | match |
| `auto-daily` | `hf.co/bartowski/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-GGUF:Q4_K_M-ctx32k` | Ollama | `ollama-general` (ollama) | `ollama-general` (ollama) | ollama | match | match |
| `auto-daily::deep` | `hf.co/unsloth/Qwen3.8-27B-GGUF:Q4_K_M-ctx96k` | Ollama | `omlx-general` (omlx) | `ollama-general` (ollama) | omlx | match | mismatch |
| `auto-daily::fast` | `hf.co/unsloth/Qwen3.6-35B-A3B-GGUF:UD-Q4_K_XL-ctx96k` | Ollama | `omlx-general` (omlx) | `ollama-general` (ollama) | omlx | match | mismatch |
| `auto-daily::gemma-fast` | `gemma4:26b-a4b-it-qat-ctx32k` | Ollama | `omlx-general` (omlx) | `ollama-general` (ollama) | omlx | match | mismatch |
| `auto-daily::inkling` | `inkling-2-mini:ctx256k` | Ollama | `ollama-general` (ollama) | `ollama-general` (ollama) | ollama | match | match |
| `auto-daily::nemotron` | `hf.co/bartowski/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-GGUF:Q4_K_M-ctx32k` | Ollama | `ollama-general` (ollama) | `ollama-general` (ollama) | ollama | match | match |
| `auto-documents` | `gemma4:26b-a4b-it-qat-ctx32k` | Ollama | `omlx-general` (omlx) | `ollama-general` (ollama) | omlx | match | mismatch |
| `auto-documents::extract-uncensored` | `hf.co/gaston-parravicini/LFM2.5-8B-A1B-Uncensored-Gaston-GGUF:q4_K_M-ctx8k` | Ollama | `ollama-general` (ollama) | `ollama-general` (ollama) | ollama | match | match |
| `auto-general-uncensored` | `hf.co/mradermacher/Huihui-Qwen3.6-35B-A3B-abliterated-GGUF:q4_K_M-ctx32k` | Ollama | `ollama-general` (ollama) | `ollama-general` (ollama) | ollama | match | match |
| `auto-general-uncensored::creative` | `fredrezones55/Qwen3.6-35B-A3B-Uncensored-HauhauCS-Aggressive:Q4-ctx24k` | Ollama | `omlx-general` (omlx) | `ollama-general` (ollama) | omlx | match | mismatch |
| `auto-general-uncensored::throwaway` | `portal5/hauhaucs-qwen36-35b:q4_K_M-ctx256k` | Ollama | `ollama-general` (ollama) | `ollama-general` (ollama) | ollama | match | match |
| `auto-general-uncensored::throwaway-gemma4-heretic` | `portal5/gemma4-26b-heretic:q4_K_M-ctx256k` | Ollama | `ollama-general` (ollama) | `ollama-general` (ollama) | ollama | match | match |
| `auto-general-uncensored::throwaway-ornith15` | `portal5/ornith15-35b:q4_K_M-ctx256k` | Ollama | `ollama-general` (ollama) | `ollama-general` (ollama) | ollama | match | match |
| `auto-reasoning` | `hf.co/bartowski/K2-Horizon-MoVA-36B-A4B-GGUF:Q4_K_M-ctx64k` | Ollama | `ollama-reasoning` (ollama) | `ollama-reasoning` (ollama) | ollama | match | match |
| `auto-reasoning::deep` | `hf.co/unsloth/Qwen3.8-27B-GGUF:Q4_K_M-ctx32k` | Ollama | `omlx-reasoning` (omlx) | `ollama-reasoning` (ollama) | omlx | match | mismatch |
| `auto-reasoning::glm-thinker` | `hf.co/bartowski/THUDM_GLM-Z1-32B-0414-GGUF:Q4_K_M-ctx32k` | Ollama | `ollama-reasoning` (ollama) | `ollama-reasoning` (ollama) | ollama | match | match |
| `auto-reasoning::magistralstrategist` | `hf.co/unsloth/Magistral-Small-2509-GGUF:Q8_0-ctx64k` | Ollama | `ollama-general` (ollama) | `ollama-general` (ollama) | ollama | match | match |
| `auto-reasoning::math` | `glm-4.7-flash:Q4_K_M-ctx24k` | Ollama | `ollama-general` (ollama) | `ollama-general` (ollama) | ollama | match | match |
| `auto-research` | `hf.co/sjakek/Nex-N2-mini-GGUF:UD-Q4_K_M-ctx32k` | Ollama | `ollama-general` (ollama) | `ollama-general` (ollama) | ollama | match | match |
| `auto-research::data` | `hf.co/unsloth/Qwen3.6-35B-A3B-GGUF:UD-Q4_K_XL-ctx32k` | Ollama | `omlx-reasoning` (omlx) | `ollama-reasoning` (ollama) | omlx | match | mismatch |
| `auto-security` | `Inkling-2-Mini-oQ4e-mtp` | oMLX | `omlx-security` (omlx) | `omlx-security` (omlx) | omlx | match | match |
| `auto-security::blueteam` | `granite4.1:8b-ctx16k` | Ollama | `ollama-security` (ollama) | `ollama-security` (ollama) | ollama | match | match |
| `auto-security::blueteam-council` | `Inkling-2-Mini-oQ4e-mtp` | oMLX | `omlx-security` (omlx) | `omlx-security` (omlx) | omlx | match | match |
| `auto-security::blueteam-orchestrated` | `Inkling-2-Mini-oQ4e-mtp` | oMLX | `omlx-security` (omlx) | `omlx-security` (omlx) | omlx | match | match |
| `auto-security::bully-handoff-drafter` | `granite4.1:30b-ctx16k` | Ollama | `omlx-general` (omlx) | `ollama-general` (ollama) | omlx | match | mismatch |
| `auto-security::pentest` | `fredrezones55/Qwen3.6-35B-A3B-Uncensored-HauhauCS-Aggressive:Q4-ctx24k` | Ollama | `omlx-security` (omlx) | `ollama-general` (ollama) | omlx | match | mismatch |
| `auto-security::purpleteam` | `huihui_ai/qwen3.5-abliterated:9b-ctx64k` | Ollama | `omlx-security` (omlx) | `ollama-security` (ollama) | omlx | match | mismatch |
| `auto-security::purpleteam-deep` | `Inkling-2-Mini-abliterated-oQ4e-mtp` | oMLX | `omlx-security` (omlx) | `omlx-security` (omlx) | omlx | match | match |
| `auto-security::purpleteam-exec` | `supergemma4-26b-uncensored:Q4_K_M-ctx64k` | Ollama | `omlx-security` (omlx) | `ollama-security` (ollama) | omlx | match | mismatch |
| `auto-security::redteam` | `huihui_ai/qwen3.5-abliterated:9b-ctx64k` | Ollama | `omlx-security` (omlx) | `ollama-security` (ollama) | omlx | match | mismatch |
| `auto-security::redteam-deep` | `supergemma4-26b-uncensored:Q4_K_M-ctx64k` | Ollama | `omlx-security` (omlx) | `ollama-security` (ollama) | omlx | match | mismatch |
| `auto-security::security-council-granite41-30b` | `granite4.1:30b-ctx16k` | Ollama | `omlx-general` (omlx) | `ollama-general` (ollama) | omlx | match | mismatch |
| `auto-security::security-council-mistral-small32-24b` | `mistral-small3.2:24b-ctx16k` | Ollama | `ollama-security` (ollama) | `ollama-security` (ollama) | ollama | match | match |
| `auto-security::security-council-qwen36-27b` | `qwen3.6:27b-q4_K_M-ctx4k` | Ollama | `ollama-security` (ollama) | `ollama-security` (ollama) | ollama | match | match |
| `auto-security::security-expert-foundation-sec-8b` | `hf.co/fdtn-ai/Foundation-Sec-8B-Reasoning-Q8_0-GGUF:Q8_0-ctx8k` | Ollama | `ollama-security` (ollama) | `ollama-security` (ollama) | ollama | match | match |
| `auto-security::security-tool-granite41-8b` | `granite4.1:8b-ctx16k` | Ollama | `ollama-security` (ollama) | `ollama-security` (ollama) | ollama | match | match |
| `auto-security::uncensored` | `Inkling-2-Mini-abliterated-oQ4e-mtp` | oMLX | `omlx-security` (omlx) | `omlx-security` (omlx) | omlx | match | match |
| `auto-spl` | `Qwen3.8-27B-oQ4e-mtp` | oMLX | `omlx-coding` (omlx) | `omlx-coding` (omlx) | omlx | match | match |
| `auto-spl::nano` | `orcacyber-nano-1.0:ctx64k` | Ollama | `ollama-coding` (ollama) | `ollama-coding` (ollama) | ollama | match | match |
| `auto-vision` | `qwen3-vl:32b-ctx16k` | Ollama | `ollama-vision` (ollama) | `ollama-vision` (ollama) | ollama | match | match |
| `auto-vision::gemma4jangvision` | `hf.co/douyamv/Gemma-4-31B-JANG_4M-CRACK-GGUF:gemma-4-31b-jang-crack-Q4_K_M.gguf-ctx8k` | Ollama | `ollama-vision` (ollama) | `ollama-vision` (ollama) | ollama | match | match |
| `auto-vision::gemma_vision` | `gemma4:31b-it-qat-ctx16k` | Ollama | `ollama-vision` (ollama) | `ollama-vision` (ollama) | ollama | match | match |
| `compliance-council-deepseek-r1` | `hf.co/unsloth/DeepSeek-R1-0528-Qwen3-8B-GGUF:Q4_K_XL-ctx64k` | Ollama | `omlx-reasoning` (omlx) | `ollama-reasoning` (ollama) | ollama | mismatch | match |
| `compliance-council-granite41` | `granite4.1:30b-ctx16k` | Ollama | `omlx-general` (omlx) | `ollama-general` (ollama) | ollama | mismatch | match |
| `compliance-council-qwen38` | `hf.co/unsloth/Qwen3.8-27B-GGUF:Q4_K_M-ctx32k` | Ollama | `omlx-general` (omlx) | `ollama-general` (ollama) | ollama | mismatch | match |
| `compliance-mapping` | `gemma4:26b-a4b-it-q4_K_M-ctx128k` | Ollama | `omlx-general` (omlx) | `ollama-general` (ollama) | omlx | match | mismatch |
| `compliance-reading-overflow` | `gemma4:26b-a4b-it-qat-ctx64k` | Ollama | `omlx-general` (omlx) | `ollama-general` (ollama) | omlx | match | mismatch |
| `hunt-reasoning` | `gemma4:26b-a4b-it-qat-ctx8k-hunt` | Ollama | `omlx-general` (omlx) | `omlx-general` (omlx) | omlx | match | match |
| `security-reviewer` | `granite4.1:8b-ctx16k` | Ollama | `ollama-general` (ollama) | `ollama-general` (ollama) | ollama | match | match |
| `tools-specialist` | `hf.co/unsloth/Qwen3.6-35B-A3B-GGUF:UD-Q4_K_XL-ctx96k` | Ollama | `omlx-general` (omlx) | `ollama-general` (ollama) | omlx | match | mismatch |
| `tools-specialist::fast` | `gemma4:e4b-it-qat-ctx8k` | Ollama | `ollama-general` (ollama) | `ollama-general` (ollama) | ollama | match | match |

## Findings

- The baseline hot-seat rule promoted an Ollama alias-capable fallback ahead of a priority-10 oMLX alias head when a different oMLX model had been active. The fix now treats any resolvable oMLX model hint as an eligible preferred seat, keeping configured order.
- The three compliance council workspaces had an oMLX configured first candidate despite the explicit co-resident council exception. The route now promotes the matching Ollama candidate for those three workspaces.
- The earlier handoff names 29 alias candidates. The current full production chain has 28 scenario mismatches: `hunt-reasoning` remains oMLX-first because its `max_concurrent > 1` batching policy restores the oMLX candidate after hot-seat protection; the other 28 flagged rows are shown above.
- Busy-aware failover probes oMLX `GET /api/status` (`active_requests` and `waiting_requests`), then requires the same-hint Ollama model in that backend's `/api/ps` and idle in `LoadGuard`. Probe failures fail open to configured oMLX routing. It starts no parallel request and triggers no model load.
- Local unit tests cover alias order, the council exception, busy-and-warm gating, and active/queued oMLX status. The orchestrator still owns live route proof.
