"""Hunt views page within the tool-result byte budget and never lose an item or a field."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from portal.modules.security.core.hunt import product_jobs
from portal.modules.security.tools import review_mcp

LIMIT = review_mcp._hunt_result_byte_limit()
FAT = "f" * 2000


@pytest.fixture(autouse=True)
def _hunt_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(product_jobs, "_ROOT", tmp_path)


def _encoded(value: dict[str, Any]) -> int:
    return len(json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))


def _store(job_id: str, tmp_path: Path, files: dict[str, Any]) -> str:
    run_dir = tmp_path / job_id
    run_dir.mkdir()
    for name, payload in files.items():
        path = run_dir / name
        if name.endswith(".jsonl"):
            path.write_text("".join(json.dumps(row) + "\n" for row in payload))
        else:
            path.write_text(json.dumps(payload))
    product_jobs._write(
        job_id,
        {
            "job_id": job_id,
            "index": "ix",
            "status": "COMPLETE",
            "stage": "done",
            "started": 1.0,
            "finished": 2.0,
            "run_dir": str(run_dir),
        },
    )
    return job_id


def _lead_rows(count: int) -> list[dict[str, Any]]:
    return [
        {
            "notable_id": f"notable-{index:02d}",
            "generator": "alerts",
            "source_id": f"hb_kyoushi_s1:{FAT}",
            "why": f"reason {index:02d} " + FAT,
            "evidence": [{"line": "line", "query": "search index=ix " + FAT}],
        }
        for index in range(count)
    ]


def _page_all(view: Any, **kwargs: Any) -> list[dict[str, Any]]:
    """Follow next_offset to the end of a view, asserting each page fits the budget."""
    items: list[dict[str, Any]] = []
    while True:
        page = view(**kwargs)
        assert "error" not in page, page
        assert _encoded(page) <= LIMIT, _encoded(page)
        items.extend(page[next(key for key in page if isinstance(page[key], list))])
        if "next_offset" not in page:
            return items
        kwargs["offset"] = page["next_offset"]


def test_paging_leads_to_the_end_returns_every_lead_once_in_rank_order(tmp_path: Path) -> None:
    job_id = _store("hunt-r2-page-leads", tmp_path, {"notables.jsonl": _lead_rows(10)})
    items = _page_all(review_mcp.hunt_leads, job_id=job_id, n=5)
    assert [lead["rank"] for lead in items] == list(range(1, 11))
    assert [lead["notable_id"] for lead in items] == [f"notable-{index:02d}" for index in range(10)]
    first = review_mcp.hunt_leads(job_id=job_id, n=5)
    assert first["total_leads"] == 10
    assert first["omitted_leads"] == 10 - len(first["leads"])
    assert first["next_offset"] == len(first["leads"])


def test_shortened_lead_fields_are_marked_and_full_values_are_retrievable(tmp_path: Path) -> None:
    why = "reason 00 " + "w" * 80
    query = "search index=ix " + "q" * 104
    source = "hb_kyoushi_s1:" + "s" * 56
    rows = [
        {
            "notable_id": "notable-00",
            "generator": "alerts",
            "source_id": source,
            "why": why,
            "evidence": [{"line": "line", "query": query}],
        }
    ]
    job_id = _store("hunt-r2-lead-marks", tmp_path, {"notables.jsonl": rows})
    lead = review_mcp.hunt_leads(job_id=job_id, n=3)["leads"][0]
    assert lead["why_truncated"] is True
    assert lead["evidence_query_truncated"] is True
    assert lead["source_truncated"] is True
    assert lead["why"].startswith("reason 00 ")
    detail = review_mcp.hunt_leads(job_id=job_id, notable_id="notable-00")
    assert detail["why"] == why
    assert detail["evidence_query"] == query
    assert detail["source"] == source
    assert detail["rank"] == 1
    assert "error" in review_mcp.hunt_leads(job_id=job_id, notable_id="missing")


def test_worst_case_detail_is_the_single_item_error_case(tmp_path: Path) -> None:
    job_id = _store("hunt-r2-lead-fat-detail", tmp_path, {"notables.jsonl": _lead_rows(1)})
    detail = product_jobs.lead_detail(job_id, None, "notable-00")
    assert detail["why"] == "reason 00 " + FAT
    assert detail["evidence_query"] == "search index=ix " + FAT
    page = review_mcp.hunt_leads(job_id=job_id, notable_id="notable-00")
    assert page["error"] == "hunt response exceeds the configured tool-loop result limit"
    assert page["max_bytes"] == LIMIT
    assert page["result_bytes"] > LIMIT


def test_paging_case_evidence_to_the_end_returns_every_line_once(tmp_path: Path) -> None:
    lines = [
        {"source": f"source-{index:02d}", "line": f"line {index:02d} " + "l" * 160}
        for index in range(25)
    ]
    job_id = _store(
        "hunt-r2-page-case",
        tmp_path,
        {"relate.json": {"cases": [{"case_id": "c1", "evidence": lines}]}},
    )
    items = _page_all(review_mcp.hunt_case, job_id=job_id, case=1, n=3)
    assert [row["source"] for row in items] == [f"source-{index:02d}" for index in range(25)]
    assert all(row["line_truncated"] is True for row in items)
    first = review_mcp.hunt_case(job_id=job_id, case=1, n=3)
    assert first["evidence_count"] == 25
    assert first["evidence_omitted"] == 25 - first["next_offset"]
    detail = review_mcp.hunt_case(job_id=job_id, case=1, evidence=24)
    assert detail["line"] == "line 24 " + "l" * 160
    assert "error" in review_mcp.hunt_case(job_id=job_id, case=1, evidence=25)


def test_paging_source_cards_to_the_end_returns_every_card_once(tmp_path: Path) -> None:
    reason = "reason 3 " + "r" * 110
    cards = [
        {
            "card_id": f"card-{index}",
            "source_id": f"source-{index}",
            "kind": "other",
            "understood": False,
            "reason": f"reason {index} " + "r" * 110,
        }
        for index in range(7)
    ]
    job_id = _store(
        "hunt-r2-page-sources",
        tmp_path,
        {"sources.json": {"totals": {"sources": 7, "cards": 7, "understood": 0}, "cards": cards}},
    )
    items = _page_all(review_mcp.hunt_sources, job_id=job_id, n=3)
    assert [row["source"] for row in items] == [f"source-{index}" for index in range(7)]
    assert all(row["reason_truncated"] is True for row in items)
    full = review_mcp.hunt_sources(job_id=job_id, source="source-3")
    assert full["cards"] == [
        {"source": "source-3", "kind": "other", "reason": reason, "understood": False}
    ]
    assert "error" in review_mcp.hunt_sources(job_id=job_id, source="absent")


def test_single_item_that_cannot_fit_even_alone_still_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    job_id = _store("hunt-r2-page-fat", tmp_path, {"notables.jsonl": _lead_rows(1)})
    monkeypatch.setattr(review_mcp, "_hunt_result_byte_limit", lambda: 200)
    page = review_mcp.hunt_leads(job_id=job_id, n=1)
    assert page["error"] == "hunt response exceeds the configured tool-loop result limit"
    assert page["max_bytes"] == 200
    assert page["result_bytes"] > 200


def test_views_reject_a_negative_offset(tmp_path: Path) -> None:
    lines = [{"source": "source-0", "line": "l"}]
    job_id = _store(
        "hunt-r2-page-neg",
        tmp_path,
        {
            "notables.jsonl": _lead_rows(1),
            "relate.json": {"cases": [{"case_id": "c1", "evidence": lines}]},
            "sources.json": {"totals": {}, "cards": []},
        },
    )
    for call in (
        lambda: review_mcp.hunt_leads(job_id=job_id, offset=-1),
        lambda: review_mcp.hunt_case(job_id=job_id, offset=-1),
        lambda: review_mcp.hunt_sources(job_id=job_id, offset=-1),
    ):
        assert call()["error"] == "offset must be 0 or greater"


def test_paging_defaults_stay_bounded_without_a_byte_limit(tmp_path: Path) -> None:
    job_id = _store("hunt-r2-page-legacy", tmp_path, {"notables.jsonl": _lead_rows(5)})
    view = product_jobs.leads_view(job_id=job_id, n=25)
    assert len(view["leads"]) == product_jobs.LEADS_VIEW_LIMIT
    assert view["total_leads"] == 5
    assert "error" not in view
