"""Regression tests for deterministic auto-routing handoffs."""

from __future__ import annotations

import pytest

from portal.platform.inference.router import preinject


@pytest.mark.asyncio
async def test_tls_firewall_routes_to_daily_with_security_handoff_note() -> None:
    messages = [
        {
            "role": "user",
            "content": (
                "An NGINX ingress began failing TLS handshakes from one internal subnet after "
                "a firewall change. Separate likely network, certificate, and application causes; "
                "give read-only checks before suggesting a change."
            ),
        }
    ]

    assert await preinject._resolve_auto_routing("auto", messages) == "auto-daily"
    assert any(
        message.get("role") == "system"
        and "Do not answer the security request" in message.get("content", "")
        and "auto-security" in message.get("content", "")
        for message in messages
    )


@pytest.mark.asyncio
async def test_kubernetes_rbac_routes_to_coding_even_if_layer_one_misclassifies(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def classify_as_daily(_messages: list[dict[str, str]]) -> str:
        return "auto-daily"

    monkeypatch.setattr(preinject, "_route_with_llm", classify_as_daily)
    messages = [
        {
            "role": "user",
            "content": (
                "We run Kubernetes 1.30 and need read-only access to pods in namespace staging. "
                "Propose the least-privilege Role and RoleBinding, explain the scope choice, "
                "and give a safe way to verify it."
            ),
        }
    ]

    assert await preinject._resolve_auto_routing("auto", messages) == "auto-coding"


@pytest.mark.asyncio
async def test_math_followup_stays_on_reasoning_even_if_layer_one_misclassifies(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def classify_as_daily(_messages: list[dict[str, str]]) -> str:
        return "auto-daily"

    monkeypatch.setattr(preinject, "_route_with_llm", classify_as_daily)
    messages = [
        {
            "role": "user",
            "content": "Evaluate the definite integral from 0 to 1 of x squared times e to x.",
        },
        {"role": "assistant", "content": "The antiderivative gives the result e - 2."},
        {
            "role": "user",
            "content": "Differentiate your antiderivative to check the result and state its decimal approximation.",
        },
    ]

    assert await preinject._resolve_auto_routing("auto", messages) == "auto-reasoning::math"


@pytest.mark.asyncio
async def test_auto_route_uses_entry_text_when_memory_was_added_to_user_message() -> None:
    from portal.platform.inference.router import trace

    current_turn = (
        "We run Kubernetes 1.30 and need read-only access to pods in namespace staging. "
        "Propose the least-privilege Role and RoleBinding, explain the scope choice, "
        "and give a safe way to verify it."
    )
    memories = [
        "CVE exploitation with an authorized purple team attack chain.",
        "Security incident response, threat hunting, and firewall analysis.",
        "Write Sigma rules to detect credential theft and lateral movement.",
        "Review penetration test findings and exploit validation results.",
    ]
    injected_memory = "\n".join(memories)
    messages = [{"role": "user", "content": f"{current_turn}\n\n{injected_memory}"}]
    record = trace.TurnTrace("test-route-before-memory")
    token = trace._current.set(record)
    try:
        workspace = await preinject._resolve_auto_routing(
            "auto", messages, current_turn_text=current_turn
        )
        receipt = record.to_dict()["routing_receipt"]
    finally:
        trace._current.reset(token)

    assert workspace == "auto-coding"
    assert receipt["current_turn_text_chars"] == len(current_turn)
    assert receipt["memory_chars_excluded"] == len("\n\n" + injected_memory)
    assert not {item["keyword"] for item in receipt["matched_keywords"]} & {
        "cve",
        "exploit",
        "security",
        "purple team",
        "firewall",
    }


@pytest.mark.asyncio
async def test_classifier_and_keyword_fallback_use_entry_text_with_memory_suffix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from portal.platform.inference.router import trace

    current_turn = "Please compare the runtime tradeoffs between two generic application designs."
    memories = ["CVE exploitation, purple team attack chain, and firewall incident response."] * 4
    messages = [{"role": "user", "content": f"{current_turn}\n\n" + "\n".join(memories)}]
    classifier_inputs: list[list[dict[str, str]]] = []
    fallback_inputs: list[list[dict[str, str]]] = []

    async def classify(route_messages):
        classifier_inputs.append(route_messages)
        return None

    def keyword_fallback(route_messages):
        fallback_inputs.append(route_messages)
        return "auto-reasoning"

    monkeypatch.setattr(preinject, "_route_with_llm", classify)
    monkeypatch.setattr(preinject, "_detect_workspace", keyword_fallback)
    record = trace.TurnTrace("test-classifier-before-memory")
    token = trace._current.set(record)
    try:
        workspace = await preinject._resolve_auto_routing(
            "auto", messages, current_turn_text=current_turn
        )
        receipt = record.to_dict()["routing_receipt"]
    finally:
        trace._current.reset(token)

    expected_input = [{"role": "user", "content": current_turn}]
    assert workspace == "auto-reasoning"
    assert classifier_inputs == [expected_input]
    assert fallback_inputs == [expected_input]
    assert receipt["scorer"] == "keyword_fallback"
    assert receipt["memory_chars_excluded"] == len("\n\n" + "\n".join(memories))
    assert not {item["keyword"] for item in receipt["matched_keywords"]} & {
        "cve",
        "exploit",
        "purple team",
        "firewall",
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("multipart", [False, True])
async def test_open_webui_memory_context_suffix_does_not_influence_route(
    monkeypatch: pytest.MonkeyPatch, multipart: bool
) -> None:
    from portal.platform.inference.router import handlers, trace

    prompt = (
        "We run Kubernetes 1.30 and need read-only access to pods in namespace staging. "
        "Propose the least-privilege Role and RoleBinding, explain the scope choice, "
        "and give a safe way to verify it."
    )
    injected = (
        "<memory_context>\n[User Memory]\n- Security incident response, CVE exploits, "
        "purple-team exercises, and firewall analysis.\n</memory_context>"
    )
    content = (
        [{"type": "text", "text": prompt}, {"type": "text", "text": injected}]
        if multipart
        else f"{prompt}\n{injected}"
    )
    messages = [{"role": "user", "content": content}]
    body = {"messages": messages}

    async def classify_as_daily(_messages: list[dict[str, str]]) -> str:
        return "auto-daily"

    monkeypatch.setattr(preinject, "_route_with_llm", classify_as_daily)
    current_turn = handlers._capture_current_turn_text(body)
    record = trace.TurnTrace(f"test-owui-memory-{multipart}")
    token = trace._current.set(record)
    try:
        workspace = await preinject._resolve_auto_routing(
            "auto", messages, current_turn_text=current_turn
        )
        receipt = record.to_dict()["routing_receipt"]
    finally:
        trace._current.reset(token)

    assert workspace == "auto-coding"
    assert current_turn == prompt
    assert receipt["current_turn_text_chars"] == len(prompt)
    assert receipt["memory_chars_excluded"] > 0
    assert not {item["keyword"] for item in receipt["matched_keywords"]} & {
        "cve",
        "exploit",
        "security",
        "purple team",
        "firewall",
    }
