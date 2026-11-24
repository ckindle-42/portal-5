"""Compliance MCP conversation surface: context material serialization.

Hermetic: no network, no models, no retrieval; repository and runtime config
are monkeypatched.
"""

from __future__ import annotations

from portal.modules.compliance.tools import compliance_mcp


def test_compliance_context_material_is_json(monkeypatch):
    """mode=material once returned render()'s in-process AnswerContract and
    failed serialization on every call (PIPELINE_ALIGNMENT_V1 §13); the DD3
    builder is JSON by construction and its payload passes through whole."""
    import json

    from portal.modules.compliance.core import dual_document, runtime_config

    class _Repo:
        def close(self) -> None:
            pass

    monkeypatch.setattr(compliance_mcp, "_repo", _Repo)
    monkeypatch.setattr(
        runtime_config,
        "reading_context_limits",
        lambda: {"context_limit": 131072, "predict_limit": 24576},
    )
    monkeypatch.setattr(runtime_config, "reading_route_ceiling", lambda: 262144)
    monkeypatch.setattr(
        dual_document,
        "build",
        lambda repo, **kw: {
            "mode": "dual_document",
            "ref": kw["requirement_ref"],
            "text": "payload",
            "window": {
                "context_limit": kw["context_limit"],
                "served_ceiling": kw["served_ceiling"],
                "fits": True,
            },
            "documents_included": [{"title": "doc"}],
        },
    )

    out = compliance_mcp.compliance_context("CIP-007-6 R2 Part 2.3", mode="material")
    assert out["mode"] == "dual_document" and out["text"] == "payload"
    json.dumps(out)
