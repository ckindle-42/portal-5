"""The exposed MCP and CLI adapters call the same public review runtime."""

from __future__ import annotations

import json
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


def test_manifest_matches_review_dispatch() -> None:
    manifest_path = (
        Path(__file__).resolve().parents[3]
        / "config"
        / "security"
        / ("tools_manifest_review_mcp.json")
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    names = {str(item["name"]) for item in manifest}
    assert names == set(review_mcp._DISPATCH)
    assert names == {str(item["name"]) for item in review_mcp.TOOLS_MANIFEST}
    assert len(names) == 8


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
