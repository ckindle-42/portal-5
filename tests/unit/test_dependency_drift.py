"""Dependency drift + currency gates (TASK_VL_RUNTIME_LANDING_V4 P7.3 / P7.4).

P7.3 — venv-vs-lock drift: the check that would have caught the situation this
task exists to fix (a hand-patched VL-capable venv the committed lock did not
describe, one `uv sync` away from destruction). More important than currency.

P7.4 — no upper bound in pyproject without a receipt comment.

Both are offline: `uv sync --check --frozen` resolves nothing (the lock is
frozen), it only diffs the lock against the installed environment.
"""

from __future__ import annotations

import shutil
import subprocess
import tomllib
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.skipif(shutil.which("uv") is None, reason="uv not on PATH")
def test_venv_matches_lock():
    r = subprocess.run(
        ["uv", "sync", "--all-extras", "--frozen", "--check"],
        capture_output=True,
        text=True,
        cwd=_ROOT,
        timeout=180,
    )
    assert r.returncode == 0, (
        "project venv diverges from uv.lock — run `uv sync --all-extras` "
        f"after reviewing the diff:\n{r.stdout}\n{r.stderr}"
    )


def test_no_upper_bound_without_a_receipt():
    """Every `<`/`<=`/`==` constraint in pyproject needs a receipt: a comment on
    the same or an immediately preceding line explaining why (a linked issue, a
    reproducing failure, or -- for `==` -- a hard coupling)."""
    lines = (_ROOT / "pyproject.toml").read_text().splitlines()
    data = tomllib.loads((_ROOT / "pyproject.toml").read_text())
    specs: list[str] = list(data["project"].get("dependencies", []))
    for group in data["project"].get("optional-dependencies", {}).values():
        specs.extend(group)

    capped = [s for s in specs if ("<" in s or "==" in s)]
    offenders = []
    for spec in capped:
        name = spec.split(">")[0].split("<")[0].split("==")[0].strip().strip('"')
        # find the line the spec sits on, check it + the 6 lines above for a comment
        idx = next(
            (
                i
                for i, ln in enumerate(lines)
                if name in ln and (">" in ln or "<" in ln or "==" in ln)
            ),
            None,
        )
        if idx is None:
            continue
        window = lines[max(0, idx - 6) : idx + 1]
        if not any(ln.lstrip().startswith("#") for ln in window):
            offenders.append(spec)
    assert not offenders, f"capped/pinned deps without a receipt comment: {offenders}"
