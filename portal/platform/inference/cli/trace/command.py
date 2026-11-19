"""``portal trace`` — a read-only, hop-by-hop check of the running system."""

from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path
from typing import Annotated, Any

import typer

from . import containers, engines, host, lab, music, owui, pins, workspaces
from .context import TraceContext, env_value, host_url, run_cmd
from .model import Hop, Section, Status, TraceReport, render_json, render_text

Runner = Callable[[TraceContext, dict[str, Any]], list[Hop]]


def _host(ctx: TraceContext, portal: dict[str, Any]) -> list[Hop]:
    return host.run(ctx.repo_root)


def _containers(ctx: TraceContext, portal: dict[str, Any]) -> list[Hop]:
    return containers.run(ctx)


def _workspaces(ctx: TraceContext, portal: dict[str, Any]) -> list[Hop]:
    return workspaces.run(ctx, portal)


def _pins(ctx: TraceContext, portal: dict[str, Any]) -> list[Hop]:
    return pins.run(ctx, portal)


def _engines(ctx: TraceContext, portal: dict[str, Any]) -> list[Hop]:
    return engines.run(ctx)


def _lab(ctx: TraceContext, portal: dict[str, Any]) -> list[Hop]:
    return lab.run()


SECTION_RUNNERS: tuple[tuple[str, str, Runner], ...] = (
    ("host", "HOST SERVICES", _host),
    ("containers", "CONTAINERS", _containers),
    ("workspaces", "WORKSPACES END TO END", _workspaces),
    ("pins", "PINS AND ALIASES", _pins),
    ("aliases", "DEPRECATED ALIASES", lambda ctx, portal: pins.alias_hops(ctx, portal)),
    ("engines", "ENGINES", _engines),
    ("owui", "OPEN WEBUI TOOL PATH", lambda ctx, portal: owui.run(ctx, portal)),
    ("lab", "LAB PATHS", _lab),
    ("music", "MUSIC ARTIFACT", lambda ctx, portal: music.run(ctx, portal)),
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[5]


def _context(repo_root: Path, budget: float, timeout: float) -> TraceContext:
    return TraceContext(
        repo_root=repo_root,
        pipeline_url=host_url(
            "PIPELINE_URL", "http://127.0.0.1:9099", "PORTAL_REVIEW_PIPELINE_URL"
        ),
        api_key=env_value("PIPELINE_API_KEY"),
        omlx_url=host_url("OMLX_URL", "http://127.0.0.1:8085", "PORTAL_REVIEW_OMLX_URL"),
        ollama_url=host_url("OLLAMA_URL", "http://127.0.0.1:11434", "PORTAL_REVIEW_OLLAMA_URL"),
        owui_url=host_url("OWUI_URL", "http://127.0.0.1:8080"),
        budget_s=budget,
        timeout_s=timeout,
    )


def _head(repo_root: Path) -> str:
    return run_cmd(["git", "-C", str(repo_root), "rev-parse", "--short", "HEAD"]).stdout.strip()


def selected(sections: list[str] | None) -> list[tuple[str, str, Runner]]:
    """Resolve ``--section`` keys (or 1-based section numbers, or key prefixes)."""
    if not sections:
        return list(SECTION_RUNNERS)
    wanted: set[str] = set()
    for raw in sections:
        token = raw.strip().lower()
        match = next(
            (
                key
                for index, (key, _title, _run) in enumerate(SECTION_RUNNERS, start=1)
                if token in (key, str(index)) or key.startswith(token)
            ),
            None,
        )
        if match is None:
            choices = ", ".join(key for key, _title, _run in SECTION_RUNNERS)
            raise typer.BadParameter(f"unknown section {raw!r}; choose one of: {choices}")
        wanted.add(match)
    return [entry for entry in SECTION_RUNNERS if entry[0] in wanted]


def _portal_config(repo_root: Path) -> dict[str, Any]:
    import yaml

    data = yaml.safe_load((repo_root / "config" / "portal.yaml").read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def cmd_trace(
    section: Annotated[
        list[str] | None,
        typer.Option(
            "--section",
            "-s",
            help="Run one section: host, containers, workspaces, "
            "pins, aliases, engines, owui, lab, music (or its number). Repeatable.",
        ),
    ] = None,
    json_output: Annotated[bool, typer.Option("--json", help="Emit the report as JSON")] = False,
    budget: Annotated[
        float, typer.Option("--budget", help="Seconds the workspace sweep may spend in total")
    ] = 900.0,
    timeout: Annotated[
        float, typer.Option("--timeout", help="Seconds one live request may take")
    ] = 180.0,
) -> None:
    """Check every hop from host services to the lab against the running system (read-only)."""
    repo_root = _repo_root()
    ctx = _context(repo_root, budget, timeout)
    started = time.monotonic()
    sections: list[Section] = []
    portal: dict[str, Any] = {}
    for key, title, runner in selected(section):
        if key in ("workspaces", "pins", "aliases", "music") and not portal:
            portal = _portal_config(repo_root)
        try:
            hops = runner(ctx, portal)
        except Exception as exc:  # noqa: BLE001 - reported as a hop, not silently skipped
            hops = [Hop(key, Status.FAIL, f"{type(exc).__name__}: {exc}", "section completes")]
        sections.append(Section(key, title, hops))
    report = TraceReport(sections, time.monotonic() - started, _head(repo_root))
    typer.echo(render_json(report) if json_output else render_text(report))
    if not report.ok:
        raise typer.Exit(code=1)


def register(app: typer.Typer) -> None:
    app.command("trace")(cmd_trace)
