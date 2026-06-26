#!/usr/bin/env bash
# models.sh — Portal 5 model commands (sourced by launch.sh)
# shellcheck shell=bash

# Deprecated: delegated to ``portal models pull`` in portal_pipeline/cli.py (M5 Stage 2).
# Retained for parity; remove in next M5 pass.
_launch_pull_models() {
    set -a; source "$ENV_FILE" 2>/dev/null || true; set +a

    # ── Ollama availability check ─────────────────────────────────────────────
    _ollama_cmd() {
        # Returns the ollama command prefix to use (native or docker exec)
        if command -v ollama &>/dev/null && curl -s http://localhost:11434/api/tags &>/dev/null 2>&1; then
            echo "ollama"
        elif docker ps --format '{{.Names}}' 2>/dev/null | grep -q "^portal5-ollama$"; then
            echo "docker exec portal5-ollama ollama"
        else
            echo ""
        fi
    }

    # ── Check if model is already loaded in Ollama ────────────────────────────
    _model_exists() {
        local model_name="$1"
        local ollama_cmd
        ollama_cmd=$(_ollama_cmd)
        [ -n "$ollama_cmd" ] && $ollama_cmd list 2>/dev/null | grep -qi "^${model_name}"
    }

    # ── Refresh model (force re-pull even if present) ─────────────────────────
    _refresh_model() {
        local model="$1"
        local ollama_cmd
        ollama_cmd=$(_ollama_cmd)

        if [ -z "$ollama_cmd" ]; then
            echo "  ❌ No Ollama available. Run: ./launch.sh install-ollama"
            return 1
        fi

        # ── Native Ollama registry (no hf.co/ prefix) ────────────────────────
        if [[ "$model" != hf.co/* ]]; then
            echo "  Checking: $model"
            $ollama_cmd pull --force "$model"
            return $?
        fi

        # ── HuggingFace model ───────────────────────────────────────────────
        local repo_id="${model#hf.co/}"
        local actual_repo=""
        local filename=""
        local glob_pattern=""
        local ollama_name=""
        local gated="false"

        case "$repo_id" in
            AlicanKiraz0/Cybersecurity-BaronLLM_Offensive_Security_LLM_Q6_K_GGUF)
                actual_repo="AlicanKiraz0/Cybersecurity-BaronLLM_Offensive_Security_LLM_Q6_K_GGUF"
                filename="baronllm-llama3.1-v1-q6_k.gguf"
                ollama_name="baronllm:q6_k"
                gated="true"
                ;;
            segolilylabs/Lily-Cybersecurity-7B-v0.2-GGUF)
                actual_repo="segolilylabs/Lily-Cybersecurity-7B-v0.2-GGUF"
                filename="Lily-7B-Instruct-v0.2.Q4_K_M.gguf"
                ollama_name="lily-cybersecurity:7b-q4_k_m"
                ;;
            cognitivecomputations/Dolphin3.0-R1-Mistral-24B-GGUF)
                actual_repo="bartowski/cognitivecomputations_Dolphin3.0-R1-Mistral-24B-GGUF"
                filename="cognitivecomputations_Dolphin3.0-R1-Mistral-24B-Q4_K_M.gguf"
                ollama_name="dolphin3-r1-mistral:24b-q4_k_m"
                ;;
            WhiteRabbitNeo/WhiteRabbitNeo-33B-v1.5-GGUF)
                actual_repo="dranger003/WhiteRabbitNeo-33B-v1.5-iMat.GGUF"
                filename="ggml-whiterabbitneo-33b-v1.5-q4_k_m.gguf"
                ollama_name="whiterabbitneo:33b-v1.5-q4_k_m"
                ;;
            mradermacher/OmniCoder-2-9B-GGUF)
                actual_repo="mradermacher/OmniCoder-2-9B-GGUF"
                filename="OmniCoder-2-9B.Q4_K_M.gguf"
                ollama_name="omnicoder2:9b-q4_k_m"
                ;;
            deepseek-ai/DeepSeek-R1-32B-GGUF)
                actual_repo="bartowski/DeepSeek-R1-Distill-Qwen-32B-GGUF"
                filename="DeepSeek-R1-Distill-Qwen-32B-Q4_K_M.gguf"
                ollama_name="deepseek-r1:32b-q4_k_m"
                ;;
            Jiunsong/supergemma4-26b-uncensored-gguf-v2)
                actual_repo="Jiunsong/supergemma4-26b-uncensored-gguf-v2"
                filename="supergemma4-26b-uncensored-fast-v2-Q4_K_M.gguf"
                ollama_name="supergemma4-26b-uncensored:q4_k_m"
                ;;
            cognitivecomputations/dolphin-3-llama3-70b-GGUF)
                actual_repo="bartowski/dolphin-2.9.1-llama3-70b-GGUF"
                filename="dolphin-2.9.1-llama3-70b-Q4_K_M.gguf"
                ollama_name="dolphin-llama3:70b-q4_k_m"
                ;;
            meta-llama/Meta-Llama-3.3-70B-GGUF)
                actual_repo="bartowski/Llama-3.3-70B-Instruct-GGUF"
                filename="Llama-3.3-70B-Instruct-Q4_K_M.gguf"
                ollama_name="llama3.3:70b-q4_k_m"
                ;;
            *)
                echo "  ⚠️  No verified spec for $repo_id — attempting direct ollama pull"
                $ollama_cmd pull --force "$model"
                return $?
                ;;
        esac

        if [ "$gated" = "true" ] && [ -z "${HF_TOKEN:-}" ]; then
            echo "  ❌ $actual_repo requires HF_TOKEN (gated repo)"
            return 1
        fi

        _ensure_hf_cli

        echo "  Checking for updates: https://huggingface.co/$actual_repo"
        local _hf_err
        _hf_err=$(mktemp)
        local gguf_path=""
        if [ -n "$filename" ]; then
            gguf_path=$(HF_TOKEN="${HF_TOKEN:-}" \
                DL_REPO="$actual_repo" \
                DL_FILE="$filename" \
                python3 -W ignore -c "
import os, sys, warnings
warnings.filterwarnings('ignore')
from huggingface_hub import hf_hub_download
token = os.environ.get('HF_TOKEN') or None
try:
    path = hf_hub_download(
        repo_id=os.environ['DL_REPO'],
        filename=os.environ['DL_FILE'],
        token=token,
    )
    print(path)
except Exception as e:
    print(f'ERROR: {type(e).__name__}: {e}', file=sys.stderr)
    sys.exit(1)
" 2>"$_hf_err")
        fi

        if [ -z "$gguf_path" ] || [ ! -f "$gguf_path" ]; then
            echo "  ❌ Download failed for $actual_repo"
            [ -s "$_hf_err" ] && echo "  Error detail: $(cat "$_hf_err")"
            rm -f "$_hf_err"
            return 1
        fi
        rm -f "$_hf_err"
        echo "  ✅ Ready: $(basename "$gguf_path")"
        echo "  Importing as: $ollama_name"

        local modelfile
        modelfile=$(mktemp)
        printf 'FROM %s\nPARAMETER temperature 0.7\nPARAMETER num_ctx 8192\n' "$gguf_path" > "$modelfile"

        if $ollama_cmd create --force "$ollama_name" -f "$modelfile"; then
            echo "  ✅ Refreshed: $ollama_name"
            rm -f "$modelfile"
            return 0
        else
            echo "  ❌ ollama create --force failed"
            rm -f "$modelfile"
            return 1
        fi
    }

    # ── HuggingFace CLI availability ──────────────────────────────────────────
    _ensure_hf_cli() {
        # Check importability via python3 — avoids PATH issues with the binary
        if ! python3 -c "import huggingface_hub" &>/dev/null 2>&1; then
            echo "  Installing huggingface_hub..."
            pip3 install "huggingface_hub>=0.28" --quiet --break-system-packages 2>/dev/null || \
            pip3 install "huggingface_hub>=0.28" --quiet
        fi
        # Authenticate if token provided — use python API (no binary PATH needed)
        if [ -n "${HF_TOKEN:-}" ]; then
            python3 -W ignore -c "
from huggingface_hub import login
import warnings; warnings.filterwarnings('ignore')
try:
    login(token='${HF_TOKEN}', add_to_git_credential=False)
except Exception:
    pass
" 2>/dev/null || true
        fi
    }

    # ── Main model pull function ──────────────────────────────────────────────
    # Routes hf.co/ models through huggingface-cli + ollama create (bypasses
    # Ollama's broken cross-host auth redirect for HuggingFace models).
    # Native Ollama registry models use ollama pull directly.
    _pull_model() {
        local model="$1"
        local ollama_cmd
        ollama_cmd=$(_ollama_cmd)

        if [ -z "$ollama_cmd" ]; then
            echo "  ❌ No Ollama available. Run: ./launch.sh install-ollama"
            return 1
        fi

        # ── Native Ollama registry (no hf.co/ prefix) ────────────────────────
        # Always run pull — Ollama checks the registry and downloads only
        # changed layers; prints "already up to date" when nothing changed.
        if [[ "$model" != hf.co/* ]]; then
            $ollama_cmd pull "$model"
            return $?
        fi

        # ── HuggingFace model: download via Python huggingface_hub + import ──
        # This bypasses Ollama's broken cross-host auth redirect.
        # Uses snapshot_download() which correctly returns the actual cache path
        # regardless of ~/.cache vs --local-dir quirks.

        local repo_id="${model#hf.co/}"

        # ── Per-model spec: actual_repo, filename (or glob), ollama_name ─────
        local actual_repo=""
        local filename=""       # exact filename — preferred
        local glob_pattern=""   # fallback when exact name unverifiable
        local ollama_name=""
        local gated="false"

        case "$repo_id" in
            # ── Security models ──────────────────────────────────────────────
            AlicanKiraz0/Cybersecurity-BaronLLM_Offensive_Security_LLM_Q6_K_GGUF)
                # Gated: accept terms at https://huggingface.co/AlicanKiraz0/Cybersecurity-BaronLLM_Offensive_Security_LLM_Q6_K_GGUF
                actual_repo="AlicanKiraz0/Cybersecurity-BaronLLM_Offensive_Security_LLM_Q6_K_GGUF"
                filename="baronllm-llama3.1-v1-q6_k.gguf"
                ollama_name="baronllm:q6_k"
                gated="true"
                ;;
            segolilylabs/Lily-Cybersecurity-7B-v0.2-GGUF)
                # Source: https://huggingface.co/segolilylabs/Lily-Cybersecurity-7B-v0.2-GGUF
                actual_repo="segolilylabs/Lily-Cybersecurity-7B-v0.2-GGUF"
                filename="Lily-7B-Instruct-v0.2.Q4_K_M.gguf"
                ollama_name="lily-cybersecurity:7b-q4_k_m"
                ;;
            cognitivecomputations/Dolphin3.0-R1-Mistral-24B-GGUF)
                # Source: https://huggingface.co/bartowski/cognitivecomputations_Dolphin3.0-R1-Mistral-24B-GGUF/tree/main
                actual_repo="bartowski/cognitivecomputations_Dolphin3.0-R1-Mistral-24B-GGUF"
                filename="cognitivecomputations_Dolphin3.0-R1-Mistral-24B-Q4_K_M.gguf"
                ollama_name="dolphin3-r1-mistral:24b-q4_k_m"
                ;;
            WhiteRabbitNeo/WhiteRabbitNeo-33B-v1.5-GGUF)
                # Source: https://huggingface.co/dranger003/WhiteRabbitNeo-33B-v1.5-iMat.GGUF
                # Q4_K_M imatrix quant — 19.9 GB
                actual_repo="dranger003/WhiteRabbitNeo-33B-v1.5-iMat.GGUF"
                filename="ggml-whiterabbitneo-33b-v1.5-q4_k_m.gguf"
                ollama_name="whiterabbitneo:33b-v1.5-q4_k_m"
                ;;

            # ── Coding models ────────────────────────────────────────────────
            mradermacher/OmniCoder-2-9B-GGUF)
                # Source: https://huggingface.co/mradermacher/OmniCoder-2-9B-GGUF
                # V6 bench candidate (TASK_MODEL_REFRESH_V6). Qwen3.5-9B SFT on
                # agentic traces. v2 fixes v1's repetition loops + bloated thinking.
                actual_repo="mradermacher/OmniCoder-2-9B-GGUF"
                filename="OmniCoder-2-9B.Q4_K_M.gguf"
                ollama_name="omnicoder2:9b-q4_k_m"
                ;;
            MiniMaxAI/MiniMax-M2.1-GGUF)
                # Q4_K_M = 138 GB — does not fit in 48 GB unified memory
                echo "  ⚠️  Skipping MiniMax-M2.1: smallest useful quant is 138 GB (requires ~160 GB RAM)"
                echo "     To pull manually if you have sufficient RAM:"
                echo "     hf hub download bartowski/MiniMaxAI_MiniMax-M2.1-GGUF --include 'MiniMaxAI_MiniMax-M2.1-Q4_K_M.gguf'"
                return 0
                ;;

            # ── Reasoning models ─────────────────────────────────────────────
            deepseek-ai/DeepSeek-R1-32B-GGUF)
                # NOTE: deepseek-ai/DeepSeek-R1-32B-GGUF does NOT exist on HuggingFace.
                # The actual model is DeepSeek-R1-Distill-Qwen-32B.
                # Source: https://huggingface.co/bartowski/DeepSeek-R1-Distill-Qwen-32B-GGUF
                actual_repo="bartowski/DeepSeek-R1-Distill-Qwen-32B-GGUF"
                filename="DeepSeek-R1-Distill-Qwen-32B-Q4_K_M.gguf"
                ollama_name="deepseek-r1:32b-q4_k_m"
                ;;
            Jiunsong/supergemma4-26b-uncensored-gguf-v2)
                # Source: https://huggingface.co/Jiunsong/supergemma4-26b-uncensored-gguf-v2
                # Gemma 4 26B A4B MoE uncensored, Q4_K_M, ~17GB
                actual_repo="Jiunsong/supergemma4-26b-uncensored-gguf-v2"
                filename="supergemma4-26b-uncensored-fast-v2-Q4_K_M.gguf"
                ollama_name="supergemma4-26b-uncensored:q4_k_m"
                ;;

            # ── Heavy 70B models (PULL_HEAVY=true) ───────────────────────────
            cognitivecomputations/dolphin-3-llama3-70b-GGUF)
                # No reliable GGUF hosting for this exact repo.
                # Source: https://huggingface.co/bartowski/dolphin-2.9.1-llama-3-70b-GGUF
                actual_repo="bartowski/dolphin-2.9.1-llama-3-70b-GGUF"
                filename="dolphin-2.9.1-llama-3-70b-Q4_K_M.gguf"
                ollama_name="dolphin-llama3:70b-q4_k_m"
                ;;
            meta-llama/Meta-Llama-3.3-70B-GGUF)
                # Gated at meta-llama; use bartowski's public rehost.
                # Source: https://huggingface.co/bartowski/Llama-3.3-70B-Instruct-GGUF
                actual_repo="bartowski/Llama-3.3-70B-Instruct-GGUF"
                filename="Llama-3.3-70B-Instruct-Q4_K_M.gguf"
                ollama_name="llama3.3:70b-q4_k_m"
                ;;

            *)
                echo "  ⚠️  No verified spec for $repo_id — attempting direct ollama pull"
                echo "     (May fail due to Ollama hf.co auth redirect issue)"
                $ollama_cmd pull "$model"
                return $?
                ;;
        esac

        # ── Skip if already registered in Ollama ─────────────────────────────
        if _model_exists "$ollama_name"; then
            echo "  ✅ Already in Ollama as $ollama_name — skipping"
            return 0
        fi

        # ── Token check for gated repos ───────────────────────────────────────
        if [ "$gated" = "true" ] && [ -z "${HF_TOKEN:-}" ]; then
            echo "  ❌ $actual_repo requires HF_TOKEN (gated repo)"
            echo "     1. Accept terms: https://huggingface.co/$actual_repo"
            echo "     2. Create token: https://huggingface.co/settings/tokens (Read scope)"
            echo "     3. Add to .env:  HF_TOKEN=hf_..."
            return 1
        fi

        # ── Ensure huggingface_hub is installed ───────────────────────────────
        _ensure_hf_cli

        # ── Download via Python snapshot_download ─────────────────────────────
        # hf_hub_download uses ~/.cache/huggingface/hub/ as a content-addressed
        # cache. On subsequent calls it checks the remote ETag and returns the
        # cached path without re-downloading if the file is unchanged.

        echo "  Fetching from HuggingFace (cached if unchanged): $actual_repo"

        local _hf_err
        _hf_err=$(mktemp)
        local gguf_path=""
        if [ -n "$filename" ]; then
            echo "  File: $filename"
            gguf_path=$(HF_TOKEN="${HF_TOKEN:-}" \
                DL_REPO="$actual_repo" \
                DL_FILE="$filename" \
                python3 -W ignore -c "
import os, sys, warnings
warnings.filterwarnings('ignore')
from huggingface_hub import hf_hub_download
token = os.environ.get('HF_TOKEN') or None
try:
    path = hf_hub_download(
        repo_id=os.environ['DL_REPO'],
        filename=os.environ['DL_FILE'],
        token=token,
    )
    print(path)
except Exception as e:
    print(f'ERROR: {type(e).__name__}: {e}', file=sys.stderr)
    sys.exit(1)
" 2>"$_hf_err")
        elif [ -n "$glob_pattern" ]; then
            echo "  Pattern: $glob_pattern (listing repo to find file)"
            gguf_path=$(HF_TOKEN="${HF_TOKEN:-}" \
                DL_REPO="$actual_repo" \
                DL_GLOB="$glob_pattern" \
                python3 -W ignore -c "
import os, sys, fnmatch, warnings
warnings.filterwarnings('ignore')
from huggingface_hub import hf_hub_download, list_repo_files
token = os.environ.get('HF_TOKEN') or None
try:
    files = list(list_repo_files(os.environ['DL_REPO'], token=token))
    pat = os.environ['DL_GLOB']
    # Case-insensitive match to handle repos that use lowercase quant names
    matches = [f for f in files if fnmatch.fnmatch(f.lower(), pat.lower()) and f.endswith('.gguf')]
    if not matches:
        print(f'ERROR: no .gguf files matching {pat} in repo. Available: {[f for f in files if f.endswith(\".gguf\")]}', file=sys.stderr)
        sys.exit(1)
    target = next((f for f in matches if 'q4_k_m.gguf' in f.lower()), matches[0])
    path = hf_hub_download(
        repo_id=os.environ['DL_REPO'],
        filename=target,
        token=token,
    )
    print(path)
except Exception as e:
    print(f'ERROR: {type(e).__name__}: {e}', file=sys.stderr)
    sys.exit(1)
" 2>"$_hf_err")
        fi

        if [ -z "$gguf_path" ] || [ ! -f "$gguf_path" ]; then
            echo "  ❌ Download failed for $actual_repo"
            [ -s "$_hf_err" ] && echo "  Error detail: $(cat "$_hf_err")"
            rm -f "$_hf_err"
            echo "     Retry manually:"
            echo "       hf hub download $actual_repo ${filename:-} --local-dir ~/Downloads"
            echo "     Then import: ./launch.sh import-gguf ~/Downloads/${filename:-model.gguf} $ollama_name"
            return 1
        fi
        rm -f "$_hf_err"

        echo "  ✅ Ready: $(basename "$gguf_path")"
        echo "  Importing as: $ollama_name"

        local modelfile
        modelfile=$(mktemp)
        printf 'FROM %s\nPARAMETER temperature 0.7\nPARAMETER num_ctx 8192\n' "$gguf_path" > "$modelfile"

        if $ollama_cmd create "$ollama_name" -f "$modelfile"; then
            echo "  ✅ Imported: $ollama_name"
            rm -f "$modelfile"
            return 0
        else
            echo "  ❌ ollama create failed — GGUF kept at: $gguf_path"
            rm -f "$modelfile"
            return 1
        fi
    }

    echo "=== Portal 5: Pulling AI models ==="
    echo "This may take 30-90 minutes depending on connection speed."
    echo ""

    # ── HuggingFace authentication — required for hf.co/ models ─────────────
    echo "[portal-5] ℹ️  HuggingFace models: using hf hub download (bypasses Ollama auth issues)"
    echo "   For gated models (BaronLLM etc.), you must first accept terms at huggingface.co"
    echo "   then set HF_TOKEN in .env:"
    echo "     1. https://huggingface.co/<repo> → Accept conditions"
    echo "     2. https://huggingface.co/settings/tokens → Create token (read scope)"
    echo "     3. Add to .env:  HF_TOKEN=hf_..."
    echo ""

    MODELS=(
        # ── Core ──────────────────────────────────────────────────────────
        "${DEFAULT_MODEL:-dolphin-llama3:8b}"
        "huihui_ai/qwen3.5-abliterated:9b"   # NEW: AUTO + general line 1 (uncensored, tool-capable)
        "hf.co/QuantFactory/Llama-3.2-3B-Instruct-abliterated-GGUF"
        "nomic-embed-text:latest"
        # ── Security ─────────────────────────────────────────────────────
        "hf.co/AlicanKiraz0/Cybersecurity-BaronLLM_Offensive_Security_LLM_Q6_K_GGUF"
        "hf.co/segolilylabs/Lily-Cybersecurity-7B-v0.2-GGUF"
        "hf.co/cognitivecomputations/Dolphin3.0-R1-Mistral-24B-GGUF"
        "xploiter/the-xploiter"
        "hf.co/WhiteRabbitNeo/WhiteRabbitNeo-33B-v1.5-GGUF"
        "huihui_ai/baronllm-abliterated"
        "lazarevtill/Llama-3-WhiteRabbitNeo-8B-v2.0:q4_0"
        # ── Coding ───────────────────────────────────────────────────────
        "qwen3.5:9b"                   # Fast dense: 8-12GB, ~30-50 t/s on M4
        "qwen3-coder:30b"              # 30B-A3B MoE (3B active), 19GB
        "deepseek-coder-v2:16b-lite-instruct-q4_K_M"
        "devstral:24b"
        "granite4.1:8b"                # backfill: auto-video primary (de96984), general line 4
        "granite4.1:30b"               # backfill: ollama-reasoning fallback line 6
        # ── Reasoning / Research ──────────────────────────────────────────
        "hf.co/deepseek-ai/DeepSeek-R1-32B-GGUF"
        "gpt-oss:20b"
        "huihui_ai/tongyi-deepresearch-abliterated"
        "hf.co/Jiunsong/supergemma4-26b-uncensored-gguf-v2"   # ~17GB — Gemma 4 26B MoE uncensored, tool-use, Google lineage
        # ── Vision ───────────────────────────────────────────────────────
        "qwen3-vl:32b"
        "llava:7b"
        # ── V6 adds (TASK_MODEL_REFRESH_V6) ──────────────────────────────
        "huihui_ai/Qwen3.6-abliterated:27b"                     # ~20GB Q4 — Qwen3.6 35B-A3B abliterated, lineage successor to qwen3.5-abliterated:9b
        "hf.co/mradermacher/OmniCoder-2-9B-GGUF"                # ~5.7GB — Qwen3.5-9B SFT on agentic traces (v2 fixes v1's known issues)
    )

    total=${#MODELS[@]}
    count=0
    failed=0
    for model in "${MODELS[@]}"; do
        count=$((count + 1))
        echo "[$count/$total] $model"
        if _pull_model "$model"; then
            echo "  ✅ Done"
        else
            failed=$((failed + 1))
        fi
        echo ""
    done

    # Heavy 70B models — gated behind PULL_HEAVY=true
    if [ "${PULL_HEAVY:-false}" = "true" ]; then
        echo "Pulling heavy 70B models (PULL_HEAVY=true)..."
        for model in \
            "hf.co/cognitivecomputations/dolphin-3-llama3-70b-GGUF" \
            "hf.co/meta-llama/Meta-Llama-3.3-70B-GGUF"; do
            echo "  Pulling: $model (~35GB)"
            _pull_model "$model" && echo "  ✅ Done" || { echo "  ❌ Failed"; failed=$((failed + 1)); }
        done
    else
        echo "Skipping 70B models (set PULL_HEAVY=true in .env to pull ~35GB models)"
        echo "  - hf.co/cognitivecomputations/dolphin-3-llama3-70b-GGUF"
        echo "  - hf.co/meta-llama/Meta-Llama-3.3-70B-GGUF"
    fi

    echo ""
    echo "=== Pull complete: $((total - failed))/$total succeeded ==="
}

# Deprecated: delegated to ``portal models refresh`` in portal_pipeline/cli.py (M5 Stage 2).
# Retained for parity; remove in next M5 pass.
_launch_refresh_models() {
    set -a; source "$ENV_FILE" 2>/dev/null || true; set +a

    _ollama_cmd() {
        if command -v ollama &>/dev/null && curl -s http://localhost:11434/api/tags &>/dev/null 2>&1; then
            echo "ollama"
        elif docker ps --format '{{.Names}}' 2>/dev/null | grep -q "^portal5-ollama$"; then
            echo "docker exec portal5-ollama ollama"
        else
            echo ""
        fi
    }

    _ensure_hf_cli() {
        if ! python3 -c "import huggingface_hub" &>/dev/null 2>&1; then
            echo "  Installing huggingface_hub..."
            pip3 install "huggingface_hub>=0.28" --quiet --break-system-packages 2>/dev/null || \
            pip3 install "huggingface_hub>=0.28" --quiet
        fi
        if [ -n "${HF_TOKEN:-}" ]; then
            python3 -W ignore -c "
from huggingface_hub import login
import warnings; warnings.filterwarnings('ignore')
try:
    login(token='${HF_TOKEN}', add_to_git_credential=False)
except Exception:
    pass
" 2>/dev/null || true
        fi
    }

    _refresh_model() {
        local model="$1"
        local ollama_cmd
        ollama_cmd=$(_ollama_cmd)

        if [ -z "$ollama_cmd" ]; then
            echo "  ❌ No Ollama available. Run: ./launch.sh install-ollama"
            return 1
        fi

        # Native Ollama registry — pull --force checks registry and re-imports changed layers
        if [[ "$model" != hf.co/* ]]; then
            $ollama_cmd pull "$model"
            return $?
        fi

        local repo_id="${model#hf.co/}"
        local actual_repo="" filename="" ollama_name="" gated="false"

        case "$repo_id" in
            AlicanKiraz0/Cybersecurity-BaronLLM_Offensive_Security_LLM_Q6_K_GGUF)
                actual_repo="AlicanKiraz0/Cybersecurity-BaronLLM_Offensive_Security_LLM_Q6_K_GGUF"
                filename="baronllm-llama3.1-v1-q6_k.gguf"
                ollama_name="baronllm:q6_k"
                gated="true"
                ;;
            segolilylabs/Lily-Cybersecurity-7B-v0.2-GGUF)
                actual_repo="segolilylabs/Lily-Cybersecurity-7B-v0.2-GGUF"
                filename="Lily-7B-Instruct-v0.2.Q4_K_M.gguf"
                ollama_name="lily-cybersecurity:7b-q4_k_m"
                ;;
            cognitivecomputations/Dolphin3.0-R1-Mistral-24B-GGUF)
                actual_repo="bartowski/cognitivecomputations_Dolphin3.0-R1-Mistral-24B-GGUF"
                filename="cognitivecomputations_Dolphin3.0-R1-Mistral-24B-Q4_K_M.gguf"
                ollama_name="dolphin3-r1-mistral:24b-q4_k_m"
                ;;
            WhiteRabbitNeo/WhiteRabbitNeo-33B-v1.5-GGUF)
                actual_repo="dranger003/WhiteRabbitNeo-33B-v1.5-iMat.GGUF"
                filename="ggml-whiterabbitneo-33b-v1.5-q4_k_m.gguf"
                ollama_name="whiterabbitneo:33b-v1.5-q4_k_m"
                ;;
            mradermacher/OmniCoder-2-9B-GGUF)
                actual_repo="mradermacher/OmniCoder-2-9B-GGUF"
                filename="OmniCoder-2-9B.Q4_K_M.gguf"
                ollama_name="omnicoder2:9b-q4_k_m"
                ;;
            deepseek-ai/DeepSeek-R1-32B-GGUF)
                actual_repo="bartowski/DeepSeek-R1-Distill-Qwen-32B-GGUF"
                filename="DeepSeek-R1-Distill-Qwen-32B-Q4_K_M.gguf"
                ollama_name="deepseek-r1:32b-q4_k_m"
                ;;
            Jiunsong/supergemma4-26b-uncensored-gguf-v2)
                actual_repo="Jiunsong/supergemma4-26b-uncensored-gguf-v2"
                filename="supergemma4-26b-uncensored-fast-v2-Q4_K_M.gguf"
                ollama_name="supergemma4-26b-uncensored:q4_k_m"
                ;;
            cognitivecomputations/dolphin-3-llama3-70b-GGUF)
                actual_repo="bartowski/dolphin-2.9.1-llama-3-70b-GGUF"
                filename="dolphin-2.9.1-llama-3-70b-Q4_K_M.gguf"
                ollama_name="dolphin-llama3:70b-q4_k_m"
                ;;
            meta-llama/Meta-Llama-3.3-70B-GGUF)
                actual_repo="bartowski/Llama-3.3-70B-Instruct-GGUF"
                filename="Llama-3.3-70B-Instruct-Q4_K_M.gguf"
                ollama_name="llama3.3:70b-q4_k_m"
                ;;
            *)
                echo "  ⚠️  No verified spec for $repo_id — attempting direct ollama pull"
                $ollama_cmd pull "$model"
                return $?
                ;;
        esac

        if [ "$gated" = "true" ] && [ -z "${HF_TOKEN:-}" ]; then
            echo "  ❌ $actual_repo requires HF_TOKEN (gated repo)"
            return 1
        fi

        _ensure_hf_cli

        echo "  Checking for updates: https://huggingface.co/$actual_repo"
        local _hf_err
        _hf_err=$(mktemp)
        local gguf_path
        gguf_path=$(HF_TOKEN="${HF_TOKEN:-}" \
            DL_REPO="$actual_repo" \
            DL_FILE="$filename" \
            python3 -W ignore -c "
import os, sys, warnings
warnings.filterwarnings('ignore')
from huggingface_hub import hf_hub_download
token = os.environ.get('HF_TOKEN') or None
try:
    path = hf_hub_download(
        repo_id=os.environ['DL_REPO'],
        filename=os.environ['DL_FILE'],
        token=token,
    )
    print(path)
except Exception as e:
    print(f'ERROR: {type(e).__name__}: {e}', file=sys.stderr)
    sys.exit(1)
" 2>"$_hf_err")

        if [ -z "$gguf_path" ] || [ ! -f "$gguf_path" ]; then
            echo "  ❌ Download failed for $actual_repo"
            [ -s "$_hf_err" ] && echo "  Error detail: $(cat "$_hf_err")"
            rm -f "$_hf_err"
            return 1
        fi
        rm -f "$_hf_err"

        echo "  ✅ Ready: $(basename "$gguf_path")"
        local modelfile
        modelfile=$(mktemp)
        printf 'FROM %s\nPARAMETER temperature 0.7\nPARAMETER num_ctx 8192\n' "$gguf_path" > "$modelfile"

        local ollama_cmd_bin
        ollama_cmd_bin=$(_ollama_cmd)
        if $ollama_cmd_bin create "$ollama_name" -f "$modelfile"; then
            echo "  ✅ Refreshed: $ollama_name"
            rm -f "$modelfile"
            return 0
        else
            echo "  ❌ ollama create failed"
            rm -f "$modelfile"
            return 1
        fi
    }

    echo "=== Portal 5: Refreshing models (only downloads changes) ==="
    echo "Each model will be checked — unchanged models will say 'up to date'."
    echo ""

    MODELS=(
        "${DEFAULT_MODEL:-dolphin-llama3:8b}"
        "huihui_ai/qwen3.5-abliterated:9b"   # NEW: AUTO + general line 1
        "hf.co/QuantFactory/Llama-3.2-3B-Instruct-abliterated-GGUF"
        "nomic-embed-text:latest"
        "hf.co/AlicanKiraz0/Cybersecurity-BaronLLM_Offensive_Security_LLM_Q6_K_GGUF"
        "hf.co/segolilylabs/Lily-Cybersecurity-7B-v0.2-GGUF"
        "hf.co/cognitivecomputations/Dolphin3.0-R1-Mistral-24B-GGUF"
        "xploiter/the-xploiter"
        "hf.co/WhiteRabbitNeo/WhiteRabbitNeo-33B-v1.5-GGUF"
        "huihui_ai/baronllm-abliterated"
        "lazarevtill/Llama-3-WhiteRabbitNeo-8B-v2.0:q4_0"
        "qwen3.5:9b"
        "qwen3-coder:30b"
        "deepseek-coder-v2:16b-lite-instruct-q4_K_M"
        "devstral:24b"
        "granite4.1:8b"                # backfill: auto-video primary
        "granite4.1:30b"               # backfill: ollama-reasoning fallback
        "hf.co/deepseek-ai/DeepSeek-R1-32B-GGUF"
        "gpt-oss:20b"
        "huihui_ai/tongyi-deepresearch-abliterated"
        "hf.co/Jiunsong/supergemma4-26b-uncensored-gguf-v2"
        "qwen3-vl:32b"
        "llava:7b"
    )

    if [ "${PULL_HEAVY:-false}" = "true" ]; then
        MODELS+=(
            "hf.co/cognitivecomputations/dolphin-3-llama3-70b-GGUF"
            "hf.co/meta-llama/Meta-Llama-3.3-70B-GGUF"
        )
    fi

    total=${#MODELS[@]}
    count=0
    failed=0
    for model in "${MODELS[@]}"; do
        count=$((count + 1))
        echo "[$count/$total] $model"
        if _refresh_model "$model"; then
            echo "  ✅ Done"
        else
            failed=$((failed + 1))
        fi
        echo ""
    done

    echo "=== Refresh complete: $((total - failed))/$total succeeded ==="
}

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

