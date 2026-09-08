#!/usr/bin/env python3
"""WFE result + manifest contracts.

The central design decision here: a fitness result is NOT a boolean. A boolean
collapses "the model got it wrong" together with "the harness threw", "the tool
call errored", "the budget ran out" and "the output was truncated" — and a
harness defect then reads as a model verdict, which is the exact failure class
the WFE program exists to prevent. Outcomes are therefore an enum, and only a
defined subset counts toward a model-quality denominator.
"""

from __future__ import annotations

import hashlib
import json
import math
import platform
import subprocess
import sys
import urllib.request
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from pathlib import Path

RESULT_SCHEMA_VERSION = "wfe-result-2"
MANIFEST_SCHEMA_VERSION = "wfe-manifest-1"
REPO = Path(__file__).resolve().parents[2]


class Outcome(StrEnum):
    """Terminal state of one task-run."""

    PASS = "PASS"
    FAIL = "FAIL"
    REFUSED = "REFUSED"
    TRUNCATED = "TRUNCATED"
    BUDGET_EXHAUSTED = "BUDGET_EXHAUSTED"
    TOOL_ERROR = "TOOL_ERROR"
    HARNESS_ERROR = "HARNESS_ERROR"
    PENDING_REVIEW = "PENDING_REVIEW"
    BLOCKED = "BLOCKED"


#: Outcomes attributable to the model. These form the denominator of every
#: fitness rate reported. Everything else is quarantined and reported separately.
MODEL_QUALITY_OUTCOMES = frozenset(
    {
        Outcome.PASS,
        Outcome.FAIL,
        Outcome.REFUSED,
        Outcome.TRUNCATED,
        Outcome.BUDGET_EXHAUSTED,
    }
)

#: Outcomes that indicate the INSTRUMENT failed, not the model. Never counted.
INSTRUMENT_OUTCOMES = frozenset({Outcome.TOOL_ERROR, Outcome.HARNESS_ERROR, Outcome.BLOCKED})


def counts_for_quality(outcome: str | Outcome) -> bool:
    return Outcome(outcome) in MODEL_QUALITY_OUTCOMES


@dataclass
class Economics:
    """Per-run cost. Ollama returns these on every response; the pre-repair
    runner discarded them, which is why dimensions 24/25 read as PENDING."""

    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    load_ms: int | None = None
    wall_s: float | None = None
    cold_load: bool = False

    def merge(self, other: Economics) -> None:
        for k in ("prompt_tokens", "completion_tokens", "total_tokens"):
            a, b = getattr(self, k), getattr(other, k)
            if b is not None:
                setattr(self, k, (a or 0) + b)
        if other.load_ms is not None:
            self.load_ms = max(self.load_ms or 0, other.load_ms)


@dataclass
class ResultRow:
    """One (arm x workspace x suite x task x repeat) task-run."""

    schema: str = RESULT_SCHEMA_VERSION
    run_id: str = ""
    campaign_id: str = ""
    stage: str = "screen"
    workspace: str | None = None
    arm: str = ""
    arm_role: str = "incumbent"
    suite: str = ""
    task_id: str = ""
    repeat: int = 0
    outcome: str = Outcome.HARNESS_ERROR.value
    notes: str = ""
    evidence: dict = field(default_factory=dict)
    persona_slug: str | None = None
    prompt_sha: str | None = None
    tool_surface: list[str] = field(default_factory=list)
    tool_surface_proxy: bool = True
    harness: dict = field(default_factory=dict)
    sampling: dict = field(default_factory=dict)
    baked_params: dict = field(default_factory=dict)
    seed: int | None = None
    turns: int = 0
    tool_calls: int = 0
    tool_errors: int = 0
    finish_reason: str | None = None
    economics: dict = field(default_factory=dict)
    env: dict = field(default_factory=dict)
    final_text_head: str = ""
    transcript: list = field(default_factory=list)
    tool_call_log: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def sha12(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", "ignore")).hexdigest()[:12]


def _git_sha() -> str:
    try:
        r = subprocess.run(
            ["git", "-C", str(REPO), "rev-parse", "--short=8", "HEAD"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return r.stdout.strip() or "unknown"
    except Exception:
        return "unknown"


def _ollama_version(base: str = "http://localhost:11434") -> str:
    try:
        with urllib.request.urlopen(f"{base}/api/version", timeout=5) as r:
            return json.load(r).get("version", "unknown")
    except Exception:
        return "unreachable"


def env_fingerprint(base: str = "http://localhost:11434") -> dict:
    """Environment stamp. Dimension 22: an Ollama upgrade changes behaviour, so
    a report must refuse to mix fingerprints without an explicit override."""
    fp = {
        "git_sha": _git_sha(),
        "ollama_version": _ollama_version(base),
        "python": sys.version.split()[0],
        "platform": platform.platform(),
    }
    fp["fingerprint"] = sha12(json.dumps(fp, sort_keys=True))
    return fp


def wilson(passes: int, n: int, z: float = 1.96) -> tuple[float, float, float]:
    """(point, lo, hi) Wilson score interval. Returns (0,0,1) for n == 0."""
    if n <= 0:
        return (0.0, 0.0, 1.0)
    p = passes / n
    d = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = (z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / d
    return (round(p, 4), round(max(0.0, centre - half), 4), round(min(1.0, centre + half), 4))


def intervals_overlap(a: tuple[float, float, float], b: tuple[float, float, float]) -> bool:
    """True when two Wilson intervals overlap — i.e. n is insufficient to
    separate the two arms. Drives the staged escalation to n=3."""
    return not (a[2] < b[1] or b[2] < a[1])
