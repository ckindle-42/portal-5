"""Shared primitives for capability-oriented model probes (V11).

Fixes the V10 methodology failures documented in TASK_BENCH_METHODOLOGY_V11:
  - extract_final_answer() strips ALL leading reasoning, not just <think> tags
  - reasoning-aware token budgets (see RUNNERS in bench_capability.py)
  - capability scoring (execute/validate) rather than regex-on-preamble
"""

from __future__ import annotations

import re
import subprocess
import sys
import tempfile
from pathlib import Path

# Markers that signal the model has stopped reasoning and started answering.
# Ordered: the earliest match wins as the answer boundary.
_ANSWER_BOUNDARIES = [
    r"</think>",
    r"\n#{1,6}\s+\w",  # a markdown header
    r"\n```",  # a fenced code block
    r"\n\s*\d+[.)]\s+\S",  # a numbered list item
    r"\n(?:Answer|Final answer|Solution|Here(?:'|\u2019)s)\b",
]

# Prose preambles a reasoning-in-plain-text model emits before the real answer.
_PREAMBLE_PATTERNS = [
    r"^\s*(?:The user (?:wants|is asking|asked)|Thinking Process|Let me think|"
    r"Let'?s think|I need to|First,? I|Okay,? (?:let|so)|Reasoning:)\b",
]


def extract_final_answer(text: str) -> str:
    """Return the model's final answer with leading reasoning removed.

    Handles three cases the V10 _strip_think() missed:
      1. <think>...</think> tagged reasoning (strip the block)
      2. bare-prose reasoning preamble ("The user wants...", "Thinking Process:")
         followed by the real answer at the first structural boundary
      3. clean answers with no reasoning (returned unchanged)
    """
    if not text:
        return ""
    # Case 1: tagged reasoning anywhere — drop all think blocks first.
    stripped = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    # If an unclosed <think> remains (truncated), drop everything up to it.
    stripped = re.sub(r"<think>.*\Z", "", stripped, flags=re.DOTALL)
    stripped = stripped.strip()

    # Case 2: does it open with a prose reasoning preamble?
    opens_with_preamble = any(re.match(p, stripped, re.IGNORECASE) for p in _PREAMBLE_PATTERNS)
    if opens_with_preamble:
        # Find the earliest answer boundary and return from there.
        earliest = None
        for pat in _ANSWER_BOUNDARIES:
            m = re.search(pat, stripped)
            if m and (earliest is None or m.start() < earliest):
                earliest = m.start()
        if earliest is not None:
            return stripped[earliest:].strip()
        # Preamble but no detectable answer boundary — return as-is so the
        # scorer can still see (and fail) it honestly rather than scoring "".
    return stripped


def run_python_against_tests(source: str, test_source: str, timeout: int = 20) -> tuple[bool, str]:
    """Write source + test to a temp dir, run pytest, return (passed, output).

    This is the heart of capability (not format) scoring for coding probes:
    the code either runs and passes the tests or it doesn't.
    """
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        (d / "solution.py").write_text(source)
        (d / "test_solution.py").write_text(test_source)
        try:
            proc = subprocess.run(
                [sys.executable, "-m", "pytest", "-q", str(d / "test_solution.py")],
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=str(d),
            )
        except subprocess.TimeoutExpired:
            return False, "TIMEOUT"
        return proc.returncode == 0, (proc.stdout + proc.stderr)[-2000:]


def extract_code_block(text: str, lang: str = "python") -> str:
    """Pull the first fenced code block (optionally language-tagged). Empty if none."""
    body = extract_final_answer(text)
    m = re.search(rf"```(?:{lang}|py)?\s*\n(.*?)\n```", body, re.DOTALL | re.IGNORECASE)
    if m:
        return m.group(1)
    # Fall back: a bare ``` block with no language tag.
    m = re.search(r"```\s*\n(.*?)\n```", body, re.DOTALL)
    return m.group(1) if m else ""


def parse_tcpdump_filter(cmd: str) -> dict:
    """Structurally validate a tcpdump command instead of regex-matching a fence.

    Returns a dict of capability facts the scorer can grade with partial credit.
    """
    facts = {
        "is_tcpdump": bool(re.search(r"\btcpdump\b", cmd)),
        "has_interface": bool(re.search(r"-i\s+\S+", cmd)),
        "has_bpf_primitive": bool(
            re.search(r"\b(?:host|port|portrange|tcp|udp|src|dst|net)\b", cmd)
        ),
        "targets_http_ports": bool(re.search(r"\bport\s+(?:80|443|8000|8080)\b", cmd)),
        "writes_pcap_or_limits": bool(re.search(r"-w\s+\S+|-c\s+\d+", cmd)),
    }
    facts["capability_score"] = round(
        sum(
            (
                facts["is_tcpdump"],
                facts["has_bpf_primitive"],
                facts["targets_http_ports"],
            )
        )
        / 3.0,
        2,
    )
    return facts
