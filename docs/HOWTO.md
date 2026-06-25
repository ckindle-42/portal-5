# Portal 6.0.3 — How-To Guide

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
# Should show: Routing workspace=auto → backend=ollama-local model=<model> stream=True

# Check which model Ollama has loaded (router should always be in the list)
curl -s http://localhost:11434/api/ps | jq '.models[] | {name, size_vram}'

# LLM router (Layer 1) is primary — grammar-enforced JSON output from OBLITERATED E4B
# Keyword scoring (Layer 2) fires when router times out or returns low confidence
```

---

## 3. Workspaces

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
| Portal Document Builder | Word/Excel/PPT files | Granite-4.1-8B (Ollama) + Documents MCP |
| Portal Video Creator | Text-to-video | Granite-4.1-8B (Ollama) + Video MCP |
| Portal Music Producer | Generate music | Qwen3.5-abliterated (Ollama) + Music MCP |
| Portal Research Assistant | Web research | Gemma-4-26B-A4B-IT (Ollama) · Tongyi-DeepResearch (Ollama) |
| Portal Vision | Image analysis | Gemma-4-26B-A4B-IT (Ollama) · Qwen3-VL (Ollama) |
| Portal Data Analyst | Statistics, analysis | Granite-4.1-30B (Ollama) |
| Portal Compliance Analyst | NERC CIP gap analysis, policy-to-standard mapping | Granite-4.1-30B (Ollama) · DeepSeek-R1 (Ollama) |
| Portal Mistral Reasoner | Structured reasoning, strategic planning | Magistral-Small (Ollama) |
| Portal SPL Engineer | Writing or debugging Splunk SPL queries | Qwen3-Coder-Next-abliterated 80B (Ollama) |
| Portal Agentic Coder (Heavy) | Long-horizon multi-file agentic coding tasks | Qwen3-Coder-Next 80B (Ollama) |

**Example — coding:**
1. Select `Portal Code Expert`
2. Type: `Write a Python function that finds the longest palindromic substring`
3. The pipeline routes to `qwen3-coder:30b-a3b-q4_K_M` via Ollama
4. The code sandbox MCP is auto-activated

**Verify workspace routing:**
```bash
curl -s http://localhost:9099/v1/models \
  -H "Authorization: Bearer $(grep PIPELINE_API_KEY .env | cut -d= -f2)" \
  | python3 -m json.tool | grep '"id"'
# Expected: 90 workspace IDs total (42 auto-/tools-specialist + 48 bench-*)
```

---

## 4. Personas

**What:** Pre-configured specialist prompts that shape the AI's behavior.

**How:** Select a persona from the model dropdown (alongside workspaces).

**Available personas (96 production + 54 benchmark = 150 total):**

| Category | Count | Personas |
|----------|-------|----------|
| Development | 24 | Bug Discovery Code Assistant, Code Review Assistant, Code Reviewer, Codebase WIKI Documentation, Creative Coder, DevOps Automator, DevOps Engineer, E2E Debugger, E2E Test Author, Ethereum Developer, Form Filler, Fullstack Developer, GitHub Expert, Go Engineer, JavaScript Console, K8s/Docker Learning, Python Code Generator, Python Interpreter, Rust Engineer, Senior Frontend Dev, Senior Software Engineer, Software QA Tester, TypeScript Engineer, UX/UI Developer |
| Data | 10 | Dashboard Architect, Data Analyst, Data Extractor, Data Scientist, Database Architect, Excel Sheet, Machine Learning Engineer, Phi-4 STEM Analyst, Research Analyst, Statistician |
| General | 9 | Agent Orchestrator, Business Analyst, Daily Driver, Interview Coach, IT Expert, Personal Assistant, Product Manager, Tech Reviewer, Web Navigator |
| Research | 7 | Fact Checker, Gemma Research Analyst, Knowledge Base Navigator, Market Analyst, Paywalled Researcher, SuperGemma4 Uncensored Researcher, Web Researcher |
| Security | 7 | Blue Team Defender, Cyber Security Specialist, Network Engineer, Penetration Tester, Red Team Operator, Splunk Detection Author, Splunk SPL Engineer |
| Vision | 7 | Chart Analyst, Code Screenshot Reader, Diagram Reader, Gemma 4 Edge Vision, Gemma 4 JANG Unfiltered Vision, OCR Specialist, Whiteboard Converter |
| Compliance | 7 | CIP Policy Writer, Compliance Analyst (Multi-Framework), GDPR DPO, HIPAA Privacy Officer, NERC CIP Compliance Analyst, PCI-DSS Assessor, SOC 2 Auditor |
| Writing | 6 | Creative Writer, Documentation Architect, Hermes Narrative Writer, Proofreader, Tech Writer, Transcript Analyst |
| Reasoning | 4 | GPT-OSS Analyst, Magistral Strategist, Math Reasoner, Phi-4 Technical Analyst |
| Systems | 3 | Linux Terminal, SQL Terminal, Terraform Writer |
| Architecture | 1 | IT Architect |
| Benchmark | 54 | bench-agentworld, bench-devstral, bench-devstral-small-2, bench-glm, bench-glm-reap, bench-glm-z1-rumination, bench-gptoss, bench-granite41-8b, bench-granite41-30b, bench-laguna, bench-lfm25-8b, bench-nex-n2-mini, bench-omnicoder2, bench-qwable-35b, bench-qwen35-abliterated, bench-qwen36-27b, bench-qwen36-35b-a3b, bench-qwen36-35b-a3b-ud, bench-qwen3-coder-30b, bench-qwen3-coder-next, bench-sylink, bench-vulnllm-r7b, and others (see WORKSPACES for full list) |

**Example — red team:**
1. Select `Red Team Operator` from the model dropdown
2. Type: `Analyze the attack surface of a typical REST API with JWT authentication`
3. Gets routed to `auto-redteam` workspace — SuperGemma4-26B uncensored or Qwen3.5-abliterated (simulation only, no tool execution)

**Verify personas seeded:**
```bash
# Open WebUI models come through the pipeline at :9099
curl -s http://localhost:9099/v1/models \
  -H "Authorization: Bearer $(grep PIPELINE_API_KEY .env | cut -d= -f2)" \
  | python3 -c "import sys,json; [print(m['name']) for m in json.load(sys.stdin)['data']]" \
  | grep -i "red.team"
```


**Example — NERC CIP Compliance:**
1. Select `NERC CIP Compliance Analyst` from the model dropdown
2. Type: `Analyze CIP-007-6 R2 Part 2.1 — what evidence is needed?`
3. Example response:
   ```
   For CIP-007-6 R2, evidence is required to support the following: 

(2.1) All events specified in this requirement are available for access by appropriate Information System personnel. This capability
   ```

**Example — Phi-4 Technical Analyst:**
1. Select `Phi-4 Technical Analyst` from the model dropdown
2. Type: `Write a technical design document for a rate-limiting middleware in FastAPI`
3. Routes to `auto-documents` workspace → `granite4.1:8b` (Ollama) — structured document generation

**Example — Phi-4 STEM Analyst:**
1. Select `Phi-4 STEM Analyst` from the model dropdown
2. Type: `Given a Poisson process with rate λ=3 events/hour, what is the probability of exactly 5 events in 2 hours?`
3. Routes to `auto-phi4` workspace → `phi4-reasoning:plus` (Ollama) — RL-trained reasoning, competition-level mathematics

**Example — GPT-OSS Analyst:**
1. Select `GPT-OSS Analyst` from the model dropdown
2. Type: `Compare the architectural trade-offs between event-driven and request-response microservice communication patterns`
3. Routes to `gpt-oss:20b` (Ollama) — OpenAI-lineage open-weight model with RL-trained reasoning

**Example — Gemma 4 Edge Vision (image + audio):**
1. Select `Gemma 4 Edge Vision` from the model dropdown
2. Attach an image or audio clip (up to 30 seconds) and type: `Describe what you see/hear and identify any anomalies`
3. Routes to `auto-gemma-e4b` workspace — Gemma 4 E4B (Ollama) — native audio+image+text input, 256K ctx

**Example — Gemma 4 JANG Unfiltered Vision:**
1. Select `Gemma 4 JANG Unfiltered Vision` from the model dropdown
2. Attach a screenshot and type: `Analyze this network diagram for security weaknesses — no restrictions`
3. Routes to `auto-vision` workspace (Ollama) — uncensored vision analysis, no refusal guardrails

---

## 5. Code Generation & Execution

**What:** Generate code with AI and execute it in an isolated Docker-in-Docker sandbox.

**Activate:** Select `Portal Code Expert` workspace, or enable the `Portal Code` tool manually.

### Generate code

1. Select `Portal Code Expert`
2. Type: `Write a Python script that finds all prime numbers up to 1000 and returns them as JSON`
3. The AI generates code using Qwen3-Coder-Next

### Execute code in sandbox

1. Select **Code Expert** from the model dropdown (this enables the Code tool automatically)
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

**What:** Nine security-focused workspaces across three tiers — simulation, research, and execution.

| Workspace | Tier | Model | Tools |
|---|---|---|---|
| `auto-security` | Research | VulnLLM-R-7B (AppSec/CVE specialist) | web_search, web_fetch, classify_vulnerability, execute_python, execute_bash, kb_search |
| `auto-security-uncensored` | Research | VulnLLM-R-7B (no guardrails) | web_search, kb_search |
| `auto-redteam` | Simulation | Qwen3.5-abliterated 9B | none |
| `auto-redteam-deep` | Simulation | SuperGemma4-26B uncensored (0.915 bench) | none |
| `auto-blueteam` | Research | sylink:8b (SOC triage, DFIR, ATT&CK) | web_search, web_fetch, classify_vulnerability, kb_search |
| `auto-pentest` | Execution | Gemma4-E2B-QAT abliterated (~3GB, thinking model) | execute_bash, execute_python, web_search |
| `auto-purpleteam` | Simulation | Qwen3.5-abliterated → Foundation-Sec-8B | none |
| `auto-purpleteam-deep` | Simulation | 4-hop chain (red→blue→detect→IR) | none |
| `auto-purpleteam-exec` | Execution | 4-hop chain, primary has live execution | execute_bash, execute_python, web_search |

### Defensive Security (auto-security)

1. Select `Portal Security Analyst`
2. Type: `Review this nginx config for security misconfigurations: [paste config]`
3. Routes to BaronLLM with web_search and kb_search for current CVE lookup

### Offensive Security — Simulation (auto-redteam / auto-redteam-deep)

Red team workspaces generate structured ATT&CK content. **No tools** — simulation only.

1. Select `Portal Red Team` (fast, 9B) or `Portal Red Team · Deep` (SuperGemma4-26B, denser ATT&CK coverage)
2. Type: `Enumerate attack vectors against an Active Directory environment with Kerberos`
3. Output structured with `## ATTACK VECTORS`, `## EXPLOITATION`, `## PERSISTENCE`, `## DEFENDER CUE`

LLM-based intent classifier auto-routes offensive prompts to `auto-redteam`; keyword scoring provides fallback (signals like "exploit", "payload", "shellcode" trigger routing).

### Penetration Testing with Execution (auto-pentest)

For **authorized** penetration tests only. JANG-CRACK 31B uses `execute_bash` and `execute_python` to validate commands live against real targets.

1. Select `Portal Pentest Assistant`
2. Type: `The target runs Apache 2.4.49. Identify the CVE, confirm the vulnerability, and attempt path traversal to /etc/passwd`
3. Model plans the attack, executes curl/exploit commands via tools, reports real output

### Purple Team Chains

Purple team workspaces run multi-hop chains — red team output feeds directly into blue team analysis.

**`auto-purpleteam`** (2-hop, ~3 min):
```
Attack scenario: AWS S3 bucket misconfiguration allowing public read access
```
1. Hop 1 — Qwen3.5-abliterated: attack vectors, exploitation, persistence
2. Hop 2 — Foundation-Sec-8B-Reasoning: detection, IOCs, mitigations

**`auto-purpleteam-deep`** (4-hop, ~10-15 min):
Same as above plus:
3. Hop 3 — Qwen3-Coder: Sigma rules, Wazuh XML, hunting queries
4. Hop 4 — Qwen3.6-27B: full IR playbook (triage → containment → recovery)

**`auto-purpleteam-exec`** (4-hop with live execution, authorized targets only):
Primary hop has `execute_bash`/`execute_python` — actually runs enumeration and PoC commands, passes real output through the detection/IR chain.

### Blue Team (auto-blueteam)

1. Select `Portal Blue Team`
2. Type: `Analyze these firewall logs for indicators of compromise: [paste logs]`
3. Routes to Foundation-Sec-8B-Reasoning (Cisco cybersec-trained, native `<think>` reasoning)

**Verify security routing:**
```bash
# Content-aware routing: LLM-based intent classification (primary) with keyword scoring fallback
curl -s http://localhost:9099/v1/chat/completions \
  -H "Authorization: Bearer $(grep PIPELINE_API_KEY .env | cut -d= -f2)" \
  -H "Content-Type: application/json" \
  -d '{"model": "auto", "messages": [{"role": "user", "content": "exploit vulnerability payload injection"}], "stream": false}'
# Check logs for: Routing workspace=auto-redteam
```

---

## 7. Document Generation

**What:** Generate Word (.docx), Excel (.xlsx), and PowerPoint (.pptx) files from chat.

**Activate:** Select **Document Builder** from the model dropdown. The Documents tool is automatically available when this workspace is selected.

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

**Activate:** Image generation is available through the ComfyUI MCP tool server. ComfyUI must be running on the host (see [ComfyUI Setup](COMFYUI_SETUP.md)).

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

**Activate:** Select **Video Creator** from the model dropdown. The Video tool is automatically available when this workspace is selected.

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

**Activate:** Select **Music Producer** from the model dropdown. The Music tool is automatically available when this workspace is selected.

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
# Returns: {"status": "ok", "service": "music-mcp"}
```

**Output:** WAV file delivered as a chat attachment.

---

## 11. Text-to-Speech

**What:** Convert text to spoken audio using MLX-native speech (Kokoro + Qwen3-TTS).

**Activate:** Select **Music Producer** from the model dropdown. The TTS (text-to-speech) tool is automatically available in this workspace.

### Speak text

```
Read this aloud: Portal 5 is a complete local AI platform running entirely on your own hardware with zero cloud dependencies.
```

### Choose a voice

```
Read this with a British male voice: The quick brown fox jumps over the lazy dog.
```

### MLX Speech voices (Apple Silicon — primary)

| Voice ID | Backend | Description |
|----------|---------|-------------|
| `af_heart` | Kokoro | American English female (default) |
| `bm_george` | Kokoro | British English male |
| `Chelsie` | Qwen3-TTS | Preset speaker with style control |
| `Ryan` | Qwen3-TTS | Preset speaker |
| `Vivian` | Qwen3-TTS | Preset speaker |
| `design:A deep male narrator` | Qwen3-TTS | Voice created from text description |
| `clone:/path/to/reference.wav` | Qwen3-TTS | Voice cloned from 3-30s reference audio |

### Style control (Qwen3-TTS CustomVoice)

```
Read this in an excited, energetic tone: You won the lottery!
```

### Voice design

```
Read this: Hello world
Voice: design:A warm female voice with a slight British accent
```

### Direct API call

```bash
curl -X POST http://localhost:8918/v1/audio/speech \
  -H "Content-Type: application/json" \
  -d '{"input": "Hello from Portal 5!", "voice": "af_heart"}' \
  --output hello.wav
```

**Verify:**
```bash
curl -s http://localhost:8918/health
# Returns: {"status": "ok", "service": "mlx-speech", "voice_cloning": true}
```

---

## 12. Speech-to-Text (ASR)

**What:** Transcribe audio files to text using Qwen3-ASR (MLX-native).

**Activate:** Select any workspace from the model dropdown. The Whisper transcription tool is automatically available in all workspaces.

### Transcribe an audio file

Upload an audio file (MP3, WAV, M4A, etc.) and type:
```
Transcribe this audio file
```

### Direct API call

```bash
curl -X POST http://localhost:8918/v1/audio/transcriptions \
  -F "file=@recording.mp3" \
  -F "language=English"
```

**Supported formats:** MP3, WAV, M4A, FLAC, OGG, WebM

**Verify:**
```bash
curl -s http://localhost:8918/health
# Returns: {"status": "ok", "service": "mlx-speech"}
```

**Note:** The first transcription downloads the Qwen3-ASR model (~800MB). Subsequent calls are instant.

**Fallback:** Docker `mcp-whisper` (:8915) and `mcp-tts` (:8916) still run as backup on non-Apple-Silicon hosts.

---

## Diarized Transcription (Speaker-Labeled Transcripts)

**What:** Drop an audio file in OWUI chat, get back a transcript with speaker labels (SPEAKER_00, SPEAKER_01, ...). Outputs JSON + Markdown to the shared workspace at `~/AI_Output/generated/transcripts/`.

**Pre-flight (one-time):**

1. Visit `https://huggingface.co/pyannote/segmentation-3.0` — accept user conditions
2. Visit `https://huggingface.co/pyannote/speaker-diarization-3.1` — accept user conditions
3. Generate read token at `https://huggingface.co/settings/tokens`
4. Add to `.env`: `HF_TOKEN=hf_...`

**Start the service (Apple Silicon primary):**
```bash
./launch.sh start-transcribe
# First run downloads ~1.5 GB whisper-large-v3-turbo + ~30 MB pyannote
```

**Workflow A — Drop in chat (recommended for files <15 min):**

1. Open WebUI → select `Transcript Analyst` persona (Documents workspace)
2. Drag-drop an audio file (mp3, wav, m4a, ogg, flac) into the chat input
3. Type instructions, e.g., "transcribe with 2 speakers" or "summarize this meeting"
4. Hit submit
5. Persona detects the attachment, calls the transcription tool, displays the labeled transcript

The `transcriptanalyst` persona accepts:
- `"transcribe this"` — auto-detects speaker count
- `"transcribe with N speakers"` — passes `num_speakers=N` to constrain pyannote
- `"summarize this meeting"` — transcribe first, then produce a summary with decisions/action items
- `"make me a Word doc"` — transcribe, then chain to `create_word_document` for .docx output

**Workflow B — Long files (>15 min) or batch processing:**

For files where OWUI's tool timeout might bite (or for scripted use), call the HTTP endpoint directly:
```bash
curl -X POST http://localhost:8924/v1/audio/transcribe-with-speakers \
  -F "file=@long_meeting.mp3" \
  -F "num_speakers=3" | jq -r '.md_path'
# /Users/you/AI_Output/generated/transcripts/transcript_a3f2b1c4d5e6.md
```

Then in OWUI, ask the persona to "format the transcript at <md_path>".

**Tool timeout for long files:** OWUI's default MCP tool timeout is shorter than processing time for files >5 min. To raise it:
```bash
echo "TOOL_SERVER_REQUEST_TIMEOUT=1800" >> .env  # 30 minutes
./launch.sh restart open-webui
```

**Performance (M4 Pro, 10-min 2-speaker audio):** ~60–130s end-to-end. Versus Docker fallback path: ~4–8 min (CPU-bound). Time scales roughly linearly with audio length.

**Speaker count drift:** for files >15 min, pyannote can occasionally split one speaker into multiple IDs across long silences. If the result has more speakers than you expected, ask the persona to re-run with `num_speakers=<your_count>` to constrain.

**Verify:**
```bash
curl http://localhost:8924/health
# {"status":"ok","service":"mlx-transcribe","whisper_model":"...","diarization_loaded":false,"voxtral_loaded":false}
# (diarization_loaded / voxtral_loaded become true after first respective call)
```

**Output files:**
- `~/AI_Output/generated/transcripts/transcript_<id>.json` — structured data
- `~/AI_Output/generated/transcripts/transcript_<id>.md` — speaker-labeled markdown

Both also downloadable via `http://localhost:8924/files/<filename>`.

### Voxtral Multilingual Transcription

**What:** Mistral Voxtral-Mini-3B adds 8-language recognition (en, fr, de, es, it, pt, nl, ru) to the transcription stack. No diarization (single SPEAKER_00), but auto-language detection across supported languages.

**Pre-flight (one-time download, ~18.7 GB):**
```bash
./launch.sh pull-voxtral
# Downloads mlx-community/Voxtral-Mini-3B-2507-bf16 to the MLX model directory
# Only needed once; takes ~20 min on a 1 Gbps connection
```

**Use in chat:** Select the Transcript Analyst persona, then specify language:
- `"transcribe this — it's in French"` → engine auto-switches to Voxtral with `language=fr`
- `"multilingual meeting, no speaker labels needed"` → Voxtral, auto-detect language

**Direct API (select engine explicitly):**
```bash
# Voxtral — multilingual, no speaker labels
curl -X POST http://localhost:8924/v1/audio/transcribe-with-speakers \
  -F "file=@meeting_fr.mp3" \
  -F "language=fr" | jq -r '.text'
```

Or via MCP tool in a pipeline:
```json
{"engine": "voxtral-mini-3b", "language": "de"}
```

**Trade-offs:**

| | whisper-large-v3-turbo (default) | voxtral-mini-3b |
|---|---|---|
| Languages | English-optimized | en/fr/de/es/it/pt/nl/ru |
| Speaker labels | Yes (pyannote diarization) | No |
| Model size | ~3 GB | ~18.7 GB |
| Requires HF_TOKEN | Yes (pyannote) | No |
| Use case | Multi-speaker English meetings | Multilingual single-speaker audio |

### Workflow A is finally working — what changed

After TASK-OWUI-AUDIO-DROP-001 lands, three configuration items handle the gaps that previously broke chat-drop:

1. **`AIOHTTP_CLIENT_TIMEOUT_TOOL_SERVER_DATA=1800`** lifts OWUI's default ~60s tool-call timeout to 30 minutes.
2. **`WEBUI_SECRET_KEY`** is auto-generated and persistent so MCP tool registrations survive container rebuilds.
3. **`scripts/openwebui_init.py`** auto-registers the `portal_mlx_transcribe` MCP server on launch — no manual UI clicks.

**Sanity check after a fresh deploy:**
```bash
./tests/integration/test_owui_audio_drop.sh
# Expected: all checks pass
```

### When chat-drop still doesn't work — the runner script

Some OWUI builds enforce an additional internal 60s ceiling on tool calls that no env var lifts (open-webui#16902). If you hit that on a long file, use the manual runner:

```bash
./scripts/transcribe_and_complete.sh meeting.m4a --speakers 2
```

This script transcribes via curl, sends the transcript to the persona via OWUI's API, the persona renders the .docx via its `create_word_document` tool, then reviews its own output. Final .docx + transcript artifacts land next to your source audio. Same persona, same outputs, just orchestrated by the script instead of a chat session.

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

**How it works:** Documents are chunked into 1500-char segments with 100-char overlap, embedded using `microsoft/harrier-oss-v1-0.6b` (served by portal5-embedding TEI container on :8917), and searched with hybrid mode (semantic + keyword). Results are reranked by `bge-reranker-v2-m3` cross-encoder.

**Verify:**
```bash
# Embedding service should be healthy
curl -s http://localhost:8917/health
# Should return: {"status":"ok"}

# Or check inside Docker
docker exec portal5-embedding curl -s http://localhost:8917/health
```

### RAG Embedding & Reranking

Portal 5 v6.1+ uses Microsoft Harrier-0.6B as the primary embedding model for RAG, served by the `portal5-embedding` container (HuggingFace Text Embeddings Inference). This replaces the default Ollama `nomic-embed-text` with a SOTA embedding model that supports 32K context windows and 100+ languages.

**Architecture**: Open WebUI → portal5-embedding (:8917) → Harrier-0.6B embeddings → ChromaDB vector store → bge-reranker-v2-m3 cross-encoder reranking → results

**Configuration** (in docker-compose.yml, already set):
- `RAG_EMBEDDING_ENGINE=openai` — uses OpenAI-compatible API from TEI
- `RAG_OPENAI_API_BASE_URL=http://portal5-embedding:8917/v1`
- `RAG_EMBEDDING_MODEL=microsoft/harrier-oss-v1-0.6b`
- `RAG_RERANKING_MODEL=BAAI/bge-reranker-v2-m3`

**Fallback**: If the embedding service is unavailable, change `RAG_EMBEDDING_ENGINE=ollama` and `RAG_EMBEDDING_MODEL=nomic-embed-text:latest` in `.env` or docker-compose.yml to revert to Ollama-based embeddings.

**Memory impact**: The embedding service uses ~1.2GB. The reranker runs inside Open WebUI's process and uses ~0.6GB. Total: ~1.8GB always-on overhead.

### Cross-session memory

The AI remembers facts you share across conversations:
```
I'm working on a Python FastAPI project with PostgreSQL
```
Future sessions will remember this context.

**View memories:** Settings → Personalization → Memory

---

### Docling Document Parsing (RAG MCP :8921)

Portal 5's RAG MCP uses Docling (`docling>=2.0.0`, installed in `Dockerfile.mcp`)
for document text extraction during `kb_ingest`. This is separate from Open
WebUI's built-in RAG above.

| Feature | Without Docling | With Docling |
|---|---|---|
| PDF table extraction | Lost | Preserved as Markdown tables |
| Multi-column layout | Reading order scrambled | Correct reading order |
| Supported formats | .md, .txt, .pdf, .docx | + .pptx, .xlsx, .html, .htm, .epub |

`_read_file()` in `portal_mcp/rag/rag_mcp.py` tries Docling first for
PDF/DOCX/PPTX/XLSX/HTML/EPUB (in a worker thread, with a cached converter).
If Docling is unavailable, fails, or returns no usable text, it falls back to
pypdf (PDF) or python-docx (DOCX) — no loss of existing functionality. Docling
is a soft dependency: the MCP image includes it (model weights pre-fetched at
build time), the code does not hard-require it.

The `kb_ingest` tool surface is unchanged — you still point it at a directory;
the improvement is in what text gets extracted from each file.

Optional: Docling also ships an Open WebUI document-extraction integration
(OWUI Admin → Settings → Document Extraction), independent of this MCP. See
https://docs.openwebui.com/features/rag/document-extraction/docling

### LanceDB Search Modes, Indexing & Rollback (RAG MCP :8921)

**Search modes** — `kb_search` / `kb_search_all` accept `query_type`:

| query_type | What it does | When to use |
|---|---|---|
| `vector` (default) | Semantic similarity (bge embeddings) | Conceptual questions |
| `fts` | Native Lance BM25 keyword search | Exact terms: CIP-007 R2, CVE IDs, hostnames |
| `hybrid` | Vector + FTS fused with built-in RRF | Best of both; mixed queries |

`fts`/`hybrid` need an FTS index: re-ingest with `"fts": true` on `kb_ingest`.
`kb_search_all` silently falls back to vector for KBs without an index.
All modes keep the existing pipeline: 50 candidates -> bge reranker -> top_k.

**Vector indexing** — `kb_optimize` builds an IVF_PQ index (L2,
`num_partitions = min(512, sqrt(rows))`, `num_sub_vectors=64`). KBs under 256
chunks are skipped — brute force is already fast there. Run after large ingests:

```bash
curl -s localhost:8921/tools/kb_optimize -X POST \
  -H 'Content-Type: application/json' \
  -d '{"arguments": {"kb_id": "nerc-cip"}}'
```

**Version history & rollback** — every LanceDB write creates a version.
`kb_ingest` with `"rebuild": true` no longer drops the table; it tags the
current state (`pre-rebuild-<timestamp>`) and deletes rows, so a bad rebuild is
recoverable:

```bash
# list versions + tags
curl -s localhost:8921/tools/kb_versions -X POST \
  -H 'Content-Type: application/json' -d '{"arguments": {"kb_id": "nerc-cip"}}'

# roll back
curl -s localhost:8921/tools/kb_restore -X POST \
  -H 'Content-Type: application/json' \
  -d '{"arguments": {"kb_id": "nerc-cip", "version": 42}}'
```

Note: `optimize()` prunes **untagged** versions older than 7 days; the
automatic pre-rebuild tags are exempt. The restore itself is a new version, so
restores are undoable.

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

**Available workspaces:** `auto`, `auto-agentic`, `auto-agentic-lite`, `auto-audio`, `auto-bigfix`, `auto-blueteam`, `auto-cad`, `auto-coding`, `auto-coding-agentic`, `auto-coding-uncensored`, `auto-coding-uncensored-agentic`, `auto-compliance`, `auto-creative`, `auto-daily`, `auto-data`, `auto-devstral`, `auto-documents`, `auto-extract-uncensored`, `auto-gemma-e4b`, `auto-gemma-fast`, `auto-gemma-vision`, `auto-general-uncensored`, `auto-glm`, `auto-glm-thinking`, `auto-math`, `auto-mistral`, `auto-music`, `auto-pentest`, `auto-phi4`, `auto-purpleteam`, `auto-purpleteam-deep`, `auto-purpleteam-exec`, `auto-reasoning`, `auto-redteam`, `auto-redteam-deep`, `auto-research`, `auto-security`, `auto-security-uncensored`, `auto-spl`, `auto-video`, `auto-vision`, `tools-specialist`

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

## Shared Workspace

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
    ├── videos/             ← Video MCP outputs
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
from portal_mcp.core import get_uploads_dir, get_generated_dir, resolve_upload_path

# Read a file dropped by the user in OWUI chat
audio_path = resolve_upload_path(file_id_from_chat)

# Write your tool's output
out = get_generated_dir("transcripts") / f"transcript_{uid}.json"
out.write_text(json_payload)
```

**Drop-and-process workflow:** when a user drags an audio/document/image into OWUI chat, the file lands at `~/AI_Output/uploads/<file_id>`. The persona consuming the message can call any MCP tool and pass the file path; the MCP container sees the same file at `/workspace/uploads/<file_id>`.

**Auto-STT note:** Open WebUI's auto-transcription (`AUDIO_STT_ENGINE`) is disabled. Audio file uploads in chat stay as attachments — personas process them via MCP tools (e.g., `transcribe_with_speakers`). **Side effect:** voice-input via the OWUI microphone button does not transcribe. To re-enable voice-input only, see KNOWN_LIMITATIONS.md.

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

---

## 21. Remote API Access (Pipeline at :9099)

**What:** The Portal Pipeline exposes an OpenAI-compatible HTTP API. Any tool that accepts a custom OpenAI base URL can connect directly — no Open WebUI required.

### Authentication

All requests require `PIPELINE_API_KEY` from `.env` as a Bearer token:

```bash
PIPELINE_API_KEY=$(grep PIPELINE_API_KEY .env | cut -d= -f2)
```

### Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Service health check |
| GET | `/metrics` | Prometheus metrics (text format) |
| GET | `/v1/models` | List all workspaces and personas |
| POST | `/v1/chat/completions` | Send messages, stream or blocking |

### Base URL

- **Local:** `http://localhost:9099`
- **LAN (same network):** `http://<your-machine-ip>:9099`
- **Remote via reverse proxy:** `https://portal.yourdomain.com:9099`

### List available models

```bash
curl -s http://localhost:9099/v1/models \
  -H "Authorization: Bearer $PIPELINE_API_KEY" \
  | python3 -m json.tool | grep '"id"'
# Returns: auto, auto-daily, auto-coding, auto-security, auto-vision, ... + all 102 personas
```

### Chat (blocking)

```bash
curl -s http://localhost:9099/v1/chat/completions \
  -H "Authorization: Bearer $PIPELINE_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "auto-coding",
    "messages": [{"role": "user", "content": "Write a Python function to parse ISO 8601 dates"}],
    "stream": false
  }' | python3 -c "import sys,json; print(json.load(sys.stdin)['choices'][0]['message']['content'])"
```

### Chat (streaming)

```bash
curl -s http://localhost:9099/v1/chat/completions \
  -H "Authorization: Bearer $PIPELINE_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "auto-reasoning",
    "messages": [{"role": "user", "content": "Explain the CAP theorem"}],
    "stream": true
  }'
# SSE stream: data: {"choices":[{"delta":{"content":"..."}}]}
```

### Using the OpenAI Python SDK

```python
from openai import OpenAI
import os

client = OpenAI(
    base_url="http://localhost:9099/v1",
    api_key=os.environ["PIPELINE_API_KEY"],
)

response = client.chat.completions.create(
    model="auto-security",
    messages=[{"role": "user", "content": "Review this nginx config for security issues:\nserver { listen 80; root /var/www; }"}],
)
print(response.choices[0].message.content)
```

### Compatible tools

Any tool with a configurable OpenAI API base URL works out-of-the-box:

| Tool | Setting | Value |
|------|---------|-------|
| **Continue.dev** (VS Code/JetBrains) | `apiBase` | `http://localhost:9099/v1` |
| **Cursor** | Custom model → Base URL | `http://localhost:9099/v1` |
| **Aider** | `--openai-api-base` | `http://localhost:9099/v1` |
| **LM Studio** (client mode) | API Base URL | `http://localhost:9099/v1` |
| **Jan** | OpenAI-compatible server | `http://localhost:9099/v1` |
| **Shell scripts** | `curl` with `-H "Authorization: Bearer ..."` | see examples above |
| **Python scripts** | `openai.OpenAI(base_url=...)` | see example above |

**Model selection:** Use any workspace ID (`auto`, `auto-coding`, `auto-security`, etc.) or any persona slug (`redteamoperator`, `magistralstrategist`, etc.) as the `model` field. The pipeline routes to the appropriate backend automatically.

### Verify

```bash
# Health check
curl -s http://localhost:9099/health
# Returns: {"status": "ok", "backends": {...}}

# End-to-end test
curl -s http://localhost:9099/v1/chat/completions \
  -H "Authorization: Bearer $PIPELINE_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model": "auto", "messages": [{"role": "user", "content": "Say OK"}], "stream": false}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['choices'][0]['message']['content'])"
```

**Verify:**
```bash
./launch.sh status
# Shows all backends and their health status
```

---

## 22. MLX Acceleration (Apple Silicon) — RETIRED

> **Retired (commit 3a0c58e).** The MLX inference proxy was removed; all chat
> inference now runs through Ollama (:11434) with its native MLX Metal backend.
> The MLX *speech* (:8918) and *transcription* (:8924) servers documented
> elsewhere in this guide are unaffected and remain in use.

---

## 23. Metrics & Monitoring

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
./launch.sh update          # Full update: git pull, Docker images, rebuilds, model refresh, re-seed
./launch.sh update --skip-models  # Update without model refresh (faster)
./launch.sh update --models-only  # Only refresh Ollama models
./launch.sh rebuild         # Rebuild portal-pipeline Docker image after git pull
./launch.sh prune           # Prune Docker resources

# Models
./launch.sh pull-models     # Pull all Ollama models (30-90 min)
./launch.sh refresh-models  # Re-pull models (update existing)
./launch.sh import-gguf <path> [name]  # Import a local .gguf file into Ollama
./launch.sh start-speech    # Start MLX Speech server (Qwen3-TTS + Qwen3-ASR)
./launch.sh stop-speech     # Stop MLX Speech server

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
./launch.sh reseed          # Force-refresh all presets (delete + recreate)
./launch.sh clean           # Wipe Open WebUI data (keep models)
./launch.sh clean-all       # Wipe everything including models

# ComfyUI
./launch.sh install-comfyui              # Install ComfyUI
./launch.sh download-comfyui-models      # Download image/video models

# Music
./launch.sh install-music                # Install Music MCP natively

# Testing
./launch.sh test            # Run live smoke tests
pytest tests/ -v --tb=short # Run unit tests (no Docker needed)
```

---

*Last updated: 2026-05-21 | Portal 6.1.0*
