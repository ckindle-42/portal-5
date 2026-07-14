# Portal 7.6.0 — Admin Guide

## First Login

After `./launch.sh up`, credentials are printed to the console and saved in `.env`.
Log in at `http://localhost:8080` with the generated admin account.

## User Management

### Approve Pending Users
1. Admin Panel > Users
2. Find users with "pending" role
3. Click the user > set role to "user"

### Create Users via CLI
```bash
./launch.sh add-user alice@team.local "Alice Smith"
./launch.sh add-user bob@team.local "Bob Jones" admin
./launch.sh list-users
```

### User Roles
- `pending` — cannot use the system, waiting for approval
- `user` — standard access to workspaces, tools, chat
- `admin` — full access including user management and all settings

## Model Management

### Pull Additional Models
```bash
./launch.sh pull-models
# Pulls: xploiter, whiterabbitneo, baronllm, tongyi, qwen3-coder, devstral, etc.
# Takes 30-90 minutes depending on connection speed
```

### Add a Cluster Node
Edit `config/backends.yaml` — see `docs/CLUSTER_SCALE.md`.

## Routine Operations

```bash
./launch.sh status      # Check service health
./launch.sh logs        # Pipeline logs (default)
./launch.sh logs ollama # Ollama logs
./launch.sh seed        # Re-seed workspaces/personas (after config changes)
./launch.sh down        # Stop all services (data preserved)
./launch.sh clean       # Wipe Open WebUI data (fresh start, Ollama models kept)
```

## Security Notes

- Generated secrets are in `.env` — never commit this file
- PIPELINE_API_KEY protects the routing API — rotate if compromised
- WEBUI_SECRET_KEY secures user sessions — rotation requires all users to re-login
- To rotate secrets: edit `.env`, restart stack

## Network Exposure

Portal 5 is designed for single-machine local use. Open WebUI binds to `127.0.0.1` by default and is only reachable from `localhost`. All MCP servers (8910–8923) are always 127.0.0.1-bound and never reach the network directly.

### Recommended remote access: Cloudflare Tunnel

Run `cloudflared` on the host and configure ingress rules that route specific paths to the local services. The MCP servers stay loopback-only — cloudflared (running on the host, not in docker) reaches them through `127.0.0.1`. A reference ingress configuration is provided at `config/cloudflared/config.yml.example`.

To make generated media links work for remote browsers:

```
ENABLE_REMOTE_ACCESS=true
PORTAL_PUBLIC_URL=https://portal.example.com
```

`launch.sh` derives `MUSIC_PUBLIC_URL`, `TTS_PUBLIC_URL`, `VIDEO_PUBLIC_URL`, and `COMFYUI_PUBLIC_URL` from `PORTAL_PUBLIC_URL`, and the MCPs emit those into chat instead of `http://localhost:<port>/...`.

Without `PORTAL_PUBLIC_URL` set, every MCP falls back to localhost-only links — Open WebUI can still be reached remotely, but media download links inside chat won't resolve from a remote browser.

### Alternative: LAN reverse proxy (Caddy / nginx)

For deployments that don't use Cloudflare Tunnel, a Caddy or nginx reverse proxy on the same machine can serve the same role. Reverse-proxy `/files/{music,tts,video}/*` and `/comfyui/*` to the corresponding loopback ports, set `PORTAL_PUBLIC_URL` to the proxy's public address, and the same env-var derivation works. A first-class Caddy profile in `docker-compose.yml` is on the roadmap but not yet implemented.

**Never expose the MCP ports directly to the internet.** Routing only `/files/{kind}/*` keeps the rest of the MCP API surface private.

The pipeline API (port 9099) and all MCP servers (8910–8923) are always bound to 127.0.0.1 and are not reachable externally under any configuration. Cloudflare Tunnel reaches them via the host loopback only because cloudflared itself runs on the host.

> **Note:** Grafana (port 3000) binds to `0.0.0.0:3000` and **is** reachable from other machines on your network. Grafana requires login (`admin` / `GRAFANA_PASSWORD` from `.env`) and does not expose inference data — but if your LAN is untrusted, restrict it with a firewall rule or set `GF_SERVER_HTTP_ADDR=127.0.0.1` in `docker-compose.yml`.

## Backup

Critical data is in Docker volumes:
- `portal-5_open-webui-data` — all user accounts, chat history, settings
- `portal-5_ollama-models` — downloaded model weights (replaceable, not personal data)

```bash
# Easiest: use the launch script (saves to ./backups/)
./launch.sh backup

# Or manually (Open WebUI):
docker run --rm -v portal-5_open-webui-data:/data -v $(pwd):/backup \
    alpine tar czf /backup/openwebui-backup-$(date +%Y%m%d).tar.gz /data
```

## Inference Health Monitoring

Portal 5 runs a single inference backend: **Ollama** (:11434). The MLX inference proxy
(:8081/:18081/:18082) was retired in commit 3a0c58e.

### Debugging crashes

```bash
# Check Ollama health and model list
curl -s http://localhost:11434/api/tags | jq .

# Check pipeline health
curl -s http://localhost:9099/health/all | jq .

# Check all services
./launch.sh status
```

---

## Router Configuration

### How the LLM Router Works

The pipeline routes every `auto` workspace request through a **two-layer intent classifier**:

- **Layer 1 — LLM router** (`portal/platform/inference/router/routing.py`): A small model classifies intent via Ollama `/api/generate` with grammar-enforced JSON output. Result: `{"workspace": "<id>", "confidence": 0.0–1.0}`. Fast, accurate.
- **Layer 2 — Keyword scoring** (`portal/platform/inference/router/routing.py`): Weighted keyword match. Fires when LLM router times out, returns low confidence, or errors.

### Three-Tier Router Models

Three models are available; select via `LLM_ROUTER_MODEL` in `.env`:

| Tier | Model | Accuracy | p50 Latency | VRAM | When to use |
|------|-------|----------|-------------|------|-------------|
| **PRIMARY** | `hf.co/mradermacher/gemma-4-E4B-it-OBLITERATED-GGUF:Q4_K_M` | 82.2% | ~840ms | 5.3GB | Default — best accuracy |
| **STANDBY** | `llama3.2:3b` | 75.3% | ~433ms | ~2GB | If PRIMARY is evicted frequently in your fleet |
| **FALLBACK** | `qwen2.5:1.5b` | 67.1% | ~339ms | 1GB | Extremely memory-constrained; stays hot under any fleet load |

Accuracy figures are from `tests/benchmarks/bench_router.py` (36-query GOLDEN_SET, 3 rounds).

### OLLAMA_MAX_LOADED_MODELS=3

The Ollama slot count is set to **3** (not 2) for two reasons:

**1. Router keep-warm.** The router model holds its own slot alongside two inference models. Without this, Ollama evicts the router to make room for inference models — the first request after eviction falls back to Layer 2 keyword scoring while the router cold-loads.

**Cold-load times** (after eviction): PRIMARY 4.2s · STANDBY 2.4s · FALLBACK 1.6s. All exceed the production `LLM_ROUTER_TIMEOUT_MS` limit, so the first post-eviction request always goes to Layer 2 — exactly one fallback, then the router reloads and stays warm.

**2. Security multi-chain operations.** The purple team and security exec-chain workspaces (auto-security's `purpleteam`/`purpleteam-deep`/`purpleteam-exec` variants, folded in BUILD_PROGRAM_COLLAPSE_V1.md Phase 6) run multi-hop model chains where two inference models need to be simultaneously warm: the attack model and the defender/blue-team model. The bench exec-chain driver (`portal/modules/security/core/commands/run.py`) explicitly relies on `MAX_LOADED=3` to pre-warm all chain models before any chain prompt runs — it evicts non-chain inference models first, then fills all 3 slots with chain models so no mid-chain eviction occurs.

In production, the purple team chain steps execute sequentially (not concurrently), but having both models loaded avoids a cold-load stall between hops. With `MAX_LOADED=2`, the second chain model evicts the first, causing a cold-load on every hop reversal.

**Bench parallelism (added 2026-06-29).** The default `MAX_LOADED` has been raised to **5**
to support `tests/benchmarks/bench_security.py --parallel-workspaces N` (default N=2).
The 4-hop `purpleteam-deep` variant chain needs 4 distinct chain models hot; without `MAX_LOADED>=4`
Ollama evicts and re-cold-loads between hops, defeating the parallelism gain. Operators running
the security bench in parallel should verify the live Ollama process picks up the new value
(`ps eww -p $(pgrep -f "ollama serve") | tr ' ' '\n' | grep OLLAMA_MAX_LOADED`).

### Changing the Router Model

All three variables live in `.env`:
```bash
LLM_ROUTER_MODEL=hf.co/mradermacher/gemma-4-E4B-it-OBLITERATED-GGUF:Q4_K_M
LLM_ROUTER_TIMEOUT_MS=1000   # 1000 for PRIMARY, 500 for STANDBY/FALLBACK
OLLAMA_MAX_LOADED_MODELS=5
```

Then restart the pipeline (not Ollama):
```bash
docker compose -f deploy/portal-5/docker-compose.yml restart portal-pipeline
```

### Ollama is Native — Plist Is the Source of Truth

Ollama runs under launchd, not Docker. Docker-compose env vars pass through to the pipeline container but **do not affect Ollama itself**. The authoritative config is:

```
~/Library/LaunchAgents/homebrew.mxcl.ollama.plist
```

To change `OLLAMA_MAX_LOADED_MODELS` (or add `OLLAMA_MEMORY_LIMIT`), edit the plist and reload:

```bash
# Edit the plist, then:
launchctl unload ~/Library/LaunchAgents/homebrew.mxcl.ollama.plist
launchctl load  ~/Library/LaunchAgents/homebrew.mxcl.ollama.plist

# Verify the new value was picked up:
ps eww -p $(pgrep -f "ollama serve") | tr ' ' '\n' | grep OLLAMA_MAX_LOADED
```

### Runtime VRAM vs File Size Gap

Ollama allocates KV cache at model-load time. Runtime resident size is **significantly larger** than the model file:

| Model | File size | Runtime VRAM | Driver |
|-------|-----------|--------------|--------|
| devstral:24b | 14.3 GB | ~25.7 GB | Large default context window |
| granite4.1:8b | 5.3 GB | ~16.8 GB | Large context + KV q8_0 |
| OBLITERATED E4B | 5.3 GB | ~5.3 GB | Compact architecture |

**devstral:24b specifically**: its 25.7 GB runtime footprint can cause memory-pressure eviction of other models regardless of `MAX_LOADED_MODELS`. This is expected graceful behavior — Ollama offloads CPU layers rather than crashing (unlike MLX Metal OOM). If devstral evicts the router, Layer 2 keyword scoring handles that one request, then the router reloads. Not a bug.

### OLLAMA_MEMORY_LIMIT (deferred)

`OLLAMA_MEMORY_LIMIT` is currently **not set** (unlimited). On the M4 Pro 64GB, worst-case slot composition (router 5.3GB + devstral 25.7GB + granite 16.8GB) can hit ~47.8GB — well within budget. Ollama gracefully offloads to CPU before crashing, but if kernel panics or Metal OOM errors appear under heavy multi-model loads, add to the plist:

```xml
<key>OLLAMA_MEMORY_LIMIT</key>
<string>42g</string>
```

42 GB leaves ~6 GB for macOS + pipeline + Open WebUI.

### Verifying Router Is Warm

```bash
# Check which models Ollama currently has loaded
curl -s http://localhost:11434/api/ps | jq '.models[] | {name, size_vram}'

# Check pipeline logs for router decisions
./launch.sh logs | grep -E "LLM router|Routing workspace|keyword fallback" | tail -20

# Pull router model if not yet downloaded
ollama pull hf.co/mradermacher/gemma-4-E4B-it-OBLITERATED-GGUF:Q4_K_M
```

### Router Benchmarks

To re-validate router accuracy after model changes:
```bash
# Accuracy across 36-query GOLDEN_SET
OLLAMA_URL=http://localhost:11434 python3 tests/benchmarks/bench_router.py

# VRAM eviction and cold-load conditions bench (3 router candidates × 4 scenarios)
OLLAMA_URL=http://localhost:11434 python3 tests/benchmarks/bench_router_conditions.py \
  --companions devstral:24b granite4.1:8b
```

Results are written to `tests/benchmarks/results/`.

## Live Facts (Generated)

The tables below are generated from `portal_wiki/canonical/` fact units —
computed from live config on every `sync-config` run
(DESIGN_WIKI_GENERATION_LOOP_V1.md). Do not hand-edit inside the markers;
edit the source config and re-run `sync-config` instead.

### Personas

<!-- WIKI:GENERATED unit=unit-fact-persona-roster -->
# Persona roster (138 personas)

| Slug | Module | Workspace | Model Pin |
|---|---|---|---|
| `adversarysimulator` | security | `auto-security` | — |
| `agenticheavy` | coding | `auto-coding` | — |
| `agenticlite` | coding | `auto-coding` | — |
| `agentorchestrator` | coding | `auto-coding` | — |
| `bench-devstral` | eval | `bench-devstral-small-2` | — |
| `bench-devstral-small-2` | eval | `bench-devstral-small-2` | — |
| `bench-gemma4-12b` | eval | `bench-gemma4-12b` | — |
| `bench-gemma4-26b-optiq` | eval | `bench-gemma4-26b-optiq` | — |
| `bench-gemma4-26b-qat` | eval | `bench-gemma4-26b-qat` | — |
| `bench-gemma4-31b-qat` | eval | `bench-gemma4-31b-qat` | — |
| `bench-gemma4-e2b` | eval | `bench-gemma4-e2b` | — |
| `bench-gemma4-e4b` | eval | `bench-gemma4-e4b` | — |
| `bench-gemma4-e4b-qat` | eval | `bench-gemma4-e4b-qat` | — |
| `bench-glm` | eval | `bench-glm` | — |
| `bench-glm-reap` | eval | `bench-glm-reap` | — |
| `bench-glm-z1-rumination` | eval | `bench-glm-z1-rumination` | — |
| `bench-gptoss` | eval | `bench-gptoss` | — |
| `bench-granite41-30b` | eval | `bench-granite41-30b` | — |
| `bench-granite41-8b` | eval | `bench-granite41-8b` | — |
| `bench-huihui-qwen36-27b` | eval | `bench-huihui-qwen36-27b` | — |
| `bench-huihui-qwen36-35b-a3b` | eval | `bench-huihui-qwen36-35b-a3b` | — |
| `bench-laguna` | eval | `bench-laguna` | — |
| `bench-lfm25-8b` | eval | `bench-lfm25-8b` | — |
| `bench-lfm25-8b-uncensored` | eval | `bench-lfm25-8b-uncensored` | — |
| `bench-nex-n2-mini` | eval | `bench-nex-n2-mini` | — |
| `bench-omnicoder2` | eval | `bench-omnicoder2` | — |
| `bench-qwen35-abliterated` | eval | `bench-qwen35-abliterated` | — |
| `bench-qwen36-27b` | eval | `bench-qwen36-27b` | — |
| `bench-qwen36-27b-mtp` | eval | `bench-qwen36-27b-mtp` | — |
| `bench-qwen36-27b-optiq` | eval | `bench-qwen36-27b-optiq` | — |
| `bench-qwen36-27b-ud` | eval | `bench-qwen36-27b-ud` | — |
| `bench-qwen36-35b-a3b` | eval | `bench-qwen36-35b-a3b` | — |
| `bench-qwen36-35b-a3b-ud` | eval | `bench-qwen36-35b-a3b-ud` | — |
| `bench-qwen36-abl-27b` | eval | `bench-huihui-qwen36-27b` | — |
| `bench-qwen36-hauhaucs` | eval | `bench-qwen36-hauhaucs` | — |
| `bench-qwen3-coder-30b` | eval | `bench-qwen3-coder-30b` | — |
| `bench-qwen3-coder-next` | eval | `bench-qwen3-coder-next` | — |
| `bench-qwen3-coder-next-abliterated` | eval | `bench-qwen3-coder-next-abliterated` | — |
| `blueteamdefender` | security | `auto-security` | — |
| `bugdiscoverycodeassistant` | coding | `auto-coding` | — |
| `businessanalyst` | general | `auto-reasoning` | — |
| `cadquerydesigner` | cad | `auto-cad` | — |
| `chartanalyst` | general | `auto-vision` | — |
| `cippolicywriter` | compliance | `auto-compliance` | — |
| `codebasewikidocumentationskill` | coding | `auto-coding` | — |
| `codereviewassistant` | coding | `auto-coding` | — |
| `codereviewer` | coding | `auto-coding` | — |
| `codescreenshotreader` | general | `auto-vision` | — |
| `codingagentic` | coding | `auto-coding` | — |
| `codinguncensored` | coding | `auto-coding` | — |
| `codinguncensoredagentic` | coding | `auto-coding` | — |
| `complianceanalyst` | compliance | `auto-compliance` | — |
| `creativecoder` | coding | `auto-coding` | — |
| `creativewriter` | media | `auto-creative` | — |
| `cybersecurityspecialist` | security | `auto-security` | — |
| `dailydriver` | general | `auto-daily` | — |
| `dashboardarchitect` | research | `auto-data` | — |
| `dataanalyst` | research | `auto-data` | — |
| `databasearchitect` | research | `auto-data` | — |
| `dataextractor` | research | `auto-data` | — |
| `datascientist` | research | `auto-data` | — |
| `devopsautomator` | coding | `auto-coding` | — |
| `devopsengineer` | general | `auto-reasoning` | — |
| `devstral_coder` | coding | `auto-coding` | `devstral-small-2:latest-ctx8k` |
| `diagramreader` | general | `auto-vision` | — |
| `documentationarchitect` | documents | `auto-documents` | — |
| `e2edebugger` | coding | `auto-coding` | — |
| `e2etestauthor` | coding | `auto-coding` | — |
| `ethereumdeveloper` | coding | `auto-coding` | — |
| `excelsheet` | coding | `auto-coding` | — |
| `factchecker` | research | `auto-research` | — |
| `formfiller` | coding | `auto-coding` | — |
| `fullstacksoftwaredeveloper` | coding | `auto-coding` | — |
| `gdprdpoadvisor` | compliance | `auto-compliance` | — |
| `gemma4e4bvision` | general | `auto-vision` | — |
| `gemma4jangvision` | general | `auto-vision` | `hf.co/douyamv/Gemma-4-31B-JANG_4M-CRACK-GGUF:gemma-4-31b-jang-crack-Q4_K_M.gguf` |
| `gemma_e4b` | general | `auto-daily` | — |
| `gemma_fast` | general | `auto-daily` | — |
| `gemma_vision` | general | `auto-vision` | `gemma4:31b-it-qat-ctx8k` |
| `gemmaresearchanalyst` | research | `auto-research` | — |
| `githubexpert` | coding | `auto-coding` | — |
| `glm-coder` | coding | `auto-coding` | `hf.co/unsloth/GLM-4.7-Flash-REAP-23B-A3B-GGUF:UD-Q4_K_XL-ctx64k` |
| `glm-thinker` | general | `auto-reasoning` | `hf.co/bartowski/THUDM_GLM-Z1-Rumination-32B-0414-GGUF:THUDM_GLM-Z1-Rumination-32B-0414-Q4_K_M.gguf-ctx64k` |
| `goengineer` | coding | `auto-coding` | — |
| `gptossanalyst` | general | `auto-reasoning` | — |
| `hermes3writer` | media | `auto-creative` | — |
| `hipaaprivacyofficer` | compliance | `auto-compliance` | — |
| `interviewcoach` | media | `auto-creative` | — |
| `itarchitect` | general | `auto-reasoning` | — |
| `itexpert` | general | `auto` | — |
| `javascriptconsole` | coding | `auto-coding` | — |
| `kbnavigator` | research | `auto-research` | — |
| `kubernetesdockerrpglearningengine` | coding | `auto-coding` | — |
| `linuxterminal` | coding | `auto-coding` | — |
| `machinelearningengineer` | research | `auto-data` | — |
| `magistralstrategist` | general | `auto-reasoning` | `hf.co/unsloth/Magistral-Small-2509-GGUF:Q8_0-ctx64k` |
| `marketanalyst` | research | `auto-research` | — |
| `mathreasoner` | general | `auto-math` | — |
| `nerccipcomplianceanalyst` | compliance | `auto-compliance` | — |
| `networkengineer` | security | `auto-security` | — |
| `ocrspecialist` | general | `auto-vision` | — |
| `paywalledresearcher` | research | `auto-research` | — |
| `pcidssassessor` | compliance | `auto-compliance` | — |
| `pentester` | security | `auto-security` | — |
| `pentestlead` | security | `auto-security` | — |
| `personalassistant` | general | `auto-daily` | — |
| `phi4specialist` | documents | `auto-documents` | — |
| `phi4stemanalyst` | general | `auto-reasoning` | — |
| `printabilityengineer` | cad | `auto-cad` | — |
| `productmanager` | general | `auto-reasoning` | — |
| `proofreader` | media | `auto-creative` | — |
| `purpleteamexec` | security | `auto-security` | — |
| `purpleteamlead` | security | `auto-security` | — |
| `pythoncodegeneratorcleanoptimizedproduction-ready` | coding | `auto-coding` | — |
| `pythoninterpreter` | coding | `auto-coding` | — |
| `redteamoperator` | security | `auto-security` | — |
| `researchanalyst` | research | `auto-research` | — |
| `rustengineer` | coding | `auto-coding` | — |
| `securityuncensored` | security | `auto-security` | — |
| `seniorfrontenddeveloper` | coding | `auto-coding` | — |
| `seniorsoftwareengineersoftwarearchitectrules` | general | `auto-reasoning` | — |
| `soc2auditor` | compliance | `auto-compliance` | — |
| `softwarequalityassurancetester` | coding | `auto-coding` | — |
| `splunkdetectionauthor` | general | `auto-spl` | — |
| `splunksplgineer` | general | `auto-spl` | — |
| `sqlterminal` | coding | `auto-coding` | — |
| `statistician` | research | `auto-data` | — |
| `supergemma4researcher` | research | `auto-research` | — |
| `techreviewer` | general | `auto` | — |
| `techwriter` | documents | `auto-documents` | — |
| `terraformwriter` | coding | `auto-coding` | — |
| `toolcomposer` | general | `tools-specialist` | — |
| `transcriptanalyst` | documents | `auto-documents` | — |
| `typescriptengineer` | coding | `auto-coding` | — |
| `ux-uideveloper` | coding | `auto-coding` | — |
| `webnavigator` | general | `auto` | — |
| `webresearcher` | research | `auto-research` | — |
| `whiteboardconverter` | general | `auto-vision` | — |
<!-- /WIKI:GENERATED -->

### Workspaces

<!-- WIKI:GENERATED unit=unit-fact-workspace-roster -->
# Workspace roster (21 production, 60 eval, 81 total)

## Production workspaces (acceptance/UAT scope, eval OFF)

| Workspace | Module | Model Hint |
|---|---|---|
| `auto` | general | `huihui_ai/qwen3.5-abliterated:9b-ctx8k` |
| `auto-audio` | media | `gemma4:12b-it-qat-ctx8k` |
| `auto-bigfix` | general | `qwen3-coder:30b-a3b-q4_K_M-ctx16k` |
| `auto-cad` | cad | `qwen3-coder:30b-a3b-q4_K_M-ctx8k` |
| `auto-coding` | coding | `qwen3-coder:30b-a3b-q4_K_M-ctx16k` |
| `auto-compliance` | compliance | `granite4.1:8b-ctx16k` |
| `auto-creative` | media | `fredrezones55/Qwen3.6-35B-A3B-Uncensored-HauhauCS-Aggressive:Q4-ctx8k` |
| `auto-daily` | general | `gemma4:26b-a4b-it-qat-ctx8k` |
| `auto-data` | research | `granite4.1:30b-ctx64k` |
| `auto-documents` | documents | `granite4.1:8b-ctx16k` |
| `auto-extract-uncensored` | documents | `hf.co/gaston-parravicini/LFM2.5-8B-A1B-Uncensored-Gaston-GGUF:Q4_K_M-ctx8k` |
| `auto-general-uncensored` | general | `huihui_ai/Qwen3.6-abliterated:27b-ctx8k` |
| `auto-math` | general | `phi4-mini-reasoning:latest-ctx24k` |
| `auto-music` | media | `lfm2.5:8b-ctx8k` |
| `auto-reasoning` | general | `hf.co/unsloth/DeepSeek-R1-0528-Qwen3-8B-GGUF:Q4_K_XL-ctx64k` |
| `auto-research` | research | `huihui_ai/tongyi-deepresearch-abliterated:latest-ctx64k` |
| `auto-security` | security | `hf.co/mradermacher/VulnLLM-R-7B-GGUF:Q4_K_M-ctx8k` |
| `auto-spl` | general | `hf.co/bartowski/huihui-ai_Qwen3-Coder-Next-abliterated-GGUF:Q4_K_M-ctx64k` |
| `auto-video` | media | `granite4.1:8b-ctx16k` |
| `auto-vision` | general | `qwen3-vl:32b-ctx8k` |
| `tools-specialist` | general | `granite4.1:8b-ctx8k` |

## Eval/bench workspaces (need PORTAL_ENABLE_EVAL=1)

- `bench-agents-a1`
- `bench-agentworld`
- `bench-bugtrace-ultra-27b`
- `bench-cybersecqwen-4b-toolfix`
- `bench-devstral`
- `bench-devstral-small-2`
- `bench-e2b-pentest`
- `bench-exec-exploit`
- `bench-exec-reasoning`
- `bench-exec-recon`
- `bench-fastcontext`
- `bench-gemma4-12b`
- `bench-gemma4-12b-agentic`
- `bench-gemma4-26b-optiq`
- `bench-gemma4-26b-qat`
- `bench-gemma4-31b-crack`
- `bench-gemma4-31b-qat`
- `bench-gemma4-e2b`
- `bench-gemma4-e4b`
- `bench-gemma4-e4b-qat`
- `bench-glm`
- `bench-glm-reap`
- `bench-glm-z1-rumination`
- `bench-gptoss`
- `bench-granite41-30b`
- `bench-granite41-8b`
- `bench-huihui-qwen36-27b`
- `bench-huihui-qwen36-35b-a3b`
- `bench-laguna`
- `bench-lfm-micro-1p2b`
- `bench-lfm-micro-230m`
- `bench-lfm-micro-350m`
- `bench-lfm25-8b`
- `bench-lfm25-8b-uncensored`
- `bench-meta-secalign-8b`
- `bench-mistral7b-uncensored`
- `bench-nex-n2-mini`
- `bench-north-mini-code`
- `bench-omnicoder2`
- `bench-ornith-35b`
- `bench-qwable-35b`
- `bench-qwen3-14b-abliterated`
- `bench-qwen3-coder-30b`
- `bench-qwen3-coder-next`
- `bench-qwen3-coder-next-abliterated`
- `bench-qwen35-9b-heretic-vision`
- `bench-qwen35-abliterated`
- `bench-qwen36-27b`
- `bench-qwen36-27b-mtp`
- `bench-qwen36-27b-optiq`
- `bench-qwen36-27b-ud`
- `bench-qwen36-35b-a3b`
- `bench-qwen36-35b-a3b-ud`
- `bench-qwen36-hauhaucs`
- `bench-qwopus-coder-mtp-v2`
- `bench-security-slm-1p5b`
- `bench-supergemma4-sec`
- `bench-superqwen-agentworld-ablit`
- `bench-sylink`
- `bench-vulnllm-r7b`
<!-- /WIKI:GENERATED -->

### Model Bindings (reachability-resolved)

<!-- WIKI:GENERATED unit=unit-fact-model-bindings -->
# Model bindings (reachability-resolved)

What each production workspace/persona actually SERVES, not what it
claims. A row marked GAP means the intended model is unreachable via
the workspace's routing groups and silently falls back to the pool
default.

## Workspace model_hint reachability

| Workspace | model_hint | Reachable |
|---|---|---|
| `auto` | `huihui_ai/qwen3.5-abliterated:9b-ctx8k` | yes |
| `auto-audio` | `gemma4:12b-it-qat-ctx8k` | yes |
| `auto-bigfix` | `qwen3-coder:30b-a3b-q4_K_M-ctx16k` | yes |
| `auto-cad` | `qwen3-coder:30b-a3b-q4_K_M-ctx8k` | yes |
| `auto-coding` | `qwen3-coder:30b-a3b-q4_K_M-ctx16k` | yes |
| `auto-compliance` | `granite4.1:8b-ctx16k` | yes |
| `auto-creative` | `fredrezones55/Qwen3.6-35B-A3B-Uncensored-HauhauCS-Aggressive:Q4-ctx8k` | yes |
| `auto-daily` | `gemma4:26b-a4b-it-qat-ctx8k` | yes |
| `auto-data` | `granite4.1:30b-ctx64k` | yes |
| `auto-documents` | `granite4.1:8b-ctx16k` | yes |
| `auto-extract-uncensored` | `hf.co/gaston-parravicini/LFM2.5-8B-A1B-Uncensored-Gaston-GGUF:Q4_K_M-ctx8k` | yes |
| `auto-general-uncensored` | `huihui_ai/Qwen3.6-abliterated:27b-ctx8k` | yes |
| `auto-math` | `phi4-mini-reasoning:latest-ctx24k` | yes |
| `auto-music` | `lfm2.5:8b-ctx8k` | yes |
| `auto-reasoning` | `hf.co/unsloth/DeepSeek-R1-0528-Qwen3-8B-GGUF:Q4_K_XL-ctx64k` | yes |
| `auto-research` | `huihui_ai/tongyi-deepresearch-abliterated:latest-ctx64k` | yes |
| `auto-security` | `hf.co/mradermacher/VulnLLM-R-7B-GGUF:Q4_K_M-ctx8k` | yes |
| `auto-spl` | `hf.co/bartowski/huihui-ai_Qwen3-Coder-Next-abliterated-GGUF:Q4_K_M-ctx64k` | yes |
| `auto-video` | `granite4.1:8b-ctx16k` | yes |
| `auto-vision` | `qwen3-vl:32b-ctx8k` | yes |
| `tools-specialist` | `granite4.1:8b-ctx8k` | yes |

## Persona model_pin reachability

| Persona | Workspace | model_pin | Reachable |
|---|---|---|---|
| `devstral_coder` | `auto-coding` | `devstral-small-2:latest-ctx8k` | yes |
| `gemma4jangvision` | `auto-vision` | `hf.co/douyamv/Gemma-4-31B-JANG_4M-CRACK-GGUF:gemma-4-31b-jang-crack-Q4_K_M.gguf` | yes |
| `gemma_vision` | `auto-vision` | `gemma4:31b-it-qat-ctx8k` | yes |
| `glm-coder` | `auto-coding` | `hf.co/unsloth/GLM-4.7-Flash-REAP-23B-A3B-GGUF:UD-Q4_K_XL-ctx64k` | yes |
| `glm-thinker` | `auto-reasoning` | `hf.co/bartowski/THUDM_GLM-Z1-Rumination-32B-0414-GGUF:THUDM_GLM-Z1-Rumination-32B-0414-Q4_K_M.gguf-ctx64k` | yes |
| `magistralstrategist` | `auto-reasoning` | `hf.co/unsloth/Magistral-Small-2509-GGUF:Q8_0-ctx64k` | yes |

**0 reachability gap(s)** — clean.
<!-- /WIKI:GENERATED -->

### MCP Fleet

<!-- WIKI:GENERATED unit=unit-fact-mcp-fleet -->
# MCP fleet (24 servers)

| ID | Name | Port |
|---|---|---|
| `filesystem` | filesystem |  |
| `fetch` | fetch |  |
| `git` | git |  |
| `docker` | docker |  |
| `comfyui` | portal-comfyui | 8910 |
| `video` | portal-video | 8911 |
| `music` | portal-music | 8912 |
| `documents` | portal-documents | 8913 |
| `execution` | portal-sandbox | 8914 |
| `whisper` | portal-whisper | 8915 |
| `tts` | portal-tts | 8916 |
| `security` | portal-security | 8919 |
| `memory` | portal-memory | 8920 |
| `rag` | portal-rag | 8921 |
| `research` | portal-research | 8922 |
| `browser` | portal-browser | 8923 |
| `mlx_transcribe` | portal-mlx-transcribe | 8924 |
| `reranker` | portal-reranker | 8925 |
| `cad_render` | portal-cad-render | 8926 |
| `proxmox` | portal-proxmox | 8927 |
| `pipeline` | portal-pipeline | 8928 |
| `mitre` | portal-mitre | 8929 |
| `wiki` | portal-wiki | 8931 |
| `detections` | portal-detections | 8932 |
<!-- /WIKI:GENERATED -->

### Model Catalog

<!-- WIKI:GENERATED unit=unit-fact-model-catalog -->
# Model catalog (149 model ids across 6 backend groups)

## coding (39)

- `devstral-small-2`
- `devstral-small-2:latest-ctx8k`
- `devstral:24b`
- `glm-4.7-flash:Q4_K_M`
- `gpt-oss:20b`
- `hf.co/Abiray/Agents-A1-Q4_K_M-GGUF:Q4_K_M`
- `hf.co/Jiunsong/SuperQwen-AgentWorld-35B-A3B-abliterated-gguf-4bit:Q4_K_M`
- `hf.co/Mia-AiLab/Qwable-3.6-35b:Qwable-3.6-35b_q4_k_m.gguf`
- `hf.co/bartowski/Qwen_Qwen3.6-27B-GGUF:Q4_K_M`
- `hf.co/bartowski/THUDM_GLM-Z1-Rumination-32B-0414-GGUF:THUDM_GLM-Z1-Rumination-32B-0414-Q4_K_M.gguf`
- `hf.co/bartowski/THUDM_GLM-Z1-Rumination-32B-0414-GGUF:THUDM_GLM-Z1-Rumination-32B-0414-Q4_K_M.gguf-ctx64k`
- `hf.co/bartowski/huihui-ai_Qwen3-Coder-Next-abliterated-GGUF:Q4_K_M`
- `hf.co/bartowski/huihui-ai_Qwen3-Coder-Next-abliterated-GGUF:Q4_K_M-ctx64k`
- `hf.co/coder543/North-Mini-Code-1.0-QAD-GGUF:NVFP4`
- `hf.co/coder543/North-Mini-Code-1.0-QAD-GGUF:NVFP4-ctx8k`
- `hf.co/deepreinforce-ai/Ornith-1.0-35B-GGUF:Q4_K_M`
- `hf.co/deepreinforce-ai/Ornith-1.0-35B-GGUF:Q4_K_M-ctx64k`
- `hf.co/mitkox/FastContext-1.0-4B-SFT-Q4_K_M-GGUF:Q4_K_M`
- `hf.co/sjakek/Nex-N2-mini-GGUF:UD-Q4_K_M`
- `hf.co/unsloth/GLM-4.7-Flash-REAP-23B-A3B-GGUF:UD-Q4_K_XL`
- `hf.co/unsloth/GLM-4.7-Flash-REAP-23B-A3B-GGUF:UD-Q4_K_XL-ctx64k`
- `hf.co/unsloth/Qwen-AgentWorld-35B-A3B-GGUF:UD-Q4_K_XL`
- `hf.co/unsloth/Qwen-AgentWorld-35B-A3B-GGUF:UD-Q4_K_XL-ctx64k`
- `hf.co/unsloth/Qwen3.6-35B-A3B-GGUF:UD-Q4_K_XL`
- `hf.co/yuxinlu1/gemma-4-12B-agentic-fable5-composer2.5-v2-3.5x-tau2-GGUF:Q4_K_M`
- `huihui_ai/qwen3-abliterated:14b-v2`
- `laguna-xs.2:Q4_K_M`
- `laguna-xs.2:Q4_K_M-ctx64k`
- `omnicoder2:9b-q4_k_m`
- `omnicoder2:9b-q4_k_m-ctx8k`
- `phi4-reasoning:plus`
- `phi4-reasoning:plus-ctx32k`
- `qwen3-coder-next:latest`
- `qwen3-coder-next:latest-ctx64k`
- `qwen3-coder:30b-a3b-q4_K_M`
- `qwen3-coder:30b-a3b-q4_K_M-ctx16k`
- `qwen3-coder:30b-a3b-q4_K_M-ctx8k`
- `qwen3.6:27b-q4_K_M`
- `qwen3.6:35b-a3b-q4_K_M`

## creative (10)

- `dolphin-llama3:8b`
- `fredrezones55/Qwen3.6-35B-A3B-Uncensored-HauhauCS-Aggressive:Q4`
- `fredrezones55/Qwen3.6-35B-A3B-Uncensored-HauhauCS-Aggressive:Q4-ctx8k`
- `hermes3:8b`
- `hf.co/gaston-parravicini/LFM2.5-8B-A1B-Uncensored-Gaston-GGUF:Q4_K_M`
- `hf.co/gaston-parravicini/LFM2.5-8B-A1B-Uncensored-Gaston-GGUF:Q4_K_M-ctx8k`
- `huihui_ai/Qwen3.6-abliterated:27b`
- `huihui_ai/Qwen3.6-abliterated:27b-ctx8k`
- `huihui_ai/baronllm-abliterated`
- `huihui_ai/baronllm-abliterated:latest-ctx8k`

## general (36)

- `dolphin-llama3:8b`
- `gemma4:26b-a4b-it-q4_K_M`
- `gemma4:26b-a4b-it-qat`
- `gemma4:26b-a4b-it-qat-ctx8k`
- `gemma4:e4b-it-q4_K_M`
- `granite4.1:8b`
- `granite4.1:8b-ctx16k`
- `granite4.1:8b-ctx8k`
- `hf.co/Abiray/Agents-A1-Q4_K_M-GGUF:Q4_K_M`
- `hf.co/Andycurrent/Mistral-7B-Uncensored-GGUF:Q4_K_M`
- `hf.co/BugTraceAI/BugTraceAI-CORE-Ultra-27B-Q6:Q6_K`
- `hf.co/Jiunsong/SuperQwen-AgentWorld-35B-A3B-abliterated-gguf-4bit:Q4_K_M`
- `hf.co/LiquidAI/LFM2.5-1.2B-Instruct-GGUF:Q4_K_M`
- `hf.co/LiquidAI/LFM2.5-230M-GGUF:Q4_K_M`
- `hf.co/LiquidAI/LFM2.5-350M-GGUF:Q4_K_M`
- `hf.co/QuantFactory/Llama-3.2-3B-Instruct-abliterated-GGUF`
- `hf.co/mradermacher/Huihui-Qwen3.6-35B-A3B-abliterated-GGUF:Q4_K_M`
- `hf.co/mradermacher/Qwen3.5-9B-Claude-4.6-HighIQ-THINKING-HERETIC-UNCENSORED-GGUF:Q4_K_M`
- `hf.co/mradermacher/gemma-4-26B-A4B-it-uncensored-heretic-GGUF:gemma-4-26B-A4B-it-uncensored-heretic.Q4_K_M.gguf`
- `hf.co/unsloth/Magistral-Small-2509-GGUF:Q8_0`
- `hf.co/unsloth/Magistral-Small-2509-GGUF:Q8_0-ctx64k`
- `hf.co/unsloth/Qwen-AgentWorld-35B-A3B-GGUF:UD-Q4_K_XL`
- `hf.co/unsloth/Qwen-AgentWorld-35B-A3B-GGUF:UD-Q4_K_XL-ctx64k`
- `hf.co/unsloth/Qwen3.6-35B-A3B-GGUF:UD-Q4_K_XL`
- `hf.co/yuxinlu1/gemma-4-12B-agentic-fable5-composer2.5-v2-3.5x-tau2-GGUF:Q4_K_M`
- `huihui_ai/Qwen3.6-abliterated:27b`
- `huihui_ai/Qwen3.6-abliterated:27b-ctx8k`
- `huihui_ai/qwen3.5-abliterated:9b`
- `huihui_ai/qwen3.5-abliterated:9b-ctx64k`
- `huihui_ai/qwen3.5-abliterated:9b-ctx8k`
- `lfm2.5:8b`
- `lfm2.5:8b-ctx8k`
- `mistral-small3.2:24b`
- `phi4-mini`
- `phi4:14b-q8_0`
- `portal5/gemma4-12b:q4_K_M-ctx8k`

## reasoning (22)

- `deepseek-r1:32b-q4_k_m`
- `gpt-oss:20b`
- `granite4.1:30b`
- `granite4.1:30b-ctx64k`
- `granite4.1:8b`
- `granite4.1:8b-ctx16k`
- `granite4.1:8b-ctx8k`
- `hf.co/Jackrong/Qwopus3.6-27B-v2-MTP-GGUF:Qwopus3.6-27B-v2-MTP-Q5_K_M.gguf`
- `hf.co/bartowski/THUDM_GLM-Z1-Rumination-32B-0414-GGUF:THUDM_GLM-Z1-Rumination-32B-0414-Q4_K_M.gguf`
- `hf.co/bartowski/THUDM_GLM-Z1-Rumination-32B-0414-GGUF:THUDM_GLM-Z1-Rumination-32B-0414-Q4_K_M.gguf-ctx64k`
- `hf.co/fdtn-ai/Foundation-Sec-8B-Reasoning-Q8_0-GGUF:Q8_0`
- `hf.co/unsloth/DeepSeek-R1-0528-Qwen3-8B-GGUF:Q4_K_XL`
- `hf.co/unsloth/DeepSeek-R1-0528-Qwen3-8B-GGUF:Q4_K_XL-ctx64k`
- `huihui_ai/tongyi-deepresearch-abliterated`
- `huihui_ai/tongyi-deepresearch-abliterated:latest-ctx64k`
- `phi4-mini-reasoning`
- `phi4-mini-reasoning:latest-ctx24k`
- `portal5/qwen3.6-27b-mtp:q8_0-drafted`
- `qwen3.6:27b-mtp-q4_K_M`
- `qwen3.6:27b-q8_0`
- `supergemma4-26b-uncensored:Q4_K_M`
- `supergemma4-26b-uncensored:Q4_K_M-ctx64k`

## security (26)

- `cybersecqwen-4b-toolfix:latest`
- `devstral-small-2:latest`
- `devstral-small-2:latest-ctx8k`
- `granite4.1:8b`
- `granite4.1:8b-ctx16k`
- `granite4.1:8b-ctx8k`
- `hf.co/BugTraceAI/BugTraceAI-CORE-Ultra-27B-Q6:Q6_K`
- `hf.co/Nguuma/security-slm-unsloth-1.5b:latest`
- `hf.co/douyamv/Gemma-4-31B-JANG_4M-CRACK-GGUF:gemma-4-31b-jang-crack-Q4_K_M.gguf`
- `hf.co/mradermacher/CyberSecQwen-4B-GGUF:Q4_K_M`
- `hf.co/mradermacher/VulnLLM-R-7B-GGUF:Q4_K_M`
- `hf.co/mradermacher/VulnLLM-R-7B-GGUF:Q4_K_M-ctx8k`
- `huihui_ai/baronllm-abliterated`
- `huihui_ai/baronllm-abliterated:latest-ctx8k`
- `huihui_ai/gemma-4-abliterated:E2b-qat`
- `huihui_ai/gemma-4-abliterated:E2b-qat-ctx8k`
- `huihui_ai/qwen3.5-abliterated:9b`
- `huihui_ai/qwen3.5-abliterated:9b-ctx64k`
- `huihui_ai/qwen3.5-abliterated:9b-ctx8k`
- `lfm2.5:8b`
- `lfm2.5:8b-ctx8k`
- `meta-secalign-8b-q4_k_m`
- `supergemma4-26b-uncensored:Q4_K_M`
- `supergemma4-26b-uncensored:Q4_K_M-ctx64k`
- `sylink/sylink:8b`
- `sylink/sylink:8b-ctx8k`

## vision (16)

- `gemma4:12b-it-qat`
- `gemma4:12b-it-qat-ctx8k`
- `gemma4:26b-a4b-it-q4_K_M`
- `gemma4:26b-a4b-it-qat`
- `gemma4:26b-a4b-it-qat-ctx8k`
- `gemma4:31b-it-qat`
- `gemma4:31b-it-qat-ctx8k`
- `gemma4:e2b-it-qat`
- `gemma4:e2b-it-qat-ctx8k`
- `gemma4:e4b-it-q4_K_M`
- `gemma4:e4b-it-qat`
- `gemma4:e4b-it-qat-ctx8k`
- `hf.co/douyamv/Gemma-4-31B-JANG_4M-CRACK-GGUF:gemma-4-31b-jang-crack-Q4_K_M.gguf`
- `hf.co/mradermacher/Qwen3.5-9B-Claude-4.6-HighIQ-THINKING-HERETIC-UNCENSORED-GGUF:Q4_K_M`
- `qwen3-vl:32b`
- `qwen3-vl:32b-ctx8k`
<!-- /WIKI:GENERATED -->
