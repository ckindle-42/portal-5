#!/usr/bin/env python3
"""Classify ``uv sync --check`` output as lock-ahead or venv-ahead.

``uv`` prints a removed distribution (``- name==old``) and an added one
(``+ name==new``) for every version change. A lock bump therefore contains
``-`` lines even when every new version is newer. Treating any ``-`` or ``~``
as "venv ahead" refuses the sync that ``up`` / ``rebuild`` must run.
``~`` is a same-version reinstall, not a downgrade.
"""

from __future__ import annotations

import re
import sys

_ANSI = re.compile(r"\x1b\[[0-9;]*m")
_CHANGE = re.compile(r"^\s*([+~-])\s+(\S+?)==(\S+)\s*$")

LOCK_AHEAD = "lock_ahead"
VENV_AHEAD = "venv_ahead"
REINSTALL = "reinstall"
UNKNOWN = "unknown"


def version_key(value: str) -> tuple[int, ...]:
    nums = [int(part) for part in re.findall(r"\d+", value)][:6]
    return tuple(nums + [0] * (6 - len(nums)))


def classify_sync_diff(text: str) -> str:
    """Return lock_ahead, venv_ahead, reinstall, or unknown."""
    removed: dict[str, list[str]] = {}
    added: dict[str, list[str]] = {}
    reinstalled: dict[str, list[str]] = {}
    for raw in _ANSI.sub("", text).splitlines():
        match = _CHANGE.match(raw.strip())
        if match is None:
            continue
        op, name, version = match.group(1), match.group(2).lower(), match.group(3)
        bucket = {"-": removed, "+": added, "~": reinstalled}[op]
        bucket.setdefault(name, []).append(version)
    if not removed and not added and not reinstalled:
        return UNKNOWN
    saw_lock = False
    saw_reinstall = bool(reinstalled)
    for name in set(removed) | set(added):
        old = removed.get(name, [])
        new = added.get(name, [])
        if old and not new:
            return VENV_AHEAD
        if new and not old:
            saw_lock = True
            continue
        if version_key(min(new, key=version_key)) < version_key(max(old, key=version_key)):
            return VENV_AHEAD
        if version_key(max(new, key=version_key)) > version_key(min(old, key=version_key)):
            saw_lock = True
        else:
            saw_reinstall = True
    if saw_lock:
        return LOCK_AHEAD
    if saw_reinstall:
        return REINSTALL
    return UNKNOWN


def drift_message(direction: str) -> str:
    if direction == LOCK_AHEAD:
        return (
            "the lock is AHEAD of the venv. "
            "`uv sync --all-extras --frozen` catches the venv up to the lock."
        )
    if direction == VENV_AHEAD:
        return (
            "the venv is AHEAD of uv.lock. Do NOT run `uv sync --all-extras` "
            "(it would uninstall or downgrade packages). Reconcile the lock "
            "(`uv lock`) after reviewing the diff, or restore a known-good venv."
        )
    if direction == REINSTALL:
        return (
            "installed versions match uv.lock but packages need a reinstall. "
            "`uv sync --all-extras --frozen` is safe."
        )
    return "could not tell which side is ahead. Refusing to sync."


def main() -> int:
    direction = classify_sync_diff(sys.stdin.read())
    print(direction)
    print(drift_message(direction))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
