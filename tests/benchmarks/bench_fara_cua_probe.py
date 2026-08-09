#!/usr/bin/env python3
"""Fara1.5-27B CUA action-emission preflight probe (isolated, no fleet change).

Not a web-task success score — that requires MagenticLite (see KNOWN_LIMITATIONS
follow-on). This asserts Fara loads and emits a well-formed computer_use
tool_call on a screenshot prompt, which is the minimum bar before investing in
the full harness.

The system prompt below is assembled from the sentences published verbatim on
the model card (huggingface.co/microsoft/Fara1.5-27B) plus the documented
action-name list. Microsoft states the full system prompt, including the
complete `computer_use` JSON tool schema, "ships with the model in
MagenticLite" and is not otherwise published — this probe does not fabricate
that missing schema text, it supplies the tool definition via the standard
Ollama `tools` field instead (which the model was trained to respond to via
its native tool-calling format, per the Q4_K_M's confirmed tool-capable
Modelfile).
"""

from __future__ import annotations

import base64
import json
import os
import re
import sys

import httpx

OLLAMA = os.environ.get("OLLAMA_URL", "http://localhost:11434")
FARA_TAG = os.environ["FARA_TAG"]
FIXTURE = os.environ.get("FARA_SCREENSHOT", "tests/benchmarks/fixtures/fara_login.png")

# Verbatim sentences from the model card's published system-prompt excerpt.
SYSTEM = os.environ.get(
    "FARA_SYSTEM_PROMPT",
    "You are Fara, a computer use agent (CUA) specialized for web browsers. "
    "You are developed by Microsoft AI Frontiers. You assist users with "
    "completing and automating tasks that require the use of a web browser. "
    "The model was trained in the timeframe of January - April 2026. Your "
    "knowledge cutoff is limited to early 2026.\n\n"
    "A critical point is a situation where we must pause and request "
    "information or confirmation from the user before proceeding. "
    "Case 1 (Missing User Information): the task requires personal "
    "information the user has not provided (e.g., email, phone number, "
    "address, payment details). Case 2 (Underspecified Task): the task "
    "description is ambiguous or missing details needed to make a decision. "
    "Case 3 (Irreversible Action): we are about to perform an action that "
    "cannot be undone (e.g., submitting a form, completing a purchase, "
    "sending a message, deleting data). Only stop at a critical point if "
    "(1) required information is missing, (2) the task is ambiguous, OR "
    "(3) an irreversible action lacks explicit user authorization.",
)
ACTIONS = {
    "left_click",
    "right_click",
    "double_click",
    "triple_click",
    "mouse_move",
    "left_click_drag",
    "type",
    "key",
    "scroll",
    "hscroll",
    "visit_url",
    "history_back",
    "web_search",
    "pause_and_memorize_fact",
    "ask_user_question",
    "wait",
    "terminate",
}
COMPUTER_USE_TOOL = {
    "type": "function",
    "function": {
        "name": "computer_use",
        "description": "Perform an action on the current browser screenshot.",
        "parameters": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": sorted(ACTIONS)},
                "coordinate": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "[x, y] pixel coordinate for click-family actions",
                },
                "text": {"type": "string", "description": "text for type/key/visit_url/web_search"},
            },
            "required": ["action"],
        },
    },
}


def _extract_action(msg: dict) -> tuple[str | None, dict]:
    """Parse Fara's tool call, whichever of three shapes it lands in.

    Depending on whether Ollama's generic (non-Fara-specific) chat template
    extracts it, the call can be: (a) native structured tool_calls (what the
    Modelfile's tool-capable template advertises, and the ideal case); (b) an
    inline JSON <tool_call>{"name":...,"arguments":{...}}</tool_call> block
    (the format the model card's raw-output docs describe); or (c) an XML
    <function=NAME><parameter=KEY>value</parameter></function> dialect,
    observed emitted inside the "thinking" field rather than "content" for
    this custom import (no FROM template override was used, so the GGUF's
    own embedded template drives extraction, and Ollama's built-in tool-call
    parser does not recognize this XML dialect as structured tool_calls).
    """
    text = msg.get("content", "") or ""
    thinking = msg.get("thinking", "") or ""
    args: dict = {}

    tool_calls = msg.get("tool_calls") or []
    if tool_calls:
        fn = tool_calls[0].get("function", {})
        args = fn.get("arguments", {})
        return args.get("action"), args

    combined = text + "\n" + thinking
    m = re.search(r"<tool_call>\s*(\{.*?\})\s*</tool_call>", combined, re.S)
    if m:
        obj = json.loads(m.group(1))
        args = obj.get("arguments", obj)
        return args.get("action") or args.get("name"), args

    m = re.search(r"<function=computer_use>(.*?)</function>", combined, re.S)
    if m:
        # Non-greedy match bounded by a lookahead for the next <parameter=
        # or the closing </function>, so a missing </parameter> close tag
        # (observed in some samples) is reported as a malformed parameter
        # rather than silently absorbing the next parameter's tag and value.
        for pm in re.finditer(
            r"<parameter=(\w+)>\s*(.*?)\s*(?:</parameter>|(?=<parameter=)|(?=$))",
            m.group(1),
            re.S,
        ):
            key, val = pm.group(1), pm.group(2).strip()
            if "<parameter=" in val or "<function" in val:
                continue  # malformed: no close tag, value bled into next field
            args[key] = val
        return args.get("action"), args

    return None, args


def main() -> int:
    img = base64.b64encode(open(FIXTURE, "rb").read()).decode()
    body = {
        "model": FARA_TAG,
        "stream": False,
        "options": {"temperature": 0.0},
        "tools": [COMPUTER_USE_TOOL],
        "messages": [
            {"role": "system", "content": SYSTEM},
            {
                "role": "user",
                "content": "Sign in to the site.",
                "images": [img],
            },
        ],
    }
    r = httpx.post(f"{OLLAMA}/api/chat", json=body, timeout=300)
    r.raise_for_status()
    msg = r.json().get("message", {})
    action, args = _extract_action(msg)

    if action is None:
        print("FAIL: no tool_call (native or inline) with an 'action' field emitted")
        print("content:", msg.get("content", "")[:400])
        print("thinking:", msg.get("thinking", "")[:400])
        return 1

    ok_action = action in ACTIONS
    has_coord = any(k in json.dumps(args) for k in ("coordinate", "x", "y"))
    print(
        json.dumps(
            {
                "emitted_tool_call": True,
                "action": action,
                "action_supported": ok_action,
                "has_coordinate": has_coord,
                "raw_args": args,
            },
            indent=2,
        )
    )
    return 0 if ok_action else 2


if __name__ == "__main__":
    sys.exit(main())
