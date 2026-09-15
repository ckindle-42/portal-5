"""Execute the seven-question CIP-007 R2 arm (END_TO_END Phase 10 / slice P6).

One shared context (``vertical_slice.build_context``), one canonical run ID,
and every operation implemented over the real primitives:

* ``requirement_duties``     — governing bundles + decompositions (deterministic)
* ``implementing_clauses``   — retrieval + candidate closure, source functions (deterministic)
* ``alignment``              — the shared assessment service per Part (model: reading
                                judgment + council cross-check + alignment diagnostic)
* ``gaps``                   — projected from the same assessment results
* ``evidence_connections``   — store traversal duty → control/activity/role/system/evidence
* ``temporal_diff``          — semantic CIP-007-6 → 7.1 obligation delta + the internal
                                material the run itself cited (grounded impact)
* ``scenario``               — isolated overlay reassessment over the same snapshot

Duty→implementation paths discovered by the reading are persisted as
relationship assertions with ``derivation='semantic_reading'`` (proposed,
visibly labeled), so trace/impact traversal works in both directions without
promoting anything to established fact by fiat.
"""

from __future__ import annotations

from typing import Any


def _op_requirement_duties(part_ids: list[str], **_shared: Any) -> dict[str, Any]:
    from portal.modules.compliance.core.assessment_source import resolve_governing_bundle
    from portal.modules.compliance.core.repository import Repository

    repo = Repository()
    duties: list[dict[str, Any]] = []
    for part_id in part_ids:
        bundle = resolve_governing_bundle(part_id)
        atoms = repo._conn.execute(
            """SELECT atom_id, COALESCE(clause_text, ''), actor, modality, action,
                      deadline_cadence, exceptions_json
               FROM obligation_atoms WHERE node_id = ? ORDER BY atom_id""",
            (part_id,),
        ).fetchall()
        deps = repo._conn.execute(
            "SELECT depends_on_ref FROM obligation_dependencies WHERE node_id = ?",
            (part_id,),
        ).fetchall()
        duties.append(
            {
                "part_id": part_id,
                "part_text": bundle.part_text,
                "lead_in": bundle.lead_in,
                "measures": [m.get("text", "") for m in bundle.measures],
                "technical_basis_count": len(bundle.technical_basis),
                "applicable_systems": bundle.applicable_systems,
                "revision_id": bundle.revision_id,
                "readiness": bundle.readiness,
                "atoms": [
                    {
                        "atom_id": a[0],
                        "clause_text": a[1],
                        "actor": a[2],
                        "modality": a[3],
                        "action": a[4],
                        "deadline_cadence": a[5],
                        "exceptions": a[6],
                    }
                    for a in atoms
                ],
                "depends_on": [d[0] for d in deps],
            }
        )
    return {"duties": duties}


def _op_implementing_clauses(
    part_ids: list[str], kb_id: str, snapshot_fingerprint: str, **_shared: Any
) -> dict[str, Any]:
    from portal.modules.compliance.core.assessment_source import (
        acquire_candidates,
        resolve_governing_bundle,
    )
    from portal.modules.compliance.core.candidate_closure import enrich_reading_packet
    from portal.modules.compliance.core.cip_register import Register
    from portal.modules.compliance.core.reading import build_reading_packet
    from portal.modules.compliance.core.repository import Repository

    repo = Repository()
    reg = Register.load()
    by_id = {n.id: n for n in reg.nodes}
    packets: dict[str, Any] = {}
    for part_id in part_ids:
        node = by_id[part_id]
        candidate_set = acquire_candidates(node, kb_id=kb_id)
        bundle = resolve_governing_bundle(part_id)
        request = type(
            "R",
            (),
            {
                "requirement_id": part_id,
                "governing": bundle,
                "candidate_set": candidate_set,
                "metadata": {},
                "snapshot": None,
            },
        )()
        packet = build_reading_packet(request, repository=repo)
        packets[part_id] = {
            "packet": enrich_reading_packet(repo, packet, requirement_id=part_id),
            "n_candidates": len(candidate_set.records) if candidate_set else 0,
            "snapshot_fingerprint": snapshot_fingerprint,
        }
    return {"packets": packets}


def _op_alignment(
    part_ids: list[str],
    kb_id: str,
    scope_text: str,
    valid_at: str,
    known_at: str,
    run_id: str,
    **_shared: Any,
) -> dict[str, Any]:
    from portal.modules.compliance.core.assessment_runs import assess_requirements_now

    results = assess_requirements_now(
        part_ids,
        kb_id=kb_id,
        scope_text=scope_text,
        effective_on=valid_at,
        known_at=known_at,
        run_id=run_id,
    )
    return {
        "run_id": run_id,
        "results": [_safe_asdict(r) for r in results],
    }


def _safe_asdict(result: Any) -> dict[str, Any]:
    from dataclasses import asdict

    try:
        payload = asdict(result)
    except Exception:  # noqa: BLE001
        payload = {"requirement_id": getattr(result, "requirement_id", "")}
    # keep the raw reading packet/response out of the routed payload; they are
    # retained in the run's stored assessment rows instead
    receipt = payload.get("receipt") or {}
    explanation = receipt.get("explanation") or {}
    raw = explanation.get("raw") or {}
    if raw:
        explanation["raw"] = {
            "response": raw.get("response"),
            "request_bytes": len(str(raw.get("request", ""))),
        }
    return payload


def _op_gaps(alignment_result: dict[str, Any] | None = None, **_shared: Any) -> dict[str, Any]:
    if alignment_result is None:
        return {"error": "gaps runs after alignment; alignment did not run"}
    rows: list[dict[str, Any]] = []
    for result in alignment_result.get("results", []):
        gaps = result.get("gaps") or []
        for gap in gaps:
            rows.append(
                {
                    "part_id": result.get("requirement_id", ""),
                    "gap_id": gap.get("gap_id", ""),
                    "kind": gap.get("kind", ""),
                    "missing_commitment": gap.get("missing_commitment", ""),
                    "governing_slice_ids": gap.get("governing_slice_ids", []),
                    "counterevidence": gap.get("internal_counterevidence_slice_ids", []),
                }
            )
        if result.get("unresolved_code"):
            rows.append(
                {
                    "part_id": result.get("requirement_id", ""),
                    "gap_id": "",
                    "kind": result.get("unresolved_code"),
                    "missing_commitment": "",
                    "governing_slice_ids": [],
                    "counterevidence": [],
                }
            )
    return {"gaps": rows, "n_gaps": len(rows)}


def _op_evidence_connections(
    part_ids: list[str], run_id: str = "", **_shared: Any
) -> dict[str, Any]:
    from portal.modules.compliance.core.repository import Repository
    from portal.modules.compliance.core.traceability import trace

    repo = Repository()
    connections: dict[str, Any] = {}
    for part_id in part_ids:
        result = trace(repo, part_id, direction="both")
        connections[part_id] = {
            "paths": result.get("paths", []),
            "truncated": result.get("truncated", False),
        }
    return {"connections": connections, "run_id": run_id}


def _op_temporal_diff(
    revision_before: str,
    revision_after: str,
    alignment_result: dict[str, Any] | None = None,
    **_shared: Any,
) -> dict[str, Any]:
    from portal.modules.compliance.core.repository import Repository
    from portal.modules.compliance.core.revision_compare import semantic_diff

    repo = Repository()
    family = revision_before.rsplit("-", 1)[0]
    diff = semantic_diff(
        repo,
        family=family,
        version_before=revision_before.rsplit("-", 1)[1],
        version_after=revision_after.rsplit("-", 1)[1],
    )
    # grounded impact: the internal material THIS run cited for each changed duty
    affected: dict[str, list[str]] = {}
    if alignment_result:
        for result in alignment_result.get("results", []):
            part_id = result.get("requirement_id", "")
            documents: set[str] = set()
            for covered in result.get("covered") or []:
                if covered.get("document_id"):
                    documents.add(str(covered["document_id"]))
                for sid in covered.get("internal_slice_ids", []):
                    if sid:
                        documents.add(str(sid))
            if documents:
                affected[part_id] = sorted(documents)
    diff["affected_internal"] = affected
    return diff


def _op_scenario(
    request: Any, overlay: Any = None, snapshot_fingerprint: str = "", **_shared: Any
) -> dict[str, Any]:
    """Isolated proposed-edit reassessment over the SAME pinned snapshot."""
    from portal.modules.compliance.core.assessment import assess_part
    from portal.modules.compliance.core.assessment_source import (
        build_assessment_request,
        materialize_overlay,
    )
    from portal.modules.compliance.core.determination import ScenarioEdit, ScenarioOverlay
    from portal.modules.compliance.core.runtime_config import build_assessment_context

    if overlay is None:
        return {
            "executed": False,
            "note": "no proposed edit supplied; supply scenario_edits to reassess",
        }
    from portal.modules.compliance.core.repository import Repository

    repo = Repository()
    requirement_id = request["part_id"]
    base = build_assessment_request(
        requirement_id,
        kb_id=request["kb_id"],
        scope_text=request["scope_text"],
        effective_on=request["valid_at"],
    )
    context = build_assessment_context(request["kb_id"], None, request["valid_at"], "", repo)
    base_result = assess_part(base, context)

    edits = [
        ScenarioEdit(
            operation=e["operation"],
            target_document=e["target_document"],
            chunk_id=e.get("chunk_id", ""),
            target_section=e.get("target_section", ""),
            char_start=e.get("char_start", 0),
            char_end=e.get("char_end", 0),
            expected_old_hash=e.get("expected_old_hash", ""),
            new_text=e["new_text"],
            label=e.get("label", ""),
        )
        for e in overlay.get("edits", [])
    ]
    overlay_obj = ScenarioOverlay(
        overlay_id="",
        base_snapshot_fingerprint=base.snapshot.fingerprint if base.snapshot else "",
        edits=edits,
    )
    virtual = materialize_overlay(base, overlay_obj)
    scenario_result = assess_part(virtual, context)
    return {
        "executed": True,
        "part_id": requirement_id,
        "before": {
            "documentary_coverage": base_result.documentary_coverage,
            "alignment": getattr(base_result, "documentary_alignment", ""),
        },
        "after": {
            "documentary_coverage": scenario_result.documentary_coverage,
            "alignment": getattr(scenario_result, "documentary_alignment", ""),
        },
        "overlay_fingerprint": virtual.overlay.overlay_id if virtual.overlay else "",
        "isolated": True,
    }


def persist_reading_edges(repo: Any, run_id: str, alignment_result: dict[str, Any]) -> int:
    """Persist duty→control IMPLEMENTS edges from the reading's covered
    commitments: proposed, derivation='semantic_reading', with exact slice-id
    citations. Visible in discovery and reverse traversal; never established
    by fiat."""
    import hashlib

    from portal.modules.compliance.core.models import RelationshipAssertion
    from portal.modules.compliance.core.temporal import now_iso

    count = 0
    for result in alignment_result.get("results", []):
        part_id = result.get("requirement_id", "")
        for covered in result.get("covered") or []:
            internal_ids = covered.get("internal_slice_ids") or []
            if not internal_ids:
                continue
            rel_id = (
                "rel-read-"
                + hashlib.sha256(
                    f"{run_id}|{part_id}|{covered.get('commitment', '')}".encode()
                ).hexdigest()[:16]
            )
            rel = RelationshipAssertion(
                rel_id,
                "IMPLEMENTS",
                part_id,
                None,
                f"control-{hashlib.sha256(str(covered.get('commitment', '')).encode()).hexdigest()[:12]}",
                None,
                part_id.split(" ")[0],
                [
                    {
                        "governing_slice_ids": covered.get("governing_slice_ids", []),
                        "internal_slice_ids": internal_ids,
                        "commitment": covered.get("commitment", ""),
                    }
                ],
                status="proposed",
                rationale=f"semantic reading pass (run {run_id})",
                derivation="semantic_reading",
                recorded_from=now_iso(),
            )
            try:
                repo.propose_relationship(rel)
                count += 1
            except Exception:  # noqa: BLE001 - duplicate edge in a rerun is fine
                continue
    return count


def run_seven_question(
    requirement: str = "CIP-007-6 R2",
    *,
    valid_at: str,
    known_at: str = "",
    kb_id: str = "operator_corpus",
    scope_text: str = "",
    scenario_part_id: str = "",
    scenario_edits: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """The compound arm over the live corpus, with real implementations."""
    from portal.modules.compliance.core import vertical_slice
    from portal.modules.compliance.core.repository import Repository

    repo = Repository()
    ctx = vertical_slice.build_context(
        requirement, valid_at=valid_at, known_at=known_at, kb_id=kb_id, scope_text=scope_text
    )
    run_id = repo.create_run(
        {
            "requirement": requirement,
            "plan": "seven_question_cip007_r2",
            "kb_id": kb_id,
            "valid_at": valid_at,
            "known_at": known_at,
            "snapshot_fingerprint": ctx.snapshot_fingerprint,
        },
        status="RUNNING",
    )
    ctx.run_id = str(run_id)

    alignment_box: dict[str, Any] = {}

    def alignment(**kwargs: Any) -> dict[str, Any]:
        kwargs["run_id"] = ctx.run_id
        result = _op_alignment(**kwargs)
        alignment_box["result"] = result
        persist_reading_edges(repo, ctx.run_id, result)
        return result

    def gaps(**kwargs: Any) -> dict[str, Any]:
        return _op_gaps(alignment_result=alignment_box.get("result"), **kwargs)

    def temporal_diff(**kwargs: Any) -> dict[str, Any]:
        return _op_temporal_diff(
            revision_before=kwargs.pop("revision_before"),
            revision_after=kwargs.pop("revision_after"),
            alignment_result=alignment_box.get("result"),
            **kwargs,
        )

    scenario_request = {
        "part_id": scenario_part_id or (ctx.part_ids[1] if ctx.part_ids else ""),
        "kb_id": kb_id,
        "scope_text": scope_text,
        "valid_at": valid_at,
    }

    def scenario(**kwargs: Any) -> dict[str, Any]:
        overlay = kwargs.pop("overlay", None)
        return _op_scenario(
            scenario_request,
            overlay=(
                {"edits": scenario_edits}
                if scenario_edits
                else (overlay if isinstance(overlay, dict) else None)
            ),
            **kwargs,
        )

    impls = {
        "requirement_duties": _op_requirement_duties,
        "implementing_clauses": _op_implementing_clauses,
        "alignment": alignment,
        "gaps": gaps,
        "evidence_connections": _op_evidence_connections,
        "temporal_diff": temporal_diff,
        "scenario": scenario,
    }
    executed = vertical_slice.execute_plan(
        ctx,
        impls,
        run_id=ctx.run_id,
        scenario_overlay=({"edits": scenario_edits} if scenario_edits else None),
    )
    repo.update_run(ctx.run_id, status="COMPLETE")
    executed["context"] = ctx.to_dict()
    return executed
