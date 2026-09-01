"""Evidence-artifact header standard (TASK_VL_RETRIEVAL_HARDENING_AND_CLOSEOUT_V2 C3).

V4's §1.3 lesson: record the verbatim output together with the resolved versions
that produced it. Three artifacts at HEAD failed that — a 0-byte file, a freeze
describing a phonemizer version a later commit removed, a parity fingerprint
with no versions. Every file written under `reports/` now carries a header:

    # command: <the exact command / probe>
    # inputs: <what was fed in — paths, HEAD sha, env>
    # resolved-versions: <key package==version, comma-sep, or "n/a">
    # timestamp: <ISO-8601 UTC>
    # ---

`header_for()` builds it; `check_reports_headers()` (validate_system HC) fails on
a zero-byte or header-less file. JSON artifacts carry the same four keys under a
top-level `"_evidence"` object instead of a comment block.
"""

from __future__ import annotations

import datetime as _dt
import json
import subprocess
from pathlib import Path

REQUIRED = ("command", "inputs", "resolved-versions", "timestamp")
_JSON_KEY = "_evidence"


def _head_sha(root: Path) -> str:
    try:
        return (
            subprocess.run(
                ["git", "-C", str(root), "rev-parse", "--short", "HEAD"],
                capture_output=True,
                text=True,
                timeout=10,
            ).stdout.strip()
            or "?"
        )
    except (OSError, subprocess.SubprocessError):
        return "?"


def resolved_versions(root: Path, packages: list[str]) -> str:
    import importlib.metadata as md

    parts = []
    for p in packages:
        try:
            parts.append(f"{p}=={md.version(p)}")
        except md.PackageNotFoundError:
            parts.append(f"{p}==<absent>")
    return ", ".join(parts) if parts else "n/a"


def header_for(
    command: str, inputs: str, *, packages: list[str] | None = None, root: Path | None = None
) -> str:
    root = root or Path(__file__).resolve().parents[2]
    ts = _dt.datetime.now(_dt.UTC).isoformat(timespec="seconds")
    ver = resolved_versions(root, packages or [])
    return (
        f"# command: {command}\n"
        f"# inputs: {inputs} (HEAD {_head_sha(root)})\n"
        f"# resolved-versions: {ver}\n"
        f"# timestamp: {ts}\n"
        f"# ---\n"
    )


def json_evidence(
    command: str, inputs: str, *, packages: list[str] | None = None, root: Path | None = None
) -> dict:
    root = root or Path(__file__).resolve().parents[2]
    return {
        "command": command,
        "inputs": f"{inputs} (HEAD {_head_sha(root)})",
        "resolved-versions": resolved_versions(root, packages or []),
        "timestamp": _dt.datetime.now(_dt.UTC).isoformat(timespec="seconds"),
    }


def _file_has_header(path: Path) -> tuple[bool, str]:
    if path.stat().st_size == 0:
        return False, "zero-byte"
    if path.suffix == ".json":
        try:
            obj = json.loads(path.read_text())
        except (ValueError, OSError) as e:
            return False, f"unreadable json: {e}"
        ev = obj.get(_JSON_KEY) if isinstance(obj, dict) else None
        if not isinstance(ev, dict):
            return False, f"no top-level {_JSON_KEY!r} object"
        missing = [k for k in REQUIRED if not ev.get(k)]
        return (not missing), (f"missing {_JSON_KEY} keys: {missing}" if missing else "ok")
    head = "\n".join(path.read_text(errors="replace").splitlines()[:15]).lower()
    missing = [k for k in REQUIRED if f"{k}:" not in head]
    return (not missing), (f"missing header keys: {missing}" if missing else "ok")


def check_reports_headers(root: Path | None = None) -> list[tuple[str, str]]:
    """Return [(relpath, reason), ...] for every offending evidence file under
    `reports/runtime/` — the dir this standard governs. Pre-existing bench
    output elsewhere under `reports/` is grandfathered (it predates the
    standard); new evidence goes under `reports/runtime/` and carries a header.
    `.md` prose reports are exempt (they carry their own front-matter).
    """
    root = root or Path(__file__).resolve().parents[2]
    runtime = root / "reports" / "runtime"
    if not runtime.is_dir():
        return []
    bad = []
    for p in runtime.rglob("*"):
        if not p.is_file() or p.suffix not in (".txt", ".json", ".jsonl", ".log"):
            continue
        ok, reason = _file_has_header(p)
        if not ok:
            bad.append((str(p.relative_to(root)), reason))
    return bad
