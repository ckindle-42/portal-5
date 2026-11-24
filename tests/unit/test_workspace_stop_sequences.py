"""Workspace stop sequences reach both inference engines without losing caller values."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
import yaml
from yaml.nodes import MappingNode, ScalarNode, SequenceNode

from portal.platform.inference.config import WorkspaceSpec, load_portal_config
from portal.platform.inference.ollama_native import to_native_request
from portal.platform.inference.router import non_streaming, validation

STOP_SEQUENCES = ["</tool_response>", "</工具使用记录>"]


def test_workspace_spec_accepts_stop_sequences() -> None:
    spec = WorkspaceSpec(
        name="Stop test", description="Stop test workspace", module="security", stop=STOP_SEQUENCES
    )

    assert spec.stop == STOP_SEQUENCES


@pytest.mark.parametrize(
    "inject", [validation._inject_omlx_options, validation._inject_ollama_options]
)
@pytest.mark.parametrize("caller_stop", ["CALLER_STOP", ["CALLER_STOP", STOP_SEQUENCES[0]]])
def test_engine_options_merge_workspace_and_caller_stops(monkeypatch, inject, caller_stop) -> None:
    monkeypatch.setitem(validation.WORKSPACES, "stop-test", {"stop": STOP_SEQUENCES})

    result = inject({"model": "test-model", "stop": caller_stop}, "stop-test")
    expected = ["CALLER_STOP", *STOP_SEQUENCES]

    assert result["stop"] == expected
    if inject is validation._inject_ollama_options:
        assert result["options"]["stop"] == expected
        assert to_native_request(result, can_think=False)["options"]["stop"] == expected


def test_chain_hop_rebuilds_workspace_stop_options_for_ollama(monkeypatch) -> None:
    backend = SimpleNamespace(
        id="ollama",
        type="ollama",
        chat_url="http://ollama/v1/chat/completions",
        resolve_model=lambda model: "native-hop" if model == "hop" else None,
    )
    registry = SimpleNamespace(
        get_backend_candidates=lambda _workspace: [backend], list_healthy_backends=lambda: []
    )
    monkeypatch.setattr(non_streaming, "registry", registry)
    monkeypatch.setitem(validation.WORKSPACES, "stop-test", {"stop": STOP_SEQUENCES})

    url, body = non_streaming.resolve_hop_target(
        "stop-test",
        "hop",
        "http://omlx/v1/chat/completions",
        {"model": "primary", "stop": ["CALLER_STOP", *STOP_SEQUENCES], "options": {"stop": []}},
    )

    expected = ["CALLER_STOP", *STOP_SEQUENCES]
    assert url == backend.chat_url
    assert body["stop"] == expected
    assert body["options"]["stop"] == expected


def test_auto_security_workspace_has_stop_and_sampling_settings() -> None:
    config = load_portal_config(_force_reload=True)
    workspace = config.workspaces["auto-security"]

    assert workspace.stop == STOP_SEQUENCES
    assert workspace.repeat_penalty == 1.12
    assert workspace.temperature == 0.4
    assert workspace.owui_system_prompt.endswith(
        " Always respond in the same language as the user's message."
    )


def _mapping_values(node: MappingNode) -> dict[str, Any]:
    return {key.value: value for key, value in node.value if isinstance(key, ScalarNode)}


def _duplicate_mapping_keys(node: Any) -> list[str]:
    if isinstance(node, MappingNode):
        keys = [key.value for key, _value in node.value if isinstance(key, ScalarNode)]
        duplicates = sorted({key for key in keys if keys.count(key) > 1})
        nested = [
            duplicate for _key, value in node.value for duplicate in _duplicate_mapping_keys(value)
        ]
        return [*duplicates, *nested]
    if isinstance(node, SequenceNode):
        return [duplicate for value in node.value for duplicate in _duplicate_mapping_keys(value)]
    return []


def test_omlx_security_backend_has_no_duplicate_keys_or_model_entries() -> None:
    path = Path(__file__).parents[2] / "config" / "backends.yaml"
    document = yaml.compose(path.read_text())
    assert isinstance(document, MappingNode)
    backends_node = _mapping_values(document)["backends"]
    assert isinstance(backends_node, SequenceNode)
    omlx_security = next(
        node
        for node in backends_node.value
        if isinstance(node, MappingNode)
        and isinstance(_mapping_values(node).get("id"), ScalarNode)
        and _mapping_values(node)["id"].value == "omlx-security"
    )
    fields = _mapping_values(omlx_security)
    models_node = fields["models"]
    assert isinstance(models_node, SequenceNode)
    model_ids = []
    for model in models_node.value:
        model_id = _mapping_values(model).get("id")
        assert isinstance(model_id, ScalarNode)
        model_ids.append(model_id.value)

    assert not _duplicate_mapping_keys(omlx_security)
    assert len(model_ids) == len(set(model_ids))
