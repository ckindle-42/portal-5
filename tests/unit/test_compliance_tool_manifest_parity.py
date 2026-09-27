"""The compliance tool manifest must not contradict the functions it describes.

The manifest (``config/inference/tools_manifest_compliance_mcp.json``) is what
the model sees; it is hand-maintained and had drifted. Two directions of drift
broke live readings (PIPELINE_ALIGNMENT_V1 §13): a parameter the schema
REQUIRED that the function defaults (``compliance_requirement.valid_at`` — the
model invented a date and got ``found: false``), and a parameter the workspace
prompt instructs that the schema HID (``compliance_context(mode="material")``).
Omitting an optional parameter from the schema is deliberate surface reduction
and is allowed.
"""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "config/inference/tools_manifest_compliance_mcp.json"
MCP_SOURCE = ROOT / "portal/modules/compliance/tools/compliance_mcp.py"


#: Required in the schema though defaulted in code, on purpose: the empty
#: default lets the function return a named authorization error (P7/F09)
#: instead of a TypeError — the parameter is semantically mandatory.
_AUTH_REQUIRED = {"reviewer_token"}


def _signatures() -> dict[str, tuple[set[str], set[str]]]:
    """Function name -> (all parameter names, parameters without a default)."""
    out: dict[str, tuple[set[str], set[str]]] = {}
    for node in ast.parse(MCP_SOURCE.read_text()).body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            args = node.args
            positional_required = args.args[: len(args.args) - len(args.defaults)]
            required = {a.arg for a in positional_required} | {
                k.arg for k, d in zip(args.kwonlyargs, args.kw_defaults, strict=True) if d is None
            }
            out[node.name] = ({a.arg for a in args.args + args.kwonlyargs}, required)
    return out


def _manifest() -> list[dict]:
    return [t.get("function", t) for t in json.loads(MANIFEST.read_text())]


@pytest.mark.parametrize("tool", _manifest(), ids=lambda t: t["name"])
def test_schema_names_only_real_parameters_and_requires_no_defaulted_one(tool: dict) -> None:
    signatures = _signatures()
    assert tool["name"] in signatures, f"{tool['name']} has no function"
    params, required = signatures[tool["name"]]
    schema = tool["parameters"]
    assert set(schema.get("properties", {})) <= params, "schema names a parameter the code lacks"
    over_required = set(schema.get("required") or []) - required - _AUTH_REQUIRED
    assert not over_required, f"schema requires parameters the code defaults: {over_required}"


def test_every_parameter_the_reading_prompt_instructs_is_in_the_schema() -> None:
    prompt = yaml.safe_load((ROOT / "config/portal.yaml").read_text())["workspaces"][
        "compliance-reading"
    ]["system_prompt_append"]
    schemas = {t["name"]: t["parameters"].get("properties", {}) for t in _manifest()}
    instructed = 0
    # each `param="value"` belongs to the nearest tool named before it
    for match in re.finditer(r"\b(\w+)=\"(\w+)\"", prompt):
        tools = re.findall(r"\b(compliance_\w+|nerc_cip_\w+)", prompt[: match.start()])
        tool, param, value = tools[-1], match.group(1), match.group(2)
        assert param in schemas.get(tool, {}), f"prompt instructs {tool}({param}=...)"
        enum = schemas[tool][param].get("enum")
        if enum and value in {"material", "index"}:
            assert value in enum, f"prompt instructs {tool}({param}={value!r})"
        instructed += 1
    assert instructed, "the prompt no longer instructs any parameter — update this test"
