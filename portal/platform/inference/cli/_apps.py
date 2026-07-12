"""Shared typer app instances — no circular imports."""

from __future__ import annotations

import typer

config_app = typer.Typer(help="Config introspection commands.")
workspace_app = typer.Typer(help="Workspace operations.")
models_app = typer.Typer(help="Model registry operations.")
module_app = typer.Typer(help="Module enable/disable operations (M7 toggle layer).")
agent_app = typer.Typer(help="Agent loop operations (platform core).")
