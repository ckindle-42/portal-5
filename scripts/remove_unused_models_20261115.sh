#!/usr/bin/env bash
# Recheck pass-one removals immediately before acting; dry-run is the default.
set -u

APPLY=0
case "${1:-}" in
  "") ;;
  --apply) APPLY=1 ;;
  -h|--help)
    printf '%s\n' "Usage: $0 [--apply]" "Default mode only reports candidates; --apply removes them after fresh checks."
    exit 0
    ;;
  *) printf 'Unknown argument: %s\n' "$1" >&2; exit 2 ;;
esac

REPO="${REPO:-/Users/chris/projects/portal-5-unused-model-inventory}"
OMLX_ROOT="${OMLX_ROOT:-/Volumes/data01/omlx-models}"
HF_ROOT="${HF_ROOT:-/Volumes/data01/hf-cache}"
CLOSEOUT="$REPO/docs/MODEL_FLEET_CLOSEOUT_20260906.tasks.json"

say() { printf '%s\n' "$*"; }

# Search only production config and source; list-only and historical files do not block removal.
has_active_reference() {
  local needle="$1" status
  command -v rg >/dev/null 2>&1 || return 2
  if rg -l -F \
    --glob '*.yaml' --glob '*.yml' --glob '*.py' --glob '*.sh' \
    --glob '!**/tests/**' --glob '!**/test_*.py' --glob '!**/_archive/**' \
    --glob '!MODEL_CATALOG.md' --glob '!**/promptfoo/**' \
    --glob '!remove_unused_models_20261115.sh' \
    -- "$needle" "$REPO/config" "$REPO/portal" "$REPO/scripts" "$REPO/deploy" "$REPO/launch.sh" \
    >/dev/null 2>&1; then
    return 0
  else
    status=$?
    [[ $status -eq 1 ]] && return 1
    return 2
  fi
}

# Return the closeout state for one exact identity; malformed state fails closed.
closeout_disposition() {
  python3 - "$CLOSEOUT" "$1" <<'PY'
import json
import sys
from pathlib import Path

path, target = Path(sys.argv[1]), sys.argv[2]
try:
    data = json.loads(path.read_text())
except (OSError, json.JSONDecodeError):
    raise SystemExit(2)
rows = list(data.get("items", [])) + list(data.get("extra_identities", []))
matches = []
for row in rows:
    identity = row.get("identity") or row.get("exact_identity")
    disposition = row.get("final_disposition") or row.get("disposition")
    if identity == target and disposition:
        matches.append(disposition)
if "INTEGRATED" in matches:
    print("INTEGRATED")
elif "RETAINED_FOR_PURPOSE" in matches:
    print("RETAINED_FOR_PURPOSE")
elif "REMOVED_CLOSED" in matches:
    print("REMOVED_CLOSED")
else:
    print("UNLISTED")
PY
}

verify_ollama() {
  local tag="$1" disposition status
  if has_active_reference "$tag"; then
    return 1
  else
    status=$?
    [[ $status -eq 1 ]] || return 1
  fi
  disposition="$(closeout_disposition "$tag")" || return 1
  if [[ "$disposition" == "INTEGRATED" || "$disposition" == "RETAINED_FOR_PURPOSE" ]]; then
    return 1
  fi
  return 0
}

verify_hf() {
  local dir="$1" body org repo target link disposition status needle
  body="${dir#models--}"
  org="${body%%--*}"
  repo="${body#*--}"
  target="$HF_ROOT/$dir"

  # Any oMLX link keeps its target, even if the link is not at the root.
  if [[ -d "$OMLX_ROOT" ]]; then
    command -v find >/dev/null 2>&1 || return 1
    command -v readlink >/dev/null 2>&1 || return 1
    while IFS= read -r -d '' link; do
      if [[ "$(readlink "$link" 2>/dev/null || true)" == *"$dir"* ]]; then
        return 1
      fi
    done < <(find "$OMLX_ROOT" -type l -print0 2>/dev/null)
  fi

  for needle in "$org/$repo" "$org--$repo"; do
    if has_active_reference "$needle"; then
      return 1
    else
      status=$?
      [[ $status -eq 1 ]] || return 1
    fi
  done
  disposition="$(closeout_disposition "$dir")" || return 1
  if [[ "$disposition" == "INTEGRATED" || "$disposition" == "RETAINED_FOR_PURPOSE" ]]; then
    return 1
  fi
  return 0
}

OLLAMA_TAGS=(
  "hf.co/bartowski/NousResearch_Arete-27B-GGUF:Q4_K_M"
)
HF_DIRS=(
  "models--Qwen--Qwen2.5-Omni-3B"
  "models--ibm-granite--granite-switch-4.1-3b-preview"
  "models--tencent--AuK-Flash"
  "models--Jiunsong--supergemma4-26b-uncensored-mlx-4bit-v2"
  "models--Youssofal--MiMo-V2.6-Qwen-9B-MTPLX-Optimized-Speed"
  "models--Youssofal--Qwen3.6-27B-MTPLX-Optimized-Speed"
)

say "=== remove_unused_models_20261115.sh (apply=$APPLY) ==="

for tag in "${OLLAMA_TAGS[@]}"; do
  disposition="$(closeout_disposition "$tag")" || {
    say "SKIP (could not read closeout state): ollama $tag"
    continue
  }
  if [[ "$disposition" == "REMOVED_CLOSED" ]]; then
    say "SKIP (closeout already REMOVED_CLOSED): ollama $tag"
    continue
  fi
  if ! verify_ollama "$tag"; then
    say "SKIP (active reference or retained disposition): ollama $tag"
    continue
  fi
  if [[ $APPLY -eq 0 ]]; then
    say "DRY-RUN: would remove only if still installed and unreferenced: ollama $tag"
    continue
  fi
  if ! command -v ollama >/dev/null 2>&1 || ! ollama show "$tag" >/dev/null 2>&1; then
    say "SKIP (already absent or Ollama unavailable): ollama $tag"
    continue
  fi
  if ! verify_ollama "$tag"; then
    say "SKIP (reference changed on immediate recheck): ollama $tag"
    continue
  fi
  say "RUNNING: ollama rm $tag"
  ollama rm "$tag" || say "  (ollama rm failed)"
done

for dir in "${HF_DIRS[@]}"; do
  target="$HF_ROOT/$dir"
  disposition="$(closeout_disposition "$dir")" || {
    say "SKIP (could not read closeout state): $target"
    continue
  }
  if [[ "$disposition" == "REMOVED_CLOSED" ]]; then
    say "SKIP (closeout already REMOVED_CLOSED): $target"
    continue
  fi
  if [[ ! -e "$target" ]]; then
    say "SKIP (already absent): $target"
    continue
  fi
  if ! verify_hf "$dir"; then
    say "SKIP (active reference, retained disposition, or oMLX link): $target"
    continue
  fi
  if [[ $APPLY -eq 0 ]]; then
    say "DRY-RUN: would remove after immediate recheck: $target"
    continue
  fi
  if ! verify_hf "$dir"; then
    say "SKIP (reference changed on immediate recheck): $target"
    continue
  fi
  say "RUNNING: rm -rf -- $target"
  rm -rf -- "$target"
done

say "=== done ==="
