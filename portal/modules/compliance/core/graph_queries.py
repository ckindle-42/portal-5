"""Read-only graph and revision queries used by the reader and MCP adapter."""

from __future__ import annotations

from typing import Any


def links(
    repo: Any, ref: str, direction: str = "both", status: str = "", derivation: str = ""
) -> dict[str, Any]:
    if direction not in ("out", "in", "both"):
        return {"error": "direction must be one of: out, in, both"}
    clauses: list[str] = []
    params: list[Any] = []
    if direction in ("out", "both"):
        clauses.append("src_ref = ?")
        params.append(ref)
    if direction in ("in", "both"):
        clauses.append("dst_ref = ?")
        params.append(ref)
    where = "(" + " OR ".join(clauses or ["src_ref = ?"]) + ")"
    if not clauses:
        params.append(ref)
    if status:
        where += " AND status = ?"
        params.append(status)
    if derivation:
        where += " AND (derivation = ? OR derivation LIKE ? OR derivation LIKE ?)"
        params.extend((derivation, f"%|{derivation}|%", f"%|{derivation}"))
    rows = repo._conn.execute(
        f"""SELECT assertion_id, relation_type, src_ref, dst_ref, status, derivation,
                    confidence, coverage, rationale, valid_from, valid_to, recorded_from,
                    version
             FROM relationship_assertions WHERE {where}
             ORDER BY status, confidence DESC LIMIT 500""",  # noqa: S608
        tuple(params),
    ).fetchall()
    edges = []
    for row in rows:
        edge = dict(row)
        edge["derivations"] = _derivations(edge.get("derivation", ""))
        edges.append(edge)
    return {
        "ref": ref,
        "direction": direction,
        "num_edges": len(edges),
        "edges": edges,
        "note": "status 'proposed' is a candidate, not an established relationship",
    }


def _derivations(value: Any) -> list[str]:
    raw = str(value or "")
    return [part for part in raw.split("|") if part]


def timeline(repo: Any, ref: str) -> dict[str, Any]:
    from portal.modules.compliance.core import reading_assembly
    from portal.modules.compliance.core.revision_compare import semantic_diff

    parsed = reading_assembly.parse_ref(ref)
    logical_id = parsed.logical_id if parsed else ref
    rows = repo._conn.execute(
        """SELECT r.revision_id, r.logical_id, r.version, r.effective_date, r.approved_date,
                      r.authored_date, r.inactive_date, r.lifecycle_status, r.recorded_from,
                      r.alias_path, d.jurisdiction, d.source_kind, d.title
               FROM document_revisions r JOIN source_documents d ON d.logical_id = r.logical_id
               WHERE r.logical_id = ? OR r.logical_id LIKE ? || '%'
               ORDER BY COALESCE(r.effective_date, ''), r.recorded_from""",
        (logical_id, logical_id.rsplit("-", 1)[0]),
    ).fetchall()
    revisions = [dict(row) for row in rows]
    delta: dict[str, Any] = {}
    if parsed:
        family = "-".join(parsed.standard.split("-")[:2])
        versions = sorted(
            {
                str(row["logical_id"]).rsplit("-", 1)[-1]
                for row in revisions
                if str(row["source_kind"]) == "regulatory_standard"
            }
        )
        if len(versions) >= 2:
            try:
                delta = semantic_diff(
                    repo, family=family, version_before=versions[0], version_after=versions[-1]
                )
            except Exception as exc:  # noqa: BLE001 - optional context
                delta = {"error": str(exc)}
    return {"ref": ref, "revisions": revisions, "semantic_delta": delta}


__all__ = ["links", "timeline"]
