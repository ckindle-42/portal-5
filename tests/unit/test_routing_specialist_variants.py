"""Deterministic math-variant promotion in the auto-router.

s5-route-math-integral failed live (2026-11-24) with "expected route
auto-reasoning::math, received auto-reasoning": both the deterministic gate
(detect_specialist_intent) and Layer 1's post-classification variant pass
(_infer_variant) dropped the ::math variant. These tests pin both paths —
and pin that general reasoning and Kubernetes turns do NOT get promoted.
"""

from __future__ import annotations

from portal.platform.inference.router.routing import (
    _detect_workspace,
    _infer_variant,
    detect_specialist_intent,
)

_UAT_INTEGRAL = (
    "Evaluate the definite integral from 0 to 1 of x squared times e to the x. "
    "Show a compact derivation and the exact result."
)

_MATH_PROMPTS = (
    _UAT_INTEGRAL,
    "Differentiate your antiderivative to check the result and state the "
    "decimal approximation to three places.",
    "Take the derivative of f(x) = x cubed times sin(x) and simplify.",
    "Solve this calculus problem: integrate 1/(1+x squared) over the real line.",
)

_GENERAL_REASONING_PROMPTS = (
    "Weigh the pros and cons of two pricing models and give a detailed analysis.",
    "Break down the trade-off between latency and consistency in this design.",
    "Explain in depth how the two proposals differ, step by step.",
)

_KUBERNETES_PROMPTS = (
    "Write the kubernetes RBAC rolebinding YAML manifest for the deploy role.",
    "Give me a k8s manifest for the ingest service with a role binding for it.",
)


def _user_messages(text: str) -> list[dict]:
    return [{"role": "user", "content": text}]


def test_detect_specialist_intent_promotes_math_variant() -> None:
    for text in _MATH_PROMPTS:
        assert detect_specialist_intent(_user_messages(text)) == "auto-reasoning::math", text


def test_infer_variant_promotes_math_variant() -> None:
    for text in _MATH_PROMPTS:
        assert _infer_variant("auto-reasoning", text) == "auto-reasoning::math", text


def test_detect_specialist_intent_leaves_general_reasoning_alone() -> None:
    for text in _GENERAL_REASONING_PROMPTS:
        assert detect_specialist_intent(_user_messages(text)) is None, text


def test_infer_variant_keeps_general_reasoning_on_base() -> None:
    for text in _GENERAL_REASONING_PROMPTS:
        assert _infer_variant("auto-reasoning", text) == "auto-reasoning", text


def test_layer2_general_reasoning_still_routes_to_base() -> None:
    for text in _GENERAL_REASONING_PROMPTS:
        assert _detect_workspace(_user_messages(text)) == "auto-reasoning", text


def test_kubernetes_prompts_still_route_to_auto_coding() -> None:
    for text in _KUBERNETES_PROMPTS:
        assert detect_specialist_intent(_user_messages(text)) == "auto-coding", text


_CORPUS_INTEGRAL = "solve this integral: ∫ x² e^x dx"


def test_baseline_gate_records_math_seat_for_corpus_integral() -> None:
    from scripts.routing_regression import deterministic_then_keywords

    assert deterministic_then_keywords(_user_messages(_CORPUS_INTEGRAL)) == "auto-reasoning::math"
