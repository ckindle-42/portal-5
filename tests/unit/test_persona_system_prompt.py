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


def test_general_role_claims_match_their_workspace() -> None:
    from portal.platform.inference.router.preinject import _resolve_workspace_variant
    from portal.platform.inference.router.workspaces import WORKSPACES

    expectations = {
        "dailydriver": (
            ("audio transcription → portal vision (`auto-vision`)",),
            ("audio transcription → portal document builder (`auto-documents`)",),
        ),
        "gemma4e4bvision": (
            ("auto-vision workspace", "16k-token context limit", "transcribe_audio"),
            ("google's gemma 4 e4b model", "128k token context window"),
        ),
        "gemma4jangvision": (
            ("8k-token context limit", "safety controls still apply"),
            ("256k token window", "no content restrictions", "thinking mode"),
        ),
        "gemma_vision": (("16k tokens",), ("256k context",)),
        "gemma_e4b": (
            ("the model is text-only", "auto-vision workspace", "transcribe_audio"),
            ("powered by gemma 4 e4b", "native audio, image, and video understanding"),
        ),
        "gemma_fast": (
            ("the model is text-only", "auto-vision workspace", "transcribe_audio"),
            (
                "powered by gemma 4 e2b",
                "you can see images, understand audio, and analyze video frames",
            ),
        ),
        "gptossanalyst": (
            ("auto-reasoning workspace", "do not claim a model identity"),
            (
                "gpt-oss analyst",
                "openai's gpt-oss model",
                "reinforcement learning from openai",
            ),
        ),
    }
    for slug, (expected, outdated) in expectations.items():
        persona = _PERSONA_MAP[slug]
        seat_id = _resolve_workspace_variant(
            persona.workspace_model, persona.workspace_model, persona.variant
        )
        seat = WORKSPACES[seat_id]
        text = " ".join(
            " ".join(
                str(value)
                for value in (
                    persona.name,
                    getattr(persona, "description", ""),
                    persona.system_prompt,
                )
                if value
            ).split()
        ).casefold()
        for phrase in expected:
            assert phrase in text, f"{slug} omits {phrase!r} for {seat_id}"
        for phrase in outdated:
            assert phrase not in text, f"{slug} still claims {phrase!r} for {seat_id}"
        assert seat.get("context_limit")
