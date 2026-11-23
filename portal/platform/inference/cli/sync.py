"""``portal sync-config`` and ``portal docs build``."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Annotated

import typer

from ._apps import docs_app


def register(app: typer.Typer) -> None:
    """Attach top-level sync commands to the typer app."""
    app.command("sync-config")(sync_config)
    docs_app.command("build")(docs_build)


def sync_config(
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Show what would change without writing")
    ] = False,
) -> None:
    """Regenerate derived artifacts from config/portal.yaml.

    Produces:
      config/backends.yaml workspace_routing block
      .mcp.json (Claude Code MCP list)
      imports/openwebui/workspaces/workspace_*.json
      imports/openwebui/workspaces/workspaces_all.json

    Idempotent — safe to run after every edit to portal.yaml.
    """
    from portal.platform.inference.config_validate import validate_config

    _cfg_errors = validate_config()
    if _cfg_errors:
        import typer as _t

        _t.echo("config validation FAILED — refusing to regenerate artifacts:")
        for _e in _cfg_errors:
            _t.echo(f"  - {_e}")
        raise _t.Exit(code=1)

    from portal.platform.inference.sync_config import main as _sync_main

    if dry_run:
        typer.echo("sync-config: --dry-run (not yet implemented in sync_config)")
        typer.echo("  Run without --dry-run to apply changes.")
        raise typer.Exit(code=0)

    sys.exit(_sync_main())


def docs_build() -> None:
    """Build generated docs separately from runtime config artifacts."""
    root = Path(__file__).resolve().parents[4]
    from portal.platform.wiki.render import (
        render_admin_guide,
        render_all_generated_blocks,
        render_architecture_map,
    )

    updated = render_all_generated_blocks(root)
    output_dir = root / "docs" / "generated"
    render_admin_guide(output_dir)
    render_architecture_map(output_dir)
    typer.echo(f"docs build: {len(updated)} managed doc(s) updated; 2 generated views rendered")
