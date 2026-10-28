"""``portal models <cmd>`` — model registry operations."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Annotated, Any

import typer

from portal.platform.inference.config import Model, load_portal_config

from ._apps import models_app
from ._common import _detect_ollama_cmd, _model_exists_in_ollama
from .model_refresh import (
    capturing_run,
    ctx_modelfile_text,
    execute_plan,
    hf_client,
    plan_for_catalog_model,
    streaming_run,
)


def _pull_native(model: str, ollama_cmd: str) -> bool:
    """Pull a native Ollama library tag. The tag is passed through unchanged."""
    from .model_refresh import pull_library

    typer.echo(f"  Pulling: {model}")
    result = pull_library(model, ollama_cmd, streaming_run)
    if not result.ok:
        typer.echo(f"  ❌ {result.message}", err=True)
    return result.ok


def _pull_hf_model(m: Model, ollama_cmd: str, *, force: bool = False) -> bool:
    """Import one catalog entry. ``hf.co`` tags are never plain-pulled."""
    if not m.ollama_name:
        typer.echo(f"  ⚠️  Skipping {m.hf_id}: no ollama_name (too large for current hardware)")
        return True

    plan = plan_for_catalog_model(m)
    if plan.action == "pull":
        return _pull_native(plan.tag, ollama_cmd)
    if plan.action == "skip":
        typer.echo(f"  ⚠️  {m.ollama_name}: {plan.reason}")
        return True

    repo = m.actual_repo or m.hf_id
    if m.gated and not os.environ.get("HF_TOKEN"):
        typer.echo(f"  ❌ {repo} requires HF_TOKEN (gated repo)")
        typer.echo(f"     1. Accept terms: https://huggingface.co/{repo}")
        typer.echo("     2. Create token: https://huggingface.co/settings/tokens")
        typer.echo("     3. Add to .env:  HF_TOKEN=hf_...")
        return False
    if not force and _model_exists_in_ollama(m.ollama_name, ollama_cmd):
        typer.echo(f"  ✅ Already in Ollama as {m.ollama_name} — skipping")
        return True

    dest = Path(tempfile.mkdtemp(prefix="portal5-gguf-"))
    with hf_client() as client:
        result = execute_plan(plan, ollama_cmd, runner=capturing_run, client=client, dest_dir=dest)
    if result.ok:
        shutil.rmtree(dest, ignore_errors=True)
        typer.echo(f"  ✅ Imported: {m.ollama_name}")
        return True
    typer.echo(f"  ❌ {result.message}", err=True)
    typer.echo(f"     kept: {dest}")
    return False


def _select_pull_targets(
    cfg_models: list[Model],
    requested_ids: list[str] | None,
    *,
    include_retired: bool,
    skip_gated: bool,
) -> list[Model]:
    """Resolve a pull-target list from the registry given user flags.

    Pure function. Used by ``models pull`` and by tests.
    """
    if requested_ids:
        wanted = set(requested_ids)
        targets = [m for m in cfg_models if m.hf_id in wanted or m.ollama_name in wanted]
    else:
        targets = list(cfg_models)
        if not include_retired:
            targets = [m for m in targets if not m.retired]
        targets = [m for m in targets if m.ollama_name]
    if skip_gated:
        targets = [m for m in targets if not m.gated]
    return targets


@models_app.command("pull")
def models_pull(
    model_ids: Annotated[
        list[str] | None,
        typer.Argument(
            help="hf_id or ollama_name from config/portal.yaml. Omit to pull all live entries."
        ),
    ] = None,
    force: Annotated[bool, typer.Option("--force", help="Re-pull even if present")] = False,
    skip_gated: Annotated[
        bool, typer.Option("--skip-gated", help="Skip models marked gated=true")
    ] = False,
    include_retired: Annotated[
        bool,
        typer.Option(
            "--include-retired", help="Include models marked retired=true (default skips)"
        ),
    ] = False,
) -> None:
    """Pull catalog entries into Ollama per config/portal.yaml models: block.

    A pinned GGUF (filename + sha256) is downloaded, verified, and created.
    An entry without that pin is reported and skipped. Library tags use
    ``ollama pull``.
    """
    cfg = load_portal_config()

    ollama_cmd = _detect_ollama_cmd()
    if ollama_cmd is None:
        typer.echo("No Ollama available. Run: ./launch.sh install-ollama", err=True)
        raise typer.Exit(code=1)

    # Select models from config
    targets = _select_pull_targets(
        cfg.models,
        model_ids,
        include_retired=include_retired,
        skip_gated=False,  # skip_gated is handled inline in the loop below
    )

    if not targets:
        typer.echo("No models to pull", err=True)
        raise typer.Exit(code=0)

    typer.echo("=== Portal 5: Pulling AI models ===")
    typer.echo("This may take 30-90 minutes depending on connection speed.\n")
    typer.echo("[portal-5] Pinned GGUF: download, verify sha256, ollama create")
    typer.echo("   Entries without filename+sha256 are skipped. Set HF_TOKEN for gated repos.\n")

    total = len(targets)
    failed = 0
    for i, m in enumerate(targets, 1):
        typer.echo(f"[{i}/{total}] {m.hf_id}")
        if skip_gated and m.gated:
            typer.echo(f"  ⏭️  Skipping gated model: {m.hf_id}")
            continue
        ok = _pull_hf_model(m, ollama_cmd, force=force)
        if ok:
            typer.echo("  ✅ Done")
        else:
            failed += 1
        typer.echo("")

    typer.echo(f"\n=== Pull complete: {total - failed}/{total} succeeded ===")
    if failed:
        raise typer.Exit(code=1)


@models_app.command("refresh")
def models_refresh() -> None:
    """Force re-pull of every currently-installed model.

    Shortcut for ``portal models pull --force --include-retired``.
    """
    models_pull(model_ids=None, force=True, skip_gated=False, include_retired=True)


@models_app.command("import-gguf")
def cmd_models_import_gguf(
    gguf_path: Annotated[Path, typer.Argument(help="Path to local .gguf file")],
    name: Annotated[str | None, typer.Option("--name", help="Ollama model name (tag)")] = None,
) -> None:
    """Import a local GGUF file into Ollama as a named model.

    Example:
        portal models import-gguf ~/Downloads/model.gguf --name my-model:q6_k
    """
    gguf_path = gguf_path.expanduser()
    if not gguf_path.is_file():
        typer.echo(f"GGUF file not found: {gguf_path}", err=True)
        raise typer.Exit(code=2)

    model_name = name or gguf_path.stem.lower().replace("_", "-")

    ollama_cmd = _detect_ollama_cmd()
    if ollama_cmd is None:
        typer.echo("No Ollama available. Run: ./launch.sh install-ollama", err=True)
        raise typer.Exit(code=1)

    typer.echo(f"[portal-5] Importing GGUF: {gguf_path}")
    typer.echo(f"           Ollama name:   {model_name}")

    import tempfile

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".Modelfile", delete=False, prefix="portal5_"
    ) as mf:
        mf.write(f"FROM {gguf_path}\nPARAMETER temperature 0.7\nPARAMETER num_ctx 8192\n")
        mf_path = mf.name

    parts = ollama_cmd.split() + ["create", model_name, "-f", mf_path]
    try:
        subprocess.run(parts, check=True)
        typer.echo(f"[portal-5] ✅ Imported: {model_name}")
        typer.echo(f"  Run it: ollama run {model_name}")
    except subprocess.CalledProcessError:
        typer.echo("[portal-5] ❌ Import failed. Check Ollama is running.")
        raise typer.Exit(code=1) from None
    finally:
        Path(mf_path).unlink(missing_ok=True)


_CTX_TAG_RE = re.compile(r"-ctx\d+k$")


def _strip_ctx_tag(model_hint: str) -> str:
    """Undo _derive_ctx_tag — recover the true base model name from a possibly
    already-tagged model_hint, so re-running apply-params after a context_limit
    change re-derives from the base rather than stacking -ctxNk-ctxMk suffixes."""
    name, sep, tag = model_hint.rpartition(":")
    if not sep:
        return model_hint
    tag = _CTX_TAG_RE.sub("", tag)
    return f"{name}:{tag}"


def _derive_ctx_tag(model_hint: str, ctx: int) -> str:
    """Derive a ctx-tagged Ollama model name, e.g. gemma4:26b-a4b-it-qat -> gemma4:26b-a4b-it-qat-ctx8k.

    Ollama tags allow only one colon (name:tag); the -ctxNk suffix is appended to
    the tag half, matching the convention router/lifespan.py's validator checks for.
    """
    base = _strip_ctx_tag(model_hint)
    name, sep, tag = base.rpartition(":")
    if not sep:
        name, tag = base, "latest"
    k = ctx // 1024
    return f"{name}:{tag}-ctx{k}k"


def _write_back_model_hints(updates: dict[str, str]) -> None:
    """Replace model_hint: <old> with model_hint: <new> for each targeted workspace
    in config/portal.yaml, in place, without disturbing formatting/comments elsewhere.
    Line-based (not a full YAML round-trip) so multi-line descriptions and comments
    in the rest of the file are untouched. A key `ws::variant` targets the
    variant's own model_hint (6-space variant key, 8-space model_hint).
    """
    import re

    from portal.platform.inference.config import PORTAL_YAML

    text = PORTAL_YAML.read_text()
    lines = text.splitlines(keepends=True)
    out: list[str] = []
    current_ws: str | None = None
    current_var: str | None = None
    in_variants = False
    done: set[str] = set()  # only rewrite the first model_hint line per target
    for line in lines:
        m = re.match(r"^  ([a-zA-Z0-9_-]+):\s*$", line)
        if m:
            current_ws, current_var, in_variants = m.group(1), None, False
        elif re.match(r"^    variants:\s*$", line):
            in_variants = True
        elif re.match(r"^    \S", line):
            in_variants, current_var = False, None
        elif in_variants and (mv := re.match(r"^      ([a-zA-Z0-9_.-]+):\s*$", line)):
            current_var = mv.group(1)
        key = f"{current_ws}::{current_var}" if current_var else current_ws
        indent = "        " if current_var else "    "
        if key in updates and key not in done and re.match(rf"^{indent}model_hint:\s*\S", line):
            out.append(f"{indent}model_hint: {updates[key]}\n")
            done.add(key)
            continue
        out.append(line)
    PORTAL_YAML.write_text("".join(out))


def _apply_params_targets(cfg: Any) -> dict[str, dict[str, Any]]:
    """Every seat apply-params sizes: base workspaces plus `ws::variant` for each
    variant with its own model_hint. Variants shallow-override their base (as the
    router resolves them); one without a model_hint serves the base's hint,
    which the base entry already handles."""
    from portal.platform.inference.config import get_workspace_dict

    workspaces = get_workspace_dict(cfg)
    targets: dict[str, dict[str, Any]] = dict(workspaces)
    for ws_id in workspaces:
        for var_id, var in cfg.workspaces[ws_id].variants.items():
            if var.get("model_hint"):
                targets[f"{ws_id}::{var_id}"] = {**workspaces[ws_id], **var}
    return targets


@models_app.command("apply-params")
def cmd_models_apply_params() -> None:
    """Bake each workspace's context_limit into a derived Ollama model tag and
    update model_hint to point at it.

    Ollama's OpenAI-compatible /v1/chat/completions endpoint (what the pipeline
    uses) ignores request-time options.num_ctx entirely — the only way to cap a
    model's context window on that endpoint is a PARAMETER num_ctx baked into the
    model at creation time. This command closes that loop: for every workspace
    with context_limit set, it creates <model>:<tag>-ctxNk (idempotent — reuses
    existing local layers, no re-download) and rewrites model_hint in
    config/portal.yaml to point at it. Workspaces without context_limit are left
    alone (protected only by the global OLLAMA_CONTEXT_LENGTH floor, if set).

    Run ./launch.sh sync-config after this to regenerate derived artifacts
    (backends.yaml workspace_routing, .mcp.json, OWUI presets) — CLAUDE.md §6.
    """
    import tempfile

    from portal.platform.inference.config import load_portal_config

    ollama_cmd = _detect_ollama_cmd()
    if ollama_cmd is None:
        typer.echo("ERROR: Ollama not reachable", err=True)
        raise typer.Exit(code=1)

    targets = _apply_params_targets(load_portal_config())
    typer.echo("Applying model params (ctx tags) ...")

    updates: dict[str, str] = {}
    created = skipped = failed = 0

    for ws_id, ws_cfg in targets.items():
        ctx_limit = ws_cfg.get("context_limit")
        model_hint = ws_cfg.get("model_hint", "")
        if not ctx_limit or not model_hint:
            continue

        base_model = _strip_ctx_tag(model_hint)
        derived = _derive_ctx_tag(model_hint, ctx_limit)

        if model_hint == derived:
            # Already pointing at the correctly-sized derived tag — nothing to do.
            continue

        if _model_exists_in_ollama(derived, ollama_cmd):
            updates[ws_id] = derived
            skipped += 1
            continue

        if not _model_exists_in_ollama(base_model, ollama_cmd):
            typer.echo(f"  SKIP {ws_id}: base model {base_model} not pulled locally")
            failed += 1
            continue

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".Modelfile", delete=False, prefix="portal5_ctx_"
        ) as mf:
            mf.write(ctx_modelfile_text(base_model, ctx_limit))
            mf_path = mf.name
        try:
            subprocess.run(
                ollama_cmd.split() + ["create", derived, "-f", mf_path],
                check=True,
                capture_output=True,
                text=True,
            )
            updates[ws_id] = derived
            created += 1
            typer.echo(f"  ✅ {ws_id}: {model_hint} -> {derived}")
        except subprocess.CalledProcessError as e:
            typer.echo(f"  ❌ {ws_id}: failed to create {derived}: {e.stderr}")
            failed += 1
        finally:
            Path(mf_path).unlink(missing_ok=True)

    if updates:
        _write_back_model_hints(updates)

    typer.echo(
        f"\napply-params: {created} created, {skipped} already tagged, "
        f"{failed} failed/skipped ({len(updates)} model_hint(s) updated in portal.yaml)"
    )
    if updates:
        typer.echo("Run './launch.sh sync-config' to regenerate derived artifacts.")


# ── models apply-mtp-drafts ───────────────────────────────────────────────────


@models_app.command("apply-mtp-drafts")
def cmd_models_apply_mtp_drafts() -> None:
    """Apply Multi-Token-Prediction draft settings for MTP-capable models.

    Wires Qwen3.6-27B MTP speculative-decoding A/B pairing.
    Graceful-skip if base or draft models are absent.
    """
    ollama_cmd = _detect_ollama_cmd()
    if ollama_cmd is None:
        typer.echo("ERROR: Ollama not reachable", err=True)
        raise typer.Exit(code=1)

    mtp_base = "qwen3.6:27b-q8_0"
    mtp_draft = "qwen3.6:27b-mtp-q4_K_M"
    mtp_created = "portal5/qwen3.6-27b-mtp:q8_0-drafted"

    typer.echo("apply-mtp-drafts: wiring Qwen3.6-27B MTP A/B pair ...")

    # Check base model
    show_cmd = ollama_cmd.split() + ["show", mtp_base]
    result = subprocess.run(show_cmd, capture_output=True, text=True)
    if result.returncode != 0:
        typer.echo(f"  SKIP — base model {mtp_base} not pulled.")
        typer.echo(f"  Run: ollama pull {mtp_base}")
        return

    # Pull draft if needed
    show_cmd = ollama_cmd.split() + ["show", mtp_draft]
    result = subprocess.run(show_cmd, capture_output=True, text=True)
    if result.returncode != 0:
        typer.echo(f"  Pulling draft model {mtp_draft} ...")
        pull_cmd = ollama_cmd.split() + ["pull", mtp_draft]
        result = subprocess.run(pull_cmd, check=False, text=True)
        if result.returncode != 0:
            typer.echo(f"  FAIL — could not pull {mtp_draft}", err=True)
            raise typer.Exit(code=1)

    # Get draft blob path
    modelfile_cmd = ollama_cmd.split() + ["show", mtp_draft, "--modelfile"]
    result = subprocess.run(modelfile_cmd, capture_output=True, text=True)
    draft_path = ""
    for line in result.stdout.splitlines():
        if line.startswith("FROM "):
            draft_path = line.split("FROM ", 1)[1].strip()
            break
    if not draft_path or not Path(draft_path).exists():
        typer.echo(
            f"  FAIL — could not resolve blob path for {mtp_draft}",
            err=True,
        )
        raise typer.Exit(code=1)
    typer.echo(f"  Draft blob: {draft_path}")

    # Create MTP model
    import tempfile

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".Modelfile", delete=False, prefix="portal5_mtp_"
    ) as mf:
        mf.write(f"FROM {mtp_base}\nDRAFT {draft_path}\n")
        mf_path = mf.name

    typer.echo("  Modelfile:")
    typer.echo(Path(mf_path).read_text().strip())
    typer.echo(f"  Creating {mtp_created} ...")

    create_cmd = ollama_cmd.split() + ["create", mtp_created, "-f", mf_path]
    result = subprocess.run(create_cmd, capture_output=True, text=True)
    exit_code = result.returncode
    Path(mf_path).unlink(missing_ok=True)

    typer.echo(result.stdout)
    if exit_code != 0:
        typer.echo(f"\n  DRAFT REJECTION (Ollama create failed, exit {exit_code}).")
        raise typer.Exit(code=1)

    typer.echo(f"\n  OK — {mtp_created} created.")


# ── models list ───────────────────────────────────────────────────────────────


@models_app.command("list")
def cmd_models_list(
    output_json: Annotated[
        bool, typer.Option("--json", help="Emit JSON instead of a table")
    ] = False,
    include_retired: Annotated[
        bool,
        typer.Option("--include-retired", help="Include retired entries (default hides them)"),
    ] = False,
) -> None:
    """Print the model registry from portal.yaml.

    Default: human-readable table, retired entries hidden.
    """
    cfg = load_portal_config()
    entries = cfg.models if include_retired else [m for m in cfg.models if not m.retired]

    if output_json:
        import json as _json

        typer.echo(_json.dumps([m.model_dump() for m in entries], indent=2))
        return

    if not entries:
        typer.echo("(no models)")
        return

    headers = ("ollama_name", "hf_id", "gated", "retired")
    rows = [
        (
            m.ollama_name,
            m.hf_id[:50] + "\u2026" if len(m.hf_id) > 50 else m.hf_id,
            "Y" if m.gated else "",
            "Y" if m.retired else "",
        )
        for m in entries
    ]
    widths = [max(len(str(r[i])) for r in (headers, *rows)) for i in range(len(headers))]
    fmt = "  ".join(f"{{:<{w}}}" for w in widths)
    typer.echo(fmt.format(*headers))
    typer.echo(fmt.format(*("-" * w for w in widths)))
    for row in rows:
        typer.echo(fmt.format(*row))
    typer.echo()
    typer.echo(
        f"{len(entries)} model(s)"
        + ("" if include_retired else " (use --include-retired to see all)")
    )


# ── models validate ───────────────────────────────────────────────────────────


@models_app.command("validate")
def cmd_models_validate(
    strict: Annotated[
        bool,
        typer.Option(
            "--strict", help="Exit 1 on unused-model warnings (default exits only on orphans)"
        ),
    ] = False,
) -> None:
    """Cross-check portal.yaml workspaces ↔ models registry.

    Hard errors (exit 1):
      - Workspace model_hint references a pullable name not in registry

    Soft warnings (exit 0 unless --strict):
      - Registered model has no workspace referencing it
    """
    from portal.platform.inference.cli._common import cross_reference_workspaces_and_models

    cfg = load_portal_config()
    report = cross_reference_workspaces_and_models(cfg)

    if report.orphan_hints:
        typer.echo("\u2717 Orphan workspace hints (must be in registry to be pullable):", err=True)
        for h in report.orphan_hints:
            typer.echo(f"    {h}", err=True)

    if report.unused_models:
        typer.echo("\u26a0 Unused registry entries (no workspace references these):")
        for n in report.unused_models:
            typer.echo(f"    {n}")
        typer.echo("  Consider marking retired=true if intentional.")

    if not report.orphan_hints and not report.unused_models:
        typer.echo("\u2713 portal.yaml is consistent")

    failed = bool(report.orphan_hints) or (strict and bool(report.unused_models))
    raise typer.Exit(code=1 if failed else 0)
