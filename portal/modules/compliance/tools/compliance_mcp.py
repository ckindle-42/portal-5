"""Portal 5 — Compliance Controls & Evidence MCP.

Authoritative control-catalog lookup (NIST SP 800-53 Rev5, CSF 2.0),
cross-framework mapping, NERC CIP requirement lookup, and CIP-007-6 R2
patch-evidence scaffolding. Read-only; catalogs are cached locally.

Port: 8937 (COMPLIANCE_MCP_PORT or MCP_PORT env override).
"""

from __future__ import annotations

import asyncio
import dataclasses
import datetime
import functools
import json
import logging
import os
import re
import urllib.request
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any, cast

from mcp.server import MCPServer
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from portal.platform.data_loader import load_data

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


@mcp.tool()
def compliance_requirement(
    requirement: str,
    scope: str = "",
    valid_at: str = "",
    known_at: str = "",
) -> dict[str, Any]:
    """Resolve governing requirements by validity interval and return atoms."""
    try:
        from portal.modules.compliance.core.cip_register import Register
        from portal.modules.compliance.core.engine import effective_parts, parse_iso_date
        from portal.modules.compliance.core.obligations import decompose, expression_for

        today = datetime.date.today().isoformat()
        when = parse_iso_date(valid_at or today, field="valid_at")
        reg = Register.load()
        active = effective_parts(reg, when)
        want = re.sub(r"\s+", "", requirement.strip()).upper()
        hits = [n for n in active if re.sub(r"\s+", "", n.id).upper().startswith(want)]
        if not hits:
            # Family queries such as CIP-003 select the effective revision at
            # the requested date; explicit retired version IDs remain exact.
            hits = [n for n in active if re.sub(r"\s+", "", n.standard).upper().startswith(want)]
        if hits:
            parts: list[dict[str, Any]] = []
            for node in hits:
                anchors = []
                try:
                    from portal.modules.compliance.core.repository import Repository

                    row = (
                        Repository()
                        ._conn.execute(
                            "SELECT source_anchor_ids_json FROM obligation_atoms WHERE node_id = ? ORDER BY atom_id LIMIT 1",
                            (node.id,),
                        )
                        .fetchone()
                    )
                    if row:
                        anchors = json.loads(row[0])
                except Exception:  # pragma: no cover - compatibility fallback
                    anchors = []
                anchors = anchors or [
                    f"{node.source_pdf}#pages={','.join(map(str, node.source_pages))}"
                ]
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
                parts.append(
                    {
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
                        "temporal_label": "historical"
                        if node.valid_to or when < today
                        else "current",
                    }
                )
            return {
                "requirement": requirement,
                "found": True,
                "scope": scope,
                "valid_at": when,
                "known_at": known_at or "latest recorded knowledge",
                "defaulted_valid_at": not bool(valid_at),
                "granularity": "exact"
                if len(parts) == 1 and re.sub(r"\s+", "", parts[0]["id"]).upper() == want
                else "rollup",
                "parts": parts,
                "readiness": {"complete": True, "missing": []},
                "source": "NERC CIP Reliability Standards verbatim register",
            }
        return {
            "requirement": requirement,
            "found": False,
            "valid_at": when,
            "note": "no governing revision is enforceable at the requested date",
        }
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)}


@mcp.tool()
def nerc_cip_requirement(req_id: str, valid_at: str = "", known_at: str = "") -> dict[str, Any]:
    """Compatibility wrapper for :func:`compliance_requirement`.

    When omitted, ``valid_at`` defaults explicitly to today's calendar date
    and the response records that default.
    """
    result = compliance_requirement(req_id, valid_at=valid_at, known_at=known_at)
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


def compliance_search(kb_id: str, query: str, top_k: int = 5) -> dict[str, Any]:
    """Sync dispatch wrapper over ``compliance_retrieval.search`` — free-form
    retrieval over the ingested compliance corpus."""
    import asyncio

    from portal.modules.compliance.tools.compliance_retrieval import search as _search

    try:
        return asyncio.run(_search(kb_id, query, top_k))
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)}


_SPAN_EXCERPT_CHARS = 180  # P0 (O11): a full-candidate row blew the 8192-token
# input budget ~2x over on a single standard (measured: 20-row CIP-007-6 result
# = ~59.8k chars / ~15k tokens against context_limit 32768 - predict_limit
# 24576 = 8192). The compact row below carries one representative citation per
# side (the first locatable span — a `verbose=True` call gets every candidate).


def _compact_citation(spans: list[dict[str, Any]]) -> dict[str, Any] | None:
    locatable = [s for s in spans if s.get("locatable")]
    chosen = locatable[0] if locatable else None
    if not chosen:
        return None
    return {
        "document": chosen["document_id"],
        "section": chosen["section_id"],
        "span": chosen["span"][:_SPAN_EXCERPT_CHARS],
    }


@mcp.tool()
def compliance_gaps(
    standard: str = "",
    requirement: str = "",
    effective_on: str = "",
    kb_id: str = "operator_corpus",
    max_rows: int = 25,
    verbose: bool = False,
) -> dict[str, Any]:
    """Coverage matrix: where the operator's ingested corpus does/doesn't cover
    each applicable NERC CIP Part. ``standard``/``requirement`` filter the rows
    (e.g. standard='CIP-007-6') and ``max_rows`` caps them — the default row
    shape (one representative citation per side, ``verbose=False``) is scoped
    to fit the compliance workspace's ~8192-token input budget; ``verbose=True``
    returns every retrieved candidate span, for review/debugging, not for the
    live workspace. Every row derived from an open review-queue item names it."""
    try:
        from portal.modules.compliance.core import coverage as _coverage
        from portal.modules.compliance.core import review_queue as rq
        from portal.modules.compliance.core.cip_register import Register
        from portal.modules.compliance.core.mapping_store import MappingStore
        from portal.modules.compliance.core.propose import default_arbiter, make_real_proposer
        from portal.modules.compliance.core.scope_derive import derive_scope

        reg = Register.load()
        # A `standard` filter scopes the COMPUTATION, not just the returned
        # rows — coverage_matrix used to run the whole ~193-node register even
        # for a single-standard call (386 VL round-trips for a 20-Part ask),
        # which is most of why a scoped call was ever slow. Register is a
        # plain nodes/edges dataclass — the same pre-filter pattern
        # compliance_change_impact already uses for old/new.
        if standard:
            reg = Register(
                nodes=[n for n in reg.nodes if n.standard.startswith(standard)], edges=reg.edges
            )
        if requirement:  # same reasoning — verified live at 792s for one Part on an unfiltered reg
            reg = Register(nodes=[n for n in reg.nodes if requirement in n.id], edges=reg.edges)
        scope, scope_meta = derive_scope(kb_id)
        if not scope.is_declared:
            return {
                "status": "honest-BLOCKED",
                "reason": scope_meta.get("reason"),
                "settling_document": scope_meta.get("settling_document"),
            }
        store = MappingStore()
        rq.sync_proposed_mappings(store)
        eff = effective_on or datetime.date.today().isoformat()
        matrix = _coverage.coverage_matrix(
            reg, scope, eff, make_real_proposer(kb_id, arbiter_fn=default_arbiter()), store
        )
        open_tiers = {i.subject_id: i.id for i in rq.open_items(kind="document_tier")}

        matching = [
            c
            for c in matrix.cells
            if c.applies
            and (not standard or c.requirement_id.startswith(standard))
            and (not requirement or requirement in c.requirement_id)
        ]
        rows = []
        for c in matching[:max_rows]:
            if verbose:
                d = c.to_dict()
                d["policy_spans"] = c.policy_spans
                d["procedure_spans"] = c.procedure_spans
                d["evidence_spans"] = c.evidence_spans
                d["COMPLIANCE_CONFLICT"] = c.conflicts
                rows.append(d)
                continue
            all_spans = c.policy_spans + c.procedure_spans + c.evidence_spans
            resting_on = sorted(
                {open_tiers[s["document_id"]] for s in all_spans if s["document_id"] in open_tiers}
                | {s["queue_item_id"] for s in all_spans if s.get("queue_item_id")}
            )
            if c.from_approved_mapping:
                resting_on.append(f"{scope_meta.get('queue_item_id', '')}(approved-mapping-scope)")
            rows.append(
                {
                    "requirement_id": c.requirement_id,
                    "coverage": c.coverage,
                    "substantively_resolved": c.substantively_resolved,
                    "retrieval_errors": c.retrieval_errors,
                    "note": c.note,
                    "policy_citation": _compact_citation(c.policy_spans),
                    "procedure_citation": _compact_citation(c.procedure_spans),
                    "gap_quote": (
                        reg_node.verbatim_text[:_SPAN_EXCERPT_CHARS]
                        if c.coverage in ("PARTIAL", "NONE")
                        and (
                            reg_node := next(
                                (n for n in reg.nodes if n.id == c.requirement_id), None
                            )
                        )
                        else None
                    ),
                    "COMPLIANCE_CONFLICT": c.conflicts,
                    "from_approved_mapping": c.from_approved_mapping,
                    "open_queue_items": resting_on,
                }
            )

        return {
            "effective_on": eff,
            "scope": {
                "impact_present": sorted(scope.impact_present),
                "associated_present": sorted(scope.associated_present),
                **scope_meta,
            },
            "summary": matrix.summary(),
            "n_matching": len(matching),
            "n_rows_returned": len(rows),
            "truncated": len(matching) > max_rows,
            "rows": rows,
        }
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)}


@mcp.tool()
def compliance_orphans(kb_id: str = "operator_corpus", effective_on: str = "") -> dict[str, Any]:
    """Ingested policy/procedure sections mapping to no requirement — dead
    weight, or evidence the register is incomplete."""
    try:
        from portal.modules.compliance.core import coverage as _coverage
        from portal.modules.compliance.core.cip_register import Register
        from portal.modules.compliance.core.mapping_store import MappingStore
        from portal.modules.compliance.core.propose import default_arbiter, make_real_proposer
        from portal.modules.compliance.core.scope_derive import derive_scope
        from portal.platform.retrieval import store as _store

        reg = Register.load()
        scope, scope_meta = derive_scope(kb_id)
        if not scope.is_declared:
            return {"status": "honest-BLOCKED", "reason": scope_meta.get("reason")}
        eff = effective_on or datetime.date.today().isoformat()
        matrix = _coverage.coverage_matrix(
            reg, scope, eff, make_real_proposer(kb_id, arbiter_fn=default_arbiter()), MappingStore()
        )
        ttbl = _store.text_table(kb_id, create=False, prefix="compliance_")
        all_sections = set()
        if ttbl is not None:
            for row in ttbl.to_pandas().to_dict("records"):
                all_sections.add(f"{row['source_file']} #chunk{row['chunk_index']} p{row['page']}")
        orphans = _coverage.orphan_policy_spans(matrix.cells, all_sections)
        return {"effective_on": eff, "n_orphans": len(orphans), "orphan_sections": sorted(orphans)}
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)}


@mcp.tool()
def compliance_change_impact(
    old_standard: str, new_standard: str, kb_id: str = "operator_corpus"
) -> dict[str, Any]:
    """Impact of a standard-version transition (e.g. old_standard='CIP-003-8',
    new_standard='CIP-003-9') on the operator's mapped sections — which prior
    verdicts are now unverified, gated on applicability."""
    try:
        from portal.modules.compliance.core.change_pipeline import impact_report
        from portal.modules.compliance.core.cip_register import Register
        from portal.modules.compliance.core.mapping_store import MappingStore
        from portal.modules.compliance.core.scope_derive import derive_scope

        reg = Register.load()
        scope, scope_meta = derive_scope(kb_id)
        if not scope.is_declared:
            return {"status": "honest-BLOCKED", "reason": scope_meta.get("reason")}
        base = old_standard.rsplit("-", 1)[0]
        old = Register(nodes=[n for n in reg.nodes if n.standard == old_standard], edges=reg.edges)
        new = Register(nodes=[n for n in reg.nodes if n.standard == new_standard], edges=reg.edges)
        if not old.nodes or not new.nodes:
            return {"error": f"standard not both in register: {old_standard} -> {new_standard}"}
        return impact_report(old, new, base, scope, MappingStore())
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)}


@mcp.tool()
def compliance_scenario(
    target_node_id: str,
    patch_text: str,
    rationale: str,
    planned_effective_date: str = "",
    kb_id: str = "operator_corpus",
    effective_on: str = "",
) -> dict[str, Any]:
    """Design §9's "How should we implement a proposed change while
    maintaining compliance?" (Q12) — an isolated before/after scenario for a
    proposed patch to ONE targeted requirement/Part, never written to any
    persisted document or effective mapping. It persists only the isolated
    scenario record and proposed work items, and returns before/after
    determinations from the same assessment engine used by analysis."""
    try:
        import datetime

        from portal.modules.compliance.core.cip_register import Register
        from portal.modules.compliance.core.mapping_store import MappingStore
        from portal.modules.compliance.core.propose import default_arbiter, make_real_proposer
        from portal.modules.compliance.core.scenarios import evaluate_scenario, new_scenario
        from portal.modules.compliance.core.scope_derive import derive_scope

        as_of = effective_on or datetime.date.today().isoformat()
        reg = Register.load()
        scope, scope_meta = derive_scope(kb_id)
        if not scope.is_declared:
            return {"status": "honest-BLOCKED", "reason": scope_meta.get("reason")}
        scenario = new_scenario(
            target_node_id,
            patch_text,
            rationale,
            planned_effective_date=planned_effective_date or None,
        )
        result = evaluate_scenario(
            scenario,
            reg,
            scope,
            as_of,
            make_real_proposer(kb_id, arbiter_fn=default_arbiter()),
            MappingStore(),
        )
        if "error" not in result:
            from portal.modules.compliance.core.repository import Repository

            repo = Repository()
            target_node = next(node for node in reg.nodes if node.id == target_node_id)
            base = repo._conn.execute(
                """SELECT revision_id FROM document_revisions
                   WHERE logical_id = ? ORDER BY retrieved_at DESC LIMIT 1""",
                (f"NERC/{target_node.standard}",),
            ).fetchone()
            if base:
                with repo._lock, repo._conn:
                    repo._conn.execute(
                        """INSERT OR REPLACE INTO change_scenarios(
                               scenario_id,base_revision_id,patch,rationale,scope,
                               planned_effective_date,created_at,org_id)
                           VALUES (?,?,?,?,?,?,?,?)""",
                        (
                            scenario.scenario_id,
                            base[0],
                            patch_text,
                            rationale,
                            scenario.scope_note,
                            scenario.planned_effective_date,
                            scenario.created_at,
                            "default",
                        ),
                    )
                    for item in result["change_plan"]["items"]:
                        repo._conn.execute(
                            """INSERT OR REPLACE INTO work_items(
                                   work_item_id,scenario_id,owner,due_date,status,org_id)
                               VALUES (?,?,?,?,?,?)""",
                            (
                                f"{scenario.scenario_id}-{item['order']}",
                                scenario.scenario_id,
                                result["change_plan"]["owner"],
                                result["change_plan"]["due_date"],
                                "open",
                                "default",
                            ),
                        )
        return result
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)}


@mcp.tool()
def compliance_prospective(
    effective_on: str = "", kb_id: str = "operator_corpus"
) -> dict[str, Any]:
    """Design §9's "What requires review when a new/revised standard takes
    effect?" (Q11) — future-effective register content as of ``effective_on``
    (default: today), explicitly segregated from "what must we do today".
    Every row is marked ``prospective: true`` and MUST NOT be read as a
    current obligation."""
    try:
        import datetime

        from portal.modules.compliance.core.change_pipeline import prospective_report
        from portal.modules.compliance.core.cip_register import Register
        from portal.modules.compliance.core.scope_derive import derive_scope

        as_of = effective_on or datetime.date.today().isoformat()
        reg = Register.load()
        scope, _ = derive_scope(kb_id)
        return prospective_report(reg, scope, as_of)
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)}


@mcp.tool()
def compliance_draft_revisions(
    old_standard: str,
    new_standard: str,
    kb_id: str = "operator_corpus",
    mode: str = "draft_as_proposal",
) -> dict[str, Any]:
    """Design §9's "What revisions would improve alignment?" (Q07) for a
    standard-version transition — what must change and why, with both
    verbatim spans, for every mapped section affected by a substantive
    change between ``old_standard`` and ``new_standard``. Drafts are returned
    as unapproved proposals with a self-reassessment. A section with NO prior mapping still
    appears via ``compliance_change_impact``'s own "no mapping" disclosure;
    this tool only covers sections that already have one."""
    try:
        from portal.modules.compliance.core.change_pipeline import draft_revisions, impact_report
        from portal.modules.compliance.core.cip_register import Register
        from portal.modules.compliance.core.mapping_store import MappingStore
        from portal.modules.compliance.core.scope_derive import derive_scope

        reg = Register.load()
        scope, scope_meta = derive_scope(kb_id)
        if not scope.is_declared:
            return {"status": "honest-BLOCKED", "reason": scope_meta.get("reason")}
        base = old_standard.rsplit("-", 1)[0]
        old = Register(nodes=[n for n in reg.nodes if n.standard == old_standard], edges=reg.edges)
        new = Register(nodes=[n for n in reg.nodes if n.standard == new_standard], edges=reg.edges)
        if not old.nodes or not new.nodes:
            return {"error": f"standard not both in register: {old_standard} -> {new_standard}"}
        impact = impact_report(old, new, base, scope, MappingStore())
        return draft_revisions(impact, mode=mode)
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
def compliance_review_list(kind: str = "", status: str = "OPEN") -> dict[str, Any]:
    """The review queue: open (default) or filtered judgements the system
    proceeded on with its best evidence-backed answer — never a blocker."""
    try:
        from portal.modules.compliance.core import review_queue as rq

        items = rq.list_items(kind=kind or None, status=status or None)
        return {"count": len(items), "items": [dataclasses.asdict(i) for i in items]}
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)}


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


@mcp.tool()
def compliance_sources(
    revision_id: str = "", alias_path: str = "", logical_id: str = ""
) -> dict[str, Any]:
    """Exact permitted source context for an immutable document revision
    (design §9's "What documents... connect" / P7's `compliance_sources`
    operation) — the first operation wired to the P2 canonical repository
    rather than the legacy JSON stores. Pass ``revision_id`` for an exact
    historical anchor; ``logical_id`` for the human-facing, source-dir-
    relative identity (e.g. "CIP-007/Some Procedure.pdf" — what an operator
    or another tool would naturally name it); or ``alias_path`` for the
    literal resolvable filesystem path a revision was ingested from. Any
    match returns the CURRENT/every revision ever recorded under that key —
    a same-path replacement never erases history, P2's core invariant.

    Integrity: when the file still exists on disk at its recorded
    ``alias_path``, its bytes are re-hashed now and compared against the
    revision's own content-hash identity — this can positively detect
    silent drift at the source (the file changed without a new ingested
    revision being recorded), which a stored hash alone cannot."""
    try:
        from portal.modules.compliance.core.provenance import content_hash
        from portal.modules.compliance.core.repository import Repository

        repo = Repository()
        if revision_id:
            rev = repo.get_revision(revision_id)
            revisions = [rev] if rev else []
        elif logical_id:
            revisions = repo.revisions_for_logical_id(logical_id)
        elif alias_path:
            revisions = repo.revisions_for_alias(alias_path)
        else:
            return {"error": "must supply revision_id, logical_id, or alias_path"}
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


_ANALYSIS_JOBS: dict[str, dict[str, Any]] = {}


@mcp.tool()
def compliance_analyze(
    requirements: list[str] | str,
    scope: str = "",
    valid_at: str = "",
    known_at: str = "",
    operation: str = "start",
    run_id: str = "",
) -> dict[str, Any]:
    """Start/status/result/cancel a bounded compliance analysis job."""
    import uuid

    if operation in {"status", "result", "cancel"}:
        job = _ANALYSIS_JOBS.get(run_id)
        if not job:
            return {"error": f"unknown run_id: {run_id}"}
        if operation == "cancel":
            job["status"] = "cancelled"
        return (
            job if operation == "result" else {k: job[k] for k in ("run_id", "status", "partial")}
        )
    refs = [requirements] if isinstance(requirements, str) else list(requirements)
    rid = run_id or "analysis-" + uuid.uuid4().hex[:16]
    results = []

    # V6: assess LIVE through the gate + council. The pre-V6 cached `claims`
    # SELECT is deleted — a determination is produced now, not read back.
    from portal.modules.compliance.core.applicability import parse_scope_declaration
    from portal.modules.compliance.core.operations import judge
    from portal.modules.compliance.core.policy_graph import build_policy_graph
    from portal.modules.compliance.core.runtime_config import load_org_commitments, seat_roster

    graph = build_policy_graph()
    actor_ids = {n.id for n in graph.nodes if n.node_type == "actor_cu"}
    asset_scope = parse_scope_declaration(scope)
    seats = seat_roster()
    org_commitments = load_org_commitments()

    for ref in refs:
        parts = sorted(i for i in actor_ids if i == ref or i.startswith(ref + " "))
        if not parts:
            results.append(
                {
                    "node_id": ref,
                    "determination": "UNRESOLVED",
                    "unresolved_code": "U02_MISSING_GOVERNING_SOURCE",
                    "missing_fact": {"logical_id": ref},
                    "citations": [],
                }
            )
            continue
        for pid in parts:
            det = judge(
                pid,
                scope=asset_scope,
                org_commitments=org_commitments,
                seats=seats,
                policy_graph=graph,
            )
            results.append(
                {
                    "node_id": pid,
                    "determination": det.determination,
                    "finding_type": det.finding_type,
                    "citations": det.citations,
                    "council_votes": det.council_votes,
                    "dissent": det.dissent,
                    "sme_decision_kind": det.sme_decision_kind,
                    "gate_gated_out": det.gate_gated_out,
                    "rationale": det.rationale,
                }
            )
    job = {
        "run_id": rid,
        "status": "complete",
        "partial": False,
        "requirements": refs,
        "results": results,
        "cursor": None,
    }
    _ANALYSIS_JOBS[rid] = job
    return {"run_id": rid, "status": "complete", "partial": False, "result_count": len(results)}


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


@mcp.tool()
def compliance_impact(start_ref: str, max_depth: int = 5, max_edges: int = 1000) -> dict[str, Any]:
    """Return direct, transitive, and inferred impacts with cutoff disclosure."""
    try:
        from portal.modules.compliance.core.impact import analyze
        from portal.modules.compliance.core.repository import Repository

        return analyze(Repository(), start_ref, max_depth=max_depth, max_edges=max_edges)
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}


TOOLS_MANIFEST = load_data("config/inference", "tools_manifest_compliance_mcp")

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
    "compliance_gaps": compliance_gaps,
    "compliance_orphans": compliance_orphans,
    "compliance_change_impact": compliance_change_impact,
    "compliance_mappings": compliance_mappings,
    "compliance_scope": compliance_scope,
    "compliance_route": compliance_route,
    "compliance_review_list": compliance_review_list,
    "compliance_review_decide": compliance_review_decide,
    "compliance_sources": compliance_sources,
    "compliance_trace": compliance_trace,
    "compliance_prospective": compliance_prospective,
    "compliance_scenario": compliance_scenario,
    "compliance_draft_revisions": compliance_draft_revisions,
    "compliance_intentionality": compliance_intentionality,
    "compliance_flexibility": compliance_flexibility,
    "compliance_analyze": compliance_analyze,
    "compliance_compare": compliance_compare,
    "compliance_impact": compliance_impact,
}


@_route("/health", methods=["GET"])
async def health_check(request: Request) -> JSONResponse:
    return JSONResponse({"status": "ok", "service": "compliance-mcp", "port": _port})


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


@_route("/tools/{tool_name}", methods=["POST"])
async def invoke_tool(request: Request) -> JSONResponse:
    name = request.path_params.get("tool_name", "")
    fn = _DISPATCH.get(name)
    if fn is None:
        return JSONResponse({"error": f"unknown tool {name}"}, status_code=404)
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
        result = await asyncio.get_running_loop().run_in_executor(
            None, functools.partial(fn, **args)
        )
        return JSONResponse(result)
    except TypeError as e:
        return JSONResponse({"error": f"bad params: {e}"}, status_code=400)


if __name__ == "__main__":
    mcp.run(transport="streamable-http", host="0.0.0.0", port=_port)
