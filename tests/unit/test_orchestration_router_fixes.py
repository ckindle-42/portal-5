"""Regression tests for the orchestration arm's real router seams."""

from __future__ import annotations

import pytest

from portal.platform.inference.router import validation


@pytest.mark.parametrize(
    "inject",
    [validation._inject_ollama_options, validation._inject_omlx_options],
)
def test_bite_sampling_follows_think_off_seat(inject) -> None:
    from portal.platform.inference.router.preinject import _resolve_workspace_variant

    workspace_id = _resolve_workspace_variant("auto-daily::fast", "auto-daily", "fast")
    model = validation.WORKSPACES[workspace_id]["model_hint"]
    request = {
        "model": model,
        "portal_bite_tools": ["finish"],
        "max_tokens": 4096,
    }

    prepared = inject(request, workspace_id)
    sampling = prepared["options"] if inject is validation._inject_ollama_options else prepared

    assert sampling["temperature"] == 0.7
    assert sampling["top_p"] == 0.8
    assert sampling["top_k"] == 20
    assert sampling["min_p"] == 0.0
    assert sampling["presence_penalty"] == 1.5
    assert not prepared.get("thinking_budget")
    if inject is validation._inject_omlx_options:
        assert prepared["chat_template_kwargs"]["enable_thinking"] is False
    else:
        assert prepared["think"] is False


def test_bite_persona_inherits_tools_from_its_own_workspace_model() -> None:
    """The real splunkdetectionauthor has no tools_allow; its pool is auto-spl's (10-28)."""
    from portal.platform.inference.router.eval_gate import resolve_bite_tool_pool

    workspaces = {
        "auto-daily::deep": {"tools": ["web_search"]},
        "auto-spl": {"tools": ["query_splunk", "spl_validate_syntax"]},
    }
    personas = {"splunkdetectionauthor": {"workspace_model": "auto-spl"}}

    def resolve(persona, workspace_id):
        allow = persona.get("tools_allow")
        return sorted(allow if allow is not None else workspaces[workspace_id]["tools"])

    body = {"portal_bite_tools": ["query_splunk"], "portal_bite_persona": "splunkdetectionauthor"}
    pool = resolve_bite_tool_pool(
        body, "auto-daily::deep", "auto-daily::deep", personas, workspaces, resolve
    )
    assert pool == ["query_splunk", "spl_validate_syntax"]
    assert "portal_bite_persona" not in body
