"""Source acquisition / snapshot adapter for the reading architecture.

Workstream B of ``docs/IMPLEMENTATION_BRIEF_COMPLIANCE_READING_20260912.md``.
This is the transport layer between retrieval and the assessment service: it
pins the corpus, resolves the *complete* governing text, carries the full
retrieved candidate text plus provenance forward, and materialises exact
scenario overlays over a pinned snapshot.

Nothing here decides relevance, coverage or compliance. Retrieval query
generation, ranking/reranking, top-k and chunking are owned by ``propose`` and
are reused unchanged. The one job of this module is to stop the full text,
identifiers and provenance that retrieval already possesses from being dropped
before a reader sees them.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import replace
from pathlib import Path
from typing import Any

from portal.modules.compliance.core import propose as _propose
from portal.modules.compliance.core.applicability import (
    AssetScope,
    parse_scope_declaration,
)
from portal.modules.compliance.core.cip_register import Register, RegisterNode
from portal.modules.compliance.core.determination import (
    COMPLETENESS_STATES,
    AssessmentRequest,
    CandidateRecord,
    CandidateSet,
    CorpusSnapshot,
    GoverningBundle,
    ScenarioEdit,
    ScenarioOverlay,
    SourceSlice,
)
from portal.modules.compliance.core.regulatory_bundle import SourceBundleIncompleteError

__all__ = [
    "acquire_candidates",
    "build_assessment_request",
    "build_corpus_snapshot",
    "materialize_overlay",
    "resolve_governing_bundle",
]


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _register_node(requirement_id: str) -> RegisterNode:
    reg = Register.load()
    node = next((n for n in reg.nodes if n.id == requirement_id), None)
    if node is None:
        raise ValueError(f"governing requirement {requirement_id!r} is not in the register")
    return node


def _governing_slice(
    *,
    node_id: str,
    text: str,
    role: str,
    document_id: str,
    chunk_id: str,
    locator: str,
) -> SourceSlice:
    """A slice of a register node's stored text. ``revision_hash`` is the
    content hash of that exact text — the register carries no separate revision
    id, so the text is the revision."""
    return SourceSlice(
        slice_id=f"gov-{hashlib.sha256(f'{node_id}|{role}'.encode()).hexdigest()[:16]}",
        ref=node_id,
        document_id=document_id,
        revision_hash=_sha256(text),
        chunk_id=chunk_id,
        locator=locator,
        text=text,
        char_start=0,
        char_end=len(text),
        role=role,
    )


_bundle_cache: dict[str, Any] = {}


def _revision_bundle(source_pdf: str, expected_prefix: str) -> Any:
    """The extracted RevisionBundle for one pinned source PDF, cached by
    digest. Prefers the officially acquired bytes and falls back to the
    register's pinned public copy; both must carry the register's hash
    prefix, so a foreign revision can never be read."""
    from portal.modules.compliance.core.regulatory_bundle import (
        extract_revision_bundle,
        sha256_of,
    )

    module_dir = Path(__file__).resolve().parent.parent
    candidates = [
        module_dir / "data" / "private" / "nerc_official" / Path(source_pdf).name,
        module_dir / "data" / "cip_pdfs" / Path(source_pdf).name,
    ]
    for path in candidates:
        if not path.is_file():
            continue
        content = path.read_bytes()
        digest = sha256_of(content)
        if expected_prefix and not digest.startswith(expected_prefix):
            continue  # not the pinned revision — try the next source
        if digest not in _bundle_cache:
            _bundle_cache[digest] = extract_revision_bundle(
                content, expected_sha256=digest, source_name=Path(source_pdf).name
            )
        return _bundle_cache[digest]
    raise ValueError(f"governing source revision unavailable for {source_pdf!r}")


def _bundle_fingerprint(slices: list[SourceSlice]) -> str:
    body = [(s.ref, s.revision_hash, s.char_start, s.char_end) for s in slices]
    return hashlib.sha256(json.dumps(body, separators=(",", ":")).encode()).hexdigest()


def _bundle_components(
    node: RegisterNode, reg: Register
) -> tuple[dict[str, Any], Any, list[dict[str, str]]]:
    """P3 components from the pinned source revision: the part bundle plus
    the extracted RevisionBundle (for lead-in recovery) plus readiness
    failures. A source that cannot be read is a ``source_revision`` failure,
    never a silent empty bundle."""
    from portal.modules.compliance.core.regulatory_bundle import (
        part_bundle,
        verify_bundle_spans,
    )

    failures: list[dict[str, str]] = []
    extracted = None
    try:
        extracted = _revision_bundle(
            node.source_pdf, reg.source_pdfs.get(Path(node.source_pdf).name, "")
        )
        pb = (
            part_bundle(extracted, node.requirement, node.part)
            if node.granularity == "part"
            else _requirement_level_bundle(extracted, node)
        )
        for locator in verify_bundle_spans(extracted):
            failures.append(
                {
                    "component": "span_offsets",
                    "detail": f"span failed hash re-verification: {locator}",
                    "code": "U14_INCOMPLETE_SOURCE_BUNDLE",
                }
            )
        failures.extend(regulatory_readiness_failures(pb))
        return pb, extracted, failures
    except (ValueError, OSError) as exc:
        failures.append(
            {
                "component": "source_revision",
                "detail": str(exc),
                "code": "U14_INCOMPLETE_SOURCE_BUNDLE",
            }
        )
        return {}, None, failures


def _lead_in_node(
    node: RegisterNode, requirement_id: str, reg: Register, by_id: dict[str, Any], extracted: Any
) -> Any:
    """The verified parent R lead-in for a numbered Part. Only numbered
    requirements carry one — attachment criteria have an attachment section
    as parent, and no lead-in exists to recover, by source shape."""
    if node.granularity != "part" or not re.fullmatch(r"R\d+", node.requirement):
        return None
    base_id = requirement_id.rsplit(" Part ", 1)[0]
    lead = by_id.get(base_id) or next((n for n in reg.nodes if n.id == base_id), None)
    if lead is None and extracted is not None:
        lead_text = extracted.leadins.get(node.requirement, ("", "", ""))[0]
        if lead_text:
            lead = replace(
                node, id=base_id, part="", verbatim_text=lead_text, granularity="requirement"
            )
    return lead if lead is not None else _pdf_parent_requirement(node, reg)


def resolve_governing_bundle(requirement_id: str, *, policy_graph: Any = None) -> GoverningBundle:
    """Assemble the authoritative governing text for one Part.

    Carries the complete ``RegisterNode.verbatim_text`` — never trimmed to a
    role or a first atom — plus the verified parent R lead-in when the Part is
    a ``granularity == "part"`` node, and every ``REFERS_TO`` target's verbatim
    text. Referenced targets are bucketed by the policy graph's own typing:
    ``premise`` nodes become ``definitions``, everything else ``references``.
    A reference whose endpoint does not resolve is dropped, never fabricated.

    Foundation P3: the bundle also carries the Part's Measures (``MEASURE``
    role — evidence expectation, not an extra duty), the requirement's
    Guidelines and Technical Basis spans (``TECHNICAL_BASIS`` role — read as
    interpretive context, never binding text), the applicable-systems column,
    the recorded definitions disposition, and the component ``readiness``
    verdict over the pinned source revision.
    """
    reg = Register.load()
    node = next((n for n in reg.nodes if n.id == requirement_id), None)
    if node is None:
        raise ValueError(f"governing requirement {requirement_id!r} is not in the register")

    graph = policy_graph if policy_graph is not None else _build_policy_graph(reg)
    by_id = {n.id: n for n in graph.nodes}

    slices: list[SourceSlice] = [
        _governing_slice(
            node_id=node.id,
            text=node.verbatim_text,
            role="governing",
            document_id=node.source_pdf or node.standard,
            chunk_id=node.id,
            locator=_locator(node),
        )
    ]
    meta: list[dict[str, Any]] = [_node_meta(node, "governing")]

    # ── P3: complete-bundle components from the pinned source revision ──
    pb, extracted, failures = _bundle_components(node, reg)
    measures = list(pb.get("measures", []))
    technical_basis = [
        *pb.get("technical_basis", []),
        *pb.get("technical_basis_parts", []),
        *pb.get("technical_basis_rationale", []),
    ]
    applicable_systems = (getattr(node, "applicable_systems", "") or "") or pb.get(
        "applicable_systems", ""
    )
    document_id = node.source_pdf or node.standard
    for m in measures:
        slices.append(_context_slice(m, role="measure", document_id=document_id))
    for span in technical_basis:
        slices.append(_context_slice(span, role="technical_basis", document_id=document_id))

    lead_in = ""
    lead = _lead_in_node(node, requirement_id, reg, by_id, extracted)
    if lead is not None and lead.verbatim_text:
        lead_in = lead.verbatim_text
        slices.append(
            _governing_slice(
                node_id=lead.id,
                text=lead.verbatim_text,
                role="governing",
                document_id=getattr(lead, "source_pdf", "") or getattr(lead, "standard", ""),
                chunk_id=lead.id,
                locator=getattr(lead, "part", "") or getattr(lead, "requirement", ""),
            )
        )
        meta.append(_node_meta(lead, "lead_in"))

    definitions, references, ref_slices = _graph_references(graph, requirement_id, by_id)
    slices.extend(ref_slices)

    # P2: the external-glossary deferral, actually resolved. A standard with no
    # definitions section defers to the NERC Glossary; before this the
    # disposition was recorded and nothing ever fetched it, so every defined
    # term in the duty text resolved to nothing.
    if pb.get("definitions_disposition") == "external_glossary":
        definitions.extend(
            _glossary_definitions(
                " ".join(
                    [
                        node.verbatim_text,
                        lead_in,
                        applicable_systems,
                        *(str(m.get("text", "")) for m in measures),
                    ]
                )
            )
        )

    bundle_out = GoverningBundle(
        ref=requirement_id,
        part_text=node.verbatim_text,
        lead_in=lead_in,
        definitions=definitions,
        references=references,
        meta=meta,
        source_slices=slices,
        measures=measures,
        technical_basis=technical_basis,
        applicable_systems=applicable_systems,
        revision_id=pb.get("revision_id", ""),
        definitions_disposition=pb.get("definitions_disposition", ""),
        readiness={"ready": not failures, "failures": failures},
    )
    bundle_out.fingerprint = _bundle_fingerprint(slices)
    return bundle_out


def _glossary_definitions(text: str) -> list[dict[str, Any]]:
    """Resolved NERC Glossary terms the duty text depends on, each with its own
    provenance and effectivity. An unresolvable term is carried explicitly
    unresolved — never guessed and never silently omitted. A store without the
    Glossary registered yields an empty list rather than an error: the bundle is
    still usable, and the absence is visible in the payload."""
    from portal.modules.compliance.core.glossary import resolve_bundle_definitions
    from portal.modules.compliance.core.repository import Repository

    repo = Repository()
    try:
        resolution = resolve_bundle_definitions(repo, text)
    except Exception:  # noqa: BLE001 - an unreadable store defers, never invents
        return []
    finally:
        repo.close()
    return [
        {
            "ref": entry["term"],
            "text": entry["definition"],
            "role": "definition",
            "source": "NERC Glossary of Terms",
            "matched_as": entry.get("matched_as", ""),
            "section_id": entry["section_id"],
            "revision_id": entry["revision_id"],
            "effective_date": entry["effective_date"],
            "inactive_date": entry["inactive_date"],
            "resolved": entry["resolved"],
            "detail": entry["detail"],
        }
        for entry in resolution["terms"]
    ]


def _graph_references(
    graph: Any, requirement_id: str, by_id: dict[str, Any]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[SourceSlice]]:
    """REFERS_TO targets bucketed into definitions/references, each carried
    as a reference-role slice. Unresolved endpoints are dropped, never
    fabricated."""
    definitions: list[dict[str, Any]] = []
    references: list[dict[str, Any]] = []
    ref_slices: list[SourceSlice] = []
    for edge in graph.edges:
        if edge.get("src") != requirement_id or edge.get("rel") != "REFERS_TO":
            continue
        dst = edge.get("dst") or ""
        target = by_id.get(dst)
        if not dst or target is None:
            continue  # an unresolved endpoint is not a fabricated reference
        entry = {
            "ref": dst,
            "text": getattr(target, "verbatim_text", "") or "",
            "surface_text": edge.get("surface_text", ""),
            "char_start": edge.get("char_start"),
            "char_end": edge.get("char_end"),
            "resolution": edge.get("resolution", ""),
        }
        if getattr(target, "node_type", "") == "premise":
            definitions.append(entry)
        else:
            references.append(entry)
        ref_slices.append(
            _governing_slice(
                node_id=target.id,
                text=entry["text"],
                role="reference",
                document_id=getattr(target, "source_pdf", "") or getattr(target, "standard", ""),
                chunk_id=target.id,
                locator=getattr(target, "part", "") or getattr(target, "requirement", ""),
            )
        )
    return definitions, references, ref_slices


def _requirement_level_bundle(bundle: Any, node: RegisterNode) -> dict[str, Any]:
    """Components for a requirement-granularity node (no Parts table)."""
    from portal.modules.compliance.core.regulatory_bundle import part_bundle

    return part_bundle(bundle, node.requirement, "")


def _context_slice(record: dict[str, Any], *, role: str, document_id: str) -> SourceSlice:
    """A MEASURE / TECHNICAL_BASIS context slice. Context is carried for the
    reader but is never selectable duty evidence — build_reading_packet keeps
    these out of ``selectable_slice_ids``."""
    text = str(record.get("text", ""))
    locator = str(record.get("locator", ""))
    return SourceSlice(
        slice_id=f"ctx-{hashlib.sha256(f'{locator}|{role}|{text}'.encode()).hexdigest()[:16]}",
        ref=str(record.get("ref", "")) or locator,
        document_id=document_id,
        revision_hash=_sha256(text),
        chunk_id=locator,
        locator=locator,
        text=text,
        char_start=0,
        char_end=len(text),
        role=role,
    )


def regulatory_readiness_failures(pb: dict[str, Any]) -> list[dict[str, str]]:
    from portal.modules.compliance.core.regulatory_bundle import readiness_failures

    return readiness_failures(pb)


def _pdf_parent_requirement(node: RegisterNode, reg: Register) -> RegisterNode:
    """Recover a table's omitted R header from the register's pinned public PDF."""
    import pymupdf

    from portal.modules.compliance.core.cip_extract import _leadins

    pdf = Path(__file__).resolve().parent.parent / "data" / "cip_pdfs" / Path(node.source_pdf).name
    content = pdf.read_bytes()
    expected = reg.source_pdfs.get(pdf.name, "")
    if not expected or not hashlib.sha256(content).hexdigest().startswith(expected):
        raise ValueError(f"governing parent PDF revision mismatch: {pdf.name}")
    with pymupdf.open(stream=content, filetype="pdf") as document:  # type: ignore[no-untyped-call]
        headers = _leadins(" ".join(page.get_text() for page in document))
    if node.requirement not in headers:
        raise ValueError(f"governing parent unavailable: {node.standard} {node.requirement}")
    return replace(
        node,
        id=f"{node.standard} {node.requirement}",
        part="",
        verbatim_text=headers[node.requirement][0],
        granularity="requirement",
    )


def _build_policy_graph(reg: Register) -> Any:
    from portal.modules.compliance.core.policy_graph import build_policy_graph

    return build_policy_graph(reg)


def _locator(node: Any) -> str:
    part = getattr(node, "part", "") or ""
    req = getattr(node, "requirement", "") or ""
    return f"{req} Part {part}".strip() if part else req


def _node_meta(node: Any, role: str) -> dict[str, Any]:
    return {
        "node_id": getattr(node, "id", ""),
        "role": role,
        "standard": getattr(node, "standard", ""),
        "requirement": getattr(node, "requirement", ""),
        "part": getattr(node, "part", ""),
        "granularity": getattr(node, "granularity", ""),
        "applicable_systems": getattr(node, "applicable_systems", ""),
    }


# ── corpus snapshot ─────────────────────────────────────────────────────────


def _snapshot_fingerprint(snapshot: CorpusSnapshot) -> str:
    """sha256 of the pinned fields — never the random snapshot id, so the same
    content always fingerprints the same."""
    body = {
        "kb_id": snapshot.kb_id,
        "manifest_hash": snapshot.manifest_hash,
        "index_generation": snapshot.index_generation,
        "table_name": snapshot.table_name,
        "table_version": snapshot.table_version,
        "document_revision_hashes": dict(sorted(snapshot.document_revision_hashes.items())),
        "candidate_identities": sorted(snapshot.candidate_identities),
        "acquisition_mode": snapshot.acquisition_mode,
        "completeness": snapshot.completeness,
    }
    return hashlib.sha256(
        json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _store() -> Any:
    from portal.platform.retrieval import store as _store_mod

    return _store_mod


def _document_revision_hashes(ttbl: Any) -> dict[str, str]:
    """Per-document content hash over the stored rows, when the store exposes
    them. Missing/unreadable storage is honestly empty, never invented."""
    try:
        if hasattr(ttbl, "to_pandas"):
            rows = ttbl.to_pandas().to_dict("records")
        else:
            rows = ttbl.search().limit(1_000_000).to_list()
    except Exception:  # noqa: BLE001 — an unreadable store yields no hashes
        return {}
    grouped: dict[str, list[tuple[int, str]]] = {}
    for row in rows:
        doc = str(row.get("source_file", "") or "")
        if not doc:
            continue
        grouped.setdefault(doc, []).append(
            (int(row.get("chunk_index", 0) or 0), str(row.get("text", "") or ""))
        )
    out: dict[str, str] = {}
    for doc, rows_ in grouped.items():
        rows_.sort(key=lambda item: item[0])
        out[doc] = _sha256("\n".join(f"{idx}:{text}" for idx, text in rows_))
    return out


def build_corpus_snapshot(
    kb_id: str, *, acquisition_receipt: dict[str, Any] | None = None
) -> CorpusSnapshot:
    """Pin the retrieval store's current view for one assessment.

    ``completeness`` is ``UNKNOWN`` for ordinary top-k retrieval and only
    becomes ``COMPLETE`` with an explicit completed-boundary receipt — a search
    that ran is not a search that read the whole declared population.
    """
    receipt = acquisition_receipt or {}
    store = _store()
    table_name = store.tname(kb_id, prefix="compliance_")
    ttbl = store.text_table(kb_id, create=False, prefix="compliance_")
    table_version = int(getattr(ttbl, "version", 0) or 0) if ttbl is not None else 0
    stamp = store.read_stamp(kb_id, prefix="compliance_") or {}
    embed_model = str(stamp.get("embed_model", "") or "")
    index_generation = f"{table_name}@{table_version}" + (f":{embed_model}" if embed_model else "")
    revision_hashes = _document_revision_hashes(ttbl) if ttbl is not None else {}
    manifest_hash = (
        _sha256(json.dumps(dict(sorted(revision_hashes.items())), separators=(",", ":")))
        if revision_hashes
        else ""
    )

    mode = str(receipt.get("acquisition_mode", "RETRIEVAL") or "RETRIEVAL")
    if mode not in ("RETRIEVAL", "EXPLICIT_SET"):
        mode = "RETRIEVAL"
    boundary = receipt.get("boundary_receipt") or {}
    from portal.modules.compliance.core.boundary import verified_completeness

    completeness = "COMPLETE" if verified_completeness(boundary) else "UNKNOWN"
    if completeness not in COMPLETENESS_STATES:
        completeness = "UNKNOWN"

    candidates = receipt.get("candidate_identities") or []
    snapshot = CorpusSnapshot(
        snapshot_id="",
        kb_id=kb_id,
        manifest_hash=manifest_hash,
        index_generation=index_generation,
        table_name=table_name,
        table_version=table_version,
        document_revision_hashes=revision_hashes,
        candidate_identities=[str(c) for c in candidates],
        acquisition_mode=mode,
        completeness=completeness,
    )
    fingerprint = _snapshot_fingerprint(snapshot)
    snapshot.fingerprint = fingerprint
    snapshot.snapshot_id = f"snap-{fingerprint[:20]}"
    return snapshot


# ── candidate acquisition ───────────────────────────────────────────────────


def _slice_for_hit(hit: dict[str, Any], document_id: str, chunk_id: str, text: str) -> SourceSlice:
    ref = str(hit.get("section_id") or f"{document_id} #{chunk_id}")
    return SourceSlice(
        slice_id=f"cand-{hashlib.sha256(f'{chunk_id}|{ref}'.encode()).hexdigest()[:16]}",
        ref=ref,
        document_id=document_id,
        revision_hash=_sha256(text),
        chunk_id=chunk_id,
        locator=str(hit.get("headings") or hit.get("section_id") or ""),
        text=text,
        char_start=0,
        char_end=len(text),
        doc_char_start=hit.get("char_start"),
        doc_char_end=hit.get("char_end"),
        role="candidate",
    )


def _candidate_record(hit: dict[str, Any]) -> CandidateRecord:
    text = str(hit.get("text") or "")
    document_id = str(hit.get("document_id") or hit.get("source_file") or "")
    chunk_id = str(hit.get("chunk_id") or hit.get("section_id") or "")
    sl = _slice_for_hit(hit, document_id, chunk_id, text)
    return CandidateRecord(
        candidate_id=chunk_id or sl.slice_id,
        document_id=document_id,
        chunk_id=chunk_id,
        text=text,
        locator=sl.locator,
        layer=str(hit.get("layer") or ""),
        rerank_score=float(hit.get("rerank_score") or 0.0),
        relevant=bool(hit.get("relevant")),
        anchor_verified=bool(hit.get("anchor_verified", True)),
        revision_hash=sl.revision_hash,
        char_start=0,
        char_end=len(text),
        source_slice=sl,
    )


def _annotation(hit: dict[str, Any], record: CandidateRecord) -> dict[str, Any]:
    return {
        "candidate_id": record.candidate_id,
        "chunk_id": record.chunk_id,
        "document_id": record.document_id,
        "layer": record.layer,
        "rerank_score": record.rerank_score,
        "relevant": record.relevant,
        "locatable": bool(hit.get("locatable", False)),
        "queue_item_id": hit.get("queue_item_id", ""),
    }


def acquire_exhaustively(
    *,
    kb_id: str,
    jurisdiction: str = "internal",
    scope_sections: list[str] | None = None,
    withhold: list[str] | None = None,
) -> CandidateSet:
    """Read the WHOLE declared population, and say so (BILATERAL_CORPUS_V1 P4.6).

    Top-k retrieval can never support an absence claim: a search that ran is not
    a search that read the declared population. This path reads every section in
    the scope straight from the canonical store and emits the boundary receipt
    that says which sections were eligible, which were examined, and which
    document revisions they came from.

    SUBSTRATE_PROPERTIES_V1 P6.1: the population reading itself now lives in
    ONE place — :func:`enumeration.declared_population` — because file B's
    closure and file D's orphans need exactly the same primitive. This function
    is the assessment-shaped caller of it: it wraps the population in a
    ``CandidateSet``.

    Because ``chunk_id`` is now ``section_id``, ``examined_sections`` and the
    candidate identities are the same strings — which is what
    ``_boundary_proof_id``'s equality check has always demanded and never been
    able to get, the two ids having come from different worlds.

    ``withhold`` removes sections from the EXAMINED set while leaving them
    eligible. That is the shape of a real omission, and it must make the receipt
    incomplete.
    """
    from portal.modules.compliance.core import enumeration
    from portal.modules.compliance.core.repository import Repository

    repo = Repository()
    try:
        population = enumeration.declared_population(
            repo, jurisdiction=jurisdiction, kb_id=kb_id, scope_sections=scope_sections
        )
        held = set(withhold or ())
        examined = [s for s in population["examined_sections"] if s not in held]
        resolved = {
            s: entry for s, entry in population["sections"].items() if s in set(examined)
        }
        records = [
            _candidate_record(
                {
                    "document_id": str(entry.get("logical_id") or ""),
                    "section_id": section_id,
                    "chunk_id": section_id,
                    "text": str(entry.get("text") or ""),
                    "headings": str(entry.get("headings") or ""),
                    "page": entry.get("page_start"),
                    "relevant": True,
                    "anchor_verified": True,
                }
            )
            for section_id, entry in sorted(resolved.items())
        ]
        receipt = population["boundary_receipt"]
        receipt["examined_sections"] = sorted(set(examined) & set(resolved))
        receipt["omissions"] = sorted(set(scope_sections or receipt["eligible_sections"]) - set(receipt["examined_sections"]))
        receipt["complete"] = bool(receipt["eligible_sections"]) and not receipt["omissions"]
    finally:
        repo.close()
    return CandidateSet(
        records=records,
        retrieval_annotations=[_annotation({}, r) for r in records],
        acquisition_receipt={
            "kb_id": kb_id,
            "acquisition_mode": "EXPLICIT_SET",
            "completeness": "COMPLETE" if receipt["complete"] else "UNKNOWN",
            "candidate_identities": [r.candidate_id for r in records],
            "n_candidates": len(records),
            "n_unresolved": 0,
            "boundary_receipt": receipt,
        },
        unresolved=[],
    )


def acquire_candidates(
    node: RegisterNode,
    *,
    kb_id: str,
    top_k: int = 15,
    arbiter_fn: Any = None,
) -> CandidateSet:
    """Retrieve once and preserve every full candidate with provenance.

    Reuses ``propose``'s search/rerank unchanged. Non-text pointers go to
    ``unresolved`` and can never become quoted evidence; an empty result is a
    typed empty ``CandidateSet`` with a receipt, never a fabricated
    completeness.

    This is a top-k path and therefore can never carry a completed-boundary
    receipt — see :func:`acquire_exhaustively` for the path that can.
    """
    hits, unresolved, receipt = _propose.resolve_candidates(
        node, kb_id=kb_id, top_k=top_k, arbiter_fn=arbiter_fn
    )
    records = [_candidate_record(hit) for hit in hits]
    annotations = [_annotation(hit, record) for hit, record in zip(hits, records, strict=True)]
    receipt = dict(receipt)
    receipt.setdefault("acquisition_mode", "RETRIEVAL")
    receipt.setdefault("completeness", "UNKNOWN")
    receipt["candidate_identities"] = [r.candidate_id for r in records]
    receipt["n_candidates"] = len(records)
    receipt["n_unresolved"] = len(unresolved)
    return CandidateSet(
        records=records,
        retrieval_annotations=annotations,
        acquisition_receipt=receipt,
        unresolved=unresolved,
    )


# ── request assembly ────────────────────────────────────────────────────────


def _resolve_scope(kb_id: str, scope_text: str) -> tuple[AssetScope, dict[str, Any]]:
    if scope_text:
        return parse_scope_declaration(scope_text), {"basis": "declared"}
    from portal.modules.compliance.core.scope_derive import derive_scope

    return derive_scope(kb_id)


def build_assessment_request(
    requirement_id: str,
    *,
    kb_id: str = "operator_corpus",
    scope_text: str = "",
    effective_on: str = "",
    known_at: str = "",
    org_id: str = "default",
    conditional_scope: bool = False,
    top_k: int = 15,
    arbiter_fn: Any = None,
    policy_graph: Any = None,
) -> AssessmentRequest:
    """Build one fully specified request. A silently-loaded default org graph
    is never consulted; the caller declares scope or the corpus derives it.

    A governing bundle with a failed component (``U14_INCOMPLETE_SOURCE_BUNDLE``)
    stops here — an incomplete source bundle is an engineering defect to
    repair, never an assessment to run against a partial governing text and
    never an item for the SME queue.
    """
    node = _register_node(requirement_id)
    scope, scope_meta = _resolve_scope(kb_id, scope_text)
    governing = resolve_governing_bundle(requirement_id, policy_graph=policy_graph)
    readiness = governing.readiness or {}
    if readiness and not readiness.get("ready", True):
        raise SourceBundleIncompleteError(
            ref=requirement_id, failures=list(readiness.get("failures", []))
        )
    candidates = acquire_candidates(node, kb_id=kb_id, top_k=top_k, arbiter_fn=arbiter_fn)
    snapshot = build_corpus_snapshot(kb_id, acquisition_receipt=candidates.acquisition_receipt)
    return AssessmentRequest(
        requirement_id=requirement_id,
        kb_id=kb_id,
        org_id=org_id,
        scope=scope,
        scope_basis="conditional" if conditional_scope else "actual",
        effective_on=effective_on,
        known_at=known_at,
        conditional_scope=conditional_scope,
        governing=governing,
        snapshot=snapshot,
        candidate_set=candidates,
        metadata={"scope": scope_meta},
    )


# ── scenario overlay materialisation ────────────────────────────────────────


def _proposed_slice(*, document_id: str, chunk_id: str, section: str, text: str) -> SourceSlice:
    return SourceSlice(
        slice_id=f"prop-{hashlib.sha256(f'{document_id}|{chunk_id}|{text}'.encode()).hexdigest()[:16]}",
        ref=f"{document_id} {section}".strip(),
        document_id=document_id,
        revision_hash=_sha256(text),
        chunk_id=chunk_id,
        locator=section,
        text=text,
        char_start=0,
        char_end=len(text),
        role="proposed",
    )


def _add_record(edit: ScenarioEdit, sequence: int, *, label: str = "") -> CandidateRecord:
    text = edit.new_text
    document_id = edit.target_document
    chunk_id = edit.chunk_id or f"{document_id}#proposed-{sequence}"
    section = edit.target_section or edit.label or "proposed"
    if label:
        section = f"{section} ({label})"
    sl = _proposed_slice(document_id=document_id, chunk_id=chunk_id, section=section, text=text)
    return CandidateRecord(
        candidate_id=chunk_id,
        document_id=document_id,
        chunk_id=chunk_id,
        text=text,
        locator=section,
        layer="proposed",
        relevant=False,
        anchor_verified=True,
        revision_hash=sl.revision_hash,
        char_start=0,
        char_end=len(text),
        source_slice=sl,
    )


def _replace_record(edit: ScenarioEdit, target: CandidateRecord) -> CandidateRecord:
    text = target.text
    start, end = edit.char_start, edit.char_end
    if end <= start:
        start, end = 0, len(text)
    if start < 0 or end > len(text):
        raise ValueError("replacement range is outside the stored chunk (U13)")
    old = text[start:end]
    if edit.expected_old_hash and edit.expected_old_hash != _sha256(old):
        raise ValueError(
            "stale expected_old_hash — overlay does not match the pinned snapshot (U13)"
        )
    if edit.expected_old_text and edit.expected_old_text != old:
        raise ValueError(
            "stale expected_old_text — overlay does not match the pinned snapshot (U13)"
        )
    new_text = text[:start] + edit.new_text + text[end:]
    sl = _proposed_slice(
        document_id=target.document_id,
        chunk_id=target.chunk_id,
        section=edit.target_section or target.locator or "proposed",
        text=new_text,
    )
    return replace(
        target,
        candidate_id=f"{target.candidate_id}:proposed",
        text=new_text,
        layer="proposed",
        relevant=False,
        source_slice=sl,
        char_start=0,
        char_end=len(new_text),
        revision_hash=sl.revision_hash,
    )


def _match_target(records: list[CandidateRecord], edit: ScenarioEdit) -> CandidateRecord:
    by_chunk = [
        r
        for r in records
        if r.document_id == edit.target_document and edit.chunk_id and r.chunk_id == edit.chunk_id
    ]
    if not by_chunk and edit.target_section:
        by_chunk = [
            r
            for r in records
            if r.document_id == edit.target_document and r.locator == edit.target_section
        ]
    if len(by_chunk) != 1:
        raise ValueError(
            f"ambiguous or missing replacement target {edit.target_document!r}/"
            f"{edit.chunk_id or edit.target_section!r} (U13)"
        )
    return by_chunk[0]


def _overlaps(
    spans: dict[tuple[str, str], list[tuple[int, int]]],
    key: tuple[str, str],
    start: int,
    end: int,
) -> bool:
    return any(not (end <= s or start >= e) for s, e in spans.get(key, []))


def materialize_overlay(request: AssessmentRequest, overlay: ScenarioOverlay) -> AssessmentRequest:
    """Apply ordered, non-overlapping edits over a pinned base snapshot and
    return a NEW request. The base request is never mutated.

    A ``REPLACE`` requires an exact target plus ``expected_old_hash``; a stale
    hash, an ambiguous/missing target or an overlapping range is rejected. A
    bare legacy patch (no exact target/hash) is treated as an ``ADD`` labelled
    as such — never a silent replacement.
    """
    if request.snapshot is None:
        raise ValueError("cannot materialize an overlay over an unpinned request")
    if (
        not overlay.base_snapshot_fingerprint
        or overlay.base_snapshot_fingerprint != request.snapshot.fingerprint
    ):
        raise ValueError(
            "overlay base_snapshot_fingerprint does not match the pinned snapshot (U13): "
            f"{overlay.base_snapshot_fingerprint!r} != {request.snapshot.fingerprint!r}"
        )

    base = list(request.candidate_set.records) if request.candidate_set else []
    proposed: list[CandidateRecord] = []
    replaced_ids: set[str] = set()
    affected: set[str] = set()
    spans: dict[tuple[str, str], list[tuple[int, int]]] = {}

    for edit in overlay.edits:
        operation = edit.operation.upper()
        bare_patch = operation == "REPLACE" and not (edit.chunk_id and edit.expected_old_hash)
        if operation == "ADD" or bare_patch:
            if not edit.target_document:
                raise ValueError(
                    "ADD requires a named target document/section or an explicit new procedure"
                )
            record = _add_record(edit, len(proposed), label="legacy-add" if bare_patch else "")
            proposed.append(record)
            affected.add(edit.target_document)
            continue

        target = _match_target(base, edit)
        start, end = edit.char_start, edit.char_end
        if end <= start:
            start, end = 0, len(target.text)
        key = (target.document_id, target.chunk_id)
        if _overlaps(spans, key, start, end):
            raise ValueError("overlapping overlay edits are rejected (U13)")
        spans.setdefault(key, []).append((start, end))
        proposed.append(_replace_record(edit, target))
        replaced_ids.add(target.candidate_id)
        affected.add(target.document_id)

    records = [r for r in base if r.candidate_id not in replaced_ids] + proposed
    identities = [r.candidate_id for r in records]

    snapshot = replace(request.snapshot)
    snapshot.candidate_identities = identities
    snapshot.acquisition_mode = "EXPLICIT_SET"
    snapshot.fingerprint = _snapshot_fingerprint(snapshot)
    snapshot.snapshot_id = f"snap-{snapshot.fingerprint[:20]}"

    candidate_set = replace(request.candidate_set) if request.candidate_set else CandidateSet()
    candidate_set.records = records
    candidate_set.acquisition_receipt = dict(
        candidate_set.acquisition_receipt or {"acquisition_mode": "EXPLICIT_SET"}
    )
    candidate_set.acquisition_receipt["acquisition_mode"] = "EXPLICIT_SET"
    candidate_set.acquisition_receipt["candidate_identities"] = identities

    return replace(
        request,
        snapshot=snapshot,
        candidate_set=candidate_set,
        overlay=overlay,
        affected_parts=sorted(set(request.affected_parts) | affected),
    )
