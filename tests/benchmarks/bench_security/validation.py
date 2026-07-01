"""Loop-driven validation — prove red/blue/purple against real lab data.

Implements ptai's honeypot + hardened-twin methodology: a use-case PASSES only
if the finding lands on the vulnerable target AND vanishes on the hardened twin
(zero false positives). Reuses existing runners — does not reimplement them.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ._data import _LAB_EXEC_AVAILABLE


@dataclass
class RoleVerdict:
    role: str  # 'red' | 'blue' | 'purple'
    passed: bool
    metric: float
    on_vulnerable: dict | None = None
    on_hardened: dict | None = None
    false_positive: bool = False
    evidence: str = ""


def validate_usecase(
    usecase: dict,
    *,
    lab_exec: bool = False,
    dry_run: bool = False,
) -> dict:
    """Run one validation use-case across vulnerable + hardened twin.

    Red passes: proven on vulnerable AND not-landed on hardened.
    Blue passes: detected on vulnerable telemetry AND zero on hardened.
    Purple passes: red lands AND blue detects AND evasion_delta converges.

    Returns {usecase, status, red/blue/purple RoleVerdicts}.
    """
    if not _LAB_EXEC_AVAILABLE:
        return {
            "usecase": usecase.get("name", "unknown"),
            "status": "indeterminate",
            "reason": "lab exec not available — real data is required",
            "verdicts": {},
        }

    if dry_run:
        return _dry_run_validate(usecase)

    return _run_validate(usecase, lab_exec)


def _dry_run_validate(usecase: dict) -> dict:
    """Plan a validation run without executing."""
    return {
        "usecase": usecase.get("name", "?"),
        "status": "dry_run",
        "target": usecase.get("target", "?"),
        "cve": usecase.get("cve", "?"),
        "models": {
            "red": usecase.get("red_models", []),
            "blue": usecase.get("blue_models", []),
        },
        "hardened_twin": usecase.get("hardened_twin", {}),
        "verdicts_expected": "red=land, blue=detect, purple=converge on vulnerable; zero on hardened",
    }


def _run_validate(usecase: dict, lab_exec: bool) -> dict:
    """Run a real validation use-case (placeholder — integrated loop path)."""
    # In the full implementation, this would:
    # 1. Spin up the vulnerable target
    # 2. Run the red multi-model chain → collect proven findings
    # 3. Run blue detection → telemetry analysis
    # 4. Restore the hardened twin
    # 5. Re-run the same chain → verify zero findings
    return {
        "usecase": usecase.get("name", "?"),
        "status": "placeholder",
        "reason": "full validation requires live lab + exec_chain integration",
        "verdicts": {},
    }
