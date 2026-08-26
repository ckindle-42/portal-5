"""Project workspace for binary research.

Each research item is a directory with a static structure. Projects live under
a standard root (BINRESEARCH_PROJECTS_ROOT, default ~/binresearch). The harness
works out of the current project dir; the MCP mounts it by name.

Resolution:
  - explicit path or name under the root  -> that project
  - CWD is (or is inside) a project dir    -> that project (auto-detect)
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path

_WORKSPACE_DIRS = ["artifacts", "verifiers", "02_evidence"]
_WORKSPACE_FILES = [
    "00_inventory.md",
    "01_hypotheses.md",
    "03_model.md",
    "04_checks.md",
    "05_report.md",
]
_MARKER = ".binresearch"  # written at project root so CWD auto-detect works


def projects_root() -> Path:
    return Path(
        os.getenv("BINRESEARCH_PROJECTS_ROOT", str(Path.home() / "binresearch"))
    ).expanduser()


def resolve_project(name_or_path: str | None) -> Path:
    """Resolve a project directory from a name, a path, or the CWD."""
    if name_or_path:
        p = Path(name_or_path).expanduser()
        if p.is_absolute() or p.exists() or "/" in name_or_path:
            return p.resolve()
        return (projects_root() / name_or_path).resolve()
    # Auto-detect: walk up from CWD looking for the marker.
    cur = Path.cwd().resolve()
    for cand in [cur, *cur.parents]:
        if (cand / _MARKER).exists():
            return cand
    return cur  # fall back to CWD


def is_initialized(project_dir: Path) -> bool:
    """True if the project has the static structure."""
    if not (project_dir / _MARKER).exists():
        return False
    return all((project_dir / d).is_dir() for d in _WORKSPACE_DIRS) and all(
        (project_dir / f).exists() for f in _WORKSPACE_FILES
    )


def init_project(project_dir: Path) -> None:
    """Create the static structure (idempotent)."""
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / _MARKER).touch()
    for d in _WORKSPACE_DIRS:
        (project_dir / d).mkdir(exist_ok=True)
    for f in _WORKSPACE_FILES:
        p = project_dir / f
        if not p.exists():
            p.write_text(f"# {f.removesuffix('.md')}\n\n")
    trace = project_dir / "trace.jsonl"
    if not trace.exists():
        trace.touch()


def has_artifacts(project_dir: Path) -> bool:
    a = project_dir / "artifacts"
    return a.is_dir() and any(f for f in a.iterdir() if not f.name.startswith("."))


def verifier_count(project_dir: Path) -> int:
    v = project_dir / "verifiers"
    if not v.is_dir():
        return 0
    return sum(1 for f in v.iterdir() if f.suffix in {".sh", ".py"} and not f.name.startswith("."))


def snapshot(project_dir: Path, *, max_file_chars: int = 2000) -> str:
    parts: list[str] = []
    for fname in ["00_inventory.md", "01_hypotheses.md", "03_model.md", "04_checks.md"]:
        p = project_dir / fname
        if p.exists():
            text = p.read_text()
            if len(text) > max_file_chars:
                text = text[:max_file_chars] + "\n... [truncated]"
            parts.append(f"### {fname}\n{text}")
    for dname in ["02_evidence", "verifiers", "artifacts"]:
        d = project_dir / dname
        if d.is_dir():
            files = sorted(f.name for f in d.iterdir() if not f.name.startswith("."))
            parts.append(f"### {dname}/\n{', '.join(files) if files else '(empty)'}")
    return "\n\n".join(parts)


class TraceLog:
    def __init__(self, project_dir: Path):
        self._path = project_dir / "trace.jsonl"

    def log(self, event_type: str, data: dict) -> None:
        entry = {"ts": datetime.now(UTC).isoformat(), "type": event_type, **data}
        with self._path.open("a") as f:
            f.write(json.dumps(entry, default=str) + "\n")
