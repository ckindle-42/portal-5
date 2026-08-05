"""Capture validity — verify a capture actually contains technique-specific
evidence for its declared ground truth, honestly.

Never fabricates or credits missing evidence: a technique with no matching
signal in the real captured telemetry is reported missing, not synthesized.
An earlier version of this module (`enrich_capture`/`get_missing_signals`)
did synthesize plausible-looking signal lines into captures with gaps --
removed 2026-07-24 as unused dead code (no callers anywhere in the codebase)
that also directly contradicted this module's now-current honesty guarantee;
see validate_capture_signals' own docstring for the historical incident that
established never-fabricate as a hard rule here.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parents[5]


def _load_data(name: str) -> Any:
    """Load a data file that was a module-level literal before V1."""
    path = _PROJECT_ROOT / "config" / "security" / f"{name}.json"
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


# ── Expected signals per technique ───────────────────────────────────────────
# Each technique maps to (sourcetype, [lines]) that SHOULD be present in the
# capture for the model to have a chance of detecting it.

EXPECTED_SIGNALS: dict[str, tuple[str, list[str]]] = {
    k: (v[0], v[1]) for k, v in _load_data("capture_enrichment_expected_signals").items()
}

# Regex-based ALTERNATIVE evidence per technique, checked with OR logic
# against the EXPECTED_SIGNALS token-match above (either satisfies the
# technique -- see validate_capture_signals). Exists because a MITRE
# technique can be legitimately proven by evidence shapes EXPECTED_SIGNALS'
# single (sourcetype, [literal example lines]) format can't express: exact
# literal substrings can't match a value that legitimately varies (a uid
# number, a session token), and some techniques are provable via more than
# one real evidence channel depending on target OS/exploit class.
#
# Vulhub LXCs cannot own the host-wide Linux audit facility, so command
# execution must also be recognizable through independently captured response
# and packet evidence. Reflected `id` output is strong evidence, but its
# uid/gid values vary and cannot be represented by literal example lines.
ADDITIONAL_SIGNAL_PATTERNS: dict[str, list[str]] = {
    "T1059": [
        # `id` command output reflected into a response/log/packet capture --
        # e.g. "uid=0(root) gid=0(root) groups=0(root)". Effectively unfakeable
        # by coincidental web content; every Class-A scenario's prompt (see
        # exec_chain.py) explicitly runs `id` as its documented verification
        # step. Blind callback-only CVEs are excluded because the lab network
        # cannot reliably reach Docker Desktop published listener ports.
        r"uid=\d+\([\w.-]+\)\s*gid=\d+\([\w.-]+\)",
    ],
}

# Technique evidence is often scenario-specific. A generic T1190 example for
# SQL injection cannot validate an observed Shellshock, Gremlin, or Spring
# data-binding request. These signatures are deliberately scoped by scenario
# so an ordinary request in one capture cannot certify an unrelated exploit.
SCENARIO_SIGNAL_PATTERNS: dict[str, dict[str, list[str]]] = _load_data(
    "capture_enrichment_scenario_signal_patterns"
)


def validate_capture_signals(scenario: str, telemetry: dict[str, list[str]]) -> dict:
    """Validate that a capture has TECHNIQUE-SPECIFIC signals for its ground
    truth techniques.

    Returns:
        {valid: bool, coverage: float, found: [str], missing: [str],
         unchecked: [str], techniques_checked: int}

    `coverage` is computed only over the CHECKABLE subset (techniques with an
    `EXPECTED_SIGNALS` entry) — `unchecked` techniques (no entry exists yet)
    are never silently credited as found.  The lower-level signal result keeps
    them separate from real misses; replay eligibility applies the stricter
    rule that every declared scorer label must be checked and found.

    Generic attack words cannot prove a specific technique: a token such as
    "failed" in unrelated FTP telemetry must not satisfy missing SSH or process
    evidence. Downstream replay and ablation consumers rely on this gate to
    certify technique-specific evidence without repeating a live capture.
    """
    try:
        from portal.modules.security.core.exec_chain import SCENARIOS
    except ImportError:
        return {
            "valid": False,
            "coverage": 0.0,
            "found": [],
            "missing": [],
            "unchecked": [],
            "techniques_checked": 0,
        }

    sc = SCENARIOS.get(scenario, {})
    gt = sc.get("detect_ground_truth", [])
    if not gt:
        return {
            "valid": False,
            "coverage": 0.0,
            "found": [],
            "missing": [],
            "unchecked": [],
            "techniques_checked": 0,
        }

    all_existing = " ".join(line for lines in telemetry.values() for line in lines)

    found = []
    missing_techniques = []
    unchecked = []
    for technique in gt:
        expected = EXPECTED_SIGNALS.get(technique)
        extra_patterns = [
            *ADDITIONAL_SIGNAL_PATTERNS.get(technique, []),
            *SCENARIO_SIGNAL_PATTERNS.get(scenario, {}).get(technique, []),
        ]
        if not expected and not extra_patterns:
            unchecked.append(technique)
            continue

        _sourcetype, expected_lines = expected or ("", [])
        # A technique is found only if ONE example line's FULL field set is
        # present (AND within that line's own tokens), not any single token
        # pooled across every example (OR across lines is fine — two example
        # lines are two legitimate variants of the same technique).
        #
        # Match every field from one example line together. Pooling fields
        # across examples lets generic values such as Account=administrator or
        # EventCode=4662 falsely prove an unrelated technique.
        has_signal = False
        for line in expected_lines:
            line_tokens = {tok for tok in line.split() if "=" in tok}
            if line_tokens and all(tok in all_existing for tok in line_tokens):
                has_signal = True
                break
        if not has_signal:
            for pattern in extra_patterns:
                if re.search(pattern, all_existing):
                    has_signal = True
                    break
        if has_signal:
            found.append(technique)
        else:
            missing_techniques.append(technique)

    checked_n = len(found) + len(missing_techniques)
    coverage = len(found) / checked_n if checked_n else 0.0
    return {
        "valid": checked_n > 0 and len(found) == checked_n,
        "coverage": round(coverage, 3),
        "found": found,
        "missing": missing_techniques,
        "unchecked": unchecked,
        "techniques_checked": checked_n,
    }
