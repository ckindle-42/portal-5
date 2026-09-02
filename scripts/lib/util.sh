#!/usr/bin/env bash
# util.sh — Portal 5 utility functions (sourced by launch.sh)
# shellcheck shell=bash

# ── JSON parsing helper ────────────────────────────────────────────────────────
# Prefer jq (faster), fall back to python3 if unavailable.
if command -v jq &>/dev/null; then
    _USE_JQ=true
else
    _USE_JQ=false
fi

OLLAMA_MIN_VERSION="0.32.4"

_version_at_least() {
    local have="$1" need="$2"
    local have_major have_minor have_patch need_major need_minor need_patch
    IFS=. read -r have_major have_minor have_patch <<< "$have"
    IFS=. read -r need_major need_minor need_patch <<< "$need"
    have_major=${have_major:-0}; have_minor=${have_minor:-0}; have_patch=${have_patch:-0}
    need_major=${need_major:-0}; need_minor=${need_minor:-0}; need_patch=${need_patch:-0}
    [ "$have_major" -gt "$need_major" ] ||
        { [ "$have_major" -eq "$need_major" ] && [ "$have_minor" -gt "$need_minor" ]; } ||
        { [ "$have_major" -eq "$need_major" ] && [ "$have_minor" -eq "$need_minor" ] &&
          [ "$have_patch" -ge "$need_patch" ]; }
}

# Usage: _jq_get <json_string> <jq_filter> <python_fallback_expr> [default]
# Example: _jq_get "$JSON" '.status // "?"' "d.get('status','?')"
_json_get() {
    local json="$1" jq_filter="$2" py_expr="$3" default="${4:-}"
    if $_USE_JQ; then
        echo "$json" | jq -r "$jq_filter" 2>/dev/null || echo "${default}"
    else
        echo "$json" | python3 -c "import json,sys; d=json.load(sys.stdin); print($py_expr)" 2>/dev/null || echo "${default}"
    fi
}

# ── Secret generation ─────────────────────────────────────────────────────────
generate_secret() {
    # Works on macOS (LibreSSL) and Linux (OpenSSL)
    openssl rand -base64 32 | tr -d '/+=' | head -c 43
}

# ── Hardware check ──────────────────────────────────────────────────────────
_check_hardware() {
    echo "[portal-5] Checking system requirements..."
    WARN=0

    # RAM check (need ≥16GB, warn below 32GB for full model catalog)
    # Cross-platform: /proc/meminfo on Linux, sysctl on macOS
    RAM_GB=0
    if [ "$(uname -s)" = "Darwin" ]; then
        # macOS
        MEM_BYTES=$(sysctl -n hw.memsize 2>/dev/null || echo 0)
        RAM_GB=$(( MEM_BYTES / 1024 / 1024 / 1024 ))
    elif [ -f /proc/meminfo ]; then
        # Linux
        MEM_KB=$(awk '/MemTotal/ {print $2}' /proc/meminfo 2>/dev/null || echo 0)
        RAM_GB=$(( MEM_KB / 1024 / 1024 ))
    fi

    if [ "$RAM_GB" -lt 16 ] 2>/dev/null; then
        echo "  ⚠️  RAM: ${RAM_GB}GB detected — 16GB minimum required"
        echo "     Portal 5 may crash or fail to load models"
        WARN=1
    elif [ "$RAM_GB" -lt 32 ] 2>/dev/null; then
        echo "  ℹ️  RAM: ${RAM_GB}GB — enough for core models (32GB+ for full catalog)"
    elif [ "$RAM_GB" -gt 0 ]; then
        echo "  ✅ RAM: ${RAM_GB}GB"
    fi

    # Disk check (need ≥20GB free; FLUX alone is ~12GB)
    # Check root filesystem "/" - more reliable than current directory on macOS
    DISK_FREE=$(python3 -c "import shutil; print(shutil.disk_usage('/').free // 1024**3)" 2>/dev/null || \
                df -k / 2>/dev/null | tail -1 | awk '{printf "%d\n", $4/1024/1024}' || \
                echo 0)
    if [ "$DISK_FREE" -lt 20 ] 2>/dev/null; then
        echo "  ⚠️  Disk: ${DISK_FREE}GB free — 20GB minimum (FLUX model is 12GB)"
        echo "     Free up disk space before continuing: docker system prune -a"
        WARN=1
    elif [ "$DISK_FREE" -lt 50 ] 2>/dev/null; then
        echo "  ℹ️  Disk: ${DISK_FREE}GB free — enough for core stack (50GB+ for all models)"
    else
        echo "  ✅ Disk: ${DISK_FREE}GB free"
    fi

    # Docker check (with timeout — Docker Desktop can hang in zombie state)
    local _docker_ok=0
    if command -v timeout &>/dev/null; then
        timeout 5 docker info &>/dev/null && _docker_ok=1
    else
        # macOS has no `timeout` — use bash background process with kill
        ( docker info &>/dev/null ) & local _dpid=$!
        ( sleep 5 && kill -9 $_dpid &>/dev/null ) & local _kpid=$!
        wait $_dpid 2>/dev/null && _docker_ok=1
        kill -9 $_kpid 2>/dev/null; wait $_kpid 2>/dev/null || true
    fi
    if [ "$_docker_ok" -eq 1 ]; then
        echo "  ✅ Docker: running"
    else
        # Check if Docker process exists but is unresponsive (zombie/hung state)
        if pgrep -f "com.docker.backend|Docker.app" &>/dev/null; then
            echo "  ❌ Docker: process running but unresponsive (hung daemon)"
            echo ""
            echo "  This happens when Docker Desktop enters a zombie state."
            echo "  Fix: kill Docker and restart from /Applications"
            echo ""
            printf "  Kill hung Docker processes now? [y/N] "
            read -r confirm
            if [ "$confirm" = "y" ] || [ "$confirm" = "Y" ]; then
                echo "  Killing Docker processes..."
                pkill -f "com.docker.backend" 2>/dev/null || true
                pkill -f "com.docker.driver.amd" 2>/dev/null || true
                pkill -f "com.docker.qemu" 2>/dev/null || true
                pkill -f "com.docker.hyperkit" 2>/dev/null || true
                pkill -f "com.docker.vmnetd" 2>/dev/null || true
                pkill -f "Docker.app" 2>/dev/null || true
                echo "  ✅ Docker processes killed."
                echo ""
                echo "  Now open Docker Desktop from /Applications and wait for it to start."
                echo "  Then run: ./launch.sh up"
                exit 1
            else
                echo "  Aborted. Restart Docker Desktop manually and retry."
                exit 1
            fi
        else
            echo "  ❌ Docker: not running — start Docker Desktop and retry"
            exit 1
        fi
    fi

    # Apple Silicon detection (helpful context)
    ARCH=$(uname -m)
    if [ "$ARCH" = "arm64" ]; then
        echo "  ✅ Platform: Apple Silicon — Metal acceleration available"
        # Version/liveness are read from the live API, not a PATH-resolved
        # `ollama` binary — `command -v ollama` can silently resolve to a
        # stale/wrong install (e.g. Homebrew's, disabled 2026-08-10 for
        # shipping below OLLAMA_MIN_VERSION) while the correct server
        # (com.portal5.ollama LaunchDaemon) is what's actually serving :11434.
        OLLAMA_API_VER=$(curl -s http://localhost:11434/api/version 2>/dev/null | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1)
        if [ -n "$OLLAMA_API_VER" ]; then
            if _version_at_least "$OLLAMA_API_VER" "$OLLAMA_MIN_VERSION"; then
                echo "  ✅ Ollama: native ($OLLAMA_API_VER) — Metal GPU active"
            else
                echo "  ⚠️  Ollama ${OLLAMA_API_VER} is below required ${OLLAMA_MIN_VERSION}"
                echo "     Upgrade the active server before launch; older MLX builds can evict pinned models"
                WARN=1
            fi
        else
            echo "  ⚠️  Ollama not responding on :11434 — restart it:"
            echo "     sudo launchctl kickstart -k system/com.portal5.ollama"
            WARN=1
        fi
        # Image/video generation is host-native MLX now (mflux :8933, video-mlx
        # :8935), managed by their own launchd services — see ./launch.sh
        # install-mflux / install-video-mlx. Not checked here.
    elif [ "$ARCH" = "x86_64" ]; then
        # Check for NVIDIA GPU
        if command -v nvidia-smi &>/dev/null && nvidia-smi -L &>/dev/null 2>&1; then
            GPU=$(nvidia-smi -L 2>/dev/null | head -1 | sed 's/GPU 0: //' | cut -d'(' -f1)
            echo "  ✅ GPU: $GPU (CUDA acceleration available)"
        else
            echo "  ℹ️  GPU: No NVIDIA GPU detected — CPU inference (slower)"
        fi
    fi

    if [ "$WARN" -eq 1 ]; then
        echo ""
        echo "[portal-5] ⚠️  System requirements warning — see above"
        echo "           Press Enter to continue anyway, or Ctrl+C to abort"
        read -r _
    fi
}

# ── Durable host-native MCP supervision ──────────────────────────────────────
_ensure_native_mcp_service() {
    local service="$1" label="$2" port="$3" log_name="$4"
    local wrapper="$PORTAL_ROOT/scripts/native-mcp-service.sh"
    local log_dir="$HOME/.portal5/logs"
    local pid_file="/tmp/portal-${service}.pid"

    if curl -fsS "http://localhost:${port}/health" &>/dev/null 2>&1; then
        echo "[portal-5]   ✅ ${service}: running on :${port}"
        return 0
    fi

    mkdir -p "$log_dir"
    chmod +x "$wrapper"

    if [ "$(uname -s)" = "Darwin" ]; then
        local agent_dir="$HOME/Library/LaunchAgents"
        local plist="$agent_dir/${label}.plist"
        local domain="gui/$(id -u)"
        mkdir -p "$agent_dir"

        cat > "$plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>${label}</string>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>${wrapper}</string>
        <string>${service}</string>
    </array>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PORTAL_ROOT</key>
        <string>${PORTAL_ROOT}</string>
    </dict>
    <key>WorkingDirectory</key>
    <string>${PORTAL_ROOT}</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>ThrottleInterval</key>
    <integer>10</integer>
    <key>StandardOutPath</key>
    <string>${log_dir}/${log_name}.log</string>
    <key>StandardErrorPath</key>
    <string>${log_dir}/${log_name}.log</string>
</dict>
</plist>
PLIST

        launchctl bootout "${domain}/${label}" 2>/dev/null || true
        if launchctl bootstrap "$domain" "$plist"; then
            rm -f "$pid_file"
            echo "[portal-5]   ✅ ${service}: launchd supervision enabled on :${port}"
        else
            echo "[portal-5]   ⚠️  ${service}: launchd registration failed; see ${log_dir}/${log_name}.log"
            return 1
        fi
    else
        nohup "$wrapper" "$service" >> "$log_dir/${log_name}.log" 2>&1 &
        echo $! > "$pid_file"
        echo "[portal-5]   ✅ ${service}: started on :${port} (PID $!)"
    fi
}

# ── Auto-start native services if installed but not running ─────────────────
_ensure_native_services() {
    local ARCH
    ARCH=$(uname -m)
    echo "[portal-5] Checking native services..."

    # Native launchers below must use the project's own venv, not a bare
    # `python3` — that resolves to whatever's first on PATH (e.g. Homebrew's
    # global Python), which lacks this project's pinned `mcp`/`portal` deps
    # and makes these services crash-loop silently on import errors.
    local PY="$PORTAL_ROOT/.venv/bin/python3"
    [ -x "$PY" ] || PY="python3"

    # ── Ollama ───────────────────────────────────────────────────────────────
    # Apple Silicon runs the pinned build (`com.portal5.ollama`, a system
    # LaunchDaemon at /Library/LaunchDaemons/) — NOT Homebrew's `ollama`
    # (disabled 2026-08-10, ships below OLLAMA_MIN_VERSION). Detection and
    # restart both go through the LaunchDaemon/API, never `command -v ollama`
    # or `brew services` — PATH can silently resolve to a stale reinstall.
    if [ "$ARCH" = "arm64" ] && [ -f /Library/LaunchDaemons/com.portal5.ollama.plist ]; then
        if ! curl -s http://localhost:11434/api/tags &>/dev/null 2>&1; then
            echo "[portal-5]   Ollama not responding — restarting com.portal5.ollama..."
            sudo -n /bin/launchctl kickstart -k system/com.portal5.ollama &>/dev/null || true
            local retries=10
            while [ "$retries" -gt 0 ]; do
                sleep 1
                if curl -s http://localhost:11434/api/tags &>/dev/null 2>&1; then
                    echo "[portal-5]   ✅ Ollama started"
                    break
                fi
                retries=$((retries - 1))
            done
            if [ "$retries" -eq 0 ]; then
                echo "[portal-5]   ⚠️  Ollama did not respond after 10s — check:"
                echo "[portal-5]      sudo launchctl print system/com.portal5.ollama"
            fi
        else
            echo "[portal-5]   ✅ Ollama: running"
        fi
    elif command -v ollama &>/dev/null; then
        if ! curl -s http://localhost:11434/api/tags &>/dev/null 2>&1; then
            echo "[portal-5]   Ollama installed but not running — starting..."
            # Linux: start as background process
            mkdir -p "$HOME/.portal5/logs"
            OLLAMA_MODELS="${OLLAMA_MODELS:-$HOME/.ollama/models}" nohup ollama serve > "$HOME/.portal5/logs/ollama.log" 2>&1 &
            local retries=10
            while [ "$retries" -gt 0 ]; do
                sleep 1
                if curl -s http://localhost:11434/api/tags &>/dev/null 2>&1; then
                    echo "[portal-5]   ✅ Ollama started"
                    break
                fi
                retries=$((retries - 1))
            done
            if [ "$retries" -eq 0 ]; then
                echo "[portal-5]   ⚠️  Ollama did not respond after 10s"
            fi
        else
            echo "[portal-5]   ✅ Ollama: running"
        fi
    fi

    # ── oMLX inference server (host-native, :8085) ──────────────────────────
    # Peer infra to Ollama: serves the six omlx-* backend groups in
    # config/backends.yaml (Lightning MTP / shadow-shift). Supervised by
    # Homebrew's `homebrew.mxcl.omlx` LaunchAgent, whose KeepAlive only
    # catches a clean exit — not the "process alive but not answering :8085"
    # wedge we have hit in production. So: (1) make sure the brew service is
    # started, (2) install the liveness watchdog LaunchAgent that restarts it
    # on a hang (see scripts/omlx-watchdog.sh).
    if [ "$ARCH" = "arm64" ] && command -v brew &>/dev/null && brew services list 2>/dev/null | grep -q '^omlx'; then
        # oMLX caps every request at settings.json `sampling.max_context_window`
        # regardless of the per-request context — a stale 32768 there silently
        # truncated the auto-coding / laguna / heavy lanes below the context
        # config/portal.yaml grants them (up to 262144). Raise the floor to the
        # fleet's largest declared window; restart only if we actually changed it.
        _omlx_settings="$HOME/.omlx/settings.json"
        if [ -f "$_omlx_settings" ] && python3 - "$_omlx_settings" <<'PY'
import json, sys
FLOOR = 262144
p = sys.argv[1]
d = json.load(open(p))
s = d.setdefault("sampling", {})
changed = False
for k in ("max_context_window", "max_tokens"):
    if int(s.get(k, 0) or 0) < FLOOR:
        s[k] = FLOOR
        changed = True
if changed:
    json.dump(d, open(p, "w"), indent=2)
sys.exit(0 if changed else 1)
PY
        then
            echo "[portal-5]   oMLX settings.json context window raised to 262144 — restarting..."
            brew services restart jundot/omlx/omlx &>/dev/null || true
        fi
        if curl -fsS -m 5 "http://127.0.0.1:8085/v1/models" &>/dev/null 2>&1; then
            echo "[portal-5]   ✅ oMLX: running on :8085"
        else
            echo "[portal-5]   oMLX not answering on :8085 — restarting brew service..."
            brew services restart jundot/omlx/omlx &>/dev/null || true
        fi

        local _omlx_wd_label="com.portal5.omlx-watchdog"
        local _omlx_wd_src="$PORTAL_ROOT/deploy/launchd/${_omlx_wd_label}.plist"
        local _omlx_wd_dst="$HOME/Library/LaunchAgents/${_omlx_wd_label}.plist"
        local _omlx_wd_domain="gui/$(id -u)"
        if [ -f "$_omlx_wd_src" ]; then
            mkdir -p "$HOME/.portal5/logs" "$HOME/Library/LaunchAgents"
            sed -e "s#__PORTAL_ROOT__#${PORTAL_ROOT}#g" \
                -e "s#__LOG_DIR__#${HOME}/.portal5/logs#g" \
                "$_omlx_wd_src" > "$_omlx_wd_dst"
            if ! launchctl print "${_omlx_wd_domain}/${_omlx_wd_label}" &>/dev/null 2>&1; then
                launchctl bootstrap "$_omlx_wd_domain" "$_omlx_wd_dst" &>/dev/null \
                    && echo "[portal-5]   ✅ oMLX watchdog: launchd supervision enabled (120s interval)" \
                    || echo "[portal-5]   ⚠️  oMLX watchdog: launchd registration failed"
            fi
        fi
    fi

    # ── MFLUX image MCP (native MLX on Apple Silicon) ──────────────────────
    if [ "$ARCH" = "arm64" ]; then
        if [ -f "$HOME/.portal5/mflux/.venv/bin/python" ]; then
            if ! curl -s "http://localhost:${MFLUX_MCP_PORT:-8933}/health" &>/dev/null 2>&1; then
                launchctl start com.portal5.mflux 2>/dev/null || true
                echo "[portal-5]   ⏳ MFLUX image MCP starting on :${MFLUX_MCP_PORT:-8933}"
            else
                echo "[portal-5]   ✅ MFLUX image MCP: running"
            fi
        fi
        # video-mlx MCP is supervised by launchd only when the operator has
        # installed it (video module is off by default) — start if present.
        if [ -f "$HOME/.portal5/video-mlx/ltx-2-mlx/.venv/bin/python" ]; then
            curl -s "http://localhost:${VIDEO_MLX_MCP_PORT:-8935}/health" &>/dev/null 2>&1 \
                || launchctl start com.portal5.video-mlx 2>/dev/null || true
        fi
    fi

    # ── MiniMax music MCP (native MLX on Apple Silicon) ─────────────────────
    if [ "$ARCH" = "arm64" ]; then
        if [ -f "$HOME/.portal5/music-minimax/.venv/bin/python" ]; then
            if ! curl -s "http://localhost:${MUSIC_MINIMAX_PORT:-8912}/health" &>/dev/null 2>&1; then
                launchctl start com.portal5.music-minimax 2>/dev/null || true
                echo "[portal-5]   ⏳ MiniMax music MCP starting on :${MUSIC_MINIMAX_PORT:-8912}"
            else
                echo "[portal-5]   ✅ MiniMax music MCP: running"
            fi
        fi
    fi

    # ACE-Step engine and proxy are independently supervised by launchd.
    if [ -f "$HOME/.portal5/music-ace/.venv/bin/python" ]; then
        curl -s "http://localhost:${MUSIC_ACE_MCP_PORT:-8934}/health" &>/dev/null 2>&1 || launchctl start com.portal5.music-ace-mcp 2>/dev/null || true
        curl -s "http://localhost:${ACESTEP_ENGINE_PORT:-8001}/health" &>/dev/null 2>&1 || launchctl start com.portal5.acestep-server 2>/dev/null || true
    fi

    # ── MLX Speech (Apple Silicon native only) ──────────────────────────────
    if [ "$ARCH" = "arm64" ]; then
        if "$PY" -c "import mlx_audio" &>/dev/null 2>&1 &&
            [ -f "$PORTAL_ROOT/scripts/mlx-speech.py" ]; then
            # launchd-supervised like :8924 — the wrapper runs the same drift
            # pre-flight, so the gate is not lost by moving off the bare nohup.
            _ensure_native_mcp_service \
                "mlx-speech" "com.portal5.mlx-speech" \
                "${MLX_SPEECH_PORT:-8918}" "mlx-speech"
        fi
    fi

    # ── MLX Transcribe (Apple Silicon native only) ───────────────────────────
    if [ "$ARCH" = "arm64" ]; then
        if [ -f "$PORTAL_ROOT/scripts/mlx-transcribe.py" ]; then
            _ensure_native_mcp_service \
                "mlx-transcribe" "com.portal5.mlx-transcribe" \
                "${MLX_TRANSCRIBE_PORT:-8924}" "mlx-transcribe"
        fi
    fi

    # ── Pipeline MCP (host-native, :8928) ────────────────────────────────────
    # Exposes get_pipeline_status, list_workspaces, get_loaded_models,
    # explore_repository (FastContext subagent), and get_metrics_summary
    # to coding tools (Claude Code, opencode) via .mcp.json.
    _ensure_native_mcp_service \
        "pipeline-mcp" "com.portal5.pipeline-mcp" \
        "${PIPELINE_MCP_PORT:-8928}" "pipeline-mcp"

    # ── MITRE ATT&CK MCP (host-native, :8929) ────────────────────────────────
    # Reads tests/benchmarks/bench_security/siem/spl_detections.py via a
    # repo-relative sys.path hack — not packaged into Dockerfile.mcp, so this
    # must run against the host checkout rather than as a container.
    _ensure_native_mcp_service \
        "mitre-mcp" "com.portal5.mitre-mcp" \
        "${MITRE_MCP_PORT:-8929}" "mitre-mcp"

    # ── Detections MCP (host-native, :8932) ──────────────────────────────────
    # Same tests/benchmarks/ dependency as MITRE MCP above.
    _ensure_native_mcp_service \
        "detections-mcp" "com.portal5.detections-mcp" \
        "${DETECTIONS_MCP_PORT:-8932}" "detections-mcp"

    # ── Wiki MCP (host-native, :8931) ─────────────────────────────────────────
    # Reads portal_wiki/canonical/ via a repo-relative path and calls Ollama
    # directly for wiki_explain — not packaged into Dockerfile.mcp.
    _ensure_native_mcp_service \
        "wiki-mcp" "com.portal5.wiki-mcp" \
        "${WIKI_MCP_PORT:-8931}" "wiki-mcp"

    # ── Vulnintel MCP (host-native, :8934) ───────────────────────────────────
    # Read-only outbound-HTTPS-only vuln/threat-intel fronting NVD/EPSS/KEV/OSV/
    # CISA ICSA + a clearnet IOC subset. Host-native (stdlib + httpx only, no
    # Dockerfile.mcp deps); all API keys optional.
    _ensure_native_mcp_service \
        "vulnintel-mcp" "com.portal5.vulnintel-mcp" \
        "${VULNINTEL_MCP_PORT:-8934}" "vulnintel-mcp"

    # ── ICS/OT MCP (host-native, :8936) ─────────────────────────────────────
    # Passive read-only ICS protocol dissection (scapy) + ATT&CK-for-ICS
    # correlation. Host-native — scapy lives in the .venv, not Dockerfile.mcp.
    _ensure_native_mcp_service \
        "icsot-mcp" "com.portal5.icsot-mcp" \
        "${ICSOT_MCP_PORT:-8936}" "icsot-mcp"

    # ── Compliance MCP (host-native, :8937) ────────────────────────────────
    # Read-only control-catalog lookup (distilled NIST 800-53 / CSF 2.0 OSCAL)
    # + CIP-007 R2 patch-evidence bridge into vulnintel. Host-native, stdlib.
    _ensure_native_mcp_service \
        "compliance-mcp" "com.portal5.compliance-mcp" \
        "${COMPLIANCE_MCP_PORT:-8937}" "compliance-mcp"

    # ── Detection MCP (host-native, :8938) ─────────────────────────────────
    # pySigma conversion + YARA + promoted read-only lab-scoped SIEM search.
    # Host-native — pySigma/yara live in the .venv; the live tools reuse the
    # security module's SIEM primitives (not packaged into Dockerfile.mcp).
    _ensure_native_mcp_service \
        "detection-mcp" "com.portal5.detection-mcp" \
        "${DETECTION_MCP_PORT:-8938}" "detection-mcp"

    # ── Data MCP (host-native, :8939) ──────────────────────────────────────
    # Sandboxed local DuckDB conversational analytics. Host-native — duckdb
    # lives in the .venv, not Dockerfile.mcp.
    _ensure_native_mcp_service \
        "data-mcp" "com.portal5.data-mcp" \
        "${DATA_MCP_PORT:-8939}" "data-mcp"

    # ── Network Forensics MCP (host-native, :8941) ─────────────────────────
    # Passive tshark PCAP analysis + gated lab-scoped nmap recon. Host-native
    # — shells out to tshark/nmap (brew install wireshark nmap); every tool
    # degrades gracefully when they are absent.
    _ensure_native_mcp_service \
        "netforensics-mcp" "com.portal5.netforensics-mcp" \
        "${NETFORENSICS_MCP_PORT:-8941}" "netforensics-mcp"

    # ── Qwen3-VL retrieval server (host-native, :8942) ─────────────────────
    # The RAG stack's multimodal embed/rerank backend (text+image joint space).
    # Not an MCP — a FastAPI service (scripts/vl-retrieval-server.py) in the
    # project .venv. The shared text embedder :8917 and reranker :8925 stay up
    # for memory / the Bully ORG projection.
    #
    # Runtime (TASK_VL_RUNTIME_LANDING_V4): mlx-embeddings 0.1.0 ships the
    # `qwen3_vl` module; the model loads once transformers 5.x's torchvision-
    # backed `vision` backend is present (torchvision is a declared apple-silicon
    # dep purely to satisfy that class-level import gate — inference runs on the
    # PIL path). Readiness is a *version-aware* check: a bare `import
    # mlx_embeddings` also passes on 0.0.5, which has no VL path, so it is not a
    # sufficient gate. If the check fails the server is NOT started (the `else`
    # branch below only prints a warning); kb_search then gets connection-refused,
    # which rag_multimodal maps to the same plain 503 pointing at /ready.
    _VL_PORT="${VL_PORT:-8942}"
    if ! curl -fsS "http://localhost:${_VL_PORT}/health" &>/dev/null 2>&1; then
        _VL_PY="$PORTAL_ROOT/.venv/bin/python3"
        _VL_READY_CHECK='import importlib.util as u, sys
sys.exit(0 if all(u.find_spec(m) for m in
    ("mlx_embeddings.models.qwen3_vl", "torchvision", "fastapi", "uvicorn")) else 1)'
        if [ -x "$_VL_PY" ] && "$_VL_PY" -c "$_VL_READY_CHECK" &>/dev/null 2>&1; then
            # launchd-supervised: O1's VL_MAX_REQUESTS self-exit assumes a
            # supervisor restarts the process, and the wrapper re-runs the same
            # drift pre-flight the inline branch used to run here.
            _ensure_native_mcp_service \
                "vl-retrieval" "com.portal5.vl-retrieval" \
                "$_VL_PORT" "vl-retrieval"
        else
            echo "[portal-5]   ⚠️  VL retrieval deps missing (need mlx-embeddings>=0.1.0 + torchvision) — RAG multimodal retrieval will 503"
        fi
    fi
}

# ── Teardown helper (shared by 'down' and the pre-start phase of 'up') ────────
_do_down() {
    # ── Stop Docker stack ─────────────────────────────────────────────────
    # --profile telegram/slack must be passed even when those tokens aren't
    # configured: `down` only tears down services in the active profile set,
    # so without these flags the profiled portal-slack/portal-telegram
    # containers are silently left running/exited and orphaned across a
    # Docker daemon restart (stale network reference, fails to start on
    # next `up`). Safe to pass unconditionally — a no-op if absent.
    cd "$COMPOSE_DIR"
    docker compose --profile telegram --profile slack down
    echo "[portal-5] Docker stack stopped."

    # ── Stop native macOS services (MLX image/video, Music MCP, Speech) ──────
    # These run outside Docker and must be stopped explicitly.
    # Uses launchctl if the service is registered, falls back to pkill.
    if [ "$(uname -s)" = "Darwin" ]; then
        # MLX image/video generation MCPs (:8933 / :8935)
        launchctl stop com.portal5.mflux 2>/dev/null || true
        launchctl stop com.portal5.video-mlx 2>/dev/null || true

        launchctl stop com.portal5.music-minimax 2>/dev/null || true
        launchctl stop com.portal5.music-ace-mcp 2>/dev/null || true
        launchctl stop com.portal5.acestep-server 2>/dev/null || true
        echo "[portal-5] Music backends stopped (MiniMax, ACE proxy, ACE engine)."

        # MLX Speech (:8918) — launchd-supervised; the pid-file branch is the
        # pre-supervision fallback for a host that still has one lying around.
        if launchctl print "gui/$(id -u)/com.portal5.mlx-speech" &>/dev/null 2>&1; then
            launchctl bootout "gui/$(id -u)/com.portal5.mlx-speech" 2>/dev/null || true
            rm -f /tmp/portal-mlx-speech.pid
            echo "[portal-5] MLX Speech stopped (launchd)."
        elif [ -f /tmp/portal-mlx-speech.pid ] && kill -0 "$(cat /tmp/portal-mlx-speech.pid)" 2>/dev/null; then
            kill "$(cat /tmp/portal-mlx-speech.pid)" 2>/dev/null || true
            rm -f /tmp/portal-mlx-speech.pid
            echo "[portal-5] MLX Speech stopped."
        else
            echo "[portal-5] MLX Speech: not running (nothing to stop)."
        fi

        # VL retrieval (:8942) — launchd-supervised; KeepAlive must be torn down
        # or it restarts the server the moment we kill it.
        if launchctl print "gui/$(id -u)/com.portal5.vl-retrieval" &>/dev/null 2>&1; then
            launchctl bootout "gui/$(id -u)/com.portal5.vl-retrieval" 2>/dev/null || true
            rm -f /tmp/portal-vl-retrieval.pid
            echo "[portal-5] VL retrieval stopped (launchd)."
        elif pgrep -f "scripts/vl-retrieval-server.py" >/dev/null 2>&1; then
            pkill -f "scripts/vl-retrieval-server.py" 2>/dev/null || true
            echo "[portal-5] VL retrieval stopped."
        else
            echo "[portal-5] VL retrieval: not running (nothing to stop)."
        fi

        # MLX Transcribe (:8924)
        if launchctl print "gui/$(id -u)/com.portal5.mlx-transcribe" &>/dev/null 2>&1; then
            launchctl bootout "gui/$(id -u)/com.portal5.mlx-transcribe" 2>/dev/null || true
            rm -f /tmp/portal-mlx-transcribe.pid
            echo "[portal-5] MLX Transcribe stopped (launchd)."
        elif [ -f /tmp/portal-mlx-transcribe.pid ] && kill -0 "$(cat /tmp/portal-mlx-transcribe.pid)" 2>/dev/null; then
            kill "$(cat /tmp/portal-mlx-transcribe.pid)" 2>/dev/null || true
            rm -f /tmp/portal-mlx-transcribe.pid
            echo "[portal-5] MLX Transcribe stopped."
        else
            echo "[portal-5] MLX Transcribe: not running (nothing to stop)."
        fi

        # Pipeline MCP (:8928)
        if launchctl print "gui/$(id -u)/com.portal5.pipeline-mcp" &>/dev/null 2>&1; then
            launchctl bootout "gui/$(id -u)/com.portal5.pipeline-mcp" 2>/dev/null || true
            rm -f /tmp/portal-pipeline-mcp.pid
            echo "[portal-5] Pipeline MCP stopped (launchd)."
        elif [ -f /tmp/portal-pipeline-mcp.pid ] && kill -0 "$(cat /tmp/portal-pipeline-mcp.pid)" 2>/dev/null; then
            kill "$(cat /tmp/portal-pipeline-mcp.pid)" 2>/dev/null || true
            rm -f /tmp/portal-pipeline-mcp.pid
            echo "[portal-5] Pipeline MCP stopped."
        else
            echo "[portal-5] Pipeline MCP: not running (nothing to stop)."
        fi

        # MITRE MCP (:8929)
        if launchctl print "gui/$(id -u)/com.portal5.mitre-mcp" &>/dev/null 2>&1; then
            launchctl bootout "gui/$(id -u)/com.portal5.mitre-mcp" 2>/dev/null || true
            rm -f /tmp/portal-mitre-mcp.pid
            echo "[portal-5] MITRE MCP stopped (launchd)."
        elif [ -f /tmp/portal-mitre-mcp.pid ] && kill -0 "$(cat /tmp/portal-mitre-mcp.pid)" 2>/dev/null; then
            kill "$(cat /tmp/portal-mitre-mcp.pid)" 2>/dev/null || true
            rm -f /tmp/portal-mitre-mcp.pid
            echo "[portal-5] MITRE MCP stopped."
        else
            echo "[portal-5] MITRE MCP: not running (nothing to stop)."
        fi

        # Detections MCP (:8932)
        if launchctl print "gui/$(id -u)/com.portal5.detections-mcp" &>/dev/null 2>&1; then
            launchctl bootout "gui/$(id -u)/com.portal5.detections-mcp" 2>/dev/null || true
            rm -f /tmp/portal-detections-mcp.pid
            echo "[portal-5] Detections MCP stopped (launchd)."
        elif [ -f /tmp/portal-detections-mcp.pid ] && kill -0 "$(cat /tmp/portal-detections-mcp.pid)" 2>/dev/null; then
            kill "$(cat /tmp/portal-detections-mcp.pid)" 2>/dev/null || true
            rm -f /tmp/portal-detections-mcp.pid
            echo "[portal-5] Detections MCP stopped."
        else
            echo "[portal-5] Detections MCP: not running (nothing to stop)."
        fi

        # Wiki MCP (:8931)
        if launchctl print "gui/$(id -u)/com.portal5.wiki-mcp" &>/dev/null 2>&1; then
            launchctl bootout "gui/$(id -u)/com.portal5.wiki-mcp" 2>/dev/null || true
            rm -f /tmp/portal-wiki-mcp.pid
            echo "[portal-5] Wiki MCP stopped (launchd)."
        elif [ -f /tmp/portal-wiki-mcp.pid ] && kill -0 "$(cat /tmp/portal-wiki-mcp.pid)" 2>/dev/null; then
            kill "$(cat /tmp/portal-wiki-mcp.pid)" 2>/dev/null || true
            rm -f /tmp/portal-wiki-mcp.pid
            echo "[portal-5] Wiki MCP stopped."
        else
            echo "[portal-5] Wiki MCP: not running (nothing to stop)."
        fi

        # Vulnintel MCP (:8934)
        if launchctl print "gui/$(id -u)/com.portal5.vulnintel-mcp" &>/dev/null 2>&1; then
            launchctl bootout "gui/$(id -u)/com.portal5.vulnintel-mcp" 2>/dev/null || true
            rm -f /tmp/portal-vulnintel-mcp.pid
            echo "[portal-5] Vulnintel MCP stopped (launchd)."
        elif [ -f /tmp/portal-vulnintel-mcp.pid ] && kill -0 "$(cat /tmp/portal-vulnintel-mcp.pid)" 2>/dev/null; then
            kill "$(cat /tmp/portal-vulnintel-mcp.pid)" 2>/dev/null || true
            rm -f /tmp/portal-vulnintel-mcp.pid
            echo "[portal-5] Vulnintel MCP stopped."
        else
            echo "[portal-5] Vulnintel MCP: not running (nothing to stop)."
        fi

        # ICS/OT MCP (:8936)
        if launchctl print "gui/$(id -u)/com.portal5.icsot-mcp" &>/dev/null 2>&1; then
            launchctl bootout "gui/$(id -u)/com.portal5.icsot-mcp" 2>/dev/null || true
            rm -f /tmp/portal-icsot-mcp.pid
            echo "[portal-5] ICS/OT MCP stopped (launchd)."
        elif [ -f /tmp/portal-icsot-mcp.pid ] && kill -0 "$(cat /tmp/portal-icsot-mcp.pid)" 2>/dev/null; then
            kill "$(cat /tmp/portal-icsot-mcp.pid)" 2>/dev/null || true
            rm -f /tmp/portal-icsot-mcp.pid
            echo "[portal-5] ICS/OT MCP stopped."
        else
            echo "[portal-5] ICS/OT MCP: not running (nothing to stop)."
        fi

        # Compliance MCP (:8937)
        if launchctl print "gui/$(id -u)/com.portal5.compliance-mcp" &>/dev/null 2>&1; then
            launchctl bootout "gui/$(id -u)/com.portal5.compliance-mcp" 2>/dev/null || true
            rm -f /tmp/portal-compliance-mcp.pid
            echo "[portal-5] Compliance MCP stopped (launchd)."
        elif [ -f /tmp/portal-compliance-mcp.pid ] && kill -0 "$(cat /tmp/portal-compliance-mcp.pid)" 2>/dev/null; then
            kill "$(cat /tmp/portal-compliance-mcp.pid)" 2>/dev/null || true
            rm -f /tmp/portal-compliance-mcp.pid
            echo "[portal-5] Compliance MCP stopped."
        else
            echo "[portal-5] Compliance MCP: not running (nothing to stop)."
        fi

        # Detection MCP (:8938)
        if launchctl print "gui/$(id -u)/com.portal5.detection-mcp" &>/dev/null 2>&1; then
            launchctl bootout "gui/$(id -u)/com.portal5.detection-mcp" 2>/dev/null || true
            rm -f /tmp/portal-detection-mcp.pid
            echo "[portal-5] Detection MCP stopped (launchd)."
        elif [ -f /tmp/portal-detection-mcp.pid ] && kill -0 "$(cat /tmp/portal-detection-mcp.pid)" 2>/dev/null; then
            kill "$(cat /tmp/portal-detection-mcp.pid)" 2>/dev/null || true
            rm -f /tmp/portal-detection-mcp.pid
            echo "[portal-5] Detection MCP stopped."
        else
            echo "[portal-5] Detection MCP: not running (nothing to stop)."
        fi

        # Data MCP (:8939)
        if launchctl print "gui/$(id -u)/com.portal5.data-mcp" &>/dev/null 2>&1; then
            launchctl bootout "gui/$(id -u)/com.portal5.data-mcp" 2>/dev/null || true
            rm -f /tmp/portal-data-mcp.pid
            echo "[portal-5] Data MCP stopped (launchd)."
        elif [ -f /tmp/portal-data-mcp.pid ] && kill -0 "$(cat /tmp/portal-data-mcp.pid)" 2>/dev/null; then
            kill "$(cat /tmp/portal-data-mcp.pid)" 2>/dev/null || true
            rm -f /tmp/portal-data-mcp.pid
            echo "[portal-5] Data MCP stopped."
        else
            echo "[portal-5] Data MCP: not running (nothing to stop)."
        fi

        # Network Forensics MCP (:8941)
        if launchctl print "gui/$(id -u)/com.portal5.netforensics-mcp" &>/dev/null 2>&1; then
            launchctl bootout "gui/$(id -u)/com.portal5.netforensics-mcp" 2>/dev/null || true
            rm -f /tmp/portal-netforensics-mcp.pid
            echo "[portal-5] Network Forensics MCP stopped (launchd)."
        elif [ -f /tmp/portal-netforensics-mcp.pid ] && kill -0 "$(cat /tmp/portal-netforensics-mcp.pid)" 2>/dev/null; then
            kill "$(cat /tmp/portal-netforensics-mcp.pid)" 2>/dev/null || true
            rm -f /tmp/portal-netforensics-mcp.pid
            echo "[portal-5] Network Forensics MCP stopped."
        else
            echo "[portal-5] Network Forensics MCP: not running (nothing to stop)."
        fi

        # ARM64 embedding server (:8917)
        # launchd-managed: leave the service running (it manages its own lifecycle),
        # just print a note so the operator knows it's still up.
        if launchctl list com.portal5.embedding 2>/dev/null | grep -q '"PID"'; then
            echo "[portal-5] Embedding server: still running (launchd-managed — use './launch.sh uninstall-embedding-service' to stop permanently)."
        elif [ -f /tmp/portal-embedding-arm.pid ] && kill -0 "$(cat /tmp/portal-embedding-arm.pid)" 2>/dev/null; then
            kill "$(cat /tmp/portal-embedding-arm.pid)" 2>/dev/null || true
            rm -f /tmp/portal-embedding-arm.pid
            echo "[portal-5] ARM64 embedding server stopped."
        else
            echo "[portal-5] Embedding server: not running (nothing to stop)."
        fi
    fi
}

# ── Port pre-flight check ───────────────────────────────────────────────────
_check_ports() {
    echo "[portal-5] Checking for port conflicts..."
    local FAILED=0

    # Check if a port is in use. Prints owning process if found.
    # Usage: _port_check <port> <service_name> [skip_if_profile_absent]
    _port_check() {
        local port="$1"
        local name="$2"
        local in_use=0

        # Primary check: try connecting
        if command -v nc &>/dev/null; then
            nc -z 127.0.0.1 "$port" 2>/dev/null && in_use=1
        else
            # bash built-in /dev/tcp fallback — works without nc
            (echo >/dev/tcp/127.0.0.1/"$port") 2>/dev/null && in_use=1 || true
        fi

        if [ "$in_use" -eq 1 ]; then
            echo "  ❌ Port $port ($name) is already in use"
            # Show which process owns it
            if command -v lsof &>/dev/null; then
                local owner
                owner=$(lsof -ti :"$port" 2>/dev/null | head -1)
                if [ -n "$owner" ]; then
                    local proc
                    proc=$(ps -p "$owner" -o comm= 2>/dev/null || echo "PID $owner")
                    echo "     └─ Owned by: $proc (PID $owner)"
                    echo "     └─ To free:  kill $owner"
                fi
            elif command -v ss &>/dev/null; then
                ss -tlnp "sport = :$port" 2>/dev/null | tail -1 | awk '{print "     └─ " $0}'
            fi
            FAILED=1
        else
            echo "  ✅ Port $port ($name) is free"
        fi
    }

    # Core services — always checked
    _port_check 8080  "Open WebUI"
    _port_check 9099  "Portal Pipeline"
    _port_check 8088  "SearXNG"
    _port_check 9090  "Prometheus"
    _port_check 3000  "Grafana"

    # MCP servers — use env overrides if set
    _port_check "${DOCUMENTS_HOST_PORT:-8913}"  "MCP Documents"
    # Music MCP runs natively on macOS — skip Docker port conflict check
    if [ "$(uname -m)" != "arm64" ]; then
        _port_check "${MUSIC_MINIMAX_PORT:-8912}"  "MCP Music MiniMax"
    fi
    _port_check "${TTS_HOST_PORT:-8916}"        "MCP TTS"
    _port_check "${WHISPER_HOST_PORT:-8915}"    "MCP Whisper"
    _port_check "${SANDBOX_HOST_PORT:-8914}"    "MCP Sandbox"
    # MLX image/video MCPs run host-native under launchd when installed, and
    # `up` starts them (via _ensure_native_services) *before* this check runs —
    # so a healthy /health response means it's our own service, not a squatter.
    if [ -f "$HOME/.portal5/mflux/.venv/bin/python" ]; then
        if curl -s "http://localhost:${MFLUX_MCP_PORT:-8933}/health" &>/dev/null 2>&1; then
            echo "  ✅ Port ${MFLUX_MCP_PORT:-8933} (MCP MFLUX (image)) — launchd-managed native server"
        else
            _port_check "${MFLUX_MCP_PORT:-8933}" "MCP MFLUX (image)"
        fi
    fi
    if [ -f "$HOME/.portal5/video-mlx/ltx-2-mlx/.venv/bin/python" ]; then
        if curl -s "http://localhost:${VIDEO_MLX_MCP_PORT:-8935}/health" &>/dev/null 2>&1; then
            echo "  ✅ Port ${VIDEO_MLX_MCP_PORT:-8935} (MCP video-mlx) — launchd-managed native server"
        else
            _port_check "${VIDEO_MLX_MCP_PORT:-8935}" "MCP video-mlx"
        fi
    fi
    # On ARM64 the native embedding server is launchd-managed and intentionally
    # owns this port — skip the conflict check when it's our own service.
    if [ "$(uname -m)" = "arm64" ] && launchctl list com.portal5.embedding 2>/dev/null | grep -q '"PID"'; then
        echo "  ✅ Port ${EMBEDDING_HOST_PORT:-8917} (MCP Embedding) — launchd-managed native server"
    else
        _port_check "${EMBEDDING_HOST_PORT:-8917}"  "MCP Embedding"
    fi
    _port_check "${SECURITY_HOST_PORT:-8919}"   "MCP Security"

    # MLX Speech (port 8918) — only check if installed
    if python3 -c "import mlx_audio" &>/dev/null 2>&1; then
        if curl -s "http://localhost:8918/health" &>/dev/null 2>&1; then
            echo "  ✅ Port 8918 (MLX Speech) — already responding"
        else
            _port_check 8918   "MLX Speech (Qwen3-TTS + Qwen3-ASR)"
        fi
    fi

    # Ollama (Docker profile) — only check if explicitly using docker-ollama
    # Native Ollama on 11434 is expected and correct for the default setup
    if echo "${COMPOSE_PROFILES:-}" | grep -q "docker-ollama"; then
        _port_check 11434 "Ollama (Docker profile — conflicts with native Ollama)"
    fi

    if [ "$FAILED" -eq 1 ]; then
        echo ""
        echo "[portal-5] ❌ Port conflict(s) detected — cannot start safely."
        echo ""
        echo "  Options:"
        echo "  1. Stop the conflicting process (see 'kill <PID>' above)"
        echo "  2. If it's a previous Portal 5 stack:  ./launch.sh down"
        echo "     Note: 'down' also stops native Speech (:8918) and the MLX image/video MCPs"
        echo "  3. If it's a different service, override the port in .env:"
        echo "     e.g.:  DOCUMENTS_HOST_PORT=9013  (for MCP Documents)"
        echo "     All overrideable ports are documented in .env.example"
        echo ""
        exit 1
    fi

    echo "[portal-5] ✅ All ports are free."
}

# ── First-run bootstrap ───────────────────────────────────────────────────────
bootstrap_secrets() {
    local env_file="$1"
    local changed=0

    # Replace CHANGEME placeholders with generated secrets
    local tmp
    tmp=$(mktemp)
    cp "$env_file" "$tmp"

    if grep -q "^PIPELINE_API_KEY=CHANGEME" "$tmp"; then
        local key; key=$(generate_secret)
        sed -i.bak "s|^PIPELINE_API_KEY=CHANGEME|PIPELINE_API_KEY=$key|" "$tmp"
        echo "[portal-5] Generated PIPELINE_API_KEY"
        changed=1
    fi

    if grep -qE "^WEBUI_SECRET_KEY=CHANGEME(-AUTOGEN)?$" "$tmp"; then
        local key; key=$(generate_secret)
        sed -i.bak "s|^WEBUI_SECRET_KEY=CHANGEME.*|WEBUI_SECRET_KEY=$key|" "$tmp"
        echo "[portal-5] Generated WEBUI_SECRET_KEY"
        changed=1
    fi

    if grep -q "^OPENWEBUI_ADMIN_PASSWORD=CHANGEME" "$tmp"; then
        local pass; pass=$(generate_secret)
        sed -i.bak "s|^OPENWEBUI_ADMIN_PASSWORD=CHANGEME|OPENWEBUI_ADMIN_PASSWORD=$pass|" "$tmp"
        echo "[portal-5] Generated OPENWEBUI_ADMIN_PASSWORD"
        echo ""
        echo "  ╔══════════════════════════════════════════════════════╗"
        echo "  ║  First-run credentials (save these now)              ║"
        echo "  ║                                                      ║"
        echo "  ║  Open WebUI: http://localhost:8080                   ║"
        printf "  ║  Email:    %-41s ║\n" "$(grep "^OPENWEBUI_ADMIN_EMAIL=" "$tmp" | cut -d= -f2)"
        printf "  ║  Password: %-41s ║\n" "$pass"
        echo "  ╚══════════════════════════════════════════════════════╝"
        echo ""
        changed=1
    fi

    if grep -q "^SEARXNG_SECRET_KEY=CHANGEME" "$tmp"; then
        local key; key=$(generate_secret)
        sed -i.bak "s|^SEARXNG_SECRET_KEY=CHANGEME|SEARXNG_SECRET_KEY=$key|" "$tmp"
        echo "[portal-5] Generated SEARXNG_SECRET_KEY"
        changed=1
    fi

    if grep -q "^GRAFANA_PASSWORD=CHANGEME" "$tmp"; then
        local key; key=$(generate_secret | head -c 20)
        sed -i.bak "s|^GRAFANA_PASSWORD=CHANGEME|GRAFANA_PASSWORD=$key|" "$tmp"
        echo "[portal-5] Generated GRAFANA_PASSWORD"
        changed=1
    fi

    # Clean up sed backup files
    rm -f "${tmp}.bak"

    if [ $changed -eq 1 ]; then
        cp "$tmp" "$env_file"
        echo "[portal-5] Secrets written to .env"
    fi
    rm -f "$tmp"
}

# ── Admin API token helper ────────────────────────────────────────────────────
get_admin_token() {
    # Returns a JWT token for the admin account
    # Reads credentials from .env
    local url="${OPENWEBUI_URL:-http://localhost:8080}"
    local email="${OPENWEBUI_ADMIN_EMAIL:-admin@portal.local}"
    local pass="${OPENWEBUI_ADMIN_PASSWORD:-}"

    if [ -z "$pass" ]; then
        echo "ERROR: OPENWEBUI_ADMIN_PASSWORD not set in .env" >&2
        exit 1
    fi

    local _auth_json
    _auth_json=$(curl -s -X POST "$url/api/v1/auths/signin" \
        -H "Content-Type: application/json" \
        -d "{\"email\":\"$email\",\"password\":\"$pass\"}" \
        2>/dev/null)
    _json_get "$_auth_json" '.token // ""' "d.get('token','')" ""
}

# ── Status display ─────────────────────────────────────────────────────────
_cmd_status() {
    local ARCH
    ARCH=$(uname -m)

    _svc_icon() {
        case "$1" in
            healthy)  echo "✅" ;;
            running)  echo "✅" ;;
            starting) echo "⏳" ;;
            *)        echo "❌" ;;
        esac
    }

    echo ""
    echo "  Portal 5 — System Status"
    echo "  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""

    # ── Stack services ────────────────────────────────────────────────────────
    echo "  STACK SERVICES"
    # Build status table: python3 looks up health per container name
    _stack_status() {
        cd "$COMPOSE_DIR" && docker compose ps --format json 2>/dev/null | python3 -c "
import json, sys
health = {}
for line in sys.stdin:
    line = line.strip()
    if not line: continue
    try:
        d = json.loads(line)
        h = d.get('Health','') or ('running' if 'Up' in d.get('Status','') else 'stopped')
        health[d['Name']] = h
    except: pass

rows = [
    ('portal5-open-webui',    'Open WebUI',           'http://localhost:8080'),
    ('portal5-pipeline',      'Portal Pipeline',      'http://localhost:9099'),
    ('portal5-searxng',       'SearXNG',              'http://localhost:8088'),
    ('portal5-prometheus',    'Prometheus',           'http://localhost:9090'),
    ('portal5-grafana',       'Grafana',              'http://localhost:3000'),
    ('portal5-mcp-documents', 'MCP Documents',        ':8913'),
    ('portal5-mcp-tts',       'MCP TTS',              ':8916'),
    ('portal5-mcp-whisper',   'MCP Whisper',          ':8915'),
    ('portal5-mcp-sandbox',   'MCP Code Sandbox',     ':8914'),
    ('portal5-mcp-security',  'MCP Security',         ':8919'),
    ('portal5-browser',       'MCP Browser (Obscura)',   ':8923'),
    ('portal5-mcp-research',  'MCP Research',         ':8922'),
    ('portal5-mcp-memory',    'MCP Memory',           ':8920'),
    ('portal5-mcp-rag',       'MCP RAG',              ':8921'),
    ('portal5-mcp-cad-render','MCP CAD Render',       ':8926'),
]
icons = {'healthy': '✅', 'running': '✅', 'starting': '⏳'}
for key, label, url in rows:
    h = health.get(key, 'stopped')
    icon = icons.get(h, '❌')
    print(f'    {icon}  {label:<28} {url}')
" 2>/dev/null
    }
    _stack_status
    echo ""

    # ── Native services ───────────────────────────────────────────────────────
    if [ "$ARCH" = "arm64" ]; then
        echo "  NATIVE SERVICES (host)"

        if python3 -c "import urllib.request; urllib.request.urlopen('http://localhost:11434/api/tags', timeout=2)" &>/dev/null 2>&1; then
            _OV=$(curl -s http://localhost:11434/api/version 2>/dev/null | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1)
            printf "    ✅  %-28s %s\n" "Ollama" ":11434  (v${_OV:-?})"
        else
            printf "    ❌  %-28s %s\n" "Ollama" "not running — sudo launchctl kickstart -k system/com.portal5.ollama"
        fi

        # oMLX inference server — serves the six omlx-* backend groups
        if command -v brew &>/dev/null && brew services list 2>/dev/null | grep -q '^omlx'; then
            if python3 -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8085/v1/models', timeout=3)" &>/dev/null 2>&1; then
                _OMV=$(brew list --versions omlx 2>/dev/null | awk '{print $2}')
                printf "    ✅  %-28s %s\n" "oMLX" ":8085  (v${_OMV:-?})"
            else
                printf "    ❌  %-28s %s\n" "oMLX" "wedged/not answering — brew services restart jundot/omlx/omlx"
            fi
        fi

        if python3 -c "import urllib.request; urllib.request.urlopen('http://localhost:${MFLUX_MCP_PORT:-8933}/health', timeout=2)" &>/dev/null 2>&1; then
            printf "    ✅  %-28s %s\n" "MFLUX image MCP" ":${MFLUX_MCP_PORT:-8933}"
        elif [ -f "$HOME/.portal5/mflux/.venv/bin/python" ]; then
            printf "    ❌  %-28s %s\n" "MFLUX image MCP" "installed but not running"
        else
            printf "    ℹ️   %-28s %s\n" "MFLUX image MCP" "not installed — ./launch.sh install-mflux"
        fi
        if python3 -c "import urllib.request; urllib.request.urlopen('http://localhost:${VIDEO_MLX_MCP_PORT:-8935}/health', timeout=2)" &>/dev/null 2>&1; then
            printf "    ✅  %-28s %s\n" "video-mlx MCP" ":${VIDEO_MLX_MCP_PORT:-8935}"
        elif [ -f "$HOME/.portal5/video-mlx/ltx-2-mlx/.venv/bin/python" ]; then
            printf "    ❌  %-28s %s\n" "video-mlx MCP" "installed but not running"
        else
            printf "    ℹ️   %-28s %s\n" "video-mlx MCP" "not installed (video module off by default) — ./launch.sh install-video-mlx"
        fi

        if python3 -c "import urllib.request; urllib.request.urlopen('http://localhost:${MUSIC_MINIMAX_PORT:-8912}/health', timeout=2)" &>/dev/null 2>&1; then
            printf "    ✅  %-28s %s\n" "Music MiniMax MCP" ":${MUSIC_MINIMAX_PORT:-8912}"
        elif [ -f "$HOME/.portal5/music-minimax/.venv/bin/python" ]; then
            printf "    ❌  %-28s %s\n" "Music MiniMax MCP" "installed but not running"
        else
            printf "    ℹ️   %-28s %s\n" "Music MiniMax MCP" "not installed — ./launch.sh install-music-minimax"
        fi
        for _music_check in "Music ACE MCP|${MUSIC_ACE_MCP_PORT:-8934}|$HOME/.portal5/music-ace/.venv/bin/python|install-music-ace" "ACE-Step engine|${ACESTEP_ENGINE_PORT:-8001}|$HOME/.portal5/music-ace/ace-runtime|install-music-ace"; do
            IFS='|' read -r _music_label _music_port _music_path _music_install <<< "$_music_check"
            if python3 -c "import urllib.request; urllib.request.urlopen('http://localhost:${_music_port}/health', timeout=2)" &>/dev/null 2>&1; then
                printf "    ✅  %-28s %s\n" "$_music_label" ":${_music_port}"
            elif [ -e "$_music_path" ]; then
                printf "    ❌  %-28s %s\n" "$_music_label" "installed but not running"
            else
                printf "    ℹ️   %-28s %s\n" "$_music_label" "not installed — ./launch.sh $_music_install"
            fi
        done

        # MLX Speech
        if python3 -c "import urllib.request; urllib.request.urlopen('http://localhost:8918/health', timeout=2)" &>/dev/null 2>&1; then
            printf "    ✅  %-28s %s\n" "MLX Speech" ":8918 (Qwen3-TTS + Qwen3-ASR)"
        elif [ -f /tmp/portal-mlx-speech.pid ] && kill -0 "$(cat /tmp/portal-mlx-speech.pid)" 2>/dev/null; then
            printf "    ⏳  %-28s %s\n" "MLX Speech" "starting"
        elif python3 -c "import mlx_audio" &>/dev/null 2>&1; then
            printf "    ❌  %-28s %s\n" "MLX Speech" "installed but not running — ./launch.sh start-speech"
        fi

        # MLX Transcribe service status
        if python3 -c "import urllib.request; urllib.request.urlopen('http://localhost:${MLX_TRANSCRIBE_PORT:-8924}/health', timeout=2)" &>/dev/null 2>&1; then
            printf "    ✅  %-28s %s\n" "MLX Transcribe" ":${MLX_TRANSCRIBE_PORT:-8924}"
        elif launchctl print "gui/$(id -u)/com.portal5.mlx-transcribe" &>/dev/null 2>&1; then
            printf "    ⏳  %-28s %s\n" "MLX Transcribe" "starting (launchd-managed)"
        elif [ -f /tmp/portal-mlx-transcribe.pid ] && kill -0 "$(cat /tmp/portal-mlx-transcribe.pid)" 2>/dev/null; then
            printf "    ⏳  %-28s %s\n" "MLX Transcribe" "starting (PID $(cat /tmp/portal-mlx-transcribe.pid))"
        elif [ -f scripts/mlx-transcribe.py ]; then
            printf "    ❌  %-28s %s\n" "MLX Transcribe" "installed but not running — ./launch.sh start-transcribe"
        fi

        # Embedding server
        if python3 -c "import urllib.request; urllib.request.urlopen('http://localhost:${EMBEDDING_HOST_PORT:-8917}/health', timeout=2)" &>/dev/null 2>&1; then
            printf "    ✅  %-28s %s\n" "Embedding" ":${EMBEDDING_HOST_PORT:-8917}"
        elif launchctl list com.portal5.embedding 2>/dev/null | grep -q '"PID"'; then
            printf "    ⏳  %-28s %s\n" "Embedding" "starting (launchd-managed)"
        else
            printf "    ❌  %-28s %s\n" "Embedding" "not running — ./launch.sh up"
        fi

        # Powermetrics daemon
        if [ -S /tmp/portal5-powermetrics.sock ] && python3 -c "import socket; s=socket.socket(socket.AF_UNIX); s.connect('/tmp/portal5-powermetrics.sock'); s.close()" &>/dev/null 2>&1; then
            printf "    ✅  %-28s %s\n" "Powermetrics" "/tmp/portal5-powermetrics.sock"
        elif launchctl list com.portal5.powermetrics 2>/dev/null | grep -q '"PID"'; then
            printf "    ⏳  %-28s %s\n" "Powermetrics" "starting (launchd)"
        else
            printf "    ❌  %-28s %s\n" "Powermetrics" "not running — ./launch.sh install-powermetrics"
        fi

        echo ""
    fi

    # ── Pipeline summary ──────────────────────────────────────────────────────
    echo "  PIPELINE"
    _PH=$(python3 -c "
import urllib.request, json
d = json.loads(urllib.request.urlopen('http://localhost:9099/health', timeout=3).read())
print(f\"{d.get('backends_healthy','?')}/{d.get('backends_total','?')} backends healthy, {d.get('workspaces','?')} workspaces\")
" 2>/dev/null)
    if [ -n "$_PH" ]; then
        printf "    ✅  %s\n" "$_PH"
    else
        printf "    ❌  Pipeline unreachable\n"
    fi
    echo ""

    # ── Model counts ─────────────────────────────────────────────────────────
    echo "  MODELS"
    local _OW_EMAIL="${OPENWEBUI_ADMIN_EMAIL:-admin@portal.local}"
    local _OW_PASS="${OPENWEBUI_ADMIN_PASSWORD:-}"
    _OW_COUNTS=$(python3 -c "
import httpx
try:
    # Workspace count from pipeline
    ws_count = '?'
    try:
        pr = httpx.get('http://localhost:9099/health', timeout=3)
        ws_count = str(pr.json().get('workspaces', '?'))
    except: pass
    # Persona count from OWUI
    ps_count = '?'
    r = httpx.post('http://localhost:8080/api/v1/auths/signin',
        json={'email': '${_OW_EMAIL}', 'password': '${_OW_PASS}'}, timeout=5)
    token = r.json().get('token','')
    if token:
        r2 = httpx.get('http://localhost:8080/api/v1/models/export',
            headers={'Authorization': 'Bearer ' + token}, timeout=5)
        items = r2.json() if isinstance(r2.json(), list) else r2.json().get('items', r2.json().get('data', []))
        ps_count = str(len(items))
    print(ws_count, ps_count)
except Exception as e:
    print('? ?')
" 2>/dev/null || echo "? ?")
    read -r _WS_COUNT _PERSONA_COUNT <<< "$_OW_COUNTS"
    if [ "$_WS_COUNT" != "?" ]; then
        printf "    ✅  Workspaces: %-4s  Personas: %s\n" "${_WS_COUNT}" "${_PERSONA_COUNT}"
    else
        printf "    ❌  Open WebUI not reachable (model counts unavailable)\n"
    fi
    echo ""

    # ── Channels (only shown when tokens are configured) ─────────────────────
    if [ -n "${TELEGRAM_BOT_TOKEN:-}" ] || [ -n "${SLACK_BOT_TOKEN:-}" ]; then
        echo "  CHANNELS"
        if [ -n "${TELEGRAM_BOT_TOKEN:-}" ]; then
            _TG=$(docker ps --format "{{.Names}}" 2>/dev/null | grep -c "portal5-telegram")
            if [ "$_TG" -ge 1 ]; then
                printf "    ✅  %-28s %s\n" "Telegram Bot" "running"
            else
                printf "    ❌  %-28s %s\n" "Telegram Bot" "configured but not running — ./launch.sh up"
            fi
        fi
        if [ -n "${SLACK_BOT_TOKEN:-}" ] && [ -n "${SLACK_APP_TOKEN:-}" ]; then
            _SL=$(docker ps --format "{{.Names}}" 2>/dev/null | grep -c "portal5-slack")
            if [ "$_SL" -ge 1 ]; then
                printf "    ✅  %-28s %s\n" "Slack Bot" "running"
            else
                printf "    ❌  %-28s %s\n" "Slack Bot" "configured but not running — ./launch.sh up"
            fi
        fi
        echo ""
    fi

}
