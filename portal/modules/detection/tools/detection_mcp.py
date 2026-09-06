"""Portal 5 — Detection-as-Code MCP.

Sigma conversion/validation (pySigma), YARA compile/scan (sandboxed), and a
promotion of the previously eval-siloed live SIEM search tools into a
first-class, read-only, lab-scoped surface. Unifies with — does not duplicate —
the detections_mcp SPL library (that stays for library search/validate).

Port: 8938 (DETECTION_MCP_PORT or MCP_PORT env override).
"""

from __future__ import annotations

import importlib
import logging
import os
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any, cast

from mcp.server import MCPServer
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from portal.platform.data_loader import load_data

logger = logging.getLogger(__name__)
_port = int(os.environ.get("DETECTION_MCP_PORT") or os.environ.get("MCP_PORT", "8938"))
mcp = MCPServer(
    "detection",
    instructions="Detection-as-code — pySigma conversion (Sigma -> SPL/Lucene/KQL) with "
    "validation, YARA compile/scan under a sandboxed root, and read-only lab-scoped live "
    "SIEM search (query_splunk / query_windows_events) promoted from the blue-eval harness.",
)

# MCPServer.custom_route() has no return annotation upstream (mcp SDK), so mypy
# sees its decorator result as Any and flags every routed handler with
# untyped-decorator. Bind the concrete decorator type once so handlers keep
# their annotations.
_route: Callable[
    ...,
    Callable[[Callable[..., Awaitable[Response]]], Callable[..., Awaitable[Response]]],
] = mcp.custom_route

_YARA_ROOT = Path(
    os.environ.get("DETECTION_YARA_ROOT", os.path.expanduser("~/AI_Output"))
).resolve()

# (module, class) per pySigma backend. Lazy-imported on first convert.
_BACKENDS = {
    "splunk": ("sigma.backends.splunk", "SplunkBackend"),
    "elasticsearch": ("sigma.backends.elasticsearch", "LuceneBackend"),
    "kql": ("sigma.backends.kusto", "KustoBackend"),
}


@mcp.tool()
def convert_sigma(sigma_yaml: str, target: str = "splunk") -> dict[str, Any]:
    """Convert a Sigma rule (YAML string) to a target backend query and validate it.

    target: 'splunk' (SPL) | 'elasticsearch' (Lucene) | 'kql' (Kusto/KQL).
    """
    try:
        from sigma.collection import SigmaCollection

        if target not in _BACKENDS:
            return {"error": f"unknown target {target}; have {sorted(_BACKENDS)}"}
        mod_name, cls_name = _BACKENDS[target]
        backend_cls = getattr(importlib.import_module(mod_name), cls_name)
        rules = SigmaCollection.from_yaml(sigma_yaml)  # parse == validation
        queries = backend_cls().convert(rules)
        return {
            "target": target,
            "valid": True,
            "queries": queries,
            "rule_count": len(rules.rules),
        }
    except Exception as e:  # noqa: BLE001
        return {"target": target, "valid": False, "error": str(e)}


@mcp.tool()
def validate_sigma(sigma_yaml: str) -> dict[str, Any]:
    """Validate a Sigma rule structurally (parse + pySigma) without converting."""
    try:
        from sigma.collection import SigmaCollection

        rules = SigmaCollection.from_yaml(sigma_yaml)
        return {
            "valid": True,
            "rule_count": len(rules.rules),
            "titles": [r.title for r in rules.rules],
        }
    except Exception as e:  # noqa: BLE001
        return {"valid": False, "error": str(e)}


@mcp.tool()
def compile_yara(rule_text: str) -> dict[str, Any]:
    """Compile a YARA rule string; return ok/errors (no scan)."""
    try:
        import yara

        yara.compile(source=rule_text)
        return {"valid": True}
    except Exception as e:  # noqa: BLE001
        return {"valid": False, "error": str(e)}


@mcp.tool()
def scan_yara(rule_text: str, target_path: str) -> dict[str, Any]:
    """Compile a YARA rule and scan a file under the sandboxed root; return matches."""
    try:
        import yara

        p = (
            Path(target_path).resolve()
            if os.path.isabs(target_path)
            else (_YARA_ROOT / target_path).resolve()
        )
        if p != _YARA_ROOT and _YARA_ROOT not in p.parents:
            return {"error": f"target escapes sandbox root {_YARA_ROOT}"}
        if not p.is_file():
            return {"error": f"not a file: {p}"}
        rules = yara.compile(source=rule_text)
        matches = rules.match(str(p))
        return {
            "target": str(p),
            "match_count": len(matches),
            "matches": [{"rule": m.rule, "tags": list(m.tags)} for m in matches],
        }
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)}


@mcp.tool()
def query_splunk(
    spl: str, earliest: str = "-24h", latest: str = "now", max_results: int = 100
) -> dict[str, Any]:
    """Run a read-only SPL search against the lab SIEM.

    Promoted from the blue-eval harness — reuses SplunkBackend's REST connection
    primitive and the same subsearch / pipe-command guardrails. Never writes.
    """
    try:
        from portal.modules.security.core.siem.spl_backend import (
            _EPISODE_PIPE_COMMANDS,
            SplunkBackend,
        )

        requested = (spl or "").strip()
        if any(tok in requested for tok in ("[", "]", "`", ";")):
            return {"error": "query rejected: subsearches and command separators are not allowed"}
        if requested.lower().startswith("search "):
            requested = requested[7:].strip()
        for segment in requested.split("|")[1:]:
            cmd = segment.strip().split(maxsplit=1)[0].lower() if segment.strip() else ""
            if cmd and cmd not in _EPISODE_PIPE_COMMANDS:
                return {"error": f"query rejected: pipeline command {cmd!r} is not allowed"}

        be = SplunkBackend()
        base = f"search index={be.index}"
        search = f"{base} | search {requested}" if requested else f"{base} | head {max_results}"
        rows = be._run_search(search, earliest, latest)[:max_results]
        return {
            "spl": search,
            "requested_spl": spl,
            "time_bounds": {"earliest": earliest, "latest": latest},
            "row_count": len(rows),
            "rows": rows,
        }
    except Exception as e:  # noqa: BLE001
        return {"error": f"live Splunk unavailable ({e}); requires the lab SIEM reachable"}


@mcp.tool()
def query_windows_events(
    event_ids: list[int] | None = None, max_records: int = 50
) -> dict[str, Any]:
    """Read-only Windows Security event-log query on the lab DC.

    Promoted from the blue-eval harness — reuses the lab exec primitive
    (`_lab_mcp_call`) and DC credentials; issues a single Get-WinEvent read.
    """
    try:
        # portal.modules.security.core._data binds the LAB_* coordinates and
        # the `_lab_mcp_call` exec primitive inside a try/except ImportError
        # (bench_lab_exec is only importable when the lab env is up), so mypy
        # treats them as conditionally-defined and not statically importable.
        # Access them defensively via the module — identical runtime result,
        # since _data always binds them (real import or synthetic fallback).
        from portal.modules.security.core import _data as _lab_data
        from portal.modules.security.core.siem.collect import (
            strip_nxc_line_prefix,
            unwrap_mcp_stdout,
        )

        lab_exec_available = cast(bool, getattr(_lab_data, "_LAB_EXEC_AVAILABLE", False))
        lab_dc = cast(str, getattr(_lab_data, "_LAB_DC", ""))
        lab_admin_pass = cast(str, getattr(_lab_data, "_LAB_ADMIN_PASS", ""))
        lab_mcp_call = cast(
            Callable[..., dict[str, Any]], getattr(_lab_data, "_lab_mcp_call", None)
        )

        if not (lab_exec_available and lab_dc):
            return {"error": "lab DC exec not available; requires the lab reachable"}
        ids = ",".join(str(int(e)) for e in (event_ids or [4624, 4625, 4688, 4768, 4769]))
        cap = max(1, min(int(max_records), 200))
        ps = (
            f"Get-WinEvent -FilterHashtable @{{LogName='Security';Id={ids}}} "
            f"-MaxEvents {cap} | Format-List Id,TimeCreated,Message"
        )
        code = f"nxc winrm {lab_dc} -u administrator -p '{lab_admin_pass}' -X \"{ps}\" 2>&1"
        r = lab_mcp_call(code, timeout=90)
        raw = strip_nxc_line_prefix(unwrap_mcp_stdout(r.get("output", "")))
        text = "\n".join(ln for ln in raw.splitlines() if not ln.lstrip().startswith("[*]"))[:16000]
        return {"dc": lab_dc, "event_ids": ids, "max_records": cap, "events": text}
    except Exception as e:  # noqa: BLE001
        return {"error": f"live DC unavailable ({e}); requires the lab reachable"}


TOOLS_MANIFEST = load_data("config/inference", "tools_manifest_detection_mcp")

_DISPATCH: dict[str, Any] = {
    "convert_sigma": convert_sigma,
    "validate_sigma": validate_sigma,
    "compile_yara": compile_yara,
    "scan_yara": scan_yara,
    "query_splunk": query_splunk,
    "query_windows_events": query_windows_events,
}


@_route("/health", methods=["GET"])
async def health_check(request: Request) -> JSONResponse:
    return JSONResponse({"status": "ok", "service": "detection-mcp", "port": _port})


@_route("/ready", methods=["GET"])
async def ready(request: Request) -> JSONResponse:
    caps: dict[str, bool] = {}
    for name, mod in (("pysigma", "sigma.collection"), ("yara", "yara")):
        try:
            importlib.import_module(mod)
            caps[name] = True
        except Exception:  # noqa: BLE001
            caps[name] = False
    return JSONResponse({"port": _port, "capabilities": caps})


@_route("/tools", methods=["GET"])
async def list_tools(request: Request) -> JSONResponse:
    return JSONResponse({"tools": TOOLS_MANIFEST})


@_route("/tools/{tool_name}", methods=["POST"])
async def invoke_tool(request: Request) -> JSONResponse:
    name = request.path_params.get("tool_name", "")
    fn = _DISPATCH.get(name)
    if fn is None:
        return JSONResponse({"error": f"unknown tool {name}"}, status_code=404)
    try:
        body = await request.json()
    except Exception:
        body = {}
    args = body.get("arguments", body) if isinstance(body, dict) else {}
    try:
        return JSONResponse(fn(**args))
    except TypeError as e:
        return JSONResponse({"error": f"bad params: {e}"}, status_code=400)


if __name__ == "__main__":
    mcp.run(transport="streamable-http", host="0.0.0.0", port=_port)
