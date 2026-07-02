"""``portal models <cmd>`` — model registry operations."""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Annotated

import typer

from portal_pipeline.config import Model, load_portal_config

from ._apps import models_app
from ._common import _detect_ollama_cmd, _model_exists_in_ollama


def _pull_native(model: str, ollama_cmd: str) -> bool:
    """Pull a native Ollama registry model."""
    parts = ollama_cmd.split() + ["pull", model]
    typer.echo(f"  Pulling: {model}")
    try:
        subprocess.run(parts, check=True)
        return True
    except subprocess.CalledProcessError:
        return False


def _pull_hf_model(m: Model, ollama_cmd: str) -> bool:
    """Pull a HuggingFace model via Python API + ollama create."""

    actual_repo = m.actual_repo or m.hf_id
    filename = m.filename
    ollama_name = m.ollama_name
    gated = m.gated

    if not ollama_name:
        typer.echo(f"  ⚠️  Skipping {m.hf_id}: no ollama_name (too large for current hardware)")
        return True

    if not filename:
        typer.echo(f"  ⚠️  No filename for {m.hf_id} — attempting direct ollama pull")
        return _pull_native(f"hf.co/{actual_repo}", ollama_cmd)

    # Check if already in Ollama
    if _model_exists_in_ollama(ollama_name, ollama_cmd):
        typer.echo(f"  ✅ Already in Ollama as {ollama_name} — skipping")
        return True

    # Token check for gated repos
    if gated and not os.environ.get("HF_TOKEN"):
        typer.echo(f"  ❌ {actual_repo} requires HF_TOKEN (gated repo)")
        typer.echo(f"     1. Accept terms: https://huggingface.co/{actual_repo}")
        typer.echo("     2. Create token: https://huggingface.co/settings/tokens")
        typer.echo("     3. Add to .env:  HF_TOKEN=hf_...")
        return False

    # Download via Python
    try:
        from huggingface_hub import hf_hub_download  # noqa: PLC0415
    except ImportError:
        typer.echo("  Installing huggingface_hub...")
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "huggingface_hub>=0.28", "--quiet"],
            check=True,
        )

    typer.echo(f"  Fetching from HuggingFace: {actual_repo}")
    typer.echo(f"  File: {filename}")

    token = os.environ.get("HF_TOKEN") or None
    try:
        from huggingface_hub import hf_hub_download  # noqa: PLC0415

        gguf_path = hf_hub_download(
            repo_id=actual_repo,
            filename=filename,
            token=token,
        )
    except Exception as e:
        typer.echo(f"  ❌ Download failed: {e}")
        typer.echo("     Retry manually:")
        typer.echo(f"       hf hub download {actual_repo} {filename}")
        typer.echo(f"     Then import: ./launch.sh import-gguf <path> {ollama_name}")
        return False

    if not gguf_path or not Path(gguf_path).exists():
        typer.echo("  ❌ Download failed — file not found after download")
        return False

    typer.echo(f"  ✅ Ready: {Path(gguf_path).name}")

    # Import via ollama create
    typer.echo(f"  Importing as: {ollama_name}")
    import tempfile

    with tempfile.NamedTemporaryFile(mode="w", suffix=".modelfile", delete=False) as mf:
        mf.write(f"FROM {gguf_path}\nPARAMETER temperature 0.7\nPARAMETER num_ctx 8192\n")
        modelfile_path = mf.name

    try:
        parts = ollama_cmd.split() + ["create", ollama_name, "-f", modelfile_path]
        subprocess.run(parts, check=True)
        typer.echo(f"  ✅ Imported: {ollama_name}")
        return True
    except subprocess.CalledProcessError:
        typer.echo(f"  ❌ ollama create failed — GGUF kept at: {gguf_path}")
        return False
    finally:
        Path(modelfile_path).unlink(missing_ok=True)


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
    """Pull HuggingFace models into Ollama per config/portal.yaml models: block.

    Model definitions are read from config/portal.yaml.
    Native Ollama registry models use ``ollama pull`` directly.
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
    typer.echo("[portal-5] HuggingFace models: using hf hub download (bypasses Ollama auth issues)")
    typer.echo(
        "   For gated models, first accept terms at huggingface.co then set HF_TOKEN in .env\n"
    )

    total = len(targets)
    failed = 0
    for i, m in enumerate(targets, 1):
        typer.echo(f"[{i}/{total}] {m.hf_id}")
        if skip_gated and m.gated:
            typer.echo(f"  ⏭️  Skipping gated model: {m.hf_id}")
            continue
        ok = _pull_hf_model(m, ollama_cmd)
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
    in the rest of the file are untouched.
    """
    import re

    from portal_pipeline.config import PORTAL_YAML

    text = PORTAL_YAML.read_text()
    lines = text.splitlines(keepends=True)
    out: list[str] = []
    current_ws: str | None = None
    for line in lines:
        m = re.match(r"^  ([a-zA-Z0-9_-]+):\s*$", line)
        if m and not line.startswith("    "):
            current_ws = m.group(1)
        if current_ws in updates and re.match(r"^    model_hint:\s*\S", line):
            out.append(f"    model_hint: {updates[current_ws]}\n")
            current_ws = None  # only rewrite the first model_hint line per workspace
            continue
        out.append(line)
    PORTAL_YAML.write_text("".join(out))


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

    from portal_pipeline.config import get_workspace_dict, load_portal_config

    ollama_cmd = _detect_ollama_cmd()
    if ollama_cmd is None:
        typer.echo("ERROR: Ollama not reachable", err=True)
        raise typer.Exit(code=1)

    workspaces = get_workspace_dict(load_portal_config())
    typer.echo("Applying model params (ctx tags) ...")

    updates: dict[str, str] = {}
    created = skipped = failed = 0

    for ws_id, ws_cfg in workspaces.items():
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
            mf.write(f"FROM {base_model}\nPARAMETER num_ctx {ctx_limit}\n")
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
        result = subprocess.run(pull_cmd, check=False)
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
    from portal_pipeline.cli._common import cross_reference_workspaces_and_models

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
