"""Council Review: isolated seats, full-roster quorum, and bounded synthesis."""

from __future__ import annotations

import asyncio
import json

import pytest
from starlette.requests import Request

import portal.platform.inference.router.council as council_mod
from portal.platform.inference.cluster_backends import Backend
from portal.platform.inference.config import CouncilSpec
from portal.platform.inference.router.council import (
    CouncilCompletion,
    CouncilOpinion,
    aggregate_opinions,
    parse_opinion,
    run_council_review,
    stream_council_review,
)
from portal.platform.inference.router.workspaces import WORKSPACES


def _opinion(member_id: str, recommendation: str, *, valid: bool = True) -> CouncilOpinion:
    return CouncilOpinion(
        member_id=member_id,
        label=member_id,
        model=f"model-{member_id}",
        recommendation=recommendation,
        confidence=0.8,
        valid=valid,
    )


def test_parse_opinion_accepts_fenced_json() -> None:
    member = {"id": "evidence", "label": "Evidence", "model": "m1"}
    text = """```json
{"recommendation":"REVISE","confidence":0.9,"findings":[{"claim":"Missing test",
"evidence":["proposal says tests are TBD"],"action":"Add the test"}]}
```"""
    result = parse_opinion(member, text)
    assert result.valid is True
    assert result.recommendation == "REVISE"
    assert result.confidence == 0.9
    assert result.findings[0]["claim"] == "Missing test"


def test_invalid_output_abstains_without_becoming_a_vote() -> None:
    member = {"id": "challenger", "label": "Challenger", "model": "m2"}
    result = parse_opinion(member, "I think this looks good.")
    assert result.valid is False
    assert result.participated is False
    assert result.recommendation == "ABSTAIN"
    assert result.error


def test_quorum_uses_full_roster_not_only_participants() -> None:
    opinions = [
        _opinion("one", "SUPPORT"),
        _opinion("two", "ABSTAIN"),
        _opinion("three", "ABSTAIN", valid=False),
    ]
    result = aggregate_opinions(opinions, minimum_participation=0.33, quorum=0.66)
    assert result.decision == "ESCALATE"
    assert result.required_votes == 2
    assert result.votes["SUPPORT"] == 1


def test_two_of_three_reaches_configured_quorum_and_preserves_dissent() -> None:
    opinions = [
        _opinion("evidence", "REVISE"),
        _opinion("challenger", "REVISE"),
        _opinion("operator", "SUPPORT"),
    ]
    result = aggregate_opinions(opinions, minimum_participation=0.66, quorum=0.66)
    assert result.decision == "REVISE"
    assert result.participating == 3
    assert result.required_votes == 2
    assert result.dissent == ["operator"]


def test_low_participation_escalates_even_when_remaining_reviewers_agree() -> None:
    opinions = [
        _opinion("evidence", "SUPPORT"),
        _opinion("challenger", "SUPPORT"),
        _opinion("operator", "ABSTAIN", valid=False),
    ]
    result = aggregate_opinions(opinions, minimum_participation=0.67, quorum=0.66)
    assert result.decision == "ESCALATE"
    assert "participation" in result.rationale


def test_council_schema_rejects_duplicate_evidence_ids() -> None:
    with pytest.raises(ValueError, match="unique"):
        CouncilSpec.model_validate(
            {
                "members": [
                    {"id": "same", "label": "A", "model": "m1", "system": "a"},
                    {"id": "same", "label": "B", "model": "m2", "system": "b"},
                ],
                "synthesizer_model": "m3",
            }
        )


def test_production_workspace_is_explicit_and_tool_free() -> None:
    workspace = WORKSPACES["auto-council"]
    assert workspace["tools"] == []
    assert len(workspace["council"]["members"]) == 3
    assert workspace["council"]["synthesizer_model"] == workspace["model_hint"]


def test_every_configured_council_model_is_reachable() -> None:
    import yaml

    raw = yaml.safe_load(open("config/backends.yaml"))
    catalog = {
        entry["id"] if isinstance(entry, dict) else entry
        for backend in raw["backends"]
        for entry in backend.get("models", [])
    }
    council = WORKSPACES["auto-council"]["council"]
    configured = {member["model"] for member in council["members"]}
    configured.add(council["synthesizer_model"])
    assert configured <= catalog


class _Response:
    def __init__(self, content: str) -> None:
        self._content = content

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return {"choices": [{"message": {"content": self._content}}]}


class _Client:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def post(self, _url: str, *, json: dict) -> _Response:
        self.calls.append(json)
        model = json["model"]
        if model == "synth":
            return _Response(
                "## Recommendation\nREVISE\n\n"
                "## Evidence and findings\nEvidence reviewer found a gap.\n\n"
                "## Strongest objection\nOperator dissented.\n\n"
                "## Missing evidence\nTests.\n\n"
                "## Conditions that would change the recommendation\nPassing tests.\n\n"
                "## Next actions\nAdd tests."
            )
        recommendation = {
            "evidence-model": "REVISE",
            "challenger-model": "REVISE",
            "operator-model": "SUPPORT",
        }[model]
        return _Response(
            json_module(
                {
                    "recommendation": recommendation,
                    "confidence": 0.8,
                    "findings": [
                        {
                            "claim": f"{model} finding",
                            "severity": "medium",
                            "evidence": ["The proposal says tests are pending"],
                            "action": "Add tests",
                        }
                    ],
                    "missing_evidence": ["test result"],
                    "strongest_objection": "The change may be unnecessary",
                    "conditions_to_change": ["Show a passing test"],
                }
            )
        )


def json_module(value: dict) -> str:
    """Keep the fake client's ``json`` argument name from shadowing the module."""
    return json.dumps(value)


class _Registry:
    def __init__(self) -> None:
        self.backend = Backend(
            id="test-backend",
            type="ollama",
            url="http://test",
            group="general",
            models=["evidence-model", "challenger-model", "operator-model", "synth"],
        )

    def get_backend_candidates(self, _workspace_id: str) -> list[Backend]:
        return [self.backend]

    def list_healthy_backends(self) -> list[Backend]:
        return [self.backend]


class _Slot:
    def __init__(self) -> None:
        self.releases = 0

    def release(self) -> None:
        self.releases += 1


@pytest.mark.asyncio
async def test_runtime_isolates_reviewers_then_synthesizes_code_decision(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _Client()
    monkeypatch.setattr(council_mod, "_http_client", client)
    council = {
        "members": [
            {
                "id": "evidence",
                "label": "Evidence",
                "model": "evidence-model",
                "system": "Audit evidence.",
            },
            {
                "id": "challenger",
                "label": "Challenger",
                "model": "challenger-model",
                "system": "Challenge assumptions.",
            },
            {
                "id": "operator",
                "label": "Operator",
                "model": "operator-model",
                "system": "Check operations.",
            },
        ],
        "synthesizer_model": "synth",
        "minimum_participation": 0.66,
        "quorum": 0.66,
        "reviewer_max_tokens": 1024,
        "synthesizer_max_tokens": 1024,
    }
    completion = await run_council_review(
        {
            "messages": [
                {
                    "role": "user",
                    "content": "Review this proposal. The proposal says tests are pending.",
                }
            ]
        },
        council,
        registry=_Registry(),
        workspace_id="auto-council",
    )

    aggregate = completion.data["portal_council"]["aggregate"]
    assert aggregate["decision"] == "REVISE"
    assert aggregate["votes"] == {"SUPPORT": 1, "REVISE": 2, "REJECT": 0}
    assert aggregate["dissent"] == ["operator"]
    content = completion.data["choices"][0]["message"]["content"]
    assert content.startswith("**Code-determined decision: REVISE**")

    reviewer_calls = client.calls[:3]
    assert {call["model"] for call in reviewer_calls} == {
        "evidence-model",
        "challenger-model",
        "operator-model",
    }
    # Reviewers receive only the original review material, never sibling output.
    assert all("evidence-model finding" not in str(call["messages"]) for call in reviewer_calls)
    assert client.calls[3]["model"] == "synth"


@pytest.mark.asyncio
async def test_stream_releases_slot_after_done(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _Client()
    monkeypatch.setattr(council_mod, "_http_client", client)
    config = {
        "members": [
            {"id": "evidence", "label": "Evidence", "model": "evidence-model", "system": "a"},
            {
                "id": "challenger",
                "label": "Challenger",
                "model": "challenger-model",
                "system": "b",
            },
            {"id": "operator", "label": "Operator", "model": "operator-model", "system": "c"},
        ],
        "synthesizer_model": "synth",
        "minimum_participation": 0.66,
        "quorum": 0.66,
    }
    slot = _Slot()
    chunks = [
        chunk
        async for chunk in stream_council_review(
            {"messages": [{"role": "user", "content": "Review this."}]},
            config,
            slot,
            registry=_Registry(),
            workspace_id="auto-council",
        )
    ]
    assert chunks[-1] == b"data: [DONE]\n\n"
    assert slot.releases == 1


@pytest.mark.asyncio
async def test_stream_emits_invisible_heartbeats_during_long_review(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def slow_review(body, council, *, registry, workspace_id):
        await asyncio.sleep(0.03)
        return CouncilCompletion(
            data={
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": "**Code-determined decision: SUPPORT**",
                        }
                    }
                ]
            },
            backend_id="test-backend",
            model="synth",
        )

    monkeypatch.setattr(council_mod, "run_council_review", slow_review)
    monkeypatch.setattr(council_mod, "_STREAM_HEARTBEAT_S", 0.005)
    slot = _Slot()

    chunks = [
        chunk
        async for chunk in stream_council_review(
            {"messages": [{"role": "user", "content": "Review this."}]},
            {},
            slot,
            registry=_Registry(),
            workspace_id="auto-council",
        )
    ]

    assert any(chunk == b": portal-council keep-alive\n\n" for chunk in chunks)
    assert chunks[-1] == b"data: [DONE]\n\n"
    assert slot.releases == 1


@pytest.mark.asyncio
async def test_chat_handler_short_circuits_primary_model_for_council(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import portal.platform.inference.router.handlers as handlers

    payload = json.dumps(
        {
            "model": "auto-council",
            "stream": False,
            "messages": [{"role": "user", "content": "Review this proposal."}],
        }
    ).encode()
    sent = False

    async def receive() -> dict:
        nonlocal sent
        if sent:
            return {"type": "http.disconnect"}
        sent = True
        return {"type": "http.request", "body": payload, "more_body": False}

    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/v1/chat/completions",
            "query_string": b"",
            "headers": [(b"content-length", str(len(payload)).encode())],
        },
        receive,
    )
    calls: list[str] = []

    async def fake_run(body, config, *, registry, workspace_id):
        calls.append(workspace_id)
        return CouncilCompletion(
            data={
                "model": workspace_id,
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": "**Code-determined decision: REVISE**",
                        }
                    }
                ],
            },
            backend_id="test-backend",
            model=config["synthesizer_model"],
        )

    class FakeRequestSlot:
        async def acquire_global(self) -> None:
            return None

        async def acquire_api_key(self, _api_key: str) -> None:
            return None

        async def acquire_workspace(self, _workspace_id: str) -> None:
            return None

        def mark_active(self) -> None:
            return None

        def detach(self):
            return self

        def release_if_attached(self) -> None:
            return None

    registry = _Registry()
    monkeypatch.setattr(handlers, "_verify_key", lambda _authorization: None)
    monkeypatch.setattr(handlers, "registry", registry)
    monkeypatch.setattr(handlers, "RequestSlot", FakeRequestSlot)
    monkeypatch.setattr(handlers, "run_council_review", fake_run)
    # If the ordinary single-model path is reached, the test must fail.
    monkeypatch.setattr(
        handlers,
        "_try_non_streaming",
        lambda *_args, **_kwargs: pytest.fail("primary model path should be bypassed"),
    )

    response = await handlers.chat_completions(request, authorization="Bearer test")
    assert response.status_code == 200
    assert calls == ["auto-council"]
    assert json.loads(response.body)["choices"][0]["message"]["content"].endswith("REVISE**")
