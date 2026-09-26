# DeepSeek-R1 (0528) tool-call output parser for mlx_lm.
#
# WHY THIS FILE EXISTS IN THE REPO: oMLX loads text-model tool parsers from
# `mlx_lm.tool_parsers.<tool_parser_type>` (mlx_lm/tokenizer_utils.py reads
# `tool_parser_type` from the model's tokenizer_config.json). The first copy
# of this parser was installed directly into the brew oMLX site-packages and
# was silently LOST on a later brew upgrade (found 2026-09-25 when the
# DeepSeek-R1-0528-Qwen3-8B council-operator seat stopped emitting tool
# calls). The canonical copy now lives here; scripts/install_omlx_parsers.sh
# copies it into the running install and stamps the model's tokenizer_config.
# Re-run it after every `brew upgrade omlx`.
#
# FORMAT (emitted by DeepSeek-R1-0528-Qwen3-8B, verified live):
#   <｜tool▁calls▁begin｜><｜tool▁call▁begin｜>function<｜tool▁sep｜>NAME
#   ```json
#   {"arg": "value"}
#   ```<｜tool▁call▁end｜>
#   <｜tool▁call▁begin｜>...<｜tool▁call▁end｜>
#   <｜tool▁calls▁end｜>
#
# The markers use U+FF5C (fullwidth vertical line) and U+2581 (lower one
# eighth block) — copied verbatim from the model's tokenizer, not ASCII
# look-alikes.

import json
from typing import Any

import regex as re

tool_call_start = "<｜tool▁calls▁begin｜>"
tool_call_end = "<｜tool▁calls▁end｜>"

_call_regex = re.compile(
    r"<｜tool▁call▁begin｜>\s*function\s*<｜tool▁sep｜>\s*(?P<name>[\w.\-]+)\s*"
    r"```json\s*(?P<args>\{.*?\})\s*```\s*<｜tool▁call▁end｜>",
    re.DOTALL,
)


def parse_tool_call(text: str, tools: Any | None = None):
    """Every complete tool call in the payload, in order.

    Returns a LIST of {"name", "arguments"} — the oMLX consumer
    (api/tool_calling.py) accepts list-or-dict and one
    <｜tool▁calls▁begin｜> block may contain several calls.
    Raises ValueError when no call is present (the consumer's no-tool-call
    signal), never returns a fabricated one.
    """
    calls = []
    for match in _call_regex.finditer(text):
        calls.append({"name": match.group("name"), "arguments": json.loads(match.group("args"))})
    if not calls:
        raise ValueError(f"Could not parse tool call from: {text[:200]}")
    return calls
