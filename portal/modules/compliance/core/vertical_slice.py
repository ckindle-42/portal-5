"""The compound CIP-007 R2 analysis plan (END_TO_END Phase 7 / slice P1).

The seven bounded questions are ONE compound analysis over ONE immutable
context — not seven disconnected calls and not a keyword-selected intent
(``compliance_route`` may classify for UI, but the executed plan never drops
alignment, gap, trace, temporal, impact, or scenario components from a
compound request).

:func:`build_context` pins everything once: the governing parts, both
revisions' bundles, the corpus snapshot (source/corpus/index), both clocks,
scope, and the model/prompt configuration ids. Every operation in the plan
shares that context, so its answers are comparable and every result carries
the same fingerprint set. Operation implementations are injected — the plan
is the persisted operation graph, and Phase 10's live run executes it with
the real primitives through the async run lifecycle.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

#: the seven bounded questions of slice §3, in execution order
SEVEN_QUESTIONS: tuple[dict[str, str], ...] = (
    {
        "id": "Q1",
        "op": "requirement_duties",
        "question": "What does current CIP-007-6 R2 require, duty by duty?",
    },
    {
        "id": "Q2",
        "op": "implementing_clauses",
        "question": "Which exact operative internal clauses implement each duty?",
    },
    {
        "id": "Q3",
        "op": "alignment",
        "question": "Are the documented procedures aligned, partial, or misaligned, and why?",
    },
    {
        "id": "Q4",
        "op": "gaps",
        "question": "Where are missing, weaker, conflicting, stale, or ambiguous commitments?",
    },
    {
        "id": "Q5",
        "op": "evidence_connections",
        "question": "What evidence, activity, role, system, or recurring cadence is connected to each duty?",
    },
    {
        "id": "Q6",
        "op": "temporal_diff",
        "question": "What changes between CIP-007-6 and CIP-007-7.1, and what internal material is affected?",
    },
    {
        "id": "Q7",
        "op": "scenario",
        "question": "If a procedure change is proposed, does it remain aligned and what else changes?",
    },
)


@dataclass
class SliceContext:
    """One immutable analysis context shared by every operation."""

    requirement: str
    part_ids: list[str]
    valid_at: str
    known_at: str
    kb_id: str
    scope_text: str
    corpus_dir: str
    revision_before: str
    revision_after: str
    snapshot_fingerprint: str = ""
    snapshot_id: str = ""
    index_generation: str = ""
    corpus_boundary: dict[str, Any] = field(default_factory=dict)
    model_config: dict[str, Any] = field(default_factory=dict)
    bundle_fingerprints: dict[str, str] = field(default_factory=dict)
    run_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "requirement": self.requirement,
            "part_ids": self.part_ids,
            "valid_at": self.valid_at,
            "known_at": self.known_at,
            "kb_id": self.kb_id,
            "scope_text": self.scope_text,
            "corpus_dir": self.corpus_dir,
            "revision_before": self.revision_before,
            "revision_after": self.revision_after,
            "snapshot_fingerprint": self.snapshot_fingerprint,
            "snapshot_id": self.snapshot_id,
            "index_generation": self.index_generation,
            "corpus_boundary": self.corpus_boundary,
            "model_config": self.model_config,
            "bundle_fingerprints": self.bundle_fingerprints,
            "run_id": self.run_id,
        }


@dataclass
class SliceOperation:
    question_id: str
    op: str
    question: str
    args: dict[str, Any] = field(default_factory=dict)
    operation_id: str = ""
    ran: bool = False
    result: Any = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "question_id": self.question_id,
            "op": self.op,
            "question": self.question,
            "args": self.args,
            "operation_id": self.operation_id,
            "ran": self.ran,
        }


def resolve_part_ids(requirement: str) -> list[str]:
    """The register's Part nodes under one requirement ('CIP-007-6 R2'), in
    Part order — the governed duty set of the analysis."""
    from portal.modules.compliance.core.cip_register import Register

    reg = Register.load()
    prefix = f"{requirement} Part "
    return sorted(
        (node.id for node in reg.nodes if node.id.startswith(prefix)),
        key=lambda nid: [int(x) for x in nid.rsplit(" Part ", 1)[1].split(".")],
    )


def build_context(
    requirement: str = "CIP-007-6 R2",
    *,
    valid_at: str,
    known_at: str = "",
    kb_id: str = "operator_corpus",
    scope_text: str = "",
    corpus_dir: str = "coding_task/v9_compliance/LSPG-CIP",
    revision_after: str = "CIP-007-7.1",
) -> SliceContext:
    """Pin ONE immutable analysis context: parts, governing bundles (with
    their fingerprints), the corpus snapshot, and both clocks. A bundle whose
    readiness fails raises ``SourceBundleIncompleteError`` here — the plan is
    never built on a defective governing side."""
    from portal.modules.compliance.core.assessment_source import (
        build_corpus_snapshot,
        resolve_governing_bundle,
    )

    part_ids = resolve_part_ids(requirement)
    if not part_ids:
        raise ValueError(f"no governing Parts found for {requirement!r}")
    fingerprints: dict[str, str] = {}
    for part_id in part_ids:
        bundle = resolve_governing_bundle(part_id)
        readiness = bundle.readiness or {}
        if readiness and not readiness.get("ready", True):
            from portal.modules.compliance.core.regulatory_bundle import (
                SourceBundleIncompleteError,
            )

            raise SourceBundleIncompleteError(
                ref=part_id, failures=list(readiness.get("failures", []))
            )
        fingerprints[part_id] = getattr(bundle, "fingerprint", "")
    snapshot = build_corpus_snapshot(kb_id)
    before_revision = requirement.rsplit(" R", 1)[0]
    return SliceContext(
        requirement=requirement,
        part_ids=part_ids,
        valid_at=valid_at,
        known_at=known_at,
        kb_id=kb_id,
        scope_text=scope_text,
        corpus_dir=corpus_dir,
        revision_before=before_revision,
        revision_after=revision_after,
        snapshot_fingerprint=snapshot.fingerprint,
        snapshot_id=snapshot.snapshot_id,
        index_generation=snapshot.index_generation,
        model_config=_model_config(),
        bundle_fingerprints=fingerprints,
    )


def _model_config() -> dict[str, Any]:
    """The model/prompt configuration the plan's judgment steps will use —
    recorded on the context so results can be reproduced against it."""
    try:
        from portal.modules.compliance.core.runtime_config import build_assessment_context

        context = build_assessment_context(
            "operator_corpus",
            None,
            "",
            "",
            None,  # type: ignore[arg-type]
        )
        seats = [
            {"role": seat.get("role", ""), "model": seat.get("model", "")}
            for seat in getattr(context, "seats", [])
        ]
        return {
            "seats": seats,
            "report_model": getattr(context, "report_model", ""),
        }
    except Exception:  # noqa: BLE001 - configuration is disclosed, never guessed
        return {"seats": [], "report_model": "", "error": "unresolvable at plan time"}


def seven_question_plan(ctx: SliceContext) -> list[SliceOperation]:
    """The compound plan: one operation per bounded question, every operation
    carrying the SAME shared context ids. Deterministic — no keyword routing."""
    shared = {
        "requirement": ctx.requirement,
        "part_ids": ctx.part_ids,
        "valid_at": ctx.valid_at,
        "known_at": ctx.known_at,
        "kb_id": ctx.kb_id,
        "scope_text": ctx.scope_text,
        "snapshot_id": ctx.snapshot_id,
        "snapshot_fingerprint": ctx.snapshot_fingerprint,
        "revision_before": ctx.revision_before,
        "revision_after": ctx.revision_after,
        "corpus_dir": ctx.corpus_dir,
    }
    ops = []
    for spec in SEVEN_QUESTIONS:
        op_args = dict(shared)
        if spec["op"] == "alignment":
            op_args["bundle_fingerprints"] = ctx.bundle_fingerprints
        if spec["op"] == "scenario":
            op_args["overlay"] = None  # supplied at execution time
        ops.append(
            SliceOperation(
                question_id=spec["id"], op=spec["op"], question=spec["question"], args=op_args
            )
        )
    return ops


def dry_run(ctx: SliceContext) -> dict[str, Any]:
    """The persisted plan without execution: all seven operations sharing one
    consistent source, corpus, index, time, and model context."""
    operations = seven_question_plan(ctx)
    return {
        "plan": "seven_question_cip007_r2",
        "run_id": ctx.run_id,
        "context": ctx.to_dict(),
        "n_operations": len(operations),
        "operations": [op.to_dict() for op in operations],
        "shared_context_ids": {
            "snapshot_id": ctx.snapshot_id,
            "snapshot_fingerprint": ctx.snapshot_fingerprint,
            "index_generation": ctx.index_generation,
            "valid_at": ctx.valid_at,
            "known_at": ctx.known_at or "latest recorded knowledge",
            "kb_id": ctx.kb_id,
            "model_config": ctx.model_config,
        },
    }


def execute_plan(
    ctx: SliceContext,
    op_impls: dict[str, Any],
    *,
    run_id: str = "",
    scenario_overlay: Any = None,
) -> dict[str, Any]:
    """Execute the plan with injected operation implementations. Every result
    carries the operation id, the shared snapshot fingerprint, and the same
    clocks. A missing implementation is a recorded planning failure — the
    answer can never be composed from an operation that did not run."""
    plan = seven_question_plan(ctx)
    ctx.run_id = run_id or ctx.run_id
    executed: list[dict[str, Any]] = []
    for index, op in enumerate(plan):
        op.operation_id = f"{ctx.run_id or 'plan'}#{index + 1}:{op.op}"
        impl = op_impls.get(op.op)
        if impl is None:
            executed.append({**op.to_dict(), "error": f"no implementation for op {op.op!r}"})
            continue
        args = dict(op.args)
        if op.op == "scenario" and scenario_overlay is not None:
            args["overlay"] = scenario_overlay
        op.result = impl(**args)
        op.ran = True
        executed.append({**op.to_dict(), "result_available": op.result is not None})
    return {
        "run_id": ctx.run_id,
        "context_fingerprint": ctx.snapshot_fingerprint,
        "operations": executed,
        "answers": {op.op: op.result for op in plan if op.ran},
    }
