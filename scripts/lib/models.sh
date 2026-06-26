#!/usr/bin/env bash
# models.sh — Portal 5 model commands (sourced by launch.sh)
# shellcheck shell=bash

_launch_apply_model_params() {
    # Idempotent: create Ollama tags with baked-in PARAMETER num_ctx values.
    # Run once after pulling the base models; safe to re-run (ollama create is idempotent).
    set -a; source "$ENV_FILE" 2>/dev/null || true; set +a

    _apm_ollama() {
        if command -v ollama &>/dev/null && curl -s http://localhost:11434/api/tags &>/dev/null 2>&1; then
            ollama "$@"
        elif docker ps --format '{{.Names}}' 2>/dev/null | grep -q "^portal5-ollama$"; then
            docker exec portal5-ollama ollama "$@"
        else
            echo "ERROR: Ollama not reachable (not running locally or in Docker)" >&2
            return 1
        fi
    }

    # _apm_create_ctx_tag <base_tag> <tag_suffix> <num_ctx_value>
    # e.g. _apm_create_ctx_tag "model:tag" "ctx32k" "32768"
    # The tag suffix and numeric value are separate so the tag name stays
    # human-readable (ctx32k) while the Modelfile gets the exact integer.
    _apm_create_ctx_tag() {
        local base_tag="$1" tag_suffix="$2" ctx="$3"
        local new_tag="${base_tag}-${tag_suffix}"
        # Check if source model exists
        if ! _apm_ollama show "$base_tag" &>/dev/null 2>&1; then
            echo "  SKIP $new_tag — base model $base_tag not pulled (run ./launch.sh pull-models first)"
            return 0
        fi
        local modelfile
        modelfile=$(mktemp)
        printf 'FROM %s\nPARAMETER num_ctx %d\n' "$base_tag" "$ctx" > "$modelfile"
        echo "  Creating $new_tag (num_ctx=$ctx) ..."
        if _apm_ollama create "$new_tag" -f "$modelfile"; then
            echo "  OK $new_tag"
        else
            echo "  FAIL $new_tag — see above"
        fi
        rm -f "$modelfile"
    }

    echo "Applying model params (ctx tags) ..."
    echo "No active ctx tags in this fleet version (480B removed TASK_MODEL_FLEET_REFRESH_V2 Phase 3)."
    echo "Done."
}

_launch_import_gguf() {
    # Import a locally downloaded GGUF file into Ollama
    # Usage: ./launch.sh import-gguf /path/to-model.gguf [ollama-name]
    _gguf_path="${2:-}"
    _model_name="${3:-}"

    # Expand ~ manually since this runs at script level, not inside a function
    _gguf_path="${_gguf_path/#\~/$HOME}"

    if [ -z "$_gguf_path" ] || [ ! -f "$_gguf_path" ]; then
        echo "Usage: ./launch.sh import-gguf <path-to-gguf> [model-name]"
        echo ""
        echo "  path-to-gguf   Full path to a .gguf file"
        echo "  model-name     Name to register in Ollama (default: filename without extension)"
        echo ""
        echo "Example:"
        echo "  ./launch.sh import-gguf ~/Downloads/baronllm-q6_k.gguf baronllm:q6_k"
        echo "  ./launch.sh import-gguf ~/Downloads/WhiteRabbitNeo-33B-v1.5-Q4_K_M.gguf whiterabbitneo:33b-v1.5-q4_k_m"
        exit 1
    fi

    if [ -z "$_model_name" ]; then
        _model_name=$(basename "$_gguf_path" .gguf | tr '[:upper:]' '[:lower:]' | tr '_' '-')
    fi

    # Detect Ollama (native or Docker)
    if command -v ollama &>/dev/null && curl -s http://localhost:11434/api/tags &>/dev/null 2>&1; then
        _ollama_import_cmd="ollama"
    elif docker ps --format '{{.Names}}' 2>/dev/null | grep -q "^portal5-ollama$"; then
        _ollama_import_cmd="docker exec portal5-ollama ollama"
    else
        echo "[portal-5] ❌ No Ollama available. Run: ./launch.sh install-ollama"
        exit 1
    fi

    echo "[portal-5] Importing GGUF: $_gguf_path"
    echo "           Ollama name:   $_model_name"

    _tmp_dir=$(mktemp -d)
    cat > "$_tmp_dir/Modelfile" << MEOF
FROM $_gguf_path
PARAMETER temperature 0.7
PARAMETER num_ctx 8192
MEOF

    if $_ollama_import_cmd create "$_model_name" -f "$_tmp_dir/Modelfile"; then
        echo "[portal-5] ✅ Imported: $_model_name"
        echo "  Run it: ollama run $_model_name"
    else
        echo "[portal-5] ❌ Import failed. Check Ollama is running: brew services info ollama"
        rm -rf "$_tmp_dir"
        exit 1
    fi
    rm -rf "$_tmp_dir"
}

_launch_apply_mtp_drafts() {
    # Wire Qwen3.6-27B MTP speculative-decoding A/B pairing.
    #
    # Creates: portal5/qwen3.6-27b-mtp:q8_0-drafted
    #   Base:  qwen3.6:27b-q8_0       (high-precision quality model)
    #   Draft: qwen3.6:27b-mtp-q4_K_M (MTP-capable fast draft model)
    #
    # The resulting model runs at q8_0 quality with draft-accelerated token
    # generation. bench-qwen36-27b-mtp is wired to this tag for the Phase-6
    # TPS A/B vs bench-qwen36-27b (plain q8_0).
    #
    # Idempotent: re-running recreates the model (safe after any base update).
    # Graceful-skip: if either base or draft is absent, prints SKIP and exits 0.
    # DRAFT rejection: if Ollama rejects MTP for this architecture, the error
    # is logged verbatim and the command exits 1 so the operator can see it.
    # Retry condition: after Ollama adds broader MTP arch support (tracked in
    # TASK_MODEL_FLEET_REFRESH_V2 Phase 5 notes).

    set -a; source "$ENV_FILE" 2>/dev/null || true; set +a

    _mtp_ollama() {
        if command -v ollama &>/dev/null && curl -s http://localhost:11434/api/tags &>/dev/null 2>&1; then
            ollama "$@"
        elif docker ps --format '{{.Names}}' 2>/dev/null | grep -q "^portal5-ollama$"; then
            docker exec portal5-ollama ollama "$@"
        else
            echo "ERROR: Ollama not reachable (not running locally or in Docker)" >&2
            return 1
        fi
    }

    MTP_BASE_TAG="qwen3.6:27b-q8_0"
    MTP_DRAFT_TAG="qwen3.6:27b-mtp-q4_K_M"
    MTP_CREATED_TAG="portal5/qwen3.6-27b-mtp:q8_0-drafted"

    echo "apply-mtp-drafts: wiring Qwen3.6-27B MTP A/B pair ..."

    # Check base model
    if ! _mtp_ollama show "$MTP_BASE_TAG" &>/dev/null 2>&1; then
        echo "  SKIP — base model $MTP_BASE_TAG not pulled."
        echo "  Run: ollama pull $MTP_BASE_TAG  (or ./launch.sh pull-models)"
        exit 0
    fi

    # Pull draft model if needed
    if ! _mtp_ollama show "$MTP_DRAFT_TAG" &>/dev/null 2>&1; then
        echo "  Pulling draft model $MTP_DRAFT_TAG ..."
        if ! _mtp_ollama pull "$MTP_DRAFT_TAG"; then
            echo "  FAIL — could not pull $MTP_DRAFT_TAG"
            exit 1
        fi
    fi

    # Get the GGUF blob path for the draft model
    MTP_DRAFT_PATH=$(_mtp_ollama show "$MTP_DRAFT_TAG" --modelfile 2>/dev/null | grep '^FROM ' | head -1 | awk '{print $2}')
    if [ -z "$MTP_DRAFT_PATH" ] || [ ! -f "$MTP_DRAFT_PATH" ]; then
        echo "  FAIL — could not resolve blob path for $MTP_DRAFT_TAG (got: '$MTP_DRAFT_PATH')"
        echo "  This may indicate the model is not locally cached. Re-pull and retry."
        exit 1
    fi
    echo "  Draft blob: $MTP_DRAFT_PATH"

    # Create the MTP-drafted model
    MTP_MODELFILE=$(mktemp)
    printf 'FROM %s\nDRAFT %s\n' "$MTP_BASE_TAG" "$MTP_DRAFT_PATH" > "$MTP_MODELFILE"
    echo "  Modelfile:"
    cat "$MTP_MODELFILE"
    echo "  Creating $MTP_CREATED_TAG ..."

    MTP_CREATE_OUTPUT=$(ollama create "$MTP_CREATED_TAG" -f "$MTP_MODELFILE" 2>&1)
    MTP_CREATE_EXIT=$?
    rm -f "$MTP_MODELFILE"

    echo "$MTP_CREATE_OUTPUT"

    if [ $MTP_CREATE_EXIT -ne 0 ]; then
        echo ""
        echo "  DRAFT REJECTION (Ollama create failed, exit $MTP_CREATE_EXIT)."
        echo "  Verbatim error above. Architecture MTP support may not be available in"
        echo "  Ollama ${_OLLAMA_VER:-$(ollama --version 2>/dev/null | awk '{print $NF}')} for Qwen3.6."
        echo "  Retry condition: after Ollama adds Qwen3.6 MTP arch support."
        echo "  Wiring: bench-qwen36-27b-mtp hint is kept for the retry."
        exit 1
    fi

    # Verify
    echo ""
    echo "  Verifying $MTP_CREATED_TAG ..."
    _mtp_ollama show "$MTP_CREATED_TAG" 2>&1 | head -10
    echo ""
    echo "  OK — $MTP_CREATED_TAG created."
    echo "  Re-hint bench-qwen36-27b-mtp in workspaces.py if the workspace's hint"
    echo "  still points to the Qwopus artifact (TASK_MODEL_FLEET_REFRESH_V2 Phase 5)."
}

