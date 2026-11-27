"""P5 — the one citation-integrity diagnostic, and harness parity.

Every case runs against a fixture store built in ``tmp_path`` (one regulatory
document, one operator document, synthetic text) so nothing skips: the
resolving, fabricated and side-evidencing paths are all exercised.
"""

from __future__ import annotations

from scripts.compliance.truth.citation_integrity import MIN_QUOTE_WORDS


def test_min_quote_words_is_the_b0_calibrated_value():
    assert MIN_QUOTE_WORDS == 2


def test_obligation_attribution_inside_a_quote_is_not_an_attribution():
    import importlib

    conv = importlib.import_module("scripts.compliance.ask_conversational")
    pattern = conv._STANDARD_ATTRIBUTION
    quoted = '- "Updated CIP-004 and CIP-011 requirements for standards effective 1/1/2024"'
    assert not pattern.search(conv.QUOTED_SPAN.sub(" ", quoted))
    assert not pattern.search("CIP-011 requirements were updated")
    assert pattern.search("CIP-011 requires an information protection program")


def test_acceptance_workspace_preserves_thread_resolves_alias_and_reports_ungrounded(
    monkeypatch, tmp_path
) -> None:
    import httpx

    from scripts import compliance_acceptance as ca

    thread = ca.WorkspaceThread(httpx.Client(), "compliance-reading", "http://localhost:9099")
    assert thread.preset["params"].get("system"), (
        "compliance-reading alias must load OWUI system prompt"
    )

    created: list[object] = []

    class _FakeThread:
        def __init__(self, *_args, **_kwargs) -> None:
            self.messages: list[dict[str, str]] = []
            created.append(self)

        def turn(self, question: str) -> dict:
            self.messages.append({"role": "user", "content": question})
            self.messages.append({"role": "assistant", "content": 'No source "fake quote here".'})
            return {
                "question": question,
                "answer": 'No source "fake quote here".',
                "http_status": 200,
                "turn_budget_exceeded": False,
                "prompt_tokens_high_water": 100,
                "serving": {"serving_window": 131072},
                "tool_calls": {"compliance_context": 1},
            }

    monkeypatch.setattr(ca, "WorkspaceThread", _FakeThread)
    monkeypatch.setattr(ca, "environment", lambda _u: {})
    monkeypatch.setattr(
        ca, "_campaign_inputs", lambda _s: {"seat": _s, "workspace_prompt_sha": "x"}
    )
    monkeypatch.setattr(
        "scripts.compliance.truth.citation_integrity.integrity",
        lambda *_a, **_kw: {
            "lines": [{"claim": "bad line", "grounded": False}],
            "fabricated_tokens": [],
            "grounded": False,
            "ungrounded_lines": ["bad line"],
            "n_claims": 1,
        },
    )
    threads: dict = {}
    c1 = {
        "id": "parent",
        "ref": "CIP-007-6 R2",
        "thread": "main",
        "question": "Q1",
        "tool_calls_min": 1,
    }
    c2 = {
        "id": "choice",
        "ref": "CIP-007-6 R2 Part 2.3",
        "thread": "main",
        "question": "Q2",
        "tool_calls_min": 1,
    }
    r1 = ca.run_cell(
        httpx.Client(), "http://localhost:8937", c1, "seat", "workspace", 1, tmp_path, threads
    )
    r2 = ca.run_cell(
        httpx.Client(), "http://localhost:8937", c2, "seat", "workspace", 1, tmp_path, threads
    )
    assert len(created) == 1, "main-thread turns must reuse one WorkspaceThread"
    assert r2["thread_length_messages"] == 4
    cite_check = next(c for c in r1["checks"] if c["assertion"] == "cited_ids_resolve")
    assert not cite_check["ok"] and cite_check["detail"] == ["bad line"]


def test_reading_workspace_prompt_covers_vsl_and_quote_discipline() -> None:
    import yaml

    from portal.platform.inference.config import effective_workspace

    portal = yaml.safe_load(open("config/portal.yaml", encoding="utf-8"))
    prompt = effective_workspace(portal["workspaces"], "auto-compliance::reading")[
        "system_prompt_append"
    ]
    assert "Violation Severity Levels" in prompt and "compliance_search" in prompt
    assert "Reserve double quotes strictly for verbatim source quotes" in prompt
