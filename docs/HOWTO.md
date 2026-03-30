# Portal 5.2 — How-To Guide

Complete working examples for every feature. Each section shows: what it does, how to activate it, a working example, and how to verify.

---

## 1. Quick Start

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
# All services should show "healthy" or "running"
```

**Troubleshoot:**
```bash
docker compose -f deploy/portal-5/docker-compose.yml logs <service-name>
```

---

## 2. Chat with AI

**What:** Open WebUI connects to Portal Pipeline, which routes to the best model.

**How:** Open http://localhost:8080, sign in with the admin credentials from `.env`.

**Example — general chat:**
1. Select `Portal Auto Router` from the model dropdown
2. Type: `Explain how Docker networking works`
3. The pipeline routes to `dolphin-llama3:8b` via Ollama

**Verify routing:**
```bash
# Check pipeline logs for routing decision
./launch.sh logs | grep "Routing workspace="
# Should show: Routing workspace=auto → backend=ollama-local model=dolphin-llama3:8b stream=True
```

---

## 3. Workspaces

**What:** Each workspace routes to a specialized model and activates relevant tools.

**How:** Select a workspace from the model dropdown in the top bar.

| Workspace | Select this when... | Routes to |
|-----------|---------------------|-----------|
| Portal Auto Router | You're unsure | Best available model |
| Portal Code Expert | Writing or reviewing code | Qwen3-Coder-Next (MLX) |
| Portal Security Analyst | Security questions | BaronLLM |
| Portal Red Team | Offensive security | BaronLLM |
| Portal Blue Team | Incident response | Lily-Cybersecurity |
| Portal Creative Writer | Stories, scripts | Dolphin Llama3 |
| Portal Deep Reasoner | Complex analysis | DeepSeek-R1 |
| Portal Document Builder | Word/Excel/PPT files | Qwen + Documents MCP |
| Portal Video Creator | Text-to-video | Dolphin + Video MCP |
| Portal Music Producer | Generate music | Dolphin + Music MCP |
| Portal Research Assistant | Web research | DeepSeek-R1 |
| Portal Vision | Image analysis | Qwen3-VL |
| Portal Data Analyst | Statistics, analysis | DeepSeek-R1 |

**Example — coding:**
1. Select `Portal Code Expert`
2. Type: `Write a Python function that finds the longest palindromic substring`
3. The pipeline routes to `mlx-community/Qwen3-Coder-Next-4bit` via MLX (or Ollama fallback)
4. The code sandbox MCP is auto-activated

**Verify workspace routing:**
```bash
curl -s http://localhost:9099/v1/models \
  -H "Authorization: Bearer $(grep PIPELINE_API_KEY .env | cut -d= -f2)" \
  | python3 -m json.tool | grep '"id"'
# Expected: 13 workspace IDs (auto, auto-coding, auto-security, auto-redteam, etc.)
```

---

## 4. Personas

**What:** Pre-configured specialist prompts that shape the AI's behavior.

**How:** Select a persona from the model dropdown (alongside workspaces).

**Available personas (35 total):**

| Category | Personas |
|----------|----------|
| Development (17) | Bug Discovery Code Assistant, Code Review Assistant, Code Reviewer, DevOps Automator, DevOps Engineer, Ethereum Developer, Full Stack Developer, GitHub Expert, JavaScript Console, K8s/Docker Learning, Python Code Generator, Python Interpreter, Senior Frontend Dev, Senior Software Engineer, QA Tester, UX/UI Developer, Codebase Wiki Documentation |
| Security (5) | Cyber Security Specialist, Network Engineer, Red Team Operator, Blue Team Defender, Pentester |
| Data/Research (6) | Data Analyst, Data Scientist, ML Engineer, Statistician, IT Architect, Research Analyst |
| Systems (2) | Linux Terminal, SQL Terminal |
| General/Writing (5) | IT Expert, Tech Reviewer, Tech Writer, Creative Writer, Excel Sheet |

**Example — red team:**
1. Select `Red Team Operator` from the model dropdown
2. Type: `Analyze the attack surface of a typical REST API with JWT authentication`
3. Gets routed to `xploiter/the-xploiter` security model

**Verify personas seeded:**
```bash
# Open WebUI models come through the pipeline at :9099
curl -s http://localhost:9099/v1/models \
  -H "Authorization: Bearer $(grep PIPELINE_API_KEY .env | cut -d= -f2)" \
  | python3 -c "import sys,json; [print(m['name']) for m in json.load(sys.stdin)['data']]" \
  | grep -i "red.team"
```

---

## 5. Code Generation & Execution

**What:** Generate code with AI and execute it in an isolated Docker-in-Docker sandbox.

**Activate:** Select `Portal Code Expert` workspace, or enable the `Portal Code` tool manually.

### Generate code

1. Select `Portal Code Expert`
2. Type: `Write a Python script that finds all prime numbers up to 1000 and returns them as JSON`
3. The AI generates code using Qwen3-Coder-Next

### Execute code in sandbox

1. In the same chat, click the **+** icon → enable `Portal Code`
2. Type: `Run this code and show me the output`
3. The code executes in a Docker-in-Docker container (isolated from host)

**Verify sandbox:**
```bash
# Sandbox runs in DinD container on port 8914
curl -s http://localhost:8914/health
# Should return: {"status": "ok"}
```

**Sandbox constraints:**
- Network: **disabled** (no internet access, cannot scrape external sites)
- Filesystem: read-only except `/tmp` (64MB tmpfs)
- Memory: 256MB, CPU: 0.5 cores, 30s timeout (max 120s)
- Packages: Python standard library only — no `pip install` possible
- If you need network access or third-party packages, run code directly on the host instead

---

## 6. Security Analysis

**What:** Three security-focused workspaces for different threat perspectives.

### Defensive Security (auto-security)

1. Select `Portal Security Analyst`
2. Type: `Review this nginx config for security misconfigurations: [paste config]`
3. Routes to BaronLLM for defensive analysis

### Offensive Security (auto-redteam)

1. Select `Portal Red Team`
2. Type: `Enumerate potential injection points in this GraphQL schema: [paste schema]`
3. Routes to BaronLLM with red team perspective
4. Requires 2+ security keywords in the message to trigger auto-routing

### Blue Team (auto-blueteam)

1. Select `Portal Blue Team`
2. Type: `Analyze these firewall logs for indicators of compromise: [paste logs]`
3. Routes to Lily-Cybersecurity model

**Verify security routing:**
```bash
# Content-aware routing: messages with 2+ red team keywords auto-route
curl -s http://localhost:9099/v1/chat/completions \
  -H "Authorization: Bearer $(grep PIPELINE_API_KEY .env | cut -d= -f2)" \
  -H "Content-Type: application/json" \
  -d '{"model": "auto", "messages": [{"role": "user", "content": "exploit vulnerability payload injection"}], "stream": false}'
# Check logs for: Routing workspace=auto-redteam
```

---

## 7. Document Generation

**What:** Generate Word (.docx), Excel (.xlsx), and PowerPoint (.pptx) files from chat.

**Activate:** Click **+** → enable `Portal Documents`, or select `Portal Document Builder` workspace.

### Generate a Word document

```
Create a project proposal for migrating our monolith to microservices.
Include: executive summary, architecture diagram description, timeline, risk matrix.
Save as a Word document.
```

The AI generates structured markdown. The MCP server converts it to `.docx` using python-docx.

### Generate an Excel spreadsheet

```
Create an Excel spreadsheet with a budget breakdown:
- Column A: Category (Hardware, Software, Services, Personnel)
- Column B: Q1 Cost, Column C: Q2 Cost, Column D: Total
- Include formulas for totals
```

### Generate a PowerPoint

```
Create a 5-slide PowerPoint presentation about container security best practices.
Slides: Title, Threat Landscape, Best Practices, Implementation, Q&A.
```

**Verify:**
```bash
curl -s http://localhost:8913/health
# Should return: {"status": "ok"}

# List available tools
curl -s http://localhost:8913/tools | python3 -m json.tool
```

**Output:** Files are returned as downloadable attachments in the chat.

---

## 8. Image Generation

**What:** Generate images using ComfyUI with FLUX.1-schnell or other models.

**Activate:** Click **+** → enable `Portal ComfyUI`.

### Prerequisites

ComfyUI must be running on the host:

```bash
# Install (one-time)
./launch.sh install-comfyui

# Download default model (one-time, ~12GB)
./launch.sh download-comfyui-models

# Verify
curl http://localhost:8188/system_stats
```

### Generate an image

```
Generate an image of a futuristic city skyline at sunset, cyberpunk style, neon lights reflecting in rain puddles
```

**Parameters you can specify:**
- Resolution (default: 1024x1024)
- Number of steps (default: 4 for schnell, 20 for dev)
- CFG scale
- Seed (for reproducibility)

**Verify:**
```bash
# ComfyUI runs natively on host at http://localhost:8188 (not in Docker)
curl -s http://localhost:8188/system_stats | python3 -c "import sys,json; d=json.load(sys.stdin); print('ComfyUI:', d['system']['comfyui_version'], '| MPS available:', 'mps' in [dev['type'] for dev in d['system']['devices']])"

# ComfyUI MCP bridge health (from inside container):
docker exec portal5-mcp-comfyui python3 -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8910/health').read().decode())"
```

---

## 9. Video Generation

**What:** Generate short video clips from text prompts using Wan2.2.

**Activate:** Click **+** → enable `Portal Video`, or select `Portal Video Creator` workspace.

### Prerequisites

Wan2.2 model must be downloaded:

```bash
./launch.sh download-comfyui-models
# Select wan2.2 when prompted (~18GB)
```

### Generate a video

```
Generate a 3-second video of ocean waves crashing on a rocky shoreline at golden hour
```

**Parameters:**
- Duration: 2-5 seconds (longer = more VRAM)
- Resolution: 480p or 720p
- FPS: 8 or 16

**Verify:**
```bash
curl -s http://localhost:8911/health
```

**Note:** Video generation is resource-intensive. On 32GB systems, close other heavy workloads first. On 64GB systems, Wan2.2 (~18GB) coexists safely with Ollama general models.

---

## 10. Music Generation

**What:** Generate music clips from text descriptions using AudioCraft/MusicGen.

**Activate:** Click **+** → enable `Portal Music`, or select `Portal Music Producer` workspace.

### Generate music

```
Generate a 15-second lo-fi hip hop beat with mellow piano chords and vinyl crackle
```

**Parameters:**
- Duration: 5-30 seconds (default: 10)
- Model size: `small` (fast, ~1GB), `medium` (balanced, ~3GB), `large` (best quality, ~10GB)

**Example with parameters:**
```
Generate a 20-second orchestral cinematic trailer music piece with dramatic percussion, using the large model
```

### Melody conditioning

Upload a reference audio clip and ask:
```
Generate music that matches the melody of this reference clip, style: jazz piano
```

**Verify:**
```bash
curl -s http://localhost:8912/health
# Returns: {"status": "ok", "backend": "audiocraft"}
```

**Output:** WAV file delivered as a chat attachment.

---

## 11. Text-to-Speech

**What:** Convert text to spoken audio using kokoro-onnx (built-in) or Fish Speech (optional).

**Activate:** Click **+** → enable `Portal TTS`.

### Speak text

```
Read this aloud: Portal 5 is a complete local AI platform running entirely on your own hardware with zero cloud dependencies.
```

### Choose a voice

```
Read this with a British male voice: The quick brown fox jumps over the lazy dog.
```

**Available kokoro-onnx voices:**

| Voice ID | Description |
|----------|-------------|
| af_heart | American English female (default) |
| af_sky | American English female |
| af_bella | American English female |
| af_nicole | American English female |
| af_sarah | American English female |
| am_adam | American English male |
| am_michael | American English male |
| bf_emma | British English female |
| bf_isabella | British English female |
| bm_george | British English male |
| bm_lewis | British English male |

### Direct API call

```bash
curl -X POST http://localhost:8916/v1/audio/speech \
  -H "Content-Type: application/json" \
  -d '{"input": "Hello from Portal 5!", "voice": "af_heart"}' \
  --output hello.mp3
```

**Verify:**
```bash
curl -s http://localhost:8916/health
# Returns: {"status": "ok", "backend": "kokoro"}
```

---

## 12. Speech-to-Text (Whisper)

**What:** Transcribe audio files to text using faster-whisper.

**Activate:** Click **+** → enable `Portal Whisper`.

### Transcribe an audio file

Upload an audio file (MP3, WAV, M4A, etc.) and type:
```
Transcribe this audio file
```

### Direct API call

```bash
curl -X POST http://localhost:8915/v1/audio/transcriptions \
  -F "file=@recording.mp3" \
  -F "language=en"
```

**Supported formats:** MP3, WAV, M4A, FLAC, OGG, WebM

**Verify:**
```bash
# Whisper MCP health (from inside container):
docker exec portal5-mcp-whisper python3 -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8915/health').read().decode())"
```

**Note:** The first transcription downloads the Whisper model (~150MB). Subsequent calls are instant.

---

## 13. Web Search

**What:** Private web search powered by SearXNG — no data leaves your machine.

**Activate:** Built-in. The AI automatically uses web search when it needs current information.

### Ask a research question

```
What are the latest security vulnerabilities disclosed this week in Linux kernel?
```

The AI automatically searches via SearXNG and synthesizes results.

### Force a search

```
Search the web for: best practices for securing Kubernetes pods in 2026
```

**Verify:**
```bash
# SearXNG is running internally on port 8088
docker compose -f deploy/portal-5/docker-compose.yml ps searxng
# Should show "healthy"
```

**Configuration:** SearXNG is auto-configured via environment variables in docker-compose.yml. No manual setup needed.

---

## 14. Document RAG (Knowledge Base)

**What:** Upload documents and have conversations grounded in their content.

### Upload a document

1. Open chat at http://localhost:8080
2. Click the **+** (paperclip) icon in the chat input
3. Upload a PDF, DOCX, TXT, or Markdown file
4. Type: `Summarize the key points from this document`

### Create a persistent knowledge base

1. Go to **Workspace → Knowledge** in the left sidebar
2. Click **+ New Collection** → name it (e.g., "Company Policies")
3. Upload documents to the collection
4. In any chat, type: `#Company Policies What is our remote work policy?`

### Supported formats

PDF (with image extraction), DOCX, TXT, Markdown, CSV, HTML

**How it works:** Documents are chunked into 1500-char segments with 100-char overlap, embedded using `nomic-embed-text` (runs in Ollama), and searched with hybrid mode (semantic + keyword).

**Verify:**
```bash
# Embedding model should be pulled
docker exec portal5-ollama ollama list | grep nomic-embed-text
```

### Cross-session memory

The AI remembers facts you share across conversations:
```
I'm working on a Python FastAPI project with PostgreSQL
```
Future sessions will remember this context.

**View memories:** Settings → Personalization → Memory

---

## 15. User Management

### Create users via CLI

```bash
# Standard user
./launch.sh add-user alice@team.local "Alice Smith"

# Admin user
./launch.sh add-user bob@team.local "Bob Jones" admin

# List all users
./launch.sh list-users
```

### Approve pending users

1. Open http://localhost:8080 → Admin Panel → Users
2. Find users with "pending" role
3. Click the user → set role to "user"

### User roles

| Role | Permissions |
|------|-------------|
| `pending` | Cannot use the system, waiting for approval |
| `user` | Standard access to workspaces, tools, chat |
| `admin` | Full access including user management and all settings |

**Configure default role:** Set `DEFAULT_USER_ROLE=user` in `.env` to auto-approve new signups.

---

## 16. Telegram Bot

**What:** Chat with Portal 5 through Telegram.

### Setup

1. Message **@BotFather** on Telegram → `/newbot` → copy the token
2. Get your Telegram user ID from **@userinfobot**
3. Add to `.env`:
   ```bash
   TELEGRAM_BOT_TOKEN=your-token-here
   TELEGRAM_USER_IDS=your-user-id
   ```
4. Start:
   ```bash
   ./launch.sh up-telegram
   ```

### Usage

```
/start                          — verify connection
/workspace <name>              — switch workspace (see options below)
Write me a Python web scraper   — normal chat (uses current workspace)
```

**Available workspaces:** `auto`, `auto-coding`, `auto-security`, `auto-redteam`, `auto-blueteam`, `auto-creative`, `auto-reasoning`, `auto-documents`, `auto-video`, `auto-music`, `auto-research`, `auto-vision`, `auto-data`

### Verify

```bash
# Check container is running
docker compose -f deploy/portal-5/docker-compose.yml ps portal-telegram

# Message your bot /start on Telegram
# Should respond with a welcome message
```

**Rate limiting:** The bot maintains a 20-message sliding window per user to prevent memory exhaustion.

---

## 17. Slack Bot

**What:** Chat with Portal 5 through Slack.

### Setup

1. Go to https://api.slack.com/apps → **Create New App** → **From scratch**
2. Under **OAuth & Permissions** → add bot scopes:
   `app_mentions:read`, `chat:write`, `channels:history`, `im:history`, `im:read`, `im:write`
3. Under **Socket Mode** → enable → generate **App-Level Token** (xapp-...)
4. Install app to workspace
5. Add to `.env`:
   ```bash
   SLACK_BOT_TOKEN=xoxb-...
   SLACK_APP_TOKEN=xapp-...
   SLACK_SIGNING_SECRET=...
   ```
6. Start:
   ```bash
   ./launch.sh up-slack
   ```

### Usage

```
@portal Write a bash script to rotate nginx logs
@portal Analyze this error log for root cause: [paste log]
```

Direct messages to the bot also work — just message it directly.

### Verify

```bash
docker compose -f deploy/portal-5/docker-compose.yml ps portal-slack
# Mention @portal in any channel — should respond
```

### Start both channels

```bash
./launch.sh up-channels
```

---

## 18. Notifications & Alerts

**What:** Get operational alerts and daily usage summaries via Slack, Telegram, Email, or Pushover.

### Enable

Add to `.env`:
```bash
NOTIFICATIONS_ENABLED=true
```

### Configure channels

**Slack:**
```bash
SLACK_ALERT_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK/URL
SLACK_ALERT_CHANNEL=#portal-alerts
```

**Telegram (use a separate alert bot):**
```bash
TELEGRAM_ALERT_BOT_TOKEN=123456789:ABCdef...
TELEGRAM_ALERT_CHANNEL_ID=-1001234567890
```

**Email:**
```bash
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_USER=your-username
SMTP_PASSWORD=your-password
SMTP_FROM=portal@portal.local
EMAIL_ALERT_TO=admin@portal.local
```

**Pushover:**
```bash
PUSHOVER_API_TOKEN=your-app-token
PUSHOVER_USER_KEY=your-user-key
```

### Alert types

| Event | When it fires |
|-------|---------------|
| `backend_down` | A backend fails N consecutive health checks (default: 3) |
| `backend_recovered` | A previously-down backend comes back |
| `all_backends_down` | Every backend is unhealthy simultaneously |
| `config_error` | `backends.yaml` is missing or unparseable |
| `daily_summary` | Once per day at configured hour (default: 09:00 UTC) |

### Adjust thresholds

```bash
ALERT_BACKEND_DOWN_THRESHOLD=3
ALERT_SUMMARY_HOUR=9
ALERT_SUMMARY_TIMEZONE=America/New_York
```

### Verify

```bash
# Restart pipeline to pick up new env vars
docker compose -f deploy/portal-5/docker-compose.yml restart portal-pipeline

# Check logs for notification init
./launch.sh logs | grep -i "notification"
# Should show: "NotificationScheduler attached to pipeline metrics"
```

**Disable all notifications:** Set `NOTIFICATIONS_ENABLED=false` — no code changes needed.

---

## 19. Backup & Restore

### Backup Open WebUI data (critical)

```bash
docker run --rm -v portal-5_open-webui-data:/data -v $(pwd):/backup \
    alpine tar czf /backup/openwebui-backup-$(date +%Y%m%d).tar.gz /data
```

### Backup configuration

```bash
tar czf config-backup-$(date +%Y%m%d).tar.gz config/ .env
```

### Full backup script

```bash
./launch.sh backup
# Creates timestamped backups in ./backups/
```

### Restore

```bash
# Stop services
./launch.sh down

# Restore data
docker run --rm -v portal-5_open-webui-data:/data -v $(pwd):/backup \
    alpine tar xzf /backup/openwebui-backup-20260330.tar.gz -C /

# Restart
./launch.sh up
```

### Automated daily backup

```bash
# Add to crontab (crontab -e)
0 2 * * * cd /path/to/portal-5 && ./launch.sh backup
```

### Migration to new host

```bash
# On source:
./launch.sh backup
# Copy ./backups/ and .env to new host

# On new host:
git clone https://github.com/ckindle-42/portal-5
cd portal-5
cp /path/to/.env .env
./launch.sh down
docker volume create portal-5_open-webui-data
docker run --rm -v portal-5_open-webui-data:/data -v /path/to/backups:/backup \
    alpine tar xzf /backup/openwebui-backup-*.tar.gz -C /
./launch.sh up
```

---

## 20. Cluster Scaling

**What:** Add more machines to increase throughput — no code changes needed.

### Add a second Mac Studio

1. Install Ollama on the new machine:
   ```bash
   OLLAMA_HOST=0.0.0.0 ollama serve
   ```

2. Edit `config/backends.yaml`:
   ```yaml
   - id: ollama-node-2
     type: ollama
     url: "http://192.168.1.102:11434"
     group: general
     models: [dolphin-llama3:8b]
   ```

3. Restart the pipeline:
   ```bash
   docker compose -f deploy/portal-5/docker-compose.yml restart portal-pipeline
   ```

### Add a vLLM node for 70B models

```yaml
- id: vllm-70b
  type: openai_compatible
  url: "http://192.168.1.103:8000"
  group: general
  models: [meta-llama/Llama-3.1-70B-Instruct]
```

### Assign specialized nodes

```yaml
- id: vllm-coding
  url: "http://192.168.1.104:8000"
  group: coding      # auto-coding routes here first
  models: [Qwen/Qwen2.5-Coder-32B-Instruct]
```

**Verify:**
```bash
./launch.sh status
# Shows all backends and their health status
```

---

## 21. MLX Acceleration (Apple Silicon)

**What:** 20-40% faster inference than Ollama GGUF on M-series Macs.

### Install

```bash
./launch.sh install-mlx
```

### Set the model

Edit `.env`:
```bash
MLX_MODEL=mlx-community/Qwen3-Coder-Next-4bit
```

### Switch models at runtime

```bash
./launch.sh switch-mlx-model mlx-community/DeepSeek-R1-0528-4bit
```

### Available MLX models

| Model | RAM | Best for |
|-------|-----|----------|
| `mlx-community/Qwen3-Coder-Next-4bit` | ~18GB | Code generation |
| `mlx-community/DeepSeek-R1-0528-4bit` | ~18GB | Reasoning |
| `mlx-community/Devstral-Small-2505-4bit` | ~13GB | Code + lightweight |
| `mlx-community/Llama-3.2-3B-Instruct-4bit` | ~2GB | Fast baseline |
| `mlx-community/Llama-3.3-70B-Instruct-4bit` | ~40GB | Maximum quality |

### Memory coexistence (64GB system)

```
Qwen3-Coder-Next (~18GB) + Wan2.2 video (~18GB) + Ollama general (~5GB) = 41GB ✓
```

### Verify

```bash
curl -s http://localhost:8081/v1/models
# Lists the loaded MLX model

# Check pipeline logs for MLX routing
./launch.sh logs | grep "mlx"
```

---

## 22. Metrics & Monitoring

**What:** Prometheus metrics collection and Grafana dashboards.

### Access

- **Grafana:** http://localhost:3000 (credentials in `.env`: `GRAFANA_PASSWORD`)
- **Prometheus:** http://localhost:9090

### Available metrics

| Metric | Description |
|--------|-------------|
| `portal_requests_by_model_total` | Total requests per model and workspace |
| `portal_tokens_per_second` | Token generation rate histogram |
| `portal_input_tokens_total` | Total input tokens processed |
| `portal_output_tokens_total` | Total output tokens generated |

### Check in Prometheus

1. Open http://localhost:9090
2. Enter query: `rate(portal_requests_by_model_total[5m])`
3. Click "Execute"

### Grafana dashboard

The `portal5_overview.json` dashboard is auto-provisioned. Open http://localhost:3000 → Dashboards → Portal 5 Overview.

### Verify

```bash
# Prometheus is scraping the pipeline
curl -s http://localhost:9090/api/v1/targets | python3 -m json.tool | grep portal-pipeline

# Pipeline is exposing metrics
curl -s http://localhost:9099/metrics | head -20
```

---

## Quick Reference: All CLI Commands

```bash
# Lifecycle
./launch.sh up              # Start everything
./launch.sh down            # Stop (data preserved)
./launch.sh status          # Health check
./launch.sh logs [service]  # View logs

# Models
./launch.sh pull-models     # Pull all Ollama models (30-90 min)
./launch.sh install-mlx     # Install MLX for Apple Silicon
./launch.sh switch-mlx-model <tag>  # Switch active MLX model
./launch.sh import-gguf <path> [name]  # Import a local .gguf file into Ollama

# Users
./launch.sh add-user <email> [name] [role]
./launch.sh list-users

# Channels
./launch.sh up-telegram     # Start with Telegram bot
./launch.sh up-slack        # Start with Slack bot
./launch.sh up-channels     # Start both

# Data
./launch.sh backup          # Backup all data
./launch.sh restore <file>  # Restore from backup
./launch.sh seed            # Re-seed Open WebUI (workspaces + personas)
./launch.sh clean           # Wipe Open WebUI data (keep models)
./launch.sh clean-all       # Wipe everything including models

# ComfyUI
./launch.sh install-comfyui              # Install ComfyUI
./launch.sh download-comfyui-models      # Download image/video models

# Testing
./launch.sh test            # Run live smoke tests
pytest tests/ -v --tb=short # Run unit tests (no Docker needed)
```

---

*Last updated: 2026-03-30 | Portal 5.2.0*
