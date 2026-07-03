#!/usr/bin/env bash
# execute_local_sec_bench.sh — one-command supervised full-coverage sec bench (local, no frontier agent).
#
# Usage:
#   ./execute_local_sec_bench.sh                     # full-coverage supervised run (Layer 1 only)
#   ./execute_local_sec_bench.sh --smoke             # single-scenario smoke test first (recommended)
#   ./execute_local_sec_bench.sh --scenario web_sqli_dump   # one named scenario
#   ./execute_local_sec_bench.sh --triage propose    # P40 diagnoses, you confirm
#   ./execute_local_sec_bench.sh --triage auto       # P40 diagnoses + acts (allowlisted), for overnight
set -euo pipefail
cd "$(dirname "$0")"
export PYTHONPATH="tests/benchmarks:."

# ── Config (env-overridable) ──
RED_MODELS="${RED_MODELS:-${RED_MODEL:-huihui_ai/baronllm-abliterated}}"
BLUE_MODELS="${BLUE_MODELS:-${BLUE_MODEL:-sylink/sylink:8b}}"
# OLLAMA_URL honored if exported (point red at a separate lab box); default localhost:11434.
TRIAGE_OLLAMA_URL="${TRIAGE_OLLAMA_URL:-http://localhost:11434}"
TRIAGE_MODEL="${TRIAGE_MODEL:-ducquoc/gpt-oss-sonnet:latest}"

# ── Preconditions: lab reachable ──
echo "== preflight: probing lab reachability =="
python3 -m bench_security --probe-lab || { echo "LAB UNREACHABLE — aborting"; exit 1; }

# ── Scope: full, smoke (one scenario), or a named scenario ──
SCOPE="--all-scenarios"
if [[ "${1:-}" == "--smoke" ]]; then SCOPE="--scenario kerberoast_to_da"; shift || true; fi
if [[ "${1:-}" == "--scenario" ]]; then SCOPE="--scenario ${2:?scenario name}"; shift 2 || true; fi

# ── Triage mode (optional, default: off = Layer 1 only) ──
TRIAGE_ARGS=""
if [[ "${1:-}" == "--triage" ]]; then
  TRIAGE_MODE="${2:?propose or auto}"
  TRIAGE_ARGS="--triage-mode ${TRIAGE_MODE} --triage-ollama-url ${TRIAGE_OLLAMA_URL} --triage-model ${TRIAGE_MODEL}"
  shift 2 || true
fi

# ── Canonical full-coverage run-args (blue/purple-driven; theory benches off) — ONE source of truth ──
RUN_ARGS="--skip-workspace-bench --lab-exec ${SCOPE} --purple \
  --chain-models ${RED_MODELS} --blue-models ${BLUE_MODELS} --blue-active"

echo "== launching supervised run: ${SCOPE} =="
exec python3 scripts/bench_supervisor.py \
  --run-args "${RUN_ARGS}" \
  --stall-minutes "${STALL_MINUTES:-15}" \
  --on-unknown "${ON_UNKNOWN:-pause}" \
  --max-corrections-per-scenario "${MAX_CORRECTIONS:-3}" \
  ${TRIAGE_ARGS} \
  2>&1 | tee "supervisor_$(date +%Y%m%dT%H%M%SZ).log"
