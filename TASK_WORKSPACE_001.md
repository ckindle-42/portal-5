# TASK: Unified Shared Workspace — File-Bridging Foundation

**Task ID:** TASK-WORKSPACE-001
**Version target:** v6.1.0
**Priority:** Normal — foundational; unblocks TASK-TRANSCRIBE-001 and future file-handling MCPs
**Category:** Architecture / Infrastructure
**Protected files touched:** `docs/HOWTO.md`, `CLAUDE.md` (both append-only via str_replace at named anchors)
**Estimated risk:** Low-medium — touches docker-compose volume mounts and OWUI configuration; reversible via git revert + `./launch.sh restart`
**Depends on:** None
**Blocks:** TASK-TRANSCRIBE-001 (revised version) — must execute before transcription rebuild

---

## Problem Statement

Portal 5 has at least four disconnected filesystem namespaces:

1. **Host filesystem** — `~/AI_Output/` (used by `mlx-speech.py`, `mlx-proxy.py`)
2. **Docker MCP containers** — `/app/data/generated/` (mounted from `${AI_OUTPUT_DIR}` for `mcp-documents`, `mcp-tts`, `mcp-comfyui`; not mounted at all for `mcp-whisper`, `mcp-music`, `mcp-video`, etc.)
3. **OWUI named volume** — `open-webui-data:/app/backend/data/` containing user uploads at `uploads/<file_id>` — **not visible to anything else**
4. **HF cache + model weights** — separate volumes per service

The user-facing consequence: a file dropped into Open WebUI chat exists only inside the OWUI container's named volume. An MCP server (host-native or in another container) cannot read it. This forces every cross-tool flow into HTTP indirection (file uploads through MCP HTTP endpoints) or operator-managed paths (curl from host).

The platform-facing consequence: every new MCP that handles user files must solve file-bridging from scratch. The TASK-TRANSCRIBE-001 design exposed this; future OCR, video analysis, document QA, and code-on-uploads tools will hit the same wall.

This task establishes a unified shared workspace at `${AI_OUTPUT_DIR}` (default `~/AI_Output/`) with a standard subdirectory layout. OWUI uploads and MCP outputs land at the same physical paths, visible to all services that mount the workspace. The task is intentionally minimal — it does not migrate existing services; it adds the shared mount points, the OWUI-side bridge, and the helper module new code will use.

## Decision Log

| Decision | Choice | Why |
|---|---|---|
| Workspace root | `${AI_OUTPUT_DIR:-${HOME}/AI_Output}` | Already the de-facto convention in `.env.example` and `docker-compose.yml`. Standardize, don't rename. |
| Mount point in containers | `/workspace` | Distinct from the existing `/app/data/generated` mount used by current MCPs. New code uses `/workspace`; existing MCPs keep their current paths until next opportunistic migration. |
| Subdirectory layout | `uploads/`, `generated/<category>/` | Two-level: source vs derived. Categories mirror MCP names (`transcripts`, `documents`, `images`, `videos`, `music`, `speech`). |
| OWUI uploads handling | Bind-mount overlay on `/app/backend/data/uploads` | Surgical — leaves OWUI's database, config, RAG storage in the named volume; only files become host-visible. |
| Auto-STT (`AUDIO_STT_ENGINE`) | **Disabled** | Per operator decision. Removes auto-transcription on file drop. **Side effect:** voice-input via microphone in OWUI is also disabled (global toggle). Documented in KNOWN_LIMITATIONS. |
| Existing MCP migration | **Not in scope** | `mcp-documents`, `mcp-tts`, `mcp-comfyui` keep their current `/app/data/generated` mount and write to the workspace root (flat). Future task migrates them to `/workspace/generated/<category>/` on next opportunistic touch. |
| Helper module | New `portal_mcp/core/workspace.py` | Provides `get_uploads_dir()`, `get_generated_dir(category)`, `resolve_upload_path(file_id)`. New MCPs use this; old ones continue with bare paths. |
| Permissions | Mode 0775, group writable | Works for OWUI's root-user container and MCP `portal:portal` user. Set explicitly during workspace-init. |
| Migration of pre-existing OWUI uploads | One-time copy in pre-flight | If the named volume already contains uploads, copy them to the host bind mount before the overlay takes effect. Otherwise overlay hides them. |

**Rejected alternatives:**

- **Single big `/workspace` mount replacing `/app/data/generated`:** Breaks the existing MCPs' code paths. Forced migration is risky for v1 of this task; opt for additive.
- **Sidecar service that proxies file access between OWUI and MCPs:** Adds network latency, an additional moving part, and a new failure mode. Bind mounts are simpler and faster.
- **Move all OWUI data to a bind mount (replace `open-webui-data` named volume):** Forces full data migration on existing deployments. The overlay-on-uploads approach achieves the goal with no impact on existing OWUI databases.
- **Keep auto-STT enabled with redirect to mlx-transcribe diarization:** Operator chose disable. Re-enabling later (e.g., for voice-input only) is a separate task.

## What This Task Does NOT Do

To keep scope tight and risk low:

- **Does not migrate existing MCPs (`mcp-documents`, `mcp-tts`, `mcp-comfyui`) to the new layout.** They keep writing to `~/AI_Output/` flat. Migration is a future opportunistic cleanup.
- **Does not add retention/cleanup logic.** Future task — `./launch.sh workspace-clean --age=30d` or similar.
- **Does not implement transcription.** That's TASK-TRANSCRIBE-001 (revised), which depends on this.
- **Does not change OWUI's database, RAG storage, or any data outside `uploads/`.** Surgical scope.
- **Does not restore voice-input via microphone.** Auto-STT disabled is the trade-off; restoration is a separate concern (Function-based or alternative input route).

---

## Pre-Flight Checks

```bash
cd ~/portal-5
git status                          # clean working tree
git rev-parse --abbrev-ref HEAD     # main
git pull --ff-only

# Baseline: workspace consistency check (CLAUDE.md Rule 6)
python3 -c "
import yaml
from portal_pipeline.router.workspaces import WORKSPACES
cfg = yaml.safe_load(open('config/backends.yaml'))
pipe_ids = set(WORKSPACES.keys())
yaml_ids = set(cfg['workspace_routing'].keys())
assert pipe_ids == yaml_ids, f'Mismatch: pipe={pipe_ids-yaml_ids} yaml={yaml_ids-pipe_ids}'
print('✅ Workspace IDs consistent (baseline)')
"

# Baseline: tests + lint pass
pytest tests/unit/ -q --tb=no
ruff check . && ruff format --check .

# Baseline: AI_OUTPUT_DIR resolves
echo "AI_OUTPUT_DIR resolves to: ${AI_OUTPUT_DIR:-${HOME}/AI_Output}"
test -d "${AI_OUTPUT_DIR:-${HOME}/AI_Output}" && \
  echo "✅ Workspace root exists" || \
  { mkdir -p "${AI_OUTPUT_DIR:-${HOME}/AI_Output}" && echo "✅ Workspace root created"; }

# Baseline: detect existing OWUI uploads in the named volume
# (these need to be migrated to host bind mount in Phase 1)
EXISTING_UPLOADS=$(docker compose -f deploy/portal-5/docker-compose.yml exec -T open-webui \
  ls /app/backend/data/uploads/ 2>/dev/null | wc -l || echo 0)
echo "Existing OWUI uploads in named volume: ${EXISTING_UPLOADS} files"
# Non-fatal — informational. Phase 1 handles migration.

# Baseline: containers running
docker compose -f deploy/portal-5/docker-compose.yml ps --format json | \
  python3 -c "import json, sys; [print(c.get('Service'), c.get('State')) for c in [json.loads(l) for l in sys.stdin if l.strip()]]"
# Expected: open-webui, portal-pipeline, mcp-* all 'running'
```

If any baseline step fails, STOP and resolve before proceeding. The OWUI uploads migration is the only step that may produce a non-zero count — that's expected and handled below.

---

## Phase 0 — Branch & Workspace Initialization

```bash
git checkout -b feat/shared-workspace

# Create the canonical directory structure on the host
WORKSPACE="${AI_OUTPUT_DIR:-${HOME}/AI_Output}"
mkdir -p "${WORKSPACE}"/{uploads,generated/transcripts,generated/documents,generated/images,generated/videos,generated/music,generated/speech}
chmod -R 0775 "${WORKSPACE}"
ls -la "${WORKSPACE}/"
# Expected: drwxrwxr-x for all subdirs
```

### Migrate existing OWUI uploads (if any)

If the pre-flight detected files in OWUI's named volume, copy them to the bind mount path before the overlay takes effect:

```bash
if [ "${EXISTING_UPLOADS:-0}" -gt 0 ]; then
  echo "Migrating ${EXISTING_UPLOADS} existing OWUI uploads to ${WORKSPACE}/uploads/"
  docker compose -f deploy/portal-5/docker-compose.yml cp \
    open-webui:/app/backend/data/uploads/. "${WORKSPACE}/uploads/"
  ls -la "${WORKSPACE}/uploads/" | head -10
fi
```

**Verification:** files visible at `${WORKSPACE}/uploads/` from the host shell. If migration fails, do not proceed — the overlay would hide existing user data.

---

## Phase 1 — `.env.example` Updates

### File 1: `.env.example` (MODIFY)

Standardize `AI_OUTPUT_DIR` as the canonical name. Keep `OUTPUT_DIR` as a backward-compat alias for existing MCP code paths.

**Find this block (line ~162-165):**
```
# ── Output Directory ─────────────────────────────────────────────────────────
# Where generated files (images, audio, video, documents) are saved.
# All MCP servers (TTS, Music, Documents) read this as OUTPUT_DIR.
OUTPUT_DIR=${HOME}/AI_Output
```

**Replace with:**
```
# ── Shared Workspace ─────────────────────────────────────────────────────────
# Canonical user-artifact root (TASK-WORKSPACE-001).
# All MCPs read uploads from ${AI_OUTPUT_DIR}/uploads/
# All MCPs write outputs to ${AI_OUTPUT_DIR}/generated/<category>/
# OWUI bind-mounts ${AI_OUTPUT_DIR}/uploads to /app/backend/data/uploads.
AI_OUTPUT_DIR=${HOME}/AI_Output

# Legacy alias — existing MCPs (documents, tts, comfyui) still read this.
# Points at the same path; remove once all MCPs are migrated to /workspace.
OUTPUT_DIR=${AI_OUTPUT_DIR}
```

Also add the new env var for OWUI auto-STT control. Find the OWUI section or add a new block:

**Add (anywhere logical, e.g., after the Speech config near line 200 if present):**
```
# ── Open WebUI Audio STT ─────────────────────────────────────────────────────
# AUDIO_STT_ENGINE controls Open WebUI's auto-transcription of audio uploads
# AND microphone voice input. Disabling it (empty value) means:
#   - Audio files dropped in chat stay as attachments (handled by personas via tools)
#   - Voice-input via microphone in OWUI no longer transcribes
# This is the configured behavior for diarized-transcription workflows.
# To re-enable voice-input only, see TASK-FUT (not yet scoped).
OWUI_AUDIO_STT_ENGINE=
```

**Verification:**
```bash
grep -E "^AI_OUTPUT_DIR|^OUTPUT_DIR|^OWUI_AUDIO_STT_ENGINE" .env.example
# Expected: 3 lines, exact matches
```

---

## Phase 2 — `docker-compose.yml` Updates

### File 2: `deploy/portal-5/docker-compose.yml` (MODIFY)

Three groups of changes: OWUI uploads bind mount, audio STT disable, and `/workspace` mount on all MCPs that handle user files.

#### Change 2a — OWUI uploads bind mount overlay

**Find this block (around line 143-145):**
```yaml
    volumes:
      - open-webui-data:/app/backend/data
    environment:
```

**Replace with:**
```yaml
    volumes:
      - open-webui-data:/app/backend/data
      # TASK-WORKSPACE-001: bind-mount uploads onto the named volume so
      # files dropped in chat are visible to MCPs at the same physical path.
      # The named volume retains everything else (database, RAG, config).
      - ${AI_OUTPUT_DIR:-${HOME}/AI_Output}/uploads:/app/backend/data/uploads
    environment:
```

#### Change 2b — Disable auto-STT in OWUI

**Find this block (around line 218-228):**
```yaml
      # ── Speech (MLX-native on host via mlx-audio) ───────────────────────────
      # Primary: mlx-speech server on host (:8918) — Qwen3-TTS + Qwen3-ASR + Kokoro
      # Fallback: Docker mcp-tts (:8916) and mcp-whisper (:8915) still run as backup
      - AUDIO_TTS_ENGINE=openai
      - AUDIO_TTS_OPENAI_API_BASE_URL=${MLX_SPEECH_URL:-http://host.docker.internal:8918}
      - AUDIO_TTS_OPENAI_API_KEY=portal-speech
      - AUDIO_TTS_MODEL=kokoro
      - AUDIO_TTS_VOICE=af_heart
      - AUDIO_STT_ENGINE=openai
      - AUDIO_STT_OPENAI_API_BASE_URL=${MLX_SPEECH_URL:-http://host.docker.internal:8918}
      - AUDIO_STT_OPENAI_API_KEY=portal-speech
```

**Replace with:**
```yaml
      # ── Speech (MLX-native on host via mlx-audio) ───────────────────────────
      # Primary: mlx-speech server on host (:8918) — Qwen3-TTS + Kokoro for TTS
      # TTS still goes through mlx-speech; STT is DISABLED globally (TASK-WORKSPACE-001).
      # Audio uploads in chat stay as attachments — personas handle them via the
      # transcribe_with_speakers MCP tool. Side effect: voice-input via microphone
      # is also disabled. See KNOWN_LIMITATIONS.md.
      - AUDIO_TTS_ENGINE=openai
      - AUDIO_TTS_OPENAI_API_BASE_URL=${MLX_SPEECH_URL:-http://host.docker.internal:8918}
      - AUDIO_TTS_OPENAI_API_KEY=portal-speech
      - AUDIO_TTS_MODEL=kokoro
      - AUDIO_TTS_VOICE=af_heart
      - AUDIO_STT_ENGINE=${OWUI_AUDIO_STT_ENGINE:-}
```

The `${OWUI_AUDIO_STT_ENGINE:-}` resolves to empty by default, which OWUI interprets as "no STT engine configured" → no auto-transcription. The operator can override via `.env` if they want to re-enable later.

#### Change 2c — Add `/workspace` mount to MCPs that handle user files

For each MCP that does or will handle user-uploaded files, add the workspace bind mount. This task adds the mount; individual MCPs adopt it when they're next touched.

**Target services:** `mcp-whisper` (will be touched by TASK-TRANSCRIBE-001), `mcp-music`, `mcp-video`, `mcp-sandbox` (read-only OK for sandbox).

For `mcp-whisper`, find this block (around line 328-348):
```yaml
  mcp-whisper:
    build:
      context: ../..
      dockerfile: Dockerfile.mcp
    container_name: portal5-mcp-whisper
    restart: unless-stopped
    ports:
      - "127.0.0.1:${WHISPER_HOST_PORT:-8915}:8915"
    environment:
      - WHISPER_MCP_PORT=8915
      - MCP_PORT=8915
      - HF_HOME=/app/data/hf_cache
      - HF_TOKEN=${HF_TOKEN:-}
    command: ["python", "-m", "portal_mcp.generation.whisper_mcp"]
    volumes:
      - portal5-hf-cache:/app/data/hf_cache
    healthcheck:
```

**Add `WORKSPACE_DIR` env + workspace mount.** Replace with:
```yaml
  mcp-whisper:
    build:
      context: ../..
      dockerfile: Dockerfile.mcp
    container_name: portal5-mcp-whisper
    restart: unless-stopped
    ports:
      - "127.0.0.1:${WHISPER_HOST_PORT:-8915}:8915"
    environment:
      - WHISPER_MCP_PORT=8915
      - MCP_PORT=8915
      - HF_HOME=/app/data/hf_cache
      - HF_TOKEN=${HF_TOKEN:-}
      - WORKSPACE_DIR=/workspace
    command: ["python", "-m", "portal_mcp.generation.whisper_mcp"]
    volumes:
      - portal5-hf-cache:/app/data/hf_cache
      - ${AI_OUTPUT_DIR:-${HOME}/AI_Output}:/workspace
    healthcheck:
```

**For `mcp-music`** — locate the service block (search for `container_name: portal5-mcp-music` or similar). Apply the same pattern: add `- WORKSPACE_DIR=/workspace` to environment, add `- ${AI_OUTPUT_DIR:-${HOME}/AI_Output}:/workspace` to volumes. (Music MCP runs host-native if installed — Docker fallback may not exist; check for the service block and skip if absent.)

**For `mcp-video`** — same pattern.

**For `mcp-sandbox`** — same pattern but with `:ro` (read-only) suffix on the mount, since sandbox should not write to user space:
```yaml
      - ${AI_OUTPUT_DIR:-${HOME}/AI_Output}:/workspace:ro
```

**Verification:**
```bash
# Validate compose syntax
docker compose -f deploy/portal-5/docker-compose.yml config > /dev/null && echo "✅ compose syntax OK"

# Confirm new mounts in rendered config
docker compose -f deploy/portal-5/docker-compose.yml config | grep -A1 "/workspace"
# Expected: each touched service shows the new bind

# Confirm OWUI uploads overlay
docker compose -f deploy/portal-5/docker-compose.yml config | \
  awk '/open-webui:/,/environment:/' | grep "uploads"
# Expected: shows the bind mount line

# Confirm AUDIO_STT_ENGINE is empty
docker compose -f deploy/portal-5/docker-compose.yml config | grep AUDIO_STT_ENGINE
# Expected: AUDIO_STT_ENGINE: '' or AUDIO_STT_ENGINE: null
```

---

## Phase 3 — Workspace Helper Module

### File 3: `portal_mcp/core/__init__.py` (NEW)

```python
"""Portal 5 MCP shared core utilities.

Provides cross-MCP helpers like workspace path resolution. New MCPs should
prefer these helpers over re-implementing path logic. See workspace.py.
"""

from portal_mcp.core.workspace import (
    get_generated_dir,
    get_uploads_dir,
    get_workspace_root,
    resolve_upload_path,
)

__all__ = [
    "get_generated_dir",
    "get_uploads_dir",
    "get_workspace_root",
    "resolve_upload_path",
]
```

### File 4: `portal_mcp/core/workspace.py` (NEW)

```python
"""Shared workspace path helpers (TASK-WORKSPACE-001).

Canonical paths:
  - Workspace root: $WORKSPACE_DIR (default /workspace) inside containers,
    or $AI_OUTPUT_DIR (default ~/AI_Output) on the host.
  - Uploads:        <root>/uploads/
  - Generated:      <root>/generated/<category>/

Categories:
  transcripts, documents, images, videos, music, speech

Use these helpers instead of hardcoding paths so that a future remap (e.g.,
mounting at a different container path) requires no code changes.
"""

from __future__ import annotations

import os
from pathlib import Path

# Container default; on host, callers can pass a path or set AI_OUTPUT_DIR.
_DEFAULT_WORKSPACE = "/workspace"
_VALID_CATEGORIES = frozenset(
    {"transcripts", "documents", "images", "videos", "music", "speech"}
)


def get_workspace_root() -> Path:
    """Return the workspace root for the current process.

    Resolution order:
      1. WORKSPACE_DIR env var (set in Docker compose for participating MCPs)
      2. AI_OUTPUT_DIR env var (host-native services)
      3. /workspace (container default)
      4. ~/AI_Output (host fallback)
    """
    candidate = os.getenv("WORKSPACE_DIR") or os.getenv("AI_OUTPUT_DIR")
    if candidate:
        return Path(candidate)
    container_default = Path(_DEFAULT_WORKSPACE)
    if container_default.is_dir():
        return container_default
    return Path.home() / "AI_Output"


def get_uploads_dir() -> Path:
    """Return the uploads directory, creating it if missing."""
    p = get_workspace_root() / "uploads"
    p.mkdir(parents=True, exist_ok=True)
    return p


def get_generated_dir(category: str) -> Path:
    """Return a category-specific generated output directory.

    Args:
        category: One of: transcripts, documents, images, videos, music, speech.

    Raises:
        ValueError: if category is not in the canonical set.
    """
    if category not in _VALID_CATEGORIES:
        raise ValueError(
            f"Unknown category {category!r}. "
            f"Valid: {sorted(_VALID_CATEGORIES)}"
        )
    p = get_workspace_root() / "generated" / category
    p.mkdir(parents=True, exist_ok=True)
    return p


def resolve_upload_path(file_id_or_name: str) -> Path | None:
    """Resolve an OWUI upload reference to an absolute path on disk.

    Args:
        file_id_or_name: Either a bare file ID (UUID-like, no extension) as
            OWUI stores it, or a full filename. Tries direct match first,
            then prefix match against entries in the uploads directory.

    Returns:
        Absolute Path if found, None otherwise.
    """
    uploads = get_uploads_dir()

    # Direct match
    direct = uploads / file_id_or_name
    if direct.is_file():
        return direct.resolve()

    # Prefix match (file_id without extension)
    candidates = list(uploads.glob(f"{file_id_or_name}*"))
    candidates = [c for c in candidates if c.is_file()]
    if len(candidates) == 1:
        return candidates[0].resolve()
    if len(candidates) > 1:
        # Ambiguous — prefer exact prefix + most recent
        candidates.sort(key=lambda c: c.stat().st_mtime, reverse=True)
        return candidates[0].resolve()

    return None
```

**Verification:**
```bash
ruff check portal_mcp/core/
ruff format --check portal_mcp/core/
python3 -c "
from portal_mcp.core.workspace import get_workspace_root, get_uploads_dir, get_generated_dir
print('Root:', get_workspace_root())
print('Uploads:', get_uploads_dir())
print('Transcripts:', get_generated_dir('transcripts'))
try:
    get_generated_dir('bogus')
except ValueError as e:
    print('Validation OK:', e)
"
# Expected: paths print, validation error fires for 'bogus' category
```

---

## Phase 4 — `launch.sh` Updates

### File 5: `launch.sh` (MODIFY — add workspace commands)

Three new commands: `workspace-init` (create directory structure), `workspace-status` (disk usage by category), `workspace-show` (show resolved paths).

Locate a stable insertion point for new commands. The existing pattern uses `command)` blocks within a `case` statement at the bottom of the file. Add the new blocks alongside the `start-speech)` / `stop-speech)` blocks (around line 3230-3500 region).

**Add these three blocks (insert after `stop-transcribe)` ;; if it exists, otherwise after `stop-speech)` ;;):**

```bash
  workspace-init)
    WS="${AI_OUTPUT_DIR:-${HOME}/AI_Output}"
    echo "Initializing workspace at: ${WS}"
    mkdir -p "${WS}"/{uploads,generated/transcripts,generated/documents,generated/images,generated/videos,generated/music,generated/speech}
    chmod -R 0775 "${WS}" 2>/dev/null || true
    echo "✅ Workspace structure created"
    ls -la "${WS}/" "${WS}/generated/"
    ;;

  workspace-status)
    WS="${AI_OUTPUT_DIR:-${HOME}/AI_Output}"
    if [ ! -d "${WS}" ]; then
      echo "❌ Workspace not initialized. Run: ./launch.sh workspace-init"
      exit 1
    fi
    echo "Workspace: ${WS}"
    echo ""
    printf "%-30s %10s %10s\n" "Path" "Files" "Size"
    printf "%-30s %10s %10s\n" "----" "-----" "----"
    for d in uploads generated/transcripts generated/documents generated/images generated/videos generated/music generated/speech; do
      if [ -d "${WS}/${d}" ]; then
        n=$(find "${WS}/${d}" -type f 2>/dev/null | wc -l | tr -d ' ')
        s=$(du -sh "${WS}/${d}" 2>/dev/null | awk '{print $1}')
        printf "%-30s %10s %10s\n" "${d}" "${n}" "${s}"
      fi
    done
    echo ""
    TOTAL=$(du -sh "${WS}" 2>/dev/null | awk '{print $1}')
    echo "Total: ${TOTAL}"
    ;;

  workspace-show)
    WS="${AI_OUTPUT_DIR:-${HOME}/AI_Output}"
    echo "Workspace root (host):     ${WS}"
    echo "Workspace root (container): /workspace"
    echo "OWUI uploads (host):       ${WS}/uploads/"
    echo "OWUI uploads (container):  /app/backend/data/uploads/"
    echo ""
    echo "Generated subdirs:"
    for cat in transcripts documents images videos music speech; do
      echo "  ${cat}: ${WS}/generated/${cat}/"
    done
    ;;
```

**Update the help text and usage line** (around line 3712 / 3727):

Find:
```
    echo "Usage: ./launch.sh [up|down|...|stop-speech|...]"
```

Add `|workspace-init|workspace-status|workspace-show` to the usage line.

After existing speech help lines, add:
```
    echo ""
    echo "  workspace-init        Create shared workspace directory structure (uploads, generated/*)"
    echo "  workspace-status      Show file counts and disk usage per category"
    echo "  workspace-show        Print resolved paths for the current configuration"
```

**Update the `up)` command to call `workspace-init` first** so a fresh deploy has the directory structure ready before OWUI starts (otherwise the bind mount creates an empty subdirectory and OWUI may not have permissions to populate it).

Find the `up)` command block. Near the start of that block (after env loading but before `docker compose up`), add:

```bash
    # TASK-WORKSPACE-001: ensure workspace exists before bind mounts go live
    WS="${AI_OUTPUT_DIR:-${HOME}/AI_Output}"
    if [ ! -d "${WS}/uploads" ] || [ ! -d "${WS}/generated/transcripts" ]; then
      echo "Initializing workspace structure..."
      mkdir -p "${WS}"/{uploads,generated/transcripts,generated/documents,generated/images,generated/videos,generated/music,generated/speech}
      chmod -R 0775 "${WS}" 2>/dev/null || true
    fi
```

**Verification:**
```bash
bash -n launch.sh && echo "✅ launch.sh syntax OK"
./launch.sh workspace-show
# Expected: prints all paths

./launch.sh workspace-init
# Expected: creates structure, prints "✅ Workspace structure created"

./launch.sh workspace-status
# Expected: tabular output of files/size per category
```

---

## Phase 5 — Documentation

### File 6: `docs/HOWTO.md` (MODIFY — protected, append-only via str_replace)

Append a new section. Find a stable anchor — the end of an existing section near operations or the file structure topic.

**Strategy:** locate the section header that comes after where workspace docs should logically live (e.g., a section on "Output Files" or "Backups" or "Reset"), and insert before it. If no obvious anchor exists, insert before the final reference/links section.

**Find** (best-effort anchor — agent should grep for an actual heading):
```
## 9. Backup & Restore
```

(Or whichever section heading is the most stable in the current file. The agent should use `grep -n "^## " docs/HOWTO.md` to find candidate anchors and choose one near operations.)

**Insert this section before the chosen anchor:**

```markdown
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
```

### File 7: `CLAUDE.md` (MODIFY — protected, append-only via str_replace)

Add a new architectural rule (Rule 11) under the "Architectural Ground Rules" section.

**Find this block (around line 194-198):**
```
### 10 — Git Discipline

Commit directly to `main` during stabilization. Run tests before every push: `pytest tests/ -q --tb=no`. Commit format: `type(scope): description`. Never force push. Never commit `.env` or cloud/external deps to `pyproject.toml`.

---
```

**Replace with:**
```
### 10 — Git Discipline

Commit directly to `main` during stabilization. Run tests before every push: `pytest tests/ -q --tb=no`. Commit format: `type(scope): description`. Never force push. Never commit `.env` or cloud/external deps to `pyproject.toml`.

### 11 — Shared Workspace Is The Only Path For User Files

User-uploaded files and cross-MCP artifacts live at `${AI_OUTPUT_DIR}` (default `~/AI_Output/`), mounted into containers at `/workspace`. Never write user-facing artifacts to a container-local volume that other services cannot see.

- Reads of user uploads: `portal_mcp.core.resolve_upload_path(file_id)` or `/workspace/uploads/<id>`.
- Writes of generated artifacts: `portal_mcp.core.get_generated_dir(category)` or `/workspace/generated/<category>/`.
- Categories: `transcripts`, `documents`, `images`, `videos`, `music`, `speech`. Add a new category by editing `_VALID_CATEGORIES` in `portal_mcp/core/workspace.py` (this is the source of truth — `launch.sh workspace-init` and the docker-compose mounts derive from this list).
- New Docker MCPs that touch user files: add `${AI_OUTPUT_DIR:-${HOME}/AI_Output}:/workspace` to the volumes block and `WORKSPACE_DIR=/workspace` to the environment block.
- `AUDIO_STT_ENGINE` is intentionally empty in the OWUI config — auto-transcription is disabled so audio uploads remain accessible to personas. Do not re-enable it without a migration plan for affected workflows.

---
```

### File 8: `KNOWN_LIMITATIONS.md` (MODIFY — append)

Append at the end of the file:

```markdown
## Shared Workspace + Auto-STT Disabled (TASK-WORKSPACE-001)

- **Voice-input via microphone is disabled.** Setting `AUDIO_STT_ENGINE` to empty (the default after this task) prevents auto-transcription of both file uploads AND microphone recordings in Open WebUI. Operators who want voice-input back must either re-enable the global STT (which re-enables auto-transcribe-on-file-upload) or implement a custom OWUI Function that scopes STT to recording-only. The global toggle is currently OWUI's only knob.
- **Existing MCPs not migrated to /workspace.** `mcp-documents`, `mcp-tts`, and `mcp-comfyui` continue to write to `${AI_OUTPUT_DIR}` flat (their existing `OUTPUT_DIR=/app/data/generated` mount is unchanged). New MCPs and the helper module use `/workspace/generated/<category>/`. The two layouts coexist; migration is opportunistic, scheduled for whenever each MCP is next touched for unrelated reasons.
- **OWUI named volume retains historical uploads visibility.** The bind-mount overlay on `/app/backend/data/uploads` hides any pre-existing files in the named volume's `uploads/` subdirectory. Pre-flight migration (Phase 0) handles this for current state; new operators have empty uploads on first launch (correct behavior).
- **Permissions assume single-host deployment.** The 0775 mode on workspace directories assumes the operator's user owns the files and Docker containers run with compatible UIDs. On multi-tenant or hardened hosts, more careful UID mapping is required.
- **No retention policy.** `${AI_OUTPUT_DIR}` grows unbounded. Future task adds `./launch.sh workspace-clean --age=Nd` for time-based pruning.
```

### File 9: `CHANGELOG.md` (MODIFY)

Add an entry at the top under v6.1.0 (or create the v6.1.0 block if it doesn't exist yet).

```markdown
## [6.1.0] — 2026-XX-XX

### Added
- **Shared workspace** (TASK-WORKSPACE-001): unified file-handling foundation.
  - `${AI_OUTPUT_DIR}` (default `~/AI_Output`) is the canonical user-artifact root.
  - OWUI uploads bind-mount to `${AI_OUTPUT_DIR}/uploads` — files dropped in chat are now visible to all MCPs.
  - New helper module `portal_mcp.core.workspace` provides `get_uploads_dir()`, `get_generated_dir(category)`, `resolve_upload_path(file_id)`.
  - New launch commands: `workspace-init`, `workspace-status`, `workspace-show`.
  - `mcp-whisper`, `mcp-music`, `mcp-video`, `mcp-sandbox` now mount `/workspace`.
  - CLAUDE.md Rule 11 added: shared workspace is the only path for user files.

### Changed
- `AUDIO_STT_ENGINE` disabled in OWUI config (set via `OWUI_AUDIO_STT_ENGINE` env, default empty). Audio uploads in chat remain as attachments instead of being auto-transcribed; personas process them via MCP tools. **Side effect:** OWUI microphone voice-input no longer transcribes. See KNOWN_LIMITATIONS.

### Migration notes
- On first `./launch.sh up` after this change, the workspace structure is auto-created. If you have existing OWUI uploads in the named volume, run the migration step in TASK-WORKSPACE-001 §Phase 0 before restarting OWUI, or those files become hidden by the new bind mount.
- `OUTPUT_DIR` env var is now an alias for `AI_OUTPUT_DIR` (same value). Existing MCPs that read `OUTPUT_DIR` continue to work without changes.
```

### File 10: `P5_ROADMAP.md` (MODIFY — add a row to the table)

Append to the roadmap table:

```
| P5-FUT-015 | P2 | Unified shared workspace | DONE | TASK-WORKSPACE-001. Single `${AI_OUTPUT_DIR}` root mounted into OWUI (uploads overlay) and all participating MCPs (`/workspace`). New `portal_mcp.core.workspace` helper module. AUDIO_STT_ENGINE disabled — voice-input loss documented. Foundation for TASK-TRANSCRIBE-001 and future file-handling MCPs. |
```

---

## Phase 6 — Tests

### File 11: `tests/unit/test_workspace.py` (NEW)

```python
"""Unit tests for portal_mcp.core.workspace (TASK-WORKSPACE-001)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from portal_mcp.core.workspace import (
    _VALID_CATEGORIES,
    get_generated_dir,
    get_uploads_dir,
    get_workspace_root,
    resolve_upload_path,
)


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point WORKSPACE_DIR at a temp directory for the duration of a test."""
    monkeypatch.setenv("WORKSPACE_DIR", str(tmp_path))
    monkeypatch.delenv("AI_OUTPUT_DIR", raising=False)
    return tmp_path


def test_get_workspace_root_uses_workspace_dir(workspace: Path) -> None:
    assert get_workspace_root() == workspace


def test_get_workspace_root_falls_back_to_ai_output_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("WORKSPACE_DIR", raising=False)
    monkeypatch.setenv("AI_OUTPUT_DIR", str(tmp_path))
    assert get_workspace_root() == tmp_path


def test_get_uploads_dir_creates_directory(workspace: Path) -> None:
    uploads = get_uploads_dir()
    assert uploads == workspace / "uploads"
    assert uploads.is_dir()


def test_get_generated_dir_validates_category(workspace: Path) -> None:
    with pytest.raises(ValueError, match="Unknown category"):
        get_generated_dir("nonsense")


def test_get_generated_dir_creates_each_category(workspace: Path) -> None:
    for cat in _VALID_CATEGORIES:
        d = get_generated_dir(cat)
        assert d == workspace / "generated" / cat
        assert d.is_dir()


def test_resolve_upload_path_direct_match(workspace: Path) -> None:
    uploads = get_uploads_dir()
    target = uploads / "abc123.mp3"
    target.write_text("audio")
    resolved = resolve_upload_path("abc123.mp3")
    assert resolved is not None
    assert resolved == target.resolve()


def test_resolve_upload_path_prefix_match(workspace: Path) -> None:
    uploads = get_uploads_dir()
    target = uploads / "deadbeef-1234.wav"
    target.write_text("audio")
    resolved = resolve_upload_path("deadbeef-1234")
    assert resolved is not None
    assert resolved.name == "deadbeef-1234.wav"


def test_resolve_upload_path_returns_none_for_missing(workspace: Path) -> None:
    get_uploads_dir()  # ensure dir exists
    assert resolve_upload_path("nonexistent") is None


def test_resolve_upload_path_picks_most_recent_on_ambiguity(
    workspace: Path,
) -> None:
    uploads = get_uploads_dir()
    older = uploads / "id_a.txt"
    newer = uploads / "id_b.txt"
    older.write_text("old")
    older_mtime = older.stat().st_mtime
    newer.write_text("new")
    os.utime(newer, (older_mtime + 100, older_mtime + 100))
    # "id_" matches both — should prefer newer
    resolved = resolve_upload_path("id_")
    assert resolved is not None
    assert resolved.name == "id_b.txt"
```

**Verification:**
```bash
pytest tests/unit/test_workspace.py -v
# Expected: 9 passed
```

### File 12: `tests/portal5_acceptance_v6.py` (MODIFY — add S40 workspace tests)

Locate the S40 section (negative tests). Add a workspace section as S40 sub-tests, OR add a new section S41 for workspace verification.

**Find the existing S40 section header (negative tests).** Add **before** it (or in a sensible logical position near system-level tests):

```python
async def S15() -> None:
    """S15: Shared workspace verification (TASK-WORKSPACE-001)."""
    print("\n━━━ S15. SHARED WORKSPACE ━━━")
    sec = "S15"

    workspace_root = Path(os.environ.get("AI_OUTPUT_DIR", str(Path.home() / "AI_Output")))

    # S15-01: Workspace root exists
    t0 = time.time()
    record(
        sec,
        "S15-01",
        "Workspace root exists",
        "PASS" if workspace_root.is_dir() else "FAIL",
        str(workspace_root),
        t0=t0,
    )

    # S15-02: All canonical subdirectories exist
    t0 = time.time()
    expected = [
        "uploads",
        "generated/transcripts",
        "generated/documents",
        "generated/images",
        "generated/videos",
        "generated/music",
        "generated/speech",
    ]
    missing = [d for d in expected if not (workspace_root / d).is_dir()]
    record(
        sec,
        "S15-02",
        "Workspace subdirectories",
        "PASS" if not missing else "FAIL",
        "all present" if not missing else f"missing: {missing}",
        t0=t0,
    )

    # S15-03: OWUI bind mount visible (write from host, read from OWUI container)
    t0 = time.time()
    probe = workspace_root / "uploads" / ".workspace_probe"
    probe.write_text("portal-5 workspace probe")
    try:
        # Read from inside OWUI container
        proc = await asyncio.create_subprocess_exec(
            "docker", "compose", "-f", "deploy/portal-5/docker-compose.yml",
            "exec", "-T", "open-webui",
            "cat", "/app/backend/data/uploads/.workspace_probe",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        if b"portal-5 workspace probe" in stdout:
            record(sec, "S15-03", "OWUI uploads bind mount", "PASS", "host↔OWUI bidirectional", t0=t0)
        else:
            record(sec, "S15-03", "OWUI uploads bind mount", "FAIL", "probe not visible from OWUI", t0=t0)
    except Exception as e:
        record(sec, "S15-03", "OWUI uploads bind mount", "FAIL", str(e)[:100], t0=t0)
    finally:
        with contextlib.suppress(Exception):
            probe.unlink()

    # S15-04: Helper module imports cleanly
    t0 = time.time()
    try:
        from portal_mcp.core.workspace import get_workspace_root, get_generated_dir
        root = get_workspace_root()
        get_generated_dir("transcripts")
        record(sec, "S15-04", "workspace helper imports", "PASS", str(root), t0=t0)
    except Exception as e:
        record(sec, "S15-04", "workspace helper imports", "FAIL", str(e)[:100], t0=t0)

    # S15-05: AUDIO_STT_ENGINE is disabled in OWUI config
    t0 = time.time()
    try:
        proc = await asyncio.create_subprocess_exec(
            "docker", "compose", "-f", "deploy/portal-5/docker-compose.yml",
            "exec", "-T", "open-webui",
            "sh", "-c", "echo \"${AUDIO_STT_ENGINE}\"",
            stdout=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        value = stdout.decode().strip()
        if not value:
            record(sec, "S15-05", "AUDIO_STT_ENGINE disabled", "PASS", "empty (correct)", t0=t0)
        else:
            record(sec, "S15-05", "AUDIO_STT_ENGINE disabled", "WARN",
                   f"unexpected value: {value!r}", t0=t0)
    except Exception as e:
        record(sec, "S15-05", "AUDIO_STT_ENGINE disabled", "FAIL", str(e)[:100], t0=t0)
```

**Register the new section** — find the `ALL_SECTIONS` dict and add:
```python
    "S15": S15,
```

Place it logically — after Phase 1 (no-model tests) since workspace tests don't need a model loaded.

**Verification:**
```bash
python3 tests/portal5_acceptance_v6.py --section S15
# Expected: 5 PASS, 0 FAIL
```

---

## Phase 7 — Final Verification

```bash
# 1. Lint + format
ruff check . && echo "✅ ruff check passed"
ruff format --check . && echo "✅ ruff format passed"

# 2. Type check (no new errors)
mypy portal_pipeline/ portal_mcp/ 2>&1 | tail -10

# 3. Unit tests
pytest tests/unit/ -v --tb=short
# Expected: 100% pass, including new test_workspace.py

# 4. Workspace consistency (CLAUDE.md Rule 6) — unchanged by this task
python3 -c "
import yaml
from portal_pipeline.router.workspaces import WORKSPACES
cfg = yaml.safe_load(open('config/backends.yaml'))
pipe_ids = set(WORKSPACES.keys())
yaml_ids = set(cfg['workspace_routing'].keys())
assert pipe_ids == yaml_ids, f'Mismatch: pipe={pipe_ids-yaml_ids} yaml={yaml_ids-pipe_ids}'
print('✅ Workspace IDs consistent')
"

# 5. Compose syntax
docker compose -f deploy/portal-5/docker-compose.yml config > /dev/null && \
  echo "✅ compose syntax OK"

# 6. Bring services up
./launch.sh down  # clean stop
./launch.sh up
sleep 30  # let services settle

# 7. Workspace bind mount verified end-to-end
echo "portal-5 e2e test $(date)" > "${AI_OUTPUT_DIR:-${HOME}/AI_Output}/uploads/.e2e_probe"
docker compose -f deploy/portal-5/docker-compose.yml exec -T open-webui \
  cat /app/backend/data/uploads/.e2e_probe
# Expected: prints "portal-5 e2e test <date>"
rm -f "${AI_OUTPUT_DIR:-${HOME}/AI_Output}/uploads/.e2e_probe"

# 8. Acceptance test S15
python3 tests/portal5_acceptance_v6.py --section S15
# Expected: all S15-* PASS

# 9. Confirm AUDIO_STT_ENGINE disabled
docker compose -f deploy/portal-5/docker-compose.yml exec -T open-webui \
  sh -c 'echo "STT=[${AUDIO_STT_ENGINE}]"'
# Expected: "STT=[]" (empty)

# 10. Smoke: drop a file via OWUI upload API, verify visible to host
# (manual step — drop any file in OWUI chat; should appear in ~/AI_Output/uploads/)
```

---

## Rollback Procedure

```bash
# Revert via git
git checkout main
git branch -D feat/shared-workspace

# If already merged: revert the merge commit
git log --oneline | grep -iE "workspace|TASK-WORKSPACE-001" | head -1
git revert <commit-sha> --no-edit
git push

# Restart services with reverted compose
./launch.sh down
./launch.sh up

# OWUI uploads safety: files in ~/AI_Output/uploads/ stay on disk regardless
# of revert. To restore the pre-task state where OWUI used its named volume
# exclusively, copy them back into the volume:
mkdir -p /tmp/owui-restore
cp -r "${AI_OUTPUT_DIR:-${HOME}/AI_Output}/uploads/." /tmp/owui-restore/
docker compose -f deploy/portal-5/docker-compose.yml exec -T open-webui \
  bash -c "rm -rf /app/backend/data/uploads/* && exit"
docker compose -f deploy/portal-5/docker-compose.yml cp \
  /tmp/owui-restore/. open-webui:/app/backend/data/uploads/

# Re-enable AUDIO_STT_ENGINE in .env if voice-input was needed:
echo "OWUI_AUDIO_STT_ENGINE=openai" >> .env
./launch.sh restart open-webui
```

---

## Commit Message

```
feat(workspace): unified shared workspace foundation

Establishes ${AI_OUTPUT_DIR} (default ~/AI_Output) as the canonical
user-artifact root accessible across OWUI, host-native services, and
Docker MCPs. Eliminates cross-namespace file-bridging friction.

- OWUI uploads bind-mount overlay: files dropped in chat are now
  visible at the same physical path inside MCP containers.
- New helper module portal_mcp.core.workspace with
  get_uploads_dir, get_generated_dir(category), resolve_upload_path.
- Workspace mount added to mcp-whisper, mcp-music, mcp-video,
  mcp-sandbox (read-only). Existing MCPs (documents, tts, comfyui)
  keep their current paths until next opportunistic migration.
- New launch.sh commands: workspace-init / workspace-status /
  workspace-show. Auto-init runs as part of `./launch.sh up`.
- AUDIO_STT_ENGINE disabled (set via OWUI_AUDIO_STT_ENGINE env,
  default empty). Audio uploads stay as attachments; personas handle
  them via MCP tools. Side effect: voice-input via mic disabled.
  Documented in KNOWN_LIMITATIONS.
- CLAUDE.md Rule 11: shared workspace is the only path for user files.
- New unit tests (test_workspace.py, 9 tests) and acceptance section
  S15 (5 tests).

Foundation for TASK-TRANSCRIBE-001 (revised) and future file-handling
MCPs that need cross-service file access.

Refs: TASK-WORKSPACE-001
```

---

## Operator Checklist (Post-Merge)

- [ ] Pull merge commit
- [ ] If you have existing OWUI uploads (likely on a system that's been in use): the named-volume → bind-mount migration in Phase 0 already preserved them. Verify by spot-checking `~/AI_Output/uploads/`.
- [ ] Confirm voice-input via OWUI microphone is acceptable to lose (or note it for users).
- [ ] Run `./launch.sh down && ./launch.sh up`. First start auto-creates the workspace structure.
- [ ] Run `./launch.sh workspace-status` — sanity check.
- [ ] Drop a small file in OWUI chat. It should appear in `~/AI_Output/uploads/` on the host.
- [ ] Run `python3 tests/portal5_acceptance_v6.py --section S15` — expect all PASS.
- [ ] Greenlight TASK-TRANSCRIBE-001 (revised) for execution. The transcription rebuild will use `resolve_upload_path` to read OWUI-dropped audio files.

---

**End of TASK-WORKSPACE-001.**
