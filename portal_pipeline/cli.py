"""portal CLI — typed entry point for Portal 5 operator commands.

Stage 2 of M5: high-logic commands from launch.sh are ported here one by one;
launch.sh delegates to ``portal <cmd>`` so there is one implementation.

Currently implemented:
- ``portal config show``   — print the resolved portal.yaml config as JSON

Usage:
    portal --help
    portal config show
"""

from __future__ import annotations

import json
from typing import Annotated

import typer

from portal_pipeline.config import load_portal_config

app = typer.Typer(
    name="portal",
    help="Portal 5 operator CLI — typed commands over the portal.yaml config.",
    no_args_is_help=True,
)

config_app = typer.Typer(help="Config introspection commands.")
app.add_typer(config_app, name="config")


@config_app.command("show")
def config_show(
    raw: Annotated[bool, typer.Option("--raw", help="Emit raw YAML values (no env override)")] = False,
) -> None:
    """Print the resolved portal.yaml config as pretty-printed JSON."""
    cfg = load_portal_config()
    data = {
        "ollama_url": cfg.ollama_url,
        "request_timeout": cfg.request_timeout,
        "workspaces": list(cfg.workspaces.keys()),
        "workspace_count": len(cfg.workspaces),
        "mcp_fleet_count": len(cfg.mcp_fleet),
        "mcp_fleet": [
            {
                "id": s.id,
                "name": s.name,
                "port": s.port,
                "expose_to_pipeline": s.expose_to_pipeline,
            }
            for s in cfg.mcp_fleet
        ],
    }
    typer.echo(json.dumps(data, indent=2))


def main() -> None:
    app()


if __name__ == "__main__":
    main()
