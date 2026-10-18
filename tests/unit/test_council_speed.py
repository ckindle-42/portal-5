"""Council speed modes: timings, early quorum, one resident model, progress, decompose."""

from __future__ import annotations

import json

import pytest

import portal.platform.inference.router.council as council_mod
from portal.platform.inference.cluster_backends import Backend
from portal.platform.inference.router.council import (
    CouncilOpinion,
    claim_disposition,
    decision_from_settled,
    run_council_review,
    stream_council_review,
    votes_decide_outcome,
)
from portal.platform.inference.router.trace import _current as _trace_current
from portal.platform.inference.router.trace import start_trace
from portal.platform.inference.router.workspaces import WORKSPACES


def _opinion(member_id: str, recommendation: str, *, valid: bool = True) -> CouncilOpinion:
    return CouncilOpinion(
        member_id=member_id,
        label=member_id,
        model=f"model-{member_id}",
        recommendation=recommendation if valid else "ABSTAIN",
        confidence=0.8,
        valid=valid,
    )


def test_two_agreeing_votes_lock_the_coded_decision() -> None:
    opinions = [_opinion("evidence", "SUPPORT"), _opinion("challenger", "SUPPORT")]
    assert (
        votes_decide_outcome(opinions, remaining=1, minimum_participation=0.66, quorum=0.66)
        == "SUPPORT"
    )


def test_a_split_does_not_lock_before_the_last_seat() -> None:
    opinions = [_opinion("evidence", "SUPPORT"), _opinion("challenger", "REVISE")]
    assert (
        votes_decide_outcome(opinions, remaining=1, minimum_participation=0.66, quorum=0.66) is None
    )


def test_one_vote_does_not_lock_when_the_tail_can_outvote_it() -> None:
    opinions = [_opinion("evidence", "SUPPORT")]
    assert (
        votes_decide_outcome(opinions, remaining=2, minimum_participation=0.3, quorum=0.3) is None
    )


def test_participation_floor_keeps_the_last_seat() -> None:
    opinions = [_opinion("evidence", "SUPPORT"), _opinion("challenger", "SUPPORT")]
    assert (
        votes_decide_outcome(opinions, remaining=1, minimum_participation=1.0, quorum=0.66) is None
    )


def test_two_non_votes_lock_escalate() -> None:
    opinions = [
        _opinion("evidence", "SUPPORT", valid=False),
        _opinion("challenger", "SUPPORT", valid=False),
    ]
    assert (
        votes_decide_outcome(opinions, remaining=1, minimum_participation=0.66, quorum=0.66)
        == "ESCALATE"
    )


def test_claim_rules_settle_or_escalate() -> None:
    assert (
        claim_disposition({"evidence_present": "yes", "contradicted": "no", "stale": "no"})
        == "supported"
    )
    assert (
        claim_disposition({"evidence_present": "yes", "contradicted": "no", "stale": "yes"})
        == "stale"
    )
    assert (
        claim_disposition({"evidence_present": "no", "contradicted": "no", "stale": "no"})
        == "missing"
    )
    assert (
        claim_disposition({"evidence_present": "unsure", "contradicted": "no", "stale": "no"})
        == "escalate"
    )
    assert (
        claim_disposition({"evidence_present": "yes", "contradicted": "yes", "stale": "no"})
        == "escalate"
    )
    assert decision_from_settled(["supported", "supported"]) == "SUPPORT"
    assert decision_from_settled(["supported", "stale"]) == "REVISE"
    assert decision_from_settled(["contradicted"]) == "REJECT"
    assert decision_from_settled(["contradicted", "supported"]) == "REVISE"


def _vote(recommendation: str) -> str:
    return json.dumps(
        {
            "recommendation": recommendation,
            "confidence": 0.8,
            "findings": [
                {
                    "claim": f"{recommendation} finding",
                    "severity": "medium",
                    "evidence": ["the proposal"],
                    "action": "check it",
                }
            ],
            "missing_evidence": [],
            "strongest_objection": "maybe not",
            "conditions_to_change": [],
        }
    )


_SYNTH = (
    "## Recommendation\nSUPPORT\n\n## Evidence and findings\nNoted.\n\n"
    "## Strongest objection\nNone.\n\n## Missing evidence\nNone.\n\n"
    "## Conditions that would change the recommendation\nNone.\n\n"
    "## Next actions\nShip."
)

_PROFILE = {
    "evidence-model": (1.0, 2.0, 0.5, 11),
    "challenger-model": (3.0, 4.0, 0.5, 13),
    "operator-model": (5.0, 6.0, 0.5, 17),
    "synth": (7.0, 8.0, 0.5, 19),
    "resident-model": (1.5, 2.5, 0.5, 12),
    "decompose-model": (0.25, 0.5, 0.25, 8),
}


class _Response:
    def __init__(self, content: str, model: str) -> None:
        load_s, prefill_s, decode_s, tokens = _PROFILE[model]
        self._body = {
            "choices": [{"message": {"content": content}}],
            "load_duration": int(load_s * 1_000_000_000),
            "prompt_eval_duration": int(prefill_s * 1_000_000_000),
            "eval_duration": int(decode_s * 1_000_000_000),
            "eval_count": tokens,
        }

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._body


class _Engine:
    def __init__(self, answers: dict[str, str]) -> None:
        self.answers = answers
        self.calls: list[dict] = []

    async def post(self, _url: str, *, json: dict) -> _Response:
        self.calls.append(json)
        model = json["model"]
        return _Response(self.answers[model], model)


class _Registry:
    def __init__(self, models: list[str] | None = None) -> None:
        self.backend = Backend(
            id="test-backend",
            type="ollama",
            url="http://test",
            group="general",
            models=models
            or [
                "evidence-model",
                "challenger-model",
                "operator-model",
                "synth",
                "resident-model",
                "decompose-model",
            ],
        )

    def get_backend_candidates(self, _workspace_id: str) -> list[Backend]:
        return [self.backend]

    def list_healthy_backends(self) -> list[Backend]:
        return [self.backend]


def _members() -> list[dict]:
    return [
        {"id": "evidence", "label": "Evidence", "model": "evidence-model", "system": "Audit."},
        {
            "id": "challenger",
            "label": "Challenger",
            "model": "challenger-model",
            "system": "Challenge.",
        },
        {"id": "operator", "label": "Operator", "model": "operator-model", "system": "Operate."},
    ]


def _council(**overrides: object) -> dict:
    council = {
        "members": _members(),
        "synthesizer_model": "synth",
        "minimum_participation": 0.66,
        "quorum": 0.66,
        "reviewer_max_tokens": 8192,
        "synthesizer_max_tokens": 1024,
    }
    council.update(overrides)
    return council


def _body(text: str = "UNIQUE_ORIGINAL_SENTENCE about the proposal.") -> dict:
    return {"messages": [{"role": "user", "content": text}]}


def _reviewer_calls(engine: _Engine) -> list[dict]:
    return [call for call in engine.calls if call["model"] != "synth"]


async def _run(council: dict, text: str | None = None):
    return await run_council_review(
        _body() if text is None else _body(text),
        council,
        registry=_Registry(),
        workspace_id="auto-council",
    )


def _stage(completion, name: str) -> dict:
    stages = completion.data["portal_council"]["timings"]["stages"]
    return next(stage for stage in stages if stage["stage"] == name)


@pytest.mark.asyncio
async def test_every_run_records_engine_timings_in_the_result_and_the_trace(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = _Engine(
        {
            "evidence-model": _vote("REVISE"),
            "challenger-model": _vote("REVISE"),
            "operator-model": _vote("SUPPORT"),
            "synth": _SYNTH,
        }
    )
    monkeypatch.setattr(council_mod, "_http_client", engine)
    trace = start_trace("council-speed-timing")
    assert trace is not None
    try:
        completion = await _run(_council())
    finally:
        _trace_current.set(None)

    timings = completion.data["portal_council"]["timings"]
    assert timings["wall_s"] >= 0
    assert timings["speed"]["early_quorum"] is False
    evidence = _stage(completion, "evidence")
    assert evidence["model"] == "evidence-model"
    assert evidence["skipped"] is False
    assert evidence["called"] is True
    assert evidence["cold_load_s"] == 1.0
    assert evidence["prefill_s"] == 2.0
    assert evidence["decode_s"] == 0.5
    assert evidence["tokens"] == 11
    assert evidence["portal_timings"]["timing_source"] == "engine"
    synth = _stage(completion, "synthesizer")
    assert synth["kind"] == "synthesizer"
    assert synth["model"] == "synth"
    assert synth["cold_load_s"] == 7.0
    assert synth["prefill_s"] == 8.0
    assert synth["tokens"] == 19
    recorded = trace.to_dict()
    assert recorded["portal_council_timings"]["stages"][0]["stage"] == "evidence"
    assert any(span["name"] == "council.stage" for span in recorded["spans"])
    assert {call["model"] for call in engine.calls[:3]} == {
        "evidence-model",
        "challenger-model",
        "operator-model",
    }


@pytest.mark.asyncio
async def test_early_quorum_skips_the_tail_when_two_of_three_agree(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = _Engine(
        {
            "evidence-model": _vote("SUPPORT"),
            "challenger-model": _vote("SUPPORT"),
            "operator-model": _vote("REJECT"),
            "synth": _SYNTH,
        }
    )
    monkeypatch.setattr(council_mod, "_http_client", engine)
    completion = await _run(_council(speed={"early_quorum": True}))

    assert [call["model"] for call in _reviewer_calls(engine)] == [
        "evidence-model",
        "challenger-model",
    ]
    aggregate = completion.data["portal_council"]["aggregate"]
    assert aggregate["decision"] == "SUPPORT"
    assert aggregate["votes"] == {"SUPPORT": 2, "REVISE": 0, "REJECT": 0}
    assert aggregate["participating"] == 2
    assert aggregate["roster"] == 3
    operator = next(
        row
        for row in completion.data["portal_council"]["reviewers"]
        if row["member_id"] == "operator"
    )
    assert operator["skipped"] is True
    assert operator["skip_reason"] == "early_quorum"
    assert operator["valid"] is False
    skipped = _stage(completion, "operator")
    assert skipped["skipped"] is True
    assert skipped["called"] is False
    assert skipped["cold_load_s"] is None
    assert skipped["tokens"] is None


@pytest.mark.asyncio
async def test_early_quorum_runs_the_third_seat_on_a_split(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = _Engine(
        {
            "evidence-model": _vote("SUPPORT"),
            "challenger-model": _vote("REVISE"),
            "operator-model": _vote("REJECT"),
            "synth": _SYNTH,
        }
    )
    monkeypatch.setattr(council_mod, "_http_client", engine)
    completion = await _run(_council(speed={"early_quorum": True}))
    assert [call["model"] for call in _reviewer_calls(engine)] == [
        "evidence-model",
        "challenger-model",
        "operator-model",
    ]
    assert completion.data["portal_council"]["aggregate"]["decision"] == "ESCALATE"


@pytest.mark.asyncio
async def test_early_quorum_runs_the_third_seat_when_participation_requires_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = _Engine(
        {
            "evidence-model": _vote("SUPPORT"),
            "challenger-model": _vote("SUPPORT"),
            "operator-model": _vote("SUPPORT"),
            "synth": _SYNTH,
        }
    )
    monkeypatch.setattr(council_mod, "_http_client", engine)
    await _run(_council(speed={"early_quorum": True}, minimum_participation=1.0, quorum=0.66))
    assert len(_reviewer_calls(engine)) == 3


@pytest.mark.asyncio
async def test_early_quorum_skips_when_escalate_is_already_certain(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = _Engine(
        {
            "evidence-model": "not json",
            "challenger-model": "also not json",
            "operator-model": _vote("SUPPORT"),
            "synth": _SYNTH,
        }
    )
    monkeypatch.setattr(council_mod, "_http_client", engine)
    completion = await _run(_council(speed={"early_quorum": True}))
    assert [call["model"] for call in _reviewer_calls(engine)] == [
        "evidence-model",
        "challenger-model",
    ]
    aggregate = completion.data["portal_council"]["aggregate"]
    assert aggregate["decision"] == "ESCALATE"
    assert aggregate["votes"] == {"SUPPORT": 0, "REVISE": 0, "REJECT": 0}
    assert _stage(completion, "operator")["skipped"] is True


@pytest.mark.asyncio
async def test_early_quorum_does_not_skip_after_a_single_low_quorum_vote(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = _Engine(
        {
            "evidence-model": _vote("SUPPORT"),
            "challenger-model": _vote("REVISE"),
            "operator-model": _vote("REVISE"),
            "synth": _SYNTH,
        }
    )
    monkeypatch.setattr(council_mod, "_http_client", engine)
    await _run(_council(speed={"early_quorum": True}, quorum=0.3, minimum_participation=0.3))
    assert len(_reviewer_calls(engine)) == 3


@pytest.mark.asyncio
async def test_single_model_keeps_roles_and_isolation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The synthesizer answer is markdown, but the same model also reviews.
    # Key the script by the system prompt instead.
    calls: list[dict] = []

    class _Switch:
        async def post(self, _url: str, *, json: dict) -> _Response:
            calls.append(json)
            system = json["messages"][0]["content"]
            if "synthesizer" in system or system.startswith("You are Portal"):
                return _Response(_SYNTH, "synth")
            return _Response(_vote("REVISE"), "synth")

    monkeypatch.setattr(council_mod, "_http_client", _Switch())
    completion = await _run(_council(speed={"single_model": True}))
    reviewer_calls = calls[:3]
    assert {call["model"] for call in reviewer_calls} == {"synth"}
    systems = [call["messages"][0]["content"] for call in reviewer_calls]
    assert len(set(systems)) == 3
    users = [call["messages"][1]["content"] for call in reviewer_calls]
    assert len(set(users)) == 1
    assert all("REVISE finding" not in user for user in users)
    assert calls[3]["model"] == "synth"
    assert completion.data["portal_council"]["timings"]["speed"]["resident_model"] == "synth"
    assert completion.data["portal_council"]["aggregate"]["votes"]["REVISE"] == 3

    override_calls: list[dict] = []

    class _Override:
        async def post(self, _url: str, *, json: dict) -> _Response:
            override_calls.append(json)
            if json["model"] == "synth":
                return _Response(_SYNTH, "synth")
            return _Response(_vote("SUPPORT"), "resident-model")

    monkeypatch.setattr(council_mod, "_http_client", _Override())
    await _run(_council(speed={"single_model": True, "resident_model": "resident-model"}))
    assert {call["model"] for call in override_calls if call["model"] != "synth"} == {
        "resident-model"
    }


@pytest.mark.asyncio
async def test_progress_streams_each_verdict_before_synthesis(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = _Engine(
        {
            "evidence-model": _vote("REVISE"),
            "challenger-model": _vote("SUPPORT"),
            "operator-model": _vote("SUPPORT"),
            "synth": _SYNTH,
        }
    )
    monkeypatch.setattr(council_mod, "_http_client", engine)

    class _Slot:
        def __init__(self) -> None:
            self.releases = 0

        def release(self) -> None:
            self.releases += 1

    slot = _Slot()
    chunks = [
        chunk
        async for chunk in stream_council_review(
            _body(),
            _council(speed={"progress": True}),
            slot,
            registry=_Registry(),
            workspace_id="auto-council",
        )
    ]
    text = ""
    saw_meta = False
    for chunk in chunks:
        if not chunk.startswith(b"data: {"):
            continue
        payload = json.loads(chunk[6:])
        if payload.get("portal_council"):
            saw_meta = True
            assert payload["portal_council"]["timings"]["stages"]
        delta = (payload.get("choices") or [{}])[0].get("delta") or {}
        text += delta.get("content") or ""
    assert text.index("**Evidence:** REVISE (confidence 0.80).") < text.index(
        "**Code-determined decision:"
    )
    assert "**Challenger:** SUPPORT (confidence 0.80)." in text
    assert "**Operator:** SUPPORT (confidence 0.80)." in text
    assert saw_meta is True
    assert slot.releases == 1
    assert chunks[-1] == b"data: [DONE]\n\n"


@pytest.mark.asyncio
async def test_progress_off_does_not_emit_verdict_lines(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = _Engine(
        {
            "evidence-model": _vote("REVISE"),
            "challenger-model": _vote("REVISE"),
            "operator-model": _vote("REVISE"),
            "synth": _SYNTH,
        }
    )
    monkeypatch.setattr(council_mod, "_http_client", engine)

    class _Slot:
        def release(self) -> None:
            return None

    chunks = [
        chunk
        async for chunk in stream_council_review(
            _body(),
            _council(),
            _Slot(),
            registry=_Registry(),
            workspace_id="auto-council",
        )
    ]
    text = b"".join(chunks).decode()
    assert "(confidence" not in text
    assert "**Code-determined decision:" in text


def _claims(*rows: dict) -> str:
    return json.dumps({"claims": rows})


@pytest.mark.asyncio
async def test_decompose_settles_every_claim_without_a_big_model_vote(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = _Engine(
        {
            "decompose-model": _claims(
                {
                    "claim": "SETTLED_CACHE_BOUND",
                    "evidence_present": "yes",
                    "contradicted": "no",
                    "stale": "no",
                    "evidence": "the proposal says the cache is bounded",
                }
            ),
            "synth": _SYNTH,
        }
    )
    monkeypatch.setattr(council_mod, "_http_client", engine)
    completion = await _run(
        _council(speed={"decompose": True, "decompose_model": "decompose-model"}),
    )
    assert [call["model"] for call in engine.calls] == ["decompose-model", "synth"]
    aggregate = completion.data["portal_council"]["aggregate"]
    assert aggregate["decision"] == "SUPPORT"
    assert aggregate["decision_source"] == "decompose"
    assert aggregate["votes"] == {"SUPPORT": 0, "REVISE": 0, "REJECT": 0}
    assert all(row["skipped"] for row in completion.data["portal_council"]["reviewers"])
    decompose = _stage(completion, "decompose")
    assert decompose["cold_load_s"] == 0.25
    assert decompose["tokens"] == 8
    assert _stage(completion, "evidence")["skip_reason"] == "decompose_settled"


@pytest.mark.asyncio
async def test_decompose_sends_only_unsettled_claims_to_the_big_seats(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = _Engine(
        {
            "decompose-model": _claims(
                {
                    "claim": "SETTLED_CACHE_BOUND",
                    "evidence_present": "yes",
                    "contradicted": "no",
                    "stale": "yes",
                    "evidence": "quote",
                },
                {
                    "claim": "UNSURE_MIGRATION_RISK",
                    "evidence_present": "unsure",
                    "contradicted": "no",
                    "stale": "no",
                    "evidence": "",
                },
            ),
            "evidence-model": _vote("SUPPORT"),
            "challenger-model": _vote("SUPPORT"),
            "operator-model": _vote("SUPPORT"),
            "synth": _SYNTH,
        }
    )
    monkeypatch.setattr(council_mod, "_http_client", engine)
    completion = await _run(
        _council(speed={"decompose": True, "decompose_model": "decompose-model"}),
    )
    reviewer_users = [
        call["messages"][1]["content"]
        for call in engine.calls
        if call["model"] in {"evidence-model", "challenger-model", "operator-model"}
    ]
    assert reviewer_users
    assert all("UNSURE_MIGRATION_RISK" in user for user in reviewer_users)
    assert all("SETTLED_CACHE_BOUND" not in user for user in reviewer_users)
    assert all("UNIQUE_ORIGINAL_SENTENCE" not in user for user in reviewer_users)
    aggregate = completion.data["portal_council"]["aggregate"]
    # Settled stale claim tightens a unanimous SUPPORT.
    assert aggregate["decision"] == "REVISE"
    assert aggregate["decision_source"] == "decompose+quorum"
    assert aggregate["votes"]["SUPPORT"] == 3
    packet = engine.calls[-1]["messages"][1]["content"]
    assert "SETTLED_CACHE_BOUND" in packet
    assert "UNIQUE_ORIGINAL_SENTENCE" in packet


@pytest.mark.asyncio
async def test_decompose_disagreement_is_escalated_and_garbage_falls_back(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    disagree = _Engine(
        {
            "decompose-model": _claims(
                {
                    "claim": "SETTLED_OK",
                    "evidence_present": "yes",
                    "contradicted": "no",
                    "stale": "no",
                    "evidence": "q",
                },
                {
                    "claim": "DISAGREE_BOTH",
                    "evidence_present": "yes",
                    "contradicted": "yes",
                    "stale": "no",
                    "evidence": "q2",
                },
            ),
            "evidence-model": _vote("REVISE"),
            "challenger-model": _vote("REVISE"),
            "operator-model": _vote("REVISE"),
            "synth": _SYNTH,
        }
    )
    monkeypatch.setattr(council_mod, "_http_client", disagree)
    await _run(_council(speed={"decompose": True, "decompose_model": "decompose-model"}))
    users = [
        call["messages"][1]["content"]
        for call in disagree.calls
        if call["model"] == "evidence-model"
    ]
    assert "DISAGREE_BOTH" in users[0]
    assert "SETTLED_OK" not in users[0]
    assert "UNIQUE_ORIGINAL_SENTENCE" not in users[0]

    garbage = _Engine(
        {
            "decompose-model": "not a sheet",
            "evidence-model": _vote("SUPPORT"),
            "challenger-model": _vote("SUPPORT"),
            "operator-model": _vote("SUPPORT"),
            "synth": _SYNTH,
        }
    )
    monkeypatch.setattr(council_mod, "_http_client", garbage)
    completion = await _run(
        _council(speed={"decompose": True, "decompose_model": "decompose-model"}),
    )
    evidence_user = next(
        call["messages"][1]["content"]
        for call in garbage.calls
        if call["model"] == "evidence-model"
    )
    assert "UNIQUE_ORIGINAL_SENTENCE" in evidence_user
    assert completion.data["portal_council"]["aggregate"]["decision"] == "SUPPORT"
    assert completion.data["portal_council"]["aggregate"]["decision_source"] == "quorum"


@pytest.mark.asyncio
async def test_per_seat_output_and_thinking_budgets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = _Engine(
        {
            "evidence-model": _vote("SUPPORT"),
            "challenger-model": _vote("SUPPORT"),
            "operator-model": _vote("SUPPORT"),
            "synth": _SYNTH,
        }
    )
    monkeypatch.setattr(council_mod, "_http_client", engine)
    members = _members()
    members[0]["max_tokens"] = 200
    members[0]["reasoning_max_tokens"] = 80
    members[0]["think"] = False
    members[2]["max_tokens"] = 256
    members[2]["reasoning_max_tokens"] = 128
    members[2]["think"] = True
    await _run(_council(members=members))
    by_model = {call["model"]: call for call in engine.calls}
    assert by_model["evidence-model"]["max_tokens"] == 200
    assert by_model["evidence-model"]["think"] is False
    assert by_model["challenger-model"]["max_tokens"] == 8192
    assert by_model["challenger-model"]["think"] is False
    assert by_model["operator-model"]["max_tokens"] == 384
    assert by_model["operator-model"]["think"] is True


def test_production_speed_defaults_match_today_and_short_seats() -> None:
    council = WORKSPACES["auto-council"]["council"]
    speed = council["speed"]
    assert speed["early_quorum"] is False
    assert speed["single_model"] is False
    assert speed["progress"] is False
    assert speed["decompose"] is False
    assert speed["decompose_model"] == "granite4.1:8b-ctx16k"
    assert "resident_model" not in speed
    by_id = {member["id"]: member for member in council["members"]}
    assert by_id["evidence"]["max_tokens"] == 1024
    assert by_id["evidence"]["think"] is False
    assert by_id["challenger"]["max_tokens"] == 1024
    assert by_id["challenger"]["think"] is False
    assert "max_tokens" not in by_id["operator"]
    assert council["reviewer_max_tokens"] == 8192
