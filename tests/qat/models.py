"""Unified Release 1.0 QAT data model.

Every stage produces QATResult rows keyed to the QATScenario that ran; the
runner aggregates them into StageSummary objects and report.py renders them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class Status(StrEnum):
    PASS = "PASS"
    WARN = "WARN"
    FAIL = "FAIL"
    SKIP = "SKIP"
    BLOCKED = "BLOCKED"


class DefectClass(StrEnum):
    """Where a FAIL belongs, per the Release 1.0 acceptance vocabulary."""

    PRODUCT_BUG = "PRODUCT_BUG"
    UX_RENDER_GAP = "UX_RENDER_GAP"
    MODEL_QUALITY_GAP = "MODEL_QUALITY_GAP"
    INFRA_ENV_GAP = "INFRA_ENV_GAP"


@dataclass
class RubricCriterion:
    """One operator-scored (1-5) or machine-prefilled rubric line."""

    key: str
    label: str
    guidance: str
    weight: float = 1.0
    auto: bool = False
    score: int | None = None


@dataclass
class QATScenario:
    """One executable acceptance scenario.

    tier orders the cascade (lower runs first); model_slug is the OWUI model
    id the turn addresses (workspace preset id); kind selects the executor
    (chat, browser, artifact, infra, adversarial, note, tts).
    """

    scenario_id: str
    title: str
    stage: int
    phase: str
    tier: int
    model_slug: str
    kind: str = "chat"
    prompts: tuple[str, ...] = ()
    artifact_kind: str = ""
    rubric: tuple[RubricCriterion, ...] = ()
    tools: tuple[str, ...] = ()
    function_calling: bool = False
    browser: bool = False
    tags: tuple[str, ...] = ()
    notes: str = ""
    expected: str = ""
    enabled: bool = True
    requires: tuple[str, ...] = ()
    expected_tools: tuple[str, ...] = ()
    timeout_s: float = 180.0
    attachment: str = ""

    def cascade_key(self) -> tuple[int, str, str]:
        return (self.tier, self.model_slug, self.scenario_id)


@dataclass
class QATResult:
    scenario_id: str
    status: Status = Status.SKIP
    detail: str = ""
    defect_class: DefectClass | None = None
    duration_s: float = 0.0
    chat_id: str = ""
    served_model: str = ""
    backend: str = ""
    artifacts: tuple[str, ...] = ()
    evidence: dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "scenario_id": self.scenario_id,
            "status": self.status.value,
            "detail": self.detail,
            "defect_class": self.defect_class.value if self.defect_class else None,
            "duration_s": round(self.duration_s, 3),
            "chat_id": self.chat_id,
            "served_model": self.served_model,
            "backend": self.backend,
            "artifacts": list(self.artifacts),
            "evidence": self.evidence,
        }

    @classmethod
    def from_dict(cls, row: dict[str, object]) -> QATResult:
        defect = row.get("defect_class")
        return cls(
            scenario_id=str(row.get("scenario_id", "")),
            status=Status(str(row.get("status", "SKIP"))),
            detail=str(row.get("detail", "")),
            defect_class=DefectClass(str(defect)) if defect else None,
            duration_s=float(row.get("duration_s", 0.0) or 0.0),
            chat_id=str(row.get("chat_id", "")),
            served_model=str(row.get("served_model", "")),
            backend=str(row.get("backend", "")),
            artifacts=tuple(str(a) for a in row.get("artifacts") or ()),
            evidence=dict(row.get("evidence") or {}),
        )


@dataclass
class GateReport:
    """Outcome of one inter-phase gate pass."""

    phase: str
    checks: tuple[QATResult, ...] = ()
    memory_used_pct: float = -1.0
    resident_models: int = -1
    ok: bool = False
    blocked: bool = False

    def to_dict(self) -> dict[str, object]:
        return {
            "phase": self.phase,
            "checks": [c.to_dict() for c in self.checks],
            "memory_used_pct": self.memory_used_pct,
            "resident_models": self.resident_models,
            "ok": self.ok,
            "blocked": self.blocked,
        }


@dataclass
class StageSummary:
    stage: int
    phase: str
    results: list[QATResult] = field(default_factory=list)
    gate: GateReport | None = None

    def counts(self) -> dict[str, int]:
        out = {s.value: 0 for s in Status}
        for r in self.results:
            out[r.status.value] += 1
        return out


def classify_defect(
    *,
    infra_hop_failed: bool = False,
    browser_error: bool = False,
    model_output_miss: bool = False,
    tool_misbehaved: bool = False,
) -> DefectClass:
    """Defect class for a FAIL, first match wins in the order operators triage."""
    if infra_hop_failed:
        return DefectClass.INFRA_ENV_GAP
    if browser_error:
        return DefectClass.UX_RENDER_GAP
    if tool_misbehaved:
        return DefectClass.PRODUCT_BUG
    if model_output_miss:
        return DefectClass.MODEL_QUALITY_GAP
    return DefectClass.PRODUCT_BUG
