"""Portal 5 — Data & Analytics MCP (DuckDB).

Sandboxed, local-only conversational analytics. Attach tabular sources under a
data root, run SQL, profile, and persist named sessions across calls.

Port: 8939 (DATA_MCP_PORT or MCP_PORT env override).
"""

from __future__ import annotations

import contextlib
import logging
import os
import re
from collections import OrderedDict
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from mcp.server import MCPServer
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from portal.platform.data_loader import load_data

logger = logging.getLogger(__name__)
_port = int(os.environ.get("DATA_MCP_PORT") or os.environ.get("MCP_PORT", "8939"))
mcp = MCPServer(
    "data",
    instructions="Sandboxed local DuckDB conversational analytics — attach "
    "CSV/Parquet/JSON/xlsx under a data root, run SQL, profile columns, and persist a "
    "named session across calls. No external network; mutating/escape statements blocked.",
)

# MCPServer.custom_route() has no return annotation upstream (mcp SDK), so mypy
# sees its decorator result as Any and flags every routed handler with
# untyped-decorator. Bind the concrete decorator type once so handlers keep
# their annotations.
_route: Callable[
    ...,
    Callable[[Callable[..., Awaitable[Response]]], Callable[..., Awaitable[Response]]],
] = mcp.custom_route

_ROOT = Path(os.environ.get("DATA_MCP_ROOT", os.path.expanduser("~/AI_Output"))).resolve()
_SESS_DIR = Path(
    os.environ.get("DATA_MCP_SESSIONS", str(Path.home() / ".portal-data" / "sessions"))
)
_MAX_ROWS = int(os.environ.get("DATA_MCP_MAX_ROWS", "500"))
_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")
# Belt-and-braces denylist for a clean error message. The real guarantee is the
# query connection below, opened with enable_external_access=false: even a regex
# bypass cannot open an arbitrary path or re-enable filesystem access.
_BLOCKED = re.compile(
    r"\b(INSTALL|LOAD|ATTACH|DETACH|COPY|EXPORT|IMPORT|SET|RESET|PRAGMA|"
    r"read_csv|read_csv_auto|read_parquet|parquet_scan|read_json|read_json_auto|"
    r"read_ndjson|read_text|read_blob|glob|sniff_csv)\b",
    re.I,
)

# Memory bounds. DuckDB's default memory_limit is 80% of system RAM *per
# database*, and every session is its own database file; this server runs
# host-native (no container cap), so one large query could push the host into
# swap. SET is blocked in user SQL, so only the server moves these limits.
# Sorts, joins, windows and DISTINCT spill to disk under the cap and still
# succeed; only operators that build one huge value (list(), string_agg()) hit
# OutOfMemory. Those are retried automatically with more memory (see
# _with_headroom), so a caller never has to re-run with a bigger setting.
_MEMORY_LIMIT = os.environ.get("DATA_MCP_MEMORY_LIMIT", "4GB")  # starting cap per query
# Hard upper bound for automatic escalation; empty == half of physical RAM.
_MEMORY_CEILING = os.environ.get("DATA_MCP_MEMORY_CEILING", "")
_THREADS = int(os.environ.get("DATA_MCP_THREADS", "4"))
_MAX_CONNS = max(1, int(os.environ.get("DATA_MCP_MAX_CONNS", "4")))
_LIMITS = {"memory_limit": _MEMORY_LIMIT, "threads": _THREADS}
_SIZE = re.compile(r"^\s*([\d.]+)\s*([KMGT]I?B)?\s*$", re.I)
_UNITS = {
    "KB": 1e3,
    "MB": 1e6,
    "GB": 1e9,
    "TB": 1e12,
    "KIB": 2**10,
    "MIB": 2**20,
    "GIB": 2**30,
    "TIB": 2**40,
}

# session_id -> read-only-ish query duckdb connection, least recently used first
_conns: OrderedDict[str, Any] = OrderedDict()


def _duck() -> Any:
    import duckdb

    return duckdb


def _bytes(spec: str) -> int:
    m = _SIZE.match(spec)
    if not m:
        raise ValueError(f"bad memory size: {spec!r}")
    return int(float(m[1]) * _UNITS.get((m[2] or "").upper(), 1))


def _escalation_ceiling() -> int:
    """Most memory one query may take right now: the hard ceiling, but never
    more than 75% of what the host currently has available."""
    try:
        import psutil  # type: ignore[import-untyped]

        vm = psutil.virtual_memory()
        total, available = vm.total, vm.available
    except ImportError:
        total = os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")
        available = total
    hard = _bytes(_MEMORY_CEILING) if _MEMORY_CEILING else total // 2
    return int(min(hard, available * 0.75))


def _with_headroom(con: Any, work: Callable[[Any], Any]) -> tuple[Any, int]:
    """Run work(con). On DuckDB OutOfMemory, raise this connection's
    memory_limit 4x per step (bounded by _escalation_ceiling(), re-read each
    step) and run it again; restore the starting limit afterwards. Returns the
    result and the limit (bytes) it finally ran under."""
    import duckdb

    base = _bytes(str(_LIMITS["memory_limit"]))
    limit = base
    try:
        while True:
            try:
                return work(con), limit
            except duckdb.OutOfMemoryException as e:
                ceiling = _escalation_ceiling()
                if limit >= ceiling:
                    raise duckdb.OutOfMemoryException(
                        f"{e} [data-mcp: retried up to {limit / 1e9:.1f} GB; "
                        f"host can spare {ceiling / 1e9:.1f} GB right now]"
                    ) from e
                limit = min(limit * 4, ceiling)
                logger.warning("data-mcp: out of memory, retrying at %.1f GB", limit / 1e9)
                con.execute(f"SET memory_limit='{limit // 2**20}MiB'")
    finally:
        if limit != base:
            with contextlib.suppress(Exception):
                con.execute(f"SET memory_limit='{_LIMITS['memory_limit']}'")


def _resolve(path: str) -> Path:
    p = Path(path).resolve() if os.path.isabs(path) else (_ROOT / path).resolve()
    if p != _ROOT and _ROOT not in p.parents:
        raise ValueError(f"path escapes data root {_ROOT}: {path}")
    if not p.exists():
        raise FileNotFoundError(f"not found under data root: {path}")
    return p


def _db_path(session_id: str) -> str:
    if not _IDENT.match(session_id):
        raise ValueError(f"bad session id: {session_id!r}")
    _SESS_DIR.mkdir(parents=True, exist_ok=True)
    return str(_SESS_DIR / f"{session_id}.duckdb")


def _loader_conn(session_id: str) -> Any:
    """Short-lived connection WITH filesystem access — used only by attach_source
    to materialise a source file into a table, then closed."""
    return _duck().connect(_db_path(session_id), config=dict(_LIMITS))


def _conn(session_id: str) -> Any:
    """Cached query connection with filesystem access permanently disabled — the
    sandbox guarantee for run_sql / profile_table / list_session. DuckDB refuses
    to re-enable external access on a running database, so this cannot be undone
    from user SQL."""
    if session_id in _conns:
        _conns.move_to_end(session_id)
        return _conns[session_id]
    while len(_conns) >= _MAX_CONNS:
        _, old = _conns.popitem(last=False)
        with contextlib.suppress(Exception):
            old.close()
    _conns[session_id] = _duck().connect(
        _db_path(session_id), config={**_LIMITS, "enable_external_access": False}
    )
    return _conns[session_id]


@mcp.tool()
def attach_source(session_id: str, path: str, table: str) -> dict[str, Any]:
    """Attach a CSV/Parquet/JSON/xlsx file as a queryable table in a session.

    The source is read exactly once here, under a confined path, and materialised
    into a session table. `run_sql` then runs against a connection that has
    filesystem access permanently disabled, so it can never read the file (or any
    other path) again.
    """
    try:
        if not _IDENT.match(table):
            raise ValueError(f"bad table name: {table!r}")
        p = _resolve(path)
        # drop the sandboxed query connection so the loader can write the file
        old = _conns.pop(session_id, None)
        if old is not None:
            old.close()
        loader = _loader_conn(session_id)
        try:

            def load(c: Any) -> None:
                ext = p.suffix.lower()
                # p is resolved + confined under _ROOT; DuckDB cannot bind a prepared
                # parameter inside CREATE TABLE, so the path is quoted inline.
                lit = "'" + str(p).replace("'", "''") + "'"
                if ext in (".csv", ".tsv"):
                    c.execute(
                        f"CREATE OR REPLACE TABLE {table} AS SELECT * FROM read_csv_auto({lit})"
                    )
                elif ext in (".parquet", ".pq"):
                    c.execute(
                        f"CREATE OR REPLACE TABLE {table} AS SELECT * FROM read_parquet({lit})"
                    )
                elif ext == ".json":
                    c.execute(
                        f"CREATE OR REPLACE TABLE {table} AS SELECT * FROM read_json_auto({lit})"
                    )
                elif ext in (".xlsx", ".xls"):
                    import pandas as pd

                    df = pd.read_excel(p)
                    c.register("_src_df", df)
                    c.execute(f"CREATE OR REPLACE TABLE {table} AS SELECT * FROM _src_df")
                    c.unregister("_src_df")
                else:
                    raise ValueError(f"unsupported source type: {ext}")

            _with_headroom(loader, load)
        finally:
            loader.close()
        con = _conn(session_id)
        cols = con.execute(f"DESCRIBE {table}").fetchall()
        n = con.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
        return {
            "session_id": session_id,
            "table": table,
            "rows": n,
            "columns": [{"name": c[0], "type": c[1]} for c in cols],
        }
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)}


@mcp.tool()
def run_sql(session_id: str, sql: str, max_rows: int = _MAX_ROWS) -> dict[str, Any]:
    """Run a SQL query against the session. Mutating/escape statements are blocked."""
    try:
        if _BLOCKED.search(sql):
            return {
                "error": "statement blocked by sandbox policy (INSTALL/LOAD/ATTACH/COPY/EXPORT)"
            }
        cap = min(max_rows, _MAX_ROWS)

        def work(con: Any) -> tuple[list[str], list[Any]]:
            cur = con.execute(sql)
            cols = [d[0] for d in cur.description] if cur.description else []
            return cols, (cur.fetchmany(cap) if cols else [])

        (cols, rows), limit = _with_headroom(_conn(session_id), work)
        out = {
            "session_id": session_id,
            "columns": cols,
            "rows": [list(r) for r in rows],
            "row_count": len(rows),
            "truncated": len(rows) >= cap,
        }
        if limit != _bytes(str(_LIMITS["memory_limit"])):
            out["memory_limit_used_gb"] = round(limit / 1e9, 1)
        return out
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)}


@mcp.tool()
def profile_table(session_id: str, table: str) -> dict[str, Any]:
    """Per-column profile: type, null count, distinct count, min/max/mean for numerics."""
    try:
        if not _IDENT.match(table):
            raise ValueError("bad table name")
        con = _conn(session_id)
        cols = con.execute(f"DESCRIBE {table}").fetchall()
        prof = []
        for name, typ, *_ in cols:
            nulls = con.execute(f'SELECT count(*)-count("{name}") FROM {table}').fetchone()[0]
            distinct = con.execute(f'SELECT count(DISTINCT "{name}") FROM {table}').fetchone()[0]
            entry = {"column": name, "type": typ, "nulls": nulls, "distinct": distinct}
            if any(t in typ.upper() for t in ("INT", "DOUBLE", "DECIMAL", "FLOAT", "BIGINT")):
                mn, mx, avg = con.execute(
                    f'SELECT min("{name}"),max("{name}"),avg("{name}") FROM {table}'
                ).fetchone()
                entry.update(min=mn, max=mx, mean=avg)
            prof.append(entry)
        return {"session_id": session_id, "table": table, "profile": prof}
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)}


@mcp.tool()
def list_session(session_id: str) -> dict[str, Any]:
    """List tables/views currently in a session."""
    try:
        con = _conn(session_id)
        tables = [r[0] for r in con.execute("SHOW TABLES").fetchall()]
        return {"session_id": session_id, "tables": tables}
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)}


TOOLS_MANIFEST = load_data("config/inference", "tools_manifest_data_mcp")

_DISPATCH: dict[str, Any] = {
    "attach_source": attach_source,
    "run_sql": run_sql,
    "profile_table": profile_table,
    "list_session": list_session,
}


@_route("/health", methods=["GET"])
async def health_check(request: Request) -> JSONResponse:
    return JSONResponse({"status": "ok", "service": "data-mcp", "port": _port})


@_route("/ready", methods=["GET"])
async def ready(request: Request) -> JSONResponse:
    ok = True
    try:
        _duck()
    except Exception:  # noqa: BLE001
        ok = False
    return JSONResponse({"port": _port, "duckdb": ok, "root": str(_ROOT)})


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
