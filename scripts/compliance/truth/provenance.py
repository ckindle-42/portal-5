"""READING_TRUTH_V1 - what ran, recorded on every compliance suite receipt.

Every baseline the module has quoted so far was compared across eras whose
grader, persona, tool manifest, engine and sampling had all moved, and no
receipt said so. ``receipt_provenance`` is best-effort by design: a field it
cannot read is recorded as an error string, never guessed, and it never
raises into the harness that calls it.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import pathlib
import subprocess
import sys
from typing import Any

REPO = pathlib.Path(__file__).resolve().parents[3]
PORTAL_YAML = REPO / "config" / "portal.yaml"
HASHED_FILES = (
    "scripts/compliance_acceptance.py",
    "scripts/compliance/ask_conversational.py",
    "scripts/compliance/ask_product_questions.py",
    "scripts/compliance/truth/citation_integrity.py",
    "portal/modules/compliance/core/citation_by_quote.py",
    "portal/modules/compliance/core/answer_contract.py",
    "portal/modules/compliance/core/reading_material.py",
    "config/inference/tools_manifest_compliance_mcp.json",
)
SETTINGS = (
    "model_hint",
    "context_limit",
    "predict_limit",
    "temperature",
    "top_p",
    "top_k",
    "min_p",
    "repeat_penalty",
    "think",
)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=REPO, capture_output=True, text=True, timeout=30, check=False
    ).stdout.strip()


def receipt_provenance(workspace: str, *, harness_file: str = "") -> dict[str, Any]:
    out: dict[str, Any] = {
        "generated_utc": _dt.datetime.now(_dt.UTC).isoformat(),
        "python": sys.version.split()[0],
        "workspace": workspace,
        "errors": [],
    }
    try:
        out["git_head"] = _git("rev-parse", "HEAD")
        out["git_dirty_paths"] = len(
            [ln for ln in _git("status", "--porcelain").splitlines() if ln]
        )
    except (OSError, subprocess.SubprocessError) as exc:
        out["errors"].append(f"git: {exc}")
    try:
        import yaml

        config = yaml.safe_load(PORTAL_YAML.read_text(encoding="utf-8"))
        spaces = config.get("workspaces") or {}
        if isinstance(spaces, list):
            spaces = {w.get("id"): w for w in spaces if isinstance(w, dict)}
        ws = spaces.get(workspace) or {}
        out["workspace_settings"] = {k: ws.get(k) for k in SETTINGS}
        persona = str(ws.get("system_prompt_append") or "")
        out["persona_sha256"] = _sha(persona.encode()) if persona else ""
        out["persona_chars"] = len(persona)
        tools = [str(t) for t in ws.get("tools") or []]
        out["tools_sha256"] = _sha("\n".join(tools).encode())
        out["n_tools"] = len(tools)
    except Exception as exc:  # noqa: BLE001 - provenance never breaks a run
        out["errors"].append(f"portal.yaml: {exc}")
    shas: dict[str, str] = {}
    for rel in (*HASHED_FILES, harness_file):
        if not rel:
            continue
        path = pathlib.Path(rel)
        path = path if path.is_absolute() else REPO / path
        try:
            shas[
                str(path.resolve().relative_to(REPO)) if path.is_relative_to(REPO) else str(path)
            ] = _sha(path.read_bytes())
        except OSError:
            shas[rel] = "absent"
    out["file_sha256"] = shas
    return out
