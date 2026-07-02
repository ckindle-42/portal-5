"""``portal workspace <cmd>`` — workspace operations."""

from __future__ import annotations

import contextlib
import os
from pathlib import Path

import typer

from ._apps import workspace_app
from ._common import _fmt_size


@workspace_app.command("init")
def workspace_init() -> None:
    """Initialize ${AI_OUTPUT_DIR} structure (uploads + generated/*)."""
    ws_root = Path(os.environ.get("AI_OUTPUT_DIR", str(Path.home() / "AI_Output")))
    subdirs = [
        "uploads",
        "generated/transcripts",
        "generated/documents",
        "generated/images",
        "generated/videos",
        "generated/music",
        "generated/speech",
    ]
    for sub in subdirs:
        (ws_root / sub).mkdir(parents=True, exist_ok=True)
    with contextlib.suppress(OSError):
        ws_root.chmod(0o775)
    typer.echo("✅ Workspace structure created")
    typer.echo(f"   {ws_root}/")
    for sub in subdirs:
        typer.echo(f"   {ws_root / sub}/")


@workspace_app.command("status")
def workspace_status() -> None:
    """Print workspace state — paths, sizes, file counts."""
    ws_root = Path(os.environ.get("AI_OUTPUT_DIR", str(Path.home() / "AI_Output")))
    if not ws_root.exists():
        typer.echo(f"❌ Workspace not initialized at: {ws_root}", err=True)
        typer.echo("   Run: portal workspace init", err=True)
        raise typer.Exit(code=1)

    typer.echo(f"Workspace: {ws_root}")
    typer.echo("")
    typer.echo(f"{'Path':<30} {'Files':>10} {'Size':>10}")
    typer.echo(f"{'─' * 30} {'─' * 10} {'─' * 10}")

    dirs = [
        "uploads",
        "generated/transcripts",
        "generated/documents",
        "generated/images",
        "generated/videos",
        "generated/music",
        "generated/speech",
    ]
    for d in dirs:
        dp = ws_root / d
        if dp.exists():
            n = sum(1 for _ in dp.rglob("*") if _.is_file())
            s = sum(_.stat().st_size for _ in dp.rglob("*") if _.is_file())
            s_str = _fmt_size(s)
            typer.echo(f"{d:<30} {n:>10} {s_str:>10}")
    typer.echo("")

    total_s = sum(_.stat().st_size for _ in ws_root.rglob("*") if _.is_file())
    typer.echo(f"Total: {_fmt_size(total_s)}")


@workspace_app.command("show")
def workspace_show() -> None:
    """Show workspace mount paths (host + container)."""
    ws_root = Path(os.environ.get("AI_OUTPUT_DIR", str(Path.home() / "AI_Output")))
    typer.echo(f"Workspace root (host):     {ws_root}")
    typer.echo("Workspace root (container): /workspace")
    typer.echo(f"OWUI uploads (host):       {ws_root / 'uploads'}/")
    typer.echo("OWUI uploads (container):  /app/backend/data/uploads/")
    typer.echo("")
    typer.echo("Generated subdirs:")
    for cat in ["transcripts", "documents", "images", "videos", "music", "speech"]:
        typer.echo(f"  {cat}: {ws_root / 'generated' / cat}/")
