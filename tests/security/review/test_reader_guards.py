from __future__ import annotations

import pytest

from portal.modules.security.core.review.contracts import (
    Channel,
    EvidenceRef,
    Outcome,
    ReviewConcern,
    Verdict,
)
from portal.modules.security.core.review.intake import EventView, IntakeResult
from portal.modules.security.core.review.judge import ModelReply
from portal.modules.security.core.review.model_client import PortalModelClient
from portal.modules.security.core.review.reader import assert_prompt_label_free, build_judge_fn
from portal.modules.security.core.review.wall import WallViolation


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


class UncalledClient:
    def reasoning_verified(self, _model: str) -> bool:
        return True

    def complete(self, *_args: object, **_kwargs: object) -> ModelReply:
        raise AssertionError("label-leaking prompt reached the model")


def test_prompt_label_guard_catches_seeded_identifier() -> None:
    with pytest.raises(WallViolation, match="label identifier"):
        assert_prompt_label_free("event payload contains attack_id=T1110")


def test_reader_label_guard_rejects_seeded_event_text_before_model_call() -> None:
    window = IntakeResult(events={"src:evt": EventView("src:evt", "src", 10.0, "attack_id=T1110")})
    record = build_judge_fn(UncalledClient(), "reader-model")(_concern(), window)

    assert record.verdict == Verdict.UNSURE
    assert "label guard" in record.degraded


def test_portal_client_rejects_reasoning_suppression_before_transport() -> None:
    calls = 0

    def stream(*_args: object, **_kwargs: object):
        nonlocal calls
        calls += 1
        return {}

    client = PortalModelClient(streamer=stream, api_key="test-key")
    with pytest.raises(ValueError, match="requires reasoning on"):
        client.complete(
            [{"role": "user", "content": "x"}],
            model="general-deep",
            schema=None,
            max_tokens=8,
            think=False,
        )
    assert calls == 0
