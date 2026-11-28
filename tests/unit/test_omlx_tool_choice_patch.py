"""Verify the repo-maintained oMLX 0.8.4 forced tool_choice patch artifact."""

from __future__ import annotations

import ast
import importlib.util
import sys
import types
from pathlib import Path
from types import SimpleNamespace

PATCH = (
    Path(__file__).resolve().parents[2] / "scripts" / "omlx" / "tool_choice_required_0.8.4.patch"
)


def _extract_added_file(patch_text: str, target: str) -> str:
    lines: list[str] = []
    collecting = False
    for line in patch_text.splitlines():
        if line == f"+++ b/{target}":
            collecting = True
            continue
        if collecting and line.startswith("--- "):
            break
        if collecting and line.startswith("+") and not line.startswith("+++ "):
            lines.append(line[1:])
    return "\n".join(lines) + "\n"


def test_omlx_tool_choice_patch_structure_and_resolver(tmp_path: Path) -> None:
    text = PATCH.read_text(encoding="utf-8")
    for target in ("omlx/api/tool_choice.py", "omlx/engine/splash.py", "omlx/server.py"):
        assert f"+++ b/{target}" in text

    source = _extract_added_file(text, "omlx/api/tool_choice.py")
    ast.parse(source)

    # Load the extracted module with a minimal omlx.exceptions stub to test Qwen3.6 resolution.
    pkg = types.ModuleType("omlx")
    pkg.__path__ = []
    api_pkg = types.ModuleType("omlx.api")
    api_pkg.__path__ = []
    exc_mod = types.ModuleType("omlx.exceptions")

    class InvalidRequestError(Exception):
        def __init__(self, message: str, field: str | None = None) -> None:
            super().__init__(message)
            self.field = field

    exc_mod.InvalidRequestError = InvalidRequestError  # type: ignore[attr-defined]
    mod_file = tmp_path / "tool_choice.py"
    mod_file.write_text(source, encoding="utf-8")

    saved = {
        k: sys.modules.get(k)
        for k in ("omlx", "omlx.api", "omlx.exceptions", "omlx.api.tool_choice")
    }
    try:
        sys.modules["omlx"] = pkg
        sys.modules["omlx.api"] = api_pkg
        sys.modules["omlx.exceptions"] = exc_mod
        spec = importlib.util.spec_from_file_location("omlx.api.tool_choice", mod_file)
        assert spec and spec.loader
        mod = importlib.util.module_from_spec(spec)
        sys.modules["omlx.api.tool_choice"] = mod
        spec.loader.exec_module(mod)

        def fake_qwen3_coder_parser() -> None:
            pass

        fake_qwen3_coder_parser.__module__ = "mlx_lm.tool_parsers.qwen3_coder"
        tok = SimpleNamespace(tool_parser=fake_qwen3_coder_parser, tool_call_end="</tool_call>")
        tools = [
            {"type": "function", "function": {"name": "compliance_context"}},
            {"type": "function", "function": {"name": "compliance_read"}},
        ]
        req = mod.resolve_forced_tool_call("required", tools, tok)
        assert req is not None
        assert req.opening == "<tool_call>\n<function"
        assert req.close == "</tool_call>"
        assert req.single is False

        named = mod.resolve_forced_tool_call(
            {"type": "function", "function": {"name": "compliance_read"}}, tools, tok
        )
        assert named is not None
        assert named.opening == "<tool_call>\n<function=compliance_read>"
        assert named.single is True
        assert mod.resolve_forced_tool_call("auto", tools, tok) is None
    finally:
        for k, v in saved.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v
