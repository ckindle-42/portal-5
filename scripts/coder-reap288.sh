#!/usr/bin/env bash
# coder-reap288.sh — one command to code with the REAP-288 heavy IDE model.
#
# Qwen3.8-Flash-Next-REAP-288-MLX-4bit is ~39GB oMLX-resident (with the SSD
# PLE-streaming path) and oMLX's admission gate for it (~40.6GB) cannot be met
# while the Portal Docker stack + Ollama are loaded — with the full stack up,
# only ~10GB is reclaimable and the model is evicted on sight
# (TASK_OMLX_QWEN38FN_REAP288_BRINGUP_V1).
#
# So this script points opencode STRAIGHT AT oMLX (:8085), with the Portal
# stack DOWN, and runs the ritual to make that work:
#
#   1. stop the Portal stack        (./launch.sh down)   — frees the Docker VM
#   2. evict every loaded Ollama model                    — frees ~5-6GB more
#   3. warm-load REAP-288 into oMLX  (one :8085 request)  — ~22s first load
#   4. exec opencode with a scratch config that targets :8085 directly,
#      model preselected, --auto. The project opencode.jsonc is untouched.
#
# opencode runs on its own built-in tools here (read / write / bash / etc.) —
# NOT the Portal MCP tool + persona layer, which needs the pipeline (:9099)
# and therefore the stack. For the Portal-integrated lane use the
# `portal/codingreap288` persona once the pipeline is rebuilt and you have
# spare RAM (fragile — see config/personas/codingreap288.yaml).
#
# The Portal stack stays DOWN while you use this. Run `./launch.sh up` when
# you are done to bring OWUI / the MCP fleet back.
#
# PREFILL CEILING (measured 2026-09-02, 64GB M4 Pro): the model sits at ~39GB
# resident, leaving ~17GB under the 56GB Metal cap. Short/medium prompts are
# fine; a full agentic session that pulls ~18-20K tokens of repo context into
# the prompt drives the prefill peak to ~52-53GB and oMLX's prefill memory
# guard warns/limits it. --raise-metal-cap bumps iogpu.wired_limit_mb to 60GB
# for the session (needs sudo; reverts on reboot) to buy headroom; still tight.
# For heavy repo-wide agentic work the laguna default is the better lane.
#
# Usage:
#   ./launch.sh coder-reap288                   # full ritual, then open opencode
#   ./launch.sh coder-reap288 --warm-only       # steps 1-3 only; prints the opencode command
#   ./launch.sh coder-reap288 --no-down         # skip the stack-down (already down / you manage it)
#   ./launch.sh coder-reap288 --raise-metal-cap # sudo-bump the Metal cap to 60GB for the session
#
# Referenced by launch.sh (coder-reap288) and scripts/OPERATOR_TOOLS.md.

set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO"

OMLX_HOST="${OMLX_HOST:-127.0.0.1}"
OMLX_PORT="${OMLX_PORT:-8085}"
OMLX_BASE="http://${OMLX_HOST}:${OMLX_PORT}"
OLLAMA_URL="${OLLAMA_URL:-http://127.0.0.1:11434}"
MODEL_ID="Qwen3.8-Flash-Next-REAP-288-MLX-4bit"
OPENCODE="${OPENCODE_BIN:-$HOME/.opencode/bin/opencode}"
CONF_DIR="${XDG_CACHE_HOME:-$HOME/.cache}/portal5-coder-reap288"
CONF="$CONF_DIR/opencode.jsonc"

WARM_ONLY=0
NO_DOWN=0
RAISE_CAP=0
for arg in "$@"; do
  case "$arg" in
    --warm-only)      WARM_ONLY=1 ;;
    --no-down)        NO_DOWN=1 ;;
    --raise-metal-cap) RAISE_CAP=1 ;;
    -h|--help)   sed -n '2,40p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "coder-reap288: unknown arg '$arg'" >&2; exit 2 ;;
  esac
done

say() { printf '\033[1;36m[reap288]\033[0m %s\n' "$*"; }
die() { printf '\033[1;31m[reap288] BLOCKED:\033[0m %s\n' "$*" >&2; exit 1; }

# ── Preconditions ─────────────────────────────────────────────────────────────
command -v curl >/dev/null || die "curl not on PATH"
curl -sf "$OMLX_BASE/v1/models" >/dev/null 2>&1 \
  || die "oMLX not answering on $OMLX_BASE — check 'brew services list' / omlx-watchdog.log"
curl -sf "$OMLX_BASE/v1/models" | grep -q "$MODEL_ID" \
  || die "$MODEL_ID not in oMLX /v1/models — is it under /Volumes/data01/omlx-models? 'omlx restart' to rescan"
if [ "$WARM_ONLY" -eq 0 ]; then
  [ -x "$OPENCODE" ] || die "opencode not found at $OPENCODE (set OPENCODE_BIN=)"
fi

# ── 1. stop the stack ────────────────────────────────────────────────────────
if [ "$NO_DOWN" -eq 0 ] && docker ps --format '{{.Names}}' 2>/dev/null | grep -q '^portal5-pipeline$'; then
  say "Stopping the Portal stack to free memory (./launch.sh down)…"
  ./launch.sh down
else
  say "Portal stack already down (or --no-down) — skipping ./launch.sh down."
fi

# ── 1b. optionally raise the Metal cap for the session ───────────────────────
if [ "$RAISE_CAP" -eq 1 ]; then
  cur="$(sysctl -n iogpu.wired_limit_mb 2>/dev/null || echo 0)"
  if [ "$cur" -lt 61440 ]; then
    say "Raising iogpu.wired_limit_mb $cur -> 61440 for this session (sudo; reverts on reboot)…"
    sudo sysctl -w iogpu.wired_limit_mb=61440 || say "  (skipped — sudo declined; continuing at $cur)"
  fi
fi

# ── 2. evict loaded Ollama models ────────────────────────────────────────────
loaded="$(curl -sf "$OLLAMA_URL/api/ps" 2>/dev/null | sed -n 's/.*"name":"\([^"]*\)".*/\1/p' || true)"
if [ -n "$loaded" ]; then
  while IFS= read -r m; do
    [ -n "$m" ] || continue
    say "Evicting Ollama model: $m"
    curl -sf "$OLLAMA_URL/api/generate" -d "{\"model\":\"$m\",\"keep_alive\":0}" >/dev/null 2>&1 || true
  done <<< "$loaded"
  sleep 3
fi

# ── 3. warm-load REAP-288 ────────────────────────────────────────────────────
say "Warm-loading $MODEL_ID (first load ~22s)…"
code="$(curl -s -o "$CONF_DIR.warm.json" -w '%{http_code}' --max-time 300 \
  "$OMLX_BASE/v1/chat/completions" -H 'Content-Type: application/json' \
  -d "{\"model\":\"$MODEL_ID\",\"messages\":[{\"role\":\"user\",\"content\":\"ready\"}],\"max_tokens\":8,\"temperature\":0}" 2>/dev/null || true)"
mkdir -p "$CONF_DIR"
if [ "$code" != "200" ]; then
  echo "--- oMLX response ---" >&2; cat "$CONF_DIR.warm.json" 2>/dev/null >&2 || true; echo >&2
  die "warm load failed (HTTP $code). If it says 'does not fit', something else is holding RAM — 'ps aux | sort -nrk4 | head' and close it, then retry."
fi
say "  loaded ($(sed -n 's/.*"total_time":\([0-9.]*\).*/\1s total/p' "$CONF_DIR.warm.json"))."

# ── 4. write the scratch opencode config (project opencode.jsonc untouched) ───
cat > "$CONF" <<EOF
{
  // Generated by scripts/coder-reap288.sh — points opencode straight at the
  // local oMLX server (:$OMLX_PORT), bypassing the Portal pipeline so the
  // heavy REAP-288 model can run with the Docker stack down. Safe to delete.
  "\$schema": "https://opencode.ai/config.json",
  "provider": {
    "omlx": {
      "name": "oMLX (local, direct)",
      "api": "openai",
      "options": { "baseURL": "$OMLX_BASE/v1", "apiKey": "omlx-local" },
      "models": { "$MODEL_ID": { "name": "REAP-288 (Qwen3.8-Flash-Next, oMLX direct)" } }
    }
  },
  "model": "omlx/$MODEL_ID"
}
EOF

if [ "$WARM_ONLY" -eq 1 ]; then
  say "Warm-only. REAP-288 is resident. To open opencode:"
  say "  OPENCODE_CONFIG=$CONF $OPENCODE -m omlx/$MODEL_ID --auto $REPO"
  say "Bring the Portal stack back with: ./launch.sh up"
  exit 0
fi

# ── 5. open opencode ─────────────────────────────────────────────────────────
say "Portal stack is DOWN — run './launch.sh up' when you finish this session."
say "Opening opencode → oMLX direct, model omlx/$MODEL_ID (--auto)…"
export OPENCODE_CONFIG="$CONF"
exec "$OPENCODE" -m "omlx/$MODEL_ID" --auto "$REPO"
