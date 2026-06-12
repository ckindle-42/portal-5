"""S70: M3 information access MCPs — research, memory, RAG, SearXNG."""

import time
import uuid

from tests.acceptance._common import (
    EMBEDDING_URL,
    ROOT,
    SEARXNG_URL,
    _get_acc_client,
    record,
)


async def run() -> None:
    """S70: M3 information access MCPs — research, memory, RAG, SearXNG."""
    print("\n━━━ S70. M3 INFORMATION ACCESS MCPS ━━━")
    sec = "S70"

    # S70-01: SearXNG search
    t0 = time.time()
    try:
        c = _get_acc_client()
        r = await c.get(f"{SEARXNG_URL}/search?q=test&format=json", timeout=15)
        if r.status_code == 200:
            data = r.json()
            results = data.get("results", [])
            record(
                sec,
                "S70-01",
                "SearXNG web search",
                "PASS",
                f"{len(results)} results returned",
                t0=t0,
            )
        else:
            record(sec, "S70-01", "SearXNG web search", "WARN", f"HTTP {r.status_code}", t0=t0)
    except Exception as e:
        record(sec, "S70-01", "SearXNG web search", "FAIL", str(e)[:100], t0=t0)

    # S70-02: Research MCP health
    t0 = time.time()
    try:
        c = _get_acc_client()
        r = await c.get("http://localhost:8922/health", timeout=10)
        if r.status_code == 200:
            record(sec, "S70-02", "Research MCP health", "PASS", r.text[:80], t0=t0)
        else:
            record(sec, "S70-02", "Research MCP health", "WARN", f"HTTP {r.status_code}", t0=t0)
    except Exception as e:
        record(sec, "S70-02", "Research MCP health", "WARN", f"not running: {str(e)[:60]}", t0=t0)

    # S70-03: Memory MCP health
    t0 = time.time()
    try:
        c = _get_acc_client()
        r = await c.get("http://localhost:8920/health", timeout=10)
        if r.status_code == 200:
            record(sec, "S70-03", "Memory MCP health", "PASS", r.text[:80], t0=t0)
        else:
            record(sec, "S70-03", "Memory MCP health", "WARN", f"HTTP {r.status_code}", t0=t0)
    except Exception as e:
        record(sec, "S70-03", "Memory MCP health", "WARN", f"not running: {str(e)[:60]}", t0=t0)

    # S70-04: RAG MCP health
    t0 = time.time()
    try:
        c = _get_acc_client()
        r = await c.get("http://localhost:8921/health", timeout=10)
        if r.status_code == 200:
            record(sec, "S70-04", "RAG MCP health", "PASS", r.text[:80], t0=t0)
        else:
            record(sec, "S70-04", "RAG MCP health", "WARN", f"HTTP {r.status_code}", t0=t0)
    except Exception as e:
        record(sec, "S70-04", "RAG MCP health", "WARN", f"not running: {str(e)[:60]}", t0=t0)

    # S70-05: Embedding service
    t0 = time.time()
    try:
        c = _get_acc_client()
        r = await c.get(f"{EMBEDDING_URL}/health", timeout=10)
        if r.status_code == 200:
            record(sec, "S70-05", "Embedding service health", "PASS", r.text[:80], t0=t0)
        else:
            record(
                sec, "S70-05", "Embedding service health", "WARN", f"HTTP {r.status_code}", t0=t0
            )
    except Exception as e:
        record(sec, "S70-05", "Embedding service health", "WARN", str(e)[:100], t0=t0)

    # S70-06: Research personas exist
    t0 = time.time()
    research_personas = [
        "webresearcher",
        "factchecker",
        "kbnavigator",
        "marketanalyst",
        "supergemma4researcher",
        "gemmaresearchanalyst",
    ]
    found = []
    for p in research_personas:
        if (ROOT / "config" / "personas" / f"{p}.yaml").exists():
            found.append(p)
    if len(found) == len(research_personas):
        record(
            sec,
            "S70-06",
            "Research personas",
            "PASS",
            f"{len(found)}/{len(research_personas)} present",
            t0=t0,
        )
    else:
        missing = [p for p in research_personas if p not in found]
        record(sec, "S70-06", "Research personas", "WARN", f"missing: {missing}", t0=t0)

    # S70-07: web_search in auto-research workspace tools
    t0 = time.time()
    try:
        from portal_pipeline.router_pipe import WORKSPACES

        research_tools = WORKSPACES.get("auto-research", {}).get("tools", [])
        has_search = "web_search" in research_tools
        has_fetch = "web_fetch" in research_tools
        if has_search and has_fetch:
            record(
                sec,
                "S70-07",
                "auto-research tool whitelist",
                "PASS",
                f"tools: {research_tools}",
                t0=t0,
            )
        else:
            record(
                sec,
                "S70-07",
                "auto-research tool whitelist",
                "WARN",
                f"missing web_search/web_fetch in {research_tools}",
                t0=t0,
            )
    except Exception as e:
        record(sec, "S70-07", "auto-research tool whitelist", "FAIL", str(e)[:100], t0=t0)

    # S70-08: Memory MCP cross-session round-trip
    # Stores a tagged fact, runs a recall query that should match it,
    # asserts the fact came back, then cleans up. Tests the direct API
    # — does NOT exercise model tool-calling (covered separately by UAT
    # A-08). A failure here points to: Memory MCP service down, LanceDB
    # schema break, embedding service down, or vector index broken.
    t0 = time.time()
    try:
        c = _get_acc_client()
        # Tag with a unique marker so this run never collides with another
        # invocation, and we can recall by tag deterministically.
        unique_tag = f"acceptance-s70-08-{uuid.uuid4().hex[:12]}"
        fact_text = (
            f"For acceptance test {unique_tag}: the Portal 5 mascot is a hexagonal "
            "lantern named Lumi. This is a test marker; safe to forget."
        )
        # Step 1: remember
        r_store = await c.post(
            "http://localhost:8920/tools/remember",
            json={
                "arguments": {
                    "text": fact_text,
                    "category": "test",
                    "tags": ["acceptance", unique_tag],
                }
            },
            timeout=15,
        )
        if r_store.status_code != 200:
            record(
                sec,
                "S70-08",
                "Memory MCP round-trip",
                "FAIL",
                f"remember HTTP {r_store.status_code}: {r_store.text[:120]}",
                t0=t0,
            )
        else:
            mem_id = r_store.json().get("id", "")
            # Step 2: recall — deliberately query for the *content* not the tag,
            # so this exercises the embedding+vector path. Tag filter would
            # bypass the actual semantic recall.
            r_recall = await c.post(
                "http://localhost:8920/tools/recall",
                json={
                    "arguments": {
                        "query": "what is the Portal 5 mascot",
                        "top_k": 10,
                        "tags": ["acceptance", unique_tag],  # constrain to this run
                    }
                },
                timeout=15,
            )
            if r_recall.status_code != 200:
                record(
                    sec,
                    "S70-08",
                    "Memory MCP round-trip",
                    "FAIL",
                    f"recall HTTP {r_recall.status_code}: {r_recall.text[:120]}",
                    t0=t0,
                )
            else:
                memories = r_recall.json().get("memories", [])
                # Find our fact by ID (avoids false positives from other tagged data)
                hit = next((m for m in memories if m.get("id") == mem_id), None)
                if hit:
                    sim = hit.get("similarity", 0.0)
                    record(
                        sec,
                        "S70-08",
                        "Memory MCP round-trip",
                        "PASS",
                        f"stored+recalled: id={mem_id[:8]}, sim={sim:.2f}, {len(memories)} hits",
                        t0=t0,
                    )
                else:
                    record(
                        sec,
                        "S70-08",
                        "Memory MCP round-trip",
                        "FAIL",
                        f"stored {mem_id[:8]} but recall returned "
                        f"{len(memories)} memories without it",
                        t0=t0,
                    )
            # Step 3: cleanup — best-effort, never fails the test
            try:
                await c.post(
                    "http://localhost:8920/tools/forget",
                    json={"arguments": {"id": mem_id}},
                    timeout=10,
                )
            except Exception:
                pass
    except Exception as e:
        record(sec, "S70-08", "Memory MCP round-trip", "FAIL", str(e)[:120], t0=t0)


# ══════════════════════════════════════════════════════════════════════════════
# Report Generation
# ══════════════════════════════════════════════════════════════════════════════
