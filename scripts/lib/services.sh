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
# launchd gives us no shell env and no .env — source it so OWUI_API_KEY /
# PORTAL_PUBLIC_URL reach publish_file_sync (host-native, unlike the Docker MCPs).
set -a; [ -f "\$PORTAL_ROOT/.env" ] && . "\$PORTAL_ROOT/.env"; set +a
export PYTHONPATH="\$PORTAL_ROOT"
export MUSIC_MINIMAX_MODEL_DIR="${MM_MODEL_DIR}"
export OUTPUT_DIR="\${AI_OUTPUT_DIR:-\$HOME/AI_Output}"
export MUSIC_MINIMAX_MCP_PORT="${MM_PORT}"
export OPENWEBUI_URL="\${OPENWEBUI_URL:-http://localhost:8080}"
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

_launch_install_mflux() {
    echo "=== Installing MFLUX MCP natively (MLX-native image generation, Apple Silicon) ==="
    ARCH=$(uname -m)
    MX_DIR="$HOME/.portal5/mflux"
    MX_VENV="$MX_DIR/.venv"
    MX_LOG="$HOME/.portal5/logs/mflux.log"
    MX_PORT="${MFLUX_MCP_PORT:-8933}"

    if [ "$ARCH" != "arm64" ]; then
        echo "  ❌ MFLUX requires Apple Silicon (arm64). Detected: $ARCH."
        echo "  There is no CPU/CUDA fallback for this engine."
        exit 1
    fi
    command -v python3 &>/dev/null || { echo "  ❌ python3 not found (brew install python)"; exit 1; }

    mkdir -p "$MX_DIR" "$HOME/.portal5/logs"
    [ -d "$MX_VENV" ] || { echo "  Creating venv..."; python3 -m venv "$MX_VENV"; }

    echo "  Installing deps (mflux, mcp)..."
    "$MX_VENV/bin/pip" install --quiet --upgrade pip
    "$MX_VENV/bin/pip" install --quiet \
        "mflux" "fastapi>=0.109.0" "uvicorn[standard]>=0.27.0" "httpx>=0.26.0" \
        "pyyaml>=6.0.1" "starlette>=0.35.0" "mcp>=2.0.0,<3.0.0"

    cat > "$MX_DIR/start.sh" << MX_START
#!/bin/bash
PORTAL_ROOT="${PORTAL_ROOT}"
[ -d "\$PORTAL_ROOT/portal" ] || { echo "ERROR: PORTAL_ROOT invalid; re-run install-mflux" >&2; exit 1; }
# launchd gives us no shell env and no .env — source it so OWUI_API_KEY /
# PORTAL_PUBLIC_URL reach publish_file (host-native, unlike the Docker MCPs).
set -a; [ -f "\$PORTAL_ROOT/.env" ] && . "\$PORTAL_ROOT/.env"; set +a
export PYTHONPATH="\$PORTAL_ROOT"
export MFLUX_BIN="$MX_VENV/bin/mflux-generate"
export MFLUX_FLUX2_BIN="$MX_VENV/bin/mflux-generate-flux2"
export MFLUX_MCP_PORT="${MX_PORT}"
# Respect an operator HF cache override (large weight dir on an external volume);
# default is HF's own ~/.cache/huggingface. All mflux model families must resolve
# under the SAME \$HF_HOME/hub — mixing cache roots re-downloads weights.
[ -n "\${HF_HOME:-}" ] && export HF_HOME
export AI_OUTPUT_DIR="\${AI_OUTPUT_DIR:-\$HOME/AI_Output}"
export OPENWEBUI_URL="\${OPENWEBUI_URL:-http://localhost:8080}"
mkdir -p "\$AI_OUTPUT_DIR"
exec "$MX_VENV/bin/python" -m portal.modules.media.tools.mflux_mcp
MX_START
    chmod +x "$MX_DIR/start.sh"

    PLIST="$HOME/Library/LaunchAgents/com.portal5.mflux.plist"
    cat > "$PLIST" << PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
    <key>Label</key><string>com.portal5.mflux</string>
    <key>ProgramArguments</key><array><string>$MX_DIR/start.sh</string></array>
    <key>RunAtLoad</key><true/><key>KeepAlive</key><true/>
    <key>StandardOutPath</key><string>$MX_LOG</string>
    <key>StandardErrorPath</key><string>$MX_LOG</string>
</dict></plist>
PLIST
    launchctl load "$PLIST" 2>/dev/null || true
    echo "  ✅ Registered launchd service: com.portal5.mflux (port $MX_PORT)"
}

_launch_start_mflux() {
    launchctl kickstart -k "gui/$(id -u)/com.portal5.mflux" 2>/dev/null \
        || _launch_install_mflux
    echo "  ✅ MFLUX MCP started (port ${MFLUX_MCP_PORT:-8933})"
}

_launch_stop_mflux() {
    if launchctl print "gui/$(id -u)/com.portal5.mflux" &>/dev/null 2>&1; then
        launchctl bootout "gui/$(id -u)/com.portal5.mflux" 2>/dev/null || true
        echo "MFLUX MCP stopped (launchd)"
    else
        echo "MFLUX MCP not running"
    fi
}

_launch_pull_mflux_models() {
    MX_VENV="$HOME/.portal5/mflux/.venv"
    [ -x "$MX_VENV/bin/mflux-generate" ] || { echo "  ❌ Run ./launch.sh install-mflux first." >&2; exit 1; }
    echo "  Pre-pulling MFLUX model weights (schnell ~34GB, then klein/z-image/qwen-image)..."
    for m in "${@:-schnell flux2-klein-4b z-image-turbo qwen-image}"; do
        echo "  → $m"
        "$MX_VENV/bin/mflux-generate" --model "$m" --prompt "warmup" --steps 1 \
            --quantize 8 --low-ram --width 512 --height 512 \
            --output "/tmp/mflux_warmup_${m}.png" 2>&1 | tail -3 || true
    done
}

_launch_install_video_mlx() {
    echo "=== Installing Video-MLX MCP natively (LTX-2.3 MLX video generation, Apple Silicon) ==="
    ARCH=$(uname -m)
    VX_DIR="$HOME/.portal5/video-mlx"
    VX_SRC="$VX_DIR/ltx-2-mlx"
    VX_VENV="$VX_SRC/.venv"
    VX_LOG="$HOME/.portal5/logs/video-mlx.log"
    VX_PORT="${VIDEO_MLX_MCP_PORT:-8935}"

    if [ "$ARCH" != "arm64" ]; then
        echo "  ❌ Video-MLX requires Apple Silicon (arm64). Detected: $ARCH."
        echo "  There is no CPU/CUDA fallback for this engine."
        exit 1
    fi
    command -v uv &>/dev/null || { echo "  ❌ uv not found (curl -LsSf https://astral.sh/uv/install.sh | sh)"; exit 1; }
    command -v ffmpeg &>/dev/null || echo "  ⚠️  ffmpeg not found — ltx-2-mlx needs it for video encoding (brew install ffmpeg)"

    mkdir -p "$VX_DIR" "$HOME/.portal5/logs"
    if [ -d "$VX_SRC/.git" ]; then
        echo "  Updating ltx-2-mlx..."; git -C "$VX_SRC" pull --quiet || true
    else
        echo "  Cloning dgrauet/ltx-2-mlx..."; git clone --depth 1 https://github.com/dgrauet/ltx-2-mlx.git "$VX_SRC"
    fi
    echo "  Resolving deps (uv sync)..."
    ( cd "$VX_SRC" && uv sync --all-extras )
    # The MCP server needs mcp + starlette in the same venv as ltx-2-mlx.
    "$VX_VENV/bin/python" -m pip install --quiet "mcp>=2.0.0,<3.0.0" "starlette>=0.35.0" \
        "httpx>=0.26.0" "pyyaml>=6.0.1" 2>/dev/null || \
        ( cd "$VX_SRC" && uv pip install "mcp>=2.0.0,<3.0.0" "starlette>=0.35.0" "httpx>=0.26.0" "pyyaml>=6.0.1" )

    cat > "$VX_DIR/start.sh" << VX_START
#!/bin/bash
PORTAL_ROOT="${PORTAL_ROOT}"
[ -d "\$PORTAL_ROOT/portal" ] || { echo "ERROR: PORTAL_ROOT invalid; re-run install-video-mlx" >&2; exit 1; }
set -a; [ -f "\$PORTAL_ROOT/.env" ] && . "\$PORTAL_ROOT/.env"; set +a
export PYTHONPATH="\$PORTAL_ROOT"
export VIDEO_MLX_BIN="$VX_VENV/bin/ltx-2-mlx"
export VIDEO_MLX_MCP_PORT="${VX_PORT}"
export AI_OUTPUT_DIR="\${AI_OUTPUT_DIR:-\$HOME/AI_Output}"
export OPENWEBUI_URL="\${OPENWEBUI_URL:-http://localhost:8080}"
mkdir -p "\$AI_OUTPUT_DIR"
exec "$VX_VENV/bin/python" -m portal.modules.media.tools.video_mlx_mcp
VX_START
    chmod +x "$VX_DIR/start.sh"

    PLIST="$HOME/Library/LaunchAgents/com.portal5.video-mlx.plist"
    cat > "$PLIST" << PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
    <key>Label</key><string>com.portal5.video-mlx</string>
    <key>ProgramArguments</key><array><string>$VX_DIR/start.sh</string></array>
    <key>RunAtLoad</key><true/><key>KeepAlive</key><true/>
    <key>StandardOutPath</key><string>$VX_LOG</string>
    <key>StandardErrorPath</key><string>$VX_LOG</string>
</dict></plist>
PLIST
    launchctl load "$PLIST" 2>/dev/null || true
    echo "  ✅ Registered launchd service: com.portal5.video-mlx (port $VX_PORT)"
}

_launch_start_video_mlx() {
    launchctl kickstart -k "gui/$(id -u)/com.portal5.video-mlx" 2>/dev/null \
        || _launch_install_video_mlx
    echo "  ✅ Video-MLX MCP started (port ${VIDEO_MLX_MCP_PORT:-8935})"
}

_launch_stop_video_mlx() {
    if launchctl print "gui/$(id -u)/com.portal5.video-mlx" &>/dev/null 2>&1; then
        launchctl bootout "gui/$(id -u)/com.portal5.video-mlx" 2>/dev/null || true
        echo "Video-MLX MCP stopped (launchd)"
    else
        echo "Video-MLX MCP not running"
    fi
}

_launch_pull_video_mlx_models() {
    VX_VENV="$HOME/.portal5/video-mlx/ltx-2-mlx/.venv"
    [ -x "$VX_VENV/bin/ltx-2-mlx" ] || { echo "  ❌ Run ./launch.sh install-video-mlx first." >&2; exit 1; }
    echo "  Pre-pulling LTX-2.3 model packs (q4 ~12GB, q8 ~21GB)..."
    for m in "${@:-dgrauet/ltx-2.3-mlx-q4}"; do
        echo "  → $m"
        "$VX_VENV/bin/ltx-2-mlx" info --model "$m" 2>&1 | tail -5 || true
    done
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
export OPENWEBUI_URL="\${OPENWEBUI_URL:-http://localhost:8080}"
export OWUI_API_KEY="\${OWUI_API_KEY:-}"
export PORTAL_PUBLIC_URL="\${PORTAL_PUBLIC_URL:-}"
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

    mkdir -p "${VOICE_PROFILES_DIR:-$HOME/.portal5/voice_profiles}"
    # Warm the voice-clone weights so the first clone isn't a cold multi-GB download.
    _clone_model="${MLX_CLONE_MODEL:-${MLX_CHATTERBOX_MODEL:-mlx-community/higgs-audio-v2-3B-mlx-q8}}"
    python3 -c "from mlx_audio.tts.utils import load_model; load_model('${_clone_model}')" >/dev/null 2>&1 \
        && echo "  ✅ Voice-clone model ready (${_clone_model})" \
        || echo "  ⚠️  Voice-clone warmup failed — first clone will cold-load (or run: pip3 install -U mlx-audio)"

    PID_FILE="/tmp/portal-mlx-speech.pid"
    LOG_FILE="$HOME/.portal5/logs/mlx-speech.log"
    mkdir -p "$(dirname "$LOG_FILE")"

    if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
        echo "  ℹ️  MLX Speech already running (PID $(cat "$PID_FILE"))"
        exit 0
    fi

    echo "Starting MLX Speech Server (Kokoro + voice clone + Qwen3-ASR)..."
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
    # Pre-download both engines here (this shell has network + HF cache access).
    # The service itself runs with HF_HUB_OFFLINE=1 — under launchd the cached-file
    # revalidation HEAD requests hang indefinitely, so the service must never touch
    # the network. Warm now, serve from cache.
    TR_PY="$PORTAL_ROOT/.venv/bin/python3"; [ -x "$TR_PY" ] || TR_PY="$(command -v python3)"
    "$TR_PY" -c "from mlx_audio.stt.utils import load as sload; from mlx_audio.vad import load as vload; sload('${MLX_PARAKEET_MODEL:-mlx-community/parakeet-tdt-0.6b-v3}'); vload('${MLX_DIARIZE_MODEL:-mlx-community/diar_sortformer_4spk-v1-fp32}')" >/dev/null 2>&1 \
      && echo "  ✅ Parakeet + Sortformer cached" || echo "  ⚠️  Engine warmup skipped — first request will fail if models aren't already cached (run: uv pip install -U mlx-audio)"
    echo "Starting MLX Transcribe (port 8924, Parakeet transcript + Sortformer diarization)..."
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

