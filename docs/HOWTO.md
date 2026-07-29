# Portal 6.0.3 — How-To Guide

---

## 1. Quick Start

<!-- WIKI:GENERATED unit=unit-HOWTO-1-quick-start -->
Complete working examples for every feature. Each section shows: what it does, how to activate it, a working example, and how to verify.

**What:** Launch the entire platform with one command.

```bash
git clone https://github.com/ckindle-42/portal-5.git
cd portal-5
./launch.sh up
```

**First run pulls ~16 GB and takes 10–45 minutes.** When ready:

```
[portal-5] ✅ Stack is ready
[portal-5] Web UI:     http://localhost:8080
[portal-5] Grafana:    http://localhost:3000
```

**Verify:**
```bash
./launch.sh status
<!-- /WIKI:GENERATED -->

---

## 2. Chat with AI

<!-- WIKI:GENERATED unit=unit-HOWTO-2-chat-with-ai -->
**What:** Open WebUI connects to Portal Pipeline, which routes to the best model.

**How:** Open http://localhost:8080, sign in with the admin credentials from `.env`.

**Example — general chat:**
1. Select `Portal Auto Router` from the model dropdown
2. Type: `Explain how Docker networking works`
3. The pipeline routes to `dolphin-llama3:8b` via Ollama

**Verify routing:**
```bash
<!-- /WIKI:GENERATED -->

---

## 3. Workspaces

<!-- WIKI:GENERATED unit=unit-HOWTO-3-workspaces -->
**What:** Each workspace routes to a specialized model and activates relevant tools.

**How:** Select a workspace from the model dropdown in the top bar.

| Workspace | Select this when... | Routes to |
|-----------|---------------------|-----------|
| Portal Auto Router | You're unsure | LLM router classifies intent → best-fit workspace (Ollama) |
| Portal Daily Driver | Everyday chat, writing, summarization, planning (snappy) | Gemma-4-26B-A4B-IT (Ollama) |
| Portal Code Expert | Writing or reviewing code | Qwen3-Coder-30B MoE (Ollama) |
| Portal Security Analyst | Security questions | Qwen3.6-27B (Ollama) · BaronLLM (Ollama) |
| Portal Red Team | Offensive security | Qwen3.6-27B (Ollama) · BaronLLM (Ollama) |
| Portal Blue Team | Incident response | sylink:8b (Ollama) — SOC triage, DFIR, ATT&CK |
| Portal Creative Writer | Stories, scripts | Gemma-4-heretic (Ollama) · Dolphin (Ollama) |
| Portal Deep Reasoner | Complex analysis | Qwen3.6-27B (Ollama) · DeepSeek-R1 (Ollama) |
| Portal Council Review | Review decisions, plans, proposals, policies, or research briefs with independent evidence/risk/operator lenses | Three isolated reviewers + deterministic quorum + final synthesizer |
| Portal Document Builder | Word/Excel/PPT files | Granite-4.1-8B (Ollama) + Documents MCP |
| Portal Video Creator | Shelved; not shown in the dropdown | Video MCP is disabled |
| Portal Music Producer | Generate music | Qwen3.5-abliterated (Ollama) + Music MCP |
| Portal Research Assistant | Web research | Gemma-4-26B-A4B-IT (Ollama) · Tongyi-DeepResearch (Ollama) |
| Portal Vision | Image analysis | Gemma-4-26B-A4B-IT (Ollama) · Qwen3-VL (Ollama) |
| Portal Data Analyst | Statistics, analysis | Granite-4.1-30B (Ollama) |
| Portal Compliance Analyst | NERC CIP gap analysis, policy-to-standard mapping | Granite-4.1-30B (Ollama) · DeepSeek-R1 (Ollama) |
| Portal Mistral Reasoner | Structured reasoning, strategic planning | Magistral-Small (Ollama) |
| Portal SPL Engineer | Writing or debugging Splunk SPL queries | Qwen3-Coder-Next-abliterated 80B (Ollama) |
| Portal Agentic Coder (Heavy) | Long-horizon multi-file agentic coding tasks | Qwen3-Coder-Next 80B (Ollama) |

**Example — coding:**
1. Selec
<!-- /WIKI:GENERATED -->

---

## 4. Personas

<!-- WIKI:GENERATED unit=unit-HOWTO-4-personas -->
**What:** Pre-configured specialist prompts that shape the AI's behavior.

**How:** Select a persona from the model dropdown alongside workspaces.

**Available personas:** use `unit-fact-persona-roster` for the generated live
count, module ownership, workspace binding, and model pins. Do not maintain a
second handwritten roster here.

To inspect the live module breakdown:

```bash
python3 -m portal.platform.inference.cli module list
```

**Example — red team:**

1. Select `Red Team Operator`.
2. Ask for an attack-surface analysis or lab-scoped exercise.
3. Its `workspace_model: auto-security` and `variant: redteam` select the
   corresponding security route.

**Verify personas exposed by the pipeline:**

```bash
curl -s http://localhost:9099/v1/models \
  -H "Authorization: Bearer ${PIPELINE_API_KEY}" \
  | python3 -c "import sys,json; [print(m['name']) for m in json.load(sys.stdin)['data']]"
```
<!-- /WIKI:GENERATED -->

---

## 5. Code Generation & Execution

<!-- WIKI:GENERATED unit=unit-HOWTO-5-code-generation-execution -->
**What:** Generate code with AI and execute it in an isolated Docker-in-Docker sandbox.

**Activate:** Select `Portal Code Expert` workspace, or enable the `Portal Code` tool manually.
<!-- /WIKI:GENERATED -->

---

## 6. Security Analysis

<!-- WIKI:GENERATED unit=unit-HOWTO-6-security-analysis -->
**What:** One base workspace (`auto-security`) covering research/simulation/execution tiers.
Since BUILD_PROGRAM_COLLAPSE_V1.md Phase 6, the former nine sibling workspaces (redteam,
blueteam, pentest, purpleteam×3, uncensored) are `?variant=` query params on `auto-security`
(or a persona's `variant:` field) instead of separate workspaces — same models, same tool
grants, just resolved via `_resolve_workspace_variant()` instead of a distinct workspace id.

| Variant | Tier | Model | Tools |
|---|---|---|---|
| *(base — no variant)* | Research | VulnLLM-R-7B (AppSec/CVE specialist) | web_search, web_fetch, classify_vulnerability, execute_python, execute_bash, kb_search |
| `uncensored` | Research | BaronLLM abliterated (no guardrails) | execute_bash, execute_python, remember, recall |
| `redteam` | Simulation | Qwen3.5-abliterated 9B | none |
| `redteam-deep` | Simulation | SuperGemma4-26B uncensored (deep) | none |
| `blueteam` | Research | Granite-4.1-8B (SOC triage, DFIR, ATT&CK) | web_search, web_fetch, classify_vulnerability, kb_search |
| `pentest` | Execution | Gemma-4-E2B-QAT abliterated | execute_bash, execute_python, web_search |
| `purpleteam` | Simulation, 2-hop | Qwen3.5-abliterated → Granite-4.1-8B | none |
| `purpleteam-deep` | Simulation, 4-hop | Qwen3.5-abliterated → Granite-4.1-8B → Qwen3-Coder-30B → Qwen3.6-27B | none |
| `purpleteam-exec` | Execution, 4-hop | SuperGemma4-26B (live exec) → same 3-hop detection/IR chain | execute_bash, execute_python, web_search |
<!-- /WIKI:GENERATED -->

---

## 7. Document Generation

<!-- WIKI:GENERATED unit=unit-HOWTO-7-document-generation -->
**What:** Generate Word (.docx), Excel (.xlsx), and PowerPoint (.pptx) files from chat.

**Activate:** Select **Document Builder** from the model dropdown. The Documents tool is automatically available when this workspace is selected.
<!-- /WIKI:GENERATED -->

---

## 8. Image Generation

<!-- WIKI:GENERATED unit=unit-HOWTO-8-image-generation -->
**What:** Generate images using ComfyUI with FLUX.1-schnell or other models.

**Activate:** Image generation is available through the ComfyUI MCP tool server. ComfyUI must be running on the host (see [ComfyUI Setup](COMFYUI_SETUP.md)).
<!-- /WIKI:GENERATED -->

---

## 9. Video Generation

<!-- WIKI:GENERATED unit=unit-HOWTO-9-video-generation -->
**Shelved (2026-07-29):** Video generation is not currently in operation.
Wan 2.2's `fp8_scaled` checkpoints (T2V-A14B, S2V-14B) crash on this host's
Apple Silicon MPS stack — see `KNOWN_LIMITATIONS.md`, "Wan 2.2 fp8_scaled
Checkpoints Crash on Apple Silicon MPS." TI2V-5B alone does work, but wasn't
judged worth exposing on its own. The `auto-video` workspace is defined in
`config/portal.yaml` (`expose_to_owui: false`) but hidden from the model
dropdown, and the `mcp-video` container is stopped. Only **image** generation
(`Portal Image Creator`) is in operation — see the Image Generation section.

The code path is left in place, not deleted, in case this becomes viable
later (see the KNOWN_LIMITATIONS entry for what would need to change).
<!-- /WIKI:GENERATED -->

---

## 10. Music Generation

<!-- WIKI:GENERATED unit=unit-HOWTO-10-music-generation -->
**What:** Generate music clips from text descriptions using AudioCraft/MusicGen.

**Activate:** Select **Music Producer** from the model dropdown. The Music tool is automatically available when this workspace is selected.
<!-- /WIKI:GENERATED -->

---

## 11. Text-to-Speech

<!-- WIKI:GENERATED unit=unit-HOWTO-11-text-to-speech -->
**What:** Convert text to spoken audio using MLX-native speech (Kokoro + Qwen3-TTS).

**Activate:** Select **Music Producer** from the model dropdown. The TTS (text-to-speech) tool is automatically available in this workspace.
<!-- /WIKI:GENERATED -->

---

## 12. Speech-to-Text (ASR)

<!-- WIKI:GENERATED unit=unit-HOWTO-12-speech-to-text-asr -->
**What:** Transcribe audio files to text using Qwen3-ASR (MLX-native).

**Activate:** Select any workspace from the model dropdown. The Whisper transcription tool is automatically available in all workspaces.
<!-- /WIKI:GENERATED -->

### Diarized Transcription (Speaker-Labeled Transcripts)

<!-- WIKI:GENERATED unit=unit-HOWTO-diarized-transcription-speaker-labeled-transcripts -->
**What:** Drop an audio file in OWUI chat, get back a transcript with speaker labels (SPEAKER_00, SPEAKER_01, ...). Outputs JSON + Markdown to the shared workspace at `~/AI_Output/generated/transcripts/`.

**Pre-flight (one-time):**

1. Visit `https://huggingface.co/pyannote/segmentation-3.0` — accept user conditions
2. Visit `https://huggingface.co/pyannote/speaker-diarization-3.1` — accept user conditions
3. Generate read token at `https://huggingface.co/settings/tokens`
4. Add to `.env`: `HF_TOKEN=hf_...`

**Start the service (Apple Silicon primary):**
```bash
./launch.sh start-transcribe
<!-- /WIKI:GENERATED -->

---

## 13. Web Search

<!-- WIKI:GENERATED unit=unit-HOWTO-13-web-search -->
**What:** Private web search powered by SearXNG — no data leaves your machine.

**Activate:** Built-in. The AI automatically uses web search when it needs current information.
<!-- /WIKI:GENERATED -->

---

## 14. Document RAG (Knowledge Base)

<!-- WIKI:GENERATED unit=unit-HOWTO-14-document-rag-knowledge-base -->
**What:** Upload documents and have conversations grounded in their content.
<!-- /WIKI:GENERATED -->

---

## 15. User Management

<!-- WIKI:GENERATED unit=unit-HOWTO-15-user-management -->
## Approve Pending Users
1. Admin Panel > Users
2. Find users with "pending" role
3. Click the user > set role to "user"

## Create Users via CLI
```bash
./launch.sh add-user alice@team.local "Alice Smith"
./launch.sh add-user bob@team.local "Bob Jones" admin
./launch.sh list-users
```

## User Roles
- `pending` -- cannot use the system, waiting for approval
- `user` -- standard access to workspaces, tools, chat
- `admin` -- full access including user management and all settings
<!-- /WIKI:GENERATED -->

---

## 16. Telegram Bot

<!-- WIKI:GENERATED unit=unit-HOWTO-16-telegram-bot -->
1. Message **@BotFather** on Telegram -> `/newbot` -> copy the token
2. Get your Telegram user ID from **@userinfobot**
3. Add to `.env`:
   ```bash
   TELEGRAM_BOT_TOKEN=your-token-here
   TELEGRAM_USER_IDS=your-user-id
   ```
4. Start: `./launch.sh up-telegram`
5. Message your bot `/start` to verify
<!-- /WIKI:GENERATED -->

---

## 17. Slack Bot

<!-- WIKI:GENERATED unit=unit-HOWTO-17-slack-bot -->
1. Go to https://api.slack.com/apps -> **Create New App** -> **From scratch**
2. Under **OAuth & Permissions** -> add bot scopes:
   `app_mentions:read`, `chat:write`, `channels:history`, `im:history`, `im:read`, `im:write`
3. Under **Socket Mode** -> enable it -> generate an **App-Level Token** (xapp-...)
4. Install app to your workspace
5. Add to `.env`:
   ```bash
   SLACK_BOT_TOKEN=xoxb-...
   SLACK_APP_TOKEN=xapp-...
   SLACK_SIGNING_SECRET=...
   ```
6. Start: `./launch.sh up-slack`
7. Mention `@portal` in any channel to verify
<!-- /WIKI:GENERATED -->

---

## 18. Notifications & Alerts

<!-- WIKI:GENERATED unit=unit-HOWTO-18-notifications-alerts -->
**What:** Get operational alerts and daily usage summaries via Slack, Telegram, Email, or Pushover.
<!-- /WIKI:GENERATED -->

---

## Shared Workspace

<!-- WIKI:GENERATED unit=unit-HOWTO-shared-workspace -->
**What:** A single host directory that all Portal 5 services read from and write to. Files dropped in OWUI chat, MCP-generated outputs, and host-native script outputs all live here. Eliminates cross-service file-bridging friction.

**Where:** `${AI_OUTPUT_DIR}` on the host (default `~/AI_Output/`). Mounted into containers at `/workspace`. OWUI's uploads directory bind-mounts to `${AI_OUTPUT_DIR}/uploads`.

**Layout:**
```
~/AI_Output/
├── uploads/                ← Files dropped in OWUI chat
└── generated/
    ├── transcripts/        ← Diarized transcripts (mlx-transcribe, whisper)
    ├── documents/          ← Word/Excel/PowerPoint (documents MCP)
    ├── images/             ← ComfyUI outputs
    ├── videos/             ← Retained archival video-output category
    ├── music/              ← Music MCP outputs
    └── speech/             ← TTS outputs
```

**Initialize:**
```bash
./launch.sh workspace-init
```
(Run automatically on first `./launch.sh up`.)

**Inspect:**
```bash
./launch.sh workspace-status     # File counts and sizes per category
./launch.sh workspace-show       # Resolved paths (host vs container)
```

**Use from MCP code (new modules):**
```python
from portal.platform.mcp_host import get_uploads_dir, get_generated_dir, resolve_upload_path
```
<!-- /WIKI:GENERATED -->

---

## 19. Backup & Restore

<!-- WIKI:GENERATED unit=unit-HOWTO-19-backup-restore -->
```bash
./launch.sh backup          # Save all data to ./backups/
./launch.sh restore <file>  # Restore from backup
```

Backup files are timestamped and include all Open WebUI data.
Ollama models are not included (re-downloadable via `./launch.sh pull-models`).
<!-- /WIKI:GENERATED -->

---

## 20. Cluster Scaling

<!-- WIKI:GENERATED unit=unit-HOWTO-20-cluster-scaling -->
**What:** Add more machines to increase throughput — no code changes needed.
<!-- /WIKI:GENERATED -->

---

## 21. Remote API Access (Pipeline at :9099)

<!-- WIKI:GENERATED unit=unit-HOWTO-21-remote-api-access-pipeline-at-9099 -->
**What:** The Portal Pipeline exposes an OpenAI-compatible HTTP API. Any tool that accepts a custom OpenAI base URL can connect directly — no Open WebUI required.
<!-- /WIKI:GENERATED -->

---

## 22. MLX Acceleration (Apple Silicon) — RETIRED

<!-- WIKI:GENERATED unit=unit-HOWTO-22-mlx-acceleration-apple-silicon-retired -->
> **Retired (commit 3a0c58e).** The MLX inference proxy was removed; all chat
> inference now runs through Ollama (:11434) with its native MLX Metal backend.
> The MLX *speech* (:8918) and *transcription* (:8924) servers documented
> elsewhere in this guide are unaffected and remain in use.

---
<!-- /WIKI:GENERATED -->

---

## 23. Metrics & Monitoring

<!-- WIKI:GENERATED unit=unit-HOWTO-23-metrics-monitoring -->
**What:** Prometheus metrics collection and Grafana dashboards.
<!-- /WIKI:GENERATED -->

---

## Quick Reference: All CLI Commands

<!-- WIKI:GENERATED unit=unit-HOWTO-quick-reference-cli-commands -->
# Start / stop
./launch.sh up              # Start everything
./launch.sh down            # Stop (data preserved)
./launch.sh status          # Check service health

# Test everything is working
./launch.sh test            # Run live smoke tests against running stack

# Pull specialized models (security, coding, reasoning -- 30-90 min)
./launch.sh pull-models

# MLX (Apple Silicon)
./launch.sh start-speech    # Start MLX speech server (Apple Silicon)
./launch.sh stop-speech     # Stop MLX speech server
./launch.sh mlx-status      # Check MLX component status (includes speech)

# User management
./launch.sh add-user alice@example.com "Alice Smith"
./launch.sh list-users

# Enable messaging channels (requires tokens in .env)
./launch.sh up-telegram     # Start Telegram bot
./launch.sh up-slack        # Start Slack bot
./launch.sh up-channels     # Start both

# Backup and restore
./launch.sh backup          # Save all data to ./backups/
./launch.sh restore <file>  # Restore from backup

# Seeding
./launch.sh seed            # Re-seed Open WebUI (workspaces + personas)
./launch.sh reseed          # Force-refresh all presets (delete + recreate)

# Update (single command: git pull + rebuild + model refresh + re-seed)
./launch.sh update                  # Full update of all components
./launch.sh update --skip-models    # Skip Ollama + MLX model refresh (faster)
./launch.sh update --models-only    # Only refresh models

# Cleanup
./launch.sh clean           # Remove containers (keeps model weights)
./launch.sh clean-all       # Remove everything including models
./launch.sh rebuild         # Rebuild portal-pipeline Docker image after git pull
<!-- /WIKI:GENERATED -->
