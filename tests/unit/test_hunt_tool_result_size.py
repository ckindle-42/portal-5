"""Guard the default R2 hunt tool views against the served chat-loop budget."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import yaml

from portal.platform.mcp_host.tool_support import tool_result_byte_budget

FIXTURE = Path(__file__).parents[1] / "fixtures" / "hunt_tool_result_size.json"
# Redacted receipt excerpts plus a test-only job envelope from the named Kyoushi bundle.
HUNT_TOOLS = {"hunt_sources", "hunt_start", "hunt_status", "hunt_leads", "hunt_case"}
BOUNDED_TOOL_PARAMETERS = {
    "hunt_sources": {"job_id", "index", "n"},
    "hunt_start": {
        "index",
        "start",
        "end",
        "query_seconds",
        "job_seconds",
        "request_budget",
        "cell_budget",
        "event_budget",
        "judge",
    },
    "hunt_status": {"job_id", "index"},
    "hunt_leads": {"job_id", "index", "n"},
    "hunt_case": {"job_id", "index", "case", "n"},
}


def _encoded_size(value: dict[str, Any]) -> int:
    return len(json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))


def test_chat_hunt_tool_schemas_expose_only_budgeted_parameters() -> None:
    from portal.modules.security.tools import review_mcp

    tools = asyncio.run(review_mcp.mcp.list_tools())
    properties = {
        tool.name: set(tool.input_schema["properties"]) for tool in tools if tool.name in HUNT_TOOLS
    }
    assert properties == BOUNDED_TOOL_PARAMETERS


def test_default_hunt_tool_results_fit_smallest_served_seat(
    tmp_path: Path, monkeypatch: Any
) -> None:
    from portal.modules.security.tools import review_mcp

    fixture = json.loads(FIXTURE.read_text())
    r2_jobs = review_mcp.r2_hunt_jobs
    monkeypatch.setattr(r2_jobs, "_ROOT", tmp_path)
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "sources.json").write_text(json.dumps(fixture["sources"]))
    (run_dir / "notables.jsonl").write_text(
        "\n".join(json.dumps(row) for row in fixture["notables"]) + "\n"
    )
    (run_dir / "relate.json").write_text(json.dumps({"cases": [fixture["case"]]}))
    job = {**fixture["job"], "run_dir": str(run_dir)}
    r2_jobs._write(job["job_id"], job)

    portal = yaml.safe_load((Path(__file__).parents[2] / "config" / "portal.yaml").read_text())
    workspaces = portal["workspaces"].values()
    hunt_contexts = [
        int(workspace["context_limit"])
        for workspace in workspaces
        if HUNT_TOOLS.intersection(workspace.get("tools", []))
    ]
    assert hunt_contexts
    smallest_context = min(hunt_contexts)
    byte_budget = tool_result_byte_budget(smallest_context)
    assert byte_budget == smallest_context
    result_limit = byte_budget // 8

    class Search:
        def iter_post(self, _query: str, _start: float, _end: float) -> list[dict[str, Any]]:
            return [{"index": f"index-{i:03d}", "count": i} for i in range(100)]

    monkeypatch.setattr(review_mcp, "_hunt_search", Search)
    monkeypatch.setattr(review_mcp.r2_hunt_jobs, "start", lambda *_a, **_k: job["job_id"])
    outputs = {
        "hunt_sources discovery": review_mcp.hunt_sources(),
        "hunt_sources stored": review_mcp.hunt_sources(job_id=job["job_id"]),
        "hunt_start": review_mcp.hunt_start(index=job["index"]),
        "hunt_status": review_mcp.hunt_status(job_id=job["job_id"]),
        "hunt_leads": review_mcp.hunt_leads(job_id=job["job_id"]),
        "hunt_case": review_mcp.hunt_case(job_id=job["job_id"]),
    }

    oversized = {name: _encoded_size(output) for name, output in outputs.items()}
    assert all(size <= result_limit for size in oversized.values()), oversized
    assert set(outputs["hunt_status"]) >= {
        "status",
        "stage",
        "stages_done",
        "elapsed_s",
        "last_progress",
        "partial_reason",
        "next",
    }
    assert "progress" not in outputs["hunt_status"]
    assert set(outputs["hunt_sources stored"]) >= {"counts", "not_understood"}
    assert set(outputs["hunt_leads"]["leads"][0]) == {
        "rank",
        "notable_id",
        "generator",
        "source",
        "why",
        "evidence_query",
    }
    assert set(outputs["hunt_case"]) >= {
        "anchor",
        "seed_count",
        "evidence",
        "evidence_count",
        "evidence_omitted",
    }
