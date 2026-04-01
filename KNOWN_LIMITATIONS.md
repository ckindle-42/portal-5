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

### Persona workspace_model Values Require Research
- **ID**: P5-ROAD-MOD-001
- **Description**: 9 persona YAMLs have `workspace_model` values that differ from the intended models documented in CLAUDE.md. The YAMLs currently use Ollama `hf.co/` HuggingFace pull identifiers while CLAUDE.md documents specific Ollama registry tags. This may be intentional (personas tuned for specific GGUF variants) or unintended drift.
- **Affected personas**: `redteamoperator`, `blueteamdefender`, `dataanalyst`, `datascientist`, `machinelearningengineer`, `statistician`, `itarchitect`, `researchanalyst`, `excelsheet`
- **Current values**: `redteamoperator` → `hf.co/AlicanKiraz0/Cybersecurity-BaronLLM_Offensive_Security_LLM_Q6_K_GGUF`; `blueteamdefender` → `hf.co/segolilylabs/Lily-Cybersecurity-7B-v0.2-GGUF`; data/research personas → `hf.co/deepseek-ai/DeepSeek-R1-32B-GGUF`
- **CLAUDE.md intent**: `redteamoperator` → `xploiter/the-xploiter`; `blueteamdefender` → `huihui_ai/baronllm-abliterated`; data/research personas → `huihui_ai/tongyi-deepresearch-abliterated`
- **Action needed**: Verify whether the GGUF-specific variants are tuned for their persona tasks before aligning to CLAUDE.md or updating CLAUDE.md to match.
- **Last verified**: 2026-04-01

---

## Seeding / Init

### `openwebui-init` Skips Existing Personas and Workspaces on Re-Seed
- **ID**: P5-ROAD-INIT-001
- **Description**: `scripts/openwebui_init.py` detects existing model presets and skips them on subsequent runs. The upsert path (PUT/POST to update) returns HTTP 405 against Open WebUI v0.6.5, meaning updated `system_prompt` content in persona YAMLs is never pushed to the live instance after the first seed. This is the same pattern used for workspace model refreshes.
- **Impact**: Persona prompt upgrades, workspace toolId changes, and system prompt edits require manual action to take effect in a running Open WebUI instance. `./launch.sh seed` silently no-ops for already-seeded items.
- **Mitigation options**:
  1. Delete and re-create: delete the model preset via Open WebUI Admin UI, then re-run `docker compose run --rm openwebui-init`
  2. Add a `--force` / `--reseed` flag to `openwebui_init.py` that deletes before creating (needs investigation of correct v0.6.5 DELETE endpoint)
  3. On startup, always re-seed if YAML content hash differs from stored preset (requires storing hashes)
- **Desired behavior**: Startup seeding should behave like container image pulls — re-apply if content changed, skip if identical. Similar to how `docker compose up --build` rebuilds changed images.
- **Last verified**: 2026-04-01

---

*Last updated: 2026-04-01*
