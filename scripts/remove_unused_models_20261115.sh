#!/usr/bin/env bash
# Remove models identified as unused by docs/MODEL_UNUSED_INVENTORY_20261115.md.
# Dry-run by default; pass --apply to actually delete. Idempotent: skips items
# that no longer exist or that re-verification finds referenced.
set -u

APPLY=0
if [[ "${1:-}" == "--apply" ]]; then APPLY=1; fi

REPO="${REPO:-/Users/chris/projects/portal-5-unused-model-inventory}"
OLLAMA_STORE="/Volumes/data01/ollama/models"
OMLX_ROOT="/Volumes/data01/omlx-models"
HF_ROOT="/Volumes/data01/hf-cache"
P40_ROOT="$HOME/.claude/orchestrate"

say() { printf '%s\n' "$*"; }

# Re-verify an Ollama tag is unreferenced. Returns 0 if safe to remove.
verify_ollama() {
  local tag="$1"
  # repo search (exact tag)
  if grep -rlF --exclude='remove_unused_models_20261115.sh' --exclude='MODEL_UNUSED_INVENTORY_20261115.md' -- "$tag" "$REPO/config" "$REPO/portal" "$REPO/scripts" "$REPO/deploy" "$REPO/tests" "$REPO/launch.sh" 2>/dev/null | grep -v '/_archive/' | grep -q .; then
    return 1
  fi
  # P40 host config
  if [[ -d "$P40_ROOT" ]] && grep -rlF --exclude='*.jsonl' -- "$tag" "$P40_ROOT" 2>/dev/null | grep -v '/logs/' | grep -v '/bench/' | grep -q .; then
    return 1
  fi
  return 0
}

# Re-verify an HF-cache snapshot is orphaned + unreferenced. Returns 0 if safe.
verify_hf() {
  local d="$1"
  local body org repo slash
  body="${d#models--}"
  org="${body%%--*}"
  repo="${body#*--}"
  slash="$org/$repo"
  # linked by an oMLX entry?
  for p in "$OMLX_ROOT"/*; do
    if [[ -L "$p" ]]; then
      tgt="$(readlink "$p")"
      if [[ "$tgt" == *"$d"* ]]; then
        return 1
      fi
    fi
  done
  # repo search (dir name, slash form, repo name)
  for needle in "$d" "$slash" "$repo"; do
    [[ -z "$needle" ]] && continue
    if grep -rlF --exclude='remove_unused_models_20261115.sh' --exclude='MODEL_UNUSED_INVENTORY_20261115.md' -- "$needle" "$REPO/config" "$REPO/portal" "$REPO/scripts" "$REPO/deploy" "$REPO/tests" "$REPO/launch.sh" 2>/dev/null | grep -v '/_archive/' | grep -q .; then
      return 1
    fi
  done
  # P40 host config
  if [[ -d "$P40_ROOT" ]]; then
    for needle in "$d" "$slash" "$repo"; do
      [[ -z "$needle" ]] && continue
      if grep -rlF --exclude='*.jsonl' -- "$needle" "$P40_ROOT" 2>/dev/null | grep -v '/logs/' | grep -v '/bench/' | grep -q .; then
        return 1
      fi
    done
  fi
  return 0
}

# --- Ollama tags ---
OLLAMA_TAGS=(
  "hf.co/bartowski/NousResearch_Arete-27B-GGUF:Q4_K_M"
)

# --- HF-cache snapshots ---
HF_DIRS=(
  "models--Qwen--Qwen2.5-Omni-3B"
  "models--docling-project--docling-layout-heron"
  "models--docling-project--docling-models"
  "models--ibm-granite--granite-switch-4.1-3b-preview"
  "models--mlx-community--higgs-audio-v2-tokenizer"
  "models--mobiuslabsgmbh--faster-whisper-large-v3-turbo"
  "models--tencent--AuK-Flash"
)

say "=== remove_unused_models_20261115.sh (apply=$APPLY) ==="

# Ollama
for tag in "${OLLAMA_TAGS[@]}"; do
  if ! verify_ollama "$tag"; then
    say "SKIP (re-verify found reference): ollama $tag"
    continue
  fi
  if [[ $APPLY -eq 1 ]]; then
    say "RUNNING: ollama rm $tag"
    ollama rm "$tag" || say "  (ollama rm failed or not present)"
  else
    say "DRY-RUN: would run: ollama rm $tag"
  fi
done

# HF-cache
for d in "${HF_DIRS[@]}"; do
  target="$HF_ROOT/$d"
  if [[ ! -e "$target" ]]; then
    say "SKIP (already absent): $target"
    continue
  fi
  if ! verify_hf "$d"; then
    say "SKIP (re-verify found reference): $target"
    continue
  fi
  if [[ $APPLY -eq 1 ]]; then
    say "RUNNING: rm -rf $target"
    rm -rf "$target"
  else
    say "DRY-RUN: would run: rm -rf $target"
  fi
done

say "=== done ==="
