# Known Limitations

Architectural and design constraints that cannot be resolved without significant tradeoffs. These are accepted as part of Portal 5's design.

---

## Security

### Code Sandbox Requires Privileged Container
- **ID**: P5-ROAD-SEC-001
- **Description**: The `dind` (Docker-in-Docker) service runs with `privileged: true`. Docker-in-Docker cannot function without host kernel capabilities.
- **Impact**: In hardened environments, a compromised sandbox container could potentially escape to host.
- **Mitigation**: Either disable the code sandbox by removing `mcp-sandbox` and `dind` services from `docker-compose.yml`, or apply host-level controls (AppArmor/seccomp profile on the Docker daemon).
- **Last verified**: 2026-03-30

### No Built-in Multi-User Rate Limiting
- **ID**: P5-ROAD-031
- **Description**: Open WebUI does not have per-user rate limiting. A single user in a multi-user deployment could exhaust server resources.
- **Mitigation**: Deploy behind a reverse proxy (nginx, Traefik) with rate limiting, or use Open WebUI's admin controls to set per-user quotas.
- **Last verified**: 2026-03-03

---

## Infrastructure

### ComfyUI Runs Outside Docker
- **Description**: ComfyUI runs on the host (not in Docker) to access GPU directly (MPS on Apple Silicon, CUDA on NVIDIA). This is required for image/video generation performance.
- **Impact**: Manual setup required outside the `./launch.sh up` flow. On first run after a fresh machine, ComfyUI must be installed separately.
- **Documentation**: See `docs/COMFYUI_SETUP.md`
- **Mitigation**: `./launch.sh install-comfyui` handles the setup on supported platforms.
- **Last verified**: 2026-03-03

### Voice Cloning (fish-speech) Requires Separate Installation
- **Description**: Voice cloning via `fish-speech` is not included in the Docker stack — it requires host-side installation.
- **Impact**: Voice cloning is unavailable; TTS still works via the included `kokoro-onnx` engine.
- **Documentation**: See `docs/FISH_SPEECH_SETUP.md`
- **Mitigation**: `kokoro-onnx` provides text-to-speech out of the box with no extra setup.
- **Last verified**: 2026-03-03

---

## Models

### Persona workspace_model Values Fixed
- **ID**: P5-ROAD-MOD-001
- **Status**: **RESOLVED**
- **Description**: 9 persona YAMLs had `workspace_model` values that were either invalid Ollama identifiers or referenced HuggingFace paths that don't exist.
- **Root cause**: Ollama's `hf.co/` prefix imports models from HuggingFace under local Ollama names. The persona YAMLs were using HuggingFace paths directly (e.g., `hf.co/deepseek-ai/DeepSeek-R1-32B-GGUF`) which don't exist — the correct path is `bartowski/DeepSeek-R1-Distill-Qwen-32B-GGUF` and it's imported as `deepseek-r1:32b-q4_k_m`.
- **Resolution**:
  - `redteamoperator` → `baronllm:q6_k` (imported from `hf.co/AlicanKiraz0/Cybersecurity-BaronLLM_Offensive_Security_LLM_Q6_K_GGUF`); alternative: `xploiter/the-xploiter`
  - `blueteamdefender` → `lily-cybersecurity:7b-q4_k_m` (imported from `hf.co/segolilylabs/Lily-Cybersecurity-7B-v0.2-GGUF`); alternative: `huihui_ai/baronllm-abliterated`
  - `dataanalyst`, `datascientist`, `machinelearningengineer`, `statistician`, `itarchitect`, `researchanalyst`, `excelsheet` → `deepseek-r1:32b-q4_k_m` (the HF path `hf.co/deepseek-ai/DeepSeek-R1-32B-GGUF` doesn't exist; correct import is via `bartowski/DeepSeek-R1-Distill-Qwen-32B-GGUF`); alternative: `huihui_ai/tongyi-deepresearch-abliterated`
- **Last verified**: 2026-04-01

---

## Seeding / Init

### `openwebui-init` Skips Existing Personas and Workspaces on Re-Seed
- **ID**: P5-ROAD-INIT-001
- **Status**: **RESOLVED** — `./launch.sh reseed` now force-deletes and recreates all presets.
- **Description**: `scripts/openwebui_init.py` detects existing model presets and skips them on subsequent runs. The upsert path (PUT/POST to update) returns HTTP 405 against Open WebUI v0.6.5.
- **Resolution**: 
  - Discovered correct OW v0.6.5 API: `POST /api/v1/models/create` (create), `DELETE /api/v1/models/model/delete?id=` (delete), `POST /api/v1/models/model/update?id=` (update)
  - Added `FORCE_RESEED` env var to `openwebui_init.py` — deletes then recreates every preset
  - `./launch.sh reseed` invokes this path: delete all → recreate all with current YAML content
  - Also fixed: `base_model_id` must be set in all presets — OW v0.6.5 `get_models()` filters `WHERE base_model_id IS NOT NULL`, so presets without it are invisible to users
- **Usage**: After editing persona YAMLs or workspace JSONs, run `./launch.sh reseed` to push changes live.
- **Last verified**: 2026-04-01

---

*Last updated: 2026-04-01*
