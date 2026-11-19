"""``portal trace-seed-rag`` — load real repo docs into the trace rag hop's KB.

Copies a small fixed set of ``docs/`` markdown into the RAG MCP's own KB
sources volume, then ingests it through the MCP's own ``kb_ingest`` (one
ingest path, never a second). ``rebuild=True`` on the dedicated kb id makes
every run produce the same KB: idempotent, safe to re-run.
"""

from __future__ import annotations

from pathlib import Path

import typer

from . import mcps
from .context import run_cmd

CONTAINER = "portal5-mcp-rag"
SOURCES_DIR = "/app/data/portal5_kb_sources"
KB_DIR = f"{SOURCES_DIR}/{mcps.SEED_KB}"
#: Real repo docs — small, operational, and on-topic for the hop's query.
CORPUS: tuple[str, ...] = (
    "ADMIN_GUIDE.md",
    "ALERTS.md",
    "BACKUP_RESTORE.md",
    "COMPLIANCE_FALLBACK_POLICY.md",
)


def doc(name: str) -> Path:
    """The repo doc backing one corpus file."""
    return Path(__file__).resolve().parents[5] / "docs" / name


def _copy_corpus() -> None:
    """Copy the corpus into the container's KB sources dir (docker cp overwrites)."""
    if not run_cmd(["docker", "exec", CONTAINER, "mkdir", "-p", KB_DIR]).ok:
        raise typer.BadParameter(f"cannot reach {CONTAINER}: is the stack up?")
    for name in CORPUS:
        source = doc(name)
        if not source.is_file():
            raise typer.BadParameter(f"missing repo doc docs/{name}")
        result = run_cmd(["docker", "cp", str(source), f"{CONTAINER}:{KB_DIR}/{name}"])
        if not result.ok:
            raise typer.BadParameter(f"copy failed for {name}: {result.error}")


def cmd_seed_rag() -> None:
    """Seed the trace rag hop's knowledge base from real repo docs (idempotent)."""
    _copy_corpus()
    payload = mcps.mcp_call(
        mcps.servers()["rag"],
        "kb_ingest",
        {"kb_id": mcps.SEED_KB, "source_dir": KB_DIR, "rebuild": True},
    )
    if "error" in payload:
        typer.echo(f"seed failed: {payload['error']}")
        raise typer.Exit(code=1)
    store = mcps.mcp_call(
        mcps.servers()["rag"],
        "kb_search",
        {"kb_id": mcps.SEED_KB, "query": mcps.RAG_QUERY, "top_k": 3},
    )
    sources = [str(row.get("source_file") or "") for row in store.get("results") or []]
    typer.echo(
        f"seeded {mcps.SEED_KB}: files={payload.get('files_ingested')} "
        f"chunks={payload.get('chunks_added')} pages={payload.get('pages_added')}"
    )
    typer.echo(f"kb_search '{mcps.RAG_QUERY}' top: {sources or 'none'}")
    if not sources:
        raise typer.Exit(code=1)


def register(app: typer.Typer) -> None:
    app.command("trace-seed-rag")(cmd_seed_rag)
