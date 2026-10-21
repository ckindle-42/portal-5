"""Orchestration module hooks for CLI registration."""

from __future__ import annotations

from typing import Any

from portal.platform.plugins import module_code_present


def register_cli(app: Any) -> None:
    if not module_code_present("portal.modules.orchestration.cli"):
        return
    from portal.modules.orchestration.cli import register

    register(app)
