"""Portal 5 — Data & Analytics MCP (DuckDB).

Sandboxed, local-only conversational analytics. Attach tabular sources under a
data root, run SQL, profile, and persist named sessions across calls.

Port: 8939 (DATA_MCP_PORT or MCP_PORT env override).
"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path

from mcp.server import MCPServer
from starlette.responses import JSONResponse

from portal.platform.data_loader import load_data

logger = logging.getLogger(__name__)
_port = int(os.environ.get("DATA_MCP_PORT") or os.environ.get("MCP_PORT", "8939"))
mcp = MCPServer(
    "data",
    instructions="Sandboxed local DuckDB conversational analytics — attach "
    "CSV/Parquet/JSON/xlsx under a data root, run SQL, profile columns, and persist a "
    "named session across calls. No external network; mutating/escape statements blocked.",
)

_ROOT = Path(os.environ.get("DATA_MCP_ROOT", os.path.expanduser("~/AI_Output"))).resolve()
_SESS_DIR = Path(
    os.environ.get("DATA_MCP_SESSIONS", str(Path.home() / ".portal-data" / "sessions"))
)
_MAX_ROWS = int(os.environ.get("DATA_MCP_MAX_ROWS", "500"))
_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")
# statements that mutate the host / escape the sandbox — blocked outright
_BLOCKED = re.compile(r"\b(INSTALL|LOAD|ATTACH|COPY|EXPORT|PRAGMA\s+enable_external)\b", re.I)

_conns: dict = {}  # session_id -> duckdb connection


def _duck():
    import duckdb

    return duckdb


def _resolve(path: str) -> Path:
    p = Path(path).resolve() if os.path.isabs(path) else (_ROOT / path).resolve()
    if p != _ROOT and _ROOT not in p.parents:
        raise ValueError(f"path escapes data root {_ROOT}: {path}")
    if not p.exists():
        raise FileNotFoundError(f"not found under data root: {path}")
    return p


def _conn(session_id: str):
    if not _IDENT.match(session_id):
        raise ValueError(f"bad session id: {session_id!r}")
    if session_id not in _conns:
        _SESS_DIR.mkdir(parents=True, exist_ok=True)
        _conns[session_id] = _duck().connect(str(_SESS_DIR / f"{session_id}.duckdb"))
    return _conns[session_id]


@mcp.tool()
def attach_source(session_id: str, path: str, table: str) -> dict:
    """Attach a CSV/Parquet/JSON/xlsx file as a queryable table in a session (read-only view)."""
    try:
        if not _IDENT.match(table):
            raise ValueError(f"bad table name: {table!r}")
        p = _resolve(path)
        con = _conn(session_id)
        ext = p.suffix.lower()
        # p is a resolved path already confined under _ROOT; DuckDB cannot bind a
        # prepared parameter inside CREATE VIEW, so the path is quoted inline.
        lit = "'" + str(p).replace("'", "''") + "'"
        if ext in (".csv", ".tsv"):
            con.execute(f"CREATE OR REPLACE VIEW {table} AS SELECT * FROM read_csv_auto({lit})")
        elif ext in (".parquet", ".pq"):
            con.execute(f"CREATE OR REPLACE VIEW {table} AS SELECT * FROM read_parquet({lit})")
        elif ext == ".json":
            con.execute(f"CREATE OR REPLACE VIEW {table} AS SELECT * FROM read_json_auto({lit})")
        elif ext in (".xlsx", ".xls"):
            import pandas as pd  # xlsx via pandas -> duckdb register

            con.register(f"_{table}_df", pd.read_excel(p))
            con.execute(f"CREATE OR REPLACE VIEW {table} AS SELECT * FROM _{table}_df")
        else:
            raise ValueError(f"unsupported source type: {ext}")
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
def run_sql(session_id: str, sql: str, max_rows: int = _MAX_ROWS) -> dict:
    """Run a SQL query against the session. Mutating/escape statements are blocked."""
    try:
        if _BLOCKED.search(sql):
            return {
                "error": "statement blocked by sandbox policy (INSTALL/LOAD/ATTACH/COPY/EXPORT)"
            }
        con = _conn(session_id)
        cur = con.execute(sql)
        cols = [d[0] for d in cur.description] if cur.description else []
        cap = min(max_rows, _MAX_ROWS)
        rows = cur.fetchmany(cap) if cols else []
        return {
            "session_id": session_id,
            "columns": cols,
            "rows": [list(r) for r in rows],
            "row_count": len(rows),
            "truncated": len(rows) >= cap,
        }
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)}


@mcp.tool()
def profile_table(session_id: str, table: str) -> dict:
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
def list_session(session_id: str) -> dict:
    """List tables/views currently in a session."""
    try:
        con = _conn(session_id)
        tables = [r[0] for r in con.execute("SHOW TABLES").fetchall()]
        return {"session_id": session_id, "tables": tables}
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)}


TOOLS_MANIFEST = load_data("config/inference", "tools_manifest_data_mcp")

_DISPATCH = {
    "attach_source": attach_source,
    "run_sql": run_sql,
    "profile_table": profile_table,
    "list_session": list_session,
}


@mcp.custom_route("/health", methods=["GET"])
async def health_check(request):
    return JSONResponse({"status": "ok", "service": "data-mcp", "port": _port})


@mcp.custom_route("/ready", methods=["GET"])
async def ready(request):
    ok = True
    try:
        _duck()
    except Exception:  # noqa: BLE001
        ok = False
    return JSONResponse({"port": _port, "duckdb": ok, "root": str(_ROOT)})


@mcp.custom_route("/tools", methods=["GET"])
async def list_tools(request):
    return JSONResponse({"tools": TOOLS_MANIFEST})


@mcp.custom_route("/tools/{tool_name}", methods=["POST"])
async def invoke_tool(request):
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
