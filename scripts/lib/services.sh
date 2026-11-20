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
            echo "     $(_portal5_root launchctl-system com.portal5.ollama 'sudo launchctl kickstart -k system/com.portal5.ollama')"
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
    echo "       Set OLLAMA_KV_CACHE_TYPE from the repo .env (default q8_0)."
    echo "    4. ln -sfn ~/ollama-current/ollama /opt/homebrew/bin/ollama   (PATH)"
    echo "    5. sudo launchctl bootstrap system /Library/LaunchDaemons/com.portal5.ollama.plist"
    echo "  This is a deliberate one-time, root-owned setup step — not automated"
    echo "  here — so re-run this command once it's in place to verify status."
    exit 1
}

# Latest sweep report outside the repo. Empty when none exists.
_latest_sweep_report() {
    local report="" candidate
    for candidate in "$HOME/.portal5/security"/security_sweep_*.md; do
        [ -f "$candidate" ] || continue
        if [ -z "$report" ] || [[ "$candidate" > "$report" ]]; then
            report="$candidate"
        fi
    done
    if [ -n "${PORTAL_SWEEP_REPORT:-}" ]; then
        report="$PORTAL_SWEEP_REPORT"
    fi
    printf '%s' "$report"
}

# Resolve service deps against the engine lock floors and a fresh apply-time sweep.
_engine_dep_plan() {
    local service="$1" py="$2" mode="${3:-apply}" project="${4:-}"
    local portal_py="$PORTAL_ROOT/.venv/bin/python"
    [ -x "$portal_py" ] || portal_py="$(command -v python3)"
    local report="" work_dir="" candidate status upstream_requirements=""
    if [ "$mode" = "apply" ] || [ -n "$project" ]; then
        work_dir="$(mktemp -d "${TMPDIR:-/tmp}/portal5-engine-sweep.XXXXXX")" || return 1
    fi
    if [ "$mode" = "apply" ]; then
        if ! "$portal_py" "$PORTAL_ROOT/scripts/security_sweep.py" \
            --repo "$PORTAL_ROOT" --home "$HOME" --output-dir "$work_dir" \
            --skip-images --no-alert --no-delta; then
            echo "  ❌ fresh security sweep failed; refusing to apply engine dependencies" >&2
            [ -z "$work_dir" ] || rm -rf "$work_dir"
            return 1
        fi
        for candidate in "$work_dir"/security_sweep_*.md; do
            [ -f "$candidate" ] || continue
            report="$candidate"
        done
        if [ -z "$report" ]; then
            echo "  ❌ fresh security sweep produced no report; refusing to apply engine dependencies" >&2
            [ -z "$work_dir" ] || rm -rf "$work_dir"
            return 1
        fi
    else
        report="$(_latest_sweep_report)"
    fi
    if [ -n "$project" ]; then
        if [ ! -f "$project/uv.lock" ]; then
            echo "  ❌ upstream lock missing from $project; refusing dependency plan" >&2
            [ -z "$work_dir" ] || rm -rf "$work_dir"
            return 1
        fi
        upstream_requirements="$work_dir/upstream-requirements.txt"
        local export_args=( uv export --locked --format requirements.txt --no-hashes
            --no-annotate --no-emit-project --no-emit-local --python "$py"
            --output-file "$upstream_requirements" )
        [ "$service" != "video" ] || export_args+=( --all-extras )
        if ! ( cd "$project" && "${export_args[@]}" ); then
            echo "  ❌ cannot export upstream lock from $project; refusing dependency plan" >&2
            [ -z "$work_dir" ] || rm -rf "$work_dir"
            return 1
        fi
    fi
    local args=( "$portal_py" "$PORTAL_ROOT/scripts/engine_install_plan.py"
        --service "$service" --python "$py" --mode "$mode" )
    if [ -n "$report" ]; then
        args+=( --sweep-report "$report" )
    fi
    if [ -n "$upstream_requirements" ]; then
        args+=( --upstream-requirements "$upstream_requirements" )
    fi
    if "${args[@]}"; then status=0; else status=$?; fi
    [ -z "$work_dir" ] || rm -rf "$work_dir"
    return "$status"
}

# bootout is optional (the label may be unloaded). bootstrap and a running
# state are not: a swallowed failure left com.portal5.video-mlx unloaded.
# Reloads share _launchd_reload_job — bootout → wait gone → bootstrap retry
# → wait /health; a bespoke bootout/bootstrap raced launchd's teardown here
# and left the media services unloaded (2026-11-20, "Bootstrap failed: 5").
_launchd_reload_or_fail() {  # label, plist, health_url
    if ! _launchd_reload_job "$1" "$2" "gui/$(id -u)" "$3"; then
        echo "  ❌ $1 is not serving $3 after the install reload" >&2
        exit 1
    fi
    echo "  ✅ $1 loaded and running"
}

_launch_install_music() {
    echo "=== Installing music MCP (ACE-Step 1.5 XL-Turbo, MiniMax 8-bit fallback) ==="
    ARCH=$(uname -m)
    MUSIC_DIR="$HOME/.portal5/music"
    ACE_DIR="$MUSIC_DIR/ACE-Step-1.5"
    ACE_SHA="ca1e85fe9430179831e6bc6be790c332190a3866"
    MUSIC_PORT="${MUSIC_MCP_PORT:-8912}"
    MUSIC_LOG="$HOME/.portal5/logs/music.log"
    PY="$ACE_DIR/.venv/bin/python"

    local dry=0
    [ "${1:-}" = "--dry-run" ] && dry=1
    if [ "$ARCH" != "arm64" ]; then
        echo "  ❌ Music engines require Apple Silicon (arm64). Detected: $ARCH."
        exit 1
    fi
    if [ "$dry" -eq 1 ]; then
        _engine_dep_plan music "$PY" dry-run "$ACE_DIR"
        echo "  dry-run: no clone, no pip apply, no launchctl"
        return 0
    fi
    command -v git >/dev/null || { echo "  ❌ git not found"; exit 1; }
    command -v uv >/dev/null || { echo "  ❌ uv not found"; exit 1; }
    mkdir -p "$MUSIC_DIR" "$HOME/.portal5/logs"
    echo "  Pins: ace-step @ ${ACE_SHA} (uv.lock, Python 3.12), mlx-audio==0.6.6."
    echo "  Downloads: ACE-Step/acestep-v15-xl-turbo ~18.8GB; ACE-Step/acestep-5Hz-lm-1.7B (size unpinned);"
    echo "    acestep-download core bundle (size unpinned); mlx-community/MiniMax-Music3-8bit ~14GB estimate."

    if [ ! -d "$ACE_DIR/.git" ]; then
        git clone https://github.com/ace-step/ACE-Step-1.5.git "$ACE_DIR"
    fi
    git -C "$ACE_DIR" fetch --depth 1 origin "$ACE_SHA"
    git -C "$ACE_DIR" checkout --detach "$ACE_SHA"
    if [ -d "$ACE_DIR/.venv" ]; then
        [ -x "$PY" ] || { echo "  ❌ Existing ACE-Step venv has no usable Python: $PY" >&2; exit 1; }
        echo "  Preserving the existing ACE-Step venv; the upstream lock seeds new installs only."
    else
        ( cd "$ACE_DIR" && uv python install 3.12 && uv sync --python 3.12 --frozen )
    fi
    _engine_dep_plan music "$PY" apply "$ACE_DIR" || {
        echo "  ❌ security dependency upgrade failed" >&2; exit 1;
    }

    _music_snap() {
        local repo="$1" dest="$2" min_gb="$3" size_gb
        if [ -d "$dest" ] && [ -n "$(find "$dest" -type f -print -quit)" ]; then
            echo "  present: $dest"
        else
            echo "  downloading $repo ..."
            mkdir -p "$dest"
            ( cd "$ACE_DIR" && uv run --python 3.12 python -c \
                "from huggingface_hub import snapshot_download; snapshot_download(repo_id='${repo}', local_dir='${dest}')" )
        fi
        if [ -n "$min_gb" ]; then
            size_gb=$(du -sg "$dest" 2>/dev/null | cut -f1)
            if [ -n "$size_gb" ] && [ "$size_gb" -lt "$min_gb" ]; then
                echo "  ⚠️  $dest is ${size_gb}GB; expected at least ${min_gb}GB"
            fi
        fi
    }
    if [ ! -f "$ACE_DIR/checkpoints/.portal5-core-downloaded" ]; then
        ( cd "$ACE_DIR" && uv run --python 3.12 acestep-download )
        mkdir -p "$ACE_DIR/checkpoints"
        touch "$ACE_DIR/checkpoints/.portal5-core-downloaded"
    fi
    _music_snap "ACE-Step/acestep-v15-xl-turbo" "$ACE_DIR/checkpoints/acestep-v15-xl-turbo" 15
    _music_snap "ACE-Step/acestep-5Hz-lm-1.7B" "$ACE_DIR/checkpoints/acestep-5Hz-lm-1.7B" ""
    # The MiniMax fallback weights (~14GB) are only pulled when mlx-audio is
    # installed or the pack already exists; a held-back fallback skips them.
    if "$PY" -c 'import importlib.util; raise SystemExit(0 if importlib.util.find_spec("mlx_audio") else 1)' 2>/dev/null \
        || [ -d "$MUSIC_DIR/minimax-8bit" ]; then
        _music_snap "mlx-community/MiniMax-Music3-8bit" "$MUSIC_DIR/minimax-8bit" ""
    else
        echo "  skipping MiniMax weights download — mlx-audio held back (engine bump required)"
    fi

    echo "  verifying arm64 imports (no audio generation)..."
    "$PY" -c 'import platform; assert platform.machine()=="arm64", platform.machine(); import mlx.core as mx; assert mx.metal.is_available(); import acestep; print("verify-ok", platform.machine())'
    "$PY" -c 'import importlib.util; raise SystemExit(0 if importlib.util.find_spec("mlx_audio") else 1)' \
        || echo "  ⚠️  mlx-audio not installed — MiniMax fallback held back (engine bump required; see KNOWN_LIMITATIONS)"
    test -d "$ACE_DIR/checkpoints/acestep-v15-xl-turbo"

    cat > "$MUSIC_DIR/start.sh" << MUSIC_START
#!/bin/bash
PORTAL_ROOT="${PORTAL_ROOT}"
[ -d "\$PORTAL_ROOT/portal/modules" ] || { echo "ERROR: PORTAL_ROOT invalid; re-run install-music" >&2; exit 1; }
set -a; [ -f "\$PORTAL_ROOT/.env" ] && . "\$PORTAL_ROOT/.env"; set +a
export PYTHONPATH="\$PORTAL_ROOT"
export MUSIC_ACE_ROOT="${ACE_DIR}"
export MUSIC_PYTHON="${PY}"
export MUSIC_MCP_PORT="${MUSIC_PORT}"
export OPENWEBUI_URL="\${OPENWEBUI_URL:-http://localhost:8080}"
exec "${PY}" -m portal.modules.media.tools.music_mcp
MUSIC_START
    chmod +x "$MUSIC_DIR/start.sh"

    PLIST="$HOME/Library/LaunchAgents/com.portal5.music.plist"
    cat > "$PLIST" << PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
    <key>Label</key><string>com.portal5.music</string>
    <key>ProgramArguments</key><array><string>${MUSIC_DIR}/start.sh</string></array>
    <key>RunAtLoad</key><true/><key>KeepAlive</key><true/>
    <key>StandardOutPath</key><string>${MUSIC_LOG}</string>
    <key>StandardErrorPath</key><string>${MUSIC_LOG}</string>
</dict></plist>
PLIST
    launchctl bootout "gui/$(id -u)/com.portal5.music-minimax" 2>/dev/null || true
    launchctl bootout "gui/$(id -u)/com.portal5.music-ace-mcp" 2>/dev/null || true
    launchctl bootout "gui/$(id -u)/com.portal5.acestep-server" 2>/dev/null || true
    _launchd_reload_or_fail com.portal5.music "$PLIST" "http://127.0.0.1:${MUSIC_PORT}/health"
}

_launch_install_mflux() {
    echo "=== Installing MFLUX MCP natively (MLX-native image generation, Apple Silicon) ==="
    ARCH=$(uname -m)
    MX_DIR="$HOME/.portal5/mflux"
    MX_VENV="$MX_DIR/.venv"
    MX_LOG="$HOME/.portal5/logs/mflux.log"
    MX_PORT="${MFLUX_MCP_PORT:-8933}"

    local dry=0
    [ "${1:-}" = "--dry-run" ] && dry=1
    if [ "$ARCH" != "arm64" ]; then
        echo "  ❌ MFLUX requires Apple Silicon (arm64). Detected: $ARCH."
        echo "  There is no CPU/CUDA fallback for this engine."
        exit 1
    fi
    if [ "$dry" -eq 1 ]; then
        _engine_dep_plan mflux "$MX_VENV/bin/python" dry-run
        echo "  dry-run: no venv changes, no pip apply, no launchctl"
        return 0
    fi
    # mflux >=0.24 requires Python >=3.11; the host `python3` may still be 3.10.
    MX_PY="${MFLUX_PYTHON:-}"
    if [ -z "$MX_PY" ]; then
        for cand in python3.13 python3.12 python3.11 python3; do
            command -v "$cand" &>/dev/null || continue
            if "$cand" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)' 2>/dev/null; then
                MX_PY="$cand"; break
            fi
        done
    fi
    [ -n "$MX_PY" ] || {
        echo "  ❌ No Python >=3.11 found (mflux 0.24 requires it)."
        echo "     Install one, e.g.: brew install python@3.12  (or: uv venv --python 3.12)"
        exit 1
    }
    echo "  Using Python: $MX_PY ($("$MX_PY" -c 'import sys; print(".".join(map(str, sys.version_info[:3])))'))"

    mkdir -p "$MX_DIR" "$HOME/.portal5/logs"
    [ -d "$MX_VENV" ] || { echo "  Creating venv..."; "$MX_PY" -m venv "$MX_VENV"; }

    echo "  Installing current deps (mflux, mcp) and non-core sweep fixes..."
    _engine_dep_plan mflux "$MX_VENV/bin/python" apply
    "$MX_VENV/bin/python" -c 'import mflux, PIL; assert tuple(map(int, PIL.__version__.split(".")[:2])) >= (13, 0), f"Pillow {PIL.__version__} < 13 (GHSA-5x8w-8jj5-q52h)"' \
        || { echo "  ❌ mflux 0.24.0 / Pillow>=13.0.0 verification failed"; exit 1; }
    "$MX_VENV/bin/python" -c 'import platform; assert platform.machine() == "arm64"' \
        || { echo "  ❌ venv is not arm64-native"; exit 1; }

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
    _launchd_reload_or_fail com.portal5.mflux "$PLIST" "http://127.0.0.1:${MX_PORT}/health"
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
    # Each family tag must warm through its own entry-point binary — the base
    # mflux-generate dies on non-FLUX.1 tags. Sizes are the upstream bf16 pulls;
    # -q 8 loads the smaller pre-quantized mflux-community repos where they exist.
    MX_PULLS="flux2-klein-4b:mflux-generate-flux2 flux3-image-klein:mflux-generate-flux3 qwen-image-2.1-turbo:mflux-generate-qwen-2.1 z-image-turbo:mflux-generate-z-image-turbo"
    echo "  Pre-pulling MFLUX weights (~15GB klein-4B, ~20GB flux3, ~33GB qwen-2.1, ~21GB z-image)..."
    for pair in ${MFLUX_PULL_MODELS:-$MX_PULLS}; do
        m="${pair%%:*}"; b="${pair##*:}"
        echo "  → $m ($b)"
        "$MX_VENV/bin/$b" --model "$m" --prompt "warmup" --steps 1 \
            --quantize 8 --low-ram --width 512 --height 512 \
            --output "/tmp/mflux_warmup_${m}.png" 2>&1 | tail -3 || true
    done
}

_launch_install_video_mlx() {
    echo "=== Installing Video-MLX MCP natively (LTX-2.5 MLX video generation, Apple Silicon) ==="
    ARCH=$(uname -m)
    VX_DIR="$HOME/.portal5/video-mlx"
    VX_SRC="$VX_DIR/ltx-2-mlx"
    VX_VENV="$VX_SRC/.venv"
    VX_LOG="$HOME/.portal5/logs/video-mlx.log"
    VX_PORT="${VIDEO_MLX_MCP_PORT:-8935}"
    # Opt-in fallback engine (`install-video-mlx wan`): Blaizzy/mlx-video,
    # Wan2.2-TI2V-5B converted to MLX Q8. Silent 720p photoreal output.
    VX_WAN_MODEL="$VX_DIR/wan2.2-ti2v-5b-q8"
    VX_WAN_EXTRAS=""
    local dry=0 wan=0 arg
    for arg in "$@"; do
        case "$arg" in
            --dry-run) dry=1 ;;
            wan) wan=1 ;;
            *) echo "  ❌ unknown install-video-mlx argument: $arg" >&2; exit 1 ;;
        esac
    done

    if [ "$ARCH" != "arm64" ]; then
        echo "  ❌ Video-MLX requires Apple Silicon (arm64). Detected: $ARCH."
        echo "  There is no CPU/CUDA fallback for this engine."
        exit 1
    fi
    if [ "$dry" -eq 1 ]; then
        _engine_dep_plan video "$VX_VENV/bin/python" dry-run "$VX_SRC"
        echo "  dry-run: no clone, no pip apply, no launchctl"
        return 0
    fi
    command -v uv &>/dev/null || { echo "  ❌ uv not found (curl -LsSf https://astral.sh/uv/install.sh | sh)"; exit 1; }
    command -v ffmpeg &>/dev/null || echo "  ⚠️  ffmpeg not found — ltx-2-mlx needs it for video encoding (brew install ffmpeg)"

    mkdir -p "$VX_DIR" "$HOME/.portal5/logs"
    if [ -d "$VX_SRC/.git" ]; then
        # Never `pull`: the checkout is often detached (a symlinked pre-overhaul
        # install), where pull fails and the old `|| true` hid it, leaving a stale
        # engine while reporting success.
        echo "  Updating ltx-2-mlx..."
        git -C "$VX_SRC" fetch --quiet --depth 1 origin || {
            echo "  ❌ git fetch failed in $VX_SRC (network or remote) — refusing to run a partial install" >&2
            exit 1
        }
        git -C "$VX_SRC" checkout --quiet --detach FETCH_HEAD || {
            echo "  ❌ cannot move $VX_SRC to origin's tip — local changes?" >&2
            echo "     Inspect: git -C \"$VX_SRC\" status" >&2
            exit 1
        }
    else
        echo "  Cloning dgrauet/ltx-2-mlx..."; git clone --depth 1 https://github.com/dgrauet/ltx-2-mlx.git "$VX_SRC"
    fi
    echo "  Engine checkout: $VX_SRC -> $(cd "$VX_SRC" && pwd) @ $(git -C "$VX_SRC" rev-parse --short HEAD)"
    if [ -d "$VX_VENV" ]; then
        [ -x "$VX_VENV/bin/python" ] || {
            echo "  ❌ Existing video venv has no usable Python: $VX_VENV/bin/python" >&2
            exit 1
        }
        echo "  Preserving the existing engine venv; the upstream lock seeds new installs only."
    else
        echo "  Seeding the new venv from the upstream lock..."
        ( cd "$VX_SRC" && uv sync --all-extras )
    fi
    _engine_dep_plan video "$VX_VENV/bin/python" apply "$VX_SRC" || {
        echo "  ❌ security dependency upgrade failed" >&2; exit 1;
    }
    # `uv sync` strips anything outside the engine's own lock, and a failed late
    # install must not register a launchd job that cannot import.
    [ -x "$VX_VENV/bin/ltx-2-mlx" ] || {
        echo "  ❌ $VX_VENV/bin/ltx-2-mlx missing after uv sync" >&2; exit 1; }
    "$VX_VENV/bin/python" -c "import mcp, starlette" 2>/dev/null || {
        echo "  ❌ the engine venv cannot import mcp/starlette (MCP server deps)" >&2; exit 1; }

    if [ "$wan" -eq 1 ]; then
        echo "  Installing the mlx-video fallback (Wan2.2-TI2V-5B)..."
        ( cd "$VX_SRC" && uv pip install "mlx-video @ git+https://github.com/Blaizzy/mlx-video.git@87db56a51758fefb748a359b90a5283bb8ba4837" ) || {
            echo "  ❌ mlx-video install failed" >&2; exit 1;
        }
        if [ ! -d "$VX_WAN_MODEL" ]; then
            echo "  Downloading Wan2.2-TI2V-5B MLX Q8 (~20GB)..."
            ( cd "$VX_SRC" && "$VX_VENV/bin/huggingface-cli" download \
                "Anes1032/Wan2.2-TI2V-5B-mlx-q8" --local-dir "$VX_WAN_MODEL" ) || {
                echo "  ❌ Wan2.2 pack download failed" >&2; exit 1;
            }
        fi
        VX_WAN_EXTRAS="export VIDEO_MLX_WAN_MODEL_DIR=\"$VX_WAN_MODEL\""
    fi

    cat > "$VX_DIR/start.sh" << VX_START
#!/bin/bash
PORTAL_ROOT="${PORTAL_ROOT}"
[ -d "\$PORTAL_ROOT/portal" ] || { echo "ERROR: PORTAL_ROOT invalid; re-run install-video-mlx" >&2; exit 1; }
set -a; [ -f "\$PORTAL_ROOT/.env" ] && . "\$PORTAL_ROOT/.env"; set +a
export PYTHONPATH="\$PORTAL_ROOT"
# launchd hands a bare PATH — ltx-2-mlx shells out to ffmpeg for muxing.
export PATH="/opt/homebrew/bin:/usr/local/bin:\$PATH"
export VIDEO_MLX_BIN="$VX_VENV/bin/ltx-2-mlx"
export VIDEO_MLX_MCP_PORT="${VX_PORT}"
${VX_WAN_EXTRAS}
[ -n "\${HF_HOME:-}" ] && export HF_HOME
export AI_OUTPUT_DIR="\${AI_OUTPUT_DIR:-\$HOME/AI_Output}"
export OPENWEBUI_URL="\${OPENWEBUI_URL:-http://localhost:8080}"
# One readable line naming the install launchd actually runs, then refuse to
# crash-loop on a missing engine or a venv without the MCP deps.
[ -x "\$VIDEO_MLX_BIN" ] || { echo "ERROR: \$VIDEO_MLX_BIN missing — re-run ./launch.sh install-video-mlx" >&2; exit 1; }
"$VX_VENV/bin/python" -c 'import mcp, starlette' 2>/dev/null || { echo "ERROR: MCP deps missing from $VX_VENV — re-run ./launch.sh install-video-mlx" >&2; exit 1; }
echo "video-mlx: engine=\$VIDEO_MLX_BIN portal=\$PORTAL_ROOT hf_cache=\${HF_HUB_CACHE:-~/.cache/huggingface/hub}"
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
    # `launchctl load` on an already-loaded label is a no-op, so a rewritten
    # start.sh kept the old process running. Re-bootstrap and fail if it is
    # not actually running.
    _launchd_reload_or_fail com.portal5.video-mlx "$PLIST" "http://127.0.0.1:${VX_PORT}/health"
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
    # Same `.env` the launchd service sources — otherwise the pack lands in
    # huggingface_hub's default cache and the service can't see it.
    if [ -f "$ENV_FILE" ]; then
        set -a
        source "$ENV_FILE"
        set +a
    fi
    echo "  Pre-pulling the LTX-2.5 q4 model pack (~51GB)..."
    for m in "${@:-dgrauet/ltx-2.5-mlx-q4}"; do
        echo "  → $m"
        "$VX_VENV/bin/ltx-2-mlx" info --model "$m" 2>&1 | tail -5 || true
    done
}

_launch_pull_asr_models() {
    # The ASR services run with HF_HUB_OFFLINE=1, so this is the only way their
    # weights can appear. Idempotent: cached models are verified, not re-fetched.
    PORTAL_ROOT="${PORTAL_ROOT:-$(pwd)}"
    ASR_PY="$PORTAL_ROOT/.venv/bin/python3"
    if [ ! -x "$ASR_PY" ]; then
        echo "  ❌ Portal venv interpreter missing: $ASR_PY (run: uv sync --all-extras)" >&2
        exit 1
    fi
    if [ -f "$ENV_FILE" ]; then
        set -a
        source "$ENV_FILE"
        set +a
    fi
    echo "=== Fetching MLX ASR models (:8924 Parakeet + Sortformer, :8918 Qwen3-ASR) ==="
    env -u HF_HUB_OFFLINE -u TRANSFORMERS_OFFLINE \
        "$ASR_PY" "$PORTAL_ROOT/scripts/fetch_mlx_asr_models.py" "$@"
}

_launch_start_speech() {
    set -a; source "$ENV_FILE" 2>/dev/null || true; set +a
    local speech_py="$PORTAL_ROOT/.venv/bin/python3"

    if [ "$(uname -m)" != "arm64" ]; then
        echo "  ℹ️  MLX Speech requires Apple Silicon. Docker TTS/ASR services are available as fallback."
        exit 0
    fi

    if [ ! -x "$speech_py" ] || ! "$speech_py" -c "import mlx_audio" &>/dev/null 2>&1; then
        echo "  ❌ mlx-audio not installed in $speech_py. Run: uv sync --extra apple-silicon"
        exit 1
    fi

    mkdir -p "${VOICE_PROFILES_DIR:-$HOME/.portal5/voice_profiles}"
    # Warm the voice-clone weights so the first clone isn't a cold multi-GB download.
    _clone_model="${MLX_CLONE_MODEL:-${MLX_CHATTERBOX_MODEL:-mlx-community/higgs-audio-v2-3B-mlx-q8}}"
    "$speech_py" -c "from mlx_audio.tts.utils import load_model; load_model('${_clone_model}')" >/dev/null 2>&1 \
        && echo "  ✅ Voice-clone model ready (${_clone_model})" \
        || echo "  ⚠️  Voice-clone warmup failed — first clone will cold-load (or run: uv sync --extra apple-silicon)"

    PID_FILE="/tmp/portal-mlx-speech.pid"
    LOG_FILE="$HOME/.portal5/logs/mlx-speech.log"
    mkdir -p "$(dirname "$LOG_FILE")"

    if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
        echo "  ℹ️  MLX Speech already running (PID $(cat "$PID_FILE"))"
        exit 0
    fi

    echo "Starting MLX Speech Server (Kokoro + voice clone + Qwen3-ASR)..."
    nohup "$speech_py" "$PORTAL_ROOT/scripts/mlx-speech.py" >> "$LOG_FILE" 2>&1 &
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

_launch_install_omlx() {
    # Re-render and reload the fixed-path oMLX LaunchAgent. The repo plist is a
    # template: a copied copy runs nothing at the next login.
    if [ "$(uname)" != "Darwin" ] || [ "$(uname -m)" != "arm64" ]; then
        echo "  ℹ️  The oMLX LaunchAgent is macOS / Apple Silicon only."
        exit 0
    fi
    local label="com.portal5.omlx"
    local src="$PORTAL_ROOT/deploy/launchd/${label}.plist"
    local dst="$HOME/Library/LaunchAgents/${label}.plist"
    local domain="gui/$(id -u)"
    local venv
    venv="$(_omlx_venv_path)"
    if [ ! -f "$src" ]; then
        echo "  ❌ Missing: $src"
        exit 1
    fi
    if [ ! -x "$venv/bin/python" ]; then
        echo "  ❌ oMLX venv interpreter missing: $venv/bin/python"
        echo "     install it with: uv run python scripts/omlx_venv_install.py"
        exit 1
    fi

    mkdir -p "$HOME/Library/LaunchAgents"
    local previous=""
    if [ -f "$dst" ]; then
        previous="$(mktemp "${TMPDIR:-/tmp}/portal5-plist-previous.XXXXXX")"
        cp -f "$dst" "$previous"
    fi
    if ! _render_launchd_plist "$src" "$dst"; then
        rm -f "$previous"
        echo "  ❌ Could not render $src — a placeholder has no substitution"
        exit 1
    fi
    if ! plutil -lint "$dst" >/dev/null; then
        rm -f "$previous"
        echo "  ❌ Rendered plist failed plutil -lint: $dst"
        exit 1
    fi
    # /health answers 503 until oMLX's pinned-model preload finishes; wait long
    # enough that a slow preload is not mistaken for a failed install.
    if ! _launchd_reload_job "$label" "$dst" "$domain" \
        "http://127.0.0.1:8085/health" "$previous" 180; then
        rm -f "$previous"
        echo "  ❌ oMLX LaunchAgent install failed — log: /opt/homebrew/var/log/omlx.log"
        exit 1
    fi
    rm -f "$previous"
    echo "[portal-5] ✅ oMLX LaunchAgent rendered, loaded and answering: ${dst}"
    echo "  Venv:   ${venv}"
    echo "  Health: curl -fsS http://127.0.0.1:8085/health"
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
    SCRIPT_DST="/usr/local/libexec/portal5-powermetrics"
    PLIST_DST="/Library/LaunchDaemons/com.portal5.powermetrics.plist"
    PM_LABEL="com.portal5.powermetrics"

    if [ ! -f "$SCRIPT_SRC" ]; then
        echo "  ❌ Missing: $SCRIPT_SRC"
        exit 1
    fi
    if [ ! -x "/usr/bin/python3" ]; then
        echo "  ❌ System Python missing: /usr/bin/python3"
        exit 1
    fi
    PLIST_RENDERED="$(mktemp "${TMPDIR:-/tmp}/portal5-plist.XXXXXX")"
    if ! _render_launchd_plist "$PLIST_SRC" "$PLIST_RENDERED" \
        || ! plutil -lint "$PLIST_RENDERED" >/dev/null; then
        rm -f "$PLIST_RENDERED"
        echo "  ❌ Could not render a valid plist from $PLIST_SRC"
        exit 1
    fi

    echo "[portal-5] Installing powermetrics daemon (requires sudo)..."
    PREVIOUS_PLIST=""
    if [ -f "$PLIST_DST" ]; then
        PREVIOUS_PLIST="$(mktemp "${TMPDIR:-/tmp}/portal5-plist-previous.XXXXXX")"
        cp -f "$PLIST_DST" "$PREVIOUS_PLIST"
    fi
    sudo install -d -o root -g wheel -m 0755 /usr/local/libexec || {
        rm -f "$PLIST_RENDERED" "$PREVIOUS_PLIST"
        echo "  ❌ Failed to secure /usr/local/libexec"
        exit 1
    }
    sudo install -o root -g wheel -m 0755 "$SCRIPT_SRC" "$SCRIPT_DST" || {
        rm -f "$PLIST_RENDERED" "$PREVIOUS_PLIST"
        echo "  ❌ Failed to install daemon script"
        exit 1
    }
    sudo install -o root -g wheel -m 0644 "$PLIST_RENDERED" "$PLIST_DST" || {
        rm -f "$PLIST_RENDERED" "$PREVIOUS_PLIST"
        echo "  ❌ Failed to install plist"
        exit 1
    }
    if ! cmp -s "$PLIST_RENDERED" "$PLIST_DST"; then
        rm -f "$PLIST_RENDERED" "$PREVIOUS_PLIST"
        echo "  ❌ Installed plist does not match the rendered repo copy"
        exit 1
    fi
    rm -f "$PLIST_RENDERED"
    if ! _launchd_reload_job "$PM_LABEL" "$PLIST_DST" system "" "$PREVIOUS_PLIST"; then
        rm -f "$PREVIOUS_PLIST"
        echo "  ❌ Powermetrics install failed — check: sudo launchctl print system/${PM_LABEL}"
        exit 1
    fi
    rm -f "$PREVIOUS_PLIST"

    # A pre-a55e73caf install ran the repo copy from /usr/local/bin. It must not
    # linger: a stale process would also answer the readiness probe below.
    LEGACY_AGENT="$HOME/Library/LaunchAgents/com.portal5.powermetrics.plist"
    if [ -f "$LEGACY_AGENT" ]; then
        launchctl bootout "gui/$(id -u)/com.portal5.powermetrics" 2>/dev/null || true
        rm -f "$LEGACY_AGENT"
        echo "  Removed legacy user agent: $LEGACY_AGENT"
    fi
    if [ -f "/usr/local/bin/portal5-powermetrics" ]; then
        sudo rm -f "/usr/local/bin/portal5-powermetrics"
        echo "  Removed legacy script: /usr/local/bin/portal5-powermetrics"
    fi

    # Readiness, not a ps pattern: launchd starts the job a few seconds after
    # bootstrap, and /usr/bin/python3 re-execs into the Xcode interpreter before
    # the script path appears; the daemon then sleeps 12s before binding the socket.
    if _unix_socket_answering "/tmp/portal5-powermetrics.sock" 45; then
        echo "[portal-5] ✅ Powermetrics daemon installed and answering"
    else
        echo "  ❌ Powermetrics daemon is loaded but its socket is not answering — check:"
        echo "     sudo launchctl print system/${PM_LABEL}"
        echo "     tail -20 /var/log/portal5-powermetrics.err"
        exit 1
    fi
    echo "  Script: $SCRIPT_DST"
    echo "  Python: /usr/bin/python3"
    echo "  Plist:  $PLIST_DST"
    echo "  Socket: /tmp/portal5-powermetrics.sock"
    echo "  Status: sudo launchctl print system/${PM_LABEL}"
    echo "  Uninstall: $(_portal5_root uninstall-powermetrics 'sudo ./launch.sh uninstall-powermetrics')"
}

_launch_uninstall_powermetrics() {
    PLIST_DST="/Library/LaunchDaemons/com.portal5.powermetrics.plist"
    SCRIPT_DST="/usr/local/libexec/portal5-powermetrics"
    echo "[portal-5] Uninstalling powermetrics daemon (requires sudo)..."
    sudo launchctl unload "$PLIST_DST" 2>/dev/null || true
    sudo rm -f "$PLIST_DST" "$SCRIPT_DST" "/usr/local/bin/portal5-powermetrics"
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
    TR_PY="$PORTAL_ROOT/.venv/bin/python3"
    if [ ! -x "$TR_PY" ]; then
      echo "❌ Portal venv interpreter missing: $TR_PY"
      exit 1
    fi
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


# ── Unattended arm queue runner (com.portal5.arm-queue launchd agent) ─────────
_launch_arm_queue_tasks_dir() {
    local py="$PORTAL_ROOT/.venv/bin/python"
    local dir=""
    if [ -x "$py" ]; then
        dir="$("$py" -c 'from portal.platform.mcp_host.workspace import get_generated_dir; print(get_generated_dir("tasks"))' 2>/dev/null || true)"
    fi
    echo "${dir:-${AI_OUTPUT_DIR:-$HOME/AI_Output}/generated/tasks}"
}

_launch_install_arm_queue() {
    if [ "$(uname -s)" != "Darwin" ]; then
        echo "  ❌ com.portal5.arm-queue is a macOS launchd agent"
        exit 1
    fi
    local label="com.portal5.arm-queue"
    local src="$PORTAL_ROOT/deploy/launchd/${label}.plist"
    local dst="$HOME/Library/LaunchAgents/${label}.plist"
    local domain="gui/$(id -u)"
    local tasks_dir
    if [ ! -f "$src" ]; then
        echo "  ❌ missing $src"
        exit 1
    fi
    command -v uv &>/dev/null || { echo "  ❌ uv not found (https://docs.astral.sh/uv/)"; exit 1; }
    tasks_dir="$(_launch_arm_queue_tasks_dir)"
    mkdir -p "$tasks_dir" "$HOME/Library/LaunchAgents"
    local previous=""
    if [ -f "$dst" ]; then
        previous="$(mktemp "${TMPDIR:-/tmp}/portal5-plist-previous.XXXXXX")"
        cp -f "$dst" "$previous"
    fi
    # launchd's PATH is minimal: put the uv found here first, or the agent (and every
    # `uv run` job step) exits 127 (10-30 first start).
    sed -e "s#__PORTAL_ROOT__#${PORTAL_ROOT}#g" \
        -e "s#__LOG_DIR__#${tasks_dir}#g" \
        -e "s#__UV_DIR__#$(dirname "$(command -v uv)")#g" \
        "$src" > "$dst"
    if ! plutil -lint "$dst" >/dev/null; then
        rm -f "$previous"
        echo "  ❌ rendered plist failed lint: $dst"
        exit 1
    fi
    if ! _launchd_reload_job "$label" "$dst" "$domain" "" "$previous"; then
        rm -f "$previous"
        echo "[portal-5] ⚠️  arm queue runner install failed — see ${tasks_dir}/arm-queue.launchd.log"
        return 1
    fi
    rm -f "$previous"
    echo "[portal-5] ✅ arm queue runner installed (${label}), polling every 60s"
    echo "[portal-5]    runner log: ${tasks_dir}/arm-queue.launchd.log"
    echo "[portal-5]    stop for maintenance: ./launch.sh uninstall-arm-queue"
}

_launch_uninstall_arm_queue() {
    local label="com.portal5.arm-queue"
    local domain="gui/$(id -u)"
    if launchctl print "${domain}/${label}" &>/dev/null 2>&1; then
        launchctl bootout "${domain}/${label}" 2>/dev/null || true
        echo "[portal-5] ✅ arm queue runner stopped (${label})"
        echo "[portal-5]    a job mid-step is adopted when the runner returns"
    else
        echo "[portal-5] arm queue runner was not loaded"
    fi
    rm -f "$HOME/Library/LaunchAgents/${label}.plist"
    echo "[portal-5]    restart it with ./launch.sh install-arm-queue"
}

# Compose services that build a Portal image, derived from docker-compose.yml so a new service
# is rebuilt without anyone editing a list (10-30: a hand-kept list left the Telegram bot on an
# old build). Run from $COMPOSE_DIR with the env loaded. Always excluded: open-webui (updated
# only behind backup + health gate by scripts/image_security_update.py) and dind (restarting it
# kills live sandbox runs). Profile services (channel bots) count only when their container
# is running (a rebuild never starts a stopped bot). --mcp keeps just the MCP servers.
_compose_built_services() {
    local mode="${1:-all}"
    docker compose --profile '*' config --format json 2>/dev/null | MODE="$mode" python3 -c '
import json, os, subprocess, sys
services = json.load(sys.stdin)["services"]
existing = set(subprocess.run(["docker", "ps", "--format", "{{.Names}}"],
                              capture_output=True, text=True).stdout.split())
out = []
for name, spec in sorted(services.items()):
    if "build" not in spec or name in {"open-webui", "dind"}:
        continue
    if spec.get("profiles") and spec.get("container_name", name) not in existing:
        continue
    if os.environ["MODE"] == "--mcp" and (name == "portal-pipeline" or spec.get("profiles")):
        continue
    out.append(name)
print(" ".join(out))
'
}
