from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from portal.modules.security.core.review.contracts import (
    Channel,
    EvidenceRef,
    Outcome,
    ReviewConcern,
)
from portal.modules.security.core.review.intake import EventView, IntakeResult, event_id_for
from portal.modules.security.core.review.judge import ModelReply
from portal.modules.security.core.review.reader import build_judge_fn
from portal.modules.security.core.review.tools import ToolBox
from portal.modules.security.core.review.window import SourceSpec


class FakePivotSource:
    partition_seconds = 60

    def __init__(self, *, expected: int = 1) -> None:
        self.expected = expected
        self.searches: list[str] = []

    def _post(self, search: str, start: float, _end: float) -> list[Mapping[str, Any]]:
        self.searches.append(search)
        if "| stats count" in search:
            return [{"count": self.expected}]
        return [
            {
                "_time": start + 1,
                "_raw": "host=wkstn42 event=service-started",
                "host": "wkstn42",
            }
        ]


class ScriptedClient:
    def __init__(self) -> None:
        self.replies = [
            ModelReply(
                text=(
                    '{"action":"conclude","verdict":"something","confidence":0.8,'
                    '"claims":[{"text":"service started","evidence_ids":["src:evt"],'
                    '"quote":"event=service-started"}]}'
                ),
                reasoning="measured reasoning channel",
            ),
            ModelReply(text='{"stance":"upheld","objections":[]}', reasoning="challenge reasoning"),
        ]
        self.call_receipts: list[object] = []

    def reasoning_verified(self, model: str) -> bool:
        return model == "reader-model"

    def complete(self, *_args: object, **_kwargs: object) -> ModelReply:
        return self.replies.pop(0)


def _concern() -> ReviewConcern:
    return ReviewConcern(
        concern_id="c1",
        unit_id="u1",
        level="L2_ENTITY",
        outcome=Outcome.NOVEL,
        channels=(Channel.UNUSUAL,),
        priority_p=0.1,
        source_ids=("idx:st",),
        evidence=(EvidenceRef("src:evt", "src", 10.0),),
    )


def test_toolbox_is_bare_term_bounded_complete_and_receipted() -> None:
    source = FakePivotSource()
    toolbox = ToolBox(
        source,
        sources=[SourceSpec("idx", "st")],
        start=10.0,
        end=20.0,
    )
    results = toolbox.pivot("service-started")
    record = {
        "_time": 11.0,
        "_raw": "host=wkstn42 event=service-started",
        "host": "wkstn42",
        "index": "idx",
        "sourcetype": "st",
        "source": "",
    }
    assert results[0][0] == event_id_for("idx:st", record)
    assert "event=service-started" in results[0][1]
    assert toolbox.receipts[0].complete is True
    assert toolbox.receipts[0].expected == toolbox.receipts[0].fetched == 1
    assert toolbox.receipts[0].shown == 1
    assert '"service-started"' in source.searches[0]


def test_toolbox_fails_closed_on_incomplete_partition() -> None:
    toolbox = ToolBox(
        FakePivotSource(expected=2),
        sources=[SourceSpec("idx", "st")],
        start=10.0,
        end=20.0,
    )
    assert toolbox.pivot("x") == []
    assert toolbox.receipts[0].complete is False
    assert "expected 2, fetched 1" in toolbox.receipts[0].degraded


def test_reader_requires_reasoning_probe_and_returns_unsure_fallback() -> None:
    window = IntakeResult(events={"src:evt": EventView("src:evt", "src", 10.0, "host=wkstn42")})

    class Unprobed(ScriptedClient):
        def reasoning_verified(self, _model: str) -> bool:
            return False

    record = build_judge_fn(Unprobed(), "reader-model")(_concern(), window)
    assert record.verdict.value == "unsure"
    assert "probe missing" in record.degraded
    assert not record.claims


def test_unreachable_reader_returns_degraded_unsure_without_claims() -> None:
    class Unavailable(ScriptedClient):
        def reasoning_verified(self, _model: str) -> bool:
            return True

        def complete(self, *_args: object, **_kwargs: object) -> ModelReply:
            raise TimeoutError("probe transport unavailable")

    window = IntakeResult(events={"src:evt": EventView("src:evt", "src", 10.0, "host=wkstn42")})
    record = build_judge_fn(Unavailable(), "reader-model")(_concern(), window)

    assert record.verdict.value == "unsure"
    assert "reader unavailable: TimeoutError" in record.degraded
    assert not record.claims


def test_reader_attaches_grounding_and_call_receipts() -> None:
    window = IntakeResult(
        events={"src:evt": EventView("src:evt", "src", 10.0, "event=service-started")}
    )
    source = FakePivotSource()
    toolbox = ToolBox(source, sources=[SourceSpec("idx", "st")], start=10.0, end=20.0)
    record = build_judge_fn(
        ScriptedClient(), "reader-model", toolbox_factory=lambda _c, _w: toolbox
    )(_concern(), window)
    assert record.verdict.value == "something"
    assert record.reader_receipt["dropped_claims"] == 0
    assert record.reader_receipt["pivot_calls"] == 0
    assert record.reader_receipt["examined"] == record.reader_receipt["resolved"] == 1
