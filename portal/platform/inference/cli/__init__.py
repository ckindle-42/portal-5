"""Portal 5 typed operator CLI.

Each sub-module registers commands on typer apps from _apps.py.
Modules with top-level commands export a register(app) function.
"""

from __future__ import annotations

import typer

from ._apps import config_app, models_app, workspace_app

app = typer.Typer(
    name="portal",
    help="Portal 5 operator CLI — typed commands over the portal.yaml config.",
    no_args_is_help=True,
)

app.add_typer(config_app, name="config")
app.add_typer(workspace_app, name="workspace")
app.add_typer(models_app, name="models")

from . import config, models, workspace  # noqa: E402, F401
from . import smoke as _smoke  # noqa: E402
from . import sync as _sync  # noqa: E402
from . import update as _update  # noqa: E402

_sync.register(app)
_smoke.register(app)
_update.register(app)
