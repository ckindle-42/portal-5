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
from portal.platform.retrieval import predicates

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


@mcp.tool()
def compliance_requirement(
    requirement: str,
    scope: str = "",
    valid_at: str = "",
    known_at: str = "",
) -> dict[str, Any]:
    """Resolve governing requirements by validity interval and return atoms.

    Phase 5: both clocks are applied. ``valid_at`` selects what governed the
    requested moment and ``known_at`` selects what this store knew then —
    a fact already true but not yet recorded (late-recorded) is reported as
    ``UNKNOWN_KNOWLEDGE`` instead of being silently included or dropped.
    Effectivity comes from the canonical store's registry-sourced
    assertions, never from filenames."""
    try:
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
        want = re.sub(r"\s+", "", requirement.strip()).upper()
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
                response.update(
                    {
                        "granularity": "exact"
                        if len(parts) == 1 and re.sub(r"\s+", "", parts[0]["id"]).upper() == want
                        else "rollup",
                        "parts": parts,
                        "readiness": {"complete": True, "missing": []},
                        "source": "NERC CIP Reliability Standards verbatim register",
                    }
                )
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


def compliance_kb_search(kb_id: str, query: str, top_k: int = 5) -> dict[str, Any]:
    """Sync dispatch wrapper over ``compliance_retrieval.search`` — raw
    kb-scoped retrieval, one corpus, no section resolution and no clocks.

    ``compliance_search`` (BILATERAL_CORPUS_V1 P5) is the tool an analyst
    should use: it spans both corpora and resolves every hit to a canonical
    section that can then be read, cited and linked."""
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
    """One representative citation for a side.

    The canonical assessment path marks its exact system-owned support and
    counterevidence slices ``operative`` — those are preferred. The legacy
    coverage path supplies retrieval spans ordered by score; the first
    locatable span is used there so existing projections are preserved.
    """
    operative = [s for s in spans if s.get("operative")]
    locatable = [s for s in spans if s.get("locatable")]
    chosen = next(iter(operative or locatable or spans), None)
    if not chosen:
        return None
    return {
        "document": chosen.get("document_id") or chosen.get("document", ""),
        "section": chosen.get("section_id") or chosen.get("ref", ""),
        "span": str(chosen.get("span") or chosen.get("text", ""))[:_SPAN_EXCERPT_CHARS],
        "slice_id": chosen.get("slice_id", ""),
    }


def _slice_index(result: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(s.get("slice_id", "")): s
        for s in (result.get("selected_source_slices") or [])
        if isinstance(s, dict)
    }


def _operative_citations(
    result: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Exact support/counterevidence slices from the canonical covered/gaps."""
    slices = _slice_index(result)
    support_ids: list[str] = []
    for item in result.get("covered", []) or []:
        support_ids += [str(x) for x in item.get("internal_slice_ids", []) if x]
        support_ids += [str(x) for x in item.get("governing_slice_ids", []) if x]
    counter_ids: list[str] = []
    for item in result.get("gaps", []) or []:
        counter_ids += [str(x) for x in item.get("internal_counterevidence_slice_ids", []) if x]
        counter_ids += [str(x) for x in item.get("governing_slice_ids", []) if x]

    def project(ids: list[str]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        seen: set[str] = set()
        for slice_id in ids:
            if not slice_id or slice_id in seen or slice_id not in slices:
                continue
            seen.add(slice_id)
            row = dict(slices[slice_id])
            row.pop("text", None)
            row["span"] = str(slices[slice_id].get("text", ""))[:_SPAN_EXCERPT_CHARS]
            row["operative"] = True
            out.append(row)
        return out

    return project(support_ids), project(counter_ids)


def _governing_excerpt(result: dict[str, Any]) -> str:
    for row in result.get("selected_source_slices", []) or []:
        if isinstance(row, dict) and str(row.get("role", "")) == "governing":
            return str(row.get("text", ""))[:_SPAN_EXCERPT_CHARS]
    return ""


def _assessment_row(result: dict[str, Any]) -> dict[str, Any]:
    """Project one persisted AssessmentResult into the ordinary gaps row.

    Preserves the legacy representative citation keys (``policy_citation`` /
    ``procedure_citation``) as projections of the canonical assessment's own
    operative slices.
    """
    support, counter = _operative_citations(result)
    documentary = str(result.get("documentary_coverage", ""))
    return {
        "requirement_id": result.get("requirement_id", ""),
        "assessment_id": result.get("assessment_id", ""),
        "run_id": result.get("run_id", ""),
        "engine": result.get("engine_version", ""),
        "coverage": result.get("coverage", ""),
        "documentary_coverage": documentary,
        "substantively_resolved": bool(result.get("substantively_resolved")),
        "applicability": result.get("applicability", ""),
        "applicability_basis": result.get("applicability_basis", ""),
        "covered": result.get("covered", []),
        "gaps": result.get("gaps", []),
        "uncertainties": result.get("uncertainties", []),
        "policy_citation": _compact_citation(support),
        "procedure_citation": _compact_citation(counter),
        "gap_quote": (_governing_excerpt(result) if documentary in ("PARTIAL", "NONE") else None),
        "note": _row_note(result),
        "retrieval_errors": (result.get("receipt") or {}).get(
            "retrieval_errors", result.get("retrieval_errors", [])
        ),
        "from_approved_mapping": False,
        "open_queue_items": [],
        "receipt": result.get("receipt", {}),
        "proposals": [],
    }


def _row_note(result: dict[str, Any]) -> str:
    if result.get("unresolved_code"):
        return f"unresolved ({result['unresolved_code']}) — {result.get('missing_fact', {})}"
    documentary = str(result.get("documentary_coverage", ""))
    if (
        documentary in ("FULL", "PARTIAL", "NONE")
        and str(result.get("coverage", "")) == "UNRESOLVED"
    ):
        return f"documentary {documentary}; public coverage UNRESOLVED — " + str(
            (result.get("missing_fact") or {}).get("missing_scope_declaration", "scope unresolved")
        )
    return f"documentary {documentary}"


def _determination_projection(result: dict[str, Any]) -> dict[str, Any]:
    """Project an AssessmentResult onto the legacy analyze determination shape."""
    documentary = str(result.get("documentary_coverage", "UNRESOLVED"))
    determination = {
        "FULL": "SUPPORTED",
        "PARTIAL": "PARTIAL",
        "NONE": "ABSENT",
        "NOT_APPLICABLE": "NOT_APPLICABLE",
        "NEEDS_REVIEW": "NEEDS_REVIEW",
        "UNRESOLVED": "UNRESOLVED",
    }.get(documentary, "UNRESOLVED")
    council = result.get("council_result") or {}
    return {
        "node_id": result.get("requirement_id", ""),
        "determination": determination,
        "documentary_coverage": documentary,
        "coverage": result.get("coverage", ""),
        "assessment_id": result.get("assessment_id", ""),
        "run_id": result.get("run_id", ""),
        "engine": result.get("engine_version", ""),
        "snapshot_fingerprint": (result.get("receipt") or {}).get("snapshot_fingerprint", ""),
        "input_fingerprint": result.get("input_fingerprint", ""),
        "applicability": result.get("applicability", ""),
        "applicability_basis": result.get("applicability_basis", ""),
        "citations": [
            str(s.get("slice_id", "")) for s in result.get("selected_source_slices", []) or []
        ],
        "covered": result.get("covered", []),
        "gaps": result.get("gaps", []),
        "uncertainties": result.get("uncertainties", []),
        "council_votes": council.get("votes", {}),
        "dissent": council.get("dissent", []),
        "gate_gated_out": (
            documentary == "NOT_APPLICABLE" or result.get("applicability") == "DOES_NOT_APPLY"
        ),
        "unresolved_code": result.get("unresolved_code", ""),
        "missing_fact": result.get("missing_fact", {}),
        "rationale": _row_note(result),
    }


def _summarize_rows(results: list[dict[str, Any]]) -> dict[str, Any]:
    by_coverage: dict[str, int] = {}
    by_documentary: dict[str, int] = {}
    resolved = 0
    for result in results:
        coverage = str(result.get("coverage", "UNRESOLVED"))
        by_coverage[coverage] = by_coverage.get(coverage, 0) + 1
        documentary = str(result.get("documentary_coverage", "UNRESOLVED"))
        by_documentary[documentary] = by_documentary.get(documentary, 0) + 1
        if result.get("substantively_resolved") and coverage not in ("UNRESOLVED", "NEEDS_REVIEW"):
            resolved += 1
    return {
        "examined": len(results),
        "substantively_resolved": resolved,
        "coverage_breakdown": by_coverage,
        "documentary_breakdown": by_documentary,
        "unresolved_items": [
            r.get("requirement_id", "")
            for r in results
            if str(r.get("coverage", "")) == "UNRESOLVED"
        ],
        "confirmed_gaps_none": [
            r.get("requirement_id", "") for r in results if str(r.get("coverage", "")) == "NONE"
        ],
        "from_approved_mappings": 0,
    }


_STANDARD_PARTS_CACHE: dict[str, list[str]] = {}


def _gap_requirements(standard: str, requirement: str) -> list[str]:
    from portal.modules.compliance.core import assessment_service
    from portal.modules.compliance.core.cip_register import Register

    reg = Register.load()
    if requirement and standard:
        return sorted(
            n.id
            for n in reg.nodes
            if n.granularity == "part" and n.standard.startswith(standard) and requirement in n.id
        )
    if requirement:
        return assessment_service.part_ids(requirement)
    if standard:
        return sorted(
            n.id for n in reg.nodes if n.granularity == "part" and n.standard.startswith(standard)
        )
    from portal.modules.compliance.core.engine import effective_parts

    return sorted(n.id for n in effective_parts(reg, datetime.date.today().isoformat()))


def _resolve_context_scope(kb_id: str, scope_text: str) -> tuple[Any, dict[str, Any]]:
    from portal.modules.compliance.core.applicability import parse_scope_declaration
    from portal.modules.compliance.core.scope_derive import derive_scope

    if scope_text:
        return parse_scope_declaration(scope_text), {"basis": "declared"}
    scope, meta = derive_scope(kb_id)
    return scope, meta


def _proposals_for_rows(
    rows: list[dict[str, Any]],
    *,
    scope: Any,
    seats: list[dict[str, str]],
    policy_graph: Any,
    org_commitments: list[dict[str, Any]],
) -> None:
    """Draft generation for resolved actionable gaps only.

    Every failure is recorded as a proposal status and never alters the actual
    coverage result. One attempt per row; no retry loop.
    """
    from portal.modules.compliance.core.operations import propose

    for row in rows:
        if str(row.get("coverage")) not in ("PARTIAL", "NONE"):
            continue
        if not row.get("substantively_resolved"):
            continue
        unmet = [str(g.get("kind", "")) for g in row.get("gaps", []) if g.get("kind")] or [
            "OMISSION"
        ]
        draft = _draft_text(row)
        try:
            package = propose(
                row["requirement_id"],
                unmet,
                draft,
                scope=scope,
                org_commitments=org_commitments,
                seats=seats,
                policy_graph=policy_graph,
            )
            rejudged = package.rejudged
            row["proposals"] = [
                {
                    "status": "proposed",
                    "closes_fields": list(package.closes_fields),
                    "rejudged_determination": rejudged.determination if rejudged else "",
                    "weakens": list(package.weakens),
                }
            ]
        except Exception as exc:  # noqa: BLE001 - a failed draft never changes coverage
            row["proposals"] = [{"status": "FAILED_VALIDATION", "error": str(exc)}]


def _draft_text(row: dict[str, Any]) -> str:
    gaps = row.get("gaps") or []
    missing = "; ".join(
        str(g.get("missing_commitment", "")) for g in gaps if g.get("missing_commitment")
    )
    return (
        "The Responsible Entity shall "
        + (missing or "implement the missing commitment")
        + f" (addressing {row.get('requirement_id', '')})."
    )


@mcp.tool()
def compliance_gaps(
    standard: str = "",
    requirement: str = "",
    effective_on: str = "",
    kb_id: str = "operator_corpus",
    max_rows: int = 25,
    verbose: bool = False,
    operation: str = "start",
    run_id: str = "",
    scope: str = "",
    conditional_scope: bool = False,
    known_at: str = "",
    top_k: int = 15,
    sync: bool = False,
    generate_drafts: bool = True,
) -> dict[str, Any]:
    """Coverage by Part through the one authoritative assessment service.

    ``operation`` is ``start`` (default) | ``status`` | ``result`` | ``cancel``
    (or ``sync`` for the controlled library path). ``start`` returns a run id
    immediately and no speculative coverage rows; ``result`` returns the
    persisted per-Part assessments once the worker has finished. ``max_rows``
    caps returned rows and draft generation, never the assessed summary. Draft
    generation runs only for resolved actionable gaps; a proposal failure is
    reported as a proposal status and never changes the coverage result.
    """
    try:
        from portal.modules.compliance.core import assessment_runs
        from portal.modules.compliance.core import review_queue as rq

        eff = effective_on or datetime.date.today().isoformat()
        if operation in ("status", "result", "cancel") and run_id:
            if operation == "status":
                return assessment_runs.run_status(run_id)
            if operation == "cancel":
                return assessment_runs.cancel_run(run_id)
            payload = assessment_runs.run_result(run_id)
            if "error" in payload:
                return payload
            original = payload.get("request") or {}
            return _gaps_payload(
                payload["results"],
                str(original.get("effective_on") or eff),
                str(original.get("kb_id") or kb_id),
                max_rows,
                verbose,
                scope_text=str(original.get("scope_text") or scope),
                payload=payload,
                generate_drafts=generate_drafts,
            )

        if not (sync or operation == "sync"):
            requirements = _gap_requirements(standard, requirement)
            if not requirements:
                return {
                    "status": "honest-BLOCKED",
                    "reason": "no register Parts match the requested standard/requirement",
                }
            scope_obj, scope_meta = _resolve_context_scope(kb_id, scope)
            if not scope_obj.is_declared and not conditional_scope:
                return {
                    "status": "honest-BLOCKED",
                    "reason": scope_meta.get("reason", "asset scope undeclared"),
                    "scope": scope_meta,
                }
            started = assessment_runs.start_run(
                {
                    "requirements": requirements,
                    "kb_id": kb_id,
                    "scope_text": scope,
                    "effective_on": eff,
                    "known_at": known_at,
                    "conditional_scope": conditional_scope,
                    "top_k": top_k,
                }
            )
            status = assessment_runs.run_status(started)
            return {
                "run_id": started,
                "status": status.get("status", "QUEUED"),
                "engine": assessment_runs.ENGINE_VERSION,
                "requirements": requirements,
                "n_parts": len(requirements),
                "scope": scope_meta,
                "note": "call operation=result with this run_id once status is COMPLETE",
            }

        # ── synchronous controlled path ─────────────────────────────────────
        scope_obj, scope_meta = _resolve_context_scope(kb_id, scope)
        if not scope_obj.is_declared and not conditional_scope:
            return {
                "status": "honest-BLOCKED",
                "reason": scope_meta.get("reason", "asset scope undeclared"),
                "scope": scope_meta,
            }
        requirements = _gap_requirements(standard, requirement)
        results = assessment_runs.assess_requirements_now(
            requirements,
            kb_id=kb_id,
            scope=scope_obj,
            scope_text=scope,
            effective_on=eff,
            known_at=known_at,
            conditional_scope=conditional_scope,
            top_k=top_k,
            repository=None,
        )
        persisted = [
            {
                "assessment_id": r.assessment_id,
                "run_id": r.run_id,
                "requirement_id": r.requirement_id,
                "coverage": r.coverage,
                "documentary_coverage": r.documentary_coverage,
                "substantively_resolved": r.substantively_resolved,
                "applicability": r.applicability,
                "applicability_basis": r.applicability_basis,
                "engine_version": r.engine_version,
                "covered": [dataclasses.asdict(c) for c in r.covered],
                "gaps": [dataclasses.asdict(g) for g in r.gaps],
                "uncertainties": [dataclasses.asdict(u) for u in r.uncertainties],
                "selected_source_slices": list(r.selected_source_slices),
                "receipt": dict(r.receipt),
                "unresolved_code": r.unresolved_code,
                "missing_fact": dict(r.missing_fact),
            }
            for r in results
        ]
        return _gaps_payload(
            persisted,
            eff,
            kb_id,
            max_rows,
            verbose,
            scope_text=scope,
            generate_drafts=generate_drafts,
            open_tiers={i.subject_id: i.id for i in rq.open_items(kind="document_tier")},
        )
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)}


def _gaps_payload(
    results: list[dict[str, Any]],
    effective_on: str,
    kb_id: str,
    max_rows: int,
    verbose: bool,
    *,
    scope_text: str = "",
    payload: dict[str, Any] | None = None,
    generate_drafts: bool = True,
    open_tiers: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Rows + summary for the async result and sync paths (no assessment rerun)."""
    from portal.modules.compliance.core import review_queue as rq

    scope_obj, scope_meta = _resolve_context_scope(kb_id, scope_text)
    matching = list(results)
    if verbose:
        rows = []
        for result in matching[:max_rows]:
            row = dict(result)
            row.setdefault(
                "retrieval_errors",
                (row.get("receipt") or {}).get("retrieval_errors", []),
            )
            rows.append(row)
    else:
        open_tiers = (
            open_tiers
            if open_tiers is not None
            else {i.subject_id: i.id for i in rq.open_items(kind="document_tier")}
        )
        rows = []
        for result in matching[:max_rows]:
            row = _assessment_row(result)
            support = result.get("selected_source_slices", []) or []
            resting_on = sorted(
                {
                    open_tiers[s["document_id"]]
                    for s in support
                    if s.get("document_id") in open_tiers
                }
                | {s["queue_item_id"] for s in support if s.get("queue_item_id")}
            )
            row["open_queue_items"] = resting_on
            rows.append(row)
    if generate_drafts and not verbose:
        from portal.modules.compliance.core.cip_register import Register
        from portal.modules.compliance.core.policy_graph import build_policy_graph
        from portal.modules.compliance.core.runtime_config import seat_roster

        _proposals_for_rows(
            rows,
            scope=scope_obj,
            seats=seat_roster(),
            policy_graph=build_policy_graph(Register.load()),
            org_commitments=[],
        )
    out: dict[str, Any] = {
        "effective_on": effective_on,
        "engine": (payload or {}).get("engine", "compliance-reading/1"),
        "scope": {
            "impact_present": sorted(scope_obj.impact_present),
            "associated_present": sorted(scope_obj.associated_present),
            **scope_meta,
        },
        "summary": _summarize_rows(matching),
        "n_matching": len(matching),
        "n_rows_returned": len(rows),
        "truncated": len(matching) > max_rows,
        "rows": rows,
    }
    if payload is not None:
        out["run_id"] = payload.get("run_id", "")
        out["status"] = payload.get("status", "")
        out["assessment_ids"] = payload.get("assessment_ids", [])
        out["progress"] = payload.get("progress", {})
    return out


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
    scope: str = "",
    known_at: str = "",
    conditional_scope: bool = False,
    edit_operation: str = "ADD",
    target_document: str = "",
    target_section: str = "",
    chunk_id: str = "",
    char_start: int = 0,
    char_end: int = 0,
    expected_old_hash: str = "",
    expected_old_text: str = "",
) -> dict[str, Any]:
    """Design §9 Q12 — a before/after scenario for ONE targeted Part.

    The proposed patch is an exact :class:`ScenarioOverlay` over the pinned base
    snapshot and is re-judged through the same authoritative assessment service
    (and therefore the same engine/snapshot fingerprint) as analysis; nothing is
    written to an effective document or mapping. ``REPLACE`` requires an exact
    target (``chunk_id``/range + ``expected_old_hash``); a bare patch defaults to
    a labelled ``ADD`` and never silently replaces existing text.
    """
    try:
        from portal.modules.compliance.core import assessment_runs
        from portal.modules.compliance.core.assessment import assess_part
        from portal.modules.compliance.core.assessment_source import (
            build_corpus_snapshot,
            materialize_overlay,
        )
        from portal.modules.compliance.core.determination import ScenarioEdit, ScenarioOverlay
        from portal.modules.compliance.core.runtime_config import build_assessment_context

        as_of = effective_on or datetime.date.today().isoformat()
        scope_obj, scope_meta = _resolve_context_scope(kb_id, scope)
        if not scope_obj.is_declared and not conditional_scope:
            return {"status": "honest-BLOCKED", "reason": scope_meta.get("reason")}
        base_snapshot = build_corpus_snapshot(kb_id)
        requests = assessment_runs.build_requests_for(
            target_node_id,
            kb_id=kb_id,
            scope=scope_obj,
            effective_on=as_of,
            known_at=known_at,
            conditional_scope=conditional_scope,
            snapshot=base_snapshot,
        )
        if not requests:
            return {"error": f"target_node_id not found in register: {target_node_id}"}
        base = requests[0]
        op = edit_operation.upper()
        if op not in ("REPLACE", "ADD"):
            op = "ADD"
        bared = op == "REPLACE" and not (chunk_id and expected_old_hash)
        edit = ScenarioEdit(
            operation="ADD" if bared else op,
            target_document=target_document or target_node_id,
            target_section=target_section,
            chunk_id=chunk_id,
            char_start=char_start,
            char_end=char_end,
            expected_old_hash=expected_old_hash,
            expected_old_text=expected_old_text,
            new_text=patch_text,
            label="legacy-add" if bared else "",
        )
        overlay = ScenarioOverlay(base_snapshot_fingerprint=base_snapshot.fingerprint, edits=[edit])
        virtual = materialize_overlay(base, overlay)
        context = build_assessment_context(kb_id, scope_obj, as_of, known_at, None, arbiter_fn=None)
        before = assess_part(base, context)
        after = assess_part(virtual, context)
        return {
            "target_node_id": target_node_id,
            "rationale": rationale,
            "planned_effective_date": planned_effective_date or None,
            "exact_overlay_target": {
                "operation": edit.operation,
                "target_document": edit.target_document,
                "chunk_id": edit.chunk_id,
                "char_start": edit.char_start,
                "char_end": edit.char_end,
                "expected_old_hash": edit.expected_old_hash,
                "label": edit.label,
            },
            "before": _scenario_projection(before),
            "after": _scenario_projection(after),
            "determination_changed": before.documentary_coverage != after.documentary_coverage,
            "weakening": before.documentary_coverage in ("FULL", "PARTIAL")
            and after.documentary_coverage not in ("FULL", "PARTIAL"),
            "affected_parts": virtual.affected_parts,
            "engine": before.engine_version,
            "before_snapshot_fingerprint": base_snapshot.fingerprint,
            "after_snapshot_fingerprint": (
                virtual.snapshot.fingerprint if virtual.snapshot else ""
            ),
            "note": (
                "overlay re-judgment through the shared assessment service; "
                "effective documents and mappings are unchanged"
            ),
        }
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)}


def _scenario_projection(result: Any) -> dict[str, Any]:
    return {
        "requirement_id": result.requirement_id,
        "assessment_id": result.assessment_id,
        "run_id": result.run_id,
        "engine": result.engine_version,
        "documentary_coverage": result.documentary_coverage,
        "coverage": result.coverage,
        "substantively_resolved": result.substantively_resolved,
        "applicability": result.applicability,
        "covered": [dataclasses.asdict(c) for c in result.covered],
        "gaps": [dataclasses.asdict(g) for g in result.gaps],
        "uncertainties": [dataclasses.asdict(u) for u in result.uncertainties],
        "unresolved_code": result.unresolved_code,
    }


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
    KB/snapshot context as ``compliance_analyze`` — a draft that merely quotes
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
            items = rq.sme_packet() if view == "packet" else rq.triage_items()
            return {
                "count": len(items),
                "view": view,
                "items": [dataclasses.asdict(i) for i in items],
            }
        items = rq.list_items(kind=kind or None, status=status or None)
        return {"count": len(items), "view": "all", "items": [dataclasses.asdict(i) for i in items]}
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
    revision_id: str = "",
    alias_path: str = "",
    logical_id: str = "",
    include_sections: bool = False,
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
            if include_sections:
                # P4 source functions: the classified section tree (role per
                # section) — what makes a copied traceability row inspectable
                # as non-operative through the route.
                entry["sections"] = repo.sections_with_role(rev.revision_id)
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
def compliance_analyze(
    requirements: list[str] | str,
    scope: str = "",
    valid_at: str = "",
    known_at: str = "",
    operation: str = "start",
    run_id: str = "",
    kb_id: str = "operator_corpus",
    conditional_scope: bool = False,
    effective_on: str = "",
    sync: bool = False,
    analysis_plan: str = "",
    scenario_part_id: str = "",
    scenario_edits: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Start/status/result/cancel a bounded compliance analysis run.

    Uses the same default KB/snapshot/context service as ``compliance_gaps``
    (never the private org graph). Responses identify the engine, the assessment
    IDs and the run; the in-memory job dictionary is gone.

    ``analysis_plan="seven_question_cip007_r2"`` executes the compound
    CIP-007 R2 arm over ONE shared context through the real primitives:
    duties, implementing clauses, alignment, gaps, evidence connections, the
    semantic 6->7.1 temporal diff, and (when ``scenario_edits`` is supplied
    with ``scenario_part_id``) an isolated proposed-change reassessment.
    Sync only.
    """
    try:
        from portal.modules.compliance.core import assessment_runs, assessment_service

        if operation in ("status", "result", "cancel") and run_id:
            if operation == "status":
                return assessment_runs.run_status(run_id)
            if operation == "cancel":
                return assessment_runs.cancel_run(run_id)
            payload = assessment_runs.run_result(run_id)
            if "error" in payload:
                return payload
            payload["results"] = [_determination_projection(r) for r in payload.get("results", [])]
            payload["result_count"] = len(payload["results"])
            return payload

        refs = [requirements] if isinstance(requirements, str) else list(requirements)
        refs = [str(r).strip() for r in refs if str(r).strip()]
        if not refs:
            return {"error": "requirements must be a non-empty string or list"}
        parts: list[str] = []
        for ref in refs:
            found = assessment_service.part_ids(ref)
            parts.extend(found or [ref])

        eff = effective_on or valid_at or datetime.date.today().isoformat()
        if analysis_plan:
            if analysis_plan != "seven_question_cip007_r2":
                return {"error": f"unknown analysis_plan {analysis_plan!r}"}
            from portal.modules.compliance.core.slice_executor import run_seven_question

            return run_seven_question(
                refs[0] if refs else "CIP-007-6 R2",
                valid_at=eff,
                known_at=known_at,
                kb_id=kb_id,
                scope_text=scope,
                scenario_part_id=scenario_part_id,
                scenario_edits=scenario_edits,
            )
        if sync or operation == "sync":
            results = assessment_runs.assess_requirements_now(
                parts,
                kb_id=kb_id,
                scope_text=scope,
                effective_on=eff,
                known_at=known_at,
                conditional_scope=conditional_scope,
                repository=None,
            )
            projected = [_determination_projection(dataclasses.asdict(r)) for r in results]
            return {
                "run_id": "",
                "status": "COMPLETE",
                "engine": assessment_runs.ENGINE_VERSION,
                "result_count": len(projected),
                "results": projected,
            }

        started = assessment_runs.start_run(
            {
                "requirements": parts,
                "kb_id": kb_id,
                "scope_text": scope,
                "effective_on": eff,
                "known_at": known_at,
                "conditional_scope": conditional_scope,
            }
        )
        status = assessment_runs.run_status(started)
        return {
            "run_id": started,
            "status": status.get("status", "QUEUED"),
            "engine": assessment_runs.ENGINE_VERSION,
            "n_parts": len(parts),
            "result_count": 0,
            "note": "call operation=result with this run_id once status is COMPLETE",
        }
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


@mcp.tool()
def compliance_impact(start_ref: str, max_depth: int = 5, max_edges: int = 1000) -> dict[str, Any]:
    """Return direct, transitive, and inferred impacts with cutoff disclosure."""
    try:
        from portal.modules.compliance.core.impact import analyze
        from portal.modules.compliance.core.repository import Repository

        return analyze(Repository(), start_ref, max_depth=max_depth, max_edges=max_edges)
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}


@mcp.tool()
def compliance_bundle(requirement_id: str) -> dict[str, Any]:
    """Resolve the complete governing bundle for one requirement Part through
    the deployed route (P7 routed observation 5/6): verbatim Part text, lead-in,
    Measures, Technical Basis spans, applicable systems, definitions
    disposition, source revision id, component readiness, and the bundle
    fingerprint. No model calls — this is the deterministic governing side a
    reader would receive."""
    try:
        from portal.modules.compliance.core.assessment_source import resolve_governing_bundle

        bundle = resolve_governing_bundle(requirement_id)
        return {
            "requirement_id": requirement_id,
            "found": True,
            "part_text": bundle.part_text,
            "lead_in": bundle.lead_in,
            "measures": bundle.measures,
            "technical_basis": bundle.technical_basis,
            "applicable_systems": bundle.applicable_systems,
            "revision_id": bundle.revision_id,
            "definitions_disposition": bundle.definitions_disposition,
            "readiness": bundle.readiness,
            "fingerprint": getattr(bundle, "fingerprint", ""),
            "n_source_slices": len(bundle.source_slices),
            "source_slices": [
                {
                    "slice_id": s.slice_id,
                    "role": s.role,
                    "ref": s.ref,
                    "document_id": s.document_id,
                    "revision_hash": s.revision_hash,
                }
                for s in bundle.source_slices
            ],
        }
    except Exception as exc:  # noqa: BLE001
        return {"requirement_id": requirement_id, "found": False, "error": str(exc)}


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


def _clip(text: str, max_chars: int) -> tuple[str, dict[str, Any]]:
    """Text up to ``max_chars``, and the truncation note when there was one.

    A caller that asks for less than the whole thing is told exactly how much
    it did not get. Silent truncation is how a reader comes to believe it has
    seen a requirement it has only seen the first 180 characters of.
    """
    body = str(text or "")
    if max_chars <= 0 or len(body) <= max_chars:
        return body, {}
    return body[:max_chars], {
        "truncated": True,
        "returned_chars": max_chars,
        "total_chars": len(body),
        "omitted_chars": len(body) - max_chars,
    }


def _provenance(entry: dict[str, Any]) -> dict[str, Any]:
    """Everything needed to cite one unit, from either jurisdiction."""
    return {
        "section_id": entry.get("section_id", ""),
        "document": entry.get("document_title") or entry.get("logical_id", ""),
        "logical_id": entry.get("logical_id", ""),
        "jurisdiction": entry.get("jurisdiction", ""),
        "source_kind": entry.get("source_kind", ""),
        "authority_tier": entry.get("authority_tier", ""),  # "" == untiered, visibly
        "document_number": entry.get("document_number", ""),
        "version": entry.get("version", ""),
        "revision_id": entry.get("revision_id", ""),
        "section_path": entry.get("path", ""),
        "heading_lineage": entry.get("headings", ""),
        "title": entry.get("title", ""),
        "unit_kind": entry.get("unit_kind", ""),
        "page": entry.get("page_start"),
        "effective_date": entry.get("effective_date"),
        "approved_date": entry.get("approved_date"),
        "inactive_date": entry.get("inactive_date"),
        "lifecycle_status": entry.get("lifecycle_status", ""),
    }


def _within_clocks(entry: dict[str, Any], valid_at: str, known_at: str) -> tuple[bool, str]:
    """Both clocks over one unit, with the reason when one excludes it.

    ``valid_at`` is what applied in the world; ``known_at`` is what this store
    believed then. A unit whose revision was only recorded later is excluded as
    UNKNOWN_KNOWLEDGE rather than served — the late-recorded shape. Material
    outside either window is excluded or returned explicitly labelled, never
    silently mixed in.
    """
    effective = str(entry.get("effective_date") or "")
    inactive = str(entry.get("inactive_date") or "")
    if valid_at:
        if effective and effective > valid_at:
            return False, f"not effective at {valid_at} (effective {effective})"
        if inactive and inactive <= valid_at:
            return False, f"retired at {valid_at} (inactive from {inactive})"
    if known_at:
        recorded_from = str(entry.get("recorded_from") or "")[:10]
        recorded_to = entry.get("recorded_to")
        if recorded_from and recorded_from > known_at:
            return False, (
                f"UNKNOWN_KNOWLEDGE: the store recorded this revision on {recorded_from}, "
                f"after the requested known_at {known_at}"
            )
        if recorded_to and str(recorded_to)[:10] <= known_at:
            return False, (
                f"superseded in the store by {str(recorded_to)[:10]}, at or before the "
                f"requested known_at {known_at}"
            )
    return True, ""


def _addressed_hits(repo: Any, query: str, max_chars: int) -> list[dict[str, Any]]:
    """An exact regulatory address, resolved directly.

    A requirements-table row's verbatim text is ``2.2 | High Impact …`` and
    never contains the string ``CIP-007-6 R2 Part 2.2``, so matching the full
    address lexically is luck. The addressed units lead the results, labelled
    as addressed, with the Part's own row first.
    """
    from portal.modules.compliance.core import reading_assembly, section_index

    if reading_assembly.parse_ref(query) is None:
        return []
    out: list[dict[str, Any]] = []
    for section_id, entry in _resolve_by_address(repo, query).items():
        text, note = _clip(entry.get("text", ""), max_chars)
        out.append(
            {
                **_provenance(entry),
                "section_id": section_id,
                "kb_id": section_index.CORPUS_FOR_JURISDICTION.get(
                    str(entry.get("jurisdiction", "")), ""
                ),
                "match": "address",
                "score": None,
                "text": text,
                **note,
            }
        )
    order = {"table_row": 0, "prose": 1, "list_item": 2, "table": 3}
    out.sort(key=lambda h: (order.get(str(h.get("unit_kind")), 4), h.get("page") or 0))
    return out


def _contains_group(column: str, value: str) -> list[Any]:
    """Case-variant substring match as an OR-group of LIKEs.

    The pre-pushdown filter compared ``value.lower() in stored.lower()`` — a
    case-insensitive substring. DataFusion's ``LIKE`` is case-sensitive, so the
    group tries the value in its given, lower and upper spellings; a caller
    that passes what the store spells differently still matches. The values
    stay quoted literals inside the group (``predicates.build`` escapes them),
    so a quote or a clause fragment in a ``standard`` argument remains data.
    """
    variants = list(dict.fromkeys([value, value.lower(), value.upper()]))
    return [(column, "LIKE", f"%{v}%") for v in variants]


def _search_predicate(*, standard: str, layer: str, valid_at: str, known_at: str) -> str:
    """The pushdown predicate for ``compliance_search`` (SUBSTRATE_PROPERTIES_V1 P3).

    Property 1: the clocks filter BEFORE ranking. Written against the P1
    projection columns and their ``""`` open-bound convention:

    * valid-time at ``valid_at``: ``(effective_from = '' OR effective_from <= V)
      AND (effective_to = '' OR effective_to > V)``
    * transaction-time at ``known_at``: ``(recorded_from = '' OR recorded_from
      <= K) AND (recorded_to = '' OR recorded_to > K)``
    * neither given: ``is_superseded = 0`` — a search with no clock asks about
      what governs NOW, and superseded revisions must not spend top-k slots by
      default. A caller who wants history says so.
    """
    from portal.modules.compliance.core.section_index import _date_of

    v, k = _date_of(valid_at), _date_of(known_at)
    entries: list[Any] = []
    if standard:
        entries.append(_contains_group("logical_id", standard))
    if layer:
        entries.append(_contains_group("source_kind", layer))
    if v:
        entries.append([("effective_from", "=", ""), ("effective_from", "<=", v)])
        entries.append([("effective_to", "=", ""), ("effective_to", ">", v)])
    if k:
        entries.append([("recorded_from", "=", ""), ("recorded_from", "<=", k)])
        entries.append([("recorded_to", "=", ""), ("recorded_to", ">", k)])
    if not v and not k:
        entries.append(("is_superseded", "=", 0))
    return predicates.build(entries)


def _filter_notes(valid_at: str, known_at: str) -> list[str]:
    """What the pushed-down filter excluded, said in the payload.

    A pushdown filter cannot enumerate what it filtered out — the rows never
    come back. The exclusion CLASSES are still stated, in the same vocabulary
    the post-filter used, so a short result list is explainable instead of
    mysterious (UNKNOWN_KNOWLEDGE is the late-recorded shape's name and stays).
    """
    notes: list[str] = []
    if valid_at:
        notes.append(
            f"revisions not in force at {valid_at} were excluded below ranking "
            "(not effective yet, or inactive by then)"
        )
    if known_at:
        notes.append(
            f"UNKNOWN_KNOWLEDGE: revisions first recorded after {known_at} were excluded "
            "below ranking — the store did not know them then"
        )
    if not valid_at and not known_at:
        notes.append(
            "superseded revisions were excluded by default (is_superseded = 0); "
            "pass valid_at or known_at to query history"
        )
    return notes


def _clock_addressed(
    addressed: list[dict[str, Any]], valid_at: str, known_at: str
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Clock-check the addressed hits, keeping the per-hit reasons.

    An addressed hit is resolved directly from the store, past the search
    arms, so the clocks must be applied to it here — with the reason string
    the pushdown path cannot carry. UNKNOWN_KNOWLEDGE survives verbatim in
    ``excluded`` through this function.
    """
    if not (valid_at or known_at):
        return addressed, []
    kept: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    for a in addressed:
        ok, why = _within_clocks(a, valid_at, known_at)
        if ok:
            kept.append(a)
        else:
            excluded.append({"section_id": a.get("section_id"), "why": why})
    return kept, excluded


@mcp.tool()
def compliance_search(
    query: str,
    jurisdiction: str = "",
    standard: str = "",
    layer: str = "",
    valid_at: str = "",
    known_at: str = "",
    top_k: int = 10,
    max_chars: int = 4000,
) -> dict[str, Any]:
    """Ranked sections across BOTH corpora — regulatory and operator together.

    Every hit's ``section_id`` resolves to a canonical ``source_sections`` row
    (BILATERAL_CORPUS_V1 P4), so a result can be read, cited, linked and
    followed. Text is verbatim up to ``max_chars`` with truncation stated.
    ``jurisdiction`` is ``US`` / ``internal`` / ``operator_note``; ``standard``
    and ``layer`` filter by document; both clocks are honoured.

    SUBSTRATE_PROPERTIES_V1 P3 — property 1: every filter is pushed DOWN as a
    ``.where()`` predicate and applied BEFORE ranking, so a filter can target
    the search rather than shrink its aftermath. ``filter_applied`` carries the
    clause that ran and ``filter_notes`` the exclusion classes; ``excluded`` no
    longer lists sieve rejects (there is no sieve) — it lists hits that do not
    resolve in the canonical store, which is an integrity signal.
    """
    from portal.modules.compliance.core import section_index
    from portal.modules.compliance.tools.compliance_retrieval import search as _kb_search

    repo = _repo()
    try:
        # An exact address is an ADDRESS, not a search. Resolving it directly
        # beats hoping the sparse arm ranks it first: a requirements-table row's
        # verbatim text is "2.2 | High Impact ... " and never contains the
        # string "CIP-007-6 R2 Part 2.2", so lexical matching on the full
        # address is luck. Addressed hits lead, labelled as addressed.
        addressed = _addressed_hits(repo, query, max_chars)
        addressed, addressed_excluded = _clock_addressed(addressed, valid_at, known_at)

        where = _search_predicate(
            standard=standard, layer=layer, valid_at=valid_at, known_at=known_at
        )

        corpora = (
            [section_index.CORPUS_FOR_JURISDICTION[jurisdiction]]
            if jurisdiction in section_index.CORPUS_FOR_JURISDICTION
            else list(dict.fromkeys(section_index.CORPUS_FOR_JURISDICTION.values()))
        )
        hits: list[dict[str, Any]] = []
        searched, unavailable = [], []
        filter_report: dict[str, Any] = {}
        for kb_id in corpora:
            try:
                body = asyncio.run(_kb_search(kb_id, query, max(top_k, 3), where=where))
            except Exception as exc:  # noqa: BLE001 - an absent corpus is reported
                unavailable.append({"kb_id": kb_id, "detail": str(exc)})
                continue
            searched.append(kb_id)
            if body.get("filter_report"):
                filter_report[kb_id] = body["filter_report"]
            for row in body.get("results", []):
                row["kb_id"] = kb_id
                hits.append(row)
        hits.sort(key=lambda r: -float(r.get("fused_score", 0) or 0))

        resolved = section_index.resolve_sections(repo, [str(h.get("chunk_id", "")) for h in hits])
        out: list[dict[str, Any]] = []
        excluded: list[dict[str, Any]] = []
        addressed_ids = {a["section_id"] for a in addressed}
        for hit in hits:
            section_id = section_index.parent_section_id(str(hit.get("chunk_id", "")))
            entry = resolved.get(section_id)
            if entry is None:
                excluded.append(
                    {
                        "chunk_id": hit.get("chunk_id"),
                        "why": "does not resolve in the canonical store",
                    }
                )
                continue
            text, note = _clip(entry.get("text", ""), max_chars)
            if section_id in addressed_ids:
                continue
            out.append(
                {
                    **_provenance(entry),
                    "kb_id": hit.get("kb_id"),
                    "match": "retrieval",
                    "score": hit.get("fused_score"),
                    "text": text,
                    **note,
                }
            )
            if len(out) + len(addressed) >= top_k:
                break
        out = addressed + out
        return {
            "query": query,
            "addressed": len(addressed),
            "corpora_searched": searched,
            "corpora_unavailable": unavailable,
            "valid_at": valid_at or "latest effective",
            "known_at": known_at or "latest recorded knowledge",
            "filter_applied": where,
            "filter_notes": _filter_notes(valid_at, known_at),
            "filter_report": filter_report,
            "excluded_meaning": (
                "hits that do not resolve to a canonical source_sections row — an "
                "integrity signal, not a filter rejection (filters run below ranking)"
            ),
            "num_results": len(out),
            "results": out,
            "excluded": addressed_excluded + excluded,
        }
    finally:
        repo.close()


@mcp.tool()
def compliance_read(ref: str, neighbors: bool = False, max_chars: int = 20000) -> dict[str, Any]:
    """Verbatim text of any addressable unit, from either side.

    ``ref`` is a ``section_id``, a regulatory address (``CIP-007-6 R2 Part
    2.2``), a glossary term, or a document ``logical_id``. With ``neighbors``
    the unit's parent heading and its siblings in reading order come too.
    """
    from portal.modules.compliance.core import reading_assembly, section_index

    repo = _repo()
    try:
        resolved = section_index.resolve_sections(repo, [ref])
        if not resolved:
            resolved = _resolve_by_address(repo, ref)
        if not resolved:
            return {
                "ref": ref,
                "resolved": False,
                "detail": "no section, address, glossary term or document with that id",
            }
        units: list[dict[str, Any]] = []
        for section_id, entry in sorted(resolved.items(), key=lambda kv: kv[1].get("ordinal", 0)):
            text, note = _clip(entry.get("text", ""), max_chars)
            units.append({**_provenance(entry), "section_id": section_id, "text": text, **note})
        payload: dict[str, Any] = {"ref": ref, "resolved": True, "units": units}
        if neighbors and units:
            payload["neighbors"] = _neighbors(repo, list(resolved.values())[0], max_chars)
        parsed = reading_assembly.parse_ref(ref)
        if parsed is not None:
            payload["address"] = str(parsed)
        return payload
    finally:
        repo.close()


@mcp.tool()
def compliance_conflicts(ref: str, valid_at: str = "") -> dict[str, Any]:
    """Cross-tier contradictions touching a requirement's neighbourhood.

    Property 2 (SUBSTRATE_PROPERTIES_V1 P4): a contradiction between tiers is a
    RETRIEVABLE fact, not a verdict-engine byproduct. ``ref`` is a regulatory
    address (``CIP-007-6 R2 Part 2.2``). Each conflict carries both spans, both
    tiers, both section ids — emitted and **never reconciled**. The standard is
    compared only through its own requirement rows, so the standard quoting
    itself (Measures, Guidelines) does not fire. Documents with no recorded
    tier are listed under ``untiered_sections`` — visible, never ranked.
    """
    from portal.modules.compliance.core import reading_assembly

    repo = _repo()
    try:
        return reading_assembly.conflicts_for_requirement(repo, ref, valid_at=valid_at)
    finally:
        repo.close()


def _resolve_by_address(repo: Any, ref: str) -> dict[str, dict[str, Any]]:
    """A regulatory address, a glossary term, or a whole document."""
    from portal.modules.compliance.core import reading_assembly, section_index
    from portal.modules.compliance.core.glossary import glossary_index

    parsed = reading_assembly.parse_ref(ref)
    if parsed is not None:
        assembly = reading_assembly.assemble(repo, ref, include=["requirement"])
        ids = [
            s["section_id"] for c in assembly.get("components", []) for s in c.get("sections", [])
        ]
        if ids:
            return section_index.resolve_sections(repo, ids)
    entries = glossary_index(repo).get(ref.strip().lower())
    if entries:
        return section_index.resolve_sections(repo, [e["section_id"] for e in entries])
    ids = section_index.sections_in_scope(repo, logical_id=ref)
    return section_index.resolve_sections(repo, ids[:200]) if ids else {}


def _neighbors(repo: Any, entry: dict[str, Any], max_chars: int) -> dict[str, Any]:
    from portal.modules.compliance.core import section_index

    rows = repo._conn.execute(
        """SELECT section_id FROM source_sections
           WHERE revision_id = ? AND heading_path = ? AND char_start >= 0
           ORDER BY ordinal""",
        (entry.get("revision_id"), entry.get("heading_path", "")),
    ).fetchall()
    siblings = section_index.resolve_sections(repo, [str(r[0]) for r in rows])
    return {
        "heading_path": entry.get("heading_path", ""),
        "siblings": [
            {**_provenance(s), "text": _clip(s.get("text", ""), max_chars)[0]}
            for s in sorted(siblings.values(), key=lambda s: s.get("ordinal", 0))
        ],
    }


@mcp.tool()
def compliance_links(
    ref: str, direction: str = "both", status: str = "", derivation: str = ""
) -> dict[str, Any]:
    """Traversal over ``relationship_assertions``. Every edge is labelled with
    its status, how it was derived and its confidence — a proposal is visible
    as a proposal, never as an established fact."""
    repo = _repo()
    try:
        clauses, params = [], []
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
            where += " AND derivation = ?"
            params.append(derivation)
        rows = repo._conn.execute(
            f"""SELECT assertion_id, relation_type, src_ref, dst_ref, status, derivation,
                       confidence, coverage, rationale, valid_from, valid_to, recorded_from
                FROM relationship_assertions WHERE {where}
                ORDER BY status, confidence DESC LIMIT 500""",  # noqa: S608
            tuple(params),
        ).fetchall()
        edges = [dict(r) for r in rows]
        return {
            "ref": ref,
            "direction": direction,
            "num_edges": len(edges),
            "edges": edges,
            "note": "status 'proposed' is a candidate, not an established relationship",
        }
    finally:
        repo.close()


@mcp.tool()
def compliance_timeline(ref: str) -> dict[str, Any]:
    """Every revision of either side, with its dates — plus the semantic delta
    between consecutive regulatory revisions."""
    from portal.modules.compliance.core import reading_assembly
    from portal.modules.compliance.core.revision_compare import semantic_diff

    repo = _repo()
    try:
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
        revisions = [dict(r) for r in rows]
        delta: dict[str, Any] = {}
        if parsed:
            family = "-".join(parsed.standard.split("-")[:2])
            versions = sorted(
                {
                    str(r["logical_id"]).rsplit("-", 1)[-1]
                    for r in revisions
                    if str(r["source_kind"]) == "regulatory_standard"
                }
            )
            if len(versions) >= 2:
                try:
                    delta = semantic_diff(
                        repo,
                        family=family,
                        version_before=versions[0],
                        version_after=versions[-1],
                    )
                except Exception as exc:  # noqa: BLE001 - a delta is optional context
                    delta = {"error": str(exc)}
        return {"ref": ref, "revisions": revisions, "semantic_delta": delta}
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
    """
    from portal.modules.compliance.core import reading_assembly, section_index

    repo = _repo()
    try:
        target = f"{standard} {requirement}".strip() if requirement else standard
        parsed = reading_assembly.parse_ref(target) or reading_assembly.parse_ref(standard)
        if parsed is None:
            return {"error": f"{target!r} is not a regulatory address"}
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
                """SELECT dst_ref, status, derivation, confidence FROM relationship_assertions
                   WHERE src_ref = ? AND status IN ('approved','proposed')""",
                (ref,),
            ).fetchall()
            linked = section_index.resolve_sections(repo, [str(e[0]) for e in edges])
            rows.append(
                {
                    "requirement": ref,
                    "linked_sections": [
                        {
                            **_provenance(entry),
                            "status": dict(
                                zip([e[0] for e in edges], [e[1] for e in edges], strict=True)
                            ).get(sid, ""),
                        }
                        for sid, entry in linked.items()
                    ],
                    "unresolvable_links": [str(e[0]) for e in edges if str(e[0]) not in linked],
                    "has_link": bool(linked),
                }
            )
        return {
            "standard": parsed.standard,
            "requirement": parsed.requirement,
            "valid_at": valid_at or "latest effective",
            "known_at": known_at or "latest recorded knowledge",
            "sections_in_standard": len(assembly_ids),
            "requirements": rows,
            "requirements_with_no_link": [r["requirement"] for r in rows if not r["has_link"]],
            "deterministic": True,
        }
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
def compliance_notes(subject_ref: str = "", limit: int = 50) -> dict[str, Any]:
    """Operator notes about one subject, newest first, with their verbatim text."""
    from portal.modules.compliance.core.notes import notes_for

    repo = _repo()
    try:
        return {"subject_ref": subject_ref, "notes": notes_for(repo, subject_ref, limit=limit)}
    finally:
        repo.close()


@mcp.tool()
def compliance_context(
    ref: str,
    budget_tokens: int = 60000,
    include: str = "",
    profile: str = "",
    valid_at: str = "",
) -> dict[str, Any]:
    """**The reading assembly.** Everything a requirement's neighbourhood holds.

    Deterministic and gathered by document structure, never by relevance score:
    the requirement and its lead-in, every Part row with its own cells, the
    Measures, the Guidelines and Technical Basis, the Rationale, the VSL rows,
    Section 4 applicability and exemptions, Section 6 background and reading
    conventions, the resolved Glossary terms the text depends on, the
    implementation plan and technical rationale where they exist, the version
    history, and the linked internal sections in full.

    Sized to an explicit token budget, with anything omitted NAMED in the
    payload, so the reader knows what it has not seen.

    ``profile`` scopes the packet to a kind of question — ``full`` (default),
    ``intent``, ``conformance``, ``audit``, ``timeline``. Measured on
    CIP-007-6 R2 Part 2.2: full is ~29,900 tokens, ``intent`` ~6,500. Nothing
    infers the profile from the question; the caller names it, and everything a
    profile leaves out is listed in ``omitted`` so the honest answer to a
    question it cannot settle is "I would need the implementation plan for
    that".
    """
    from portal.modules.compliance.core.notes import notes_for
    from portal.modules.compliance.core.reading_assembly import assemble

    repo = _repo()
    try:
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
    finally:
        repo.close()


# ── BILATERAL_CORPUS_V1 P6: the reader, and the conversation as a corpus ────


def _reading_seat(profile: str = "") -> str:
    """The seat that reads — chosen WITH the packet, not once for all packets.

    P6.8 measured the same question against the same corpus at two packet
    sizes. On the full ~30,000-token neighbourhood, glm-4.7-flash misread the
    operator's procedure; on the focused ~6,000-token one it read it correctly,
    as did a 6.6 GB 9B model. The packet size, not the parameter count, was the
    failure — so the seat follows the packet:

    * a focused profile gets the fast seat (MoE, 244 tok/s prefill, 14-28 s);
    * the full packet gets the seat that was correct on 30k of material.

    Both are recorded in config/compliance/council.yaml with the transcripts
    that chose them. Every one of them fits alongside the running Docker stack,
    which is a hard requirement: this is a module inside the product, not a
    thing you take the product down to use.
    """
    import os

    from portal.modules.compliance.core.runtime_config import _read_council_config

    config = _read_council_config()
    key = "reading_seat" if profile and profile.lower() != "full" else "reading_seat_full_packet"
    configured = config.get(key) or config.get("reading_seat")
    if isinstance(configured, dict) and configured.get("model"):
        return str(configured["model"])
    return os.environ.get("COMPLIANCE_READING_MODEL", "glm-4.7-flash:Q4_K_M-ctx64k")


@mcp.tool()
def compliance_ask(
    question: str,
    ref: str,
    profile: str = "",
    budget_tokens: int = 60000,
    valid_at: str = "",
    thread_id: str = "",
    model: str = "",
) -> dict[str, Any]:
    """Ask a question about a requirement, with the whole neighbourhood in front
    of the reader.

    The reader receives ``compliance_context`` output — nothing filtered on its
    behalf, nothing marked ineligible to cite, and whatever the budget could not
    hold named in the payload. It answers in prose and cites section ids. Those
    ids are then resolved and reported with **what each one is**, so an argument
    resting on the standard quoting itself as the operator's control is visible
    as exactly that. Nothing here adjudicates whether the answer is right.

    The answer is retained and projected into the corpus as a ``derived``
    source: contestable, retrievable, never a fact, and outranked by any
    operator note on the same subject.
    """
    from portal.modules.compliance.core.reader import read

    repo = _repo()
    try:
        return read(
            repo,
            question,
            ref,
            model=model or _reading_seat(profile),
            budget_tokens=budget_tokens,
            profile=profile,
            valid_at=valid_at,
            thread_id=thread_id,
        )
    except Exception as exc:  # noqa: BLE001 - a transport failure is reported, not raised
        return {"error": str(exc), "question": question, "ref": ref}
    finally:
        repo.close()


@mcp.tool()
def compliance_answers(subject_ref: str = "", include_superseded: bool = True) -> dict[str, Any]:
    """Stored answers about a subject, each with its citations and its standing.

    An answer is one analyst's notes pinned to the revisions it read. It is
    marked SUPERSEDED once a revision it cited moves, and it says so when an
    operator note on the same subject outranks it.
    """
    from portal.modules.compliance.core.reader import answers_for

    repo = _repo()
    try:
        return {
            "subject_ref": subject_ref,
            "answers": answers_for(repo, subject_ref, include_superseded=include_superseded),
        }
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
            answers = run_standing_questions(repo, subject_ref, model=_reading_seat())
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
    "compliance_kb_search": compliance_kb_search,
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
    "compliance_bundle": compliance_bundle,
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
