#!/usr/bin/env python3
"""Apply or revert the experimental coder-seat kit."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
KIT = Path(__file__).resolve().parent / "kit"
FILES = ("config/portal.yaml", "config/backends.yaml")
MANIFEST = "manifest.json"
COPY_IGNORE = (
    ".git",
    ".venv",
    ".env",
    ".env.*",
    ".secrets",
    ".cache",
    ".claude",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    "*.pyc",
    "results",
    "reports",
    "private",
    "field_journal",
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _indent(text: str, count: int) -> str:
    return "".join((" " * count + line) if line.strip() else line for line in text.splitlines(True))


def _blocks(kit_dir: Path) -> dict[str, str]:
    raw = (kit_dir / "portal_variants.yaml").read_text()
    parts = re.split(r"^# -+ (auto-[a-z-]+)\.variants -+\s*$", raw, flags=re.M)
    return {
        name: body.strip("\n") + "\n" for name, body in zip(parts[1::2], parts[2::2], strict=True)
    }


def _insert_variants(lines: list[str], workspace: str, body: str) -> list[str]:
    start = lines.index(f"  {workspace}:\n")
    end = next(
        (i for i in range(start + 1, len(lines)) if re.match(r"^  [a-z]", lines[i])),
        len(lines),
    )
    for index in range(start + 1, end):
        if lines[index] == "    variants:\n":
            return lines[: index + 1] + [_indent(body, 6)] + lines[index + 1 :]
    return lines[:end] + ["    variants:\n", _indent(body, 6)] + lines[end:]


def render_kit(repo: Path, kit_dir: Path = KIT) -> list[Path]:
    portal = repo / "config/portal.yaml"
    lines = portal.read_text().splitlines(True)
    blocks = _blocks(kit_dir)
    for workspace in ("auto-coding", "auto-spl"):
        lines = _insert_variants(lines, workspace, blocks[workspace])
    portal.write_text("".join(lines))

    additions = yaml.safe_load((kit_dir / "backends_additions.yaml").read_text())
    backend_path = repo / "config/backends.yaml"
    backend_text = backend_path.read_text()

    def models(entries: list[dict]) -> str:
        return "".join(
            f"  - id: {entry['id']}\n    supports_tools: {str(entry['supports_tools']).lower()}\n"
            for entry in entries
        )

    anchors = (
        ("  id: ollama-coding\n  models:\n", models(additions["ollama-coding-models"])),
        ("  id: omlx-coding\n  models:\n", models(additions["omlx-coding-models"])),
    )
    for anchor, payload in anchors:
        if backend_text.count(anchor) != 1:
            raise ValueError(f"expected exactly one backend anchor: {anchor.strip()}")
        backend_text = backend_text.replace(anchor, anchor + payload)
    alias_anchor = "    hf.co/unsloth/Qwen3.8-27B-GGUF:Q4_K_M: Qwen3.8-27B-oQ4e-mtp\n"
    if backend_text.count(alias_anchor) != 1:
        raise ValueError("expected exactly one oMLX alias anchor")
    aliases = "".join(
        f"    {key}: {value}\n" for key, value in additions["omlx-coding-aliases"].items()
    )
    backend_path.write_text(backend_text.replace(alias_anchor, alias_anchor + aliases))

    documents = [row for row in yaml.safe_load_all((kit_dir / "personas.yaml").read_text()) if row]
    created = []
    for persona in documents:
        target = repo / "config/personas" / f"{persona['slug']}.yaml"
        if target.exists():
            raise FileExistsError(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(yaml.safe_dump(persona, sort_keys=False, allow_unicode=True))
        created.append(target)
    return created


def _backup_root(repo: Path) -> Path:
    digest = hashlib.sha256(str(repo.resolve()).encode()).hexdigest()[:16]
    return Path.home() / ".local/state/portal5-seat-screen" / digest


def apply_kit(repo: Path, kit_dir: Path = KIT, backup_dir: Path | None = None) -> None:
    backup = backup_dir or _backup_root(repo)
    if backup.exists():
        raise FileExistsError(f"kit backup already exists: {backup}")
    with tempfile.TemporaryDirectory(prefix="seat-kit-render-") as temp:
        candidate = Path(temp) / "candidate"
        shutil.copytree(repo / "config", candidate / "config")
        created = render_kit(candidate, kit_dir)
        created_relative = [path.relative_to(candidate).as_posix() for path in created]
        backup.mkdir(parents=True)
        for relative in FILES:
            shutil.copy2(repo / relative, backup / Path(relative).name)
        try:
            for relative in FILES:
                shutil.copy2(candidate / relative, repo / relative)
            for relative in created_relative:
                shutil.copy2(candidate / relative, repo / relative)
            manifest = {
                "added_personas": created_relative,
                "applied_hashes": {relative: _sha256(repo / relative) for relative in FILES},
                "persona_hashes": {
                    relative: _sha256(repo / relative) for relative in created_relative
                },
            }
            (backup / MANIFEST).write_text(json.dumps(manifest, indent=2) + "\n")
        except OSError:
            for relative in FILES:
                shutil.copy2(backup / Path(relative).name, repo / relative)
            for relative in created_relative:
                (repo / relative).unlink(missing_ok=True)
            shutil.rmtree(backup, ignore_errors=True)
            raise
    print(f"kit applied; backup: {backup}")


def revert_kit(repo: Path, backup_dir: Path | None = None) -> None:
    backup = backup_dir or _backup_root(repo)
    manifest = json.loads((backup / MANIFEST).read_text())
    for relative, digest in manifest["applied_hashes"].items():
        if _sha256(repo / relative) != digest:
            raise ValueError(f"{relative} changed after kit apply; refusing to overwrite it")
    for relative, digest in manifest["persona_hashes"].items():
        path = repo / relative
        if not path.is_file() or _sha256(path) != digest:
            raise ValueError(f"{relative} changed after kit apply; refusing to remove it")
    for relative in FILES:
        shutil.copy2(backup / Path(relative).name, repo / relative)
    for relative in manifest["added_personas"]:
        (repo / relative).unlink()
    shutil.rmtree(backup)
    print("kit reverted")


def _copy_repo(repo: Path, target: Path) -> None:
    shutil.copytree(repo, target, ignore=shutil.ignore_patterns(*COPY_IGNORE))


def _audit_workspace_ids(repo: Path) -> list[str]:
    portal = yaml.safe_load((repo / "config/portal.yaml").read_text()) or {}
    workspaces = portal.get("workspaces") or {}
    workspace_ids: list[str] = []
    for workspace_id in ("auto-coding", "auto-spl"):
        workspace_ids.append(workspace_id)
        variants = (workspaces.get(workspace_id) or {}).get("variants") or {}
        workspace_ids.extend(f"{workspace_id}::{variant_id}" for variant_id in variants)
    return workspace_ids


def _audit_config(repo: Path) -> subprocess.CompletedProcess[str]:
    workspace_ids = _audit_workspace_ids(repo)
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "tests.wfe.settings_audit",
            "--config-only",
            "--workspace",
            *workspace_ids,
        ],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )


def dry_run(action: str, repo: Path, kit_dir: Path, backup_dir: Path) -> int:
    with tempfile.TemporaryDirectory(prefix="seat-kit-dry-run-") as temp:
        target = Path(temp) / "repo"
        _copy_repo(repo, target)
        target_backup = Path(temp) / "backup"
        if action == "apply":
            apply_kit(target, kit_dir, target_backup)
        else:
            if not backup_dir.is_dir():
                raise FileNotFoundError(f"kit backup not found: {backup_dir}")
            shutil.copytree(backup_dir, target_backup)
            revert_kit(target, target_backup)
        audit = _audit_config(target)
        print((audit.stdout + audit.stderr).strip())
        print(f"dry-run settings_audit --config-only exit={audit.returncode}")
        return audit.returncode


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("apply", "revert"))
    parser.add_argument("--repo", type=Path, default=ROOT)
    parser.add_argument("--kit-dir", type=Path, default=KIT)
    parser.add_argument("--backup-dir", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    repo = args.repo.resolve()
    backup = args.backup_dir.resolve() if args.backup_dir else _backup_root(repo)
    if args.dry_run:
        return dry_run(args.action, repo, args.kit_dir.resolve(), backup)
    if args.action == "apply":
        apply_kit(repo, args.kit_dir.resolve(), backup)
    else:
        revert_kit(repo, backup)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
