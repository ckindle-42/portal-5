"""Archive mechanism — retained on disk, out of the working set.

Archiving is not deletion. Catalog changes in this project are additive-only,
so an archived unit keeps its file (moved to `portal_wiki/archive/`) and its
frontmatter unchanged; it simply leaves the live store that search, coverage,
drift, quality, and render operate over.

The preconditions for archiving live *in this module*, not in the operator's
discipline:

  - a reason is mandatory, phrased as a fact ("cites only docs/HOWTO.md, which
    is generated output; no code determines its truth")
  - no `WIKI:GENERATED` doc block may reference the id
  - no live unit's body may link the id
  - no cited source may be a live `.py`/`.yaml`/`.json`/`.sh`

The last refusal is overridable only with `--superseded-by <unit-id>`; the
command then verifies the named survivor exists and cites every code path the
archived unit cited, so knowledge is not lost to reachability.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]

_ARCHIVE_INDEX = "INDEX.md"

# Extensions that make a source a *live code/config* source the archive must
# not strand. Anything else (a doc, a URL, a technique id, a bench-run id) is
# not a code source.
_CODE_EXTENSIONS = (".py", ".yaml", ".yml", ".json", ".sh", ".toml")


@dataclass(frozen=True)
class ArchiveRefusal:
    """One reason a unit cannot be archived. Non-empty means refuse."""

    reason: str = ""


def _current_commit(repo_root: Path) -> str:
    proc = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo_root, capture_output=True, text=True, check=False
    )
    return proc.stdout.strip() or ""


def _archive_index_path(repo_root: Path) -> Path:
    del repo_root
    from portal.platform.wiki.store import _get_archive_dir

    return _get_archive_dir() / _ARCHIVE_INDEX


def check_archivable(unit, repo_root: Path | None = None) -> list[str]:
    """Every precondition that would make archiving this unit unsafe.

    Returns a list of refusal reasons; empty means archiving is allowed.
    These are enforced by the `archive` command and cannot be waived by
    asserting them in a commit message.
    """
    root = repo_root or _REPO_ROOT
    refusals: list[str] = []

    # 1. Doc blocks: scan Tier-1 docs for a WIKI:GENERATED marker naming the id.
    from portal.platform.wiki.render import TIER1_DOCS

    for rel in TIER1_DOCS:
        p = root / rel
        if not p.exists():
            continue
        if re.search(rf"unit={re.escape(unit.id)}\b", p.read_text(encoding="utf-8")):
            refusals.append(
                f"WIKI:GENERATED block in {rel} references {unit.id} — "
                f"remove the block (or re-point it) before archiving"
            )

    # 2. Inbound links: another live unit's body mentions the id.
    from portal.platform.wiki.store import load_all

    for other in load_all():
        if other.id == unit.id:
            continue
        if re.search(rf"\b{re.escape(unit.id)}\b", other.body):
            refusals.append(
                f"live unit {other.id} links {unit.id} in its body — "
                f"remove the link before archiving"
            )

    # 3. Live code sources: any cited source is a live code/config file or
    #    directory. A directory citation (e.g. `unit-module-*` citing
    #    `portal/modules/<name>/`) is a live code source too — the module toggle
    #    reads those units as config, so archiving them must be refused exactly
    #    like a file citation would be.
    for src in unit.sources:
        raw = (src.path or "").split("#", 1)[0].strip()
        if not raw or raw.startswith(("http://", "https://", "/")):
            continue
        if (raw.endswith(_CODE_EXTENSIONS) or (root / raw).is_dir()) and (root / raw).exists():
            refusals.append(
                f"cites live source {raw} — a code/config path determines its truth; "
                f"re-ground it or pass --superseded-by <survivor>"
            )

    return refusals


def verify_superseded(unit, survivor_id: str, repo_root: Path | None = None) -> str | None:
    """The `--superseded-by` override: the survivor must exist and the code paths
    the archived unit cited must remain covered by the live store (the named
    survivor plus other live units). Returns None on success, else the refusal.

    A unit is safely superseded when every code/config path it cited is still
    cited by at least one live unit — the aggregate `unit-code-*` stubs cite
    five files each, every one of which now has its own covering unit, so no
    path loses grounding when the stub is archived.
    """
    root = repo_root or _REPO_ROOT
    from portal.platform.wiki.store import load_all, load_unit

    survivor = load_unit(survivor_id)
    if survivor is None:
        return f"--superseded-by {survivor_id}: survivor unit does not exist"
    live_paths: set[str] = set()
    for u in load_all():
        if u.id == unit.id:
            continue
        for s in u.sources:
            raw = (s.path or "").split("#", 1)[0].strip()
            if not raw:
                continue
            if any(ch in raw for ch in "*?["):
                live_paths.update(_expand_glob(root, raw))
            else:
                live_paths.add(raw)
    missing = [
        (s.path or "").split("#", 1)[0].strip()
        for s in unit.sources
        if (s.path or "").endswith(_CODE_EXTENSIONS)
        and (s.path or "").split("#", 1)[0].strip() not in live_paths
    ]
    if missing:
        return (
            f"--superseded-by {survivor_id}: {', '.join(sorted(set(missing))[:5])} "
            f"cited by no live unit — the archive would strand them"
        )
    return None


def _expand_glob(root: Path, pattern: str) -> set[str]:
    """Expand a glob source path to matching repo-relative files."""
    try:
        return {str(m.relative_to(root)) for m in root.glob(pattern) if m.is_file()}
    except (OSError, ValueError):
        return set()


def archive_unit(
    unit_id: str, reason: str, repo_root: Path | None = None, superseded_by: str | None = None
) -> tuple[bool, str]:
    """Move a live unit to the archive store and append its index line.

    Returns (ok, message). On refusal, ok is False and nothing is moved.
    """
    root = repo_root or _REPO_ROOT
    from portal.platform.wiki.store import _get_archive_dir, _get_canonical_dir, load_unit

    if not reason or not reason.strip():
        return False, "archive refused: --reason <text> is required"

    unit = load_unit(unit_id)
    if unit is None:
        return False, f"no live unit {unit_id}"

    refusals = check_archivable(unit, root)
    code_refusals = [r for r in refusals if "cites live source" in r]
    other_refusals = [r for r in refusals if r not in code_refusals]

    # The code-source refusal is the only one overridable, and only with a
    # verified survivor that covers every code path the archived unit cited.
    if superseded_by:
        err = verify_superseded(unit, superseded_by, root)
        if err:
            return False, err
    elif code_refusals:
        return False, "; ".join(refusals)

    if other_refusals:
        return False, "; ".join(other_refusals)

    canonical = _get_canonical_dir()
    archive = _get_archive_dir()
    src = canonical / f"{unit_id}.md"
    if not src.exists():
        return False, f"no file {src}"
    archive.mkdir(parents=True, exist_ok=True)
    dst = archive / f"{unit_id}.md"
    src.rename(dst)

    commit = _current_commit(root)
    date = datetime.now(UTC).strftime("%Y-%m-%d")
    index = _archive_index_path(root)
    with index.open("a", encoding="utf-8") as fh:
        fh.write(f"- `{unit_id}` | {date} | {commit} | {reason.strip()}\n")
    return True, f"archived {unit_id} → portal_wiki/archive/ (indexed at {commit})"


def archive_reachability(root: Path | None = None) -> list[str]:
    """Archived units are unreachable from the live store: no live unit's body
    links an archived id, and no Tier-1 doc block references one. Empty = clean.
    """
    repo_root = root or _REPO_ROOT
    from portal.platform.wiki.render import TIER1_DOCS
    from portal.platform.wiki.store import load_all, load_archived

    archived = {u.id for u in load_archived()}
    if not archived:
        return []
    live = load_all()
    violations: list[str] = []

    for other in live:
        for aid in archived:
            if re.search(rf"\b{re.escape(aid)}\b", other.body):
                violations.append(f"live unit {other.id} links archived {aid}")
    for rel in TIER1_DOCS:
        p = repo_root / rel
        if not p.exists():
            continue
        text = p.read_text(encoding="utf-8")
        for aid in archived:
            if re.search(rf"unit={re.escape(aid)}\b", text):
                violations.append(f"doc block in {rel} references archived {aid}")
    return sorted(set(violations))
