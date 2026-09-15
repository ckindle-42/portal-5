#!/usr/bin/env python3
"""Materialize complete CIP-007 regulatory bundles into the canonical store.

Foundation task P3. The v3 source materializer registers the register's
standards and their decomposition; this script completes the CIP-007 picture
it cannot produce:

* both official revisions — CIP-007-6 (current) and CIP-007-7.1 (future) —
  as immutable document revisions with role-typed source sections
  (``REGULATORY_REQUIREMENT`` / ``MEASURE`` / ``TECHNICAL_BASIS``) whose
  spans hash-verify against the revision bytes;
* CIP-007-7.1's revision-specific duty rows (the register does not carry
  7.1 yet), decomposed with the same decomposer, with effectivity asserted
  from the Phase-2 lifecycle facts;
* semantic duty concepts and lineage between the revisions — computed from
  duty-text correspondence, never from matching Part numbers;
* the per-Part inspection receipt for CIP-007-6 R2.1–R2.4 (the phase exit
  evidence), written to the private artifact hierarchy.

Idempotent: identical bytes and identical derived rows re-run as a no-op.
Makes no model calls and emits no coverage verdicts.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

import pymupdf

from portal.modules.compliance.core.duty_lineage import (
    DutyHandle,
    assign_concepts,
    pair_duties,
)
from portal.modules.compliance.core.models import SourceDocument, SourceSection
from portal.modules.compliance.core.obligations import (
    decompose,
    expression_for,
)
from portal.modules.compliance.core.regulatory_bundle import (
    extract_revision_bundle,
    part_bundle,
    readiness_failures,
)
from portal.modules.compliance.core.repository import Repository
from portal.modules.compliance.core.temporal import now_iso

_DATA = Path(__file__).resolve().parents[1] / "portal/modules/compliance/data"
OFFICIAL_DIR = _DATA / "private" / "nerc_official"
PINNED_DIR = _DATA / "cip_pdfs"
PRIVATE_RECEIPTS = (
    Path(__file__).resolve().parents[1] / "coding_task/v9_compliance/private/regulatory_bundles"
)


def _id(prefix: str, value: str) -> str:
    return prefix + hashlib.sha256(value.encode()).hexdigest()[:20]


def _load_source(name: str, expected_prefix: str) -> bytes:
    for directory in (OFFICIAL_DIR, PINNED_DIR):
        path = directory / name
        if not path.is_file():
            continue
        content = path.read_bytes()
        if expected_prefix and not hashlib.sha256(content).hexdigest().startswith(expected_prefix):
            continue
        return content
    raise FileNotFoundError(f"no verified source bytes for {name!r}")


def _register_revision(repo: Repository, logical_id: str, title: str, name: str, content: bytes):
    repo.upsert_source_document(
        SourceDocument(
            logical_id=logical_id,
            title=title,
            issuer="NERC",
            source_kind="regulatory_standard",
            jurisdiction="United States",
        )
    )
    revision = repo.add_document_revision(logical_id, name, content, binding_effect="regulatory")
    conn = repo._conn
    with repo._lock, conn:
        version = name.rsplit("-", 1)[1].removesuffix(".pdf")
        conn.execute(
            "INSERT OR IGNORE INTO standard_revisions(revision_id,logical_id,family,version,org_id) VALUES (?,?,?,?,?)",
            (revision.revision_id, logical_id, "CIP-007", version, "default"),
        )
    return revision.revision_id


def _bundle_sections(
    repo: Repository,
    revision_id: str,
    bundle,
    extractor_version: str,
) -> dict[str, int]:
    """Persist every extracted component as a role-typed section + spans.

    Span offsets are half-open ranges in the bundle's normalized document
    text (the same coordinates ``RegulatorySpan.verify`` re-derives from the
    revision bytes)."""
    counts = {"sections": 0, "spans": 0}

    def _add(label: str, role: str, text: str, page_start: int, page_end: int, offsets) -> None:
        section_id = _id("section-", revision_id + label)
        repo.add_source_section(
            SourceSection(
                section_id=section_id,
                revision_id=revision_id,
                path=label,
                page_start=page_start,
                page_end=page_end,
                extractor="regulatory-bundle/1",
                extractor_version=extractor_version,
                role=role,
            )
        )
        start, end = offsets
        if end > start:
            repo.add_source_span(
                _id("span-", revision_id + label + text),
                section_id,
                start,
                end,
                hashlib.sha256(text.encode()).hexdigest(),
            )
            counts["spans"] += 1
        counts["sections"] += 1

    for part in bundle.parts:
        pid = bundle.part_id(part)
        _add(
            pid,
            "REGULATORY_REQUIREMENT",
            part.verbatim_text,
            part.source_pages[0] if part.source_pages else None,
            part.source_pages[-1] if part.source_pages else None,
            _find_offsets(bundle, part.verbatim_text),
        )
        if part.measure_text:
            _add(
                f"{pid} Measures",
                "MEASURE",
                part.measure_text,
                part.source_pages[0] if part.source_pages else None,
                part.source_pages[-1] if part.source_pages else None,
                _find_offsets(bundle, part.measure_text),
            )
    for req, lead in bundle.leadins.items():
        if lead[0]:
            _add(
                f"{req} lead-in",
                "REGULATORY_REQUIREMENT",
                lead[0],
                None,
                None,
                _find_offsets(bundle, lead[0]),
            )
        if req in bundle.measures_leadins:
            _add(
                f"{req} Measures lead-in",
                "MEASURE",
                bundle.measures_leadins[req],
                None,
                None,
                _find_offsets(bundle, bundle.measures_leadins[req]),
            )
    for group in (
        bundle.technical_basis,
        bundle.technical_basis_parts,
        bundle.technical_basis_rationale,
    ):
        for key, spans in group.items():
            for span in spans:
                _add(
                    f"{span.locator} ({key})",
                    span.role,
                    span.text,
                    span.page_start,
                    span.page_end,
                    (span.doc_char_start, span.doc_char_end),
                )
    return counts


def _find_offsets(bundle, text: str) -> tuple[int, int]:
    """Offsets of ``text`` in the normalized document text, or (-1, -1)."""
    from portal.modules.compliance.core.regulatory_bundle import _doc_text

    doc = _doc_text(bundle.normalized_pages)
    pos = doc.find(text)
    return (pos, pos + len(text)) if pos >= 0 else (-1, -1)


def _duty_rows(
    repo: Repository,
    revision_id: str,
    bundle,
    requirements: tuple[str, ...],
) -> int:
    conn = repo._conn
    written = 0
    known = {row[0] for row in conn.execute("SELECT node_id FROM requirement_nodes").fetchall()}
    lead_ins = {
        (part.standard, part.requirement): text
        for part in bundle.parts
        for text in [bundle.leadins.get(part.requirement, ("", "", ""))[0]]
    }
    for part in bundle.parts:
        if part.part and not any(part.requirement == r for r in requirements):
            continue
        node_id = bundle.part_id(part)
        if node_id not in known:
            with repo._lock, conn:
                conn.execute(
                    "INSERT OR IGNORE INTO requirement_nodes(node_id,standard_revision_id,requirement,part,logical_lineage_id,org_id) VALUES (?,?,?,?,?,?)",
                    (node_id, revision_id, part.requirement, part.part, "", "default"),
                )
                known.add(node_id)
        anchor_id = _id("span-", revision_id + node_id + part.verbatim_text)
        section_id = _id("section-", revision_id + node_id)
        repo.add_source_section(
            SourceSection(
                section_id=section_id,
                revision_id=revision_id,
                path=node_id,
                extractor="regulatory-bundle/1",
                extractor_version=pymupdf.__version__,
                role="REGULATORY_REQUIREMENT",
            )
        )
        repo.add_source_span(
            anchor_id,
            section_id,
            0,
            len(part.verbatim_text),
            hashlib.sha256(part.verbatim_text.encode()).hexdigest(),
        )
        lead = lead_ins.get((part.standard, part.requirement), "") if part.part else ""
        atoms = decompose(node_id, part.verbatim_text, lead_in=lead, anchor_ids=[anchor_id])
        repo.replace_obligation_derivation(
            node_id,
            [a.to_record() for a in atoms],
            expression_for(atoms, part.verbatim_text),
            expression_id=_id("expr-", node_id),
        )
        base_id = node_id.rsplit(" Part ", 1)[0]
        for atom in atoms:
            for ref in atom.depends_on:
                target = f"{base_id} {ref}"
                if target not in known or target == node_id:
                    continue
                repo.add_obligation_dependency(
                    _id("dep-", node_id + atom.atom_id + ref),
                    node_id,
                    atom.atom_id,
                    depends_on_node_id=target,
                    depends_on_ref=ref,
                )
        written += 1
    return written


def _lifecycle_effectivity(
    repo: Repository, node_ids: list[str], valid_from: str, valid_to: str | None
) -> int:
    """Assert registry-sourced effectivity for each duty, replacing the
    unverified ``legacy:`` default rows (no retirement boundary) those nodes
    carry. Derived assertions are replaced, never duplicated with conflicting
    validity."""
    conn = repo._conn
    written = 0
    with repo._lock, conn:
        for node_id in node_ids:
            conn.execute(
                "DELETE FROM effectivity_assertions WHERE node_id = ? AND assertion_id LIKE 'legacy:%'",
                (node_id,),
            )
            assertion_id = _id("eff-", node_id)
            exists = conn.execute(
                "SELECT 1 FROM effectivity_assertions WHERE assertion_id = ?", (assertion_id,)
            ).fetchone()
            if exists:
                continue
            conn.execute(
                """INSERT INTO effectivity_assertions(assertion_id,node_id,jurisdiction,valid_from,valid_to,recorded_from,approval_status,org_id)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (
                    assertion_id,
                    node_id,
                    "NERC",
                    valid_from,
                    valid_to,
                    now_iso(),
                    "verified",
                    "default",
                ),
            )
            written += 1
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--receipt-dir", type=Path, default=PRIVATE_RECEIPTS)
    args = parser.parse_args(argv)

    reg_path = _DATA / "nerc_cip_register.json"
    reg = json.loads(reg_path.read_text())
    prefixes = reg["source_pdfs"]

    started = time.time()
    repo = Repository()
    receipt: dict = {"started_at": now_iso(), "revisions": {}, "lineage": {}, "r2_inspection": []}

    revisions: dict[str, tuple[str, object]] = {}
    for name, title, logical_id in (
        (
            "cip-007-6.pdf",
            "CIP-007-6 — Cyber Security – Systems Security Management",
            "NERC/CIP-007-6",
        ),
        (
            "cip-007-7.1.pdf",
            "CIP-007-7.1 — Cyber Security – Systems Security Management",
            "NERC/CIP-007-7.1",
        ),
    ):
        content = _load_source(name, prefixes.get(name, ""))
        revision_id = _register_revision(repo, logical_id, title, name, content)
        bundle = extract_revision_bundle(content, expected_sha256=revision_id, source_name=name)
        revisions[logical_id] = (revision_id, bundle)
        span_counts = _bundle_sections(repo, revision_id, bundle, pymupdf.__version__)
        receipt["revisions"][logical_id] = {
            "revision_id": revision_id,
            "source": name,
            "technical_basis_section": bundle.technical_basis_section,
            "definitions_disposition": bundle.definitions_disposition,
            **span_counts,
        }

    # 7.1 duty rows (the register does not carry 7.1 yet) — all requirements
    duties_71 = _duty_rows(
        repo,
        revisions["NERC/CIP-007-7.1"][0],
        revisions["NERC/CIP-007-7.1"][1],
        tuple(f"R{i}" for i in range(1, 6)),
    )
    receipt["revisions"]["NERC/CIP-007-7.1"]["duty_rows"] = duties_71

    # effectivity from the Phase-2 sourced lifecycle facts
    n6 = _lifecycle_effectivity(
        repo,
        sorted(bundle.part_id(p) for p in revisions["NERC/CIP-007-6"][1].parts if p.part),
        "2016-07-01",
        "2028-06-30",
    )
    n71 = _lifecycle_effectivity(
        repo,
        sorted(bundle.part_id(p) for p in revisions["NERC/CIP-007-7.1"][1].parts if p.part),
        "2028-07-01",
        None,
    )
    receipt["effectivity_assertions"] = {"CIP-007-6": n6, "CIP-007-7.1": n71}

    # semantic lineage: pair every duty of the two revisions by text
    handles = {}
    for logical_id in ("NERC/CIP-007-6", "NERC/CIP-007-7.1"):
        bundle = revisions[logical_id][1]
        handles[logical_id] = [
            DutyHandle(node_id=bundle.part_id(p), standard=bundle.standard, text=p.verbatim_text)
            for p in bundle.parts
            if p.part
        ]
    pairs, unpaired_6, unpaired_71 = pair_duties(
        handles["NERC/CIP-007-6"], handles["NERC/CIP-007-7.1"]
    )
    prior = {
        row[0]: row[1]
        for row in repo._conn.execute(
            "SELECT node_id, logical_lineage_id FROM requirement_nodes WHERE logical_lineage_id <> ''"
        ).fetchall()
    }
    concepts = assign_concepts(pairs, unpaired_6 + unpaired_71, prior_concepts=prior)
    for concept in concepts:
        repo.upsert_obligation_concept(
            concept.concept_id,
            family=concept.family,
            label=concept.label,
            derivation=concept.derivation,
        )
        for node_id in concept.members:
            repo.set_requirement_lineage(node_id, concept.concept_id)
    receipt["lineage"] = {
        "derivation": concepts[0].derivation if concepts else "",
        "pairs": [{"a": p.a.node_id, "b": p.b.node_id, "score": round(p.score, 4)} for p in pairs],
        "unpaired": [d.node_id for d in unpaired_6 + unpaired_71],
        "concepts": len(concepts),
    }

    # ── the phase-exit receipt: independently inspect CIP-007-6 R2.1–R2.4 ──
    bundle6 = revisions["NERC/CIP-007-6"][1]
    for part in ("2.1", "2.2", "2.3", "2.4"):
        pb = part_bundle(bundle6, "R2", part)
        node_id = f"CIP-007-6 R2 Part {part}"
        lead = bundle6.leadins.get("R2", ("", "", ""))[0]
        atoms = decompose(node_id, pb["part_text"], lead_in=lead)
        expression = expression_for(atoms, pb["part_text"])
        from portal.modules.compliance.core.obligations import decomposition_defects

        defects = decomposition_defects(atoms, expression, pb["part_text"])
        entry = {
            "ref": node_id,
            "readiness": readiness_failures(pb) or "READY",
            "lead_in_sha256": hashlib.sha256(lead.encode()).hexdigest()[:12] if lead else "",
            "part_text_sha256": hashlib.sha256(pb["part_text"].encode()).hexdigest()[:12],
            "applicable_systems_sha256": hashlib.sha256(
                pb["applicable_systems"].encode()
            ).hexdigest()[:12],
            "measures": [
                {
                    "locator": m["locator"],
                    "sha256": hashlib.sha256(m["text"].encode()).hexdigest()[:12],
                }
                for m in pb["measures"]
            ],
            "technical_basis": [
                {"locator": t["locator"], "sha256": t["sha256"][:12]} for t in pb["technical_basis"]
            ],
            "definitions_disposition": pb["definitions_disposition"],
            "atoms": len(atoms),
            "expression": expression,
            "decomposition_defects": defects,
            "dependencies": sorted({d for a in atoms for d in a.depends_on}),
        }
        receipt["r2_inspection"].append(entry)

    receipt["elapsed_s"] = round(time.time() - started, 1)
    out_dir = args.receipt_dir / time.strftime("%Y%m%dT%H%M%S", time.gmtime())
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "inspection.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(
        json.dumps(
            {
                "receipt": str(out_dir / "inspection.json"),
                "revisions": {k: v["revision_id"][:12] for k, v in receipt["revisions"].items()},
                "lineage_pairs": len(receipt["lineage"]["pairs"]),
                "unpaired": receipt["lineage"]["unpaired"],
                "r2_inspection": [
                    {"ref": e["ref"], "readiness": e["readiness"], "atoms": e["atoms"]}
                    for e in receipt["r2_inspection"]
                ],
            },
            indent=2,
        )
    )
    ok = all(
        e["readiness"] == "READY" and not e["decomposition_defects"]
        for e in receipt["r2_inspection"]
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
