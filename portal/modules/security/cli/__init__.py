"""``portal security ...`` — CLI surface for the security module.

Slice 6 of BUILD-SPEC-PORTAL-MODULES-V1. This is a thin argv pass-through
to the existing portal.modules.security.core dispatcher (self-index,
stage2-propose, candidate-eval, compliance-report, and the full bench
argparse CLI as the default) rather than a reimplementation — the RBP
engine already owns real argument parsing for each of those; duplicating
it here as separate Typer subcommands would be new integration code for
no behavior change, and the spec's "bench, eval, coverage, report, grow"
naming doesn't map 1:1 onto existing entry points (run_growth_loop has no
standalone CLI wrapper today, for one). This keeps `portal security ...`
and `python3 -m portal.modules.security.core ...` behaving identically —
one surface, no drift.
"""

from __future__ import annotations

import runpy
import sys

import typer


def cmd_security(ctx: typer.Context) -> None:
    """Security module CLI — forwards to portal.modules.security.core
    (self-index, stage2-propose, candidate-eval, compliance-report, bench)."""
    argv = ctx.args
    sys.argv = ["portal-security", *argv]
    runpy.run_module("portal.modules.security.core", run_name="__main__")


def register(app: typer.Typer) -> None:
    app.command(
        "security",
        context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
    )(cmd_security)
