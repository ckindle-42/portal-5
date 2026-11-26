"""Portal 5 — Compliance Controls & Evidence MCP.

Authoritative control-catalog lookup (NIST SP 800-53 Rev5, CSF 2.0),
cross-framework mapping, NERC CIP requirement lookup, and CIP-007-6 R2
patch-evidence scaffolding. Read-only; catalogs are cached locally.

Port: 8937 (COMPLIANCE_MCP_PORT or MCP_PORT env override).
"""

from __future__ import annotations

import asyncio
import collections
import contextvars
import dataclasses
import datetime
import functools
import json
import logging
import os
import re
import time
import urllib.request
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Annotated, Any, cast

from mcp.server import MCPServer
from pydantic import BeforeValidator
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from portal.modules.compliance.core import cancellation as _cancellation
from portal.modules.compliance.core import search_service as _search_service
from portal.modules.compliance.core.addressing import (
    clip as _clip,
)
from portal.modules.compliance.core.addressing import (
    neighbors as _neighbors,
)
from portal.modules.compliance.core.addressing import (
    provenance as _provenance,
)
from portal.modules.compliance.core.addressing import (
    resolve_by_address as _resolve_by_address,
)
from portal.modules.compliance.core.addressing import (
    with_cite_header as _with_cite_header,
)
from portal.modules.compliance.core.graph_queries import links as _graph_links
from portal.modules.compliance.core.graph_queries import timeline as _graph_timeline
from portal.platform.data_loader import load_data
from portal.platform.mcp_host.build_info import build_info
from portal.platform.mcp_host.eval_scope import bind_native_context
from portal.platform.mcp_host.tool_support import align_native_tools

logger = logging.getLogger(__name__)
_port = int(os.environ.get("COMPLIANCE_MCP_PORT") or os.environ.get("MCP_PORT", "8937"))
mcp = MCPServer(
    "compliance",
    instructions="Authoritative compliance control lookup — NIST SP 800-53 Rev5, CSF 2.0, "
    "a NERC CIP requirement map, an OLIR-style crosswalk seed, and a CIP-007-6 R2 "
    "patch-evidence bridge into vulnintel. Every control carries an id + source for citation.",
)

# TASK_RAG_COMPOSITION_SEAM_V1 P7: the compliance retrieval composition. Its
# routes are registered here, before the generic /tools/{tool_name} handler, so
# they resolve first. Defensive import — the retrieval stack (lancedb/pyarrow)
# ships in Dockerfile.mcp; a host without the research extra keeps the catalog
# tools working without it.
try:
    from portal.modules.compliance.tools.compliance_retrieval import (
        register_compliance_retrieval_routes,
    )

    register_compliance_retrieval_routes(mcp)
except ImportError as _e:  # pragma: no cover - depends on optional deps
    logger.warning("compliance retrieval routes unavailable: %s", _e)

_DATA = Path(__file__).resolve().parent.parent / "data"
_cache: dict[str, Any] = {}

# distilled from usnistgov/oscal-content by scripts/refresh_compliance_catalogs.py
_OSCAL_800_53 = (
    "https://raw.githubusercontent.com/usnistgov/oscal-content/main/nist.gov/"
    "SP800-53/rev5/json/NIST_SP-800-53_rev5_catalog-min.json"
)
_OSCAL_CSF = (
    "https://raw.githubusercontent.com/usnistgov/oscal-content/main/nist.gov/"
    "CSF/v2.0/json/NIST_CSF_v2.0_catalog-min.json"
)
_FRAMEWORKS = {
    "nist_800_53": ("nist_800_53_rev5", "NIST SP 800-53 Rev5"),
    "csf_2_0": ("csf_2_0", "NIST CSF 2.0"),
}


def _catalog(name: str) -> dict[str, Any]:
    if name not in _cache:
        p = _DATA / f"{name}.json"
        loaded = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
        _cache[name] = loaded if isinstance(loaded, dict) else {}
    return cast("dict[str, Any]", _cache[name])


def _controls(framework: str) -> dict[str, Any]:
    fname = _FRAMEWORKS.get(framework, (framework, framework))[0]
    return cast("dict[str, Any]", _catalog(fname).get("controls", {}))


@mcp.tool()
def lookup_control(control_id: str, framework: str = "nist_800_53") -> dict[str, Any]:
    """Return the authoritative text for a control id (e.g. 'AC-2' in NIST 800-53, 'PR.AA-05' in CSF 2.0)."""
    try:
        if framework not in _FRAMEWORKS:
            return {"error": f"framework not loaded: {framework} (have: {sorted(_FRAMEWORKS)})"}
        cid = control_id.strip().upper()
        entry = _controls(framework).get(cid)
        source = _FRAMEWORKS[framework][1]
        if not entry:
            return {
                "framework": framework,
                "id": cid,
                "found": False,
                "note": "not found; run refresh_catalogs if the catalog is empty",
            }
        return {"framework": framework, "id": cid, "source": source, "found": True, **entry}
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)}


@mcp.tool()
def search_controls(
    keyword: str, framework: str = "nist_800_53", top_k: int = 10
) -> dict[str, Any]:
    """Keyword search across control titles/statements; returns citable ids."""
    try:
        if framework not in _FRAMEWORKS:
            return {"error": f"framework not loaded: {framework}"}
        kw = keyword.lower()
        hits = [
            {"id": cid, "title": e.get("title", "")}
            for cid, e in sorted(_controls(framework).items())
            if kw in e.get("title", "").lower() or kw in e.get("statement", "").lower()
        ][:top_k]
        return {
            "framework": framework,
            "source": _FRAMEWORKS[framework][1],
            "keyword": keyword,
            "count": len(hits),
            "controls": hits,
        }
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)}


def _register_part(
    conn: Any,
    reg: Any,
    node: Any,
    decompose: Any,
    expression_for: Any,
    when: str,
    today: str,
) -> dict[str, Any]:
    """One register-resolved governing part with its atoms and sourced
    effectivity (the register path of ``compliance_requirement``)."""
    anchors = []
    try:
        row = conn.execute(
            "SELECT source_anchor_ids_json FROM obligation_atoms WHERE node_id = ? ORDER BY atom_id LIMIT 1",
            (node.id,),
        ).fetchone()
        if row:
            anchors = json.loads(row[0])
    except Exception:  # pragma: no cover - compatibility fallback
        anchors = []
    anchors = anchors or [f"{node.source_pdf}#pages={','.join(map(str, node.source_pages))}"]
    parent = next(
        (
            candidate.verbatim_text
            for candidate in reg.nodes
            if candidate.standard == node.standard
            and candidate.requirement == node.requirement
            and candidate.granularity == "requirement"
        ),
        "",
    )
    atoms = decompose(
        node.id,
        node.verbatim_text,
        lead_in=parent if node.granularity == "part" else "",
        anchor_ids=anchors,
    )
    return {
        "id": node.id,
        "standard": node.standard,
        "verbatim_text": node.verbatim_text,
        "atoms": [atom.to_record() for atom in atoms],
        "expression": expression_for(atoms, node.verbatim_text),
        "conditions": node.applicable_systems,
        "effectivity": {
            "valid_from": node.valid_from,
            "valid_to": node.valid_to,
            "anchor": reg.lifecycle_source,
        },
        "temporal_label": "historical" if node.valid_to or when < today else "current",
    }


def _payload_pricing() -> dict[str, Any]:
    """The declared limits and the served ceiling, as the payload guard prices
    them (DATA_TRUTH DD3c: every payload-bearing tool uses this one helper)."""
    from portal.modules.compliance.core.runtime_config import (
        reading_context_limits,
        reading_route_ceiling,
    )

    limits = reading_context_limits()
    ceiling = reading_route_ceiling()
    return {
        "context_limit": min(limits["context_limit"], ceiling or limits["context_limit"]),
        "predict_limit": limits["predict_limit"],
        "served_ceiling": ceiling,
    }


@mcp.tool()
def compliance_requirement(
    requirement: str,
    scope: str = "",
    valid_at: str = "",
    known_at: str = "",
    max_chars: int = 6000,
    include_dual_document: bool = False,
) -> dict[str, Any]:
    """Resolve governing requirements by validity interval and return atoms.

    Phase 5: both clocks are applied. ``valid_at`` selects what governed the
    requested moment and ``known_at`` selects what this store knew then —
    a fact already true but not yet recorded (late-recorded) is reported as
    ``UNKNOWN_KNOWLEDGE`` instead of being silently included or dropped.
    Effectivity comes from the canonical store's registry-sourced
    assertions, never from filenames.

    Text ceiling: ``max_chars`` (default 6,000) bounds the verbatim text this
    ONE call returns, shared across the matched parts; every clip is STATED
    in ``truncation``, and a rollup whose budget ran out names where."""
    try:
        from portal.modules.compliance.core import reading_assembly
        from portal.modules.compliance.core.cip_register import Register
        from portal.modules.compliance.core.engine import effective_parts, parse_iso_date
        from portal.modules.compliance.core.obligations import decompose, expression_for
        from portal.modules.compliance.core.repository import Repository
        from portal.modules.compliance.core.temporal_selection import (
            select_revision_effectivity,
            store_nodes_for_revisions,
            withhold_unknown_knowledge,
        )

        today = datetime.date.today().isoformat()
        when = parse_iso_date(valid_at or today, field="valid_at")
        reg = Register.load()
        repo = Repository()
        conn = repo._conn
        family_match = re.match(r"(CIP-\d+)", requirement.strip().upper())
        family = family_match.group(1) if family_match else ""
        selection = (
            select_revision_effectivity(conn, family=family, valid_at=when, known_at=known_at)
            if family
            else None
        )
        selected_versions = (
            {rev["version"] for rev in selection["selected"]} if selection else set()
        )
        selected_revision_ids = (
            {rid for rev in selection["selected"] for rid in rev["revision_ids"]}
            if selection
            else set()
        )
        active = effective_parts(reg, when)
        # The register is pinned to current revisions; a selected future or
        # historical store revision it does not carry still resolves from the
        # canonical store (requirement_nodes + verbatim atom clauses).
        # Canonicalize the address spelling first ("Requirement 2" → "R2"):
        # the register's ids only carry the canonical form.
        address = reading_assembly.parse_ref(requirement)
        want = re.sub(r"\s+", "", str(address) if address else requirement.strip()).upper()
        hits = [n for n in active if re.sub(r"\s+", "", n.id).upper().startswith(want)]
        if not hits:
            # Family queries such as CIP-003 select the effective revision at
            # the requested date; explicit retired version IDs remain exact.
            hits = [n for n in active if re.sub(r"\s+", "", n.standard).upper().startswith(want)]
        # drop register nodes whose standard revision the store's sourced
        # effectivity does not select at this valid_at/known_at
        if selected_versions:
            hits = [n for n in hits if n.standard.rsplit("-", 1)[1] in selected_versions]
        parts = [
            _register_part(conn, reg, node, decompose, expression_for, when, today) for node in hits
        ]
        # canonical-store nodes for selected revisions the register does not
        # carry (e.g. the future CIP-007-7.1) resolve from the store's own
        # decompositions — verbatim atom clauses, never invented text.
        if selected_revision_ids:
            carried = {n.standard for n in hits}
            store_parts = store_nodes_for_revisions(
                conn, selected_revision_ids, exclude_standards=carried
            )
            for node_id, entry in store_parts.items():
                if want in re.sub(r"\s+", "", node_id).upper() or not re.search(r"R\d+", want):
                    parts.append(entry)
        # as-known strictness: a part whose revision's effectivity was not
        # yet recorded at the requested known_at is NOT served as known —
        # the disclosure names it (late-recorded fact, L21).
        parts, withheld_knowledge = withhold_unknown_knowledge(parts, selection)
        if parts or selection:
            response: dict[str, Any] = {
                "requirement": requirement,
                "found": bool(parts),
                "scope": scope,
                "valid_at": when,
                "known_at": known_at or "latest recorded knowledge",
                "defaulted_valid_at": not bool(valid_at),
            }
            if selection is not None:
                response["revision_selection"] = {
                    "selected": selection["selected"],
                    "future": selection["future"],
                    "historical": selection["historical"],
                    "unknown_knowledge": selection["unknown_knowledge"],
                }
            if withheld_knowledge:
                response["withheld_as_unknown_knowledge"] = withheld_knowledge
            if parts:
                parts, truncation = _ceiling(parts, max_chars)
                response.update(
                    {
                        "granularity": "exact"
                        if len(parts) == 1 and re.sub(r"\s+", "", parts[0]["id"]).upper() == want
                        else "rollup",
                        "parts": parts,
                        "readiness": {"complete": True, "missing": []},
                        "source": "NERC CIP Reliability Standards verbatim register",
                        "truncation": truncation,
                    }
                )
            if include_dual_document:
                try:
                    from portal.modules.compliance.core import dual_document

                    response["dual_document"] = dual_document.build(
                        repo, requirement_ref=requirement, **_payload_pricing()
                    )
                except Exception as e:  # noqa: BLE001 - the atoms stand alone
                    response["dual_document"] = {"resolved": False, "error": str(e)}
            return response
        return {
            "requirement": requirement,
            "found": False,
            "valid_at": when,
            "known_at": known_at or "latest recorded knowledge",
            "revision_selection": {
                "selected": selection["selected"],
                "future": selection["future"],
                "historical": selection["historical"],
                "unknown_knowledge": selection["unknown_knowledge"],
            }
            if selection
            else None,
            "note": "no governing revision is enforceable at the requested date",
        }
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)}


@mcp.tool()
def nerc_cip_requirement(
    req_id: str,
    valid_at: str = "",
    known_at: str = "",
    include_dual_document: bool = False,
) -> dict[str, Any]:
    """Compatibility wrapper for :func:`compliance_requirement`.

    When omitted, ``valid_at`` defaults explicitly to today's calendar date
    and the response records that default.
    """
    result = compliance_requirement(
        req_id,
        valid_at=valid_at,
        known_at=known_at,
        include_dual_document=include_dual_document,
    )
    if result.get("found") and result.get("granularity") == "exact" and len(result["parts"]) == 1:
        part = result["parts"][0]
        return {
            **result,
            "req_id": part["id"],
            "verbatim_text": part["verbatim_text"],
            "standard": part["standard"],
            # legacy flat surface kept by this compatibility wrapper
            "valid_from": part["effectivity"]["valid_from"],
            "lifecycle_state": (
                "EFFECTIVE" if part["temporal_label"] == "current" else "HISTORICAL"
            ),
        }
    return result


@mcp.tool()
def map_frameworks(
    control_id: str, from_fw: str = "csf_2_0", to_fw: str = "nist_800_53"
) -> dict[str, Any]:
    """Cross-framework mapping for a control id (via the bundled OLIR-style crosswalk seed).

    Handles both directions: csf_2_0 -> nist_800_53 is a direct lookup;
    nist_800_53 -> csf_2_0 is resolved by reverse index.
    """
    try:
        xwalk = _catalog("crosswalk")
        mappings = xwalk.get("mappings", {})
        cid = control_id.strip().upper()
        key = f"{from_fw}:{cid}"
        mapped = mappings.get(key, {}).get(to_fw, [])
        if not mapped:
            # reverse: the crosswalk is stored csf-keyed, so find every
            # `to_fw:<x>` entry whose `from_fw` list contains cid
            mapped = sorted(
                stored.split(":", 1)[1]
                for stored, tgt in mappings.items()
                if stored.startswith(f"{to_fw}:") and cid in tgt.get(from_fw, [])
            )
        return {
            "from": key,
            "to_framework": to_fw,
            "mapped": mapped,
            "coverage": xwalk.get("coverage", "partial-seed"),
            "note": xwalk.get("source", ""),
        }
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)}


@mcp.tool()
def patch_evidence(cve_id: str) -> dict[str, Any]:
    """CIP-007-6 R2 patch-evaluation record for a CVE (uses vulnintel triage)."""
    try:
        from portal.modules.vulnintel.tools.vulnintel_mcp import triage_cve  # T1 dependency

        t = triage_cve(cve_id, depth="deep")
        return {
            "cve_id": cve_id,
            "source_identified": "NVD / CISA KEV (via portal-vulnintel)",
            "applicability": "OPERATOR: confirm affected assets are in scope",
            "risk": {
                "score": t.get("risk_score"),
                "label": t.get("label"),
                "in_kev": t.get("signals", {}).get("in_kev"),
            },
            "ssvc_decision": t.get("ssvc_decision"),
            "cip_007_r2": (
                "Evaluate applicability within 35 calendar days of the source's release; then, "
                "within the next 35 calendar days, apply the patch, create a dated mitigation "
                "plan, or revise an existing plan. Document the apply-or-mitigate decision and "
                "rationale. KEV / active exploitation warrants expedited action."
            ),
            "record_ready": True,
        }
    except Exception as e:  # noqa: BLE001
        return {"error": f"vulnintel unavailable ({e}); ensure T1 landed"}


def _distil_800_53(raw: dict[str, Any]) -> dict[str, Any]:
    def prose(parts: list[dict[str, Any]] | None) -> list[str]:
        out: list[str] = []
        for p in parts or []:
            if p.get("prose"):
                out.append(p["prose"].strip())
            out.extend(prose(p.get("parts")))
        return out

    def stmt(c: dict[str, Any]) -> str:
        for part in c.get("parts", []):
            if part.get("name") == "statement":
                return " ".join(prose([part])).strip()
        return ""

    flat: dict[str, Any] = {}

    def walk(controls: list[dict[str, Any]], family: str) -> None:
        for c in controls:
            flat[c.get("id", "").upper()] = {
                "title": c.get("title", ""),
                "family": family,
                "statement": stmt(c),
            }
            if c.get("controls"):
                walk(c["controls"], family)

    for g in raw.get("catalog", {}).get("groups", []):
        walk(g.get("controls", []), g.get("title", ""))
    return flat


def _distil_csf(raw: dict[str, Any]) -> dict[str, Any]:
    def prose(parts: list[dict[str, Any]] | None) -> list[str]:
        out: list[str] = []
        for p in parts or []:
            if p.get("prose"):
                out.append(p["prose"].strip())
            out.extend(prose(p.get("parts")))
        return out

    flat: dict[str, Any] = {}

    def walk(controls: list[dict[str, Any]], fn: str) -> None:
        for c in controls:
            flat[c.get("id", "").upper()] = {
                "title": c.get("title", ""),
                "function": fn,
                "statement": " ".join(prose(c.get("parts", []))).strip(),
            }
            if c.get("controls"):
                walk(c["controls"], fn)

    for g in raw.get("catalog", {}).get("groups", []):
        walk(g.get("controls", []), g.get("title", ""))
        for sub in g.get("groups", []):
            walk(sub.get("controls", []), g.get("title", ""))
    return flat


@mcp.tool()
def refresh_catalogs() -> dict[str, Any]:
    """Re-pull the authoritative OSCAL catalogs (NIST 800-53 Rev5, CSF 2.0) into the local data dir.

    Network operation. honest-BLOCKED on failure — never fabricates control text.
    """
    results = {}
    for url, out_name, distil in (
        (_OSCAL_800_53, "nist_800_53_rev5", _distil_800_53),
        (_OSCAL_CSF, "csf_2_0", _distil_csf),
    ):
        try:
            with urllib.request.urlopen(url, timeout=90) as fh:  # noqa: S310
                raw = json.load(fh)
            flat = distil(raw)
            if not flat:
                results[out_name] = "BLOCKED: distillation produced no controls"
                continue
            (_DATA / f"{out_name}.json").write_text(
                json.dumps(
                    {"control_count": len(flat), "controls": flat}, indent=1, sort_keys=True
                ),
                encoding="utf-8",
            )
            results[out_name] = f"ok ({len(flat)} controls)"
        except Exception as e:  # noqa: BLE001
            results[out_name] = f"BLOCKED: {e}"
    _cache.clear()
    present = {p.stem: p.stat().st_size for p in _DATA.glob("*.json")}
    return {"data_dir": str(_DATA), "results": results, "catalogs_present": present}


@mcp.tool()
def nerc_cip_currency() -> dict[str, Any]:
    """Per-standard currency: our held version, whether a newer version PDF is
    published on nerc.com, and an explicit 'verify the enforcement date' — the
    standard PDFs defer their effective date to a separate Implementation Plan,
    so currency is never inferred. honest-BLOCKED when nerc.com is unreachable."""
    try:
        from portal.modules.compliance.core.currency import nerc_currency as _cur

        return _cur()
    except ImportError as e:
        return {"status": "honest-BLOCKED", "reason": f"register not importable: {e}"}
    except Exception as e:  # noqa: BLE001
        return {"status": "honest-BLOCKED", "reason": str(e)}


# ── TASK_COMPLIANCE_ENGINE_LANDING_V1 P2: route the engine ──────────────────
# Everything below wraps a core module that previously had no route and no
# tool — coverage.py, engine.py, mapping_store.py, applicability.py,
# review_queue.py. `engine.route()` had never dispatched (see the task's
# discovery). Every function here must ALSO be added to a workspace's
# `tools:` list in config/portal.yaml — being reachable at this REST surface
# is necessary but not sufficient (Do Not: "stop at MCP registration").


@mcp.tool()
def compliance_ingest(
    source_dir: str, kb_id: str = "operator_corpus", rebuild: bool = False
) -> dict[str, Any]:
    """Sync dispatch wrapper — see ``compliance_retrieval.ingest_folder`` (the
    async ``/tools/compliance_ingest`` custom route calls the same function).
    Kept in ``_DISPATCH`` so this tool is generic-POST-dispatchable AND
    manifest-listed, closing the exact gap this task exists to fix."""
    import asyncio

    from portal.modules.compliance.core.ingest import ingest_folder

    try:
        return asyncio.run(ingest_folder(source_dir, kb_id, rebuild))
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)}


_STANDARD_PARTS_CACHE: dict[str, list[str]] = {}


def _resolve_context_scope(kb_id: str, scope_text: str) -> tuple[Any, dict[str, Any]]:
    from portal.modules.compliance.core.applicability import parse_scope_declaration
    from portal.modules.compliance.core.scope_derive import derive_scope

    if scope_text:
        return parse_scope_declaration(scope_text), {"basis": "declared"}
    scope, meta = derive_scope(kb_id)
    return scope, meta


@mcp.tool()
def compliance_orphans(
    kb_id: str = "operator_corpus", effective_on: str = "", run_id: str = ""
) -> dict[str, Any]:
    """Ingested policy/procedure sections mapping to no requirement — dead
    weight, or evidence the register is incomplete.

    With an explicit ``run_id``, the resolved source links of that assessment
    run are the basis; an item the run left UNRESOLVED is surfaced separately
    and is never reported as a proven orphan. Without one, this is a
    retrieval-only inventory that does not claim any item is orphaned.
    """
    try:
        eff = effective_on or datetime.date.today().isoformat()
        all_sections = _all_sections(kb_id)
        if run_id:
            from portal.modules.compliance.core.assessment_runs import run_result

            payload = run_result(run_id)
            if "error" in payload:
                return payload
            linked: set[str] = set()
            unresolved: list[str] = []
            for result in payload.get("results", []):
                if str(result.get("coverage")) == "UNRESOLVED":
                    unresolved.append(str(result.get("requirement_id", "")))
                for slice_row in result.get("selected_source_slices", []) or []:
                    if not isinstance(slice_row, dict):
                        continue
                    ref = str(slice_row.get("ref", "")) or str(slice_row.get("document_id", ""))
                    if ref:
                        linked.add(ref)
            orphans = sorted(all_sections - linked)
            return {
                "basis": f"assessment-run:{run_id}",
                "inventory_only": False,
                "effective_on": eff,
                "n_orphans": len(orphans),
                "orphan_sections": orphans,
                "unresolved_items": unresolved,
                "note": (
                    "resolved links of the named run only; unresolved items are not "
                    "reported as orphans"
                ),
            }
        return {
            "basis": "retrieval-only",
            "inventory_only": True,
            "effective_on": eff,
            "n_sections": len(all_sections),
            "n_orphans": 0,
            "orphan_sections": [],
            "proven_orphans": [],
            "note": (
                "no assessment run supplied — this is a retrieval-only inventory and "
                "does not prove any section is orphaned"
            ),
        }
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)}


def _all_sections(kb_id: str) -> set[str]:
    from portal.platform.retrieval import store as _store

    ttbl = _store.text_table(kb_id, create=False, prefix="compliance_")
    all_sections: set[str] = set()
    if ttbl is not None:
        for row in ttbl.to_pandas().to_dict("records"):
            all_sections.add(f"{row['source_file']} #chunk{row['chunk_index']} p{row['page']}")
    return all_sections


@mcp.tool()
def compliance_draft_revisions(
    old_standard: str,
    new_standard: str,
    kb_id: str = "operator_corpus",
    mode: str = "draft_as_proposal",
    scope: str = "",
    effective_on: str = "",
    known_at: str = "",
    conditional_scope: bool = False,
    edits_json: str = "",
) -> dict[str, Any]:
    """Design §9 Q07 — what revisions improve alignment, for a standard-version
    transition, with both verbatim spans, for every mapped section affected by a
    substantive change.

    Drafts are unapproved proposals. Their self-reassessment runs as an exact
    overlay re-judgment through the shared proposal service against the same
    KB/snapshot context as the assessment service — a draft that merely quotes
    the governing text does not get a success receipt. When the impact payload
    lacks a resolving edit target, the proposal returns unvalidated with the
    missing-input reason.
    """
    try:
        from portal.modules.compliance.core.change_pipeline import draft_revisions, impact_report
        from portal.modules.compliance.core.cip_register import Register
        from portal.modules.compliance.core.mapping_store import MappingStore

        reg = Register.load()
        scope_obj, scope_meta = _resolve_context_scope(kb_id, scope)
        if not scope_obj.is_declared and not conditional_scope:
            return {"status": "honest-BLOCKED", "reason": scope_meta.get("reason")}
        base = old_standard.rsplit("-", 1)[0]
        old = Register(nodes=[n for n in reg.nodes if n.standard == old_standard], edges=reg.edges)
        new = Register(nodes=[n for n in reg.nodes if n.standard == new_standard], edges=reg.edges)
        if not old.nodes or not new.nodes:
            return {"error": f"standard not both in register: {old_standard} -> {new_standard}"}
        impact = impact_report(old, new, base, scope_obj, MappingStore())

        context = None
        requests_by_part: dict[str, Any] = {}
        if mode == "draft_as_proposal":
            from portal.modules.compliance.core import assessment_runs
            from portal.modules.compliance.core.runtime_config import build_assessment_context

            eff = effective_on or datetime.date.today().isoformat()
            context = build_assessment_context(kb_id, scope_obj, eff, known_at, None)
            for row in impact.get("impact_rows", []):
                part = str(row.get("changed_part", ""))
                if not part or part in requests_by_part:
                    continue
                try:
                    requests = assessment_runs.build_requests_for(
                        part,
                        kb_id=kb_id,
                        scope=scope_obj,
                        effective_on=eff,
                        known_at=known_at,
                        conditional_scope=conditional_scope,
                    )
                except Exception:  # noqa: BLE001 - a part without a request stays unvalidated
                    continue
                if requests:
                    requests_by_part[part] = requests[0]
        edits_by_section = json.loads(edits_json) if edits_json else None
        result = draft_revisions(
            impact,
            mode=mode,
            context=context,
            requests_by_part=requests_by_part,
            edits_by_section=edits_by_section,
        )
        result["engine"] = "compliance-reading/1"
        result["kb_id"] = kb_id
        return result
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)}


@mcp.tool()
def compliance_mappings(requirement_id: str = "", approved_only: bool = False) -> dict[str, Any]:
    """List/filter the mapping store (requirement -> internal document/section).
    Every approved or corrected mapping is a labelled example — the SME
    override rate is the trust signal."""
    try:
        from portal.modules.compliance.core.mapping_store import MappingStore

        store = MappingStore()
        rows = store.all_for(requirement_id) if requirement_id else list(store._rows)  # noqa: SLF001
        if approved_only:
            rows = [m for m in rows if m.is_approved]
        return {
            "count": len(rows),
            "mappings": [dataclasses.asdict(m) for m in rows],
            "override_rate": store.override_rate(),
        }
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)}


@mcp.tool()
def compliance_scope(kb_id: str = "operator_corpus") -> dict[str, Any]:
    """The asset applicability scope derived from the operator's own ingested
    corpus, with its citing evidence. Queued (`applicability_scope`) rather
    than asked for — see compliance_review_list/decide to confirm it."""
    try:
        from portal.modules.compliance.core.scope_derive import derive_scope

        scope, meta = derive_scope(kb_id)
        return {
            "impact_present": sorted(scope.impact_present),
            "associated_present": sorted(scope.associated_present),
            "has_erc": scope.has_erc,
            "has_control_center": scope.has_control_center,
            "declared_by": scope.declared_by,
            "is_declared": scope.is_declared,
            **meta,
        }
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)}


@mcp.tool()
def compliance_route(query: str, effective_on: str = "") -> dict[str, Any]:
    """Route a free-form compliance question to its intent (today / change /
    gaps / freeform) and the node set that path operates on."""
    try:
        from portal.modules.compliance.core.cip_register import Register
        from portal.modules.compliance.core.engine import route as _route

        reg = Register.load()
        eff = effective_on or datetime.date.today().isoformat()
        return _route(query, reg, eff)
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)}


@mcp.tool()
def compliance_review_list(
    kind: str = "", status: str = "OPEN", view: str = "all"
) -> dict[str, Any]:
    """The review queue: open (default) or filtered judgements the system
    proceeded on with its best evidence-backed answer — never a blocker."""
    try:
        from portal.modules.compliance.core import review_queue as rq

        # view="packet" is the SME packet: only questions a human is the right
        # answerer for. view="triage" is the complement — the module's own
        # backlog, which must never be handed to a compliance reviewer.
        if view in ("packet", "triage"):
            if view == "packet":
                repo = _repo()
                try:
                    packet = rq.mapping_packet(repo)
                finally:
                    repo.close()
                items = [*packet, *[dataclasses.asdict(item) for item in rq.sme_packet()]]
            else:
                items = [dataclasses.asdict(item) for item in rq.triage_items()]
            return {
                "count": len(items),
                "view": view,
                "items": items,
            }
        rows = rq.list_items(kind=kind or None, status=status or None)
        return {"count": len(rows), "view": "all", "items": [dataclasses.asdict(i) for i in rows]}
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)}


@mcp.tool()
def compliance_review_decide_batch(
    decisions: list[dict[str, Any]],
    sme: str,
    reviewer_token: str = "",
) -> dict[str, Any]:
    """Apply versioned mapping decisions in one transaction.

    Stale rows are returned individually with their current version; they do
    not discard the rest of the reviewer's batch.
    """
    from portal.modules.compliance.core.auth import UnauthenticatedReviewError, verify_reviewer
    from portal.modules.compliance.core.mapping_store import MappingStore

    try:
        verified = verify_reviewer(reviewer_token)
    except UnauthenticatedReviewError as exc:
        return {"error": str(exc), "status": "UNAUTHENTICATED"}
    try:
        results = MappingStore().decide_batch(decisions, verified)
        return {
            "count": len(results),
            "applied": sum(result.get("status") == "APPLIED" for result in results),
            "results": results,
            "decided_by": verified,
            "caller_label": sme,
        }
    except Exception as exc:  # noqa: BLE001 - report a batch failure as a payload
        return {"error": str(exc)}


@mcp.tool()
def compliance_review_decide(
    item_id: str,
    decision: str,
    decided_by: str,
    corrected_value: dict[str, Any] | None = None,
    reviewer_token: str = "",
) -> dict[str, Any]:
    """Confirm or reject one open queue item. Reversible: writes a NEW row
    superseding the prior one via prior_item_id; nothing is overwritten. A
    confirmed mapping_proposal is approved in the mapping store directly — no
    parallel proposal path.

    ``reviewer_token`` is required (P7/F09): authority is never taken from
    the caller-supplied ``decided_by`` string, which a model can set to
    anything. The token must match an operator-configured entry in
    ``core.auth.REVIEWERS_PATH``; the recorded ``decided_by`` is the verified
    principal's name, not the caller's ``decided_by`` argument (kept only as
    ``caller_label`` for audit)."""
    from portal.modules.compliance.core.auth import UnauthenticatedReviewError, verify_reviewer

    try:
        verified_by = verify_reviewer(reviewer_token)
    except UnauthenticatedReviewError as exc:
        return {"error": str(exc), "status": "UNAUTHENTICATED"}

    try:
        from portal.modules.compliance.core import review_queue as rq
        from portal.modules.compliance.core.mapping_store import MappingStore

        caller_label = decided_by
        new_item = rq.decide(item_id, decision, verified_by, corrected_value)
        decided_by = verified_by
        mapping_error = None
        if new_item.kind == "mapping_proposal":
            store = MappingStore()
            try:
                if decision == "CONFIRMED":
                    store.approve(
                        new_item.subject_id, decided_by, new_item.proposed_value.get("coverage")
                    )
                elif decision == "REJECTED":
                    # F09: a rejection must actually revoke a previously
                    # approved mapping, not merely record a review event that
                    # the effective coverage never sees.
                    store.revoke(new_item.subject_id, decided_by)
            except KeyError as exc:
                # a missing mapping target is an ERROR, never silent success
                # (F09) — the review decision itself still stands (recorded
                # above), but the caller must be told the mapping-side effect
                # did not happen.
                mapping_error = f"mapping target not found: {exc}"
        result = dataclasses.asdict(new_item)
        result["caller_label"] = caller_label  # audit only — never authoritative
        if mapping_error:
            result["mapping_error"] = mapping_error
        return result
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)}


def _clip_revised_sections(revision_id: str, repo: Any) -> list[dict[str, Any]]:
    """The classified section tree, with each section's text ceiling-capped.

    WINDOW_AND_SEAT_V1 P1.1: `include_sections=true` used to return whole
    sections unbounded. The ids are what a reader follows for the full text.
    """
    sections: list[dict[str, Any]] = repo.sections_with_role(revision_id)
    for section in sections:
        text, note = _clip(str(section.get("text", "")), 4000)
        section["text"] = text
        if note:
            section["truncation"] = {"max_chars": 4000, "stated": True}
    return sections


def _compact_inventory_payload(
    documents: list[dict[str, Any]], kind: str, operator_count: int, regulatory_count: int
) -> dict[str, Any]:
    compact_lines: list[str] = []
    reg_titles: list[str] = []
    for d in documents:
        if not kind and d["kind"] == "regulatory":
            reg_titles.append(d["title"] or d["logical_id"])
            continue
        parts = [d["logical_id"]]
        doc_no = " ".join(x for x in (d.get("document_number"), d.get("version")) if x)
        if doc_no:
            parts.append(doc_no)
        if d.get("effective_date"):
            parts.append(f"eff {d['effective_date']}")
        parts.append(f"{d['section_count']}s")
        if d.get("linked_standards"):
            parts.append(",".join(d["linked_standards"]))
        compact_lines.append(" | ".join(parts))
    result: dict[str, Any] = {
        "mode": "inventory",
        "kind": kind or "all",
        "count": len(documents),
        "operator_count": operator_count,
        "regulatory_count": regulatory_count,
        "documents": compact_lines,
        "note": "Compact inventory (logical_id | doc_no ver | eff date | sections | standards) to fit chat budget; pass logical_id to compliance_read() or compliance_sources() for full details.",
    }
    if reg_titles:
        result["regulatory_titles"] = reg_titles
    return result


def _source_inventory(repo: Any, kind: str) -> dict[str, Any]:
    if kind not in ("", "operator", "regulatory"):
        return {"error": "kind must be 'operator', 'regulatory', or empty"}
    from portal.modules.compliance.core.document_scope import families_for
    from portal.modules.compliance.core.jurisdiction import side_of
    from portal.modules.compliance.core.section_index import _governing_revisions

    jurisdictions = ("internal", "operator_note", "US")
    active_revisions = set().union(
        *(_governing_revisions(repo, jurisdiction) for jurisdiction in jurisdictions)
    )
    rows = repo._conn.execute(
        """SELECT d.logical_id, d.title, d.source_kind, d.jurisdiction,
                  r.revision_id, r.document_number, r.version, r.effective_date,
                  r.lifecycle_status, COUNT(DISTINCT s.section_id) AS section_count,
                  COALESCE(ds.standards_json, '[]') AS standards_json
           FROM source_documents d
           JOIN document_revisions r ON r.logical_id = d.logical_id
           LEFT JOIN source_sections s ON s.revision_id = r.revision_id
           LEFT JOIN document_scope ds ON ds.logical_id = d.logical_id
           WHERE d.jurisdiction IN (?,?,?)
           GROUP BY d.logical_id, r.revision_id
           ORDER BY CASE WHEN d.jurisdiction = 'US' THEN 1 ELSE 0 END, d.logical_id, r.revision_id""",
        jurisdictions,
    ).fetchall()
    documents = []
    operator_count = 0
    regulatory_count = 0
    for row in rows:
        side = side_of(row["jurisdiction"])
        if row["revision_id"] not in active_revisions or (kind and side != kind):
            continue
        if side == "operator":
            operator_count += 1
        elif side == "regulatory":
            regulatory_count += 1
        scope_claims = json.loads(row["standards_json"] or "[]")
        documents.append(
            {
                "kind": side,
                "logical_id": row["logical_id"],
                "revision_id": row["revision_id"],
                "title": row["title"],
                "source_kind": row["source_kind"],
                "document_number": row["document_number"],
                "version": row["version"],
                "effective_date": row["effective_date"],
                "lifecycle_status": row["lifecycle_status"],
                "section_count": int(row["section_count"]),
                "linked_standards": sorted(families_for({"claims": scope_claims})),
            }
        )
    if len(documents) > 15:
        return _compact_inventory_payload(documents, kind, operator_count, regulatory_count)
    return {
        "mode": "inventory",
        "kind": kind or "all",
        "count": len(documents),
        "operator_count": operator_count,
        "regulatory_count": regulatory_count,
        "documents": documents,
        "note": "Current recorded revisions in the canonical store; operator documents are listed first. Pass kind='operator' for a compact operator-only list.",
    }


@mcp.tool()
def compliance_sources(
    revision_id: str = "",
    alias_path: str = "",
    logical_id: str = "",
    include_sections: bool = False,
    kind: str = "",
) -> dict[str, Any]:
    """Exact permitted source context for an immutable document revision
    (design §9's "What documents... connect" / P7's `compliance_sources`
    operation) — the first operation wired to the P2 canonical repository
    rather than the legacy JSON stores. Pass ``revision_id`` for an exact
    historical anchor; ``logical_id`` for the human-facing, source-dir-
    relative identity (e.g. "CIP-007/Some Procedure.pdf" — what an operator
    or another tool would naturally name it); or ``alias_path`` for the
    literal resolvable filesystem path a revision was ingested from. With no
    selector, return the current document inventory; ``kind`` filters operator
    or regulatory sources. A match returns the CURRENT/every revision ever
    recorded under that key — a same-path replacement never erases history.

    Integrity: when the file still exists on disk at its recorded
    ``alias_path``, its bytes are re-hashed now and compared against the
    revision's own content-hash identity — this can positively detect
    silent drift at the source (the file changed without a new ingested
    revision being recorded), which a stored hash alone cannot."""
    try:
        from portal.modules.compliance.core.provenance import content_hash
        from portal.modules.compliance.core.repository import Repository

        repo = Repository()
        if not any((revision_id, logical_id, alias_path)):
            return _source_inventory(repo, kind)
        if revision_id:
            rev = repo.get_revision(revision_id)
            revisions = [rev] if rev else []
        elif logical_id:
            revisions = repo.revisions_for_logical_id(logical_id)
        elif alias_path:
            revisions = repo.revisions_for_alias(alias_path)
        if not revisions:
            return {
                "found": False,
                "reason": "no matching revision in the canonical store",
                "note": "this store is populated by core.migrate_legacy; an unmigrated "
                "corpus will have no rows here yet",
            }

        out = []
        for rev in revisions:
            entry = dataclasses.asdict(rev)
            live_path = Path(rev.alias_path)
            if live_path.is_file():
                live_hash = content_hash(live_path.read_bytes())
                entry["integrity"] = "verified" if live_hash == rev.revision_id else "DRIFTED"
                if live_hash != rev.revision_id:
                    entry["drift_detail"] = (
                        f"the file at {rev.alias_path} no longer matches this recorded "
                        f"revision's hash — it changed without a new revision being ingested"
                    )
            else:
                entry["integrity"] = "unverifiable — source file not found on disk"
            if include_sections:
                # the classified section tree (role per section) — what makes a
                # copied traceability row inspectable as non-operative through
                # the route. Text is ceiling-capped and the clip stated.
                entry["sections"] = _clip_revised_sections(rev.revision_id, repo)
            out.append(entry)
        return {
            "found": True,
            "revisions": out,
            "current_revision_id": revisions[-1].revision_id,  # most recently ingested
            "n_historical_revisions": len(revisions) - 1,
        }
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)}


@mcp.tool()
def compliance_trace(
    start_ref: str,
    direction: str = "both",
    max_depth: int = 3,
    include_proposed: bool = False,
) -> dict[str, Any]:
    """Bidirectional relationship traversal from a requirement/document/
    control reference (design §9's ``compliance_trace`` operation) — the
    second MCP operation wired to the P2 canonical repository. Returns typed
    sourced paths with edge status, and discloses depth-limited nodes and any
    work-budget-truncated frontier rather than silently presenting a partial
    traversal as complete. ``include_proposed`` widens beyond the governed
    approved-only surface for candidate-discovery use, never the default."""
    try:
        from portal.modules.compliance.core.repository import Repository
        from portal.modules.compliance.core.traceability import trace

        repo = Repository()
        assessment = repo.get_assessment(start_ref)
        if assessment is not None:
            run = repo.get_run(str(assessment.get("run_id", "")))
            return {
                "kind": "assessment",
                "assessment_id": start_ref,
                "assessment": assessment,
                "run": run,
                "run_metadata": {
                    "run_id": assessment.get("run_id", ""),
                    "status": (run or {}).get("status", ""),
                    "engine": assessment.get("engine_version", ""),
                    "input_fingerprint": assessment.get("input_fingerprint", ""),
                    "snapshot_fingerprint": (assessment.get("receipt") or {}).get(
                        "snapshot_fingerprint", ""
                    ),
                },
            }
        statuses = ("approved", "proposed") if include_proposed else ("approved",)
        return trace(repo, start_ref, direction=direction, statuses=statuses, max_depth=max_depth)
    except ValueError as e:
        return {"error": str(e)}
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)}


@mcp.tool()
def compliance_intentionality(
    requirement_id: str,
    internal_text: str,
    control_id: str = "",
) -> dict[str, Any]:
    """Are our internal rules more restrictive than the standard, and is
    that intentional? (design §9 Q08). Compares every quantitative claim
    in ``internal_text`` (paste the relevant procedure/policy span) against
    the governing requirement's verbatim text using the direction-aware
    comparator (F05/P5.3 — a shorter max_interval is stricter, a longer
    min_retention is stricter, never the reverse; different units/qualifiers
    are never converted). Never calls a stricter internal practice a
    violation, and never treats "stricter" as license to loosen it.

    Pass ``control_id`` (a real row in the ``internal_controls`` table) to
    also check for a recorded ``policy_decisions`` entry — this is the only
    way to actually know intent was deliberate rather than incidental. With
    no ``control_id`` match, intentionality is honestly reported
    ``unknown``, never inferred from the comparison alone."""
    try:
        from portal.modules.compliance.core.cip_register import Register
        from portal.modules.compliance.core.intentionality import assess_intentionality

        reg = Register.load()
        node = next((n for n in reg.nodes if n.id == requirement_id), None)
        if node is None:
            return {"error": f"unknown requirement_id: {requirement_id}"}

        result = assess_intentionality(node.verbatim_text, internal_text)
        result["requirement_id"] = requirement_id
        result["governing_citation"] = requirement_id

        intentionality: dict[str, Any] = {"status": "unknown", "reason": "no control_id supplied"}
        if control_id:
            try:
                from portal.modules.compliance.core.repository import Repository

                decisions = Repository().get_policy_decisions(control_id)
            except Exception as e:  # noqa: BLE001
                decisions = []
                intentionality = {"status": "unknown", "reason": f"lookup failed: {e}"}
            else:
                if decisions:
                    intentionality = {"status": "documented", "decisions": decisions}
                else:
                    intentionality = {
                        "status": "unknown",
                        "reason": f"no policy_decisions row for control_id {control_id!r}",
                    }
        result["intentionality"] = intentionality
        return result
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)}


@mcp.tool()
def compliance_flexibility(requirement_id: str) -> dict[str, Any]:
    """Where does the regulation permit flexibility we do not use? (design
    §9 Q09). Scans the governing requirement's verbatim text for explicit
    permissive-alternative cues ("may", "alternatively", "at its
    discretion") and returns each matching sentence verbatim, sourced to
    the requirement. Cue-word detection only — NOT semantic obligation
    modeling, and NEVER a recommendation: an SME must confirm any
    candidate's conditions before adopting it, and a forbidden/conditional
    alternative must not be read as an unconditional one (design
    anti-shortcut list)."""
    try:
        from portal.modules.compliance.core.cip_register import Register
        from portal.modules.compliance.core.intentionality import find_flexibility

        reg = Register.load()
        node = next((n for n in reg.nodes if n.id == requirement_id), None)
        if node is None:
            return {"error": f"unknown requirement_id: {requirement_id}"}
        result = find_flexibility(node.verbatim_text)
        result["requirement_id"] = requirement_id
        return result
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)}


@mcp.tool()
def compliance_compare(before_revision: str, after_revision: str) -> dict[str, Any]:
    """Compare two explicit standard revisions with raw and interpreted deltas."""
    try:
        from portal.modules.compliance.core.cip_register import Register
        from portal.modules.compliance.core.register_diff import diff_standard

        reg = Register.load()
        base = before_revision.rsplit("-", 1)[0]
        before = Register(
            nodes=[n for n in reg.nodes if n.standard == before_revision], edges=reg.edges
        )
        after = Register(
            nodes=[n for n in reg.nodes if n.standard == after_revision], edges=reg.edges
        )
        rows = [row.to_dict() for row in diff_standard(before, after, base)]
        return {
            "before_revision": before_revision,
            "after_revision": after_revision,
            "raw_diff": rows,
            "interpreted_delta": rows,
            "impacted_scope": sorted(
                {row.get("part_id_new") or row.get("part_id_old") for row in rows}
            ),
        }
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}


TOOLS_MANIFEST = load_data("config/inference", "tools_manifest_compliance_mcp")

# ── BILATERAL_CORPUS_V1 P5: addressability and the reading assembly ─────────
#
# Seven synchronous, sub-ten-second tools. NONE of them returns a run id or
# starts a background job: asking where the R2 gaps are must not start a
# 3.3-hour batch, and a model in a chat cannot read a document it has to poll
# for. `_SPAN_EXCERPT_CHARS = 180` is gone from this surface — text is whole up
# to a caller-supplied `max_chars`, and truncation is STATED, never silent.


def _repo() -> Any:
    from portal.modules.compliance.core.repository import Repository

    return Repository()


def _ceiling(
    parts: list[dict[str, Any]], max_chars: int
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Bound the verbatim text one call returns, shared across its parts.

    WINDOW_AND_SEAT_V1 P1.1: a tool that can return more than a fifth of the
    serving window in one call is a hazard on the conversation path. The
    budget is PER CALL, not per part — a four-Part rollup must not cost four
    ceilings. Every clip is stated, and the part that exhausted the budget is
    named, so a truncated read is visible as one.
    """
    remaining = max(int(max_chars), 0)
    clipped: list[dict[str, Any]] = []

    def _cut(text: str, where: str) -> str:
        nonlocal remaining
        if len(text) <= remaining:
            remaining -= len(text)
            return text
        if remaining <= 0:
            clipped.append({"where": where, "kept": 0, "omitted_chars": len(text)})
            return ""
        kept, note = _clip(text, remaining)
        clipped.append({"where": where, "kept": remaining, "omitted_chars": len(text) - remaining})
        remaining = 0
        return kept + (f"\n{note}" if note else "")

    for part in parts:
        part["verbatim_text"] = _cut(
            str(part.get("verbatim_text", "")), f"{part.get('id', '')}:verbatim_text"
        )
        for atom in part.get("atoms") or []:
            atom["verbatim_text"] = _cut(
                str(atom.get("verbatim_text", "")),
                f"{part.get('id', '')}:atom:{atom.get('atom_id', '')}",
            )
    return parts, {
        "max_chars": int(max_chars),
        "stated": True,
        "clipped": clipped,
        "budget_exhausted_by": clipped[-1]["where"] if clipped else "",
    }


@mcp.tool()
def compliance_search(
    query: str,
    jurisdiction: str = "",
    standard: str = "",
    layer: str = "",
    valid_at: str = "",
    known_at: str = "",
    requirement: str = "",
    relations: str = "governing",
    top_k: int = 10,
    max_chars: int = 4000,
    include_dual_document: bool = False,
) -> dict[str, Any]:
    """Ranked sections across BOTH corpora — regulatory and operator together.

    The composition itself is :func:`core.search_service.search`, which the
    reader's tool surface calls too: one pre-ranking predicate with one set of
    semantics, rather than a second implementation that filters after ranking.
    Pass ``include_dual_document=True`` to also attach the full dual-document
    payload when no requirement is scoped (off by default to stay within
    interactive chat context budgets).
    """
    repo = _repo()
    try:
        result = _search_service.search(
            repo,
            query,
            jurisdiction=jurisdiction,
            standard=standard,
            layer=layer,
            valid_at=valid_at,
            known_at=known_at,
            requirement=requirement,
            relations=relations,
            top_k=top_k,
            max_chars=max_chars,
        )
        if include_dual_document and not requirement.strip():
            from portal.modules.compliance.core import dual_document

            payload = dual_document.build(repo, query=query, **_payload_pricing())
            if payload.get("resolved"):
                payload.pop("mode", None)
                result["dual_document"] = payload
        return result
    finally:
        repo.close()


def _match_document_alias(repo: Any, ref: str) -> dict[str, Any]:
    """Case-insensitive doc_no / title / filename-stem fallback for a document ref.

    Live Stage 5 runs showed the seat trying a document's ``doc_no``
    ("OT-POL-007") and its PDF filename before finding the exact
    ``logical_id``, wasting three tool hops. A unique match resolves the
    document's sections directly (the payload echoes the ``logical_id`` so
    the next call can use it); an ambiguous match lists the candidates.
    Only active (governing) revisions are considered.
    """
    from portal.modules.compliance.core.section_index import (
        _governing_revisions,
        resolve_sections,
        sections_in_scope,
    )

    wanted = str(ref).strip().casefold()
    if not wanted:
        return {}
    ref_stem = Path(wanted).stem
    jurisdictions = ("internal", "operator_note", "US")
    active = set().union(
        *(_governing_revisions(repo, jurisdiction) for jurisdiction in jurisdictions)
    )
    rows = repo._conn.execute(
        """SELECT d.logical_id, d.title, r.revision_id, r.document_number
           FROM source_documents d
           JOIN document_revisions r ON r.logical_id = d.logical_id
           WHERE d.jurisdiction IN (?,?,?)
           ORDER BY d.logical_id, r.revision_id""",
        jurisdictions,
    ).fetchall()
    matches: dict[str, dict[str, Any]] = {}
    for row in rows:
        if str(row["revision_id"]) not in active:
            continue
        logical_id = str(row["logical_id"])
        candidates = (
            ("document_number", str(row["document_number"] or "")),
            ("title", str(row["title"] or "")),
            ("filename", Path(logical_id).stem),
        )
        matched_by = ""
        for field, value in candidates:
            if not value:
                continue
            if value.casefold() == wanted or (field == "filename" and value.casefold() == ref_stem):
                matched_by = field
                break
        if not matched_by or logical_id in matches:
            continue
        matches[logical_id] = {
            "logical_id": logical_id,
            "document_number": row["document_number"],
            "title": row["title"],
            "matched_by": matched_by,
        }
    if not matches:
        return {}
    if len(matches) == 1:
        descriptor = next(iter(matches.values()))
        ids = sections_in_scope(repo, logical_id=str(descriptor["logical_id"]))
        return {
            "document_match": {
                "logical_id": descriptor["logical_id"],
                "matched_by": descriptor["matched_by"],
                "note": "matched case-insensitively; pass this logical_id next time",
            },
            "sections": resolve_sections(repo, ids[:200]),
        }
    return {"available_matches": sorted(matches.values(), key=lambda m: str(m["logical_id"]))}


def _lenient_flag(value: Any) -> bool:
    """Read whatever the caller sent as a flag; a rejected call reads nothing at all."""
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, str):
        return value.strip().lower() in {"true", "t", "yes", "y", "on", "1"}
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, (list, tuple, set, dict)):
        return len(value) > 0
    return False


def _lenient_max_chars(value: Any) -> int:
    """Coerce a misspelled ceiling to the default instead of rejecting the read."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return 6000


@mcp.tool()
def compliance_read(
    ref: str,
    neighbors: Annotated[bool, BeforeValidator(_lenient_flag)] = False,
    max_chars: Annotated[int, BeforeValidator(_lenient_max_chars)] = 6000,
) -> dict[str, Any]:
    """Verbatim text of any addressable unit, from either side.

    ``ref`` is a ``section_id``, a regulatory address (``CIP-007-6 R2 Part
    2.2``), a glossary term, or a document ``logical_id``. When no exact id
    matches, the ref is tried case-insensitively against each active
    document's ``doc_no``, title and filename stem — a unique hit reads the
    document directly (with the ``logical_id`` echoed for the next call);
    an ambiguous hit returns ``available_matches`` instead of failing flat.
    With ``neighbors`` the unit's parent heading and its siblings in
    reading order come too.

    Per-call ceiling ``max_chars`` defaults to 6,000 — the same bound the
    nested reader's dispatch applies — and every clip is STATED in the unit's
    note, never silent. A section needing more can be asked for again.
    """
    from portal.modules.compliance.core import reading_assembly, section_index

    repo = _repo()
    try:
        resolved = section_index.resolve_sections(repo, [ref])
        if not resolved:
            resolved = _resolve_by_address(repo, ref)
        document_match: dict[str, Any] | None = None
        if not resolved:
            alias = _match_document_alias(repo, ref)
            if alias.get("available_matches"):
                return {
                    "ref": ref,
                    "resolved": False,
                    "detail": "no section, address, glossary term or document with that id; "
                    "the ref matched several documents case-insensitively",
                    "available_matches": alias["available_matches"],
                }
            document_match = alias.get("document_match")
            resolved = alias.get("sections") or {}
            if not resolved and document_match:
                return {
                    "ref": ref,
                    "resolved": False,
                    "detail": "the matched document has no captured sections in the store",
                    **document_match,
                }
        if not resolved:
            return {
                "ref": ref,
                "resolved": False,
                "detail": "no section, address, glossary term or document with that id; "
                + reading_assembly.ACCEPTED_ADDRESS_FORMS,
            }
        units: list[dict[str, Any]] = []
        remaining_sections: list[dict[str, Any]] = []
        remaining_chars = max(500, int(max_chars))
        for section_id, entry in sorted(resolved.items(), key=lambda kv: kv[1].get("ordinal", 0)):
            if units and remaining_chars <= 0:
                remaining_sections.append(
                    {
                        "section_id": section_id,
                        "heading_lineage": entry.get("heading_lineage") or entry.get("path", ""),
                        "title": entry.get("title", ""),
                    }
                )
                continue
            text, note = _clip(entry.get("text", ""), remaining_chars)
            remaining_chars = max(0, remaining_chars - len(text))
            units.append(
                {
                    **_provenance(entry),
                    "section_id": section_id,
                    "text": _with_cite_header(entry, text),
                    **note,
                }
            )
        payload: dict[str, Any] = {"ref": ref, "resolved": True, "units": units}
        if document_match:
            payload["document_match"] = document_match
        if remaining_sections:
            payload["remaining_sections"] = remaining_sections
            payload["truncation"] = {
                "max_chars": max_chars,
                "omitted_units": len(remaining_sections),
                "note": "Call compliance_read(ref=<section_id>) for any listed remaining section.",
            }
        if neighbors and units:
            payload["neighbors"] = _neighbors(repo, list(resolved.values())[0], max_chars)
        parsed = reading_assembly.parse_ref(ref)
        if parsed is not None:
            payload["address"] = str(reading_assembly.canonical_ref(repo, parsed))
        return payload
    finally:
        repo.close()


@mcp.tool()
def compliance_conflicts(ref: str, valid_at: str = "", span_chars: int = 1000) -> dict[str, Any]:
    """Cross-tier contradictions touching a requirement's neighbourhood.

    Property 2 (SUBSTRATE_PROPERTIES_V1 P4): a contradiction between tiers is a
    RETRIEVABLE fact, not a verdict-engine byproduct. ``ref`` is a regulatory
    address (``CIP-007-6 R2 Part 2.2``). Each conflict carries both spans, both
    tiers, both section ids — emitted and **never reconciled**. The standard is
    compared only through its own requirement rows, so the standard quoting
    itself (Measures, Guidelines) does not fire. Documents with no recorded
    tier are listed under ``untiered_sections`` — visible, never ranked.
    Ceiling: each span is clipped to ``span_chars`` (default 1,000) with the
    clip stated; the ids are what let a reader pull the full text.
    """
    from portal.modules.compliance.core import reading_assembly

    repo = _repo()
    try:
        payload = reading_assembly.conflicts_for_requirement(repo, ref, valid_at=valid_at)
        for conflict in payload.get("conflicts", []):
            for key in ("higher_authority", "lower_authority", "span_a", "span_b"):
                span = conflict.get(key)
                if isinstance(span, dict) and isinstance(span.get("text"), str):
                    text, note = _clip(span["text"], span_chars)
                    span["text"] = text
                    if note:
                        span["truncation"] = {"span_chars": span_chars, "stated": True}
        return payload
    finally:
        repo.close()


@mcp.tool()
def compliance_links(
    ref: str, direction: str = "both", status: str = "", derivation: str = "", max_edges: int = 50
) -> dict[str, Any]:
    """Traversal over ``relationship_assertions`` — REFERENCES, not text.

    Every edge is labelled with its status, how it was derived and its
    confidence — a proposal is visible as a proposal, never as an established
    fact. What an edge names is UNREAD until ``compliance_read`` fetches it.
    Ceiling: ``max_edges`` (default 50) with truncation stated when hit.
    """
    repo = _repo()
    try:
        payload = _graph_links(repo, ref, direction, status, derivation)
        edges = payload.get("edges")
        if isinstance(edges, list) and len(edges) > max_edges:
            payload["edges"] = edges[:max_edges]
            payload["truncation"] = {
                "max_edges": max_edges,
                "stated": True,
                "omitted_edges": len(edges) - max_edges,
            }
        return payload
    finally:
        repo.close()


@mcp.tool()
def compliance_timeline(ref: str) -> dict[str, Any]:
    """Every revision of either side, with its dates — plus the semantic delta
    between consecutive regulatory revisions.

    DATA_TRUTH DD3c: the result carries ``dual_document`` built for the whole
    revision family of the addressed requirement — part (a) holds EVERY
    revision's normative anchors (CIP-003-8's words beside CIP-003-9's), since
    a revision-comparison question needs the predecessor's text no
    current-revision payload can carry."""
    repo = _repo()
    try:
        result = _graph_timeline(repo, ref)
        from portal.modules.compliance.core import dual_document

        result["dual_document"] = dual_document.build_cross_revision(
            repo, ref, **_payload_pricing()
        )
        return result
    finally:
        repo.close()


@mcp.tool()
def compliance_coverage(
    standard: str = "", requirement: str = "", valid_at: str = "", known_at: str = ""
) -> dict[str, Any]:
    """Per requirement: the internal sections linked to it, and explicitly those
    with none. **Deterministic — no model call, no background job.**

    This is what replaces ``compliance_gaps``'s job queue for the question
    "where are we not covered". It reports recorded links, not verdicts: what a
    link MEANS is read at question time.

    Link standing (DATA_TRUTH Amendment 2 DD3c): ``linked_sections`` counts
    APPROVED links and ``operator_declared_sections`` carries the operator's
    own traceability declarations (``operator_traceability`` IMPLEMENTS rows,
    labelled as declarations) — either sets ``has_link``. Similarity
    ``proposed`` edges are listed under ``unverified_proposals``, labelled
    unverified, and never set ``has_link``.

    The result also carries ``dual_document``: the dual-document payload for
    the addressed requirement (the standard's normative Parts and the
    operator's document set, priced and guarded like
    ``compliance_context(mode=material)``), so a coverage question reads the
    material it reports on.
    """
    from portal.modules.compliance.core import reading_assembly, section_index

    repo = _repo()
    try:
        if requirement and reading_assembly.parse_ref(requirement) is not None:
            target = requirement  # already a full address: prefixing the standard doubled it
        else:
            target = f"{standard} {requirement}".strip() if requirement else standard
        parsed = reading_assembly.parse_ref(target) or reading_assembly.parse_ref(standard)
        if parsed is None:
            return {"error": reading_assembly.not_an_address(target)}
        parsed = reading_assembly.canonical_ref(repo, parsed, valid_at)
        assembly_ids = section_index.sections_in_scope(repo, logical_id=parsed.logical_id)
        refs = sorted(
            {
                str(r[0])
                for r in repo._conn.execute(
                    "SELECT DISTINCT src_ref FROM relationship_assertions WHERE src_ref LIKE ?",
                    (f"{parsed.standard}%",),
                ).fetchall()
            }
        )
        if requirement:
            refs = [r for r in refs if f" R{parsed.requirement}" in r]
        rows: list[dict[str, Any]] = []
        for ref in refs:
            edges = repo._conn.execute(
                """SELECT dst_ref, status, derivation FROM relationship_assertions
                   WHERE src_ref = ? AND (
                     status IN ('approved','machine_determined')
                     OR (status = 'proposed' AND derivation <> 'operator_traceability')
                   )""",
                (ref,),
            ).fetchall()
            approved: list[tuple[str, str]] = []
            declared: list[str] = []
            proposals: list[str] = []
            for dst, status, derivation in edges:
                dst, derivation = str(dst), str(derivation or "")
                if derivation == "operator_traceability":
                    declared.append(dst)
                elif status == "proposed":
                    proposals.append(dst)
                else:
                    approved.append((dst, status))
            linked = section_index.resolve_sections(repo, [d for d, _ in approved])
            declared_linked = section_index.resolve_sections(repo, declared)
            rows.append(
                {
                    "requirement": ref,
                    "linked_sections": [
                        {
                            **_provenance(entry),
                            "status": dict(approved).get(sid, ""),
                        }
                        for sid, entry in linked.items()
                    ],
                    "operator_declared_sections": [
                        {
                            **_provenance(entry),
                            "standing": "the operator's own traceability declaration",
                        }
                        for sid, entry in declared_linked.items()
                    ],
                    "unverified_proposals": [
                        {"dst_ref": dst, "standing": "unverified similarity proposal"}
                        for dst in proposals
                        if dst not in linked
                    ],
                    "unresolvable_links": [str(d) for d, _ in approved if str(d) not in linked],
                    "has_link": bool(linked or declared_linked),
                }
            )
        result = {
            "standard": parsed.standard,
            "requirement": parsed.requirement,
            "valid_at": valid_at or "latest effective",
            "known_at": known_at or "latest recorded knowledge",
            "sections_in_standard": len(assembly_ids),
            "requirements": rows,
            "requirements_with_no_link": [r["requirement"] for r in rows if not r["has_link"]],
            "deterministic": True,
        }
        from portal.modules.compliance.core import dual_document

        result["dual_document"] = dual_document.build(
            repo, requirement_ref=target, **_payload_pricing()
        )
        return result
    finally:
        repo.close()


@mcp.tool()
def compliance_note(
    subject_ref: str, body: str, kind: str = "note", author: str = ""
) -> dict[str, Any]:
    """Record an operator decision, intent or rationale as a dated, attributed,
    immutable source — citeable and retrievable from the next question onward."""
    from portal.modules.compliance.core.notes import write_note

    repo = _repo()
    try:
        return write_note(repo, subject_ref=subject_ref, body=body, kind=kind, author=author)
    except ValueError as exc:
        return {"error": str(exc)}
    finally:
        repo.close()


@mcp.tool()
def compliance_notes(
    subject_ref: str = "", limit: int = 20, max_chars: int = 4000
) -> dict[str, Any]:
    """Operator notes about one subject, newest first, with their verbatim text.

    Ceiling: each note's text is clipped to ``max_chars`` (default 4,000) with
    the clip stated on the note; ``limit`` (default 20) bounds the count.
    """
    from portal.modules.compliance.core.notes import notes_for

    repo = _repo()
    try:
        notes = notes_for(repo, subject_ref, limit=limit)
        for note in notes:
            text, clip_note = _clip(str(note.get("text", "")), max_chars)
            note["text"] = text
            if clip_note:
                note["truncation"] = {"max_chars": max_chars, "stated": True}
        return {"subject_ref": subject_ref, "notes": notes}
    finally:
        repo.close()


def _index_row(section: dict[str, Any]) -> dict[str, Any]:
    """One index row: where a section IS, and nothing of what it says."""
    from portal.modules.compliance.core.jurisdiction import is_operator_side

    jurisdiction = str(section.get("jurisdiction", ""))
    side = (
        "operator"
        if is_operator_side(jurisdiction)
        else (jurisdiction or str(section.get("source_kind", "")) or "regulatory")
    )
    return {
        "section_id": section.get("section_id", ""),
        "side": side,
        "document": section.get("document_title") or section.get("logical_id", ""),
        "path": section.get("path", "") or section.get("headings", ""),
        "title": section.get("title", ""),
        "page": section.get("page"),
        "link_status": section.get("link_status", ""),
    }


#: Components whose sections vary with the requirement — the rows an index
#: exists to enumerate. The rest are the standard's own fixed body (Section 4,
#: Section 6, the implementation plan, version history…), identical for every
#: requirement in the revision: measured on CIP-007-6 R2 Part 2.2, 210 of the
#: 233 index rows were that fixed body, which is not what "what is in scope
#: here" means and would have pushed one index call past a fifth of a 32k
#: window. They are collapsed to a stated count instead of silently dropped.
_INDEX_SCOPED = {
    "requirement",
    "measures",
    "technical_basis",
    "rationale",
    "vsl",
    "glossary",
    "linked_internal",
    "conflicts",
}


@mcp.tool()
def compliance_context(
    ref: str,
    mode: str = "index",
    budget_tokens: int = 60000,
    include: str = "",
    profile: str = "",
    valid_at: str = "",
) -> dict[str, Any]:
    """**The neighbourhood, in the shape a turn needs.** Three renderings of one
    scope, one tool.

    Default ``mode=index``: one row per section in every component — section
    id, side, document, section path, page, link status — plus the operator
    notes' metadata. NO text travels in this payload, and nothing is sized or
    omitted: the index is the whole neighbourhood. It is what a conversation
    needs to decide what to read next; the text itself is one
    ``compliance_read`` (or ``compliance_requirement``) call away.

    ``mode=material``: THE DUAL-DOCUMENT PAYLOAD (DATA_TRUTH Amendment 1
    DD3) — a question is a dual-document request, so this returns (a) the
    resolved requirement's normative text, every Part, from the governing
    anchors (no fixed body — ``compliance_read`` it on request), (b) the
    operator's own documents for that standard — filing folder plus every
    document whose traceability appendix names the standard — whole, in
    document order, structure stripped, every section labelled
    ``[document § heading] (section_id)``, (c) the operator's notes, and (d)
    the operator's traceability facts as labelled declarations. Priced against
    the declared window before it is returned: a document that does not fit
    whole is deferred and listed by title with a ``compliance_read``
    instruction — nothing is clipped and the engine is never allowed to
    truncate.

    ``mode=packet`` assembles full text — the requirement and its lead-in,
    every Part row, the Measures, the Guidelines and Technical Basis, the
    Rationale, VSL rows, Section 4/6, glossary, and the linked internal
    sections IN FULL — sized to ``budget_tokens``, with anything omitted NAMED.
    A packet is a batch-reader artifact, not one turn of a conversation: on a
    32k window a 60k-token packet ends the conversation in one call.

    ``profile`` (packet mode) scopes the packet — ``full`` (default),
    ``intent``, ``conformance``, ``audit``, ``timeline``. Measured on
    CIP-007-6 R2 Part 2.2: full is ~29,900 tokens, ``intent`` ~6,500.
    """
    from portal.modules.compliance.core.notes import notes_for
    from portal.modules.compliance.core.reading_assembly import assemble

    repo = _repo()
    try:
        if mode == "material":
            from portal.modules.compliance.core import dual_document

            payload = dual_document.build(repo, requirement_ref=ref, **_payload_pricing())
            if payload.get("error"):
                payload.pop("error", None)
                payload.update({"mode": "material", "ref": ref, "resolved": False})
                return payload
            if not payload["window"]["fits"] and not payload["documents_included"]:
                # the guard's last line: even (a)+(c)+(d) exceed the smallest
                # reachable route's window — refuse as one message, route to
                # per-Part reads, never let the engine truncate (DD4)
                return {
                    "mode": "material_routed",
                    "ref": ref,
                    "window": payload["window"],
                    "note": (
                        f"the payload for {ref} needs {payload['window']['estimated_tokens']} "
                        "tokens against a "
                        f"{payload['window']['context_limit']}-token route ceiling; nothing "
                        "was clipped or summarised. Read it per Part: "
                        "compliance_context(mode=material, ref=<part ref>) for each ref, "
                        "or compliance_read(ref) for any section."
                    ),
                }
            return payload
        if mode == "packet":
            payload = assemble(
                repo,
                ref,
                budget_tokens=budget_tokens,
                include=[i.strip() for i in include.split(",") if i.strip()] or None,
                profile=profile,
                valid_at=valid_at,
            )
            payload["operator_notes"] = notes_for(repo, ref)
            return payload
        # The index covers the WHOLE neighbourhood regardless of any budget —
        # it is ids and paths, so there is nothing to leave out. Omitting a
        # component here would be the packet's budget rule misapplied to a
        # table of contents.
        payload = assemble(
            repo,
            ref,
            budget_tokens=2**31,
            include=[i.strip() for i in include.split(",") if i.strip()] or None,
            profile=profile,
            valid_at=valid_at,
        )
        if "error" in payload:
            return payload
        payload["mode"] = "index"
        components: list[dict[str, Any]] = []
        collapsed: list[dict[str, Any]] = []
        for c in payload.get("components", []):
            if c["component"] in _INDEX_SCOPED:
                components.append(
                    {
                        "component": c["component"],
                        "why": c["why"],
                        "n_sections": len(c["sections"]),
                        "sections": [_index_row(s) for s in c["sections"]],
                    }
                )
            else:
                collapsed.append(
                    {
                        "component": c["component"],
                        "why": c["why"],
                        "n_sections": len(c["sections"]),
                        "reason": (
                            "the standard's own fixed body, identical for every requirement in "
                            "this revision — not enumerated per row; read by address or via "
                            "compliance_sources"
                        ),
                    }
                )
        payload["components"] = components
        payload["fixed_components_collapsed"] = collapsed
        payload["operator_notes"] = [
            {
                key: note[key]
                for key in ("section_id", "kind", "subject_ref", "created_at", "author")
                if key in note
            }
            for note in notes_for(repo, ref)
        ]
        payload["note"] = (
            "index only — no text is in this payload; read any id with compliance_read, "
            "or fetch requirement+Measures+GTB with compliance_requirement; "
            "mode=packet assembles full text to an explicit budget"
        )
        return payload
    finally:
        repo.close()


@mcp.tool()
def compliance_ask(
    question: str,
    ref: str,
    profile: str = "",
    budget_tokens: int = 12000,
    valid_at: str = "",
    thread_id: str = "",
    model: str = "",
    store: bool = True,
) -> dict[str, Any]:
    """Ask a question about a requirement, with the whole neighbourhood in front
    of the reader.

    The reader receives ``compliance_context`` output — nothing filtered on its
    behalf, nothing marked ineligible to cite, and whatever the budget could not
    hold named in the payload. It answers in prose, quoting the words each
    claim rests on (and any section ids it carries are resolved too). Those
    ids are then resolved and reported with **what each one is**, so an argument
    resting on the standard quoting itself as the operator's control is visible
    as exactly that. Nothing here adjudicates whether the answer is right.

    ``budget_tokens`` declares 12,000 because that is what the reader enforces
    (the assembly is clamped there regardless of what is asked); the declared
    default used to say 60,000 — a policy the code silently ignored. This is a
    batch and standing-question tool, not a conversation turn.

    The answer is retained and projected into the corpus as a ``derived``
    source: contestable, retrievable, never a fact, and outranked by any
    operator note on the same subject.

    ``store=False`` answers the question WITHOUT projecting it. The receipt is
    still retained — a reading that failed is the one most worth a record of —
    but nothing enters the corpus. That exists because projection makes repeated
    readings of one question dependent on each other: measured on three live
    CIP-007-6 Part 2.4 readings, run 1's answer came back inside run 2's
    ``compliance_links`` payload as a ``reading`` edge, run 2's prompt grew by
    105 tokens, and run 2 PASSED a case run 1 failed — at temperature 0.0, where
    the model cannot be the variable. Correct product behaviour; fatal
    measurement behaviour.
    """
    from portal.modules.compliance.core.reader import read
    from portal.modules.compliance.core.runtime_config import reading_seat

    repo = _repo()
    try:
        return read(
            repo,
            question,
            ref,
            model=model or reading_seat(),
            budget_tokens=budget_tokens,
            profile=profile,
            valid_at=valid_at,
            thread_id=thread_id,
            store=store,
        )
    except Exception as exc:  # noqa: BLE001 - a transport failure is reported, not raised
        return {"error": str(exc), "question": question, "ref": ref}
    finally:
        repo.close()


@mcp.tool()
def compliance_answers(
    subject_ref: str = "", include_superseded: bool = True, max_chars: int = 2000
) -> dict[str, Any]:
    """Stored answers about a subject, each with its citations and its standing.

    An answer is one analyst's notes pinned to the revisions it read. It is
    marked SUPERSEDED once a revision it cited moves, and it says so when an
    operator note on the same subject outranks it. Ceiling: each answer's text
    is clipped to ``max_chars`` (default 2,000) with the clip stated — read the
    sections, not the prior answers, when the argument matters.
    """
    from portal.modules.compliance.core.reader import answers_for

    repo = _repo()
    try:
        rows = answers_for(repo, subject_ref, include_superseded=include_superseded)
        for row in rows:
            text, clip_note = _clip(str(row.get("answer", "")), max_chars)
            row["answer"] = text
            if clip_note:
                row["truncation"] = {"max_chars": max_chars, "stated": True}
        return {"subject_ref": subject_ref, "answers": rows}
    finally:
        repo.close()


@mcp.tool()
def compliance_correct(answer_id: str, correction: str, author: str = "") -> dict[str, Any]:
    """Record an operator's correction of a stored answer. Kept as a note about
    the answer: the operator's word outranks the reading, and both remain."""
    from portal.modules.compliance.core.reader import record_correction

    repo = _repo()
    try:
        return record_correction(repo, answer_id, correction, author=author)
    except ValueError as exc:
        return {"error": str(exc)}
    finally:
        repo.close()


@mcp.tool()
def compliance_standing_questions(
    question: str = "", subject_ref: str = "", run: bool = False
) -> dict[str, Any]:
    """The questions the operator already cares about.

    With ``question``, records one. With ``run``, answers every standing
    question for ``subject_ref`` and keeps the answers — which is what the
    on-ingest assessment IS: the system asking the questions you already care
    about, not filling in a schema.
    """
    from portal.modules.compliance.core.reader import (
        add_standing_question,
        run_standing_questions,
        standing_questions,
    )

    repo = _repo()
    try:
        recorded = add_standing_question(repo, question, subject_ref) if question else ""
        if run and subject_ref:
            from portal.modules.compliance.core.runtime_config import reading_seat

            answers = run_standing_questions(repo, subject_ref, model=reading_seat())
            return {"subject_ref": subject_ref, "ran": len(answers), "answers": answers}
        return {
            "recorded": recorded,
            "questions": standing_questions(repo, subject_ref),
        }
    finally:
        repo.close()


# mcp.custom_route() has no return annotation upstream — bind the concrete
# decorator type once so routed handlers keep their annotations.
_route: Callable[
    ...,
    Callable[[Callable[..., Awaitable[Response]]], Callable[..., Awaitable[Response]]],
] = mcp.custom_route

_DISPATCH: dict[str, Callable[..., Any]] = {
    "lookup_control": lookup_control,
    "search_controls": search_controls,
    "nerc_cip_requirement": nerc_cip_requirement,
    "compliance_requirement": compliance_requirement,
    "nerc_cip_currency": nerc_cip_currency,
    "map_frameworks": map_frameworks,
    "patch_evidence": patch_evidence,
    "refresh_catalogs": refresh_catalogs,
    "compliance_ingest": compliance_ingest,
    "compliance_search": compliance_search,
    "compliance_orphans": compliance_orphans,
    "compliance_mappings": compliance_mappings,
    "compliance_scope": compliance_scope,
    "compliance_route": compliance_route,
    "compliance_review_list": compliance_review_list,
    "compliance_review_decide_batch": compliance_review_decide_batch,
    "compliance_review_decide": compliance_review_decide,
    "compliance_sources": compliance_sources,
    "compliance_trace": compliance_trace,
    "compliance_draft_revisions": compliance_draft_revisions,
    "compliance_intentionality": compliance_intentionality,
    "compliance_flexibility": compliance_flexibility,
    "compliance_compare": compliance_compare,
    # BILATERAL_CORPUS_V1 P5 — addressability and the reading assembly
    "compliance_read": compliance_read,
    "compliance_conflicts": compliance_conflicts,
    "compliance_links": compliance_links,
    "compliance_timeline": compliance_timeline,
    "compliance_coverage": compliance_coverage,
    "compliance_note": compliance_note,
    "compliance_notes": compliance_notes,
    "compliance_context": compliance_context,
    # BILATERAL_CORPUS_V1 P6 — the reader and the conversation corpus
    "compliance_ask": compliance_ask,
    "compliance_answers": compliance_answers,
    "compliance_correct": compliance_correct,
    "compliance_standing_questions": compliance_standing_questions,
}


#: Tool calls this process served as the compliance evaluation instance (root-fix Part 2c-2);
#: live acceptance reads it to prove that scoped calls were routed here.
_EVAL_SERVED: collections.Counter[str] = collections.Counter()


def _eval_health() -> dict[str, Any]:
    if os.environ.get("COMPLIANCE_EVAL_INSTANCE") != "1":
        return {}
    return {"eval_instance": True, "eval_tool_calls": sum(_EVAL_SERVED.values())}


@_route("/health", methods=["GET"])
async def health_check(request: Request) -> JSONResponse:
    return JSONResponse(
        {
            "status": "ok",
            "service": "compliance-mcp",
            "port": _port,
            **build_info(),
            **_eval_health(),
        }
    )


@_route("/ready", methods=["GET"])
async def ready(request: Request) -> JSONResponse:
    return JSONResponse({"port": _port, "catalogs": [p.stem for p in _DATA.glob("*.json")]})


@_route("/debug/compliance-counters", methods=["GET"])
async def compliance_counters(request: Request) -> JSONResponse:
    from portal.modules.compliance.core.runtime import snapshot

    return JSONResponse(snapshot())


@_route("/tools", methods=["GET"])
async def list_tools(request: Request) -> JSONResponse:
    return JSONResponse({"tools": TOOLS_MANIFEST})


#: How often invoke_tool checks for a disconnected client (seconds).
_DISCONNECT_POLL_S = 0.5


@_route("/tools/{tool_name}", methods=["POST"])
async def invoke_tool(request: Request) -> JSONResponse:
    name = request.path_params.get("tool_name", "")
    fn = _DISPATCH.get(name)
    if fn is None:
        return JSONResponse({"error": f"unknown tool {name}"}, status_code=404)
    if os.environ.get("COMPLIANCE_EVAL_INSTANCE") == "1":  # root-fix Part 2c-2
        from portal.modules.compliance.core.eval_instance import VERIFIED_TOOLS

        if name not in VERIFIED_TOOLS:
            return JSONResponse(
                {"error": f"{name} is not served by the evaluation instance"}, status_code=403
            )
        _EVAL_SERVED[name] += 1
    try:
        body = await request.json()
    except Exception:
        body = {}
    args = body.get("arguments", body) if isinstance(body, dict) else {}
    try:
        # A sync tool handler called directly here (no `await` in between)
        # blocks this process's ENTIRE event loop until it returns — verified
        # live: a 13-minute compliance_gaps call made this server's own
        # /health and every other tool (lookup_control, a pure dict lookup)
        # time out for its whole duration. run_in_executor moves the blocking
        # call off the loop so concurrent requests (including this server's
        # own health check) keep being served while a slow tool runs.
        #
        # The tool runs under a copy of this context carrying a cancel token;
        # a client that disconnects cancels it (HOST_MEMORY_SAFETY W3.4), so
        # model calls stop instead of running on server-side after a timeout.
        token = _cancellation.CancelToken()
        context = contextvars.copy_context()
        context.run(_cancellation.bind, token)
        started = time.monotonic()
        future = asyncio.get_running_loop().run_in_executor(
            None, functools.partial(context.run, fn, **args)
        )
        while True:
            done, _ = await asyncio.wait({future}, timeout=_DISCONNECT_POLL_S)
            if done:
                break
            if not token.is_set() and await request.is_disconnected():
                token.cancel()
                logger.info("compliance tool %s: client disconnected; cancelling", name)
        result = future.result()
        return JSONResponse(result)
    except _cancellation.TurnCancelled as e:
        receipt = {
            "tool": name,
            "status": "cancelled",
            "reason": str(e) or "client disconnected",
            "elapsed_s": round(time.monotonic() - started, 2),
        }
        logger.info("compliance tool %s cancelled after %.1fs", name, receipt["elapsed_s"])
        return JSONResponse({"error": "cancelled", "receipt": receipt}, status_code=499)
    except TypeError as e:
        return JSONResponse({"error": f"bad params: {e}"}, status_code=400)


def _native_eval_tool_guard(name: str) -> bool:
    if os.environ.get("COMPLIANCE_EVAL_INSTANCE") != "1":
        return True
    from portal.modules.compliance.core.eval_instance import VERIFIED_TOOLS

    return name in VERIFIED_TOOLS


bind_native_context(mcp, _native_eval_tool_guard)
align_native_tools(mcp, TOOLS_MANIFEST)

if __name__ == "__main__":
    mcp.run(transport="streamable-http", host="0.0.0.0", port=_port)
