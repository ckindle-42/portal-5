"""The exposed MCP and CLI adapters call the same public review runtime."""

from __future__ import annotations

from pathlib import Path

import pytest

from portal.modules.security.core.review import service
from portal.modules.security.core.review.service import ReviewRuntime
from portal.modules.security.tools import review_mcp

from .test_service_knowledge import _fixture


def _runtime(tmp_path: Path) -> ReviewRuntime:
    records, _training, source, request, reference = _fixture()
    return ReviewRuntime(
        source=source,
        embedder=None,
        index=None,
        reference=reference,
        config=request.config,
        environment_id=request.environment_id,
        review_dir=tmp_path,
        calibration_records_by_source=records,
        splunk_health=lambda: {"reachable": True, "indexes": {"memory": 240}},
        reasoning_model_probe=lambda: ["reasoner:test"],
    )


def test_every_review_surface_is_registered_natively() -> None:
    import asyncio

    names = {tool.name for tool in asyncio.run(review_mcp.mcp.list_tools())}
    assert names == {
        "review_start",
        "review_status",
        "review_result",
        "review_cancel",
        "review_verdict",
        "review_queue",
        "review_explain",
        "review_doctor",
    }


def test_mcp_start_status_and_result_use_the_durable_runtime(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime = _runtime(tmp_path)
    monkeypatch.setattr(review_mcp, "_runtime", runtime)
    try:
        started = review_mcp.review_start(
            sources=[
                {"index": "memory", "sourcetype": "wineventlog"},
                {"index": "memory", "sourcetype": "web:access"},
                {"index": "memory", "sourcetype": "linux:audit"},
            ],
            start=0.0,
            end=80.0,
            environment_id="memory-env",
        )
        run_id = str(started["run_id"])
        runtime.worker.join(run_id, timeout=10)
        status = review_mcp.review_status(run_id)
        result = review_mcp.review_result(run_id)
        assert status["status"] == "COMPLETE"
        assert result["run_id"] == run_id
        assert result["concerns"]
    finally:
        runtime.close()
        monkeypatch.setattr(review_mcp, "_runtime", None)


def test_cli_parser_exposes_all_requested_operations() -> None:
    from portal.modules.security.core.review_cli import _parser

    parser = _parser()
    examples = (
        ["run", "--source", "idx:type", "--start", "1", "--end", "2"],
        ["status", "run-1"],
        ["result", "run-1"],
        ["verdict", "cn-1", "something", "--actor", "analyst:test"],
        ["queue"],
        ["explain", "cn-1"],
        ["doctor"],
    )
    assert {parser.parse_args(example).command for example in examples} == {
        "run",
        "status",
        "result",
        "verdict",
        "queue",
        "explain",
        "doctor",
    }


def test_t3_default_reader_is_no_reader() -> None:
    # The T3 default is an engine behavior, not a model name. The live factory sets judge=None.
    assert service.DEFAULT_READER is None
