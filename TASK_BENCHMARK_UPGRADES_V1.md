# TASK_BENCHMARK_UPGRADES_V1.md — Model Upgrades, MCP Tool, Benchmark Optimizations

```
Task:     Benchmark-driven model upgrades + new MCP security tool + OMLX roadmap
Version:  1
Status:   READY
Priority: P2
Scope:    Additive only — no removals without explicit direction
Prereqs:  Read CLAUDE.md first. Read config/backends.yaml, scripts/mlx-proxy.py,
          portal_pipeline/router_pipe.py, deploy/portal-5/docker-compose.yml,
          Dockerfile.mcp, config/personas/*.yaml before making any changes.
```

---

## Context

Benchmark Run 7+ (Grafana portal5_benchmarks dashboard) validated all 17 workspaces,
108/108 tests passed, pipeline routing overhead <3%. Analysis of recent HuggingFace
model releases identified three high-value model upgrades and one new MCP tool that
address specific gaps visible in the benchmark data:

1. The censored `gemma-4-26b-a4b-it-4bit` (~35 TPS) blocks security/creative workspaces
2. The Ollama reasoning group lacks non-Qwen/non-DeepSeek lineage diversity
3. Security workspaces have no structured vulnerability classification tool
4. The 26B MoE at ~35 TPS is underutilized for research routing vs 31B dense at ~20 TPS

**Validated facts** (from HuggingFace repos, not theory):
- `Jiunsong/supergemma4-26b-abliterated-multimodal-mlx-4bit`: 15.6GB total, MLX safetensors,
  `Image-Text-to-Text` pipeline (multimodal confirmed), `model_type: "gemma4"`,
  `Gemma4ForConditionalGeneration`, `image_token_id` + `boi_token_id` present,
  4-bit affine quantization group_size=64. Last updated 2026-04-17. 44 likes.
- `Jiunsong/supergemma4-26b-uncensored-gguf-v2`: 16.8GB single GGUF file,
  `supergemma4-26b-uncensored-fast-v2-Q4_K_M.gguf`, Q4_K_M quant. Updated 2026-04-20.
  47 likes. Ollama supports Gemma 4 architecture natively (`gemma4:26b` tag exists).
- `CIRCL/vulnerability-severity-classification-roberta-base`: 503MB, safetensors,
  RoBERTa-base, MIT license, 500 commits, 82% accuracy on 600K+ CVEs, labels:
  low/medium/high/critical. `transformers` already in Dockerfile.mcp. Retrained 2026-04-17.
- OBLITERATUS/gemma-4-E4B-it-OBLITERATED: **EXCLUDED** — tagged `Text Generation`
  (NOT `Image-Text-to-Text`), 15.9GB bfloat16 (NOT quantized, NOT MLX).
  Multimodal capability NOT preserved. Would require MLX conversion + quantization +
  multimodal verification. Too much risk for the VLM fallback slot.

---

## Task 1: Add Abliterated Gemma 4 26B-A4B MLX (Replace Censored Variant)

**Rationale**: Drop-in replacement — same architecture, same ~15GB, same mlx_vlm
compatibility. Removes refusals for security/creative/research workspaces that route
through this model. Google Gemma lineage (not Qwen).

### 1A: Update `scripts/mlx-proxy.py`

**File**: `scripts/mlx-proxy.py` (PROTECTED — read-only for tests, editable for this task)

In `ALL_MODELS` list, find:
```python
    "mlx-community/gemma-4-26b-a4b-it-4bit",  # Gemma 4 26B A4B MoE — vision, 256K ctx, #6 LMArena (~15GB)
```
Replace with:
```python
    "Jiunsong/supergemma4-26b-abliterated-multimodal-mlx-4bit",  # Gemma 4 26B A4B MoE abliterated — vision, 256K ctx, uncensored (~15GB)
```

In `VLM_MODELS` set, find:
```python
    "gemma-4-26b-a4b-it-4bit",  # Gemma 4 26B A4B MoE — vision, 256K ctx, ~15GB
```
Replace with:
```python
    "supergemma4-26b-abliterated-multimodal-mlx-4bit",  # Gemma 4 26B A4B MoE abliterated — vision, 256K ctx, uncensored ~15GB
```

In `MODEL_MEMORY` dict, find:
```python
    "mlx-community/gemma-4-26b-a4b-it-4bit": 15.0,  # Gemma 4 26B A4B MoE 4bit (~15GB)
```
Replace with:
```python
    "Jiunsong/supergemma4-26b-abliterated-multimodal-mlx-4bit": 15.0,  # Gemma 4 26B A4B MoE abliterated 4bit (~15GB)
```

### 1B: Update `config/backends.yaml`

**File**: `config/backends.yaml`

In the `mlx-apple-silicon` models list, find:
```yaml
      - mlx-community/gemma-4-26b-a4b-it-4bit             # Gemma 4 26B A4B MoE — vision+text, 256K ctx, #6 LMArena (~15GB)
```
Replace with:
```yaml
      - Jiunsong/supergemma4-26b-abliterated-multimodal-mlx-4bit  # Gemma 4 26B A4B MoE abliterated — vision+text, 256K ctx, uncensored (~15GB)
```

### 1C: No router_pipe.py changes needed

The current `mlx_model_hint` references for the 26B-A4B point to the 31B dense model
or other models — no workspace directly references `gemma-4-26b-a4b-it-4bit` as a hint.
The model is used through the VLM pool when the proxy selects it. No WORKSPACES changes.

### Verification

```bash
# Verify VLM_MODELS contains the new basename
python3 -c "
import ast, re
src = open('scripts/mlx-proxy.py').read()
m = re.search(r'VLM_MODELS\s*=\s*\{([^}]+)\}', src, re.DOTALL)
assert 'supergemma4-26b-abliterated-multimodal-mlx-4bit' in m.group(1), 'VLM_MODELS missing new model'
print('VLM_MODELS: OK')
"

# Verify MODEL_MEMORY has the entry
python3 -c "
import ast, re
src = open('scripts/mlx-proxy.py').read()
assert 'Jiunsong/supergemma4-26b-abliterated-multimodal-mlx-4bit' in src, 'MODEL_MEMORY missing'
print('MODEL_MEMORY: OK')
"

# Verify backends.yaml has the new model
grep -q 'supergemma4-26b-abliterated-multimodal-mlx-4bit' config/backends.yaml && echo "backends.yaml: OK"

# Verify old censored model is removed from all three locations
! grep -q 'gemma-4-26b-a4b-it-4bit' scripts/mlx-proxy.py && echo "mlx-proxy.py cleanup: OK"
! grep -q 'gemma-4-26b-a4b-it-4bit' config/backends.yaml && echo "backends.yaml cleanup: OK"

# Workspace consistency check
python3 -c "
import yaml
from portal_pipeline.router_pipe import WORKSPACES
cfg = yaml.safe_load(open('config/backends.yaml'))
pipe_ids = set(WORKSPACES.keys())
yaml_ids = set(cfg['workspace_routing'].keys())
assert pipe_ids == yaml_ids, f'Mismatch: pipe={pipe_ids-yaml_ids} yaml={yaml_ids-pipe_ids}'
print('Workspace IDs consistent')
"
```

### Pull Command (run on host)
```bash
# Pull the new MLX model weights BEFORE removing old ones (pull-before-delete)
huggingface-cli download Jiunsong/supergemma4-26b-abliterated-multimodal-mlx-4bit \
    --local-dir ~/mlx-models/Jiunsong/supergemma4-26b-abliterated-multimodal-mlx-4bit
# Verify download completed (should be ~15.6GB)
du -sh ~/mlx-models/Jiunsong/supergemma4-26b-abliterated-multimodal-mlx-4bit
# Only THEN remove old weights if desired (optional — keeping both costs 15GB disk)
```

### Rollback
Revert all three files to use `mlx-community/gemma-4-26b-a4b-it-4bit`. The old model
weights remain on disk until explicitly deleted.

### Commit
```
feat(models): replace censored gemma-4-26b-a4b with abliterated Jiunsong variant

Jiunsong/supergemma4-26b-abliterated-multimodal-mlx-4bit is a drop-in
replacement: same Gemma 4 26B-A4B architecture, same ~15GB at 4-bit,
same mlx_vlm multimodal capability (Image-Text-to-Text confirmed).
Zero refusals — addresses uncensored requirement for security, creative,
and research workspaces. Google Gemma lineage reduces Qwen overrepresentation.
```

---

## Task 2: Add Uncensored Gemma 4 26B GGUF to Ollama Reasoning Group

**Rationale**: The `ollama-reasoning` group currently has `deepseek-r1:32b-q4_k_m` (~12 TPS),
`gpt-oss:20b`, `dolphin-llama3:8b`, and `huihui_ai/tongyi-deepresearch-abliterated`.
All are Qwen or DeepSeek lineage except dolphin-llama3. Adding an uncensored Gemma 26B
provides Google-lineage diversity, tool-use capability, and likely faster inference than
the 32B dense DeepSeek-R1 (MoE with 4B active params vs 32B dense).

### 2A: Update `config/backends.yaml`

**File**: `config/backends.yaml`

In the `ollama-reasoning` models list, after `huihui_ai/tongyi-deepresearch-abliterated`,
add:
```yaml
      - hf.co/Jiunsong/supergemma4-26b-uncensored-gguf-v2  # Gemma 4 26B A4B MoE uncensored GGUF (~17GB, tool-use, reasoning, Google lineage)
```

### 2B: No router_pipe.py changes needed

The WORKSPACES dict and workspace_routing keys are unchanged. The new model is added
to an existing backend group — it becomes available as a fallback within the reasoning
routing tier. The workspace `model_hint` for `auto-reasoning` remains `deepseek-r1:32b-q4_k_m`
(the primary). The Gemma GGUF serves as an additional option in the group.

### Verification

```bash
# Verify backends.yaml has the new model in reasoning group
grep -A 10 'ollama-reasoning' config/backends.yaml | grep -q 'supergemma4-26b-uncensored-gguf-v2' && echo "backends.yaml reasoning: OK"

# Workspace consistency check (should still pass — no workspace_routing changes)
python3 -c "
import yaml
from portal_pipeline.router_pipe import WORKSPACES
cfg = yaml.safe_load(open('config/backends.yaml'))
pipe_ids = set(WORKSPACES.keys())
yaml_ids = set(cfg['workspace_routing'].keys())
assert pipe_ids == yaml_ids, f'Mismatch: pipe={pipe_ids-yaml_ids} yaml={yaml_ids-pipe_ids}'
print('Workspace IDs consistent')
"
```

### Pull Command (run on host)

```bash
# Import via Ollama's hf.co/ path — Ollama handles Gemma 4 architecture natively
# NOTE: This is a 16.8GB download. Verify disk space first.
ollama pull hf.co/Jiunsong/supergemma4-26b-uncensored-gguf-v2

# If hf.co/ import fails (some custom GGUF filenames don't auto-resolve),
# fall back to manual import:
# 1. Download GGUF
huggingface-cli download Jiunsong/supergemma4-26b-uncensored-gguf-v2 \
    supergemma4-26b-uncensored-fast-v2-Q4_K_M.gguf \
    --local-dir /tmp/supergemma4-import
# 2. Create Modelfile
cat > /tmp/supergemma4-import/Modelfile << 'EOF'
FROM /tmp/supergemma4-import/supergemma4-26b-uncensored-fast-v2-Q4_K_M.gguf
PARAMETER temperature 0.7
PARAMETER num_ctx 8192
EOF
# 3. Import
ollama create supergemma4-26b-uncensored:q4_k_m -f /tmp/supergemma4-import/Modelfile
# 4. Update backends.yaml model name to match: supergemma4-26b-uncensored:q4_k_m

# Verify
ollama list | grep -i supergemma
```

### Rollback
Remove the model line from `config/backends.yaml` `ollama-reasoning` group.
Run `ollama rm supergemma4-26b-uncensored:q4_k_m` (or the hf.co name) to free disk.

### Commit
```
feat(models): add uncensored Gemma 4 26B GGUF to Ollama reasoning group

Jiunsong/supergemma4-26b-uncensored-gguf-v2 (Q4_K_M, ~17GB) adds
Google Gemma lineage diversity to the reasoning tier. MoE architecture
(26B total, 4B active) provides faster inference than the 32B dense
DeepSeek-R1. Uncensored, tool-use capable, strong on logic benchmarks
(95.2 vs 86.9 baseline per model card).
```

---

## Task 3: Add CIRCL VLAI CVE Severity Classifier — New MCP Security Tool

**Rationale**: The security/blueteam workspaces lack structured vulnerability classification.
CIRCL's VLAI model (RoBERTa-base, 503MB, MIT license, 82% accuracy on 600K+ CVEs) provides
automated severity triage as an MCP tool. `transformers` and `torch` are already in
Dockerfile.mcp — zero additional pip installs needed.

### 3A: Create MCP Security Server

**File**: `portal_mcp/security/` (NEW directory)
**File**: `portal_mcp/security/__init__.py` (NEW, empty)
**File**: `portal_mcp/security/security_mcp.py` (NEW)

```python
"""Portal 5 — Security MCP Tool Server.

Provides vulnerability severity classification using CIRCL's VLAI RoBERTa model.
Port: 8919 (configurable via SECURITY_MCP_PORT or MCP_PORT env var)
"""

from __future__ import annotations

import logging
import os

import torch
from fastapi import FastAPI
from transformers import AutoModelForSequenceClassification, AutoTokenizer

# Vendored FastMCP
from portal_mcp.mcp_server.fastmcp import FastMCP

logger = logging.getLogger(__name__)

# ── Model Configuration ──────────────────────────────────────────────────────
_MODEL_NAME = "CIRCL/vulnerability-severity-classification-roberta-base"
_LABELS = ["low", "medium", "high", "critical"]

# Lazy-loaded globals (loaded on first tool call, not import time)
_tokenizer = None
_model = None


def _ensure_model():
    """Load the VLAI model on first use. Downloads from HuggingFace if not cached."""
    global _tokenizer, _model
    if _model is not None:
        return
    logger.info("Loading VLAI severity classifier: %s", _MODEL_NAME)
    _tokenizer = AutoTokenizer.from_pretrained(_MODEL_NAME)
    _model = AutoModelForSequenceClassification.from_pretrained(_MODEL_NAME)
    _model.eval()
    logger.info("VLAI model loaded successfully (%d labels)", len(_LABELS))


# ── MCP Server Setup ─────────────────────────────────────────────────────────
_port = int(os.environ.get("SECURITY_MCP_PORT") or os.environ.get("MCP_PORT", "8919"))

mcp = FastMCP(
    "Portal Security Tools",
    description="Vulnerability severity classification and security analysis tools",
)

app = FastAPI(title="Portal Security MCP", version="1.0.0")


@app.get("/health")
async def health():
    return {"status": "ok", "service": "security-mcp", "port": _port}


@mcp.tool()
def classify_vulnerability(description: str) -> dict:
    """Classify a vulnerability description into severity level (low/medium/high/critical).

    Uses CIRCL's VLAI model (RoBERTa-base, 82% accuracy, trained on 600K+ CVEs).
    Input: CVE or vulnerability description text.
    Returns: severity label, confidence score, and all class probabilities.

    Args:
        description: The vulnerability description text to classify.
                     Works best with CVE-style descriptions (1-3 sentences).
    """
    _ensure_model()

    inputs = _tokenizer(description, return_tensors="pt", truncation=True, padding=True, max_length=512)

    with torch.no_grad():
        outputs = _model(**inputs)
        probabilities = torch.nn.functional.softmax(outputs.logits, dim=-1)

    predicted_idx = torch.argmax(probabilities, dim=-1).item()
    confidence = probabilities[0][predicted_idx].item()

    return {
        "severity": _LABELS[predicted_idx],
        "confidence": round(confidence, 4),
        "probabilities": {
            label: round(prob.item(), 4)
            for label, prob in zip(_LABELS, probabilities[0])
        },
        "model": _MODEL_NAME,
    }


# ── Mount and Serve ──────────────────────────────────────────────────────────
# Mount the FastMCP SSE transport onto the FastAPI app
mcp.mount_to_fastapi(app)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=_port, log_level="info")
```

### 3B: Add Docker Compose Service

**File**: `deploy/portal-5/docker-compose.yml`

Add after the `mcp-sandbox` service block (before the `# FUTURE CLUSTER NODES` section
or similar):

```yaml
  # ── MCP: Security Tools (CVE severity classification) ──────────────────────
  mcp-security:
    build:
      context: ../..
      dockerfile: Dockerfile.mcp
    container_name: portal5-mcp-security
    restart: unless-stopped
    ports:
      - "127.0.0.1:${SECURITY_HOST_PORT:-8919}:8919"
    environment:
      - SECURITY_MCP_PORT=8919
      - MCP_PORT=8919
      - HF_HOME=/app/data/hf_cache
    command: ["python", "-m", "portal_mcp.security.security_mcp"]
    volumes:
      - security-hf-cache:/app/data/hf_cache
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8919/health"]
      interval: 30s
      timeout: 5s
      start_period: 120s
      retries: 3
```

Add volume at the bottom of the `volumes:` section:
```yaml
  security-hf-cache:
```

NOTE: `start_period: 120s` gives time for the first model download from HuggingFace
(~503MB, one-time). Subsequent starts use the cached volume.

### 3C: Add MCP Tool Server Registration JSON

**File**: `imports/openwebui/tools/portal_security.json` (NEW)

```json
{
  "id": "portal_security",
  "name": "Portal Security Tools",
  "description": "Vulnerability severity classification (CIRCL VLAI). Classifies CVE descriptions into low/medium/high/critical severity with confidence scores.",
  "url": "http://portal5-mcp-security:8919",
  "type": "mcp"
}
```

### 3D: Add to `imports/openwebui/mcp-servers.json`

**File**: `imports/openwebui/mcp-servers.json`

Add to the JSON array:
```json
{
    "name": "Portal Security Tools",
    "url": "http://portal5-mcp-security:8919/mcp",
    "description": "CVE severity classification via CIRCL VLAI (RoBERTa-base, 82% accuracy)"
}
```

### Verification

```bash
# Verify file exists and is valid Python
python3 -c "import ast; ast.parse(open('portal_mcp/security/security_mcp.py').read()); print('Syntax: OK')"

# Verify __init__.py exists
test -f portal_mcp/security/__init__.py && echo "__init__.py: OK"

# Verify docker-compose has the service
grep -q 'mcp-security' deploy/portal-5/docker-compose.yml && echo "docker-compose: OK"
grep -q '8919' deploy/portal-5/docker-compose.yml && echo "port 8919: OK"

# Verify tool registration JSON is valid
python3 -c "import json; json.load(open('imports/openwebui/tools/portal_security.json')); print('Tool JSON: OK')"

# Verify mcp-servers.json is valid after edit
python3 -c "import json; json.load(open('imports/openwebui/mcp-servers.json')); print('MCP servers JSON: OK')"

# Integration test (after docker compose up):
# curl -s http://localhost:8919/health | python3 -m json.tool
# Expected: {"status": "ok", "service": "security-mcp", "port": 8919}
```

### Rollback
Remove `portal_mcp/security/` directory, remove `mcp-security` service from docker-compose,
remove tool registration JSON, remove entry from mcp-servers.json.

### Commit
```
feat(mcp): add security MCP server with CIRCL VLAI CVE severity classifier

New MCP tool server on port 8919 provides classify_vulnerability() tool
using CIRCL's VLAI RoBERTa model (503MB, MIT, 82% accuracy, 600K+ CVEs).
Returns severity (low/medium/high/critical) with confidence scores.
Runs on CPU in the MCP container — transformers already in Dockerfile.mcp.
Enriches auto-security, auto-blueteam, auto-redteam persona workflows.
```

---

## Task 4: Benchmark Optimization — Route `auto-research` Through 26B MoE

**Rationale**: The benchmark shows Gemma 4 31B dense at ~20 TPS vs Gemma 4 26B-A4B MoE
at ~35 TPS. Both serve the research workspace, but `auto-research` currently hints at
the 31B dense. For research queries that don't require the 31B's denser reasoning or
its full 256K context, the 26B MoE provides 75% faster throughput with uncensored
capability (after Task 1).

### 4A: Update `auto-research` mlx_model_hint

**File**: `portal_pipeline/router_pipe.py`

Find:
```python
    "auto-research": {
        "name": "🔍 Portal Research Assistant",
        "description": "Web research, information synthesis, fact-checking",
        "model_hint": "huihui_ai/tongyi-deepresearch-abliterated",
        "mlx_model_hint": "mlx-community/gemma-4-31b-it-4bit",  # Gemma 4 dense 31B — 256K functional context, #3 open model; abliterated-4bit stays in pool for sensitive research
    },
```
Replace with:
```python
    "auto-research": {
        "name": "🔍 Portal Research Assistant",
        "description": "Web research, information synthesis, fact-checking",
        "model_hint": "huihui_ai/tongyi-deepresearch-abliterated",
        "mlx_model_hint": "Jiunsong/supergemma4-26b-abliterated-multimodal-mlx-4bit",  # Gemma 4 26B A4B MoE abliterated — ~35 TPS (vs 31B dense ~20 TPS), uncensored, 256K ctx
    },
```

### 4B: Preserve 31B for vision (no change)

`auto-vision` keeps `mlx-community/gemma-4-31b-it-4bit` as its primary VLM. The 31B
dense model remains the best option for complex visual reasoning requiring dense
attention. The JANG abliterated 31B remains for uncensored vision tasks.

### Verification

```bash
# Verify the hint was updated
python3 -c "
from portal_pipeline.router_pipe import WORKSPACES
hint = WORKSPACES['auto-research']['mlx_model_hint']
assert 'supergemma4-26b-abliterated' in hint, f'Wrong hint: {hint}'
print(f'auto-research mlx_model_hint: {hint} — OK')
"

# Verify auto-vision still points to 31B
python3 -c "
from portal_pipeline.router_pipe import WORKSPACES
hint = WORKSPACES['auto-vision']['mlx_model_hint']
assert 'gemma-4-31b-it-4bit' in hint, f'Vision hint changed: {hint}'
print(f'auto-vision mlx_model_hint: {hint} — OK')
"

# Workspace consistency
python3 -c "
import yaml
from portal_pipeline.router_pipe import WORKSPACES
cfg = yaml.safe_load(open('config/backends.yaml'))
pipe_ids = set(WORKSPACES.keys())
yaml_ids = set(cfg['workspace_routing'].keys())
assert pipe_ids == yaml_ids, f'Mismatch: pipe={pipe_ids-yaml_ids} yaml={yaml_ids-pipe_ids}'
print('Workspace IDs consistent')
"
```

### Rollback
Revert `auto-research` `mlx_model_hint` to `mlx-community/gemma-4-31b-it-4bit`.

### Commit
```
perf(routing): route auto-research through 26B MoE abliterated (~35 vs ~20 TPS)

Benchmark shows Gemma 4 26B A4B MoE at ~35 TPS vs 31B dense at ~20 TPS.
Research workspace benefits from faster throughput for synthesis/factcheck
tasks. The abliterated 26B also removes refusals for sensitive research.
Vision workspace retains the 31B dense for complex visual reasoning.
```

---

## Task 5: Add OMLX to Roadmap

**Rationale**: OMLX (github.com/jundot/omlx) is an MLX inference server with continuous
batching, SSD KV caching, multi-model LRU eviction, VLM support, and OpenAI API
compatibility. It could replace Portal 5's custom `mlx-proxy.py` with significant
performance benefits, but requires careful evaluation of existing admission control,
VLM routing, and big-model-mode logic preservation.

### 5A: Update `P5_ROADMAP.md`

**File**: `P5_ROADMAP.md`

Add to the "Future Considerations" table:

```markdown
| P5-FUT-013 | P3 | OMLX evaluation — MLX inference tier upgrade | FUTURE | Evaluate jundot/omlx (github.com/jundot/omlx, Apache 2.0) as replacement for scripts/mlx-proxy.py. Key benefits: continuous batching (up to 4.14x at 8x concurrency per their benchmarks), SSD KV cache persistence (TTFT 30-90s → 1-3s for repeated contexts), multi-model LRU eviction with pinning, native VLM + embedding + reranker support, OpenAI + Anthropic API compat, DFlash speculative decoding (experimental, Qwen3.5 only). Risks: Must preserve existing admission control (MODEL_MEMORY checks), VLM routing (VLM_MODELS set), big-model-mode orchestration (BIG_MODEL_SET eviction), and mlx-lm<0.31 version pin for qwen3_next architecture. OMLX uses its own mlx-lm fork — version compatibility requires investigation. Approach: Install OMLX alongside existing proxy on a separate port, benchmark same model set, compare TPS and switch latency. Do not replace mlx-proxy.py until parity is confirmed on all workspaces. |
```

### 5B: Add Implementation Notes Section

Add after the existing "Implementation Notes" entries:

```markdown
### P5-FUT-013: OMLX Evaluation

**NOT YET STARTED** — spike evaluation only, not a replacement commitment.

**What OMLX offers** (validated from repo, v0.3.x as of 2026-04-20):
- Continuous batching via mlx-lm BatchGenerator (configurable concurrency, default: 8)
- Two-tier KV cache: hot (RAM) + cold (SSD, safetensors format), survives restarts
- Multi-model serving: LLMs, VLMs, embeddings, rerankers in one process
- LRU eviction + model pinning + per-model TTL + process memory enforcement
- OpenAI /v1/chat/completions + Anthropic API compatible
- Native macOS menu bar app (PyObjC, not Electron) OR CLI `omlx serve`
- DFlash speculative decoding (experimental, 3-4x speedup on supported models)
- mlx-audio integration: STT (Whisper, Qwen3-ASR), TTS (Qwen3-TTS, Kokoro)
- Built-in admin dashboard with benchmarking

**What Portal 5 would need to verify**:
1. Can OMLX enforce the MODEL_MEMORY admission control checks?
   - OMLX has `--max-model-memory` and `--max-process-memory` — may cover this
2. Can OMLX replicate the VLM_MODELS routing (mlx_lm ↔ mlx_vlm auto-switch)?
   - OMLX has VLMEngine with auto-detection — likely yes, needs testing
3. Can OMLX handle BIG_MODEL_SET eviction (unload everything, load 46GB model)?
   - OMLX has manual load/unload + LRU eviction — likely yes
4. Does OMLX work with mlx-lm<0.31 pin (qwen3_next architecture)?
   - OMLX uses its own mlx-lm fork — version compatibility unknown
5. Does OMLX respect the 0.0.0.0 binding requirement for LAN access?
   - CLI supports `--host 0.0.0.0` — yes
6. Can OMLX integrate with existing Prometheus metrics?
   - OMLX has persistent stats — may need a metrics bridge
7. Does OMLX's mlx-audio subsystem overlap/conflict with mlx-speech.py?
   - Both use Qwen3-TTS/Kokoro — potential consolidation opportunity

**Evaluation approach**: Install OMLX on host alongside existing mlx-proxy on port 8000
(proxy stays on 8081). Run the same bench_tps.py benchmark against both. Compare TPS,
model switch latency, and memory behavior. If parity + improvement confirmed, plan
migration as a separate task file.
```

### Verification

```bash
# Verify roadmap entry exists
grep -q 'P5-FUT-013' P5_ROADMAP.md && echo "Roadmap entry: OK"
grep -q 'omlx' P5_ROADMAP.md && echo "OMLX mentioned: OK"
```

### Commit
```
docs(roadmap): add P5-FUT-013 OMLX evaluation for MLX inference tier upgrade

OMLX (github.com/jundot/omlx) offers continuous batching, SSD KV cache,
multi-model LRU eviction, and native VLM support. Added as FUTURE item
with detailed evaluation criteria and risk assessment. No code changes —
evaluation spike only.
```

---

## Execution Order

1. **Task 1** (MLX model swap) — prerequisite for Task 4
2. **Task 4** (research routing optimization) — depends on Task 1's model being in place
3. **Task 2** (Ollama GGUF addition) — independent, can run in parallel
4. **Task 3** (MCP security tool) — independent, can run in parallel
5. **Task 5** (OMLX roadmap) — independent, documentation only

Tasks 2, 3, and 5 have no dependencies on each other or Tasks 1/4.

## Tests

```bash
# Run unit tests (should pass before AND after all changes)
pytest tests/unit/ -v --tb=short

# Run linter
ruff check . --fix && ruff format .

# Full consistency check
python3 -c "
import yaml
from portal_pipeline.router_pipe import WORKSPACES
cfg = yaml.safe_load(open('config/backends.yaml'))
pipe_ids = set(WORKSPACES.keys())
yaml_ids = set(cfg['workspace_routing'].keys())
assert pipe_ids == yaml_ids, f'Mismatch: pipe={pipe_ids-yaml_ids} yaml={yaml_ids-pipe_ids}'
print('All workspace IDs consistent')
"
```

---

## Acceptance Criteria

- [ ] Task 1: Old censored `gemma-4-26b-a4b-it-4bit` replaced in mlx-proxy.py + backends.yaml
- [ ] Task 1: New model in VLM_MODELS, ALL_MODELS, MODEL_MEMORY with correct basename
- [ ] Task 2: Uncensored Gemma 26B GGUF in `ollama-reasoning` group in backends.yaml
- [ ] Task 3: `portal_mcp/security/security_mcp.py` exists and passes syntax check
- [ ] Task 3: `mcp-security` service in docker-compose.yml on port 8919
- [ ] Task 3: Tool registration JSON and mcp-servers.json updated
- [ ] Task 4: `auto-research` mlx_model_hint points to abliterated 26B MoE
- [ ] Task 4: `auto-vision` mlx_model_hint unchanged (still 31B dense)
- [ ] Task 5: P5-FUT-013 in P5_ROADMAP.md with evaluation criteria
- [ ] All: `pytest tests/unit/ -v --tb=short` passes
- [ ] All: `ruff check .` clean
- [ ] All: Workspace consistency check passes
- [ ] Task 6: Acceptance v6 `_MLX_MODEL_FULL_PATHS` and `_MLX_MODEL_SIZES_GB` updated
- [ ] Task 6: Acceptance v6 `_MLX_ORGS` includes `"Jiunsong/"`
- [ ] Task 6: Acceptance v6 `_MLX_MODEL_TO_WORKSPACE` updated for auto-research reroute
- [ ] Task 6: Acceptance v6 S1-08 validates new abliterated 26B in VLM_MODELS
- [ ] Task 6: Acceptance v6 MCP dict + S2 health checks include security on 8919
- [ ] Task 6: Acceptance v6 MLX_PERSONA_GROUPS Group 4 split for research→26B, vision→31B
- [ ] Task 6: Acceptance v4 MCP dict + health checks + container map include security
- [ ] Task 6: Acceptance v4 `_MLX_ORGS` includes `"Jiunsong/"`

---

## Task 6: Acceptance Test Updates for Tasks 1–4

**Rationale**: The acceptance suites derive ground truth from source files. Tasks 1–4
change model names, add an MCP service, and reroute a workspace. Without matching
acceptance updates, the suites would produce false FAILs on the next run.

**Protected file note**: Acceptance test files are NOT in the protected-files list
(`portal_pipeline/**`, `portal_mcp/**`, `config/`, `deploy/`, `docs/HOWTO.md`,
`scripts/mlx-proxy.py`). Test files are editable.

### 6A: `tests/portal5_acceptance_v6.py` — `_MLX_MODEL_FULL_PATHS`

Find (line ~637):
```python
    "gemma-4-26b-a4b-it-4bit": "mlx-community/gemma-4-26b-a4b-it-4bit",
```
Replace with:
```python
    "supergemma4-26b-abliterated-multimodal-mlx-4bit": "Jiunsong/supergemma4-26b-abliterated-multimodal-mlx-4bit",
```

### 6B: `tests/portal5_acceptance_v6.py` — `_MLX_MODEL_SIZES_GB`

Find (line ~658):
```python
    "gemma-4-26b-a4b-it-4bit": 15,
```
Replace with:
```python
    "supergemma4-26b-abliterated-multimodal-mlx-4bit": 15,
```

### 6C: `tests/portal5_acceptance_v6.py` — `_MLX_ORGS`

Find (line ~665):
```python
_MLX_ORGS = ["mlx-community/", "lmstudio-community/", "Jackrong/", "unsloth/", "dealignai/"]
```
Replace with:
```python
_MLX_ORGS = ["mlx-community/", "lmstudio-community/", "Jackrong/", "Jiunsong/", "unsloth/", "dealignai/"]
```

### 6D: `tests/portal5_acceptance_v6.py` — `_MLX_MODEL_TO_WORKSPACE`

Find (line ~677):
```python
    "mlx-community/gemma-4-31b-it-4bit": "auto-research",
    "mlx-community/gemma-4-31b-it-4bit": "auto-vision",   # same model serves both
```
Replace with:
```python
    "Jiunsong/supergemma4-26b-abliterated-multimodal-mlx-4bit": "auto-research",  # Task 4: rerouted from 31B dense to 26B MoE abliterated (~35 vs ~20 TPS)
    "mlx-community/gemma-4-31b-it-4bit": "auto-vision",
```

### 6E: `tests/portal5_acceptance_v6.py` — `MCP` dict

Find (line ~119-129):
```python
# MCP ports
MCP = {
    "comfyui": int(os.environ.get("COMFYUI_MCP_HOST_PORT", "8910")),
    "video": int(os.environ.get("VIDEO_MCP_HOST_PORT", "8911")),
    "music": int(os.environ.get("MUSIC_HOST_PORT", "8912")),
    "documents": int(os.environ.get("DOCUMENTS_HOST_PORT", "8913")),
    "sandbox": int(os.environ.get("SANDBOX_HOST_PORT", "8914")),
    "whisper": int(os.environ.get("WHISPER_HOST_PORT", "8915")),
    "tts": int(os.environ.get("TTS_HOST_PORT", "8916")),
    "embedding": int(os.environ.get("EMBEDDING_HOST_PORT", "8917")),
}
```
Replace with:
```python
# MCP ports
MCP = {
    "comfyui": int(os.environ.get("COMFYUI_MCP_HOST_PORT", "8910")),
    "video": int(os.environ.get("VIDEO_MCP_HOST_PORT", "8911")),
    "music": int(os.environ.get("MUSIC_HOST_PORT", "8912")),
    "documents": int(os.environ.get("DOCUMENTS_HOST_PORT", "8913")),
    "sandbox": int(os.environ.get("SANDBOX_HOST_PORT", "8914")),
    "whisper": int(os.environ.get("WHISPER_HOST_PORT", "8915")),
    "tts": int(os.environ.get("TTS_HOST_PORT", "8916")),
    "embedding": int(os.environ.get("EMBEDDING_HOST_PORT", "8917")),
    "security": int(os.environ.get("SECURITY_HOST_PORT", "8919")),
}
```

### 6F: `tests/portal5_acceptance_v6.py` — S2 MCP health checks

Find (line ~1323-1331):
```python
    # S2-08 to S2-14: MCP services
    mcp_services = [
        ("S2-08", "documents", MCP["documents"]),
        ("S2-09", "music", MCP["music"]),
        ("S2-10", "tts", MCP["tts"]),
        ("S2-11", "whisper", MCP["whisper"]),
        ("S2-12", "sandbox", MCP["sandbox"]),
        ("S2-13", "video", MCP["video"]),
        ("S2-14", "embedding", MCP["embedding"]),
    ]
```
Replace with:
```python
    # S2-08 to S2-15: MCP services
    mcp_services = [
        ("S2-08", "documents", MCP["documents"]),
        ("S2-09", "music", MCP["music"]),
        ("S2-10", "tts", MCP["tts"]),
        ("S2-11", "whisper", MCP["whisper"]),
        ("S2-12", "sandbox", MCP["sandbox"]),
        ("S2-13", "video", MCP["video"]),
        ("S2-14", "embedding", MCP["embedding"]),
        ("S2-15", "security", MCP["security"]),
    ]
```

Also renumber the tests that follow. Find (line ~1343-1361):
```python
    # S2-15: MLX proxy health
    t0 = time.time()
    state, data = await _mlx_health()
    record(
        sec, "S2-15", "MLX proxy",
        "PASS" if state in ("ready", "none", "switching") else "INFO",
        f"state={state}",
        t0=t0,
    )

    # S2-16: MLX Speech health
    t0 = time.time()
    code, _ = await _get(f"{MLX_SPEECH_URL}/health", timeout=5)
    record(
        sec, "S2-16", "MLX Speech",
        "PASS" if code == 200 else "INFO",
        f"HTTP {code}" if code else "not running (optional)",
        t0=t0,
    )
```
Replace with:
```python
    # S2-16: MLX proxy health
    t0 = time.time()
    state, data = await _mlx_health()
    record(
        sec, "S2-16", "MLX proxy",
        "PASS" if state in ("ready", "none", "switching") else "INFO",
        f"state={state}",
        t0=t0,
    )

    # S2-17: MLX Speech health
    t0 = time.time()
    code, _ = await _get(f"{MLX_SPEECH_URL}/health", timeout=5)
    record(
        sec, "S2-17", "MLX Speech",
        "PASS" if code == 200 else "INFO",
        f"HTTP {code}" if code else "not running (optional)",
        t0=t0,
    )
```

### 6G: `tests/portal5_acceptance_v6.py` — S1-08 VLM_MODELS validation

The current S1-08 validates 31B, E4B, and JANG. After Task 1, the new abliterated 26B
is also a VLM model and should be validated. Add it to the check.

Find (line ~1193-1205):
```python
            # Gemma 4 31B dense, E4B, and JANG must be in VLM_MODELS (require mlx_vlm)
            gemma_31b_vlm = "gemma-4-31b-it-4bit" in vlm_section
            gemma_e4b_vlm = "gemma-4-e4b-it-4bit" in vlm_section
            gemma_31b_all = "mlx-community/gemma-4-31b-it-4bit" in proxy_src
            jang_vlm = "Gemma-4-31B-JANG_4M-CRACK" in vlm_section
            jang_all = "dealignai/Gemma-4-31B-JANG_4M-CRACK" in proxy_src
            all_ok = gemma_31b_vlm and gemma_e4b_vlm and gemma_31b_all and jang_vlm and jang_all
            record(
                sec, "S1-08",
                "MLX routing: VLM models in VLM_MODELS (mlx_vlm backend)",
                "PASS" if all_ok else "FAIL",
                "✓ Gemma 4 31B + E4B + JANG in VLM_MODELS" if all_ok
                else f"31b_vlm={gemma_31b_vlm} e4b_vlm={gemma_e4b_vlm} 31b_all={gemma_31b_all} jang_vlm={jang_vlm} jang_all={jang_all}",
                t0=t0,
            )
```
Replace with:
```python
            # Gemma 4 31B dense, E4B, JANG, and abliterated 26B MoE must be in VLM_MODELS (require mlx_vlm)
            gemma_31b_vlm = "gemma-4-31b-it-4bit" in vlm_section
            gemma_e4b_vlm = "gemma-4-e4b-it-4bit" in vlm_section
            gemma_31b_all = "mlx-community/gemma-4-31b-it-4bit" in proxy_src
            jang_vlm = "Gemma-4-31B-JANG_4M-CRACK" in vlm_section
            jang_all = "dealignai/Gemma-4-31B-JANG_4M-CRACK" in proxy_src
            gemma_26b_abl_vlm = "supergemma4-26b-abliterated-multimodal-mlx-4bit" in vlm_section
            gemma_26b_abl_all = "Jiunsong/supergemma4-26b-abliterated-multimodal-mlx-4bit" in proxy_src
            all_ok = gemma_31b_vlm and gemma_e4b_vlm and gemma_31b_all and jang_vlm and jang_all and gemma_26b_abl_vlm and gemma_26b_abl_all
            record(
                sec, "S1-08",
                "MLX routing: VLM models in VLM_MODELS (mlx_vlm backend)",
                "PASS" if all_ok else "FAIL",
                "✓ Gemma 4 31B + E4B + JANG + 26B-abl in VLM_MODELS" if all_ok
                else f"31b_vlm={gemma_31b_vlm} e4b_vlm={gemma_e4b_vlm} 31b_all={gemma_31b_all} jang_vlm={jang_vlm} jang_all={jang_all} 26b_abl_vlm={gemma_26b_abl_vlm} 26b_abl_all={gemma_26b_abl_all}",
                t0=t0,
            )
```

### 6H: `tests/portal5_acceptance_v6.py` — MLX_PERSONA_GROUPS Group 4

Find (line ~1913-1918):
```python
        # Group 4: Gemma 4 31B dense — serves both auto-research and auto-vision (3 personas,
        # same MLX model loaded once; workspace routing selects the right system context).
        ("mlx-community/gemma-4-31b-it-4bit", "auto-research", ["gemmaresearchanalyst"]),
        ("mlx-community/gemma-4-31b-it-4bit", "auto-vision", [
            "gemma4e4bvision", "gemma4jangvision",
        ]),
```
Replace with:
```python
        # Group 4a: Abliterated 26B MoE → auto-research (Task 4: rerouted for ~35 vs ~20 TPS)
        ("Jiunsong/supergemma4-26b-abliterated-multimodal-mlx-4bit", "auto-research", ["gemmaresearchanalyst"]),
        # Group 4b: Gemma 4 31B dense → auto-vision (unchanged — dense attention for complex visual reasoning)
        ("mlx-community/gemma-4-31b-it-4bit", "auto-vision", [
            "gemma4e4bvision", "gemma4jangvision",
        ]),
```

Also add the new model to the `model_gb` dict. Find (line ~1936-1945):
```python
        model_gb = {
            "mlx-community/Qwen3-Coder-30B-A3B-Instruct-8bit": 17,   # MoE 3B active ~17GB
            "Jackrong/MLX-Qwen3.5-35B-A3B-Claude-4.6-Opus-Reasoning-Distilled-8bit": 28,  # 35B-A3B 8bit ~28GB
            "mlx-community/gemma-4-31b-it-4bit": 18,
            "mlx-community/phi-4-8bit": 14,
            "lmstudio-community/Phi-4-reasoning-plus-MLX-4bit": 15,
            "lmstudio-community/Magistral-Small-2509-MLX-8bit": 22,
            "mlx-community/gemma-4-e4b-it-4bit": 5,
            "dealignai/Gemma-4-31B-JANG_4M-CRACK": 23,
        }.get(model_hint, 10)
```
Replace with:
```python
        model_gb = {
            "mlx-community/Qwen3-Coder-30B-A3B-Instruct-8bit": 17,   # MoE 3B active ~17GB
            "Jackrong/MLX-Qwen3.5-35B-A3B-Claude-4.6-Opus-Reasoning-Distilled-8bit": 28,  # 35B-A3B 8bit ~28GB
            "mlx-community/gemma-4-31b-it-4bit": 18,
            "Jiunsong/supergemma4-26b-abliterated-multimodal-mlx-4bit": 15,  # 26B MoE abliterated ~15GB
            "mlx-community/phi-4-8bit": 14,
            "lmstudio-community/Phi-4-reasoning-plus-MLX-4bit": 15,
            "lmstudio-community/Magistral-Small-2509-MLX-8bit": 22,
            "mlx-community/gemma-4-e4b-it-4bit": 5,
            "dealignai/Gemma-4-31B-JANG_4M-CRACK": 23,
        }.get(model_hint, 10)
```

### 6I: `tests/portal5_acceptance_v4.py` — `MCP` dict

Find (line ~396-404):
```python
MCP = {
    "documents": int(os.environ.get("DOCUMENTS_HOST_PORT", "8913")),
    "music": int(os.environ.get("MUSIC_HOST_PORT", "8912")),
    "tts": int(os.environ.get("TTS_HOST_PORT", "8916")),
    "whisper": int(os.environ.get("WHISPER_HOST_PORT", "8915")),
    "sandbox": int(os.environ.get("SANDBOX_HOST_PORT", "8914")),
    "video": int(os.environ.get("VIDEO_MCP_HOST_PORT", "8911")),
    "embedding": int(os.environ.get("EMBEDDING_HOST_PORT", "8917")),
}
```
Replace with:
```python
MCP = {
    "documents": int(os.environ.get("DOCUMENTS_HOST_PORT", "8913")),
    "music": int(os.environ.get("MUSIC_HOST_PORT", "8912")),
    "tts": int(os.environ.get("TTS_HOST_PORT", "8916")),
    "whisper": int(os.environ.get("WHISPER_HOST_PORT", "8915")),
    "sandbox": int(os.environ.get("SANDBOX_HOST_PORT", "8914")),
    "video": int(os.environ.get("VIDEO_MCP_HOST_PORT", "8911")),
    "embedding": int(os.environ.get("EMBEDDING_HOST_PORT", "8917")),
    "security": int(os.environ.get("SECURITY_HOST_PORT", "8919")),
}
```

### 6J: `tests/portal5_acceptance_v4.py` — `_svc_containers`

Find (line ~949-956):
```python
    _svc_containers = {
        "mcp-documents": "portal5-mcp-documents",
        "mcp-tts": "portal5-mcp-tts",
        "mcp-whisper": "portal5-mcp-whisper",
        "mcp-sandbox": "portal5-mcp-sandbox",
        "mcp-video": "portal5-mcp-video",
    }
```
Replace with:
```python
    _svc_containers = {
        "mcp-documents": "portal5-mcp-documents",
        "mcp-tts": "portal5-mcp-tts",
        "mcp-whisper": "portal5-mcp-whisper",
        "mcp-sandbox": "portal5-mcp-sandbox",
        "mcp-video": "portal5-mcp-video",
        "mcp-security": "portal5-mcp-security",
    }
```

### 6K: `tests/portal5_acceptance_v4.py` — S17 `mcp_checks`

Find (line ~1086-1093):
```python
    mcp_checks = [
        ("mcp-documents", f"http://localhost:{MCP['documents']}/health"),
        ("mcp-music", f"http://localhost:{MCP['music']}/health"),
        ("mcp-tts", f"http://localhost:{MCP['tts']}/health"),
        ("mcp-whisper", f"http://localhost:{MCP['whisper']}/health"),
        ("mcp-sandbox", f"http://localhost:{MCP['sandbox']}/health"),
        ("mcp-video", f"http://localhost:{MCP['video']}/health"),
    ]
```
Replace with:
```python
    mcp_checks = [
        ("mcp-documents", f"http://localhost:{MCP['documents']}/health"),
        ("mcp-music", f"http://localhost:{MCP['music']}/health"),
        ("mcp-tts", f"http://localhost:{MCP['tts']}/health"),
        ("mcp-whisper", f"http://localhost:{MCP['whisper']}/health"),
        ("mcp-sandbox", f"http://localhost:{MCP['sandbox']}/health"),
        ("mcp-video", f"http://localhost:{MCP['video']}/health"),
        ("mcp-security", f"http://localhost:{MCP['security']}/health"),
    ]
```

### 6L: `tests/portal5_acceptance_v4.py` — S2 service health list

Find (line ~1803-1814):
```python
    services = [
        ("Open WebUI", OPENWEBUI_URL, {}),
        ("Pipeline", f"{PIPELINE_URL}/health", {}),
        ("Grafana", f"{GRAFANA_URL}/api/health", {}),
        ("MCP Documents", f"http://localhost:{MCP['documents']}/health", {}),
        ("MCP Sandbox", f"http://localhost:{MCP['sandbox']}/health", {}),
        ("MCP Music", f"http://localhost:{MCP['music']}/health", {}),
        ("MCP TTS", f"http://localhost:{MCP['tts']}/health", {}),
        ("MCP Whisper", f"http://localhost:{MCP['whisper']}/health", {}),
        ("MCP Video", f"http://localhost:{MCP['video']}/health", {}),
        ("Prometheus", f"{PROMETHEUS_URL}/-/ready", {}),
    ]
```
Replace with:
```python
    services = [
        ("Open WebUI", OPENWEBUI_URL, {}),
        ("Pipeline", f"{PIPELINE_URL}/health", {}),
        ("Grafana", f"{GRAFANA_URL}/api/health", {}),
        ("MCP Documents", f"http://localhost:{MCP['documents']}/health", {}),
        ("MCP Sandbox", f"http://localhost:{MCP['sandbox']}/health", {}),
        ("MCP Music", f"http://localhost:{MCP['music']}/health", {}),
        ("MCP TTS", f"http://localhost:{MCP['tts']}/health", {}),
        ("MCP Whisper", f"http://localhost:{MCP['whisper']}/health", {}),
        ("MCP Video", f"http://localhost:{MCP['video']}/health", {}),
        ("MCP Security", f"http://localhost:{MCP['security']}/health", {}),
        ("Prometheus", f"{PROMETHEUS_URL}/-/ready", {}),
    ]
```

### 6M: `tests/portal5_acceptance_v4.py` — `_MLX_ORGS`

Find (line ~7654):
```python
        _MLX_ORGS = ("mlx-community/", "lmstudio-community/", "Jackrong/")
```
Replace with:
```python
        _MLX_ORGS = ("mlx-community/", "lmstudio-community/", "Jackrong/", "Jiunsong/")
```

### Verification

```bash
# Verify v6 acceptance has all updates
python3 -c "
src = open('tests/portal5_acceptance_v6.py').read()
assert 'supergemma4-26b-abliterated-multimodal-mlx-4bit' in src, 'v6: missing new 26B model'
assert '\"Jiunsong/\"' in src, 'v6: missing Jiunsong org'
assert '\"security\"' in src and '8919' in src, 'v6: missing security MCP'
assert 'S2-15.*security' in src or '\"S2-15\", \"security\"' in src, 'v6: missing S2-15 security'
assert 'gemma_26b_abl_vlm' in src, 'v6: missing S1-08 abliterated 26B check'
print('v6 acceptance: all checks present')
"

# Verify v4 acceptance has all updates
python3 -c "
src = open('tests/portal5_acceptance_v4.py').read()
assert '\"security\"' in src and '8919' in src, 'v4: missing security MCP'
assert 'mcp-security' in src, 'v4: missing mcp-security container'
assert '\"Jiunsong/\"' in src, 'v4: missing Jiunsong org'
print('v4 acceptance: all checks present')
"

# Syntax check both files
python3 -c "import ast; ast.parse(open('tests/portal5_acceptance_v6.py').read()); print('v6 syntax: OK')"
python3 -c "import ast; ast.parse(open('tests/portal5_acceptance_v4.py').read()); print('v4 syntax: OK')"
```

### Commit
```
test(acceptance): update v4 + v6 suites for model swap, MCP security, research reroute

v6 changes:
- _MLX_MODEL_FULL_PATHS + _MLX_MODEL_SIZES_GB: 26B censored → abliterated
- _MLX_ORGS: add Jiunsong/ prefix
- _MLX_MODEL_TO_WORKSPACE: auto-research → abliterated 26B MoE
- S1-08: validate abliterated 26B in VLM_MODELS
- MCP dict + S2 health: add security service on 8919 (S2-15)
- MLX_PERSONA_GROUPS: split Group 4 (research→26B abl, vision→31B)
- model_gb dict: add abliterated 26B entry

v4 changes:
- MCP dict: add security on 8919
- _svc_containers: add mcp-security
- S17 mcp_checks + S2 services: add security health
- _MLX_ORGS: add Jiunsong/
```

---

## Updated Execution Order

1. **Task 1** (MLX model swap) — prerequisite for Tasks 4 and 6
2. **Task 4** (research routing optimization) — depends on Task 1
3. **Task 2** (Ollama GGUF addition) — independent
4. **Task 3** (MCP security tool) — independent, prerequisite for Task 6 MCP parts
5. **Task 5** (OMLX roadmap) — independent, documentation only
6. **Task 6** (acceptance test updates) — depends on Tasks 1, 3, 4 being complete
