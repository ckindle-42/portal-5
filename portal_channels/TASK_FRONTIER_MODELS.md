# TASK_FRONTIER_MODELS.md — Portal 5 Model Enhancement Implementation
# Coding Agent Execution File

**Version**: 1.0  
**Date**: April 9, 2026  
**Scope**: Add 4 new capabilities (embedding, reranker, OCR, GLM-5.1), roadmap 2 future items, roadmap speech pipeline upgrade  
**Protected files**: `portal_pipeline/router_pipe.py` model hints and WORKSPACES dict are READ-ONLY for this task. No workspace routing changes.

---

## Pre-Flight

```bash
# Clone fresh
git clone https://github.com/ckindle-42/portal-5.git && cd portal-5

# Read before writing
cat CLAUDE.md
cat P5_ROADMAP.md
cat config/backends.yaml
cat deploy/portal-5/docker-compose.yml | head -250
cat scripts/mlx-proxy.py | head -130
cat launch.sh | grep -n "pull-mlx\|MLX_MODELS\|HEAVY_MLX" | head -20
```

---

## Scope Boundaries

### IN SCOPE (implement now)
1. **Harrier-0.6B embedding service** — Add to docker-compose, configure Open WebUI RAG
2. **bge-reranker-v2-m3 reranker** — Add to docker-compose, configure Open WebUI RAG reranking
3. **GLM-OCR-bf16** — Add to MLX model pull list (host-side, not Docker)
4. **GLM-5.1-DQ4plus-q8** — Add to MLX HEAVY model pull list and backends.yaml

### IN SCOPE (roadmap only — no implementation)
5. Roadmap entry for `huihui_ai/qwen3.5-abliterated` Ollama upgrade
6. Roadmap entry for `HauhauCS/Qwen3.5-35B-A3B-Uncensored` MLX conversion
7. Roadmap entry for speech pipeline upgrade (mlx-audio Qwen3-TTS + Qwen3-ASR)

### OUT OF SCOPE
- No changes to `portal_pipeline/router_pipe.py` WORKSPACES dict or model hints
- No changes to persona YAML files
- No changes to workspace import JSONs
- No removal of existing models (all additions are additive)
- No changes to `scripts/mlx-proxy.py` server-type routing (GLM-OCR runs host-side via mlx_vlm, not through the proxy)

---

## File Modification Summary

| # | File | Action | Description |
|---|------|--------|-------------|
| 1 | `deploy/portal-5/docker-compose.yml` | EDIT | Add embedding + reranker service, update OWU RAG env vars |
| 2 | `config/backends.yaml` | EDIT | Add GLM-5.1 to MLX models list |
| 3 | `scripts/mlx-proxy.py` | EDIT | Add GLM-5.1 to MODEL_MEMORY dict |
| 4 | `launch.sh` | EDIT | Add GLM-5.1 to HEAVY_MLX_MODELS, add GLM-OCR to MLX_MODELS, add harrier/reranker pull commands |
| 5 | `CLAUDE.md` | EDIT | Add Harrier, reranker, GLM-OCR, GLM-5.1 to model catalog |
| 6 | `P5_ROADMAP.md` | EDIT | Add 3 roadmap entries (abliterated Qwen3.5, speech pipeline) |
| 7 | `docs/HOWTO.md` | EDIT | Add RAG embedding/reranker configuration section |

---

## Implementation

### 1. Embedding + Reranker Service (docker-compose.yml)

The embedding and reranker models run as a lightweight Python service using `sentence-transformers`. Open WebUI supports external OpenAI-compatible embedding endpoints.

**Find** the RAG configuration block in `deploy/portal-5/docker-compose.yml` (around line 152-162):

```yaml
      # ── RAG / Knowledge Base ────────────────────────────────────────────────
      # Uses Ollama for embeddings (local, no external API)
      - RAG_EMBEDDING_ENGINE=ollama
      - RAG_OLLAMA_BASE_URL=${OLLAMA_URL:-http://host.docker.internal:11434}
      - RAG_EMBEDDING_MODEL=nomic-embed-text:latest
      - ENABLE_RAG_LOCAL_WEB_FETCH=true
      - RAG_RERANKING_MODEL=
      - CHUNK_SIZE=1500
      - CHUNK_OVERLAP=100
      - PDF_EXTRACT_IMAGES=true
      - ENABLE_RAG_HYBRID_SEARCH=true
```

**Replace with:**

```yaml
      # ── RAG / Knowledge Base ────────────────────────────────────────────────
      # Harrier-0.6B embedding (Microsoft, SOTA MTEB-v2, 32K context, MIT license)
      # Served by portal5-embedding service on port 8917
      - RAG_EMBEDDING_ENGINE=openai
      - RAG_OPENAI_API_BASE_URL=http://portal5-embedding:8917/v1
      - RAG_OPENAI_API_KEY=portal-embedding
      - RAG_EMBEDDING_MODEL=microsoft/harrier-oss-v1-0.6b
      - ENABLE_RAG_LOCAL_WEB_FETCH=true
      # bge-reranker-v2-m3 (BAAI, cross-encoder reranker, ~0.6B)
      - RAG_RERANKING_MODEL=BAAI/bge-reranker-v2-m3
      - RAG_RERANKING_MODEL_TRUST_REMOTE_CODE=true
      - CHUNK_SIZE=1500
      - CHUNK_OVERLAP=100
      - PDF_EXTRACT_IMAGES=true
      - ENABLE_RAG_HYBRID_SEARCH=true
```

**Find** the memory embedding config (around line 164-166):

```yaml
      # ── Cross-Session Memory ────────────────────────────────────────────────
      - ENABLE_MEMORY_FEATURE=true
      - MEMORY_EMBEDDING_MODEL=nomic-embed-text:latest
```

**Replace with:**

```yaml
      # ── Cross-Session Memory ────────────────────────────────────────────────
      - ENABLE_MEMORY_FEATURE=true
      - MEMORY_EMBEDDING_MODEL=microsoft/harrier-oss-v1-0.6b
```

**Add** the embedding service definition. Find the `mcp-whisper` service block (around line 306) and add AFTER its closing block (after the healthcheck stanza):

```yaml
  # ── Embedding + Reranker Service ─────────────────────────────────────────
  # Microsoft Harrier-0.6B (SOTA embedding, 32K ctx, MIT license)
  # Serves OpenAI-compatible /v1/embeddings endpoint for Open WebUI RAG
  portal5-embedding:
    image: ghcr.io/huggingface/text-embeddings-inference:cpu-1.7
    container_name: portal5-embedding
    ports:
      - "127.0.0.1:${EMBEDDING_HOST_PORT:-8917}:8917"
    environment:
      - MODEL_ID=microsoft/harrier-oss-v1-0.6b
      - PORT=8917
      - MAX_CLIENT_BATCH_SIZE=32
      - MAX_BATCH_TOKENS=32768
    volumes:
      - portal5-hf-cache:/data
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8917/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 120s
    deploy:
      resources:
        limits:
          memory: 4G
```

**Verification:**

```bash
# Validate docker-compose syntax
cd deploy/portal-5 && docker compose config --quiet && echo "✅ docker-compose valid" || echo "❌ docker-compose invalid"

# Verify embedding service is defined
grep -c "portal5-embedding" deploy/portal-5/docker-compose.yml
# Expected: >= 3 (service name, container_name, healthcheck reference)

# Verify RAG config points to new embedding service
grep "RAG_EMBEDDING_ENGINE=openai" deploy/portal-5/docker-compose.yml
grep "harrier-oss-v1-0.6b" deploy/portal-5/docker-compose.yml
grep "bge-reranker-v2-m3" deploy/portal-5/docker-compose.yml
```

**Note on reranker**: Open WebUI's `RAG_RERANKING_MODEL` uses `sentence-transformers` internally when set — it downloads and runs the reranker model inside the Open WebUI container itself. No separate service needed for the reranker, only for the embedding model. The `portal5-embedding` service uses HuggingFace's `text-embeddings-inference` (TEI) container which is purpose-built for serving embedding models with an OpenAI-compatible API.

---

### 2. GLM-5.1 in backends.yaml

**Find** the MLX text-only model list in `config/backends.yaml` (the comment block starting with `# ── Claude 4.6 Opus Reasoning Distilled`):

```yaml
      - mlx-community/DeepSeek-R1-Distill-Qwen-32B-abliterated-4bit           # Uncensored reasoning (~18GB)
```

**Add AFTER that line:**

```yaml
      # ── Frontier Agentic Coder (Zhipu/GLM lineage) ────────────────────────
      - mlx-community/GLM-5.1-DQ4plus-q8                                       # GLM-5.1 frontier coder (~35-40GB, HEAVY, MIT, MoE 744B/40B active)
```

**Verification:**

```bash
python3 -c "import yaml; yaml.safe_load(open('config/backends.yaml')); print('✅ YAML valid')"
grep "GLM-5.1" config/backends.yaml
```

---

### 3. GLM-5.1 in MODEL_MEMORY (mlx-proxy.py)

**Find** in `scripts/mlx-proxy.py` the last entry before the VLM section:

```python
    "mlx-community/DeepSeek-R1-Distill-Qwen-32B-abliterated-4bit": 18.0,  # R1 Distill 32B 4bit (~18GB)
```

**Add AFTER that line:**

```python
    "mlx-community/GLM-5.1-DQ4plus-q8": 38.0,  # GLM-5.1 frontier coder DQ4+q8 (~38GB, HEAVY)
```

**Verification:**

```bash
python3 -c "
import ast, sys
with open('scripts/mlx-proxy.py') as f:
    content = f.read()
# Find MODEL_MEMORY dict
start = content.index('MODEL_MEMORY: dict[str, float] = {')
end = content.index('}', start) + 1
snippet = content[start:end].replace('MODEL_MEMORY: dict[str, float] = ', '')
d = ast.literal_eval(snippet)
assert 'mlx-community/GLM-5.1-DQ4plus-q8' in d, 'GLM-5.1 not in MODEL_MEMORY'
print(f'✅ MODEL_MEMORY has {len(d)} entries, GLM-5.1 = {d[\"mlx-community/GLM-5.1-DQ4plus-q8\"]}GB')
"
```

---

### 4. launch.sh Model Pull Updates

#### 4a. Add GLM-5.1 to HEAVY_MLX_MODELS

**Find** the HEAVY_MLX_MODELS array (around line 2401):

```bash
    HEAVY_MLX_MODELS=(
        "mlx-community/Llama-3.3-70B-Instruct-4bit"        # ~40GB — unload others first
    )
```

**Replace with:**

```bash
    HEAVY_MLX_MODELS=(
        "mlx-community/Llama-3.3-70B-Instruct-4bit"        # ~40GB — unload others first
        "mlx-community/GLM-5.1-DQ4plus-q8"                 # ~38GB — GLM-5.1 frontier agentic coder (MIT, Zhipu lineage)
    )
```

**Note**: There is a duplicate HEAVY_MLX_MODELS block (lines 2396 and 2401). Update BOTH occurrences.

#### 4b. Add GLM-OCR to MLX_MODELS

**Find** in the MLX_MODELS array, the Vision section:

```bash
        # Vision
        "mlx-community/Qwen3-VL-32B-Instruct-8bit"         # ~36GB
        "mlx-community/llava-1.5-7b-8bit"                  # ~8GB
```

**Add AFTER `llava` line:**

```bash
        # OCR (document ingestion)
        "mlx-community/GLM-OCR-bf16"                        # ~2GB — Zhipu GLM-OCR for scanned document ingestion
```

#### 4c. Add Harrier embedding pull to Ollama pull-models

The embedding model is pulled by the `portal5-embedding` Docker container automatically on first start (TEI pulls from HuggingFace Hub). However, for offline/pre-pull scenarios, add to the Ollama MODELS array.

**Find** in the MODELS array (around line 1562):

```bash
        "nomic-embed-text:latest"
```

**Add AFTER that line:**

```bash
        # Note: Harrier-0.6B is served by portal5-embedding container (TEI), not Ollama.
        # nomic-embed-text kept as fallback if embedding service is down.
```

No additional Ollama pull needed — TEI handles it. But keep nomic-embed-text as a degraded-mode fallback.

**Verification:**

```bash
bash -n launch.sh && echo "✅ launch.sh syntax valid" || echo "❌ launch.sh syntax error"
grep "GLM-5.1" launch.sh
grep "GLM-OCR" launch.sh
```

---

### 5. CLAUDE.md Model Catalog Updates

#### 5a. Add Embedding section

**Find** the heading `### Generation Models (ComfyUI / HuggingFace)` and add BEFORE it:

```markdown
### Embedding & Retrieval Models

| Model | Served By | Purpose | RAM |
|---|---|---|---|
| Harrier-OSS-v1-0.6B | portal5-embedding (TEI, :8917) | RAG embedding, 32K ctx, SOTA MTEB-v2, Microsoft lineage | ~1.2GB |
| bge-reranker-v2-m3 | Open WebUI internal (sentence-transformers) | Cross-encoder reranker for RAG result scoring | ~0.6GB |
| nomic-embed-text:latest | Ollama (fallback) | Legacy embedding fallback if embedding service is down | ~0.3GB |

### OCR Models

| Model | Server | Purpose | RAM |
|---|---|---|---|
| `mlx-community/GLM-OCR-bf16` | Host-side mlx_vlm | Scanned document OCR for compliance doc ingestion | ~2GB |
```

#### 5b. Add GLM-5.1 to MLX catalog

**Find** in the MLX model table, the row for `mlx-community/Llama-3.3-70B-Instruct-4bit`:

```markdown
| `mlx-community/Llama-3.3-70B-Instruct-4bit` | ~40GB | mlx_lm | Ollama only (3B) — unload others first |
```

**Add AFTER that row:**

```markdown
| `mlx-community/GLM-5.1-DQ4plus-q8` | ~38GB | mlx_lm | Ollama only (3B) — unload others first. HEAVY: frontier agentic coder, Zhipu/GLM lineage. |
```

#### 5c. Add GLM-OCR to MLX VLM section

**Find** in the MLX model table, after the `llava-1.5-7b-8bit` row:

```markdown
| `mlx-community/Llama-3.2-11B-Vision-Instruct-abliterated-4-bit` | ~7GB | mlx_vlm | ComfyUI + Ollama + Wan2.2 video |
```

**Add AFTER that row:**

```markdown
| `mlx-community/GLM-OCR-bf16` | ~2GB | mlx_vlm | Everything — OCR specialist for document ingestion |
```

**Verification:**

```bash
grep -c "harrier" CLAUDE.md   # Expected: >= 2
grep -c "GLM-5.1" CLAUDE.md   # Expected: >= 1
grep -c "GLM-OCR" CLAUDE.md   # Expected: >= 2
grep -c "bge-reranker" CLAUDE.md  # Expected: >= 1
```

---

### 6. Roadmap Entries (P5_ROADMAP.md)

**Find** the last row in the Future Considerations table (the line starting with `| P5-FUT-009`):

```markdown
| P5-FUT-009 | P2 | Model-size-aware admission control (MLX proxy) | DONE | DONE in v6.0.0. MODEL_MEMORY dict ...
```

**Add AFTER that row:**

```markdown
| P5-FUT-010 | P2 | Abliterated Qwen3.5 Ollama upgrade | FUTURE | Replace `qwen3.5:9b` and `deepseek-r1:32b-q4_k_m` Ollama slots with `huihui_ai/qwen3.5-abliterated` variants (same trusted provider as existing baronllm-abliterated and tongyi-deepresearch-abliterated). Sizes: 9B for coding/documents, 35B-A3B for reasoning/compliance. Uncensored — 0 refusals on standard abliteration benchmarks. |
| P5-FUT-011 | P2 | Uncensored Qwen3.5-35B-A3B MLX conversion | FUTURE | Self-convert `huihui-ai/Huihui-Qwen3.5-35B-A3B-abliterated` to MLX via `mlx_lm.convert` for `auto-compliance` primary slot. Replaces Jackrong Claude-4.6-Opus distillation with native uncensored Qwen3.5 (vision, thinking mode, 262K context). Alternatively use `HauhauCS/Qwen3.5-35B-A3B-Uncensored-HauhauCS-Aggressive` GGUF via Ollama as fallback. |
| P5-FUT-012 | P3 | Speech pipeline upgrade (mlx-audio) | FUTURE | Replace kokoro-onnx TTS MCP + faster-whisper ASR MCP with unified `mlx-audio` library. Enables: (1) Qwen3-TTS-12Hz-1.7B-CustomVoice — voice cloning from 3s audio, emotion/style control, 10 languages, streaming. (2) Qwen3-ASR-1.7B — MLX-native speech recognition replacing faster-whisper. (3) Qwen3-TTS-12Hz-1.7B-VoiceDesign — design voices from text descriptions. Models: ~0.8GB each (8-bit), ~6GB each (bf16). Requires refactoring `portal_mcp/generation/tts_mcp.py` and `portal_mcp/generation/whisper_mcp.py` to use `mlx_audio` API. Library: `pip install mlx-audio`. All models available at mlx-community. Apache 2.0. |
```

**Verification:**

```bash
grep "P5-FUT-010" P5_ROADMAP.md
grep "P5-FUT-011" P5_ROADMAP.md
grep "P5-FUT-012" P5_ROADMAP.md
grep "abliterated" P5_ROADMAP.md
grep "mlx-audio" P5_ROADMAP.md
```

---

### 7. docs/HOWTO.md — RAG Configuration Section

**Find** the end of the document (or an appropriate section near RAG/knowledge base topics) and **add**:

```markdown
## RAG Embedding & Reranking

Portal 5 v6.1+ uses Microsoft Harrier-0.6B as the primary embedding model for RAG, served by the `portal5-embedding` container (HuggingFace Text Embeddings Inference). This replaces the default Ollama `nomic-embed-text` with a SOTA embedding model that supports 32K context windows and 100+ languages.

**Architecture**: Open WebUI → portal5-embedding (:8917) → Harrier-0.6B embeddings → ChromaDB vector store → bge-reranker-v2-m3 cross-encoder reranking → results

**Configuration** (in docker-compose.yml, already set):
- `RAG_EMBEDDING_ENGINE=openai` — uses OpenAI-compatible API from TEI
- `RAG_OPENAI_API_BASE_URL=http://portal5-embedding:8917/v1`
- `RAG_EMBEDDING_MODEL=microsoft/harrier-oss-v1-0.6b`
- `RAG_RERANKING_MODEL=BAAI/bge-reranker-v2-m3`

**Fallback**: If the embedding service is unavailable, change `RAG_EMBEDDING_ENGINE=ollama` and `RAG_EMBEDDING_MODEL=nomic-embed-text:latest` in `.env` or docker-compose.yml to revert to Ollama-based embeddings.

**Memory impact**: The embedding service uses ~1.2GB. The reranker runs inside Open WebUI's process and uses ~0.6GB. Total: ~1.8GB always-on overhead.
```

**Verification:**

```bash
grep "Harrier" docs/HOWTO.md
grep "bge-reranker" docs/HOWTO.md
```

---

## Post-Implementation Validation

```bash
# 1. YAML/syntax validation
python3 -c "import yaml; yaml.safe_load(open('config/backends.yaml')); print('✅ backends.yaml')"
cd deploy/portal-5 && docker compose config --quiet && echo "✅ docker-compose.yml" && cd ../..
bash -n launch.sh && echo "✅ launch.sh"

# 2. Content validation
echo "--- Model catalog checks ---"
grep -c "GLM-5.1" config/backends.yaml CLAUDE.md scripts/mlx-proxy.py launch.sh
grep -c "GLM-OCR" CLAUDE.md launch.sh
grep -c "harrier" CLAUDE.md deploy/portal-5/docker-compose.yml docs/HOWTO.md
grep -c "bge-reranker" CLAUDE.md deploy/portal-5/docker-compose.yml docs/HOWTO.md

echo "--- Roadmap checks ---"
grep "P5-FUT-01[012]" P5_ROADMAP.md | wc -l  # Expected: 3

echo "--- Docker service check ---"
grep "portal5-embedding" deploy/portal-5/docker-compose.yml | wc -l  # Expected: >= 3
```

---

## Commit Message

```
feat: add embedding, reranker, OCR, GLM-5.1 frontier models

- Add portal5-embedding service (Microsoft Harrier-0.6B via TEI)
  for SOTA RAG embeddings replacing nomic-embed-text
- Configure bge-reranker-v2-m3 cross-encoder for two-stage RAG retrieval
- Add GLM-OCR-bf16 to MLX pull list for scanned document ingestion
- Add GLM-5.1-DQ4plus-q8 to HEAVY MLX slot (frontier agentic coder,
  Zhipu/GLM lineage, MIT license)
- Add MODEL_MEMORY entry for GLM-5.1 admission control
- Update CLAUDE.md model catalog with new models
- Add P5-FUT-010/011/012 roadmap entries:
  - Abliterated Qwen3.5 Ollama upgrade
  - Uncensored Qwen3.5-35B MLX conversion
  - Speech pipeline upgrade (mlx-audio Qwen3-TTS + Qwen3-ASR)
- Update docs/HOWTO.md with RAG embedding configuration

Memory impact: +1.8GB always-on (embedding + reranker)
Model rotation: +38GB HEAVY slot (GLM-5.1), +2GB standard (GLM-OCR)
```

---

## Rollback

```bash
git stash  # or
git checkout -- config/backends.yaml deploy/portal-5/docker-compose.yml scripts/mlx-proxy.py launch.sh CLAUDE.md P5_ROADMAP.md docs/HOWTO.md
```

---

*Task file for Claude Code execution. All find/replace blocks reference current v6.0.0 repo state.*
