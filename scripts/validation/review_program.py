"""Validation for the Bully / Crogl review program's derived state."""

from __future__ import annotations

import subprocess

from ._shared import REPO_ROOT
from .registry import register


@register(
    "review_program",
    "HO. review program state is derived and current",
    order=204,
)
def check_review_program() -> tuple[str, str, list[dict[str, str]]]:
    """Require the derived review state to match the latest census and records."""
    test_command = [
        "uv",
        "run",
        "pytest",
        "tests/security/review",
        "tests/security/review_eval",
        "-q",
    ]
    command = ["uv", "run", "python", "scripts/bully_review_state.py", "--check"]
    census_dir = REPO_ROOT / "reports" / "bully_review"
    has_census = any(census_dir.glob("census_*.json"))

    try:
        tests = subprocess.run(
            test_command,
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
            timeout=600,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        detail = f"could not run {' '.join(test_command)}: {exc}"
        return (
            "FAIL",
            detail,
            [{"name": "review product and scorer tests", "status": "FAIL", "detail": detail}],
        )
    test_output = "\n".join(part.strip() for part in (tests.stdout, tests.stderr) if part.strip())
    if tests.returncode != 0:
        detail = f"`{' '.join(test_command)}` exited {tests.returncode}"
        if test_output:
            detail = f"{detail}. Test output: {test_output}"
        return (
            "FAIL",
            detail,
            [{"name": "review product and scorer tests", "status": "FAIL", "detail": detail}],
        )

    try:
        result = subprocess.run(
            command,
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
            timeout=120,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        detail = f"could not run {' '.join(command)}: {exc}"
        return (
            "FAIL",
            detail,
            [{"name": "derived review state", "status": "FAIL", "detail": detail}],
        )

    output = "\n".join(part.strip() for part in (result.stdout, result.stderr) if part.strip())
    if result.returncode == 0:
        detail = "review product/scorer tests pass and derived review state is current"
        return (
            "PASS",
            detail,
            [
                {
                    "name": "review product and scorer tests",
                    "status": "PASS",
                    "detail": test_output,
                },
                {"name": "derived review state", "status": "PASS", "detail": output},
            ],
        )

    if not has_census:
        guidance = "no census exists; run `uv run python scripts/bully_review_defect_census.py --out reports/bully_review`"
    else:
        guidance = "state is absent or stale; run `uv run python scripts/bully_review_state.py --write` after the census"
    detail = f"`{' '.join(command)}` exited {result.returncode}; {guidance}"
    if output:
        detail = f"{detail}. Checker output: {output}"
    return "FAIL", detail, [{"name": "derived review state", "status": "FAIL", "detail": detail}]
