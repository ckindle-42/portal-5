"""``portal sync-config`` / ``portal sync-readme``."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Annotated

import typer


def register(app: typer.Typer) -> None:
    """Attach top-level sync commands to the typer app."""
    app.command("sync-config")(sync_config)
    app.command("sync-readme")(sync_readme)


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

    Idempotent — safe to run after every edit to portal.yaml.
    """
    from portal_pipeline.sync_config import main as _sync_main

    if dry_run:
        typer.echo("sync-config: --dry-run (not yet implemented in sync_config)")
        typer.echo("  Run without --dry-run to apply changes.")
        raise typer.Exit(code=0)

    sys.exit(_sync_main())


def sync_readme(
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Show what would change without writing")
    ] = False,
) -> None:
    """Refresh README.md acceptance-testing section from ACCEPTANCE_RESULTS.md."""
    repo_root = Path(__file__).resolve().parent.parent
    results_path = repo_root / "ACCEPTANCE_RESULTS.md"
    readme_path = repo_root / "README.md"

    if not results_path.exists():
        typer.echo(
            "No ACCEPTANCE_RESULTS.md to sync from. Run acceptance tests first:"
            "\n  python3 tests/portal5_acceptance_v6.py",
            err=True,
        )
        raise typer.Exit(code=1)

    import re as _re

    results = results_path.read_text()
    readme = readme_path.read_text()

    summary_match = _re.search(r"(## Summary.*?)(?=## Results)", results, _re.DOTALL)
    summary_block = (
        summary_match.group(1).strip() if summary_match else "*(see ACCEPTANCE_RESULTS.md)*"
    )
    date_match = _re.search(r"\*\*Date:\*\*\s*([^\n]+)", results)
    date_str = date_match.group(1).strip() if date_match else "unknown"

    new_block = (
        "### Acceptance Testing\n\n"
        "The full acceptance test suite (`tests/portal5_acceptance_v6.py`) runs\n"
        "~250 checks across 30 sections. Run with:\n\n"
        "```bash\n"
        "python3 tests/portal5_acceptance_v6.py\n"
        "python3 tests/portal5_acceptance_v6.py --section S70\n"
        "```\n\n"
        f"Latest run ({date_str}):\n\n{summary_block}\n\n"
        "See [ACCEPTANCE_RESULTS.md](ACCEPTANCE_RESULTS.md) for full results.\n"
    )

    new_readme = _re.sub(
        r"### Acceptance Testing.*?(?=\n## |\n### |\Z)",
        new_block,
        readme,
        count=1,
        flags=_re.DOTALL,
    )

    if new_readme == readme:
        typer.echo("README.md: no '### Acceptance Testing' section found — nothing to update.")
        return
    if dry_run:
        typer.echo("[dry-run] README.md acceptance section would be refreshed.")
        return
    readme_path.write_text(new_readme)
    typer.echo("README.md acceptance section refreshed.")
