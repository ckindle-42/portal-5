"""Tool-call reliability instrument (P5-AUTOSEC-RESELECT).

The chain-test measures execution/coherence/pivot but has NO axis for whether a
model can actually EMIT a well-formed tool call. That blind spot hid the real
`auto-security` failure: VulnLLM-R-7B produces garbled text where JSON should be,
then spirals into meta-commentary about its own errors. This instrument makes
tool-call reliability a first-class, gating axis so a replacement is chosen on the
capability the role actually needs — not domain lore the model can't act on.

Deterministic. No model scores itself. Classifies each assistant turn, aggregates
per-model, and applies a hard gate (a model that can't reliably call tools is
disqualified regardless of its other scores).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

TURN = ("TOOL_CALL_VALID", "TOOL_CALL_MALFORMED", "PROSE_ONLY", "REFUSAL", "SPIRAL")

# Self-referential-error markers: the model talking ABOUT its own broken output
# instead of producing a corrected call. Case-insensitive.
_SPIRAL_MARKERS = (
    "i made an error",
    "i apologize",
    "my previous",
    "as i mentioned",
    "let me correct",
    "that was incorrect",
    "i seem to have",
    "my mistake",
    "the error above",
    "i notice i",
    "correcting myself",
    "i misformatted",
)
_REFUSAL_MARKERS = (
    "i can't help",
    "i cannot assist",
    "i won't",
    "not able to help with that",
    "against my guidelines",
    "i'm not able to provide",
)


def _valid_json_args(raw_args: Any) -> bool:
    if isinstance(raw_args, dict):
        return True
    if not isinstance(raw_args, str) or not raw_args.strip():
        return False
    try:
        return isinstance(json.loads(raw_args), dict)
    except (json.JSONDecodeError, ValueError):
        return False


def _looks_like_attempted_call(text: str) -> bool:
    """Model tried to call a tool in prose (garbled) — a malformed attempt, not
    a clean prose turn. Heuristic: tool-call scaffolding tokens without a parsed call."""
    t = text.lower()
    return any(
        k in t for k in ("tool_call", "function", '"name":', "arguments", "<tool", "```json")
    ) and ("{" in text or "(" in text)


def _marker_count(text: str, markers: tuple[str, ...]) -> int:
    t = text.lower()
    return sum(1 for m in markers if m in t)


def classify_turn(
    response_text: str,
    tool_calls: list[dict[str, Any]] | None,
    tool_schemas: dict[str, Any],
    prev_class: str | None = None,
) -> str:
    """Classify one assistant turn. Order encodes honesty precedence."""
    text = response_text or ""

    # 1. A parsed tool call: valid only if its args are schema-parseable JSON.
    if tool_calls:
        for tc in tool_calls:
            fn = (tc or {}).get("function", tc) if isinstance(tc, dict) else {}
            name = fn.get("name") if isinstance(fn, dict) else None
            args = fn.get("arguments") if isinstance(fn, dict) else None
            if not _valid_json_args(args):
                return "TOOL_CALL_MALFORMED"
            if tool_schemas and name and name not in tool_schemas:
                return "TOOL_CALL_MALFORMED"  # calls a tool that doesn't exist
        return "TOOL_CALL_VALID"

    # 2. No parsed call. Refusal takes precedence (a genuine stop, not a defect).
    if _marker_count(text, _REFUSAL_MARKERS) >= 1:
        return "REFUSAL"

    # 3. Spiral: self-referential error meta-commentary, esp. following a bad turn.
    spiral = _marker_count(text, _SPIRAL_MARKERS)
    if spiral >= 2 or (spiral >= 1 and prev_class in ("TOOL_CALL_MALFORMED", "SPIRAL")):
        return "SPIRAL"

    # 4. Tried to emit a call in prose but nothing parsed -> malformed attempt.
    if _looks_like_attempted_call(text):
        return "TOOL_CALL_MALFORMED"

    # 5. Otherwise it's a plain reasoning/prose turn.
    return "PROSE_ONLY"


@dataclass
class ReliabilityMetrics:
    model: str
    turns: int
    valid: int = 0
    malformed: int = 0
    prose: int = 0
    refusal: int = 0
    spiral: int = 0
    recoveries: int = 0  # malformed/spiral turn immediately followed by a valid call
    recovery_ops: int = 0  # opportunities to recover

    @property
    def valid_rate(self) -> float:
        callish = self.valid + self.malformed
        return self.valid / callish if callish else 0.0

    @property
    def malformed_rate(self) -> float:
        callish = self.valid + self.malformed
        return self.malformed / callish if callish else 0.0

    @property
    def spiral_rate(self) -> float:
        return self.spiral / self.turns if self.turns else 0.0

    @property
    def recovery_rate(self) -> float:
        return self.recoveries / self.recovery_ops if self.recovery_ops else 1.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "model": self.model,
            "turns": self.turns,
            "valid": self.valid,
            "malformed": self.malformed,
            "prose": self.prose,
            "refusal": self.refusal,
            "spiral": self.spiral,
            "valid_rate": round(self.valid_rate, 3),
            "malformed_rate": round(self.malformed_rate, 3),
            "spiral_rate": round(self.spiral_rate, 3),
            "recovery_rate": round(self.recovery_rate, 3),
        }


def aggregate(model: str, classes: list[str]) -> ReliabilityMetrics:
    m = ReliabilityMetrics(model=model, turns=len(classes))
    for i, c in enumerate(classes):
        if c == "TOOL_CALL_VALID":
            m.valid += 1
        elif c == "TOOL_CALL_MALFORMED":
            m.malformed += 1
        elif c == "PROSE_ONLY":
            m.prose += 1
        elif c == "REFUSAL":
            m.refusal += 1
        elif c == "SPIRAL":
            m.spiral += 1
        if c in ("TOOL_CALL_MALFORMED", "SPIRAL"):
            m.recovery_ops += 1
            if i + 1 < len(classes) and classes[i + 1] == "TOOL_CALL_VALID":
                m.recoveries += 1
    return m


@dataclass
class Gate:
    min_valid_rate: float = 0.70
    max_spiral_rate: float = 0.10


def gate(m: ReliabilityMetrics, g: Gate | None = None) -> tuple[bool, str]:
    """Hard disqualification gate: the role needs tool-call reliability first."""
    if g is None:
        g = Gate()
    if m.valid + m.malformed == 0:
        return False, "never emitted a tool call (all prose/refusal) — unusable in an agentic role"
    if m.valid_rate < g.min_valid_rate:
        return False, f"valid_rate {m.valid_rate:.2f} < {g.min_valid_rate} (malformed tool-calls)"
    if m.spiral_rate > g.max_spiral_rate:
        return (
            False,
            f"spiral_rate {m.spiral_rate:.2f} > {g.max_spiral_rate} (meta-commentary spiral)",
        )
    return True, f"valid_rate {m.valid_rate:.2f}, spiral_rate {m.spiral_rate:.2f}"
