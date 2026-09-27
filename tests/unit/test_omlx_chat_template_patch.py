"""scripts/omlx_chat_template_patch.py — the Gemma 4 no-think post-tool anchor.

The patched template must render the empty reasoning block after a tool
response when thinking is off (PIPELINE_ALIGNMENT_V1 §13), leave every other
generation prompt byte-identical, and patch once.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import jinja2

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location(
    "omlx_chat_template_patch", ROOT / "scripts" / "omlx_chat_template_patch.py"
)
assert _spec and _spec.loader
patcher = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(patcher)

# The generation-prompt tail every served Gemma 4 conversion carries, with a
# minimal message loop that tracks prev_message_type the way the real one does.
GEMMA4 = """{%- set ns = namespace(prev_message_type=None) -%}
{%- for message in messages -%}
    {%- if message['role'] == 'tool' -%}
        {{- '<|tool_response>' + message['content'] + '<tool_response|>' -}}
        {%- set ns.prev_message_type = 'tool_response' -%}
    {%- else -%}
        {{- '<|turn>' + message['role'] + '\\n' + message['content'] + '<turn|>\\n' -}}
        {%- set ns.prev_message_type = None -%}
    {%- endif -%}
{%- endfor -%}

{%- if add_generation_prompt -%}
    {%- if ns.prev_message_type != 'tool_response' and ns.prev_message_type != 'tool_call' -%}
        {{- '<|turn>model\\n' -}}
        {%- if not enable_thinking | default(false) -%}
            {{- '<|channel>thought\\n<channel|>' -}}
        {%- endif -%}
    {%- endif -%}
{%- endif -%}"""

EMPTY_BLOCK = "<|channel>thought\n<channel|>"
USER = [{"role": "user", "content": "q"}]
POST_TOOL = [*USER, {"role": "tool", "content": "r"}]


def _render(template: str, messages: list[dict], enable_thinking: bool) -> str:
    return (
        jinja2.Environment()
        .from_string(template)
        .render(messages=messages, add_generation_prompt=True, enable_thinking=enable_thinking)
    )


def test_post_tool_no_think_turn_opens_with_the_empty_block() -> None:
    patched = patcher.patch_text(GEMMA4)
    assert patched is not None
    assert _render(GEMMA4, POST_TOOL, False).endswith("<tool_response|>")
    assert _render(patched, POST_TOOL, False).endswith("<tool_response|>" + EMPTY_BLOCK)


def test_every_other_generation_prompt_is_unchanged() -> None:
    patched = patcher.patch_text(GEMMA4)
    assert patched is not None
    for messages, think in ((USER, False), (USER, True), (POST_TOOL, True)):
        assert _render(patched, messages, think) == _render(GEMMA4, messages, think)


def test_patch_is_idempotent_and_ignores_other_templates() -> None:
    patched = patcher.patch_text(GEMMA4)
    assert patched is not None
    assert patcher.patch_text(patched) is None
    assert patcher.patch_text("{{ messages }}") is None
