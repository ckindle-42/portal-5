"""S4: Document generation tests."""
import asyncio

from tests.acceptance._common import (
    MCP,
    ROOT,
    _get,
    _mcp,
    record,
)


async def run() -> None:
    """S4: Document generation tests."""
    print("\n━━━ S4. DOCUMENT GENERATION ━━━")
    sec = "S4"

    # S4-01: MCP Documents health
    t0 = time.time()
    code, _ = await _get(f"http://localhost:{MCP['documents']}/health")
    record(
        sec,
        "S4-01",
        "Documents MCP health",
        "PASS" if code == 200 else "FAIL",
        f"HTTP {code}",
        t0=t0,
    )

    # S4-02: Generate Word document
    await _mcp(
        MCP["documents"],
        "create_word_document",
        {
            "title": "Test Proposal",
            "content": "# Project Proposal\n\n## Executive Summary\n\nThis is a test document.\n\n## Timeline\n\n- Phase 1: Planning\n- Phase 2: Implementation",
        },
        section=sec,
        tid="S4-02",
        name="Generate Word document",
        ok_fn=lambda t: "success" in t.lower() or "created" in t.lower() or "docx" in t.lower(),
        timeout=60,
    )

    # S4-03: Generate Excel spreadsheet (tool: create_excel, data as list of lists)
    await _mcp(
        MCP["documents"],
        "create_excel",
        {
            "title": "Test Budget",
            "data": [
                ["Category", "Q1", "Q2"],
                ["Hardware", 1000, 1200],
                ["Software", 500, 600],
            ],
        },
        section=sec,
        tid="S4-03",
        name="Generate Excel spreadsheet",
        ok_fn=lambda t: "success" in t.lower() or "created" in t.lower() or "xlsx" in t.lower(),
        timeout=60,
    )

    # S4-04: Generate PowerPoint
    await _mcp(
        MCP["documents"],
        "create_powerpoint",
        {
            "title": "Test Presentation",
            "slides": [
                {"title": "Introduction", "content": "Welcome to the presentation"},
                {"title": "Overview", "content": "Key points covered today"},
                {"title": "Conclusion", "content": "Thank you"},
            ],
        },
        section=sec,
        tid="S4-04",
        name="Generate PowerPoint",
        ok_fn=lambda t: "success" in t.lower() or "created" in t.lower() or "pptx" in t.lower(),
        timeout=60,
    )

    # S4-05..S4-08: Document read tools
    _FIXTURES = ROOT / "tests" / "fixtures"
    _READ_TESTS = [
        ("S4-05", "read_word_document", "sample.docx", "docx"),
        ("S4-06", "read_excel", "sample.xlsx", "xlsx"),
        ("S4-07", "read_powerpoint", "sample.pptx", "pptx"),
        ("S4-08", "read_pdf", "sample.pdf", "pdf"),
    ]
    for n, (tid, tool, fixture, ext) in enumerate(_READ_TESTS, 5):
        fixture_path = _FIXTURES / fixture
        t0 = time.time()
        if not fixture_path.exists():
            record(sec, tid, f"MCP {tool}", "SKIP", f"fixture {fixture} missing", t0=t0)
            continue
        try:
            from mcp import ClientSession  # noqa: PLC0415
            from mcp.client.streamable_http import streamablehttp_client  # noqa: PLC0415

            url = f"http://localhost:{MCP['documents']}/mcp"
            async with streamablehttp_client(url) as (read_, write_, _):
                async with ClientSession(read_, write_) as session:
                    await session.initialize()
                    result = await asyncio.wait_for(
                        session.call_tool(tool, {"file_path": str(fixture_path)}),
                        timeout=30,
                    )
                    content = "".join(b.text for b in result.content if hasattr(b, "text"))
            if content:
                record(
                    sec,
                    tid,
                    f"MCP {tool}",
                    "PASS",
                    f"got {len(content)} chars from {fixture}",
                    t0=t0,
                )
            else:
                record(sec, tid, f"MCP {tool}", "FAIL", "empty result", t0=t0)
        except asyncio.TimeoutError:
            record(sec, tid, f"MCP {tool}", "WARN", "timeout after 30s", t0=t0)
        except ImportError:
            record(
                sec, tid, f"MCP {tool}", "FAIL", "pip install mcp --break-system-packages", t0=t0
            )
        except Exception as e:
            record(sec, tid, f"MCP {tool}", "FAIL", str(e)[:120], t0=t0)
