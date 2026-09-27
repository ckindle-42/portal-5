#!/usr/bin/env python3
"""Anchor a Gemma 4 no-think turn that follows a tool response (oMLX templates).

Gemma 4's chat template closes the reasoning channel for a no-think turn by
prefilling ``<|channel>thought\\n<channel|>`` — but only on a FRESH model turn.
After a tool response the generation prompt adds nothing, so the model decides
for itself whether to open a thought channel. Measured on the compliance
reading seat (PIPELINE_ALIGNMENT_V1 §13), with thinking off, post-tool turns
opened a channel and answered inside it, wrote the next tool call inside it,
or ran away until the token cap: through the pipeline that surfaced as a
2-token fragment or an 80 KB reasoning "answer". Prefilling the same empty
block after a tool response took the direct oMLX triage from 18/21 to 21/21
(card sampling) and from 6/7 to 7/7 (greedy); raw on Ollama, 8/8 clean calls
against 0/8. Google's canonical template (2026-07-09) and Ollama's gemma4
renderer carry the same gap; the Ollama side is handled in
``portal/platform/inference/ollama_native.py``.

For every oMLX model directory whose ``chat_template.jinja`` ends in the
Gemma 4 generation block, insert the one missing branch. Idempotent (a marker
line records the patch); the first patch keeps ``chat_template.jinja.orig``;
a patched model that is loaded is unloaded so its next load reads the file.

Run by ``./launch.sh sync-config``.
Usage: uv run python scripts/omlx_chat_template_patch.py [--dry-run]
"""

from __future__ import annotations

import json
import shutil
import sys
import urllib.request
from pathlib import Path

SETTINGS = Path.home() / ".omlx" / "settings.json"
OMLX_URL = "http://localhost:8085"
MARKER = "{#- portal5: no-think post-tool anchor (PIPELINE_ALIGNMENT_V1 §13) -#}"
_ANCHOR = """    {%- if ns.prev_message_type != 'tool_response' and ns.prev_message_type != 'tool_call' -%}
        {{- '<|turn>model\\n' -}}
        {%- if not enable_thinking | default(false) -%}
            {{- '<|channel>thought\\n<channel|>' -}}
        {%- endif -%}
"""
_BRANCH = f"""    {MARKER}
    {{%- elif ns.prev_message_type == 'tool_response' and not enable_thinking | default(false) -%}}
        {{{{- '<|channel>thought\\n<channel|>' -}}}}
"""


def patch_text(text: str) -> str | None:
    """The patched template, or None when it is not the Gemma 4 shape or is
    already patched."""
    if MARKER in text or _ANCHOR not in text:
        return None
    head, tail = text.rsplit(_ANCHOR, 1)
    if not tail.lstrip().startswith("{%- endif -%}"):
        return None
    return head + _ANCHOR + _BRANCH + tail


def _model_dirs() -> list[Path]:
    try:
        model = json.loads(SETTINGS.read_text()).get("model") or {}
    except (OSError, ValueError):
        return []
    dirs = model.get("model_dirs") or [model.get("model_dir")]
    return [Path(d) for d in dirs if d]


def _unload(model_id: str) -> None:
    req = urllib.request.Request(f"{OMLX_URL}/v1/models/{model_id}/unload", method="POST")
    try:
        urllib.request.urlopen(req, timeout=30)  # noqa: S310 - fixed localhost URL
    except Exception:  # noqa: BLE001 - not loaded / server down: next load reads the file
        pass


def main() -> int:
    dry = "--dry-run" in sys.argv
    patched = 0
    for root in _model_dirs():
        for template in sorted(root.glob("*/chat_template.jinja")):
            new = patch_text(template.read_text())
            if new is None:
                continue
            model_id = template.parent.name
            print(f"  patch {model_id}" + (" (dry run)" if dry else ""))
            if dry:
                continue
            backup = template.with_suffix(".jinja.orig")
            if not backup.exists():
                shutil.copy2(template, backup)
            template.write_text(new)
            _unload(model_id)
            patched += 1
    print(f"oMLX chat-template patch: {patched} patched")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
