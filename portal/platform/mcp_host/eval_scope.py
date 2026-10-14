"""Evaluation scope for tool calls (WFE production tool mode, root-fix Part 2a).

A WFE row sends `portal_eval` in its request body. The pipeline narrows the
workspace's tools to the scope's allowlist and forwards the scope as `eval` on
every MCP call; each MCP confines the call's files to the run's namespace and
writes a creation receipt. Without a scope nothing changes.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from contextvars import ContextVar
from pathlib import Path
from typing import Any

TOKEN = re.compile(r"^wfe_[0-9a-f]{16,40}$")
EVAL_SCOPE: ContextVar[dict[str, Any] | None] = ContextVar("portal_eval_scope", default=None)


class ScopeError(ValueError):
    """A malformed scope, or a path outside the run's namespace."""


def parse(raw: Any) -> dict[str, Any] | None:
    """A validated scope from a body's `portal_eval` (pipeline) or `eval` (MCP) field."""
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise ScopeError("eval scope must be an object")
    camp, run, allow = raw.get("campaign"), raw.get("run"), raw.get("allow")
    if not (
        isinstance(camp, str) and TOKEN.match(camp) and isinstance(run, str) and TOKEN.match(run)
    ):
        raise ScopeError("eval scope campaign and run must match wfe_<hex>")
    # An empty allowlist is a sandbox row: no workspace tools, but injection still scoped.
    if not (isinstance(allow, list) and all(isinstance(t, str) and t for t in allow)):
        raise ScopeError("eval scope allow must be a list of tool names")
    return {"campaign": camp, "run": run, "allow": sorted(set(allow))}


def run_root(base: Path | str, scope: dict[str, Any]) -> Path:
    """`<base>/wfe/<campaign>/<run>`, with `base` resolved first; created if absent."""
    root = Path(base).resolve() / "wfe" / scope["campaign"] / scope["run"]
    root.mkdir(parents=True, exist_ok=True)
    return Path(root)


def confine(base: Path | str, scope: dict[str, Any], path: str | Path, sub: str = "") -> Path:
    """`path` resolved inside the run root (relative paths under `sub`); escapes refused."""
    root = run_root(base, scope)
    p = Path(path)
    cand = (p if p.is_absolute() else root / sub / p).resolve()
    if cand != root and root not in cand.parents:
        raise ScopeError(f"path outside the evaluation namespace: {path}")
    return cand


def receipt(base: Path | str, scope: dict[str, Any], tool: str, path: Path | str) -> dict[str, Any]:
    """Append a creation receipt to `<run root>/.receipts.jsonl` and return it."""
    p = confine(base, scope, path)
    data = p.read_bytes()
    # `rel` is what the harness resolves: an MCP in a container sees the run root under its own
    # mount (/app/data/generated/...), the harness under the host's (~/AI_Output/...).
    rec = {
        "tool": tool,
        "path": str(p),
        "rel": str(p.relative_to(run_root(base, scope))),
        "sha256": hashlib.sha256(data).hexdigest(),
        "size": len(data),
        "utc": time.time(),
    }
    with (run_root(base, scope) / ".receipts.jsonl").open("a") as fh:
        fh.write(json.dumps(rec) + "\n")
    return rec
