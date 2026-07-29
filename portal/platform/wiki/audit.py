"""Integrity checks for the canonical knowledge-unit store.

The canonical units are the authored source of truth.  This module does not
try to prove their prose from some other document; it enforces the mechanical
properties that make the spine trustworthy:

* canonical bodies may not contain extraction/truncation artifacts;
* repository-local provenance must resolve to a real file or glob; and
* non-local identifiers (URLs, ATT&CK IDs, runtime event identifiers) remain
  valid provenance without being mistaken for filesystem paths.

The module is deliberately stack-agnostic and has no Portal runtime imports.
"""

from __future__ import annotations

import glob
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .schema import KnowledgeUnit, SourceRef
from .store import load_all

_CORRUPTION_PATTERNS = (
    re.compile(r"\[Content truncated\b", re.IGNORECASE),
    re.compile(r"\bWarning:\s*truncated output\b", re.IGNORECASE),
    re.compile(r"\btoken limit(?: was)? reached\b", re.IGNORECASE),
)
_IDENTIFIER_PREFIXES = (
    "ATT&CK:",
    "bench-run:",
    "module-state-change:",
)
_TECHNIQUE_ID_RE = re.compile(r"^T\d{4}(?:\.\d{3})?$")


@dataclass(frozen=True)
class IntegrityIssue:
    """One actionable canonical-store integrity failure."""

    unit_id: str
    code: str
    detail: str
    source_path: str = ""


def _without_fragment(path: str) -> str:
    """Remove a source anchor while preserving ordinary path characters."""
    return path.split("#", 1)[0].strip()


def source_is_repository_local(source: SourceRef) -> bool:
    """Return whether a source reference is intended to resolve in the repo."""
    path = _without_fragment(source.path)
    if not path or "://" in path:
        return False
    if Path(path).is_absolute():
        return False
    if source.type in {"mitre", "url"}:
        return False
    return not (path.startswith(_IDENTIFIER_PREFIXES) or _TECHNIQUE_ID_RE.fullmatch(path))


def resolve_local_source(repo_root: Path, source: SourceRef) -> tuple[Path, ...]:
    """Resolve a repository-local source, including globs and bare filenames.

    Bare filenames are supported for the historical security seeders, which
    cite ``exec_chain.py#scenario``.  Paths containing a directory component
    must resolve exactly so old package paths cannot silently bind to an
    unrelated file with the same basename.
    """
    if not source_is_repository_local(source):
        return ()

    raw = _without_fragment(source.path)
    if glob.has_magic(raw):
        return tuple(sorted(path for path in repo_root.glob(raw) if path.exists()))

    candidate = repo_root / raw
    if candidate.exists():
        return (candidate,)

    if "/" not in raw and "\\" not in raw:
        return tuple(sorted(repo_root.rglob(raw)))
    return ()


def _git_tracked_paths(repo_root: Path) -> frozenset[str] | None:
    """Return repository-relative paths present in Git's index.

    ``None`` means ``repo_root`` is not a Git worktree, in which case callers
    may fall back to filesystem-only validation (useful for isolated tests and
    extracted deployments).  An empty set is a valid result for a Git
    worktree with no indexed files.
    """
    try:
        result = subprocess.run(
            ["git", "ls-files", "-z"],
            cwd=repo_root,
            capture_output=True,
            check=True,
            timeout=10,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return None
    return frozenset(
        path for path in result.stdout.decode("utf-8", errors="surrogateescape").split("\0") if path
    )


def _match_is_tracked(repo_root: Path, match: Path, tracked_paths: frozenset[str]) -> bool:
    """Return whether a resolved file or directory survives a clean checkout."""
    try:
        relative = match.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return False
    if match.is_dir():
        prefix = f"{relative.rstrip('/')}/"
        return any(path.startswith(prefix) for path in tracked_paths)
    return relative in tracked_paths


def audit_units(
    repo_root: Path,
    units: list[KnowledgeUnit] | None = None,
    *,
    tracked_paths: frozenset[str] | None = None,
) -> list[IntegrityIssue]:
    """Audit canonical bodies and local provenance references."""
    if units is None:
        units = load_all()
    if tracked_paths is None:
        tracked_paths = _git_tracked_paths(repo_root)

    issues: list[IntegrityIssue] = []
    for unit in units:
        for pattern in _CORRUPTION_PATTERNS:
            match = pattern.search(unit.body)
            if match:
                issues.append(
                    IntegrityIssue(
                        unit_id=unit.id,
                        code="corrupt-body",
                        detail=f"contains extraction artifact {match.group(0)!r}",
                    )
                )
                break
        for source in unit.sources:
            if _without_fragment(source.path).startswith("/tmp/"):
                issues.append(
                    IntegrityIssue(
                        unit_id=unit.id,
                        code="ephemeral-source",
                        detail="canonical provenance points at an ephemeral /tmp path",
                        source_path=source.path,
                    )
                )
                continue
            if not source_is_repository_local(source):
                continue
            matches = resolve_local_source(repo_root, source)
            untracked_matches: tuple[Path, ...] = ()
            if tracked_paths is not None and matches:
                untracked_matches = tuple(
                    match
                    for match in matches
                    if not _match_is_tracked(repo_root, match, tracked_paths)
                )
                matches = tuple(match for match in matches if match not in untracked_matches)
            if not matches:
                code = "untracked-source" if untracked_matches else "missing-source"
                detail = (
                    "repository-local provenance is excluded from a clean checkout"
                    if untracked_matches
                    else "repository-local provenance does not resolve"
                )
                issues.append(
                    IntegrityIssue(
                        unit_id=unit.id,
                        code=code,
                        detail=detail,
                        source_path=source.path,
                    )
                )
            elif "/" not in _without_fragment(source.path) and len(matches) > 1:
                issues.append(
                    IntegrityIssue(
                        unit_id=unit.id,
                        code="ambiguous-source",
                        detail=f"bare provenance filename resolves to {len(matches)} files",
                        source_path=source.path,
                    )
                )
    return issues
