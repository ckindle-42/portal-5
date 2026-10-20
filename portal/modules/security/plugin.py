"""Security module hooks for CLI registration and wiki seeders."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from portal.platform.plugins import module_code_present


def register_cli(app: Any) -> None:
    if not module_code_present("portal.modules.security.cli"):
        return
    from portal.modules.security.cli import register

    register(app)


def wiki_seeders() -> list[Callable[[bool], list[Any]]]:
    if not module_code_present("portal.modules.security.core"):
        return []
    from portal.modules.security.wiki_seed import (
        seed_dcsync_specifically,
        seed_technique_signatures,
    )

    def _signatures(dry_run: bool) -> list[Any]:
        return seed_technique_signatures(dry_run=dry_run)

    def _dcsync(dry_run: bool) -> list[Any]:
        unit = seed_dcsync_specifically(dry_run=dry_run)
        return [unit] if unit is not None else []

    return [_signatures, _dcsync]
