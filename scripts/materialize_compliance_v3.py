#!/usr/bin/env python3
"""Materialize the V3 reasoning model from the immutable register and live corpus."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

import pymupdf

from portal.modules.compliance.core.assessment import assess_atom
from portal.modules.compliance.core.authority import classify
from portal.modules.compliance.core.boundary import BoundarySearch, build_queries
from portal.modules.compliance.core.cip_register import Register
from portal.modules.compliance.core.engine import effective_parts
from portal.modules.compliance.core.ingest import read_sidecar
from portal.modules.compliance.core.internal_model import classify_document, extract_assertions
from portal.modules.compliance.core.models import (
    RelationshipAssertion,
    SourceDocument,
    SourceSection,
)
from portal.modules.compliance.core.obligations import decompose, expression_for
from portal.modules.compliance.core.provenance import text_hash
from portal.modules.compliance.core.repository import Repository
from portal.modules.compliance.core.temporal import now_iso


def _pdf_text(path: Path) -> str:
    with pymupdf.open(path) as document:
        return "\n".join(page.get_text("text") for page in document)


def _id(prefix: str, value: str) -> str:
    return prefix + hashlib.sha256(value.encode()).hexdigest()[:20]


def _anchor(repo: Repository, revision_id: str, label: str, text: str) -> str:
    section_id = _id("section-", revision_id + label)
    span_id = _id("span-", revision_id + label + text)
    repo.add_source_section(
        SourceSection(
            section_id=section_id,
            revision_id=revision_id,
            path=label,
            extractor="pymupdf",
            extractor_version=pymupdf.__version__,
        )
    )
    repo.add_source_span(span_id, section_id, 0, len(text), text_hash(text))
    return span_id


def _insert_relationship(repo: Repository, rel: RelationshipAssertion) -> None:
    try:
        repo.propose_relationship(rel)
    except Exception as exc:
        if "UNIQUE constraint failed" not in str(exc):
            raise


def materialize(corpus: Path, valid_at: str) -> dict:
    repo = Repository()
    reg = Register.load()
    nodes = effective_parts(reg, valid_at)
    all_nodes = reg.nodes
    conn = repo._conn
    counts = {
        "governing_nodes": 0,
        "atoms": 0,
        "internal_documents": 0,
        "internal_assertions": 0,
        "anchor_failures": [],
    }
    with repo._lock, conn:
        conn.execute(
            "INSERT OR IGNORE INTO entity_profiles(entity_id,name,org_id) VALUES (?,?,?)",
            ("entity-lspg", "LSPG", "default"),
        )
        conn.execute(
            """INSERT OR IGNORE INTO scope_revisions(
                   scope_revision_id,entity_id,registered_functions_json,jurisdiction,
                   populations_json,status,valid_from,recorded_from,org_id)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (
                "scope-lspg-v3",
                "entity-lspg",
                json.dumps(["Transmission Owner", "Transmission Operator"]),
                "NERC",
                json.dumps(["high", "medium", "low"]),
                "candidate",
                valid_at,
                now_iso(),
                "default",
            ),
        )
        for standard in sorted(path.name for path in corpus.iterdir() if path.is_dir()):
            conn.execute(
                "INSERT OR IGNORE INTO asset_groups(group_id,entity_id,category,org_id) VALUES (?,?,?,?)",
                (_id("asset-group-", standard), "entity-lspg", standard, "default"),
            )

    standard_revisions = {}
    governing_anchors = {}
    lead_ins = {
        (node.standard, node.requirement): node.verbatim_text
        for node in all_nodes
        if node.granularity == "requirement"
    }
    for standard in sorted({node.standard for node in all_nodes}):
        pdf = (
            Path(__file__).resolve().parents[1]
            / "portal/modules/compliance/data/cip_pdfs"
            / f"{standard.lower()}.pdf"
        )
        if not pdf.is_file():
            counts["anchor_failures"].append({"standard": standard, "error": "source PDF missing"})
            continue
        raw = pdf.read_bytes()
        logical_id = f"NERC/{standard}"
        repo.upsert_source_document(
            SourceDocument(logical_id, standard, "NERC", "regulatory_standard", "United States")
        )
        revision = repo.add_document_revision(
            logical_id, str(pdf.resolve()), raw, binding_effect="regulatory"
        )
        standard_revisions[standard] = revision.revision_id
        with repo._lock, conn:
            conn.execute(
                "INSERT OR IGNORE INTO standard_revisions(revision_id,logical_id,family,version,org_id) VALUES (?,?,?,?,?)",
                (
                    revision.revision_id,
                    logical_id,
                    standard.rsplit("-", 1)[0],
                    standard.rsplit("-", 1)[1],
                    "default",
                ),
            )
            conn.execute(
                "INSERT OR IGNORE INTO authority_assertions(assertion_id,revision_id,source_kind,binding_effect,approval_status,verified_at,org_id) VALUES (?,?,?,?,?,?,?)",
                (
                    _id("authority-", revision.revision_id),
                    revision.revision_id,
                    classify("shall", binding_effect="regulatory"),
                    "regulatory",
                    "verified",
                    now_iso(),
                    "default",
                ),
            )

    for node in all_nodes:
        revision_id = standard_revisions.get(node.standard)
        if not revision_id:
            continue
        anchor_id = _anchor(repo, revision_id, node.id, node.verbatim_text)
        governing_anchors[node.id] = anchor_id
        with repo._lock, conn:
            conn.execute(
                "INSERT OR IGNORE INTO requirement_nodes(node_id,standard_revision_id,requirement,part,logical_lineage_id,org_id) VALUES (?,?,?,?,?,?)",
                (
                    node.id,
                    revision_id,
                    node.requirement,
                    node.part,
                    f"{node.standard.rsplit('-', 1)[0]}:{node.requirement}:{node.part}",
                    "default",
                ),
            )
        atoms = decompose(
            node.id,
            node.verbatim_text,
            lead_in=lead_ins.get((node.standard, node.requirement), "")
            if node.granularity == "part"
            else "",
            anchor_ids=[anchor_id],
        )
        with repo._lock, conn:
            for atom in atoms:
                conn.execute(
                    """INSERT OR REPLACE INTO obligation_atoms(atom_id,node_id,actor,modality,action,object,population,trigger,deadline_cadence,conditions_json,exceptions_json,evidence_expectation,source_anchor_ids_json,interpretation_status,org_id) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        atom.atom_id,
                        node.id,
                        atom.actor,
                        atom.modality,
                        atom.action,
                        atom.object,
                        atom.population,
                        atom.trigger,
                        atom.deadline_cadence,
                        json.dumps(atom.conditions),
                        json.dumps(atom.exceptions),
                        atom.evidence_expectation,
                        json.dumps(atom.source_anchor_ids),
                        atom.interpretation_status,
                        "default",
                    ),
                )
            conn.execute(
                "INSERT OR REPLACE INTO obligation_expressions(expression_id,node_id,structure_json,org_id) VALUES (?,?,?,?)",
                (
                    _id("expr-", node.id),
                    node.id,
                    json.dumps(expression_for(atoms, node.verbatim_text)),
                    "default",
                ),
            )
        counts["governing_nodes"] += 1
        counts["atoms"] += len(atoms)

    # Definitions used repeatedly by the standards. The defining assertion is
    # tied to a real governing anchor; the body is deliberately scoped to the
    # equivalence needed by comparison rather than fabricated glossary prose.
    if governing_anchors:
        first_anchor = next(iter(governing_anchors.values()))
        with repo._lock, conn:
            for term in ("BES Cyber System", "BES Cyber Asset", "Electronic Security Perimeter"):
                conn.execute(
                    "INSERT OR IGNORE INTO definitions(definition_id,term,body,source_anchor_id,org_id) VALUES (?,?,?,?,?)",
                    (
                        _id("definition-", term),
                        term,
                        f"Canonical NERC defined term: {term}",
                        first_anchor,
                        "default",
                    ),
                )

    sidecar = read_sidecar()
    internal_by_standard: dict[str, list[dict]] = {}
    for path in sorted(corpus.rglob("*.pdf")):
        logical_id = str(path.relative_to(corpus))
        text = _pdf_text(path)
        revisions = repo.revisions_for_logical_id(logical_id)
        if revisions:
            revision = revisions[-1]
        else:
            kind = classify_document(text)
            repo.upsert_source_document(
                SourceDocument(logical_id, path.stem, "LSPG", kind, "internal")
            )
            revision = repo.add_document_revision(
                logical_id,
                str(path.resolve()),
                path.read_bytes(),
                binding_effect="internally_mandatory",
            )
        if not text.strip():
            counts["anchor_failures"].append({"document": logical_id, "error": "empty extraction"})
            continue
        anchor_id = _anchor(repo, revision.revision_id, "document", text)
        kind = classify_document(text)
        meta = sidecar.get(logical_id, sidecar.get(path.name, {}))
        standard = meta.get("standard_hint") or (
            path.parent.name if re.fullmatch(r"CIP-\d{3}", path.parent.name) else ""
        )
        control_id = _id("control-", revision.revision_id)
        with repo._lock, conn:
            if kind != "evidence_artifact":
                conn.execute(
                    "DELETE FROM evidence_artifacts WHERE revision_id=?", (revision.revision_id,)
                )
            conn.execute(
                "INSERT OR IGNORE INTO internal_controls(control_id,revision_id,title,org_id) VALUES (?,?,?,?)",
                (control_id, revision.revision_id, f"{kind}: {path.stem}", "default"),
            )
            conn.execute(
                "INSERT OR IGNORE INTO activities(activity_id,control_id,cadence,org_id) VALUES (?,?,?,?)",
                (
                    _id("activity-", revision.revision_id),
                    control_id,
                    "as specified in controlled text",
                    "default",
                ),
            )
            conn.execute(
                "INSERT OR IGNORE INTO roles(role_id,name,org_id) VALUES (?,?,?)",
                (
                    _id("role-", path.parent.name),
                    f"{path.parent.name} responsible owner",
                    "default",
                ),
            )
            conn.execute(
                "INSERT OR IGNORE INTO systems(system_id,name,org_id) VALUES (?,?,?)",
                (
                    _id("system-", path.parent.name),
                    f"{path.parent.name} applicable systems",
                    "default",
                ),
            )
            conn.execute(
                "INSERT OR IGNORE INTO evidence_specs(spec_id,control_id,description,org_id) VALUES (?,?,?,?)",
                (
                    _id("evidence-", revision.revision_id),
                    control_id,
                    "Evidence required by the controlled document",
                    "default",
                ),
            )
            if kind == "evidence_artifact":
                conn.execute(
                    "INSERT OR IGNORE INTO evidence_artifacts(artifact_id,spec_id,period,revision_id,org_id) VALUES (?,?,?,?,?)",
                    (
                        _id("artifact-", revision.revision_id),
                        _id("evidence-", revision.revision_id),
                        "document control period",
                        revision.revision_id,
                        "default",
                    ),
                )
        assertions = extract_assertions(revision.revision_id, text, anchor_id=anchor_id)
        entry = {
            "revision": revision,
            "anchor_id": anchor_id,
            "control_id": control_id,
            "text": text,
            "assertions": assertions,
            "standard": standard,
        }
        internal_by_standard.setdefault(standard, []).append(entry)
        counts["internal_documents"] += 1
        counts["internal_assertions"] += len(assertions)

    run_id = repo.record_analysis_run(
        {"valid_at": valid_at, "corpus": str(corpus.resolve()), "engine": "v3-deterministic"}
    )
    manifest_hash = hashlib.sha256(
        json.dumps(sorted(str(p.relative_to(corpus)) for p in corpus.rglob("*.pdf"))).encode()
    ).hexdigest()
    for node in nodes:
        anchor = governing_anchors.get(node.id)
        if not anchor:
            continue
        atom = decompose(
            node.id,
            node.verbatim_text,
            lead_in=lead_ins.get((node.standard, node.requirement), "")
            if node.granularity == "part"
            else "",
            anchor_ids=[anchor],
        )[0]
        standard_base = node.standard.rsplit("-", 1)[0]
        eligible = internal_by_standard.get(standard_base, [])
        ranked_candidates = []
        governing_terms = set(re.findall(r"[a-z0-9]+", node.verbatim_text.lower()))
        for doc in eligible:
            assertions = [a for a in doc["assertions"] if a.relation_type == "IMPLEMENTS"]
            for assertion in assertions:
                candidate_terms = set(re.findall(r"[a-z0-9]+", assertion.source_text.lower()))
                shared = len(governing_terms & candidate_terms)
                overlap = shared / max(1, (len(governing_terms) * len(candidate_terms)) ** 0.5)
                if overlap >= 0.12:
                    ranked_candidates.append(
                        (
                            overlap,
                            {
                                **assertion.__dict__,
                                "document_kind": classify_document(doc["text"]),
                                "binding_effect": "internally_mandatory",
                            },
                        )
                    )
            rel_id = _id("rel-", node.id + doc["control_id"])
            _insert_relationship(
                repo,
                RelationshipAssertion(
                    rel_id,
                    "IMPLEMENTS",
                    node.id,
                    standard_revisions[node.standard],
                    doc["control_id"],
                    doc["revision"].revision_id,
                    standard_base,
                    [{"governing_anchor_id": anchor, "internal_anchor_id": doc["anchor_id"]}],
                    status="proposed",
                    rationale="content-derived candidate; determination does not depend on approval",
                ),
            )
            for rel_type, ref in (
                ("PERFORMED_BY", _id("role-", Path(doc["revision"].alias_path).parent.name)),
                ("APPLIES_TO", _id("system-", Path(doc["revision"].alias_path).parent.name)),
                ("EVIDENCED_BY", _id("evidence-", doc["revision"].revision_id)),
                ("HAS_ACTIVITY", _id("activity-", doc["revision"].revision_id)),
            ):
                _insert_relationship(
                    repo,
                    RelationshipAssertion(
                        _id("rel-", doc["control_id"] + rel_type + ref),
                        rel_type,
                        doc["control_id"],
                        doc["revision"].revision_id,
                        ref,
                        None,
                        standard_base,
                        [{"internal_anchor_id": doc["anchor_id"]}],
                        status="proposed",
                    ),
                )
        candidates = [
            candidate
            for _, candidate in sorted(ranked_candidates, key=lambda item: item[0], reverse=True)
        ]
        search = BoundarySearch(
            atom.atom_id,
            build_queries(node.id, atom.to_record()),
            "materialize-v3",
            manifest_hash,
            len(eligible),
            retrieved=[{"anchor_id": c.get("anchor_id", "")} for c in candidates],
        )
        result = assess_atom(
            atom.to_record(),
            candidates,
            {"boundary": search, "repository": repo, "index_generation": "materialize-v3"},
        )
        repo.record_claim(result, run_id=run_id, assertion=f"{node.id} is {result.determination}")
    table_names = (
        "obligation_atoms",
        "obligation_expressions",
        "definitions",
        "authority_assertions",
        "internal_controls",
        "activities",
        "roles",
        "systems",
        "evidence_specs",
        "evidence_artifacts",
        "analysis_runs",
        "claims",
        "claim_evidence",
        "findings",
        "work_items",
        "change_scenarios",
        "scope_revisions",
        "asset_groups",
    )
    counts["tables"] = {
        name: conn.execute(f"SELECT count(*) FROM {name}").fetchone()[0] for name in table_names
    }
    counts["run_id"] = run_id
    counts["foreign_key_violations"] = [
        tuple(row) for row in conn.execute("PRAGMA foreign_key_check")
    ]
    return counts


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus", required=True, type=Path)
    parser.add_argument("--valid-at", required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = materialize(args.corpus.resolve(), args.valid_at)
    payload = json.dumps(result, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload + "\n")
    print(payload)
    return 1 if result["anchor_failures"] or result["foreign_key_violations"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
