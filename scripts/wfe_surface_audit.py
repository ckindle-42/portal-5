#!/usr/bin/env python3
"""Fleet surface audit: five defect classes over every workspace and MCP tool.

Each class is a defect that cost the documents slice a campaign; this finds the same class
everywhere at once, without a model in the loop.

  1 tool-not-named      an offered tool the system prompt the pipeline sends never names or describes
  2 schema              an MCP manifest whose required/params disagree with the function, or whose
                        array items have no shape (the model has to guess the keys)
  3 unknown-arg         live through the pipeline: a read-only tool called with one extra key must
                        reject it with a structured error, not report success (--direct calls each
                        MCP itself to see the server's own behaviour)
  4 prompt-cross-talk   an unconditional ALWAYS/NEVER/MUST instruction tied to a tool's output
  5 delivery-drift      live Open WebUI presets vs the seeded files (workspaces and personas), plus
                        presets with no source file

    uv run python scripts/wfe_surface_audit.py              # table to stdout
    uv run python scripts/wfe_surface_audit.py --md docs/WFE_SURFACE_AUDIT_20261017.md
    uv run python scripts/wfe_surface_audit.py --classes 2,3
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import re
import sys
import urllib.error
import urllib.request
from collections import Counter
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))

Row = tuple[str, str, str, str]  # (class, subject, severity, detail)
#: Words a tool name is built from that say nothing about what the tool is for.
GENERIC = {
    "read",
    "write",
    "list",
    "get",
    "set",
    "create",
    "query",
    "search",
    "run",
    "tool",
    "file",
    "lookup",
    "check",
}
#: Tool-name prefixes safe to call with throwaway arguments (no writes, no side effects).
READ_ONLY = (
    "read_",
    "list_",
    "get_",
    "lookup_",
    "check_",
    "search_",
    "profile_",
    "classify_",
    "explain_",
)


def load_portal() -> dict:
    import yaml

    from portal.platform.inference.config import load_bench_workspaces_raw

    portal = yaml.safe_load((REPO / "config" / "portal.yaml").read_text()) or {}
    portal["workspaces"] = {
        **(portal.get("workspaces") or {}),
        **load_bench_workspaces_raw(REPO),
    }
    return portal


def manifests() -> dict[Path, list[dict]]:
    out = {}
    for f in sorted((REPO / "config" / "inference").glob("*manifest*.json")):
        data = json.loads(f.read_text())
        tools = data if isinstance(data, list) else data.get("tools", [])
        out[f] = [t for t in tools if isinstance(t, dict) and "name" in t]
    return out


# --------------------------------------------------------------------------
# class 1: tool not named in the prompt the pipeline sends
# --------------------------------------------------------------------------


def tool_families() -> dict[str, str]:
    """tool name -> the MCP manifest it comes from (its family)."""
    return {
        t["name"]: f.stem.removeprefix("tools_manifest_")
        for f, tools in manifests().items()
        for t in tools
    }


def class1() -> list[Row]:
    """open: the prompt names or describes some tool of a family but not this one (the documents
    prompt described create_* and never read_*). info: the prompt is silent on the whole family."""
    from tests.wfe.runner import workspace_context

    fam, rows = tool_families(), []
    for ws, spec in load_portal()["workspaces"].items():
        tools = spec.get("tools") or []
        if not tools:
            continue
        prompt = workspace_context(ws)["system_prompt"].lower()
        status = {}
        for t in tools:
            if re.search(rf"\b{re.escape(t.lower())}\b", prompt):
                status[t] = "named"
                continue
            words = [w for w in t.lower().split("_") if w not in GENERIC and len(w) > 3]
            described = bool(words) and any(re.search(rf"\b{re.escape(w)}", prompt) for w in words)
            status[t] = "described" if described else "silent"
        covered = {fam.get(t) for t, st in status.items() if st != "silent"}
        for t, st in status.items():
            if st == "named":
                continue
            if st == "described":
                rows.append(("1", f"{ws} / {t}", "info", "described by its words, not named"))
            elif fam.get(t) and fam[t] in covered:
                rows.append(
                    (
                        "1",
                        f"{ws} / {t}",
                        "open",
                        f"prompt covers other {fam[t]} tools, not this one",
                    )
                )
            else:
                rows.append(("1", f"{ws} / {t}", "info", "prompt is silent on this tool family"))
    return rows


# --------------------------------------------------------------------------
# class 2: manifest schema integrity
# --------------------------------------------------------------------------


def functions_for(manifest: Path) -> dict[str, ast.FunctionDef | ast.AsyncFunctionDef]:
    """The function definitions in the python files that load this manifest."""
    stem = manifest.stem
    found = {}
    for py in (REPO / "portal").rglob("*.py"):
        text = py.read_text(errors="ignore")
        if stem not in text:
            continue
        for node in ast.walk(ast.parse(text)):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                old = found.get(node.name)
                if old is None or (node.decorator_list and not old.decorator_list):
                    found[node.name] = node  # a registered tool beats a same-named helper
    return found


def params_of(fn) -> tuple[set[str], set[str], bool]:
    """(all named params, params without a default, takes **kwargs)."""
    a = fn.args
    pos = [x.arg for x in a.posonlyargs + a.args]
    defaults = len(a.defaults)
    required = set(pos[: len(pos) - defaults]) - {"self"}
    kw = [x.arg for x in a.kwonlyargs]
    required |= {x.arg for x, d in zip(a.kwonlyargs, a.kw_defaults, strict=True) if d is None}
    return (set(pos) | set(kw)) - {"self"}, required, a.kwarg is not None


#: Manifest/function differences that are deliberate REST adapters (the endpoint maps them).
ADAPTED = {
    ("code_sandbox_mcp", "execute_bash"): "REST endpoint accepts both `command` and `code`",
    **{
        (
            "cad_render_mcp",
            n,
        ): "run by the build123d-mcp engine through b123d_bridge, which injects session and out_dir"
        for n in (
            "cad_build",
            "cad_execute",
            "cad_finalize",
            "cad_find_holes",
            "cad_measure",
            "cad_render",
        )
    },
}


def signature_rows(subject: str, props: dict, req: set, fn) -> list[Row]:
    """manifest vs the function's own signature."""
    if fn is None:
        return [("2", subject, "info", "no function found to compare against")]
    names, needed, kwargs = params_of(fn)
    rows = []
    if not kwargs and set(props) - names:
        rows.append(
            (
                "2",
                subject,
                "open",
                f"manifest params not in the function: {sorted(set(props) - names)}",
            )
        )
    if extra := names - set(props) - {"author"}:
        rows.append(("2", subject, "info", f"function params not in the manifest: {sorted(extra)}"))
    if needed - req:
        rows.append(
            ("2", subject, "open", f"function requires {sorted(needed - req)}, manifest does not")
        )
    return rows


def shape_rows(subject: str, props: dict) -> list[Row]:
    """array/object parameters whose keys the model has to guess."""
    rows = []
    for p, spec in props.items():
        if spec.get("type") == "array":
            items = spec.get("items") or {}
            if items.get("type") == "object" and not items.get("properties"):
                rows.append(
                    ("2", f"{subject}.{p}", "shape", "array of objects with no item keys defined")
                )
            elif not items:
                rows.append(("2", f"{subject}.{p}", "shape", "array with no item schema"))
        elif spec.get("type") == "object" and not spec.get("properties"):
            rows.append(("2", f"{subject}.{p}", "shape", "object with no keys defined"))
    return rows


def class2() -> list[Row]:
    rows = []
    for f, tools in manifests().items():
        fns = functions_for(f)
        stem = f.stem.removeprefix("tools_manifest_")
        for t in tools:
            subject = f"{stem} / {t['name']}"
            schema = t.get("parameters") or t.get("inputSchema") or {}
            props, req = schema.get("properties", {}), set(schema.get("required", []))
            if req - set(props):
                rows.append(
                    ("2", subject, "open", f"required but undefined: {sorted(req - set(props))}")
                )
            if adapted := ADAPTED.get((stem, t["name"])):
                rows.append(("2", subject, "info", f"adapter: {adapted}"))
            else:
                rows += signature_rows(subject, props, req, fns.get(t["name"]))
            rows += shape_rows(subject, props)
    return rows


# --------------------------------------------------------------------------
# class 3: unknown-argument handling, live through the pipeline or MCP-direct
# --------------------------------------------------------------------------


def dummy(spec: dict):
    return {
        "string": "x",
        "integer": 1,
        "number": 1,
        "boolean": False,
        "array": [],
        "object": {},
    }.get(spec.get("type"), "x")


FILTERING = re.compile(r"for\s+k,\s*v\s+in\s+(?:arguments|args)\.items\(\)\s+if\s+k\s+in\b")


def filtering_dispatchers() -> list[Row]:
    """Static: a dispatcher that drops unknown keys and runs the call anyway (whisper did)."""
    return [
        (
            "3",
            f"{py.relative_to(REPO)}:{text[: m.start()].count(chr(10)) + 1}",
            "open",
            "dispatcher filters unknown arguments instead of rejecting them",
        )
        for py in sorted((REPO / "portal").rglob("*.py"))
        if "/tests/" not in str(py)
        for text in [py.read_text(errors="ignore")]
        for m in FILTERING.finditer(text)
    ]


def _native_tool_list(base: str) -> list[dict] | None:
    """Native tools/list, or None when that surface does not answer."""
    import asyncio

    import httpx

    from portal.platform.inference.mcp_http import list_tools

    async def fetch() -> list[dict]:
        async with httpx.AsyncClient() as client:
            return await list_tools(client, base, 3.0)

    try:
        return asyncio.run(fetch())
    except Exception:  # noqa: BLE001
        return None


def _listed_tools(base: str) -> tuple[list[dict] | None, str]:
    """Tools from native tools/list, else the REST /tools manifest."""
    native = _native_tool_list(base)
    if native is not None:
        return native, "native"
    try:
        with urllib.request.urlopen(f"{base}/tools", timeout=3) as response:  # noqa: S310
            payload = json.load(response)
    except Exception:  # noqa: BLE001
        return None, ""
    tools = payload.get("tools", []) if isinstance(payload, dict) else []
    return [t for t in tools if isinstance(t, dict)], "rest"


def _invoke_native_tool(base: str, name: str, args: dict) -> tuple[str, int]:
    import asyncio

    import httpx

    from portal.platform.inference.mcp_http import MCPHTTPError, call_tool

    async def fetch() -> dict:
        async with httpx.AsyncClient() as client:
            return await call_tool(client, base, name, args, 30.0)

    try:
        return json.dumps(asyncio.run(fetch())), 200
    except MCPHTTPError as exc:
        return str(exc), exc.status_code or 500


def _invoke_listed_tool(base: str, mode: str, name: str, args: dict) -> tuple[str, int]:
    if mode == "native":
        return _invoke_native_tool(base, name, args)
    request = urllib.request.Request(
        f"{base}/tools/{name}",
        data=json.dumps({"arguments": args}).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
            return response.read().decode(), response.status
    except urllib.error.HTTPError as err:
        return err.read().decode(), err.code


def _rejected_unknown(body: str, code: int) -> bool:
    try:
        parsed = json.loads(body)
    except json.JSONDecodeError:
        parsed = None
    is_error = isinstance(parsed, dict) and parsed.get("isError") is True
    if code not in (400, 422) and not is_error:
        return False
    return re.search(r"unexpected|invalid|unknown|extra|zz_unknown", body, re.I) is not None


def _without_is_error(body: str) -> str:
    """Drop the MCP isError flag so a successful native result is not an 'error' hit."""
    try:
        parsed = json.loads(body)
    except json.JSONDecodeError:
        return body
    if not isinstance(parsed, dict) or "isError" not in parsed:
        return body
    rest = {key: value for key, value in parsed.items() if key != "isError"}
    return json.dumps(rest)


def class3_direct() -> list[Row]:
    """Probe each MCP itself: what that server alone does with an extra key."""
    rows = []
    for e in load_portal()["mcp_fleet"]:
        port = e.get("port")
        if not port or not e.get("expose_to_pipeline", True):
            continue
        base = f"http://localhost:{port}"
        tools, mode = _listed_tools(base)
        if tools is None:
            rows.append(("3", e["id"], "info", "MCP unreachable"))
            continue
        for t in tools:
            name = t.get("name", "")
            if not name.startswith(READ_ONLY):
                rows.append(
                    ("3", f"{e['id']} / {name}", "skipped", "not a read-only tool: not called live")
                )
                continue
            schema = t.get("parameters") or t.get("inputSchema") or {}
            if not schema.get("properties"):
                rows.append(
                    ("3", f"{e['id']} / {name}", "ok", "takes no arguments: nothing can be dropped")
                )
                continue
            args = {
                k: dummy(schema.get("properties", {}).get(k, {}))
                for k in schema.get("required", [])
            }
            args["zz_unknown_probe"] = 1
            try:
                body, code = _invoke_listed_tool(base, mode, name, args)
            except Exception as err:  # noqa: BLE001
                rows.append(("3", f"{e['id']} / {name}", "info", f"call failed: {err}"))
                continue
            rejected = _rejected_unknown(body, code)
            visible = _without_is_error(body)
            ok = (
                bool(re.search(r'"success"\s*:\s*true', visible))
                or code == 200
                and not re.search(r"error", visible, re.I)
            )
            if rejected:
                rows.append(
                    ("3", f"{e['id']} / {name}", "ok", "extra key rejected with a structured error")
                )
            elif ok:
                rows.append(
                    (
                        "3",
                        f"{e['id']} / {name}",
                        "open",
                        "extra key accepted: success with an unknown argument",
                    )
                )
            else:
                rows.append(("3", f"{e['id']} / {name}", "info", f"HTTP {code}: {body[:90]}"))
    return rows


REJECTION = re.compile(r"unexpected|invalid|unknown|extra|zz_unknown", re.I)


def _pipeline_row(subject: str, result: Any) -> Row:
    """Classify one probe that went through ``ToolRegistry.dispatch``."""
    body = json.dumps(result)
    if isinstance(result, dict) and "error" in result:
        if "rejected the arguments" in body:
            return ("3", subject, "ok", "extra key rejected by the pipeline before the call")
        shaped = "returned an MCP tool error" in body or "rejected the MCP request" in body
        if shaped and REJECTION.search(body):
            return ("3", subject, "ok", "extra key rejected behind the pipeline by the server")
        return ("3", subject, "info", f"pipeline error: {result['error'][:90]}")
    if re.search(r'"success"\s*:\s*true', body) or not re.search(r"error", body, re.I):
        return ("3", subject, "open", "extra key accepted: success with an unknown argument")
    return ("3", subject, "info", f"mapped result: {body[:90]}")


def class3_pipeline() -> list[Row]:
    """Probe through ``ToolRegistry.dispatch`` — the call path production actually runs."""
    import asyncio

    from portal.platform.inference.tool_registry import MCP_SERVERS, ToolRegistry

    async def collect() -> list[Row]:
        registry = ToolRegistry()
        try:
            await registry.refresh(force=True)
            names = registry.list_tool_names()
            rows = []
            for name in names:
                tool = registry.get(name)
                subject = f"{tool.server_id} / {name}"
                schema = tool.parameters or {}
                if not name.startswith(READ_ONLY):
                    rows.append(("3", subject, "skipped", "not a read-only tool: not called live"))
                    continue
                if not schema.get("properties"):
                    rows.append(("3", subject, "ok", "takes no arguments: nothing can be dropped"))
                    continue
                args = {
                    k: dummy(schema.get("properties").get(k, {}))
                    for k in schema.get("required", [])
                }
                args["zz_unknown_probe"] = 1
                rows.append(_pipeline_row(subject, await registry.dispatch(name, args)))
            seen = {registry.get(n).server_id for n in names}
            rows += [
                ("3", sid, "info", "no tools discovered through the pipeline")
                for sid in sorted(set(MCP_SERVERS) - seen)
            ]
            return rows
        finally:
            await registry.close()

    return asyncio.run(collect())


def class3(direct: bool = False) -> list[Row]:
    """direct=True probes each MCP itself (server-level debugging); the default probes
    through the pipeline's ToolRegistry, so a finding reflects what production does."""
    rows = filtering_dispatchers()
    rows += class3_direct() if direct else class3_pipeline()
    return rows


# --------------------------------------------------------------------------
# class 4: prompt cross-talk
# --------------------------------------------------------------------------

LOUD = re.compile(r"\b(always|never|must|do not|don't)\b", re.I)
TOOLISH = re.compile(
    r"(download_url|tool result|tool output|clickable link|the tool|a tool|citation)", re.I
)
CONDITION = re.compile(r"\b(if|when|after|only|unless|once|whenever)\b", re.I)


def class4() -> list[Row]:
    from tests.wfe.runner import workspace_context

    rows = []
    for ws, spec in load_portal()["workspaces"].items():
        if not spec.get("tools"):
            continue
        for sentence in re.split(r"(?<=[.!?])\s+|\n+", workspace_context(ws)["system_prompt"]):
            if (
                LOUD.search(sentence)
                and TOOLISH.search(sentence)
                and not CONDITION.search(sentence)
            ):
                rows.append(("4", ws, "review", sentence.strip()[:150]))
    return rows


# --------------------------------------------------------------------------
# class 5: delivery drift
# --------------------------------------------------------------------------


def class5() -> list[Row]:
    import check_owui_preset_drift as drift

    if not drift._env("OWUI_API_KEY"):
        return [("5", "open-webui", "info", "no OWUI_API_KEY: nothing compared")]
    rows = []
    try:
        for ws, diffs in drift.check().items():
            rows += [("5", f"workspace {ws}", "open", d) for d in diffs]
        expected = drift.expected_personas()
        for p, diffs in drift.check_personas(expected=expected).items():
            rows += [("5", f"persona {p}", "open", d) for d in diffs]
        for p in drift.shadowed_personas(expected):
            rows.append(("5", f"persona {p}", "info", "slug is also a workspace id: never seeded"))
        req = urllib.request.Request(
            "http://localhost:8080/api/v1/models/export",
            headers={"Authorization": f"Bearer {drift._env('OWUI_API_KEY')}"},
        )
        data = json.load(urllib.request.urlopen(req, timeout=60))  # noqa: S310
        items = data if isinstance(data, list) else data.get("items") or data.get("data") or []
        source = {
            json.loads(f.read_text())["id"] for f in drift.WORKSPACES.glob("workspace_*.json")
        }
        source |= {e["id"] for e in expected}
        for m in items:
            if isinstance(m, dict) and m.get("id") not in source:
                rows.append(
                    ("5", f"preset {m.get('id')}", "orphan", f"no source file; {m.get('name')}")
                )
    except (urllib.error.URLError, OSError) as e:
        rows.append(("5", "open-webui", "info", f"unreachable: {e}"))
    return rows


# --------------------------------------------------------------------------


#: Findings reviewed and kept, with the reason. (class, subject regex) -> reason. A new hit is
#: open until someone reads it and adds a line here.
JUSTIFIED: list[tuple[str, str, str]] = [
    (
        "1",
        r"^auto-daily / ",
        "8192-token window: any prompt addition needs the S2 P-4 measurement first",
    ),
    (
        "1",
        r"^(auto-coding|auto-nemotron|auto-compliance) / read_",
        "document reading is incidental in a non-document lane; the tool description carries it",
    ),
    (
        "1",
        r"^(auto-coding::cad|bench-qwen3\d-cad|auto-coding) / (convert_cad|sandbox_status|execute_bash)",
        "self-describing utility tool in a lane whose prompt is about CAD or code",
    ),
    (
        "4",
        r"^auto-audio$",
        "conditioned on the transcription tools it follows: the URLs exist only after they ran",
    ),
    ("4", r"^auto-compliance$", "an output-format rule, not tied to a tool's output"),
    (
        "4",
        r"^auto-compliance::reading$",
        "a citations rule and a rule against writing tool syntax in prose; neither names a tool result",
    ),
]


def apply_justified(rows: list[Row]) -> list[Row]:
    out = []
    for c, subject, sev, detail in rows:
        why = next((w for cc, rx, w in JUSTIFIED if cc == c and re.search(rx, subject)), None)
        if why and sev in ("open", "review"):
            out.append((c, subject, "justified", f"{detail} | reason: {why}"))
        else:
            out.append((c, subject, "open" if sev == "review" else sev, detail))
    return out


CLASSES = {"1": class1, "2": class2, "3": class3, "4": class4, "5": class5}
TITLES = {
    "1": "tool not named in the prompt",
    "2": "manifest schema integrity",
    "3": "unknown-argument handling (live)",
    "4": "prompt cross-talk",
    "5": "delivery drift",
}


def render(rows: list[Row]) -> str:
    out = ["# WFE surface audit", "", "Generated by `scripts/wfe_surface_audit.py`.", ""]
    for c in sorted({r[0] for r in rows}):
        mine = [r for r in rows if r[0] == c]
        counts = Counter(r[2] for r in mine)
        out += [
            f"## Class {c}: {TITLES[c]}",
            "",
            "Counts: " + ", ".join(f"{k} {v}" for k, v in sorted(counts.items())),
            "",
        ]
        out += ["| subject | severity | detail |", "|---|---|---|"]
        for _, subject, sev, detail in sorted(mine, key=lambda r: (r[2] != "open", r[1])):
            out.append(f"| {subject} | {sev} | {detail.replace('|', '/')} |")
        out.append("")
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--classes", default="1,2,3,4,5")
    ap.add_argument(
        "--direct",
        action="store_true",
        help="class 3: call each MCP directly instead of through the pipeline",
    )
    ap.add_argument("--md", type=Path, help="write the full table here")
    a = ap.parse_args()
    rows: list[Row] = []
    for c in a.classes.split(","):
        rows += class3(a.direct) if c.strip() == "3" else CLASSES[c.strip()]()
    rows = apply_justified(rows)
    for c in sorted({r[0] for r in rows}):
        counts = Counter(r[2] for r in rows if r[0] == c)
        print(f"class {c} {TITLES[c]:40s}", dict(sorted(counts.items())))
    if a.md:
        a.md.write_text(render(rows))
        print(f"wrote {a.md}")
    return 1 if any(r[2] == "open" for r in rows) else 0


if __name__ == "__main__":
    os.chdir(REPO)
    sys.exit(main())
