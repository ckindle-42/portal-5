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

    assert await preinject._resolve_auto_routing("auto", messages) == "auto-reasoning"
