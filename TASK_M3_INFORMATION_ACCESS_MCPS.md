# TASK_M3_INFORMATION_ACCESS_MCPS.md

**Milestone:** M3 — Information access
**Scope:** `CAPABILITY_REVIEW_V1.md` §6.4 web search MCP, §6.5 memory MCP, §6.6 RAG MCP, §4.4 embedding+reranker models, related personas
**Estimated effort:** 6-8 weeks
**Dependencies:** **M2 must ship before M3.** M3's new MCP servers are useless without the tool-call loop — they're meant to be invoked by the model, not by the user.
**Companion files:** `CAPABILITY_REVIEW_V1.md`, `TASK_M2_TOOL_CALLING_ORCHESTRATION.md` (predecessor)

**Why this milestone:**
- `auto-research` workspace says "Web research, fact-checking" but has no actual web access — `tongyi-deepresearch-abliterated` is just a model trained to *be search-aware*, not to actually fetch.
- No persistent cross-conversation memory. Claude.ai/ChatGPT both have it.
- OWUI has its own RAG (file uploads) but it's user-driven, not agent-driven. The model can't decide "I need to look this up" and act on it.

**Success criteria:**
- New `webresearcher` persona answers "What happened in tech news today?" with cited sources from a live search.
- New `personalassistant` persona remembers the operator's stated preferences across conversations.
- New `kbnavigator` persona answers questions over a custom KB of compliance docs / SPL detection patterns.
- Three new MCP servers running on dedicated ports (research, memory, rag).
- Embedding + reranker MLX models in catalog and admission control.

**Protected files touched:** `portal_pipeline/router_pipe.py`, `deploy/docker-compose.yml`, `portal_mcp/` (new servers), `scripts/mlx-proxy.py`.

---

## Architecture Decisions

### A1. SearXNG, not paid APIs

For web search, run **SearXNG** in Portal 5's docker-compose. Self-hosted, no API key, aggregates Google/DDG/Bing/Brave. Backup: Brave Search API (free tier) via `WEB_SEARCH_BACKEND` env.

### A2. LanceDB, not ChromaDB

For memory + RAG vector storage, use **LanceDB**. Embedded (no separate server), Apache 2.0, fast on Apple Silicon, persists to disk by default. Avoids the `chromadb` ARM64 dependency hell. Storage: `/Volumes/data01/portal5_lance/{memory,rag}`.

### A3. Embedding via MLX, not TEI

Add `mlx-community/mxbai-embed-large-v1-mlx` to MLX catalog and serve through extended `mlx-proxy.py`. Memory: ~600MB embed + ~1.2GB reranker = ~1.8GB total, comfortable. TEI's ARM64 issues (per V4 acceptance) avoided entirely.

### A4. Memory scoping

Memory is per-operator (single-operator setup). Schema namespaced by `user_id` (default = `"default"`) for future multi-user. Each memory: id, user_id, text, embedding, category, created_at, last_accessed_at, access_count, tags.

### A5. RAG corpus model

Multiple knowledge bases per RAG MCP, each with `kb_id`, source files, chunking config, embeddings table. Tools: `kb_list`, `kb_search`, `kb_search_all`, `kb_ingest` (admin). Standard chunk-embed-retrieve-rerank pipeline.

---

## Task Index

| ID | Title | File(s) | Effort |
|---|---|---|---|
| M3-T01 | SearXNG container | `deploy/docker-compose.yml`, `deploy/searxng/settings.yml` | 1 day |
| M3-T02 | Web search MCP server | `portal_mcp/research/web_search_mcp.py` (new) | 3-5 days |
| M3-T03 | Add embedding + reranker MLX models | `config/backends.yaml`, `scripts/mlx-proxy.py` | 1-2 days |
| M3-T04 | MLX embedding + rerank endpoints | `scripts/mlx-proxy.py` | 2-3 days |
| M3-T05 | Memory MCP server | `portal_mcp/memory/memory_mcp.py` (new) | 5-7 days |
| M3-T06 | RAG MCP server | `portal_mcp/rag/rag_mcp.py` (new) | 1-2 weeks |
| M3-T07 | Register new MCP servers in tool registry | `portal_pipeline/tool_registry.py` | 1 day |
| M3-T08 | Update workspace tool whitelists | `portal_pipeline/router_pipe.py` | 1 day |
| M3-T09 | Add 5 information-access personas | `config/personas/*.yaml` | 1-2 days |
| M3-T10 | Acceptance tests for new MCPs | `tests/portal5_acceptance_v6.py` (S70 section) | 3-5 days |
| M3-T11 | Documentation | `docs/HOWTO.md`, `KNOWN_LIMITATIONS.md`, `CHANGELOG.md` | 1 day |

---

## M3-T01 — SearXNG Container

**File:** `deploy/docker-compose.yml`, `deploy/searxng/settings.yml` (new)

Add a SearXNG service. JSON API enabled, restricted to localhost (the MCP server is the only consumer).

**Diff** in `deploy/docker-compose.yml`:

```yaml
services:
  # ... existing services ...
  searxng:
    image: searxng/searxng:latest
    container_name: portal5_searxng
    restart: unless-stopped
    ports:
      - "127.0.0.1:8920:8080"   # localhost-only, no LAN exposure
    volumes:
      - ./deploy/searxng:/etc/searxng:rw
    environment:
      - INSTANCE_NAME=portal5_search
      - BASE_URL=http://localhost:8920
      - SEARXNG_SECRET=${SEARXNG_SECRET}
    networks:
      - portal5
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8080/healthz"]
      interval: 30s
      timeout: 5s
      retries: 3
```

**Create** `deploy/searxng/settings.yml`:

```yaml
use_default_settings: true
server:
  secret_key: "${SEARXNG_SECRET}"
  limiter: false
  image_proxy: true
search:
  formats: [html, json]   # JSON required for MCP
  default_lang: en
  max_request_timeout: 10.0
ui:
  default_theme: simple
engines:
  - {name: google, disabled: false}
  - {name: duckduckgo, disabled: false}
  - {name: bing, disabled: false}
  - {name: brave, disabled: false}
  - {name: wikipedia, disabled: false}
  - {name: github, disabled: false}
  - {name: stackoverflow, disabled: false}
```

Add to `.env.example`: `SEARXNG_SECRET=` (operator generates with `openssl rand -hex 32`).

**Verify:**
```bash
[ -z "$(grep SEARXNG_SECRET .env)" ] && echo "SEARXNG_SECRET=$(openssl rand -hex 32)" >> .env
docker-compose up -d searxng
sleep 10
curl -s http://localhost:8920/healthz                                                # 200 OK
curl -s "http://localhost:8920/search?q=portal+5&format=json" | jq '.results | length'  # > 0
```

**Rollback:** `docker-compose stop searxng && docker-compose rm -f searxng`

**Commit:** `feat(deploy): SearXNG container for web search aggregation`

---

## M3-T02 — Web Search MCP Server

**File:** `portal_mcp/research/web_search_mcp.py` (new)

Tools: `web_search`, `web_fetch`, `news_search`. Backend: SearXNG (default), Brave API (fallback if SEARXNG unreachable AND BRAVE_API_KEY set).

```python
"""Portal 5 Web Search MCP Server.

Tools:
- web_search: query SearXNG, return top N results with title/url/snippet
- web_fetch: fetch a URL's text content (size-bounded, blocks private/local)
- news_search: like web_search, biased toward recent news

Port: 8918 (RESEARCH_MCP_PORT env override).
"""
import logging
import os
import re
from urllib.parse import urlparse

import httpx
from starlette.responses import JSONResponse

from portal_mcp.mcp_server.fastmcp import FastMCP

logger = logging.getLogger(__name__)
mcp = FastMCP("research", host="0.0.0.0")

SEARXNG_URL = os.environ.get("SEARXNG_URL", "http://localhost:8920")
BRAVE_API_KEY = os.environ.get("BRAVE_API_KEY", "")
WEB_FETCH_MAX_BYTES = int(os.environ.get("WEB_FETCH_MAX_BYTES", str(2 * 1024 * 1024)))
WEB_FETCH_TIMEOUT_S = float(os.environ.get("WEB_FETCH_TIMEOUT_S", "15"))

BLOCKED_DOMAINS = {"localhost", "127.0.0.1", "0.0.0.0",
                   "169.254.169.254", "metadata.google.internal"}
PRIVATE_PREFIXES = ("192.168.", "10.", "172.16.", "172.17.", "172.18.", "172.19.",
                    "172.20.", "172.21.", "172.22.", "172.23.", "172.24.", "172.25.",
                    "172.26.", "172.27.", "172.28.", "172.29.", "172.30.", "172.31.")


@mcp.custom_route("/health", methods=["GET"])
async def health(request):
    return JSONResponse({"status": "ok", "service": "research-mcp",
                         "backend": "brave" if BRAVE_API_KEY else "searxng"})


TOOLS_MANIFEST = [
    {
        "name": "web_search",
        "description": "Search the web. Returns title, URL, snippet for top N results. Use for current events or factual lookups beyond training data.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "num_results": {"type": "integer", "default": 5, "minimum": 1, "maximum": 20},
                "time_range": {"type": "string", "enum": ["any", "day", "week", "month", "year"], "default": "any"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "web_fetch",
        "description": "Fetch the text content of a URL (HTML stripped, max 2MB). Refuses localhost and private addresses.",
        "parameters": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "Full URL with http/https scheme"},
                "max_chars": {"type": "integer", "default": 50000},
            },
            "required": ["url"],
        },
    },
    {
        "name": "news_search",
        "description": "Search recent news articles. Biased toward news sources and recent results.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "num_results": {"type": "integer", "default": 5, "minimum": 1, "maximum": 20},
            },
            "required": ["query"],
        },
    },
]


@mcp.custom_route("/tools", methods=["GET"])
async def list_tools(request):
    return JSONResponse(TOOLS_MANIFEST)


async def _searxng_search(query, num_results=5, time_range="any", category="general"):
    params = {"q": query, "format": "json", "categories": category}
    if time_range != "any":
        params["time_range"] = time_range
    async with httpx.AsyncClient(timeout=10) as c:
        try:
            r = await c.get(f"{SEARXNG_URL}/search", params=params)
            if r.status_code != 200:
                return []
            return [
                {"title": x.get("title", ""), "url": x.get("url", ""),
                 "snippet": x.get("content", "")[:500], "engine": x.get("engine", "")}
                for x in r.json().get("results", [])[:num_results]
            ]
        except Exception as e:
            logger.error("SearXNG failed: %s", e)
            return []


@mcp.custom_route("/tools/web_search", methods=["POST"])
async def web_search_endpoint(request):
    body = await request.json()
    args = body.get("arguments", {})
    if not args.get("query"):
        return JSONResponse({"error": "query is required"}, status_code=400)
    num = min(max(args.get("num_results", 5), 1), 20)
    results = await _searxng_search(args["query"], num, args.get("time_range", "any"), "general")
    return JSONResponse({"query": args["query"], "num_results": len(results), "results": results})


@mcp.custom_route("/tools/news_search", methods=["POST"])
async def news_search_endpoint(request):
    body = await request.json()
    args = body.get("arguments", {})
    if not args.get("query"):
        return JSONResponse({"error": "query is required"}, status_code=400)
    num = min(max(args.get("num_results", 5), 1), 20)
    results = await _searxng_search(args["query"], num, "week", "news")
    return JSONResponse({"query": args["query"], "num_results": len(results), "results": results})


_HTML_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")
_SCRIPT = re.compile(r"<(script|style)[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL)


def _html_to_text(html):
    return _WS.sub(" ", _HTML_TAG.sub(" ", _SCRIPT.sub("", html))).strip()


@mcp.custom_route("/tools/web_fetch", methods=["POST"])
async def web_fetch_endpoint(request):
    body = await request.json()
    args = body.get("arguments", {})
    url = args.get("url", "")
    if not url:
        return JSONResponse({"error": "url is required"}, status_code=400)
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return JSONResponse({"error": "only http/https supported"}, status_code=400)
    host = parsed.hostname or ""
    if host in BLOCKED_DOMAINS or host.startswith(PRIVATE_PREFIXES):
        return JSONResponse({"error": "private/local URLs blocked"}, status_code=403)
    max_chars = args.get("max_chars", 50000)
    try:
        async with httpx.AsyncClient(timeout=WEB_FETCH_TIMEOUT_S, follow_redirects=True) as c:
            r = await c.get(url, headers={"User-Agent": "Portal5-Research/1.0"})
            if r.status_code >= 400:
                return JSONResponse({"error": f"HTTP {r.status_code}", "url": url})
            text = _html_to_text(r.content[:WEB_FETCH_MAX_BYTES].decode("utf-8", errors="replace"))
            truncated = len(text) > max_chars
            return JSONResponse({
                "url": str(r.url), "status_code": r.status_code,
                "content_type": r.headers.get("content-type", ""),
                "char_count": len(text), "truncated": truncated,
                "text": text[:max_chars] + ("\n\n[...truncated]" if truncated else ""),
            })
    except Exception as e:
        return JSONResponse({"error": str(e)[:200], "url": url}, status_code=502)


def main():
    import uvicorn
    uvicorn.run(mcp.app, host="0.0.0.0", port=int(os.environ.get("RESEARCH_MCP_PORT", "8918")))


if __name__ == "__main__":
    main()
```

**Add to `launch.sh`** the start command for the new MCP (under the existing MCP startup logic):
```bash
python3 -m portal_mcp.research.web_search_mcp &
```

**Verify:**
```bash
python3 -m portal_mcp.research.web_search_mcp &
sleep 2
curl -s http://localhost:8918/health | jq -r .status                                # ok
curl -s http://localhost:8918/tools | jq '. | length'                              # 3
curl -s -X POST http://localhost:8918/tools/web_search \
    -H "Content-Type: application/json" \
    -d '{"arguments": {"query": "MLX Apple Silicon", "num_results": 3}}' \
    | jq '.results | length'                                                       # 3
curl -s -X POST http://localhost:8918/tools/web_fetch \
    -H "Content-Type: application/json" \
    -d '{"arguments": {"url": "http://localhost:8081/"}}' | jq -r .error           # private/local URLs blocked
```

**Rollback:** `git checkout -- portal_mcp/research/web_search_mcp.py launch.sh && rm -rf portal_mcp/research`

**Commit:** `feat(mcp): web search and fetch MCP server (SearXNG-backed, port 8918)`

---

## M3-T03 — Add Embedding + Reranker MLX Models

**Files:** `config/backends.yaml`, `scripts/mlx-proxy.py`

**Diff** in `config/backends.yaml` MLX models list:
```yaml
      # ── Embedding + Reranker (memory + RAG MCPs) ────────────────────────
      - mlx-community/mxbai-embed-large-v1-mlx       # 1024-dim embeddings, ~600MB, MIT
      - mlx-community/bge-reranker-v2-m3-mlx          # multilingual reranker, ~1.2GB
```

**Diff** in `scripts/mlx-proxy.py` `MODEL_MEMORY`:
```diff
+    # Embeddings + reranker (always-loaded for memory + RAG MCPs)
+    "mlx-community/mxbai-embed-large-v1-mlx": 0.6,
+    "mlx-community/bge-reranker-v2-m3-mlx": 1.2,
```

**Pull:**
```bash
hf download mlx-community/mxbai-embed-large-v1-mlx \
    --local-dir /Volumes/data01/models/mlx-community/mxbai-embed-large-v1-mlx
hf download mlx-community/bge-reranker-v2-m3-mlx \
    --local-dir /Volumes/data01/models/mlx-community/bge-reranker-v2-m3-mlx
```

**Verify:**
```bash
ls -la /Volumes/data01/models/mlx-community/mxbai-embed-large-v1-mlx/
ls -la /Volumes/data01/models/mlx-community/bge-reranker-v2-m3-mlx/
```

**Commit:** `feat(catalog): add MLX embedding (mxbai 1024-dim) and reranker (bge-v2-m3)`

---

## M3-T04 — MLX Embedding + Rerank Endpoints

**File:** `scripts/mlx-proxy.py`

The mlx-proxy currently serves `/v1/chat/completions` only. Extend with `/v1/embeddings` (OpenAI-compatible) and `/v1/rerank` (Cohere-style). Embeddings server is **always-loaded** as a third dedicated process alongside `lm` and `vlm` — memory cost ~600MB is tiny vs the reload latency cost on every memory recall.

**Architecture changes:**

1. Add `EMB_MODEL` and `RERANK_MODEL` constants (top of file):
```python
EMB_MODEL = "mlx-community/mxbai-embed-large-v1-mlx"
RERANK_MODEL = "mlx-community/bge-reranker-v2-m3-mlx"
EMB_PORT = int(os.environ.get("MLX_EMB_PORT", "8082"))
RERANK_PORT = int(os.environ.get("MLX_RERANK_PORT", "8083"))
```

2. Add `_emb_proc` and `_rerank_proc` to MLXState; on `start_all()` launch them; on `stop_all()` kill them.

3. Add `_start_emb_server()`:
```python
def _start_emb_server() -> int:
    """Launch mlx-lm embedding server on EMB_PORT, always-on."""
    cmd = [
        "python3", "-m", "mlx_lm.server.embeddings",
        "--model", EMB_MODEL, "--port", str(EMB_PORT), "--host", "127.0.0.1",
    ]
    log_path = os.path.join(_server_log_dir, "mlx_emb.log")
    proc = subprocess.Popen(cmd, stdout=open(log_path, "a"), stderr=subprocess.STDOUT)
    print(f"[proxy] started mlx_emb (PID {proc.pid}) port={EMB_PORT}")
    return proc.pid
```

(Same shape for `_start_rerank_server()` with bge-reranker — mlx-lm 0.30+ has reranker support; if older mlx-lm pinned, use sentence-transformers shim with the MLX safetensors weights.)

4. Add proxy endpoints in the HTTP handler `do_POST`:
```python
def do_POST(self):
    if self.path == "/v1/embeddings":
        self._proxy_request(EMB_PORT)
        return
    if self.path == "/v1/rerank":
        self._proxy_request(RERANK_PORT)
        return
    # ... existing chat completions routing ...

def _proxy_request(self, port):
    """Forward POST body to local port, return response."""
    body = self.rfile.read(int(self.headers["content-length"]))
    try:
        with httpx.Client(timeout=30) as client:
            r = client.post(f"http://127.0.0.1:{port}{self.path}",
                          content=body,
                          headers={"Content-Type": self.headers.get("content-type", "application/json")})
        self.send_response(r.status_code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(r.content)
    except Exception as e:
        self.send_response(500)
        self.end_headers()
        self.wfile.write(json.dumps({"error": str(e)}).encode())
```

5. Update launch sequence: `start_all()` after starting LM server, also start emb + rerank servers (parallel).

**Verify:**
```bash
./launch.sh restart-mlx
sleep 30                                      # let servers settle

# Embeddings endpoint (OpenAI-compatible)
curl -s -X POST http://localhost:8081/v1/embeddings \
    -H "Content-Type: application/json" \
    -d '{"input": "Portal 5 is an inference platform", "model": "mxbai"}' \
    | jq '.data[0].embedding | length'
# Expect: 1024

# Batch embed
curl -s -X POST http://localhost:8081/v1/embeddings \
    -H "Content-Type: application/json" \
    -d '{"input": ["text one", "text two", "text three"]}' \
    | jq '.data | length'
# Expect: 3

# Rerank endpoint
curl -s -X POST http://localhost:8081/v1/rerank \
    -H "Content-Type: application/json" \
    -d '{
        "query": "Apple Silicon LLM",
        "documents": ["MLX runs on Apple Silicon", "Football is a sport", "M4 chip benchmarks"],
        "top_n": 2
    }' | jq '.results | map({index, relevance_score})'
# Expect: indices 0 and 2 ranked above 1
```

**Rollback:** `git checkout -- scripts/mlx-proxy.py && ./launch.sh restart-mlx`

**Commit:** `feat(mlx-proxy): /v1/embeddings and /v1/rerank endpoints (mxbai + bge always-loaded)`

---

## M3-T05 — Memory MCP Server

**File:** `portal_mcp/memory/memory_mcp.py` (new)

Tools: `remember`, `recall`, `forget`, `list_memories`, `clear_memories`. Backed by LanceDB at `/Volumes/data01/portal5_lance/`.

```python
"""Portal 5 Memory MCP Server.

Cross-conversation persistent memory backed by LanceDB.
Each memory has: id, user_id, text, vector, category, tags, created_at,
last_accessed_at, access_count.
Recall is hybrid: vector similarity (top-K) + recency boost + tag filter.

Port: 8919 (MEMORY_MCP_PORT env override).
"""
import logging
import os
import time
import uuid

import httpx
import lancedb
import pyarrow as pa
from starlette.responses import JSONResponse

from portal_mcp.mcp_server.fastmcp import FastMCP

logger = logging.getLogger(__name__)
mcp = FastMCP("memory", host="0.0.0.0")

LANCE_DIR = os.environ.get("PORTAL5_LANCE_DIR", "/Volumes/data01/portal5_lance")
MEMORY_TABLE = "memory"
EMBEDDING_URL = os.environ.get("MLX_EMBEDDING_URL", "http://localhost:8081/v1/embeddings")
EMBEDDING_DIM = 1024
DEFAULT_USER = "default"

_memory_table = None


def _get_table():
    global _memory_table
    if _memory_table is not None:
        return _memory_table
    os.makedirs(LANCE_DIR, exist_ok=True)
    db = lancedb.connect(LANCE_DIR)
    schema = pa.schema([
        pa.field("id", pa.string()),
        pa.field("user_id", pa.string()),
        pa.field("text", pa.string()),
        pa.field("category", pa.string()),
        pa.field("tags", pa.list_(pa.string())),
        pa.field("vector", pa.list_(pa.float32(), EMBEDDING_DIM)),
        pa.field("created_at", pa.float64()),
        pa.field("last_accessed_at", pa.float64()),
        pa.field("access_count", pa.int64()),
    ])
    _memory_table = (db.create_table(MEMORY_TABLE, schema=schema)
                     if MEMORY_TABLE not in db.table_names()
                     else db.open_table(MEMORY_TABLE))
    return _memory_table


async def _embed(text: str) -> list[float]:
    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.post(EMBEDDING_URL, json={"input": text})
        r.raise_for_status()
        return r.json()["data"][0]["embedding"]


@mcp.custom_route("/health", methods=["GET"])
async def health(request):
    try:
        return JSONResponse({"status": "ok", "service": "memory-mcp",
                             "stored": len(_get_table())})
    except Exception as e:
        return JSONResponse({"status": "degraded", "error": str(e)})


TOOLS_MANIFEST = [
    {
        "name": "remember",
        "description": "Store a memory for future recall. Use for: user preferences, persistent facts about the user's projects/work, important conclusions to keep across conversations. Each memory should be self-contained — no pronouns referring to the current chat context.",
        "parameters": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "The memory content. Self-contained sentence."},
                "category": {"type": "string", "enum": ["preference", "fact", "project_context", "conversation_summary"], "default": "fact"},
                "tags": {"type": "array", "items": {"type": "string"}, "default": []},
            },
            "required": ["text"],
        },
    },
    {
        "name": "recall",
        "description": "Retrieve memories relevant to a query. Returns top matches by semantic similarity with recency boost. Use at the start of a conversation to prime context.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "top_k": {"type": "integer", "default": 5, "minimum": 1, "maximum": 20},
                "tags": {"type": "array", "items": {"type": "string"}, "default": []},
                "category": {"type": "string"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "forget",
        "description": "Delete a specific memory by ID. Use when recall returns a stale or incorrect memory.",
        "parameters": {"type": "object", "properties": {"id": {"type": "string"}}, "required": ["id"]},
    },
    {
        "name": "list_memories",
        "description": "List stored memories, optionally filtered by category or tag. For inventory and management.",
        "parameters": {
            "type": "object",
            "properties": {
                "category": {"type": "string"},
                "tags": {"type": "array", "items": {"type": "string"}, "default": []},
                "limit": {"type": "integer", "default": 50, "maximum": 500},
            },
        },
    },
    {
        "name": "clear_memories",
        "description": "Admin: delete all memories. Requires confirm_token='YES_DELETE_ALL'. Cannot be undone.",
        "parameters": {"type": "object", "properties": {"confirm_token": {"type": "string"}}, "required": ["confirm_token"]},
    },
]


@mcp.custom_route("/tools", methods=["GET"])
async def list_tools(request):
    return JSONResponse(TOOLS_MANIFEST)


@mcp.custom_route("/tools/remember", methods=["POST"])
async def remember_endpoint(request):
    body = await request.json()
    args = body.get("arguments", {})
    text = args.get("text", "").strip()
    if not text:
        return JSONResponse({"error": "text is required"}, status_code=400)
    if len(text) > 4000:
        return JSONResponse({"error": "text too long (max 4000 chars)"}, status_code=400)
    try:
        vector = await _embed(text)
    except Exception as e:
        return JSONResponse({"error": f"embedding failed: {e}"}, status_code=503)
    now = time.time()
    record = {
        "id": str(uuid.uuid4()),
        "user_id": DEFAULT_USER,
        "text": text,
        "category": args.get("category", "fact"),
        "tags": args.get("tags", []),
        "vector": vector,
        "created_at": now,
        "last_accessed_at": now,
        "access_count": 0,
    }
    _get_table().add([record])
    return JSONResponse({"id": record["id"], "stored": True, "category": record["category"]})


@mcp.custom_route("/tools/recall", methods=["POST"])
async def recall_endpoint(request):
    body = await request.json()
    args = body.get("arguments", {})
    query = args.get("query", "")
    if not query:
        return JSONResponse({"error": "query is required"}, status_code=400)
    top_k = min(max(args.get("top_k", 5), 1), 20)
    tags = args.get("tags", [])
    category = args.get("category")
    try:
        qvec = await _embed(query)
    except Exception as e:
        return JSONResponse({"error": f"embedding failed: {e}"}, status_code=503)
    table = _get_table()
    where_parts = [f"user_id = '{DEFAULT_USER}'"]
    if category:
        where_parts.append(f"category = '{category}'")
    # Tag filter is OR-of-tags inside AND with user/category
    # LanceDB array-contains via SQL: "tags LIKE ..." doesn't work; use post-filter
    # Get top-K * 3 by vector then filter — cheap because table is small
    fetch_k = min(top_k * 3, 100)
    results = (
        table.search(qvec)
        .where(" AND ".join(where_parts))
        .limit(fetch_k)
        .to_list()
    )
    if tags:
        tags_set = set(tags)
        results = [r for r in results if tags_set & set(r.get("tags", []))]
    # Recency boost: small additive bonus for recent access
    now = time.time()
    for r in results:
        recency = max(0, 1 - (now - r.get("last_accessed_at", 0)) / (90 * 86400))  # 90-day decay
        r["_score"] = r.get("_distance", 1.0) - 0.05 * recency  # lower distance is better
    results = sorted(results, key=lambda r: r["_score"])[:top_k]
    # Update access tracking
    out = []
    for r in results:
        out.append({
            "id": r["id"], "text": r["text"], "category": r["category"],
            "tags": r["tags"],
            "similarity": round(1 - r.get("_distance", 1.0), 3),
            "created_at": r["created_at"],
        })
        # Increment access count (best effort — LanceDB doesn't have native UPDATE; skip for now)
    return JSONResponse({"query": query, "num_results": len(out), "memories": out})


@mcp.custom_route("/tools/forget", methods=["POST"])
async def forget_endpoint(request):
    body = await request.json()
    args = body.get("arguments", {})
    mem_id = args.get("id", "")
    if not mem_id:
        return JSONResponse({"error": "id is required"}, status_code=400)
    try:
        _get_table().delete(f"id = '{mem_id}'")
        return JSONResponse({"id": mem_id, "deleted": True})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@mcp.custom_route("/tools/list_memories", methods=["POST"])
async def list_memories_endpoint(request):
    body = await request.json()
    args = body.get("arguments", {})
    category = args.get("category")
    tags = args.get("tags", [])
    limit = min(args.get("limit", 50), 500)
    table = _get_table()
    where = f"user_id = '{DEFAULT_USER}'"
    if category:
        where += f" AND category = '{category}'"
    rows = table.search().where(where).limit(limit).to_list()
    if tags:
        tags_set = set(tags)
        rows = [r for r in rows if tags_set & set(r.get("tags", []))]
    return JSONResponse({
        "total": len(rows),
        "memories": [
            {"id": r["id"], "text": r["text"][:200], "category": r["category"],
             "tags": r["tags"], "created_at": r["created_at"]}
            for r in rows
        ],
    })


@mcp.custom_route("/tools/clear_memories", methods=["POST"])
async def clear_memories_endpoint(request):
    body = await request.json()
    args = body.get("arguments", {})
    if args.get("confirm_token") != "YES_DELETE_ALL":
        return JSONResponse({"error": "confirm_token must be 'YES_DELETE_ALL'"}, status_code=400)
    _get_table().delete(f"user_id = '{DEFAULT_USER}'")
    return JSONResponse({"deleted": "all", "user_id": DEFAULT_USER})


def main():
    import uvicorn
    uvicorn.run(mcp.app, host="0.0.0.0", port=int(os.environ.get("MEMORY_MCP_PORT", "8919")))


if __name__ == "__main__":
    main()
```

**Add to `requirements.txt`** (or `pyproject.toml`): `lancedb>=0.13`, `pyarrow>=18.0`.

**Add to `launch.sh`** the start command:
```bash
python3 -m portal_mcp.memory.memory_mcp &
```

**Verify:**
```bash
pip install lancedb pyarrow
python3 -m portal_mcp.memory.memory_mcp &
sleep 2

# Health
curl -s http://localhost:8919/health | jq -r .status                                           # ok

# Store
curl -s -X POST http://localhost:8919/tools/remember \
    -H "Content-Type: application/json" \
    -d '{"arguments": {"text": "I prefer concise summaries with bullet points.", "category": "preference", "tags": ["communication"]}}' \
    | jq -r .id
# Expect: a uuid

# Recall
curl -s -X POST http://localhost:8919/tools/recall \
    -H "Content-Type: application/json" \
    -d '{"arguments": {"query": "How does the user want responses formatted?", "top_k": 3}}' \
    | jq '.memories[0].text'
# Expect: matches the preference text

# List
curl -s -X POST http://localhost:8919/tools/list_memories \
    -H "Content-Type: application/json" \
    -d '{"arguments": {"category": "preference"}}' | jq '.total'
# Expect: 1
```

**Rollback:** `git checkout -- portal_mcp/memory/ launch.sh && rm -rf /Volumes/data01/portal5_lance/memory.lance`

**Commit:** `feat(mcp): memory MCP server with LanceDB + mxbai embeddings (port 8919)`

---

## M3-T06 — RAG MCP Server

**File:** `portal_mcp/rag/rag_mcp.py` (new)

Multiple knowledge bases per server. Tools: `kb_list`, `kb_search`, `kb_search_all`, `kb_ingest` (admin). Two-stage retrieval: vector similarity (top-50) → reranker (top-K).

```python
"""Portal 5 RAG MCP Server.

Multiple knowledge bases (KBs) backed by LanceDB. Each KB:
- ingested from local directory of .md, .txt, .pdf, .docx files
- chunked at CHUNK_SIZE chars with CHUNK_OVERLAP overlap
- embedded via MLX mxbai
- two-stage retrieval: vector top-50 → bge reranker top-K

Tools: kb_list, kb_search, kb_search_all, kb_ingest.
Port: 8921 (RAG_MCP_PORT env override).
"""
import asyncio
import hashlib
import logging
import os
import re
import time
from pathlib import Path

import httpx
import lancedb
import pyarrow as pa
from starlette.responses import JSONResponse

from portal_mcp.mcp_server.fastmcp import FastMCP

logger = logging.getLogger(__name__)
mcp = FastMCP("rag", host="0.0.0.0")

LANCE_DIR = os.environ.get("PORTAL5_LANCE_DIR", "/Volumes/data01/portal5_lance")
RAG_DIR = os.path.join(LANCE_DIR, "rag")
KB_SOURCES_DIR = os.environ.get("PORTAL5_KB_SOURCES_DIR", "/Volumes/data01/portal5_kb_sources")
EMBEDDING_URL = os.environ.get("MLX_EMBEDDING_URL", "http://localhost:8081/v1/embeddings")
RERANK_URL = os.environ.get("MLX_RERANK_URL", "http://localhost:8081/v1/rerank")
EMBEDDING_DIM = 1024
CHUNK_SIZE = int(os.environ.get("RAG_CHUNK_SIZE", "1000"))
CHUNK_OVERLAP = int(os.environ.get("RAG_CHUNK_OVERLAP", "150"))

_db = None
_kb_cache = {}


def _get_db():
    global _db
    if _db is None:
        os.makedirs(RAG_DIR, exist_ok=True)
        _db = lancedb.connect(RAG_DIR)
    return _db


def _kb_table_name(kb_id):
    return f"kb_{re.sub(r'[^a-z0-9_]', '_', kb_id.lower())}"


def _kb_table(kb_id, create_if_missing=False):
    name = _kb_table_name(kb_id)
    db = _get_db()
    if name in db.table_names():
        return db.open_table(name)
    if not create_if_missing:
        return None
    schema = pa.schema([
        pa.field("chunk_id", pa.string()),
        pa.field("kb_id", pa.string()),
        pa.field("source_file", pa.string()),
        pa.field("chunk_index", pa.int32()),
        pa.field("text", pa.string()),
        pa.field("vector", pa.list_(pa.float32(), EMBEDDING_DIM)),
        pa.field("char_start", pa.int32()),
        pa.field("char_end", pa.int32()),
        pa.field("ingested_at", pa.float64()),
    ])
    return db.create_table(name, schema=schema)


def _list_kbs():
    """List all KBs by table prefix."""
    return sorted([
        t.replace("kb_", "", 1)
        for t in _get_db().table_names()
        if t.startswith("kb_")
    ])


async def _embed(text):
    async with httpx.AsyncClient(timeout=20) as c:
        r = await c.post(EMBEDDING_URL, json={"input": text})
        r.raise_for_status()
        return r.json()["data"][0]["embedding"]


async def _embed_batch(texts):
    async with httpx.AsyncClient(timeout=120) as c:
        r = await c.post(EMBEDDING_URL, json={"input": texts})
        r.raise_for_status()
        return [d["embedding"] for d in r.json()["data"]]


async def _rerank(query, docs, top_n):
    if len(docs) == 0:
        return []
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.post(RERANK_URL, json={"query": query, "documents": docs, "top_n": top_n})
        if r.status_code != 200:
            # Fallback: return original order if reranker unavailable
            return [{"index": i, "relevance_score": 0.5, "document": d} for i, d in enumerate(docs[:top_n])]
        return r.json()["results"]


@mcp.custom_route("/health", methods=["GET"])
async def health(request):
    try:
        kbs = _list_kbs()
        return JSONResponse({"status": "ok", "service": "rag-mcp", "knowledge_bases": kbs})
    except Exception as e:
        return JSONResponse({"status": "degraded", "error": str(e)})


TOOLS_MANIFEST = [
    {
        "name": "kb_list",
        "description": "List all available knowledge bases (KBs) and their document counts.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "kb_search",
        "description": "Search a specific knowledge base. Returns top relevant chunks with source file and similarity score. Use kb_list first to find available KB IDs.",
        "parameters": {
            "type": "object",
            "properties": {
                "kb_id": {"type": "string", "description": "Knowledge base identifier"},
                "query": {"type": "string"},
                "top_k": {"type": "integer", "default": 5, "minimum": 1, "maximum": 20},
            },
            "required": ["kb_id", "query"],
        },
    },
    {
        "name": "kb_search_all",
        "description": "Search across all knowledge bases simultaneously. Useful when the user's question may match multiple KBs.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "top_k": {"type": "integer", "default": 5, "minimum": 1, "maximum": 20},
            },
            "required": ["query"],
        },
    },
    {
        "name": "kb_ingest",
        "description": "Admin: ingest files from a directory into a knowledge base. Reads .md, .txt, .pdf, .docx files. Run via curl or as setup; not typically called from chat.",
        "parameters": {
            "type": "object",
            "properties": {
                "kb_id": {"type": "string"},
                "source_dir": {"type": "string", "description": "Absolute path to directory of source files"},
                "rebuild": {"type": "boolean", "description": "Drop existing chunks and reingest", "default": False},
            },
            "required": ["kb_id", "source_dir"],
        },
    },
]


@mcp.custom_route("/tools", methods=["GET"])
async def list_tools(request):
    return JSONResponse(TOOLS_MANIFEST)


def _chunk_text(text, chunk_size=CHUNK_SIZE, overlap=CHUNK_OVERLAP):
    """Sliding-window chunk on character boundaries; respects paragraph breaks where possible."""
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        # Try to break on paragraph or sentence boundary near `end`
        if end < len(text):
            for delim in ("\n\n", ". ", "\n"):
                idx = text.rfind(delim, start + chunk_size // 2, end + len(delim))
                if idx > 0:
                    end = idx + len(delim)
                    break
        chunks.append((start, end, text[start:end]))
        start = max(end - overlap, start + 1)
    return chunks


async def _read_file(path):
    """Best-effort text extraction from common formats."""
    suffix = path.suffix.lower()
    if suffix in (".md", ".txt"):
        return path.read_text(encoding="utf-8", errors="replace")
    if suffix == ".pdf":
        try:
            from pypdf import PdfReader
            r = PdfReader(str(path))
            return "\n\n".join(p.extract_text() or "" for p in r.pages)
        except Exception as e:
            logger.warning("PDF read failed for %s: %s", path, e)
            return ""
    if suffix == ".docx":
        try:
            from docx import Document
            d = Document(str(path))
            return "\n\n".join(p.text for p in d.paragraphs)
        except Exception as e:
            logger.warning("DOCX read failed for %s: %s", path, e)
            return ""
    return ""


@mcp.custom_route("/tools/kb_ingest", methods=["POST"])
async def kb_ingest_endpoint(request):
    body = await request.json()
    args = body.get("arguments", {})
    kb_id = args.get("kb_id", "")
    source_dir = args.get("source_dir", "")
    rebuild = args.get("rebuild", False)
    if not kb_id or not source_dir:
        return JSONResponse({"error": "kb_id and source_dir are required"}, status_code=400)
    src = Path(source_dir).expanduser().resolve()
    if not src.is_dir():
        return JSONResponse({"error": f"directory not found: {src}"}, status_code=404)

    if rebuild:
        try:
            _get_db().drop_table(_kb_table_name(kb_id))
        except Exception:
            pass

    table = _kb_table(kb_id, create_if_missing=True)

    files = [f for f in src.rglob("*")
             if f.is_file() and f.suffix.lower() in (".md", ".txt", ".pdf", ".docx")]
    files = files[:5000]   # safety bound

    total_chunks = 0
    for f in files:
        text = await _read_file(f)
        if not text:
            continue
        chunks = _chunk_text(text)
        if not chunks:
            continue
        # Embed in batches of 16
        for batch_start in range(0, len(chunks), 16):
            batch = chunks[batch_start:batch_start + 16]
            try:
                vectors = await _embed_batch([c[2] for c in batch])
            except Exception as e:
                logger.error("embed batch failed for %s: %s", f, e)
                continue
            now = time.time()
            records = []
            for i, ((cstart, cend, ctext), vec) in enumerate(zip(batch, vectors)):
                chunk_id = hashlib.sha1(
                    f"{kb_id}|{f}|{batch_start + i}".encode()
                ).hexdigest()
                records.append({
                    "chunk_id": chunk_id, "kb_id": kb_id, "source_file": str(f.relative_to(src)),
                    "chunk_index": batch_start + i,
                    "text": ctext, "vector": vec, "char_start": cstart, "char_end": cend,
                    "ingested_at": now,
                })
            table.add(records)
            total_chunks += len(records)

    return JSONResponse({"kb_id": kb_id, "files_ingested": len(files),
                         "chunks_added": total_chunks})


@mcp.custom_route("/tools/kb_list", methods=["POST"])
async def kb_list_endpoint(request):
    kbs = []
    for kb_id in _list_kbs():
        t = _kb_table(kb_id)
        if t is not None:
            kbs.append({"kb_id": kb_id, "chunks": len(t)})
    return JSONResponse({"knowledge_bases": kbs})


@mcp.custom_route("/tools/kb_search", methods=["POST"])
async def kb_search_endpoint(request):
    body = await request.json()
    args = body.get("arguments", {})
    kb_id = args.get("kb_id", "")
    query = args.get("query", "")
    top_k = min(args.get("top_k", 5), 20)
    if not kb_id or not query:
        return JSONResponse({"error": "kb_id and query required"}, status_code=400)
    table = _kb_table(kb_id)
    if table is None:
        return JSONResponse({"error": f"unknown kb_id '{kb_id}'"}, status_code=404)

    # Stage 1: vector top-50
    qvec = await _embed(query)
    candidates = table.search(qvec).limit(50).to_list()
    if not candidates:
        return JSONResponse({"kb_id": kb_id, "query": query, "results": []})

    # Stage 2: rerank top-K
    docs = [c["text"] for c in candidates]
    reranked = await _rerank(query, docs, top_k)
    out = []
    for r in reranked:
        c = candidates[r["index"]]
        out.append({
            "chunk_id": c["chunk_id"],
            "source_file": c["source_file"],
            "chunk_index": c["chunk_index"],
            "text": c["text"],
            "rerank_score": round(r["relevance_score"], 4),
        })
    return JSONResponse({"kb_id": kb_id, "query": query, "num_results": len(out), "results": out})


@mcp.custom_route("/tools/kb_search_all", methods=["POST"])
async def kb_search_all_endpoint(request):
    body = await request.json()
    args = body.get("arguments", {})
    query = args.get("query", "")
    top_k = min(args.get("top_k", 5), 20)
    if not query:
        return JSONResponse({"error": "query required"}, status_code=400)
    kbs = _list_kbs()
    if not kbs:
        return JSONResponse({"query": query, "results": []})

    qvec = await _embed(query)
    all_candidates = []
    for kb_id in kbs:
        t = _kb_table(kb_id)
        if t is None:
            continue
        for c in t.search(qvec).limit(20).to_list():
            c["_kb_id"] = kb_id
            all_candidates.append(c)
    if not all_candidates:
        return JSONResponse({"query": query, "results": []})

    docs = [c["text"] for c in all_candidates]
    reranked = await _rerank(query, docs, top_k)
    out = []
    for r in reranked:
        c = all_candidates[r["index"]]
        out.append({
            "kb_id": c["_kb_id"],
            "source_file": c["source_file"],
            "text": c["text"],
            "rerank_score": round(r["relevance_score"], 4),
        })
    return JSONResponse({"query": query, "num_results": len(out), "results": out})


def main():
    import uvicorn
    uvicorn.run(mcp.app, host="0.0.0.0", port=int(os.environ.get("RAG_MCP_PORT", "8921")))


if __name__ == "__main__":
    main()
```

**Add to `launch.sh`**:
```bash
python3 -m portal_mcp.rag.rag_mcp &
```

**Verify:**
```bash
mkdir -p /Volumes/data01/portal5_kb_sources/portal5_docs
# Copy some Portal 5 docs in:
cp docs/HOWTO.md README.md CLAUDE.md /Volumes/data01/portal5_kb_sources/portal5_docs/

python3 -m portal_mcp.rag.rag_mcp &
sleep 2
curl -s http://localhost:8921/health | jq -r .status                                       # ok

# Ingest
curl -s -X POST http://localhost:8921/tools/kb_ingest \
    -H "Content-Type: application/json" \
    -d '{"arguments": {"kb_id": "portal5_docs", "source_dir": "/Volumes/data01/portal5_kb_sources/portal5_docs"}}' \
    | jq '.chunks_added'
# Expect: > 50

# List
curl -s -X POST http://localhost:8921/tools/kb_list -d '{}' | jq .

# Search
curl -s -X POST http://localhost:8921/tools/kb_search \
    -H "Content-Type: application/json" \
    -d '{"arguments": {"kb_id": "portal5_docs", "query": "how does workspace routing work", "top_k": 3}}' \
    | jq '.results[0].text[:200]'
# Expect: chunk discussing workspace routing
```

**Rollback:** `git checkout -- portal_mcp/rag/ launch.sh && rm -rf /Volumes/data01/portal5_lance/rag`

**Commit:** `feat(mcp): RAG MCP server with multi-KB support, two-stage retrieval (port 8921)`

---

## M3-T07 — Register New MCP Servers in Tool Registry

**File:** `portal_pipeline/tool_registry.py`

Update `MCP_SERVERS` dict (added in M2-T01) with the three new servers:

```diff
 MCP_SERVERS = {
     "documents": os.environ.get("MCP_DOCUMENTS_URL", "http://localhost:8910"),
     "execution": os.environ.get("MCP_EXECUTION_URL", "http://localhost:8911"),
     "security": os.environ.get("MCP_SECURITY_URL", "http://localhost:8912"),
     "comfyui": os.environ.get("MCP_COMFYUI_URL", "http://localhost:8913"),
     "music": os.environ.get("MCP_MUSIC_URL", "http://localhost:8914"),
     "video": os.environ.get("MCP_VIDEO_URL", "http://localhost:8915"),
     "whisper": os.environ.get("MCP_WHISPER_URL", "http://localhost:8916"),
     "tts": os.environ.get("MCP_TTS_URL", "http://localhost:8917"),
+    # M3 additions:
+    "research": os.environ.get("MCP_RESEARCH_URL", "http://localhost:8918"),
+    "memory": os.environ.get("MCP_MEMORY_URL", "http://localhost:8919"),
+    "rag": os.environ.get("MCP_RAG_URL", "http://localhost:8921"),
 }
```

**Verify:**
```bash
./launch.sh restart portal-pipeline
# Wait for tool registry to refresh
sleep 60
python3 -c "
import asyncio
from portal_pipeline.tool_registry import tool_registry
n = asyncio.run(tool_registry.refresh(force=True))
names = tool_registry.list_tool_names()
expected = {'web_search', 'web_fetch', 'news_search', 'remember', 'recall', 'forget',
            'list_memories', 'kb_list', 'kb_search', 'kb_search_all'}
missing = expected - set(names)
assert not missing, f'missing: {missing}'
print(f'OK — {n} tools total, all M3 tools present')
"
```

**Commit:** `feat(registry): register research, memory, rag MCP servers`

---

## M3-T08 — Update Workspace Tool Whitelists

**File:** `portal_pipeline/router_pipe.py`

Update WORKSPACES `tools` lists (set in M2-T02) to expose the new MCP tools to relevant workspaces:

```python
"auto-research": {
    ...
    "tools": [
        "web_search", "web_fetch", "news_search",
        "kb_search", "kb_search_all", "kb_list",
        "remember", "recall",
    ],
},
"auto-agentic": {
    ...
    "tools": [
        # ... existing tools ...
        "web_search", "web_fetch",
        "remember", "recall",
        "kb_search", "kb_list",
    ],
},
"auto-compliance": {
    ...
    "tools": [
        # ... existing tools ...
        "kb_search", "kb_list",                    # for compliance KB
        "web_search",                              # for current regulation lookups
    ],
},
"auto-spl": {
    ...
    "tools": ["classify_vulnerability", "kb_search", "kb_list"],
},
"auto-security": {
    ...
    "tools": [
        # ... existing tools ...
        "web_search", "web_fetch",                 # CVE/vendor lookup
        "kb_search", "kb_list",                    # for SOC runbooks
    ],
},
"auto-data": {
    ...
    "tools": [
        # ... existing tools ...
        "kb_search",                               # for data dictionaries
    ],
},
```

`auto-creative` and `auto-coding` intentionally NOT given web_search by default — they don't need live data and adding it expands the attack surface. Personas can override via `tools_allow` if needed.

**Commit:** `feat(routing): expose M3 tools to research/agentic/compliance/security workspaces`

---

## M3-T09 — Information-Access Personas (5 new)

**Files:** 5 new YAML files in `config/personas/`.

### M3-T09a: `config/personas/webresearcher.yaml`

```yaml
name: "🌐 Web Researcher"
slug: webresearcher
category: research
workspace_model: auto-research
system_prompt: |
  You are a meticulous web researcher. You gather information from live sources, verify across multiple sources, and present findings with citations.

  Your protocol:
  1. Restate the user's research goal in one sentence.
  2. Use web_search to find candidate sources. Aim for 3-5 distinct sources from different domains.
  3. Use web_fetch to read the most promising sources in full. Extract the relevant facts.
  4. Cross-reference: if sources disagree, say so explicitly. Don't average disagreements; surface them.
  5. Synthesize: write the answer in your own words. Cite each fact inline using [Source N: domain.com].
  6. Conclude with: "Sources" section listing the URLs you read.

  Rules:
  - Never fabricate citations. Only cite sources you actually fetched.
  - Quote sparingly. Prefer paraphrase. Quotes only when exact wording matters (definitions, legal, policy).
  - Distinguish primary sources (official docs, original announcements) from secondary (blogs about the announcement).
  - For breaking news, use news_search and prefer sources within the past week.
  - For technical questions, prefer official docs and respected publications (e.g., MDN for web standards, RFCs for protocols).
  - When the user's question is ambiguous, ask one clarifying question before searching.

  When you cannot find authoritative answers, say so. "I couldn't verify this from independent sources" is a valid result.
description: "Multi-source web research with citation discipline; uses web_search, web_fetch, news_search"
tags:
  - research
  - web
  - citations
  - fact-finding
tools_allow:
  - web_search
  - web_fetch
  - news_search
  - remember
  - recall
```

### M3-T09b: `config/personas/factchecker.yaml`

```yaml
name: "🔎 Fact Checker"
slug: factchecker
category: research
workspace_model: auto-research
system_prompt: |
  You are a professional fact-checker. You verify claims against primary sources, classify confidence, and surface uncertainty honestly.

  Your verification protocol:
  1. Extract the verifiable claim. If the user gave a paragraph, list each distinct claim.
  2. For each claim:
     - Identify what would constitute proof (a specific source, a specific data point)
     - Use web_search to find authoritative sources
     - Use web_fetch to read in full and confirm context isn't being misrepresented
     - Classify: TRUE / MOSTLY TRUE / MIXED / MOSTLY FALSE / FALSE / UNVERIFIED
  3. Report findings with the strongest source for each claim.

  Rating definitions:
  - TRUE: claim is accurate as stated, primary sources confirm
  - MOSTLY TRUE: claim is accurate but missing important context
  - MIXED: claim contains both true and false elements
  - MOSTLY FALSE: claim is largely incorrect but contains some truth
  - FALSE: claim is contradicted by primary sources
  - UNVERIFIED: insufficient authoritative sources to make a determination

  Rules:
  - Source hierarchy: primary documents > peer-reviewed research > major news outlets > expert blogs > random websites
  - Beware of citation chains where multiple secondary sources cite each other but no primary source exists
  - Date-sensitivity: a claim true in 2020 may be false in 2026 — always note the temporal context
  - If a claim is unfalsifiable (opinion, prediction, value judgment), say so — don't try to fact-check it
  - When a single contradicting source exists but the consensus is broad, weigh accordingly

  Bias awareness: be alert to politically motivated framing. Stick to verifiable facts, not interpretations.
description: "Verify claims against primary sources, classify confidence, identify temporal/contextual issues"
tags:
  - research
  - fact-checking
  - verification
  - citations
tools_allow:
  - web_search
  - web_fetch
  - news_search
  - kb_search
  - kb_search_all
```

### M3-T09c: `config/personas/personalassistant.yaml`

```yaml
name: "🧑‍💼 Personal Assistant"
slug: personalassistant
category: general
workspace_model: auto-reasoning
system_prompt: |
  You are a personal assistant who remembers the user's preferences, projects, and ongoing concerns across conversations. You use the memory tool actively to maintain continuity.

  At the start of every conversation:
  1. Use `recall` with a query like "user preferences" to load communication preferences
  2. Use `recall` with "current projects" or topical to the user's question to load relevant context
  3. Don't dump recalled memories on the user — use them silently to inform your response style and content

  When the user shares new information you should remember:
  - Stated preferences ("I prefer X", "Don't ever do Y") → remember(category="preference")
  - Project context ("I'm working on Z", "My team uses W") → remember(category="project_context")
  - Important facts about them or their work → remember(category="fact")
  - Conclusions from this conversation worth keeping → remember(category="conversation_summary")

  Don't remember:
  - Trivial queries that don't reveal preferences
  - Embarrassing slips, frustrations, or things the user explicitly says "don't remember this"
  - Sensitive personal information unless the user explicitly stores it

  Be transparent about memory:
  - When you recall something relevant, briefly mention it ("Based on your preference for concise summaries...")
  - When you decide to remember something, optionally mention it ("I'll remember that")
  - If asked, list what you remember on a topic
  - If asked to forget something, use `forget` and confirm

  Rules:
  - Remember actively but parsimoniously. The memory store should be useful, not bloated.
  - Periodically review old memories — don't refresh them unnecessarily, but flag stale ones to the user
  - Respect explicit "private — don't store" markers from the user
description: "Cross-conversation memory; learns and applies user preferences and project context"
tags:
  - general
  - memory
  - assistant
  - continuity
tools_allow:
  - remember
  - recall
  - forget
  - list_memories
  - kb_search
  - web_search
```

### M3-T09d: `config/personas/kbnavigator.yaml`

```yaml
name: "📚 Knowledge Base Navigator"
slug: kbnavigator
category: research
workspace_model: auto-research
system_prompt: |
  You are a specialist in retrieving information from custom knowledge bases (KBs). You efficiently locate relevant chunks, synthesize across sources, and cite back to source files.

  Your protocol:
  1. Start with `kb_list` to confirm which KBs are available
  2. For broad questions, use `kb_search_all` to query across all KBs
  3. For domain-specific questions, use `kb_search` with the appropriate kb_id
  4. Read returned chunks carefully — chunk boundaries can split context. If a chunk seems mid-thought, search for adjacent chunks
  5. Synthesize: write the answer in your own words, citing each fact with [Source: <source_file>]
  6. If the KB doesn't contain the answer, say so — don't fall back to general knowledge as if it came from the KB

  When the user asks "what's in this KB?":
  - Return a high-level summary based on representative chunks
  - List the source files
  - Don't dump every chunk

  When the user asks something not in any KB:
  - Confirm with kb_search_all that nothing relevant exists
  - Suggest using webresearcher or general knowledge instead
  - Don't make things up to fill the gap

  When chunks contradict each other:
  - Surface the contradiction, including source files
  - Don't pick a side without justification

  When the question is ambiguous:
  - Run an exploratory search; show the user candidate matches
  - Ask which direction to pursue

  Treat KBs as authoritative for their domain — don't second-guess content unless asked to evaluate it.
description: "Multi-KB retrieval, two-stage rerank, source-file citations"
tags:
  - research
  - knowledge-base
  - rag
  - citations
tools_allow:
  - kb_list
  - kb_search
  - kb_search_all
  - recall
```

### M3-T09e: `config/personas/marketanalyst.yaml`

```yaml
name: "📈 Market Analyst"
slug: marketanalyst
category: research
workspace_model: auto-research
system_prompt: |
  You are a financial market analyst. You provide up-to-date information on companies, markets, and sectors using live web sources.

  Your protocol:
  1. For company-specific questions, use web_search to find recent news, then web_fetch the most authoritative source (SEC filings, official press releases, major financial outlets)
  2. For market-wide questions, use news_search with time_range="week" or "month"
  3. For data points (stock prices, market cap, P/E), confirm against the source's date — financial data ages quickly
  4. Cite sources with publication dates so the user can assess freshness

  Disclaimers you ALWAYS include:
  - "This is informational research, not investment advice."
  - "Verify current data before making financial decisions."
  - "Past performance does not predict future results."

  When asked for predictions:
  - Distinguish between published analyst predictions (which you can report) and your own predictions (which you should decline to make)
  - "According to <source>, the consensus estimate is X" is fine. "I think the stock will go up" is not.

  When asked about specific securities:
  - Be especially careful with date-sensitive data
  - Note the timestamp of any price/cap/volume data you cite
  - Surface conflicting analyst opinions when they exist

  When the user asks for trade execution or recommends a position: politely decline and clarify your role is informational.

  Domains: equities, fixed income, FX, commodities, crypto. For deep niche analysis (specific options strategies, derivatives pricing models), defer to specialist sources.
description: "Up-to-date market research with citations; information only, not investment advice"
tags:
  - research
  - finance
  - markets
  - news
  - analysis
tools_allow:
  - web_search
  - news_search
  - web_fetch
  - kb_search
```

**Update PERSONA_PROMPTS** in `tests/portal5_acceptance_v6.py`:

```python
"webresearcher": (
    "Find three sources discussing Apple's M5 chip and summarize the key benchmark differences from M4.",
    ["m5", "m4", "benchmark", "tflops", "memory bandwidth", "source"],
),
"factchecker": (
    "Fact-check: 'GPT-4 was released by OpenAI in 2022.' Verify against multiple sources.",
    ["false", "released", "march 2023", "source", "verified"],
),
"personalassistant": (
    "What do you remember about my work projects? Use the recall tool.",
    ["recall", "memory", "project", "remember"],
),
"kbnavigator": (
    "List the available knowledge bases and search for content about workspace routing.",
    ["kb_list", "knowledge base", "workspace", "routing", "source"],
),
"marketanalyst": (
    "What's the current state of NVDA stock? Use news_search for recent news.",
    ["nvda", "nvidia", "news", "informational", "verify"],
),
```

**Commit:** `feat(personas): add 5 information-access personas (web/fact/assistant/kb/market)`

---

## M3-T10 — Acceptance Tests (S70)

**File:** `tests/portal5_acceptance_v6.py` (new section S70), or `tests/acceptance/s70_information_access.py` if T-09 modular refactor has landed.

```python
async def S70() -> None:
    """S70: Information access (M3 — web search, memory, RAG)."""
    print("\n━━━ S70. INFORMATION ACCESS ━━━")
    sec = "S70"

    # S70-01: research MCP healthy
    t0 = time.time()
    code, data = await _get("http://localhost:8918/health")
    record(sec, "S70-01", "research MCP /health",
           "PASS" if code == 200 else "FAIL", f"HTTP {code}", t0=t0)

    # S70-02: memory MCP healthy
    t0 = time.time()
    code, data = await _get("http://localhost:8919/health")
    record(sec, "S70-02", "memory MCP /health",
           "PASS" if code == 200 else "FAIL", f"HTTP {code}", t0=t0)

    # S70-03: rag MCP healthy
    t0 = time.time()
    code, data = await _get("http://localhost:8921/health")
    record(sec, "S70-03", "rag MCP /health",
           "PASS" if code == 200 else "FAIL", f"HTTP {code}", t0=t0)

    # S70-04: tool registry includes M3 tools
    t0 = time.time()
    from portal_pipeline.tool_registry import tool_registry
    await tool_registry.refresh(force=True)
    names = set(tool_registry.list_tool_names())
    expected = {"web_search", "web_fetch", "news_search",
                "remember", "recall", "forget", "list_memories",
                "kb_list", "kb_search", "kb_search_all"}
    missing = expected - names
    record(sec, "S70-04", "tool registry includes M3 tools",
           "PASS" if not missing else "FAIL",
           f"missing: {sorted(missing)}" if missing else f"all 10 present", t0=t0)

    # S70-05: web_search works end-to-end through pipeline (auto-research workspace)
    t0 = time.time()
    code, response, model, _ = await _chat_with_model(
        "auto-research",
        "What is MLX? Search the web for the official definition.",
        max_tokens=400, timeout=120,
    )
    if code == 200 and ("apple" in response.lower() or "machine learning" in response.lower()):
        record(sec, "S70-05", "web_search end-to-end", "PASS",
               f"web_search returned relevant result", t0=t0)
    else:
        record(sec, "S70-05", "web_search end-to-end", "FAIL",
               f"HTTP {code}, response: {response[:200]}", t0=t0)

    # S70-06: memory remember + recall round-trip
    t0 = time.time()
    test_text = f"Acceptance test memory marker {int(time.time())}"
    # Direct API (bypass model — we're testing the MCP)
    async with httpx.AsyncClient() as c:
        r1 = await c.post("http://localhost:8919/tools/remember",
                         json={"arguments": {"text": test_text, "category": "fact"}})
        if r1.status_code == 200:
            r2 = await c.post("http://localhost:8919/tools/recall",
                             json={"arguments": {"query": "acceptance test memory", "top_k": 3}})
            r2_json = r2.json()
            found = any(test_text in m.get("text", "") for m in r2_json.get("memories", []))
            record(sec, "S70-06", "memory remember+recall round-trip",
                   "PASS" if found else "FAIL",
                   "marker recalled" if found else "marker not found",
                   t0=t0)
        else:
            record(sec, "S70-06", "memory remember", "FAIL", f"HTTP {r1.status_code}", t0=t0)

    # S70-07: RAG search returns chunks (assumes portal5_docs KB ingested in setup)
    t0 = time.time()
    async with httpx.AsyncClient() as c:
        r = await c.post("http://localhost:8921/tools/kb_list", json={})
        if r.status_code == 200:
            kbs = r.json().get("knowledge_bases", [])
            if kbs:
                kb_id = kbs[0]["kb_id"]
                r2 = await c.post("http://localhost:8921/tools/kb_search",
                                 json={"arguments": {"kb_id": kb_id, "query": "Portal 5", "top_k": 3}})
                if r2.status_code == 200 and r2.json().get("num_results", 0) > 0:
                    record(sec, "S70-07", "rag kb_search returns chunks", "PASS",
                           f"kb={kb_id}, results={r2.json()['num_results']}", t0=t0)
                else:
                    record(sec, "S70-07", "rag kb_search", "FAIL",
                           f"HTTP {r2.status_code} or 0 results", t0=t0)
            else:
                record(sec, "S70-07", "rag kb_search", "INFO",
                       "no KBs ingested yet — run setup", t0=t0)
        else:
            record(sec, "S70-07", "rag kb_list", "FAIL", f"HTTP {r.status_code}", t0=t0)

    # S70-08: webresearcher persona executes full research loop
    t0 = time.time()
    code, response, model, _ = await _chat_with_model(
        "auto-research",
        "Use web_search and web_fetch to find what TPS the M4 Pro achieves on MLX. Cite sources.",
        system="You are webresearcher.",
        max_tokens=600, timeout=240,
    )
    has_citations = "source" in response.lower() or "http" in response.lower()
    record(sec, "S70-08", "webresearcher cites sources",
           "PASS" if code == 200 and has_citations else "WARN",
           f"citations found: {has_citations}", t0=t0)

    # S70-09: SearXNG search latency reasonable
    t0 = time.time()
    async with httpx.AsyncClient() as c:
        r = await c.post("http://localhost:8918/tools/web_search",
                         json={"arguments": {"query": "test", "num_results": 5}}, timeout=10)
    elapsed = time.time() - t0
    record(sec, "S70-09", "SearXNG search latency",
           "PASS" if elapsed < 5 else "WARN",
           f"{elapsed:.1f}s (expect < 5s)", t0=t0)

    # S70-10: web_fetch private-IP block
    t0 = time.time()
    async with httpx.AsyncClient() as c:
        r = await c.post("http://localhost:8918/tools/web_fetch",
                         json={"arguments": {"url": "http://localhost:8081/health"}})
    blocked = "blocked" in (r.json().get("error", "").lower() if r.status_code == 403 else "")
    record(sec, "S70-10", "web_fetch blocks private/local URLs",
           "PASS" if blocked else "FAIL",
           f"HTTP {r.status_code} | blocked={blocked}", t0=t0)
```

**Verify:**
```bash
python3 tests/portal5_acceptance_v6.py --section S70
# Expect: 10 results, mostly PASS. S70-07 may be INFO if KBs not ingested.
```

**Commit:** `test(acc): S70 information-access tests (research/memory/rag MCPs + 2 personas)`

---

## M3-T11 — Documentation

**Files:** `docs/HOWTO.md`, `KNOWN_LIMITATIONS.md`, `CHANGELOG.md`

### HOWTO.md additions

Add three new sections:

**"Web Search and Fetch" section:**
- How SearXNG runs (compose service, port 8920 localhost-only)
- How to set BRAVE_API_KEY for fallback
- How to add/remove search engines in `deploy/searxng/settings.yml`

**"Persistent Memory" section:**
- How memory persists at `/Volumes/data01/portal5_lance/memory.lance`
- How to back up: `tar czf memory_backup.tgz /Volumes/data01/portal5_lance/memory.lance`
- How to clear: `curl -X POST http://localhost:8919/tools/clear_memories -d '{"arguments":{"confirm_token":"YES_DELETE_ALL"}}'`
- Privacy note: memory is stored unencrypted; encrypt the volume if sensitive

**"Knowledge Bases" section:**
- How to create a new KB:
  ```bash
  mkdir -p /Volumes/data01/portal5_kb_sources/<kb_id>
  cp my-docs/*.md /Volumes/data01/portal5_kb_sources/<kb_id>/
  curl -X POST http://localhost:8921/tools/kb_ingest \
      -H "Content-Type: application/json" \
      -d '{"arguments": {"kb_id": "<kb_id>", "source_dir": "/Volumes/data01/portal5_kb_sources/<kb_id>"}}'
  ```
- Recommended KBs to create: `soc2_controls`, `splunk_detections`, `compliance_corpus`, `portal5_docs`
- How to rebuild a KB after source updates: pass `"rebuild": true` to `kb_ingest`
- Storage cost: ~10MB per 100 chunks (vector dim 1024 × 4 bytes + chunk text)

### KNOWN_LIMITATIONS.md

```markdown
### Memory Has No Cross-User Isolation
- **ID:** P5-MEM-001
- **Status:** ACTIVE — single-operator design
- **Description:** Memory MCP namespaces by `user_id` (default = `"default"`). All memories are visible to anyone querying the MCP. For single-operator setup this is fine; if Portal 5 ever serves multiple users, add per-user authentication and namespace selection.

### LanceDB Tables Don't Auto-Compact
- **ID:** P5-MEM-002
- **Status:** ACTIVE — manual maintenance
- **Description:** LanceDB accumulates fragments after many writes/deletes. Periodically run `python3 -c "import lancedb; db = lancedb.connect('/Volumes/data01/portal5_lance'); [t.compact_files() for t in (db.open_table(n) for n in db.table_names())]"` (~monthly).

### RAG Chunking Is Character-Based, Not Token-Based
- **ID:** P5-RAG-001
- **Status:** ACTIVE
- **Description:** RAG MCP chunks at character boundaries (1000 chars default), not token boundaries. Tokenization-aware chunking would be more accurate but requires running the tokenizer per chunk. For most prose this is fine; for code or dense technical content, consider tuning `RAG_CHUNK_SIZE` env.

### SearXNG May Hit Search Engine Rate Limits
- **ID:** P5-SEARCH-001
- **Status:** ACTIVE
- **Description:** SearXNG aggregates from public search engines. High query volume can trigger rate limits or temporary blocks from individual engines. SearXNG handles this gracefully (skips blocked engines, returns from others). For production use, set `BRAVE_API_KEY` as fallback.
```

### CHANGELOG.md

```markdown
## v6.3.0 — Information access (M3)

### Added
- **Web search MCP** (port 8918) — `web_search`, `web_fetch`, `news_search` tools backed by SearXNG (with optional Brave API fallback)
- **Memory MCP** (port 8919) — `remember`, `recall`, `forget`, `list_memories`, `clear_memories` for cross-conversation persistence
- **RAG MCP** (port 8921) — multi-KB retrieval with vector similarity + BGE reranker; `kb_list`, `kb_search`, `kb_search_all`, `kb_ingest`
- **MLX embedding endpoint** (`/v1/embeddings`) and **rerank endpoint** (`/v1/rerank`) on port 8081
- **MLX models added**: `mlx-community/mxbai-embed-large-v1-mlx` (1024-dim), `mlx-community/bge-reranker-v2-m3-mlx`
- **5 information-access personas**: webresearcher, factchecker, personalassistant, kbnavigator, marketanalyst
- **SearXNG container** (port 8920, localhost-only)

### Changed
- `auto-research`, `auto-agentic`, `auto-compliance`, `auto-spl`, `auto-security`, `auto-data` workspaces gained tool whitelist entries for new MCPs

### Tests
- S70 acceptance section: MCP health, tool registry coverage, end-to-end search/memory/RAG via pipeline, persona-driven research loop
```

**Commit:** `docs: M3 information access — HOWTO, KNOWN_LIMITATIONS, CHANGELOG`

---

## Phase Regression

```bash
ruff check . && ruff format --check .
mypy portal_pipeline/ portal_mcp/

# All MCPs healthy
for port in 8910 8911 8912 8913 8914 8915 8916 8917 8918 8919 8921; do
    code=$(curl -s -o /dev/null -w "%{http_code}" "http://localhost:$port/health")
    echo "MCP $port: $code"
done
# Expect: all 200

# Tool registry coverage
python3 -c "
import asyncio
from portal_pipeline.tool_registry import tool_registry
n = asyncio.run(tool_registry.refresh(force=True))
print(f'Tools: {n} (expect >= 37: 27 existing + 10 M3)')
"

# Workspace consistency
python3 -c "
import yaml
from portal_pipeline.router_pipe import WORKSPACES
cfg = yaml.safe_load(open('config/backends.yaml'))
assert set(WORKSPACES.keys()) == set(cfg['workspace_routing'].keys())
"

# Persona count
ls config/personas/*.yaml | wc -l
# Expect: 80 (75 from M1 + 5 from M3)

# S70 + full regression
python3 tests/portal5_acceptance_v6.py --section S70
python3 tests/portal5_acceptance_v6.py 2>&1 | tail -5

# End-to-end smoke: webresearcher persona
curl -s -X POST http://localhost:9099/v1/chat/completions \
    -H "Authorization: Bearer $PIPELINE_API_KEY" \
    -H "Content-Type: application/json" \
    -d '{
        "model": "auto-research",
        "messages": [
            {"role": "system", "content": "You are webresearcher."},
            {"role": "user", "content": "What does the Anthropic homepage say about Claude?"}
        ],
        "max_tokens": 500
    }' | jq -r '.choices[0].message.content'
# Expect: response cites anthropic.com sources
```

---

## Pre-flight checklist

- [ ] M2 has shipped (tool-call orchestration is the substrate for M3)
- [ ] LanceDB and pyarrow installable on the host (`pip install lancedb pyarrow`)
- [ ] External drive `/Volumes/data01/` has ~5GB free for vector indexes
- [ ] SEARXNG_SECRET set in `.env` (operator generates with openssl)
- [ ] Operator-side commitment: ingest at least 2-3 KBs in the first week (otherwise kbnavigator has nothing to work with)

## Post-M3 success indicators

- `webresearcher` persona answers "tech news this week" with 3+ source citations
- `personalassistant` recalls a stated preference 24+ hours later in a fresh conversation
- `kbnavigator` returns relevant chunks from at least one populated KB
- `auto-research` workspace tool-call traffic visible in Prometheus

---

*End of M3. Next milestone: `TASK_M4_INFERENCE_PERFORMANCE.md`. M4 evaluates OMLX as a possible mlx-proxy successor (continuous batching, KV cache persistence, speculative decoding) plus opportunistic speculative decoding via mlx-lm `--draft-model` flag for a faster shipping window.*
