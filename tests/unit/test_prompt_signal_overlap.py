"""Lint test: multi-word signals in WORKSPACE_PROMPTS / PERSONA_PROMPTS
must not already appear in the prompt that elicits them.

A multi-word signal that's a substring of its own prompt is an always-pass —
the model just has to echo the question to satisfy it. Single-word signals
are forgiven (they are usually domain terms that naturally appear in both).

Enumerates known violations (waiver list) and fails on any new ones.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
import portal5_acceptance_v6 as v6  # noqa: E402

WAIVERS: dict[tuple[str, str], str] = {
    ("auto-spl", "splunk"): "term is the technology being asked about",
    ("auto-vision", "image"): "vision domain term unavoidable",
    ("soc2auditor", "type ii"): "SOC 2 domain term, part of audit standard name",
    ("pcidssassessor", "5 million"): "PCI DSS transaction threshold domain term",
    ("typescriptengineer", "discriminated union"): "TypeScript language feature name",
    ("typescriptengineer", "type guard"): "TypeScript language feature name",
}


def _overlaps(prompt: str, signals: list[str]) -> list[str]:
    """Return multi-word signals (containing a space) that overlap the prompt.
    Single-word signals are forgiven — they are almost always domain terms."""
    p = prompt.lower()
    return [s for s in signals if " " in s and s.lower() in p and len(s) >= 3]


def test_workspace_signals_dont_overlap_prompts():
    violations: list[str] = []
    for ws, entry in v6.WORKSPACE_PROMPTS.items():
        # Entry is (prompt, signals) or, for a canonicalized former-alias
        # entry (BUILD_PROGRAM_ALIAS_RETIRE_V1.md Phase 3), (prompt, signals,
        # route_params) — route_params isn't relevant to this overlap check.
        prompt, signals = entry[0], entry[1]
        for s in _overlaps(prompt, signals):
            if (ws, s.lower()) in WAIVERS:
                continue
            violations.append(f"{ws}: signal {s!r} appears in prompt")
    assert not violations, "Prompt-signal overlaps:\n  " + "\n  ".join(violations)


def test_persona_signals_dont_overlap_prompts():
    violations: list[str] = []
    for slug, (prompt, signals) in v6.PERSONA_PROMPTS.items():
        for s in _overlaps(prompt, signals):
            if (slug, s.lower()) in WAIVERS:
                continue
            violations.append(f"{slug}: signal {s!r} appears in prompt")
    assert not violations, "Prompt-signal overlaps:\n  " + "\n  ".join(violations)
