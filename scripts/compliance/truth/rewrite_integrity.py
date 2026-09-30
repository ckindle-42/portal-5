#!/usr/bin/env python3
"""READING_TRUTH_V1 P1R - a history rewrite may change only what it had a reason to change.

The first rewrite passed its tree-equality check while corrupting the history of
files it kept: public NERC and NIST text and a synthetic corpus were replaced by
redaction markers in every historical version, and the tip then "restored"
them. This check compares the two generations commit by commit, through the
filter-repo commit map, and fails when:

1. a PROTECTED path (public regulatory data, synthetic corpora: files that by
   provenance cannot hold operator content) differs in any rewritten commit;
2. a KEPT path (present at the rewritten tip) was removed from, or added to, a
   rewritten commit;
3. a KEPT path changed in a rewritten commit although its original blob carried
   no genuine finding (``has_findings``, the P1 detector; without it rule 3 is
   reported NOT RUN, never as a pass).

Both generations' objects must be in one repository: fetch the old bundle's refs
into a scratch copy of the rewritten mirror. Output is local-only.
"""

from __future__ import annotations

import argparse
import fnmatch
import importlib
import json
import pathlib
import subprocess
import sys
from collections.abc import Callable, Iterable
from typing import Any

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _local  # noqa: E402

MARKER = "[operator text removed]"
ZERO = "0" * 40


def _git(git_dir: pathlib.Path, *args: str) -> bytes:
    return subprocess.run(
        ["git", f"--git-dir={git_dir}", *args], capture_output=True, check=True, timeout=600
    ).stdout


def read_commit_map(path: pathlib.Path) -> list[tuple[str, str]]:
    """filter-repo's ``commit-map``: a header line, then ``<old> <new>`` per commit."""
    pairs = []
    for line in path.read_text(encoding="utf-8").splitlines():
        parts = line.split()
        if len(parts) != 2 or parts[0] == "old":
            continue
        pairs.append((parts[0], parts[1]))
    return pairs


def _tree(git_dir: pathlib.Path, commit: str) -> str:
    return _git(git_dir, "rev-parse", f"{commit}^{{tree}}").decode().strip()


def _changes(
    git_dir: pathlib.Path, old_tree: str, new_tree: str
) -> Iterable[tuple[str, str, str, str]]:
    """(status, old_blob, new_blob, path) for every path that differs between two trees."""
    raw = _git(git_dir, "diff-tree", "-r", "--no-renames", "-z", old_tree, new_tree).decode(
        "utf-8", "replace"
    )
    fields = raw.split("\0")
    i = 0
    while i + 1 < len(fields):
        meta, path = fields[i], fields[i + 1]
        i += 2
        if not meta.startswith(":"):
            continue
        _, _, old_blob, new_blob, status = meta[1:].split(" ")
        yield status[:1], old_blob, new_blob, path


def _protected(path: str, globs: list[str]) -> bool:
    return any(fnmatch.fnmatch(path, g) for g in globs)


class _Blobs:
    def __init__(self, git_dir: pathlib.Path, has_findings: Callable[[str], bool] | None) -> None:
        self.git_dir = git_dir
        self.has_findings = has_findings
        self._cache: dict[str, bool] = {}

    def justified(self, blob: str) -> bool | None:
        """Did the ORIGINAL blob carry a genuine finding? None when no detector is given."""
        if self.has_findings is None:
            return None
        if blob not in self._cache:
            text = _git(self.git_dir, "cat-file", "blob", blob).decode("utf-8", "replace")
            self._cache[blob] = bool(self.has_findings(text))
        return self._cache[blob]


def _judge(
    status: str, path: str, old_blob: str, kept: set[str], globs: list[str], blobs: _Blobs
) -> tuple[str, bool | None] | None:
    """The rule a change violates, or None; plus whether rule 3 could be decided."""
    if _protected(path, globs):
        return "1:protected path changed", True
    if path not in kept:
        return None
    if status in ("D", "A"):
        return (
            f"2:kept path {'removed from' if status == 'D' else 'added to'} a rewritten commit",
            True,
        )
    justified = blobs.justified(old_blob)
    if justified is None:
        return "3:unverified", None
    return (
        (None, True)
        if justified
        else ("3:kept path changed without a finding in its original", True)
    )


def check(
    git_dir: pathlib.Path,
    pairs: list[tuple[str, str]],
    tip: str,
    protected_globs: list[str],
    has_findings: Callable[[str], bool] | None = None,
    *,
    limit: int = 200,
) -> dict[str, Any]:
    kept = set(_git(git_dir, "ls-tree", "-r", "--name-only", tip).decode().splitlines())
    blobs = _Blobs(git_dir, has_findings)
    violations: list[dict[str, str]] = []
    counts = {"commits": 0, "commits_with_tree_change": 0, "kept_changes": 0, "unverified": 0}
    for old, new in pairs:
        if ZERO in (old, new) or old == new:
            continue
        counts["commits"] += 1
        old_tree, new_tree = _tree(git_dir, old), _tree(git_dir, new)
        if old_tree == new_tree:
            continue
        counts["commits_with_tree_change"] += 1
        for status, old_blob, _new_blob, path in _changes(git_dir, old_tree, new_tree):
            verdict = _judge(status, path, old_blob, kept, protected_globs, blobs)
            if verdict is None:
                continue
            rule, _decided = verdict
            if path in kept:
                counts["kept_changes"] += 1
            if rule == "3:unverified":
                counts["unverified"] += 1
                continue
            if rule and len(violations) < limit:
                violations.append(
                    {"rule": rule, "path": path, "old_commit": old, "new_commit": new}
                )
    tip_markers = [
        p
        for p in kept
        if _protected(p, protected_globs)
        and MARKER in _git(git_dir, "show", f"{tip}:{p}").decode("utf-8", "replace")
    ]
    for p in tip_markers:
        violations.append({"rule": "1:redaction marker in a protected path at the tip", "path": p})
    return {
        "counts": counts,
        "rule_3": "RUN" if has_findings is not None else "NOT RUN (no detector given)",
        "violations": violations,
        "verdict": "FAIL"
        if violations or (has_findings is not None and counts["unverified"])
        else "PASS",
    }


def _load_callable(spec: str) -> Callable[[str], bool]:
    module, _, name = spec.partition(":")
    return getattr(importlib.import_module(module), name)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument(
        "--git-dir", type=pathlib.Path, required=True, help="holds BOTH generations' objects"
    )
    ap.add_argument("--commit-map", type=pathlib.Path, required=True)
    ap.add_argument("--tip", required=True, help="the rewritten tip")
    ap.add_argument(
        "--protected", type=pathlib.Path, required=True, help="one fnmatch glob per line"
    )
    ap.add_argument(
        "--detector-callable", help="module:function taking text, returning True on a finding"
    )
    ap.add_argument("--out", type=pathlib.Path, required=True)
    args = ap.parse_args(argv)
    refused = _local.refusal(args.out, "the rewrite-integrity report")
    if refused:
        print(refused, file=sys.stderr)
        return 2
    globs = [
        g.strip()
        for g in args.protected.read_text().splitlines()
        if g.strip() and not g.startswith("#")
    ]
    detector = _load_callable(args.detector_callable) if args.detector_callable else None
    result = check(args.git_dir, read_commit_map(args.commit_map), args.tip, globs, detector)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2) + "\n")
    print(f"REWRITE INTEGRITY {result['verdict']} - {result['counts']} - rule 3 {result['rule_3']}")
    return 0 if result["verdict"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
