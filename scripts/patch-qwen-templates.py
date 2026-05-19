#!/usr/bin/env python3
"""Patch Qwen 3.5 / 3.6 chat templates in MLX model directories.

Reads `mlx_models[].chat_template_override` from config/backends.yaml. For
each model with override set, locates the model directory and replaces its
`chat_template.jinja` (and the `chat_template` field inside
`tokenizer_config.json` when present) with the vendored template at
`config/chat_templates/<family>/chat_template.jinja`.

The original files are backed up to `*.portal5-backup`. Re-running this script
is a no-op when the vendored template is already installed (idempotent).
Re-running after a `huggingface-cli download` that overwrote the patch restores
it automatically.

Per the additive-only policy: backups are never deleted. Revert any single
model via `--rollback <model_id>`.

Usage:
    ./scripts/patch-qwen-templates.py             # patch all configured models
    ./scripts/patch-qwen-templates.py --dry-run   # print plan, no disk writes
    ./scripts/patch-qwen-templates.py --rollback huihui-ai/Huihui-Qwen3.5-9B-abliterated-mlx-4bit
    ./scripts/patch-qwen-templates.py --refetch   # re-download templates from upstream
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import urllib.request
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent
TPL_DIR = REPO / "config" / "chat_templates"
BACKENDS_YAML = REPO / "config" / "backends.yaml"

UPSTREAM_COMMIT = "1ed82f474a5d698d98a6a4aa5470948d60a79fe6"
UPSTREAM_BASE = (
    f"https://huggingface.co/froggeric/Qwen-Fixed-Chat-Templates"
    f"/resolve/{UPSTREAM_COMMIT}"
)

VALID_FAMILIES = {"qwen3.5", "qwen3.6"}

MLX_MODELS_DIR = Path("/Volumes/data01/models")
HF_CACHE = Path.home() / ".cache" / "huggingface" / "hub"


def _model_dirs() -> list[Path]:
    return [p for p in (MLX_MODELS_DIR, HF_CACHE) if p.exists()]


def _find_model_dir(model_id: str) -> Path | None:
    for root in _model_dirs():
        direct = root / model_id
        if direct.is_dir():
            return direct
        cache_name = "models--" + model_id.replace("/", "--")
        cache_dir = root / cache_name / "snapshots"
        if cache_dir.is_dir():
            snaps = sorted(cache_dir.iterdir())
            if snaps:
                return snaps[-1]
    return None


def _vendored_template(family: str) -> Path:
    p = TPL_DIR / family / "chat_template.jinja"
    if not p.exists():
        raise SystemExit(f"FAIL: vendored template missing at {p}; run --refetch first")
    return p


def _read_overrides() -> list[tuple[str, str]]:
    cfg = yaml.safe_load(BACKENDS_YAML.read_text())
    out = []
    for be in cfg.get("backends", []):
        if be.get("type") != "mlx":
            continue
        for m in be.get("mlx_models", []):
            fam = m.get("chat_template_override")
            if fam:
                if fam not in VALID_FAMILIES:
                    print(
                        f"WARN: model {m['id']} has unrecognized "
                        f"chat_template_override={fam!r}",
                        file=sys.stderr,
                    )
                    continue
                out.append((m["id"], fam))
    return out


def _sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _verify_manifest() -> None:
    manifest = TPL_DIR / "SHA256SUMS"
    if not manifest.exists():
        raise SystemExit(f"FAIL: {manifest} missing")
    for line in manifest.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        expected, rel = line.split(None, 1)
        actual = _sha256(TPL_DIR / rel)
        if actual != expected:
            raise SystemExit(
                f"FAIL: SHA mismatch for {rel}\n"
                f"  expected: {expected}\n"
                f"  actual:   {actual}\n"
                f"  Run --refetch to repair, or restore the file from git."
            )


def _patch_model(model_id: str, family: str, dry_run: bool) -> str:
    model_dir = _find_model_dir(model_id)
    if model_dir is None:
        return f"SKIP {model_id}: not found on disk"

    target = model_dir / "chat_template.jinja"
    backup = model_dir / "chat_template.jinja.portal5-backup"
    vendored = _vendored_template(family)
    vendored_sha = _sha256(vendored)

    if target.exists() and _sha256(target) == vendored_sha:
        return f"NOOP {model_id}: already patched ({family})"

    if dry_run:
        return f"PLAN {model_id}: would install {family} template at {target}"

    if target.exists() and not backup.exists():
        shutil.copy2(target, backup)

    shutil.copy2(vendored, target)

    tok_cfg = model_dir / "tokenizer_config.json"
    if tok_cfg.exists():
        try:
            data = json.loads(tok_cfg.read_text())
            if isinstance(data.get("chat_template"), str):
                tok_backup = model_dir / "tokenizer_config.json.portal5-backup"
                if not tok_backup.exists():
                    shutil.copy2(tok_cfg, tok_backup)
                data["chat_template"] = vendored.read_text()
                tok_cfg.write_text(json.dumps(data, indent=2))
        except Exception as e:
            print(
                f"WARN {model_id}: tokenizer_config.json update skipped: {e}",
                file=sys.stderr,
            )

    return f"PATCH {model_id}: installed {family} template"


def _rollback_model(model_id: str, dry_run: bool) -> str:
    model_dir = _find_model_dir(model_id)
    if model_dir is None:
        return f"SKIP {model_id}: not found on disk"

    backup = model_dir / "chat_template.jinja.portal5-backup"
    target = model_dir / "chat_template.jinja"
    if not backup.exists():
        return f"SKIP {model_id}: no .portal5-backup present"

    if dry_run:
        return f"PLAN {model_id}: would restore from {backup}"

    shutil.copy2(backup, target)

    tok_backup = model_dir / "tokenizer_config.json.portal5-backup"
    tok_cfg = model_dir / "tokenizer_config.json"
    if tok_backup.exists():
        shutil.copy2(tok_backup, tok_cfg)

    return f"REVERT {model_id}: restored from .portal5-backup"


def _refetch() -> None:
    for fam in sorted(VALID_FAMILIES):
        url = f"{UPSTREAM_BASE}/{fam}/chat_template.jinja"
        dst = TPL_DIR / fam / "chat_template.jinja"
        dst.parent.mkdir(parents=True, exist_ok=True)
        print(f"Fetching {url}")
        with urllib.request.urlopen(url, timeout=30) as r:  # noqa: S310
            body = r.read().decode()
        header = (
            "{# vim: ft=jinja\n"
            f"   Vendored from: https://huggingface.co/froggeric/Qwen-Fixed-Chat-Templates\n"
            f"   Upstream commit: {UPSTREAM_COMMIT}\n"
            f"   Author: froggeric (HF)\n"
            f"   Original templates: Alibaba Cloud (Qwen team)\n"
            f"   License: Apache-2.0 (inherited from Qwen)\n"
            f"   Purpose: Fix |items / |safe Jinja filter crashes on mlx_lm/mlx_vlm\n"
            f"            plus empty-think-block stripping, developer role,\n"
            f"            and (3.6 only) </thinking> hallucination recovery.\n"
            f"   Update procedure: see config/chat_templates/README.md\n"
            f"#}}\n"
        )
        dst.write_text(header + body)
        print(f"  wrote {dst} ({dst.stat().st_size} bytes)")
    manifest = TPL_DIR / "SHA256SUMS"
    lines = []
    for fam in sorted(VALID_FAMILIES):
        rel = f"{fam}/chat_template.jinja"
        lines.append(f"{_sha256(TPL_DIR / rel)}  {rel}")
    manifest.write_text("\n".join(lines) + "\n")
    print(f"Re-stamped {manifest}")


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Patch Qwen 3.5/3.6 chat templates in MLX model directories."
    )
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument(
        "--rollback",
        metavar="MODEL_ID",
        help="Restore one model from .portal5-backup",
    )
    ap.add_argument(
        "--refetch",
        action="store_true",
        help="Re-download templates from upstream (updates SHA256SUMS)",
    )
    args = ap.parse_args()

    if args.refetch:
        _refetch()
        return 0

    _verify_manifest()

    if args.rollback:
        print(_rollback_model(args.rollback, args.dry_run))
        return 0

    overrides = _read_overrides()
    if not overrides:
        print("No models in backends.yaml have chat_template_override set. Nothing to do.")
        return 0

    print(f"Found {len(overrides)} models with chat_template_override:")
    for mid, fam in overrides:
        print(f"  {fam:8s}  {mid}")
    print()

    for mid, fam in overrides:
        print(_patch_model(mid, fam, args.dry_run))
    return 0


if __name__ == "__main__":
    sys.exit(main())
