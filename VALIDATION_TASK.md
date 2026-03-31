# Portal 5.2 — Claude Code Validation Task

## What This Does

Validates every feature in `docs/HOWTO.md` by hitting real APIs, creating real files, and driving the real GUI via Chromium. Produces `VALIDATION_RESULTS.md` with a pass/fail for every check plus documentation corrections.

**Run from:** `cd ~/portal-5` (production system, stack running)

---

## Setup (one time)

```bash
cd ~/portal-5

# Stack must be running
./launch.sh status || ./launch.sh up

# Validation dependencies
pip install httpx pyyaml playwright
python3 -m playwright install chromium

# Dev dependencies for unit tests
pip install -e ".[dev]"
```

---

## Step 1 — Unit tests + lint

```bash
pytest tests/ -v --tb=short
ruff check .
ruff format --check .
```

Fix any failures before proceeding.

---

## Step 2 — Workspace consistency check

```bash
python3 -c "
import yaml
from portal_pipeline.router_pipe import WORKSPACES
cfg = yaml.safe_load(open('config/backends.yaml'))
pipe_ids = set(WORKSPACES.keys())
yaml_ids = set(cfg['workspace_routing'].keys())
assert pipe_ids == yaml_ids, f'MISMATCH: pipe_only={pipe_ids-yaml_ids} yaml_only={yaml_ids-pipe_ids}'
print(f'OK: {len(pipe_ids)} workspace IDs consistent')
"
```

---

## Step 3 — Run the full validation

```bash
python3 portal5_full_validation.py
```

### What each test does

| # | Test | HOWTO § | What it actually does |
|---|------|---------|----------------------|
| 1 | Workspace Enumeration | §3 | GET /v1/models — verifies all 13 workspace IDs present |
| 2 | Chat Through Every Workspace | §2-4 | POST /v1/chat/completions 13 times (one per workspace), non-streaming, verifies a real response with content |
| 3 | MCP Health + Tool Discovery | §5,7-12 | GET /health and GET /tools on all 7 MCP servers (:8910-8916) |
| 4 | Document Creation | §7 | MCP JSON-RPC `create_word_document` (real .docx), `create_powerpoint` (3 slides), `create_excel` (budget data) — verifies `"success": true` |
| 5 | Code Sandbox | §5 | MCP JSON-RPC `execute_python` with `print(sum(range(1,101)))` — checks output contains `5050` |
| 6 | TTS Audio | §11 | POST /v1/audio/speech with two voices (`af_heart`, `bm_george`) — verifies response is WAV (checks RIFF header bytes) |
| 7 | Music Generation | §10 | MCP JSON-RPC `generate_music` — 5-second clip, small model — checks for success or AudioCraft-not-installed |
| 8 | Image Generation | §8 | Checks ComfyUI :8188 first, then MCP JSON-RPC `generate_image` via :8910 |
| 9 | Video Generation | §9 | Checks ComfyUI + Wan2.2, then MCP JSON-RPC `generate_video` via :8911 |
| 10 | Content-Aware Routing | §6 | Sends security keywords through `auto` workspace — verifies auto-redirect to `auto-redteam` |
| 11 | Metrics & Monitoring | §22 | Pipeline /metrics for portal_* counters, Prometheus healthy, Grafana healthy |
| 12 | Tool Wiring Audit | — | Verifies every workspace JSON has correct `toolIds` matching `update_workspace_tools.py`, checks MCP server registrations, flags bundle file discrepancy |
| 13 | Chromium GUI | §2-4 | Login with real credentials, find model selector, count workspace names in dropdown, type in chat textarea, navigate to admin panel, audit the + button behavior |
| 14 | HOWTO Accuracy | — | Flags the "Click + → enable" documentation error, checks tool activation documentation, flags bundle toolIds gap |

---

## Step 4 — Review results

```bash
cat VALIDATION_RESULTS.md
```

Screenshots saved to `/tmp/p5_gui_*.png`.

---

## Step 5 — Fix failures

| Result | Diagnosis | Fix |
|--------|-----------|-----|
| MCP server FAIL | Container down | `docker compose -f deploy/portal-5/docker-compose.yml restart <service>` |
| Workspace 503 | Model not pulled | `ollama pull <model>` or `./launch.sh pull-models` |
| TTS 503 | kokoro model downloading | Wait 60s, retry |
| Music timeout | AudioCraft model downloading (~300MB) | Wait, retry |
| Image/Video SKIP | ComfyUI not on host | `./launch.sh install-comfyui` |
| GUI login FAIL | Wrong password | Check `OPENWEBUI_ADMIN_PASSWORD` in `.env` |
| Workspace count < 13 | Seeding incomplete | `./launch.sh seed` |
| ToolWiring FAIL | toolIds wrong in workspace JSON | Run `python3 scripts/update_workspace_tools.py` then `./launch.sh seed` |
| HOWTO WARN | Documentation error | See "Known Issues" below |

After fixes:
```bash
python3 portal5_full_validation.py
```

---

## Known Issues Found

### 1. HOWTO "Click + → enable tools" is wrong

**Where:** HOWTO sections 5, 7, 8, 9, 10, 11, 12

**What it says:**
> Click **+** → enable `Portal Documents`

**What actually happens:** Each workspace JSON has a `toolIds` array that auto-activates MCP tools when the workspace is selected. Example from `workspace_auto_documents.json`:
```json
{ "meta": { "toolIds": ["portal_documents", "portal_code"] } }
```

The `+` button in the chat input is for **file uploads**, not tool activation.

**Fix:** Replace all "Click + → enable" instructions with:
> Select **Portal Document Builder** from the model dropdown. The Documents and Code tools are automatically available.

### 2. `portal_import_bundle.json` workspaces lack toolIds

The individual workspace files (`imports/openwebui/workspaces/workspace_*.json`) have correct `toolIds`. The bundle file (`portal_import_bundle.json`) does not. The automated seeding (`openwebui_init.py`) reads individual files so this works — but someone doing a manual GUI import from the bundle gets workspaces with **no tools attached**.

**Fix:** Add `toolIds` to each workspace in `portal_import_bundle.json`, or document that manual import must use individual workspace files.

### 3. Bundle missing 4 workspaces

Bundle has 9 workspaces. Individual files have 13. Missing: `auto-blueteam`, `auto-redteam`, `auto-vision`, `auto-data`.

**Fix:** Regenerate the bundle from the individual files.

---

## Claude Code execution

```bash
cd ~/portal-5
claude --dangerously-skip-permissions
```

Then:

> Execute portal5_full_validation.py. For every FAIL, diagnose with docker logs and source code, apply a fix, and re-run. For every HOWTO documentation error, draft the corrected text. Write all findings to VALIDATION_RESULTS.md.

---

*Portal 5.2.0 · 2026-03-30*
