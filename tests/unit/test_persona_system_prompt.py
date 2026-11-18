from __future__ import annotations

from portal.platform.inference.router.preinject import _inject_persona_system_prompt
from portal.platform.inference.router.workspaces import _PERSONA_MAP

_ROLE_SLUG = "codereviewer"


def test_follow_up_keeps_the_role_prompt_and_strips_history() -> None:
    from portal.platform.inference.router.preinject import _inject_requested_prompts

    prompt = _PERSONA_MAP[_ROLE_SLUG].system_prompt
    out = _inject_requested_prompts(
        "auto-spl",
        {
            "messages": [
                {"role": "user", "content": f"/{_ROLE_SLUG} fix: teh cat"},
                {"role": "assistant", "content": "fixed"},
                {"role": "user", "content": "and the title"},
            ]
        },
    )
    assert out["messages"][0]["content"].startswith(prompt)
    assert out["messages"][1]["content"] == "fix: teh cat"
    assert out["messages"][2]["content"] == "fixed"
    assert out["messages"][3]["content"] == "and the title"


def test_role_slash_strips_a_text_part() -> None:
    from portal.platform.inference.router.preinject import _inject_requested_prompts

    out = _inject_requested_prompts(
        "auto-spl",
        {
            "messages": [
                {
                    "role": "user",
                    "content": [{"type": "text", "text": f"/{_ROLE_SLUG} hello"}],
                }
            ]
        },
    )
    assert out["messages"][1]["content"][0]["text"] == "hello"


def test_list_system_content_keeps_caller_after_the_persona_prompt() -> None:
    prompt = _PERSONA_MAP["agenticheavy"].system_prompt
    out = _inject_persona_system_prompt(
        "agenticheavy",
        {
            "messages": [
                {"role": "system", "content": [{"type": "text", "text": "CALLER_SENTINEL"}]}
            ]
        },
    )
    content = out["messages"][0]["content"]
    assert content[0] == {"type": "text", "text": prompt}
    assert content[1]["text"] == "CALLER_SENTINEL"
