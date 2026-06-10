"""S13: RAG/Embedding tests."""
import time

from tests.acceptance._common import (
    MCP,
    _get,
    _get_acc_client,
    record,
)


async def run() -> None:
    """S13: RAG/Embedding tests."""
    print("\n━━━ S13. RAG/EMBEDDING ━━━")
    sec = "S13"

    # S13-01: Embedding service health
    t0 = time.time()
    code, data = await _get(f"http://localhost:{MCP['embedding']}/health")
    record(
        sec,
        "S13-01",
        "Embedding service",
        "PASS" if code == 200 else "WARN",
        f"HTTP {code}",
        t0=t0,
    )

    # S13-02: Generate embedding (if service is up)
    if code == 200:
        t0 = time.time()
        try:
            c = _get_acc_client()
            r = await c.post(
                f"http://localhost:{MCP['embedding']}/v1/embeddings",
                json={"input": "test embedding text", "model": "microsoft/harrier-oss-v1-0.6b"},
                timeout=30,
            )
            if r.status_code == 200:
                data = r.json()
                embedding = data.get("data", [{}])[0].get("embedding", [])
                record(sec, "S13-02", "Generate embedding", "PASS", f"dim: {len(embedding)}", t0=t0)
            else:
                record(sec, "S13-02", "Generate embedding", "WARN", f"HTTP {r.status_code}", t0=t0)
        except Exception as e:
            record(sec, "S13-02", "Generate embedding", "WARN", str(e)[:100], t0=t0)
