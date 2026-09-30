"""The operator profile: identity and location constants that live locally.

READING_TRUTH_V1 P1: operator-specific constants (the entity's name, the
corpus location, pinned store sections, document targets) moved out of the
tracked tree into the gitignored profile at
``portal/modules/compliance/data/private/profile/operator_profile.json``.
Code reads them through :func:`profile` / :func:`require`; on a machine
without the profile (CI, a fresh clone) the call raises a clear error naming
the file instead of leaking the constants into the public tree.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

PROFILE_PATH = (
    Path(__file__).resolve().parents[3]
    / "modules"
    / "compliance"
    / "data"
    / "private"
    / "profile"
    / "operator_profile.json"
)


@lru_cache(maxsize=1)
def profile() -> dict[str, Any]:
    """The whole profile dict, or a clear error naming the missing file."""
    if not PROFILE_PATH.exists():
        raise RuntimeError(
            "the operator profile is not present: "
            f"{PROFILE_PATH} (gitignored; it exists on the operator's machine)"
        )
    return dict(json.loads(PROFILE_PATH.read_text(encoding="utf-8")))


def require(key_path: str) -> Any:
    """One profile value by dotted path, e.g. ``entity.name``."""
    node: Any = profile()
    for part in key_path.split("."):
        if not isinstance(node, dict) or part not in node:
            raise RuntimeError(f"the operator profile at {PROFILE_PATH} has no {key_path!r}")
        node = node[part]
    return node
