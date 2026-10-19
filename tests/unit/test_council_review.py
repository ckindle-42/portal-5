"""Council Review: isolated seats, full-roster quorum, and bounded synthesis."""

from __future__ import annotations

import asyncio
import json

import pytest
from fastapi import HTTPException
from starlette.requests import Request

import portal.platform.inference.router.council as council_mod
from portal.platform.inference.cluster_backends import Backend
from portal.platform.inference.config import CouncilSpec
from portal.platform.inference.router.council import (
    CouncilCompletion,
    CouncilOpinion,
    _message_text,
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


def test_council_response_never_promotes_reasoning_to_the_answer() -> None:
    embedded_vote = '{"recommendation":"SUPPORT","confidence":1.0}'
    assert (
        _message_text(
            {
                "choices": [
                    {
                        "message": {
                            "content": "",
                            "reasoning_content": embedded_vote,
                            "reasoning": embedded_vote,
                        }
                    }
                ]
            }
        )
        == ""
    )
    assert (
        _message_text(
            {
                "choices": [
                    {
                        "message": {
                            "content": '{"recommendation":"REVISE"}',
                            "reasoning_content": embedded_vote,
                        }
                    }
                ]
            }
        )
        == '{"recommendation":"REVISE"}'
    )


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


def test_council_member_sampling_overrides_are_typed() -> None:
    spec = CouncilSpec.model_validate(
        {
            "members": [
                {
                    "id": "one",
                    "label": "One",
                    "model": "m1",
                    "system": "Review.",
                    "temperature": 0.4,
                    "top_p": 0.9,
                    "top_k": 20,
                    "min_p": 0.05,
                    "presence_penalty": 0.3,
                    "repeat_penalty": 1.1,
                },
                {"id": "two", "label": "Two", "model": "m2", "system": "Review."},
            ],
            "synthesizer_model": "m3",
        }
    )
    assert spec.members[0].temperature == 0.4
    assert spec.members[0].top_k == 20
    assert spec.members[0].repeat_penalty == 1.1


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
    decompose_model = (council.get("speed") or {}).get("decompose_model")
    if decompose_model:
        configured.add(decompose_model)
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
    def __init__(self, models: list[str] | None = None, backend_type: str = "ollama") -> None:
        self.backend = Backend(
            id="test-backend",
            type=backend_type,
            url="http://test",
            group="general",
            models=models or ["evidence-model", "challenger-model", "operator-model", "synth"],
        )

    def get_backend_candidates(self, _workspace_id: str) -> list[Backend]:
        return [self.backend]

    def list_healthy_backends(self) -> list[Backend]:
        return [self.backend]


class _CaptureClient:
    def __init__(self, content: str) -> None:
        self.content = content
        self.calls: list[dict] = []

    async def post(self, _url: str, *, json: dict) -> _Response:
        self.calls.append(json)
        return _Response(self.content)


async def _review_payload(
    monkeypatch: pytest.MonkeyPatch,
    *,
    model: str,
    think: bool,
    overrides: dict | None = None,
) -> dict:
    client = _CaptureClient('{"recommendation":"SUPPORT","confidence":0.9}')
    monkeypatch.setattr(council_mod, "_http_client", client)
    member = {
        "id": "reviewer",
        "label": "Reviewer",
        "model": model,
        "system": "Review evidence.",
        "think": think,
        **(overrides or {}),
    }
    opinion, result = await council_mod._call_reviewer(
        member,
        review_material="proposal material",
        workspace_id="auto-council",
        registry=_Registry([model], backend_type="omlx"),
        council={},
    )
    assert opinion.valid
    assert not result.error
    return client.calls[0]


@pytest.mark.asyncio
async def test_reviewer_prompt_contains_the_neutral_recommendation_rubric(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = await _review_payload(monkeypatch, model="evidence-model", think=False)
    system = payload["messages"][0]["content"]
    for definition in (
        (
            "SUPPORT: proceed as proposed. Minor or optional findings (style, nice-to-haves,\n"
            "  follow-ups that do not block) are listed as findings but do not change the\n"
            "  recommendation."
        ),
        "REVISE: use only when at least one finding must be fixed before proceeding. Name it.",
        "REJECT: should not proceed in this form; the premise is wrong, the risk outweighs the benefit,",
        "ABSTAIN: the material is insufficient for your assigned review.",
        "Choose the recommendation that follows from your own highest-severity finding.",
        "A low-severity finding alone never forces REVISE.",
    ):
        assert definition in system


@pytest.mark.asyncio
async def test_reviewer_sampling_uses_the_card_mode_for_think_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model = "hf.co/unsloth/Qwen3.8-27B-GGUF:Q4_K_M-ctx32k"
    thinking = await _review_payload(monkeypatch, model=model, think=True)
    instruct = await _review_payload(monkeypatch, model=model, think=False)

    keys = ("temperature", "top_p", "top_k", "min_p", "presence_penalty", "repeat_penalty")
    assert {key: thinking[key] for key in keys} == {
        "temperature": 1.0,
        "top_p": 0.95,
        "top_k": 20,
        "min_p": 0.0,
        "presence_penalty": 0.0,
        "repeat_penalty": 1.0,
    }
    assert thinking["repetition_penalty"] == 1.0
    assert thinking["chat_template_kwargs"] == {"enable_thinking": True}
    assert {key: instruct[key] for key in keys} == {
        "temperature": 0.7,
        "top_p": 0.8,
        "top_k": 20,
        "min_p": 0.0,
        "presence_penalty": 1.5,
        "repeat_penalty": 1.0,
    }
    assert instruct["chat_template_kwargs"] == {"enable_thinking": False}


@pytest.mark.asyncio
async def test_explicit_member_sampling_overrides_the_card(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = await _review_payload(
        monkeypatch,
        model="hf.co/unsloth/Qwen3.8-27B-GGUF:Q4_K_M-ctx32k",
        think=False,
        overrides={"temperature": 0.42, "top_p": 0.6, "presence_penalty": 0.2},
    )
    assert payload["temperature"] == 0.42
    assert payload["top_p"] == 0.6
    assert payload["presence_penalty"] == 0.2
    assert payload["top_k"] == 20


@pytest.mark.asyncio
async def test_synthesizer_uses_its_card_sampling(monkeypatch: pytest.MonkeyPatch) -> None:
    model = "hf.co/unsloth/Qwen3.8-27B-GGUF:Q4_K_M-ctx32k"
    client = _CaptureClient("## Recommendation\nThe coded result stands.")
    monkeypatch.setattr(council_mod, "_http_client", client)
    opinions = [_opinion("one", "SUPPORT"), _opinion("two", "SUPPORT")]
    aggregate = aggregate_opinions(opinions, minimum_participation=0.66, quorum=0.66)
    await council_mod._synthesize(
        council={"synthesizer_model": model},
        aggregate=aggregate,
        opinions=opinions,
        review_material="proposal material",
        workspace_id="auto-council",
        registry=_Registry([model], backend_type="omlx"),
    )
    payload = client.calls[0]
    assert payload["temperature"] == 0.7
    assert payload["top_p"] == 0.8
    assert payload["presence_penalty"] == 1.5
    assert payload["repeat_penalty"] == 1.0
    assert payload["repetition_penalty"] == 1.0


def test_settings_audit_checks_auto_council_cards_and_served_templates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tests.wfe import settings_audit

    template_checks: list[tuple[str, str]] = []
    stop_checks: list[tuple[str, str]] = []
    monkeypatch.setattr(
        settings_audit,
        "_served_path",
        lambda _workspace, model, _registry: ("ollama", "backend", f"served-{model}"),
    )
    monkeypatch.setattr(
        settings_audit,
        "_audit_template_conformance",
        lambda where, tag, _shows, _tmap, _violations: template_checks.append((where, tag)),
    )
    monkeypatch.setattr(
        settings_audit,
        "_audit_stop_hygiene",
        lambda where, tag, _shows, _violations: stop_checks.append((where, tag)),
    )
    council = {
        "members": [{"id": "reviewer", "model": "uncarded-model"}],
        "synthesizer_model": "known-model",
    }
    context = {
        "registry": {"known-model": {}},
        "reg": object(),
        "shows": {},
        "tmap": {},
    }
    violations: list[dict] = []
    paths = settings_audit._audit_auto_council(council, context, violations)

    assert paths["reviewer"]["served_model"] == "served-uncarded-model"
    assert paths["synthesizer"]["served_model"] == "served-known-model"
    assert template_checks == [
        ("auto-council:reviewer", "served-uncarded-model"),
        ("auto-council:synthesizer", "served-known-model"),
    ]
    assert stop_checks == template_checks
    assert any(
        violation["workspace"] == "auto-council:reviewer"
        and violation["kind"] == "council_card_missing"
        and violation["severity"] == "FAIL"
        for violation in violations
    )


def test_settings_audit_reads_omlx_template_for_the_served_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tests.wfe import settings_audit

    template_reads: list[str] = []
    monkeypatch.setattr(
        settings_audit,
        "_served_path",
        lambda _workspace, model, _registry: ("omlx", "omlx-general", f"served-{model}"),
    )
    monkeypatch.setattr(
        settings_audit,
        "_template_sha_omlx",
        lambda model: (
            template_reads.append(model) or {"tokenizer_config_chat_template": "known-sha"}
        ),
    )
    council = {
        "members": [{"id": "reviewer", "model": "known-model"}],
        "synthesizer_model": "known-model",
    }
    context = {
        "registry": {"known-model": {"known_good_template_sha": "known-sha"}},
        "reg": object(),
        "shows": {},
        "tmap": {},
    }
    violations: list[dict] = []
    paths = settings_audit._audit_auto_council(council, context, violations)

    assert template_reads == ["served-known-model", "served-known-model"]
    assert paths["reviewer"]["template_check"] == "omlx_template_identity"
    assert paths["reviewer"]["stop_check"] == "not_applicable_for_omlx"
    assert violations == []


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


def _chat_request(payload: dict) -> Request:
    raw = json.dumps(payload).encode()
    sent = False

    async def receive() -> dict:
        nonlocal sent
        if sent:
            return {"type": "http.disconnect"}
        sent = True
        return {"type": "http.request", "body": raw, "more_body": False}

    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/v1/chat/completions",
            "query_string": b"",
            "headers": [(b"content-length", str(len(raw)).encode())],
        },
        receive,
    )


@pytest.mark.asyncio
async def test_chat_handler_rejects_an_unknown_council_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import portal.platform.inference.router.handlers as handlers

    class FakeRequestSlot:
        async def acquire_global(self) -> None:
            return None

        async def acquire_api_key(self, _api_key: str) -> None:
            return None

        async def acquire_workspace(self, _workspace_id: str) -> None:
            return None

        def mark_active(self) -> None:
            return None

        def release_if_attached(self) -> None:
            return None

    monkeypatch.setattr(handlers, "_verify_key", lambda _authorization: None)
    monkeypatch.setattr(handlers, "registry", _Registry())
    monkeypatch.setattr(handlers, "RequestSlot", FakeRequestSlot)
    monkeypatch.setattr(
        handlers,
        "run_council_review",
        lambda *_args, **_kwargs: pytest.fail("rejected override must not run"),
    )
    request = _chat_request(
        {
            "model": "auto-council",
            "stream": False,
            "messages": [{"role": "user", "content": "Review this proposal."}],
            "portal_council_config": {"mode": "early_quorum"},
        }
    )
    with pytest.raises(HTTPException) as caught:
        await handlers.chat_completions(request, authorization="Bearer test")
    assert caught.value.status_code == 400
    assert "unknown keys: mode" in str(caught.value.detail)
