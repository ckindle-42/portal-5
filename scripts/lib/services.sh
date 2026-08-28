#!/usr/bin/env bash
# services.sh — Portal 5 service commands (sourced by launch.sh)
# shellcheck shell=bash

_launch_install_ollama() {
    echo "=== Ollama status (Apple Silicon / Metal GPU) ==="
    ARCH=$(uname -m)

    if [ "$ARCH" != "arm64" ]; then
        echo "  ℹ️  Non-Apple-Silicon detected ($ARCH)."
        echo "  For Linux: curl -fsSL https://ollama.com/install.sh | sh"
        echo "  Then run:  ./launch.sh up --profile docker-ollama"
        exit 0
    fi

    # Homebrew's ollama is NOT used on this project (disabled 2026-08-10) —
    # it lags upstream releases and this project tracks newer Ollama
    # versions faster than brew publishes them (native MLX Metal on Apple
    # Silicon requires 0.32.4+; see OLLAMA_MIN_VERSION in scripts/lib/util.sh).
    # The supported install is a pinned binary release run as a system
    # LaunchDaemon (`com.portal5.ollama`), not `brew install ollama`.
    if [ -f /Library/LaunchDaemons/com.portal5.ollama.plist ]; then
        OLLAMA_API_VER=$(curl -s http://localhost:11434/api/version 2>/dev/null | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1)
        if [ -n "$OLLAMA_API_VER" ]; then
            echo "  ✅ com.portal5.ollama running (v${OLLAMA_API_VER})"
        else
            echo "  ⚠️  com.portal5.ollama is configured but not responding — restart it:"
            echo "     sudo launchctl kickstart -k system/com.portal5.ollama"
        fi
        echo ""
        echo "Next steps:"
        echo "  ./launch.sh up           — start Portal 5 stack"
        echo "  ./launch.sh pull-models  — pull AI models (30-90 min)"
        return
    fi

    echo "  ❌ No pinned Ollama LaunchDaemon found."
    echo "  This project does not use 'brew install ollama' — it ships below the"
    echo "  version this project requires (see OLLAMA_MIN_VERSION) and brew lags"
    echo "  upstream releases. Set up the pinned native install manually:"
    echo "    1. Download the current Ollama release for macOS/arm64 from"
    echo "       https://github.com/ollama/ollama/releases and unpack it to"
    echo "       e.g. ~/ollama-<version>/"
    echo "    2. ln -sfn ~/ollama-<version> ~/ollama-current   (stable indirection —"
    echo "       future upgrades are then just re-pointing this one symlink, not"
    echo "       editing the plist or PATH again)"
    echo "    3. Create /Library/LaunchDaemons/com.portal5.ollama.plist with"
    echo "       ProgramArguments pointing at ~/ollama-current/ollama, and"
    echo "       EnvironmentVariables OLLAMA_MODELS/OLLAMA_MAX_LOADED_MODELS/"
    echo "       OLLAMA_NUM_PARALLEL/OLLAMA_GPU_OVERHEAD set (see docs/ADMIN_GUIDE.md)."
    echo "    4. ln -sfn ~/ollama-current/ollama /opt/homebrew/bin/ollama   (PATH)"
    echo "    5. sudo launchctl bootstrap system /Library/LaunchDaemons/com.portal5.ollama.plist"
    echo "  This is a deliberate one-time, root-owned setup step — not automated"
    echo "  here — so re-run this command once it's in place to verify status."
    exit 1
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
    --port 8188
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

_launch_install_music_minimax() {
    echo "=== Installing MiniMax-Music3-MLX MCP natively (Apple Silicon / MLX) ==="
    ARCH=$(uname -m)
    MM_DIR="$HOME/.portal5/music-minimax"
    MM_VENV="$MM_DIR/.venv"
    MM_MODEL_DIR="$MM_DIR/model"
    MM_LOG="$HOME/.portal5/logs/music-minimax.log"
    MM_PORT="${MUSIC_MINIMAX_PORT:-8912}"

    if [ "$ARCH" != "arm64" ]; then
        echo "  ❌ MiniMax-Music3-MLX requires Apple Silicon (arm64). Detected: $ARCH."
        echo "  There is no CPU/CUDA fallback for this engine."
        exit 1
    fi
    command -v python3 &>/dev/null || { echo "  ❌ python3 not found (brew install python)"; exit 1; }

    mkdir -p "$MM_DIR" "$HOME/.portal5/logs"
    [ -d "$MM_VENV" ] || { echo "  Creating venv..."; python3 -m venv "$MM_VENV"; }

    # Versions pinned to the model repo's own requirements.txt (verified 2026-08-27):
    # mlx==0.30.6, mlx-metal==0.30.6, numpy>=2.0,<3, tokenizers>=0.22,<0.23. No torch.
    echo "  Installing deps (mlx, mcp)..."
    "$MM_VENV/bin/pip" install --quiet --upgrade pip
    "$MM_VENV/bin/pip" install --quiet \
        "mlx==0.30.6" "mlx-metal==0.30.6" "numpy>=2.0,<3" "tokenizers>=0.22,<0.23" \
        "huggingface_hub[hf_xet]" "fastapi>=0.109.0" "uvicorn[standard]>=0.27.0" \
        "httpx>=0.26.0" "pyyaml>=6.0.1" "starlette>=0.35.0" "mcp>=2.0.0,<3.0.0"

    if [ -f "$MM_MODEL_DIR/minimax_mlx_model.py" ]; then
        echo "  ✅ Model already present at $MM_MODEL_DIR"
    else
        echo "  Downloading PocketAiHub/MiniMax-Music3-MLX (~11.9GB, one-time)..."
        mkdir -p "$MM_MODEL_DIR"
        "$MM_VENV/bin/hf" download PocketAiHub/MiniMax-Music3-MLX --local-dir "$MM_MODEL_DIR"
        SIZE_GB=$(du -sg "$MM_MODEL_DIR" 2>/dev/null | cut -f1)
        [ -n "$SIZE_GB" ] && [ "$SIZE_GB" -lt 8 ] && echo "  ⚠️  Only ${SIZE_GB}GB downloaded — expected ~12GB; re-run install-music-minimax"
    fi

    cat > "$MM_DIR/start.sh" << MM_START
#!/bin/bash
PORTAL_ROOT="${PORTAL_ROOT}"
[ -d "\$PORTAL_ROOT/portal_mcp" ] || { echo "ERROR: PORTAL_ROOT invalid; re-run install-music-minimax" >&2; exit 1; }
export PYTHONPATH="\$PORTAL_ROOT"
export MUSIC_MINIMAX_MODEL_DIR="${MM_MODEL_DIR}"
export OUTPUT_DIR="\${AI_OUTPUT_DIR:-\$HOME/AI_Output}"
export MUSIC_MINIMAX_MCP_PORT="${MM_PORT}"
mkdir -p "\$OUTPUT_DIR"
exec "$MM_VENV/bin/python" -m portal.modules.media.tools.music_minimax_mcp
MM_START
    chmod +x "$MM_DIR/start.sh"

    PLIST="$HOME/Library/LaunchAgents/com.portal5.music-minimax.plist"
    cat > "$PLIST" << PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
    <key>Label</key><string>com.portal5.music-minimax</string>
    <key>ProgramArguments</key><array><string>$MM_DIR/start.sh</string></array>
    <key>RunAtLoad</key><true/><key>KeepAlive</key><true/>
    <key>StandardOutPath</key><string>$MM_LOG</string>
    <key>StandardErrorPath</key><string>$MM_LOG</string>
</dict></plist>
PLIST
    launchctl load "$PLIST" 2>/dev/null || true
    echo "  ✅ Registered launchd service: com.portal5.music-minimax (port $MM_PORT)"
}

_launch_install_music_ace() {
    echo "=== Installing ACE-Step-1.5 engine + proxy MCP (Apple Silicon / MLX) ==="
    ARCH=$(uname -m)
    ACE_DIR="$HOME/.portal5/music-ace"
    ACE_RUNTIME="$ACE_DIR/ace-runtime"
    ACE_VENV="$ACE_DIR/.venv"
    ACE_ENGINE_PORT="${ACESTEP_ENGINE_PORT:-8001}"
    ACE_MCP_PORT="${MUSIC_ACE_MCP_PORT:-8933}"
    ACE_LOG="$HOME/.portal5/logs/music-ace.log"
    ACE_ENGINE_LOG="$HOME/.portal5/logs/acestep-server.log"

    if [ "$ARCH" != "arm64" ]; then
        echo "  ℹ️  Non-arm64 ($ARCH): ACE-Step-1.5 auto-falls-back to PyTorch (no MLX accel). Continuing."
    fi
    mkdir -p "$ACE_DIR" "$HOME/.portal5/logs"
    command -v uv &>/dev/null || { echo "  Installing uv..."; curl -LsSf https://astral.sh/uv/install.sh | sh; }
    UV_BIN=$(command -v uv)

    if [ ! -d "$ACE_RUNTIME" ]; then
        echo "  Cloning ace-step/ACE-Step-1.5..."
        git clone https://github.com/ace-step/ACE-Step-1.5.git "$ACE_RUNTIME"
    fi
    cd "$ACE_RUNTIME"
    uv sync

    if [ ! -d "checkpoints/acestep-v15-sft" ]; then
        echo "  Downloading ACE-Step main bundle + sft (2B non-turbo) DiT..."
        uv run acestep-download
        uv run hf download ACE-Step/acestep-v15-sft --local-dir ./checkpoints/acestep-v15-sft
    fi
    chmod +x start_api_server_macos.sh

    cat > "$ACE_DIR/start-engine.sh" << ACE_ENGINE
#!/bin/bash
cd "$ACE_RUNTIME"
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
export ACESTEP_API_PORT="${ACE_ENGINE_PORT}"
export ACESTEP_CONFIG_PATH="acestep-v15-sft"
export ACESTEP_LM_BACKEND="mlx"
exec "$UV_BIN" run acestep-api --host 127.0.0.1 --port "${ACE_ENGINE_PORT}" --lm-model-path acestep-5Hz-lm-1.7B
ACE_ENGINE
    chmod +x "$ACE_DIR/start-engine.sh"

    PLIST_ENGINE="$HOME/Library/LaunchAgents/com.portal5.acestep-server.plist"
    cat > "$PLIST_ENGINE" << PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
    <key>Label</key><string>com.portal5.acestep-server</string>
    <key>ProgramArguments</key><array><string>$ACE_DIR/start-engine.sh</string></array>
    <key>RunAtLoad</key><true/><key>KeepAlive</key><true/>
    <key>StandardOutPath</key><string>$ACE_ENGINE_LOG</string>
    <key>StandardErrorPath</key><string>$ACE_ENGINE_LOG</string>
</dict></plist>
PLIST
    launchctl load "$PLIST_ENGINE" 2>/dev/null || true

    [ -d "$ACE_VENV" ] || python3 -m venv "$ACE_VENV"
    "$ACE_VENV/bin/pip" install --quiet --upgrade pip
    "$ACE_VENV/bin/pip" install --quiet \
        "fastapi>=0.109.0" "uvicorn[standard]>=0.27.0" "httpx>=0.26.0" \
        "pyyaml>=6.0.1" "starlette>=0.35.0" "mcp>=2.0.0,<3.0.0"

    cat > "$ACE_DIR/start-mcp.sh" << ACE_MCP
#!/bin/bash
PORTAL_ROOT="${PORTAL_ROOT}"
[ -d "\$PORTAL_ROOT/portal_mcp" ] || { echo "ERROR: PORTAL_ROOT invalid; re-run install-music-ace" >&2; exit 1; }
export PYTHONPATH="\$PORTAL_ROOT"
export ACESTEP_URL="http://127.0.0.1:${ACE_ENGINE_PORT}"
export OUTPUT_DIR="\${AI_OUTPUT_DIR:-\$HOME/AI_Output}"
export MUSIC_ACE_MCP_PORT="${ACE_MCP_PORT}"
mkdir -p "\$OUTPUT_DIR"
exec "$ACE_VENV/bin/python" -m portal.modules.media.tools.music_ace_mcp
ACE_MCP
    chmod +x "$ACE_DIR/start-mcp.sh"

    PLIST_MCP="$HOME/Library/LaunchAgents/com.portal5.music-ace-mcp.plist"
    cat > "$PLIST_MCP" << PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
    <key>Label</key><string>com.portal5.music-ace-mcp</string>
    <key>ProgramArguments</key><array><string>$ACE_DIR/start-mcp.sh</string></array>
    <key>RunAtLoad</key><true/><key>KeepAlive</key><true/>
    <key>StandardOutPath</key><string>$ACE_LOG</string>
    <key>StandardErrorPath</key><string>$ACE_LOG</string>
</dict></plist>
PLIST
    launchctl load "$PLIST_MCP" 2>/dev/null || true
    echo "  ✅ ACE-Step engine (com.portal5.acestep-server, :$ACE_ENGINE_PORT) + proxy MCP (com.portal5.music-ace-mcp, :$ACE_MCP_PORT)"
}

_launch_stop_music_ace() {
    launchctl unload "$HOME/Library/LaunchAgents/com.portal5.music-ace-mcp.plist" 2>/dev/null || true
    launchctl unload "$HOME/Library/LaunchAgents/com.portal5.acestep-server.plist" 2>/dev/null || true
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
    # RETIRED CPU fallback (P0.4): the adopted default embedding backend at
    # :8917 is now Arm A (MLX Qwen3, `start-embedding-arm-a` / launchd
    # EMBEDDING_BACKEND=mlx). This function keeps the old sentence-transformers
    # server available for explicit fallback only; it is no longer the default.

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

    echo "[portal-5] Starting RETIRED CPU embedding server (fallback only)..."
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

_launch_start_embedding_arm_a() {
    # ADOPTED default embedding backend (P0.4): MLX-native embedding server
    # (Qwen3-Embedding-0.6B mxfp8), GPU-native via mlx_embeddings. Binds to
    # EMBEDDING_HOST_PORT (default 8917) — the adopted :8917 default. The SA3
    # bake-off port (8941) remains as EMBEDDING_ARM_A_PORT for parallel runs.
    if [ -f "$ENV_FILE" ]; then set -a; source "$ENV_FILE"; set +a; fi
    PID_FILE="/tmp/portal-embedding-arm-a.pid"
    if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
        echo "  ✅ Arm A MLX embedding server already running (PID $(cat "$PID_FILE"))"
        exit 0
    fi
    MODEL="${EMBEDDING_MODEL_ARM_A:-${HOME}/.portal5/models/Qwen3-Embedding-0.6B-mxfp8}"
    PORT="${EMBEDDING_ARM_A_PORT:-${EMBEDDING_HOST_PORT:-8917}}"
    LOG_FILE="${HOME}/.portal5/logs/embedding-server-mlx.log"
    mkdir -p "$(dirname "$LOG_FILE")"
    echo "Starting Arm A MLX embedding server (Qwen3-Embedding-0.6B mxfp8, adopted default)..."
    nohup uv run --project "$PORTAL_ROOT" python3 "$PORTAL_ROOT/scripts/embedding-server-mlx.py" \
        --model "$MODEL" \
        --port "$PORT" \
        --host 0.0.0.0 \
        >"$LOG_FILE" 2>&1 &
    echo $! > "$PID_FILE"
    echo "  ✅ Arm A MLX embedding server started (PID $!, port $PORT)"
    echo "  📋 Log: $LOG_FILE"
}

_launch_stop_embedding_arm_a() {
    PID_FILE="/tmp/portal-embedding-arm-a.pid"
    if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
        kill "$(cat "$PID_FILE")"
        rm -f "$PID_FILE"
        echo "  ✅ Arm A MLX embedding server stopped"
    else
        echo "  ℹ️  Arm A MLX embedding server not running"
    fi
}

_launch_start_embedding_arm_b() {
    # Arm B (SA3.3): llama.cpp embedding server (EmbeddingGemma-300M Q8_0) with
    # EmbeddingGemma task prefixes. Binds to EMBEDDING_ARM_B_PORT (default 8943)
    # and spawns llama-server as a child on --llama-port. Runs alongside the
    # incumbent CPU server during the SA3 bake-off.
    if [ -f "$ENV_FILE" ]; then set -a; source "$ENV_FILE"; set +a; fi
    PID_FILE="/tmp/portal-embedding-arm-b.pid"
    if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
        echo "  ✅ Arm B llama.cpp embedding server already running (PID $(cat "$PID_FILE"))"
        exit 0
    fi
    MODEL="${EMBEDDING_MODEL_ARM_B:-${HOME}/.portal5/models/embeddinggemma-300m/embeddinggemma-300M-Q8_0.gguf}"
    PORT="${EMBEDDING_ARM_B_PORT:-8943}"
    LOG_FILE="${HOME}/.portal5/logs/embedding-server-llamacpp.log"
    mkdir -p "$(dirname "$LOG_FILE")"
    echo "Starting Arm B llama.cpp embedding server (EmbeddingGemma-300M Q8)..."
    nohup uv run --project "$PORTAL_ROOT" python3 "$PORTAL_ROOT/scripts/embedding-server-llamacpp.py" \
        --model "$MODEL" \
        --port "$PORT" \
        --host 0.0.0.0 \
        >"$LOG_FILE" 2>&1 &
    echo $! > "$PID_FILE"
    echo "  ✅ Arm B llama.cpp embedding server started (PID $!, port $PORT)"
    echo "  📋 Log: $LOG_FILE"
}

_launch_stop_embedding_arm_b() {
    PID_FILE="/tmp/portal-embedding-arm-b.pid"
    if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
        kill "$(cat "$PID_FILE")"
        rm -f "$PID_FILE"
        echo "  ✅ Arm B llama.cpp embedding server stopped"
    else
        echo "  ℹ️  Arm B llama.cpp embedding server not running"
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

# Deprecated: delegated to ``portal workspace init`` in portal/platform/inference/cli/ (M5 Stage 2).
# Retained for parity; remove in next M5 pass.
_launch_workspace_init() {
    WS="${AI_OUTPUT_DIR:-${HOME}/AI_Output}"
    echo "Initializing workspace at: ${WS}"
    mkdir -p "${WS}"/{uploads,generated/transcripts,generated/documents,generated/images,generated/videos,generated/music,generated/speech}
    chmod -R 0775 "${WS}" 2>/dev/null || true
    echo "✅ Workspace structure created"
    ls -la "${WS}/" "${WS}/generated/"
}

# Deprecated: delegated to ``portal workspace status`` in portal/platform/inference/cli/ (M5 Stage 2).
# Retained for parity; remove in next M5 pass.
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

# Deprecated: delegated to ``portal workspace show`` in portal/platform/inference/cli/ (M5 Stage 2).
# Retained for parity; remove in next M5 pass.
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
    # Warm the fast engine so the first request isn't a cold multi-GB download.
    python3 -c "from mlx_audio.stt.utils import load; load('${MLX_PARAKEET_MODEL:-mlx-community/parakeet-tdt-0.6b-v3}')" >/dev/null 2>&1 \
      && echo "  ✅ Parakeet ASR ready" || echo "  ⚠️  Parakeet warmup skipped (or run: pip3 install -U mlx-audio)"
    echo "Starting MLX Transcribe (port 8924, Parakeet + VibeVoice diarization)..."
    _ensure_native_mcp_service \
      "mlx-transcribe" "com.portal5.mlx-transcribe" \
      "${MLX_TRANSCRIBE_PORT:-8924}" "mlx-transcribe"
    sleep 2
    if curl -fsS "http://localhost:${MLX_TRANSCRIBE_PORT:-8924}/health" &>/dev/null; then
      echo "✅ MLX Transcribe is healthy"
      echo "   Log: $LOG_FILE"
    else
      echo "❌ Failed to start. Check $LOG_FILE"
      exit 1
    fi
}

_launch_stop_transcribe() {
    PID_FILE="/tmp/portal-mlx-transcribe.pid"
    if [ "$(uname -s)" = "Darwin" ] &&
       launchctl print "gui/$(id -u)/com.portal5.mlx-transcribe" &>/dev/null 2>&1; then
      launchctl bootout "gui/$(id -u)/com.portal5.mlx-transcribe" 2>/dev/null || true
      rm -f "$PID_FILE"
      echo "MLX Transcribe stopped (launchd)"
    elif [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
      kill "$(cat "$PID_FILE")" 2>/dev/null || true
      rm -f "$PID_FILE"
      echo "MLX Transcribe stopped"
    else
      echo "MLX Transcribe not running"
      rm -f "$PID_FILE"
    fi
}

_launch_download_comfyui_models() {
    echo "  ❌ download-comfyui-models has no implementation." >&2
    echo "     scripts/download_comfyui_models.py was removed in ea864cf2 (2026-05-23)," >&2
    echo "     with the intent that pull-wan22/pull-qwen-image would replace it." >&2
    echo "     Use ./launch.sh pull-wan22 for Wan 2.2 video models." >&2
    exit 1
}

# Wan 2.2 TI2V-5B + S2V-14B + T2V-A14B — flat filenames in ComfyUI's
# actually-scanned models/<type>/ folders. Comfy-Org/Wan_2.2_ComfyUI_Repackaged
# nests these under split_files/<type>/ internally; --local-dir must target
# the model-type-folder itself (not models/) and the split_files/<type>/
# prefix must be stripped from the destination, or ComfyUI never sees the
# files (see unit-known-limitations-comfyui-model-download-commands-are-broken).
#
# T2V-A14B is a two-expert MoE (high-noise + low-noise, ~13GB each) — there is
# no single merged file, matching ComfyUI's official reference workflow.
#
# Animate-14B is NOT covered: stub requiring SAM2/DWPreprocessor/CLIPVision
# custom ComfyUI nodes that aren't installed. Documented gap, not promised —
# see unit-known-limitations-wan22-fp8-scaled-checkpoints-crash-on-apple-silicon-mps.
_launch_pull_wan22() {
    set -a; source "$ENV_FILE" 2>/dev/null || true; set +a
    COMFYUI_DIR="${COMFYUI_DIR:-$HOME/ComfyUI}"

    if [ ! -d "$COMFYUI_DIR" ]; then
        echo "  ❌ $COMFYUI_DIR not found. Run ./launch.sh install-comfyui first." >&2
        exit 1
    fi

    if ! command -v hf &>/dev/null; then
        echo "  Installing huggingface_hub CLI..."
        pip install "huggingface_hub>=0.28" --quiet --break-system-packages 2>/dev/null || \
            python3 -m pip install "huggingface_hub>=0.28" --quiet
    fi

    echo "=== Pulling Wan 2.2 TI2V-5B + S2V-14B + T2V-A14B (ComfyUI-flat layout) ==="
    echo "  Target: $COMFYUI_DIR/models/{diffusion_models,vae,text_encoders,audio_encoders}/"
    echo ""

    REPO="Comfy-Org/Wan_2.2_ComfyUI_Repackaged"
    declare -a FILES=(
        "split_files/diffusion_models/wan2.2_ti2v_5B_fp16.safetensors:diffusion_models"
        "split_files/vae/wan2.2_vae.safetensors:vae"
        "split_files/text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors:text_encoders"
        "split_files/diffusion_models/wan2.2_s2v_14B_fp8_scaled.safetensors:diffusion_models"
        "split_files/audio_encoders/wav2vec2_large_english_fp16.safetensors:audio_encoders"
        "split_files/diffusion_models/wan2.2_t2v_high_noise_14B_fp8_scaled.safetensors:diffusion_models"
        "split_files/diffusion_models/wan2.2_t2v_low_noise_14B_fp8_scaled.safetensors:diffusion_models"
    )

    for entry in "${FILES[@]}"; do
        repo_path="${entry%%:*}"
        model_type="${entry##*:}"
        dest_dir="$COMFYUI_DIR/models/$model_type"
        filename="${repo_path##*/}"
        mkdir -p "$dest_dir"
        if [ -f "$dest_dir/$filename" ]; then
            echo "  ✅ $model_type/$filename already present, skipping"
            continue
        fi
        echo "  Downloading $repo_path -> $dest_dir/"
        hf download "$REPO" "$repo_path" --local-dir "$dest_dir"
        # hf download preserves the repo-internal split_files/<type>/ prefix
        # as real subdirectories under --local-dir; flatten it.
        if [ -f "$dest_dir/$repo_path" ]; then
            mv "$dest_dir/$repo_path" "$dest_dir/$filename"
            rm -rf "$dest_dir/split_files"
        fi
    done

    echo ""
    echo "Done. Restart ComfyUI (or wait for its live model-folder re-scan) and verify:"
    echo "  curl -s localhost:8188/object_info/UNETLoader | grep wan2.2"
}

# Qwen-Image family (T2I, MPS-compatible Edit-2509, Lightning distillation
# LoRA) — same flat-layout / split_files-flatten handling as pull-wan22.
# These are the exact checkpoints verified on this Apple Silicon host. Plain
# fp8 storage works; the scaled/mixed fp8 2511 checkpoint does not. ~48GiB total.
_launch_pull_qwen_image() {
    set -a; source "$ENV_FILE" 2>/dev/null || true; set +a
    COMFYUI_DIR="${COMFYUI_DIR:-$HOME/ComfyUI}"

    if [ ! -d "$COMFYUI_DIR" ]; then
        echo "  ❌ $COMFYUI_DIR not found. Run ./launch.sh install-comfyui first." >&2
        exit 1
    fi

    if ! command -v hf &>/dev/null; then
        echo "  Installing huggingface_hub CLI..."
        pip install "huggingface_hub>=0.28" --quiet --break-system-packages 2>/dev/null || \
            python3 -m pip install "huggingface_hub>=0.28" --quiet
    fi

    echo "=== Pulling Qwen-Image T2I + Edit-2509 + Lightning LoRA (ComfyUI-flat layout) ==="
    echo "  Target: $COMFYUI_DIR/models/{diffusion_models,text_encoders,vae,loras}/"
    echo ""

    _pull_flat() {
        local repo="$1" repo_path="$2" model_type="$3"
        local dest_dir="$COMFYUI_DIR/models/$model_type"
        local filename="${repo_path##*/}"
        mkdir -p "$dest_dir"
        if [ -f "$dest_dir/$filename" ]; then
            echo "  ✅ $model_type/$filename already present, skipping"
            return
        fi
        echo "  Downloading $repo_path -> $dest_dir/"
        hf download "$repo" "$repo_path" --local-dir "$dest_dir"
        if [ -f "$dest_dir/$repo_path" ]; then
            mv "$dest_dir/$repo_path" "$dest_dir/$filename"
            rm -rf "$dest_dir/split_files"
        fi
    }

    QI_REPO="Comfy-Org/Qwen-Image_ComfyUI"
    QI_EDIT_REPO="Comfy-Org/Qwen-Image-Edit_ComfyUI"
    LIGHTNING_REPO="lightx2v/Qwen-Image-Lightning"

    _pull_flat "$QI_REPO" "split_files/diffusion_models/qwen_image_fp8_e4m3fn.safetensors" "diffusion_models"
    _pull_flat "$QI_REPO" "split_files/text_encoders/qwen_2.5_vl_7b_fp8_scaled.safetensors" "text_encoders"
    _pull_flat "$QI_REPO" "split_files/vae/qwen_image_vae.safetensors" "vae"
    _pull_flat "$QI_EDIT_REPO" "split_files/diffusion_models/qwen_image_edit_2509_fp8_e4m3fn.safetensors" "diffusion_models"

    LORA_DEST="$COMFYUI_DIR/models/loras"
    LORA_FILE="Qwen-Image-Lightning-8steps-V1.1-bf16.safetensors"
    mkdir -p "$LORA_DEST"
    if [ -f "$LORA_DEST/$LORA_FILE" ]; then
        echo "  ✅ loras/$LORA_FILE already present, skipping"
    else
        echo "  Downloading $LORA_FILE -> $LORA_DEST/"
        hf download "$LIGHTNING_REPO" "$LORA_FILE" --local-dir "$LORA_DEST"
    fi

    echo ""
    echo "Done. Verify:"
    echo "  curl -s localhost:8188/object_info/UNETLoader | grep qwen"
}
