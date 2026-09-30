"""READING_TRUTH_V1 - where these instruments may write: local only.

The operator's policy (2026-09-28): "summaries of outcomes can be in the public
reports, everything else should just be local while we continue to develop
this, when it is complete none of that will be written outside of local".
Everything this package produces is "everything else", so it goes under the
private dir (gitignored) or outside the repo - never anywhere a commit could
carry it. The public outcome summary is written by hand, not by these tools.
"""

from __future__ import annotations

import pathlib

REPO = pathlib.Path(__file__).resolve().parents[3]
PRIVATE = REPO / "portal" / "modules" / "compliance" / "data" / "private"
RUNS = PRIVATE / "runs"


def _within(path: pathlib.Path, root: pathlib.Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def is_local(path: pathlib.Path) -> bool:
    """True when ``path`` can never be committed: under the private dir, or outside the repo."""
    resolved = pathlib.Path(path).resolve()
    return _within(resolved, PRIVATE.resolve()) or not _within(resolved, REPO.resolve())


def refusal(path: pathlib.Path, what: str) -> str:
    """An error message when ``path`` is not local, else the empty string."""
    if is_local(path):
        return ""
    return f"REFUSED: {what} is local-only - write it under {PRIVATE.relative_to(REPO)} or outside the repo, not {path}"
