"""Offline contracts for the Pipeline's eval tool-schema canonicalisation."""

from __future__ import annotations

import json

from portal.platform.inference.tool_registry import (
    canonicalise_eval_tools,
    canonicalise_tools_for_template,
)

_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Get the current weather for a city",
            "parameters": {
                "type": "object",
                "required": ["city"],
                "properties": {"city": {"type": "string"}},
            },
        },
    }
]


def test_schema_keys_are_sorted_and_every_nested_node_carries_a_description() -> None:
    converted = canonicalise_tools_for_template(_TOOLS)
    parameters = converted[0]["function"]["parameters"]

    assert list(parameters) == sorted(parameters)
    assert "description" not in parameters  # oMLX passes the root schema as is_schema=False
    assert parameters["properties"]["city"]["description"] == ""
    assert converted[0]["function"]["description"] == "Get the current weather for a city"


def test_canonicalisation_is_idempotent_so_omlx_reproduces_its_own_shape() -> None:
    once = canonicalise_tools_for_template(_TOOLS)
    twice = canonicalise_tools_for_template(json.loads(json.dumps(once)))

    assert once == twice


def test_a_tool_without_parameters_gets_the_empty_object_omlx_renders() -> None:
    converted = canonicalise_tools_for_template(
        [{"type": "function", "function": {"name": "status"}}]
    )

    assert converted[0]["function"]["parameters"] == {"properties": {}, "type": "object"}
    assert converted[0]["function"]["description"] == ""


def test_eval_backends_get_canonical_tools_and_production_bodies_do_not() -> None:
    eval_body = {"tools": _TOOLS}
    prod_body = {"tools": _TOOLS}

    canonicalise_eval_tools(eval_body, "eval_openai")
    canonicalise_eval_tools(prod_body, "omlx")

    assert eval_body["tools"] == canonicalise_tools_for_template(_TOOLS)
    assert prod_body["tools"] == _TOOLS


def test_a_body_without_tools_is_left_alone() -> None:
    body: dict = {"messages": []}

    canonicalise_eval_tools(body, "eval_openai")

    assert body == {"messages": []}
