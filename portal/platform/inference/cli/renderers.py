"""``portal models apply-renderers`` — the renderer/parser repair the intake gate names.

The WFE intake gate (``tests/wfe/settings_audit.py`` ``audit_renderer_gate``)
refuses an installed tag whose RENDERER/PARSER are empty while
``config/ollama_modelfiles/renderers.yaml`` knows the pair for its
architecture. This command applies that fix: it rebuilds the tag IN PLACE
(same name, so config needs no change) from its own ``/api/show`` Modelfile
plus the table's pair, confirms renderer/parser/num_ctx by reading
``/api/show`` back, and under ``--probe`` keeps the change only when
``scripts/ollama_template_conformance_probe.py`` passes.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any

import typer
import yaml

from ._apps import models_app
from ._common import _detect_ollama_cmd

_ROOT = Path(__file__).resolve().parents[4]
RENDERERS_PATH = _ROOT / "config" / "ollama_modelfiles" / "renderers.yaml"
PROBE_SCRIPT = _ROOT / "scripts" / "ollama_template_conformance_probe.py"
OLLAMA = "http://localhost:11434"


@dataclass
class Row:
    """One tag's before/after line for the report table."""

    tag: str
    before: str
    after: str
    num_ctx: str
    status: str
    detail: str = ""


def _post(path: str, payload: dict[str, Any]) -> dict[str, Any]:
    req = urllib.request.Request(
        f"{OLLAMA}{path}",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return dict(json.load(r))


def _load_table() -> dict[str, Any]:
    """config/ollama_modelfiles/renderers.yaml ({} when unreadable)."""
    with RENDERERS_PATH.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _installed() -> list[str]:
    """Names from /api/tags — the tags a rebuild may target."""
    data = _post("/api/tags", {})
    models = data.get("models") or []
    return sorted({str(m["name"]) for m in models if isinstance(m, dict) and m.get("name")})


def _show(tag: str, shows: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """One cached /api/show per tag ({} when the tag has none)."""
    if tag not in shows:
        try:
            shows[tag] = dict(_post("/api/show", {"model": tag}))
        except Exception:
            shows[tag] = {}
    return shows[tag]


def _renderer_parser(show: dict[str, Any]) -> tuple[str, str]:
    """The RENDERER/PARSER a tag's modelfile bakes ('' when it carries none)."""
    ren = par = ""
    for line in str(show.get("modelfile") or "").splitlines():
        parts = line.split()
        if parts[:1] == ["RENDERER"] and len(parts) > 1:
            ren = parts[1]
        elif parts[:1] == ["PARSER"] and len(parts) > 1:
            par = parts[1]
    return ren, par


def _architecture(show: dict[str, Any]) -> str:
    info = show.get("model_info") or {}
    return str(info.get("general.architecture") or "") if isinstance(info, dict) else ""


def _baked_num_ctx(show: dict[str, Any]) -> int | None:
    """The baked PARAMETER num_ctx (None when the tag bakes none)."""
    for line in str(show.get("parameters") or "").splitlines():
        head, sep, value = line.strip().partition(" ")
        if head == "num_ctx" and sep and value.strip().isdigit():
            return int(value)
    return None


def _fmt_ctx(num_ctx: int | None) -> str:
    return str(num_ctx) if num_ctx is not None else "-"


def _gate_refusal(tag: str, show: dict[str, Any], table: dict[str, Any]) -> tuple[str, str] | None:
    """The (renderer, parser) the intake gate would refuse this tag for, else None.

    Mirrors tests/wfe/settings_audit._audit_renderer_missing: both directives
    empty, tag not under `allow`, and the table knows the architecture's pair."""
    ren, par = _renderer_parser(show)
    if ren or par or tag in (table.get("allow") or {}):
        return None
    entry = (table.get("renderers") or {}).get(_architecture(show)) or {}
    renderer, parser = str(entry.get("renderer") or ""), str(entry.get("parser") or "")
    return (renderer, parser) if renderer and parser else None


def _create(ollama_cmd: str, tag: str, modelfile_text: str) -> tuple[bool, str]:
    """`ollama create <tag>` from modelfile_text — True when the create succeeded."""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".Modelfile", delete=False, prefix="portal5_renderers_"
    ) as mf:
        mf.write(modelfile_text)
        path = mf.name
    try:
        result = subprocess.run(
            ollama_cmd.split() + ["create", tag, "-f", path],
            capture_output=True,
            text=True,
        )
    except OSError as exc:
        return False, str(exc)
    finally:
        Path(path).unlink(missing_ok=True)
    if result.returncode != 0:
        return False, (result.stderr or result.stdout or "").strip() or "ollama create failed"
    return True, ""


def _probe(tag: str) -> tuple[bool, str]:
    """scripts/ollama_template_conformance_probe.py <tag> — True on pass."""
    result = subprocess.run(
        [sys.executable, str(PROBE_SCRIPT), tag],
        capture_output=True,
        text=True,
    )
    return result.returncode == 0, (result.stdout + result.stderr).strip()


def _confirm(show: dict[str, Any], pair: tuple[str, str], num_ctx: int | None) -> tuple[bool, str]:
    """Read /api/show back: the pair is baked and num_ctx survived the rebuild."""
    if not show:
        return False, "/api/show unreadable after create"
    ren, par = _renderer_parser(show)
    if (ren, par) != pair:
        return False, f"RENDERER/PARSER {ren}/{par}, wanted {pair[0]}/{pair[1]}"
    after = _baked_num_ctx(show)
    if after != num_ctx:
        return False, f"num_ctx {_fmt_ctx(after)}, wanted {_fmt_ctx(num_ctx)}"
    return True, ""


def _restore(
    row: Row, tag: str, original: str, shows: dict[str, dict[str, Any]], ollama_cmd: str
) -> Row:
    """Put the tag back to its pre-change Modelfile after a failed keep."""
    ok, detail = _create(ollama_cmd, tag, original)
    if not ok:
        row.status = "failed"
        row.detail += f"; RESTORE FAILED: {detail}"
        return row
    shows.pop(tag, None)
    ren, par = _renderer_parser(_show(tag, shows))
    row.after = f"{ren}/{par}" if ren or par else "none"
    if ren or par:
        row.status = "failed"
        row.detail += "; restore left RENDERER/PARSER behind"
        return row
    row.status = "restored"
    return row


def _apply_one(
    tag: str,
    pair: tuple[str, str],
    show: dict[str, Any],
    shows: dict[str, dict[str, Any]],
    ollama_cmd: str,
    probe: bool,
) -> Row:
    """Rebuild `tag` in place from its current Modelfile plus `pair`, confirm, keep."""
    num_ctx = _baked_num_ctx(show)
    row = Row(tag, "none", "", _fmt_ctx(num_ctx), "failed")
    original = str(show.get("modelfile") or "")
    if not original:
        row.detail = "no Modelfile from /api/show"
        return row
    repaired = original.rstrip("\n") + f"\nRENDERER {pair[0]}\nPARSER {pair[1]}\n"
    ok, detail = _create(ollama_cmd, tag, repaired)
    if not ok:
        row.detail = f"ollama create failed: {detail}"
        return row
    shows.pop(tag, None)
    ok, detail = _confirm(_show(tag, shows), pair, num_ctx)
    if not ok:
        row.detail = f"rebuild did not confirm ({detail}); restoring"
        return _restore(row, tag, original, shows, ollama_cmd)
    row.after = f"{pair[0]}/{pair[1]}"
    if not probe:
        row.status = "applied"
        return row
    probe_ok, probe_out = _probe(tag)
    if probe_ok:
        row.status = "applied (probe pass)"
        return row
    row.detail = f"probe failed: {probe_out}"
    return _restore(row, tag, original, shows, ollama_cmd)


def _pass_row(tag: str, show: dict[str, Any], table: dict[str, Any]) -> Row:
    """Why the gate passes this tag — apply-renderers never touches it."""
    ren, par = _renderer_parser(show)
    num_ctx = _fmt_ctx(_baked_num_ctx(show))
    if ren or par:
        return Row(tag, f"{ren}/{par}", "-", num_ctx, "skipped", "gate passes: renderer present")
    if tag in (table.get("allow") or {}):
        return Row(tag, "none", "-", num_ctx, "skipped", "allow: entry — probe-verified setup")
    return Row(
        tag,
        "none",
        "-",
        num_ctx,
        "skipped",
        f"gate passes: no table entry for {_architecture(show) or 'unknown arch'}",
    )


def _process(
    tag: str,
    table: dict[str, Any],
    shows: dict[str, dict[str, Any]],
    installed: set[str],
    dry_run: bool,
    probe: bool,
    ollama_cmd: str,
) -> Row:
    """One selected tag → its report row (no create under --dry-run)."""
    if tag not in installed:
        return Row(tag, "-", "-", "-", "skipped", "not installed")
    show = _show(tag, shows)
    if not show:
        return Row(tag, "-", "-", "-", "skipped", "/api/show unreadable")
    refusal = _gate_refusal(tag, show, table)
    if refusal is None:
        return _pass_row(tag, show, table)
    if dry_run:
        return Row(
            tag,
            "none",
            f"{refusal[0]}/{refusal[1]} (would)",
            _fmt_ctx(_baked_num_ctx(show)),
            "would apply",
        )
    return _apply_one(tag, refusal, show, shows, ollama_cmd, probe)


def _print_rows(rows: list[Row], verbose: bool) -> None:
    shown = rows if verbose else [r for r in rows if r.status != "skipped"]
    if shown:
        headers = ("tag", "before", "after", "num_ctx", "result")
        cells = [(r.tag, r.before, r.after or "-", r.num_ctx, r.status) for r in shown]
        widths = [max(len(x[i]) for x in (headers, *cells)) for i in range(len(headers))]
        fmt = "  ".join(f"{{:<{w}}}" for w in widths)
        typer.echo(fmt.format(*headers))
        typer.echo(fmt.format(*("-" * w for w in widths)))
        for row in shown:
            typer.echo(fmt.format(row.tag, row.before, row.after or "-", row.num_ctx, row.status))
            if row.detail:
                typer.echo(f"    {row.detail}")
    skipped = sum(1 for r in rows if r.status == "skipped")
    if skipped and not verbose:
        typer.echo(f"({skipped} selected tag(s) pass the gate — untouched)")


@models_app.command("apply-renderers")
def cmd_models_apply_renderers(
    tag: Annotated[
        list[str] | None,
        typer.Option(
            "--tag",
            help="Installed tag to repair; repeat for several. Omit to select every "
            "installed tag the intake gate would refuse.",
        ),
    ] = None,
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Report what would change; write nothing.")
    ] = False,
    probe: Annotated[
        bool,
        typer.Option(
            "--probe",
            help="Keep a rebuild only when the conformance probe passes; otherwise "
            "restore the original Modelfile. A restored tag exits 1.",
        ),
    ] = False,
) -> None:
    """Apply the RENDERER/PARSER pair the intake gate refuses these tags for.

    Rebuilds each selected installed tag IN PLACE from its current /api/show
    Modelfile (FROM, every PARAMETER incl. num_ctx and stops, sampling) plus the
    renderers.yaml pair, then confirms renderer/parser/num_ctx. A tag the gate
    passes, an `allow:` entry and an unknown architecture are never touched.
    """
    ollama_cmd = _detect_ollama_cmd()
    if ollama_cmd is None:
        typer.echo("ERROR: Ollama not reachable", err=True)
        raise typer.Exit(code=1)
    table = _load_table()
    if not isinstance(table.get("renderers"), dict):
        typer.echo(f"ERROR: {RENDERERS_PATH} has no renderers: table", err=True)
        raise typer.Exit(code=2)
    if probe and dry_run:
        typer.echo("(--probe ignored with --dry-run — nothing is built)")
        probe = False
    shows: dict[str, dict[str, Any]] = {}
    try:
        installed = set(_installed())
    except Exception as exc:
        typer.echo(f"ERROR: /api/tags failed: {exc}", err=True)
        raise typer.Exit(code=1) from None
    selected = tag if tag else sorted(installed)
    rows = [_process(t, table, shows, installed, dry_run, probe, ollama_cmd) for t in selected]
    typer.echo(f"apply-renderers ({'dry-run' if dry_run else 'live'}):")
    _print_rows(rows, verbose=tag is not None)
    applied = sum(1 for r in rows if r.status.startswith("applied"))
    restored = sum(1 for r in rows if r.status == "restored")
    failed = sum(1 for r in rows if r.status == "failed")
    skipped = sum(1 for r in rows if r.status == "skipped")
    suffix = " — no changes written" if dry_run else ""
    typer.echo(
        f"apply-renderers: {applied} applied, {restored} restored, "
        f"{skipped} skipped, {failed} failed{suffix}"
    )
    if failed or restored:
        raise typer.Exit(code=1)
