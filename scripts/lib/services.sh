#!/usr/bin/env bash
# services.sh — Portal 5 service commands (sourced by launch.sh)
# shellcheck shell=bash

_launch_install_ollama() {
    echo "=== Installing Ollama natively (Apple Silicon / Metal GPU) ==="
    ARCH=$(uname -m)

    if [ "$ARCH" != "arm64" ]; then
        echo "  ℹ️  Non-Apple-Silicon detected ($ARCH)."
        echo "  For Linux: curl -fsSL https://ollama.com/install.sh | sh"
        echo "  Then run:  ./launch.sh up --profile docker-ollama"
        exit 0
    fi

    if ! command -v brew &>/dev/null; then
        echo "  ❌ Homebrew not found. Install it first:"
        echo '     /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"'
        echo "  Then re-run: ./launch.sh install-ollama"
        exit 1
    fi

    if command -v ollama &>/dev/null; then
        echo "  ✅ Ollama already installed: $(ollama --version 2>/dev/null | head -1 || echo 'installed')"
    else
        echo "  Installing Ollama via brew..."
        brew install ollama
        echo "  ✅ Ollama installed"
    fi

    echo "  Starting Ollama service (auto-starts on login)..."
    brew services start ollama
    sleep 3

    if curl -s http://localhost:11434/api/tags &>/dev/null; then
        echo "  ✅ Ollama is running at http://localhost:11434"
        echo "  ✅ Will auto-start on login via brew services"
    else
        echo "  ⚠️  Ollama installed but not yet responding — wait a moment then check:"
        echo "     curl http://localhost:11434/api/tags"
    fi

    echo ""
    echo "Next steps:"
    echo "  ./launch.sh up           — start Portal 5 stack"
    echo "  ./launch.sh pull-models  — pull AI models (30-90 min)"
}

_launch_install_comfyui() {
    echo "=== Installing ComfyUI natively (Apple Silicon / Metal GPU) ==="
    ARCH=$(uname -m)
    COMFYUI_DIR="${COMFYUI_DIR:-$HOME/ComfyUI}"

    if [ "$ARCH" != "arm64" ]; then
        echo "  ℹ️  Non-Apple-Silicon detected ($ARCH)."
        echo "  For Linux with NVIDIA: use Docker ComfyUI via --profile docker-comfyui"
        echo "  Or install manually: https://github.com/comfyanonymous/ComfyUI"
        exit 0
    fi

    # ── Install Python dependency manager ────────────────────────────────────
    if ! command -v python3 &>/dev/null; then
        echo "  ❌ python3 not found. Install via brew: brew install python"
        exit 1
    fi

    # ── Clone ComfyUI ─────────────────────────────────────────────────────────
    if [ -d "$COMFYUI_DIR" ]; then
        echo "  ✅ ComfyUI already cloned at $COMFYUI_DIR"
        echo "  Updating..."
        git -C "$COMFYUI_DIR" pull --quiet
    else
        echo "  Cloning ComfyUI to $COMFYUI_DIR..."
        git clone https://github.com/comfyanonymous/ComfyUI "$COMFYUI_DIR"
        echo "  ✅ ComfyUI cloned"
    fi

    # ── Install Python dependencies ───────────────────────────────────────────
    echo "  Installing Python dependencies (this may take a few minutes)..."
    cd "$COMFYUI_DIR"

    # Use a venv to avoid system Python conflicts
    if [ ! -d "$COMFYUI_DIR/.venv" ]; then
        python3 -m venv "$COMFYUI_DIR/.venv"
    fi

    "$COMFYUI_DIR/.venv/bin/pip" install --quiet --upgrade pip
    "$COMFYUI_DIR/.venv/bin/pip" install --quiet -r requirements.txt
    # PyTorch for Apple Silicon (MPS)
    "$COMFYUI_DIR/.venv/bin/pip" install --quiet \
        torch torchvision torchaudio
    echo "  ✅ Dependencies installed"

    # ── Create model directories ──────────────────────────────────────────────
    mkdir -p "$COMFYUI_DIR/models/checkpoints"
    mkdir -p "$COMFYUI_DIR/models/video"
    mkdir -p "$COMFYUI_DIR/output"
    echo "  ✅ Model directories created"

    # ── Create a launch script for ComfyUI ───────────────────────────────────
    cat > "$COMFYUI_DIR/start.sh" << 'COMFY_START'
#!/bin/bash
# Start ComfyUI with Metal (MPS) acceleration for Apple Silicon
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"
.venv/bin/python main.py \
    --listen 0.0.0.0 \
    --port 8188 \
    --force-fp16
COMFY_START
    chmod +x "$COMFYUI_DIR/start.sh"

    # ── Register as a launchd service (auto-start on login) ──────────────────
    PLIST_PATH="$HOME/Library/LaunchAgents/com.portal5.comfyui.plist"
    cat > "$PLIST_PATH" << PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.portal5.comfyui</string>
    <key>ProgramArguments</key>
    <array>
        <string>$COMFYUI_DIR/.venv/bin/python</string>
        <string>$COMFYUI_DIR/main.py</string>
        <string>--listen</string>
        <string>0.0.0.0</string>
        <string>--port</string>
        <string>8188</string>
        <string>--force-fp16</string>
    </array>
    <key>WorkingDirectory</key>
    <string>$COMFYUI_DIR</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>$HOME/.portal5/logs/comfyui.log</string>
    <key>StandardErrorPath</key>
    <string>$HOME/.portal5/logs/comfyui-error.log</string>
</dict>
</plist>
PLIST

    mkdir -p "$HOME/.portal5/logs"

    # ── Install ComfyUI-VideoHelperSuite (required for VHS_VideoCombine video output) ──
    echo "  Installing ComfyUI-VideoHelperSuite (video output node)..."
    VHS_DIR="$COMFYUI_DIR/custom_nodes/ComfyUI-VideoHelperSuite"
    if [ -d "$VHS_DIR" ]; then
        echo "  ✅ ComfyUI-VideoHelperSuite already installed — updating"
        git -C "$VHS_DIR" pull --quiet
    else
        git clone https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite.git "$VHS_DIR"
        echo "  ✅ ComfyUI-VideoHelperSuite installed"
    fi
    if [ -f "$VHS_DIR/requirements.txt" ]; then
        "$COMFYUI_DIR/.venv/bin/pip" install --quiet -r "$VHS_DIR/requirements.txt"
    fi

    # Load the service
    launchctl load "$PLIST_PATH" 2>/dev/null || true
    launchctl start com.portal5.comfyui 2>/dev/null || true
    sleep 5

    if curl -s http://localhost:8188/system_stats &>/dev/null; then
        echo "  ✅ ComfyUI is running at http://localhost:8188"
        echo "  ✅ Auto-starts on login via launchd"
    else
        echo "  ⚠️  ComfyUI installed but not yet responding."
        echo "  Logs: $HOME/.portal5/logs/comfyui.log"
        echo "  Or start manually: $COMFYUI_DIR/start.sh"
    fi

    echo ""
    echo "Next steps:"
    echo "  ./launch.sh download-comfyui-models   — download image/video models"
    echo "  ./launch.sh up                        — start Portal 5 stack"
}

_launch_install_music() {
    # Source .env so HF_HOME, AI_OUTPUT_DIR, and MUSIC_HOST_PORT propagate into
    # the generated com.portal5.music-mcp.plist EnvironmentVariables block.
    # Without this, a fresh shell running `./launch.sh install-music` defaults
    # HF_HOME to ~/.portal5/music/hf_cache — separate from MLX's HF cache,
    # fragmenting model storage.
    set -a; source "$ENV_FILE" 2>/dev/null || true; set +a

    echo "=== Installing Music MCP natively (Apple Silicon / MPS) ==="
    ARCH=$(uname -m)
    MUSIC_DIR="$HOME/.portal5/music"
    MUSIC_VENV="$MUSIC_DIR/.venv"
    MUSIC_LOG="$HOME/.portal5/logs/music-mcp.log"
    MUSIC_PORT="${MUSIC_HOST_PORT:-8912}"

    if [ "$ARCH" != "arm64" ]; then
        echo "  ℹ️  Non-Apple-Silicon detected ($ARCH)."
        echo "  Music MCP is designed for native macOS/MPS. On x86_64+CUDA, it can"
        echo "  still run natively but Docker is also an option."
        echo "  Continuing anyway..."
    fi

    if ! command -v python3 &>/dev/null; then
        echo "  ❌ python3 not found. Install via brew: brew install python"
        exit 1
    fi

    # ── Create venv ───────────────────────────────────────────────────────────
    mkdir -p "$MUSIC_DIR"
    mkdir -p "$HOME/.portal5/logs"
    if [ ! -d "$MUSIC_VENV" ]; then
        echo "  Creating Python venv at $MUSIC_VENV..."
        python3 -m venv "$MUSIC_VENV"
    else
        echo "  ✅ Venv already exists at $MUSIC_VENV"
    fi

    # ── Install dependencies ──────────────────────────────────────────────────
    echo "  Installing dependencies (torch, transformers, mcp — this may take a few minutes)..."
    "$MUSIC_VENV/bin/pip" install --quiet --upgrade pip
    "$MUSIC_VENV/bin/pip" install --quiet \
        "torch>=2.1.0" \
        "torchaudio>=2.1.0" \
        "transformers>=4.40.0" \
        "scipy>=1.11.0" \
        "fastapi>=0.109.0" \
        "uvicorn[standard]>=0.27.0" \
        "httpx>=0.26.0" \
        "pyyaml>=6.0.1" \
        "starlette>=0.35.0" \
        "mcp>=1.0.0" \
        "fastmcp>=0.4.0"
    echo "  ✅ Dependencies installed"

    # ── HuggingFace cache dir ─────────────────────────────────────────────────
    HF_CACHE="${HF_HOME:-$MUSIC_DIR/hf_cache}"
    mkdir -p "$HF_CACHE"
    echo "  HuggingFace cache: $HF_CACHE"
    echo "  (MusicGen models download here on first generate_music call)"

    # ── Create start script ───────────────────────────────────────────────────
    cat > "$MUSIC_DIR/start.sh" << MUSIC_START
#!/bin/bash
# Start Music MCP natively for MPS acceleration on Apple Silicon.
# PORTAL_ROOT is baked at install-music time — re-run install-music
# if the portal-5 repo moves.
PORTAL_ROOT="${PORTAL_ROOT}"
if [ ! -d "\$PORTAL_ROOT/portal_mcp" ]; then
    echo "ERROR: PORTAL_ROOT=\$PORTAL_ROOT no longer contains portal_mcp/" >&2
    echo "Re-run: ./launch.sh install-music" >&2
    exit 1
fi
export PYTHONPATH="\$PORTAL_ROOT"
export HF_HOME="${HF_CACHE}"
export TRANSFORMERS_CACHE="${HF_CACHE}"
export OUTPUT_DIR="\${AI_OUTPUT_DIR:-\$HOME/AI_Output}"
export MUSIC_MCP_PORT="${MUSIC_PORT}"
mkdir -p "\$OUTPUT_DIR"
exec "$MUSIC_VENV/bin/python" -m portal_mcp.generation.music_mcp
MUSIC_START
    chmod +x "$MUSIC_DIR/start.sh"
    echo "  ✅ Start script: $MUSIC_DIR/start.sh"

    # ── Register launchd plist (auto-start on login) ──────────────────────────
    PLIST_PATH="$HOME/Library/LaunchAgents/com.portal5.music-mcp.plist"
    cat > "$PLIST_PATH" << PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.portal5.music-mcp</string>
    <key>ProgramArguments</key>
    <array>
        <string>$MUSIC_DIR/start.sh</string>
    </array>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PYTHONPATH</key>
        <string>$PORTAL_ROOT</string>
        <key>HF_HOME</key>
        <string>$HF_CACHE</string>
        <key>TRANSFORMERS_CACHE</key>
        <string>$HF_CACHE</string>
        <key>OUTPUT_DIR</key>
        <string>${AI_OUTPUT_DIR:-$HOME/AI_Output}</string>
        <key>MUSIC_MCP_PORT</key>
        <string>$MUSIC_PORT</string>
    </dict>
    <key>WorkingDirectory</key>
    <string>$PORTAL_ROOT</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>$MUSIC_LOG</string>
    <key>StandardErrorPath</key>
    <string>$MUSIC_LOG</string>
</dict>
</plist>
PLIST
    launchctl load "$PLIST_PATH" 2>/dev/null || true
    echo "  ✅ Registered as launchd service: com.portal5.music-mcp"

    echo ""
    echo "=== Music MCP installed ==="
    echo "  Port:    :$MUSIC_PORT"
    echo "  Venv:    $MUSIC_VENV"
    echo "  Cache:   $HF_CACHE"
    echo "  Log:     $MUSIC_LOG"
    echo "  Start:   ./launch.sh up  (auto-started)"
    echo "  Models download on first call (~300MB small, ~1.5GB medium)"
    echo ""
    echo "Next steps:"
    echo "  ./launch.sh up   — start Portal 5 (Music MCP starts automatically)"
}

_launch_start_speech() {
    set -a; source "$ENV_FILE" 2>/dev/null || true; set +a

    if [ "$(uname -m)" != "arm64" ]; then
        echo "  ℹ️  MLX Speech requires Apple Silicon. Docker TTS/ASR services are available as fallback."
        exit 0
    fi

    if ! python3 -c "import mlx_audio" &>/dev/null 2>&1; then
        echo "  ❌ mlx-audio not installed. Run: pip3 install mlx-audio"
        exit 1
    fi

    PID_FILE="/tmp/portal-mlx-speech.pid"
    LOG_FILE="$HOME/.portal5/logs/mlx-speech.log"
    mkdir -p "$(dirname "$LOG_FILE")"

    if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
        echo "  ℹ️  MLX Speech already running (PID $(cat "$PID_FILE"))"
        exit 0
    fi

    echo "Starting MLX Speech Server (Qwen3-TTS + Qwen3-ASR + Kokoro)..."
    nohup python3 "$PORTAL_ROOT/scripts/mlx-speech.py" >> "$LOG_FILE" 2>&1 &
    echo $! > "$PID_FILE"
    echo "  ✅ MLX Speech started (PID $!, port ${MLX_SPEECH_PORT:-8918})"
    echo "  📋 Log: $LOG_FILE"
    echo "  💡 Models load lazily on first TTS/ASR request."
}

_launch_stop_speech() {
    PID_FILE="/tmp/portal-mlx-speech.pid"
    if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
        kill "$(cat "$PID_FILE")"
        rm -f "$PID_FILE"
        echo "  ✅ MLX Speech stopped"
    else
        echo "  ℹ️  MLX Speech not running"
    fi
}

_launch_start_embedding_cpu_arm() {
    # Start the native ARM64 embedding server (Python/sentence-transformers + MPS).
    # Replaces the TEI Docker service on Apple Silicon where the x86-only TEI image
    # has no ARM64 manifest. Binds to port 8917 — same as the Docker service.

    # Source .env so EMBEDDING_MODEL, EMBEDDING_HOST_PORT, and ENABLE_REMOTE_ACCESS
    # overrides are respected when this command is run standalone (not via `up`).
    if [ -f "$ENV_FILE" ]; then set -a; source "$ENV_FILE"; set +a; fi

    ARCH=$(uname -m)
    if [ "$ARCH" != "arm64" ]; then
        echo "  ℹ️  This command is for Apple Silicon (arm64). On x86, the Docker TEI service works directly."
        echo "  Run: ./launch.sh up  (embedding starts automatically)"
        exit 0
    fi

    PID_FILE="/tmp/portal-embedding-arm.pid"
    if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
        echo "  ✅ ARM64 embedding server already running (PID $(cat "$PID_FILE"))"
        echo "  Test: curl http://localhost:8917/health"
        exit 0
    fi

    # Use a dedicated venv (avoids conflicts with project venv and PEP 668 Homebrew Python)
    EM_VENV="${HOME}/.portal5/embedding-venv"
    EM_PY="${EM_VENV}/bin/python3"
    if [ ! -x "$EM_PY" ]; then
        echo "  Creating embedding venv at $EM_VENV..."
        python3 -m venv "$EM_VENV" --without-pip 2>/dev/null || python3 -m venv "$EM_VENV"
        "$EM_PY" -m ensurepip --upgrade &>/dev/null || true
    fi
    if ! "$EM_PY" -c "import sentence_transformers, fastapi, uvicorn" &>/dev/null 2>&1; then
        echo "  Installing deps into embedding venv..."
        "$EM_PY" -m pip install --quiet sentence-transformers fastapi uvicorn || {
            echo "  ❌ Failed to install deps into $EM_VENV"
            exit 1
        }
    fi

    # Stop the TEI Docker container if running (port conflict)
    docker stop portal5-embedding 2>/dev/null && echo "  Stopped Docker TEI container (port conflict)" || true

    MODEL="${EMBEDDING_MODEL:-microsoft/harrier-oss-v1-0.6b}"
    PORT="${EMBEDDING_HOST_PORT:-8917}"
    LOG_FILE="${HOME}/.portal5/logs/embedding-server.log"
    mkdir -p "$(dirname "$LOG_FILE")"

    echo "[portal-5] Starting ARM64 native embedding server..."
    echo "  Model: $MODEL"
    echo "  Port:  $PORT"
    echo "  Log:   $LOG_FILE"

    nohup "$EM_PY" "$PORTAL_ROOT/scripts/embedding-server.py" \
        --model "$MODEL" \
        --port "$PORT" \
        --host 0.0.0.0 \
        >"$LOG_FILE" 2>&1 &
    echo $! > "$PID_FILE"
    echo "[portal-5] ARM64 embedding server started (PID $!)"
    echo "  Health (ready in ~30s): curl http://localhost:8917/health"
}

_launch_stop_embedding_cpu_arm() {
    PID_FILE="/tmp/portal-embedding-arm.pid"
    if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
        kill "$(cat "$PID_FILE")"
        rm -f "$PID_FILE"
        echo "  ✅ ARM64 embedding server stopped"
    else
        echo "  ℹ️  ARM64 embedding server not running"
    fi
}

_launch_install_embedding_service() {
    # Install a macOS launchd agent so the ARM64 embedding server starts at login
    # and auto-restarts on crash — no dependency on launch.sh being run first.
    if [ "$(uname)" != "Darwin" ]; then
        echo "  ❌ launchd services are macOS-only"
        exit 1
    fi
    if [ "$(uname -m)" != "arm64" ]; then
        echo "  ℹ️  ARM64 embedding server is for Apple Silicon only."
        echo "  On x86, the portal5-embedding Docker service (TEI) handles embeddings."
        exit 0
    fi

    PLIST_DIR="${HOME}/Library/LaunchAgents"
    PLIST_FILE="${PLIST_DIR}/com.portal5.embedding.plist"
    LOG_DIR="${HOME}/.portal5/logs"
    WRAPPER="${PORTAL_ROOT}/scripts/embedding-launchd-wrapper.sh"

    mkdir -p "$PLIST_DIR" "$LOG_DIR"
    chmod +x "$WRAPPER"

    # Ensure venv + deps are installed before registering the service
    _EM_VENV="${HOME}/.portal5/embedding-venv"
    _EM_PY="${_EM_VENV}/bin/python3"
    if [ ! -x "$_EM_PY" ]; then
        echo "[portal-5] Creating embedding venv at $_EM_VENV..."
        python3 -m venv "$_EM_VENV" --without-pip 2>/dev/null || python3 -m venv "$_EM_VENV"
        "$_EM_PY" -m ensurepip --upgrade &>/dev/null || true
    fi
    if ! "$_EM_PY" -c "import sentence_transformers, fastapi, uvicorn" &>/dev/null 2>&1; then
        echo "[portal-5] Installing embedding server deps..."
        "$_EM_PY" -m pip install --quiet sentence-transformers fastapi uvicorn || {
            echo "  ❌ Failed to install deps — aborting"
            exit 1
        }
    fi

    # Stop any existing nohup instance so there's no port conflict
    _PID_FILE="/tmp/portal-embedding-arm.pid"
    if [ -f "$_PID_FILE" ] && kill -0 "$(cat "$_PID_FILE")" 2>/dev/null; then
        kill "$(cat "$_PID_FILE")" 2>/dev/null || true
        rm -f "$_PID_FILE"
        echo "[portal-5] Stopped existing nohup embedding instance"
    fi

    # Write the plist (paths must be absolute — launchd does not expand ~)
    cat > "$PLIST_FILE" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.portal5.embedding</string>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>${WRAPPER}</string>
    </array>
    <key>KeepAlive</key>
    <true/>
    <key>RunAtLoad</key>
    <true/>
    <key>ThrottleInterval</key>
    <integer>30</integer>
    <key>StandardOutPath</key>
    <string>${LOG_DIR}/embedding-server.log</string>
    <key>StandardErrorPath</key>
    <string>${LOG_DIR}/embedding-server-err.log</string>
    <key>WorkingDirectory</key>
    <string>${PORTAL_ROOT}</string>
</dict>
</plist>
PLIST

    # Unload any existing registration, then register the updated plist
    launchctl bootout "gui/$(id -u)/com.portal5.embedding" 2>/dev/null || true
    launchctl bootstrap "gui/$(id -u)" "$PLIST_FILE"

    echo "[portal-5] ✅ Embedding service installed and started"
    echo "  Plist:    $PLIST_FILE"
    echo "  Log:      ${LOG_DIR}/embedding-server.log"
    echo "  Status:   launchctl list com.portal5.embedding"
    echo "  Uninstall: ./launch.sh uninstall-embedding-service"
}

_launch_uninstall_embedding_service() {
    PLIST_FILE="${HOME}/Library/LaunchAgents/com.portal5.embedding.plist"
    if launchctl list com.portal5.embedding 2>/dev/null | grep -q '"PID"'; then
        launchctl bootout "gui/$(id -u)/com.portal5.embedding" 2>/dev/null || true
        echo "[portal-5] ✅ Embedding service stopped and unregistered"
    else
        launchctl bootout "gui/$(id -u)/com.portal5.embedding" 2>/dev/null || true
    fi
    if [ -f "$PLIST_FILE" ]; then
        rm -f "$PLIST_FILE"
        echo "[portal-5] Plist removed: $PLIST_FILE"
    else
        echo "[portal-5] ℹ️  No plist found at $PLIST_FILE"
    fi
}

_launch_install_powermetrics() {
    # Install powermetrics reader daemon (requires sudo — powermetrics needs root)
    if [ "$(uname)" != "Darwin" ]; then
        echo "  ❌ powermetrics is macOS-only"
        exit 1
    fi
    if [ "$(uname -m)" != "arm64" ]; then
        echo "  ℹ️  powermetrics telemetry is for Apple Silicon only."
        exit 0
    fi

    SCRIPT_SRC="${PORTAL_ROOT}/scripts/portal5-powermetrics.py"
    PLIST_SRC="${PORTAL_ROOT}/deploy/launchd/com.portal5.powermetrics.plist"
    SCRIPT_DST="/usr/local/bin/portal5-powermetrics"
    PLIST_DST="/Library/LaunchDaemons/com.portal5.powermetrics.plist"

    if [ ! -f "$SCRIPT_SRC" ]; then
        echo "  ❌ Missing: $SCRIPT_SRC"
        exit 1
    fi

    echo "[portal-5] Installing powermetrics daemon (requires sudo)..."
    sudo cp "$SCRIPT_SRC" "$SCRIPT_DST" && sudo chmod +x "$SCRIPT_DST" || {
        echo "  ❌ Failed to copy daemon script"
        exit 1
    }
    sudo cp "$PLIST_SRC" "$PLIST_DST" || {
        echo "  ❌ Failed to copy plist"
        exit 1
    }
    sudo launchctl load -w "$PLIST_DST" 2>/dev/null || sudo launchctl kickstart -k "system/com.portal5.powermetrics" 2>/dev/null || true

    sleep 3
    if [ -S "/tmp/portal5-powermetrics.sock" ]; then
        echo "[portal-5] ✅ Powermetrics daemon installed and running"
    else
        echo "[portal-5] ⏳ Powermetrics daemon installed, starting (may need 15s for first powermetrics sample)..."
    fi
    echo "  Script: $SCRIPT_DST"
    echo "  Plist:  $PLIST_DST"
    echo "  Socket: /tmp/portal5-powermetrics.sock"
    echo "  Status: sudo launchctl list com.portal5.powermetrics"
    echo "  Uninstall: ./launch.sh uninstall-powermetrics"
}

_launch_uninstall_powermetrics() {
    PLIST_DST="/Library/LaunchDaemons/com.portal5.powermetrics.plist"
    SCRIPT_DST="/usr/local/bin/portal5-powermetrics"
    echo "[portal-5] Uninstalling powermetrics daemon (requires sudo)..."
    sudo launchctl unload "$PLIST_DST" 2>/dev/null || true
    sudo rm -f "$PLIST_DST" "$SCRIPT_DST"
    rm -f "/tmp/portal5-powermetrics.sock"
    echo "[portal-5] ✅ Powermetrics daemon stopped and removed"
}

_launch_workspace_init() {
    WS="${AI_OUTPUT_DIR:-${HOME}/AI_Output}"
    echo "Initializing workspace at: ${WS}"
    mkdir -p "${WS}"/{uploads,generated/transcripts,generated/documents,generated/images,generated/videos,generated/music,generated/speech}
    chmod -R 0775 "${WS}" 2>/dev/null || true
    echo "✅ Workspace structure created"
    ls -la "${WS}/" "${WS}/generated/"
}

_launch_workspace_status() {
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
}

_launch_workspace_show() {
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
}

_launch_start_transcribe() {
    PORTAL_ROOT="${PORTAL_ROOT:-$(pwd)}"
    mkdir -p "$HOME/.portal5/logs"
    PID_FILE="/tmp/portal-mlx-transcribe.pid"
    LOG_FILE="$HOME/.portal5/logs/mlx-transcribe.log"
    if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
      echo "MLX Transcribe already running (PID $(cat "$PID_FILE"))"
      exit 0
    fi
    if [ ! -f "$PORTAL_ROOT/scripts/mlx-transcribe.py" ]; then
      echo "❌ scripts/mlx-transcribe.py not found"
      exit 1
    fi
    set -a; source "$ENV_FILE" 2>/dev/null || true; set +a
    if [ -z "${HF_TOKEN:-}" ]; then
      echo "⚠️  HF_TOKEN not set — diarization will fail on first call."
      echo "   Set in .env after accepting pyannote model licenses on HuggingFace."
    fi
    echo "Starting MLX Transcribe (port 8924)..."
    nohup python3 "$PORTAL_ROOT/scripts/mlx-transcribe.py" >> "$LOG_FILE" 2>&1 &
    echo $! > "$PID_FILE"
    sleep 2
    if kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
      echo "✅ MLX Transcribe started (PID $(cat "$PID_FILE"))"
      echo "   Log: $LOG_FILE"
    else
      echo "❌ Failed to start. Check $LOG_FILE"
      rm -f "$PID_FILE"
      exit 1
    fi
}

_launch_stop_transcribe() {
    PID_FILE="/tmp/portal-mlx-transcribe.pid"
    if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
      kill "$(cat "$PID_FILE")" 2>/dev/null || true
      rm -f "$PID_FILE"
      echo "MLX Transcribe stopped"
    else
      echo "MLX Transcribe not running"
      rm -f "$PID_FILE"
    fi
}

_launch_download_comfyui_models() {
    set -a; source "$ENV_FILE" 2>/dev/null || true; set +a
    COMFYUI_DIR="${COMFYUI_DIR:-$HOME/ComfyUI}"
    IMAGE_MODEL="${IMAGE_MODEL:-flux-schnell}"
    VIDEO_MODEL="${VIDEO_MODEL:-wan2.2}"
    HF_TOKEN="${HF_TOKEN:-}"

    echo "=== Downloading ComfyUI models ==="
    echo "  Image model: $IMAGE_MODEL"
    echo "  Video model: $VIDEO_MODEL"
    echo "  Models dir:  $COMFYUI_DIR/models/checkpoints"
    echo ""

    # Ensure huggingface_hub is available
    if ! python3 -c "import huggingface_hub" &>/dev/null; then
        echo "  Installing huggingface_hub..."
        pip install "huggingface_hub>=0.28" --quiet --break-system-packages 2>/dev/null || \
            python3 -m pip install "huggingface_hub>=0.28" --quiet
    fi

    IMAGE_MODEL="$IMAGE_MODEL" \
    VIDEO_MODEL="$VIDEO_MODEL" \
    HF_TOKEN="$HF_TOKEN" \
    MODELS_DIR="$COMFYUI_DIR/models/checkpoints" \
    python3 "$PORTAL_ROOT/scripts/download_comfyui_models.py"
}

