"""The compliance evaluation instance (root-fix Part 2c-2).

A separate compliance MCP process for WFE rows, so a scoped compliance tool call can never
read or write the operator's compliance store. Every state path is derived from one root;
the operator's private inputs (profile, org graph) point at absent files under that root;
the store is built from public, committed material only (the NERC CIP register and the
synthetic planted corpus); and only tools proven read-only, model-free and history-independent
are served. The pipeline routes scoped compliance calls here (MCP_COMPLIANCE_EVAL_URL) and
never falls back to the operator's instance.

    python -m portal.modules.compliance.core.eval_instance build --root DIR
    python -m portal.modules.compliance.core.eval_instance serve --root DIR [--port 8948]
"""

from __future__ import annotations

import argparse
import asyncio
import os
from pathlib import Path
from typing import Any

#: Measured on an isolated instance (fresh store per tool, quiescence before and after, then a
#: store warmed by every other candidate): no model call, no table or file change, and an
#: answer that does not depend on earlier calls. Re-run on the host with
#: `python -m tests.wfe.e2e.compliance_classify`. Everything else is refused (403).
VERIFIED_TOOLS = frozenset(
    {
        "compliance_answers",
        "compliance_coverage",
        "compliance_flexibility",
        "compliance_impact",
        "compliance_intentionality",
        "compliance_kb_search",
        "compliance_links",
        "compliance_mappings",
        "compliance_notes",
        "compliance_orphans",
        "compliance_prospective",
        "compliance_read",
        "compliance_requirement",
        "compliance_route",
        "compliance_search",
        "compliance_timeline",
        "compliance_trace",
        "lookup_control",
        "map_frameworks",
        "nerc_cip_currency",
        "nerc_cip_requirement",
        "patch_evidence",
        "search_controls",
    }
)
PLANTED = Path(__file__).resolve().parents[1] / "data" / "planted_corpus"


def env_for(root: Path | str, port: int = 8948) -> dict[str, str]:
    """Every state path the compliance module uses, under `root`."""
    r = Path(root).expanduser().resolve()
    return {
        "COMPLIANCE_EVAL_INSTANCE": "1",
        "COMPLIANCE_EVAL_ROOT": str(r),
        "COMPLIANCE_MCP_PORT": str(port),
        "COMPLIANCE_DB_PATH": f"{r}/compliance_store.db",
        "COMPLIANCE_MAPPING_STORE": f"{r}/compliance_store.db",
        "PORTAL5_LANCE_DIR": f"{r}/lance",
        "COMPLIANCE_PAGES_DIR": f"{r}/pages",
        "PORTAL5_EMBED_CACHE_DIR": f"{r}/embed_cache",
        "COMPLIANCE_LAYER_SIDECAR": f"{r}/layers.json",
        "COMPLIANCE_REVIEWERS_PATH": f"{r}/reviewers.json",
        "COMPLIANCE_OPERATOR_PROFILE": f"{r}/no_operator_profile.json",
        "COMPLIANCE_ORG_GRAPH": f"{r}/no_org_graph.json",
    }


def verify(root: Path | str) -> list[str]:
    """Paths the imported code will actually use that are not under `root` (empty = safe)."""
    from portal.modules.compliance.core import (
        mapping_store,
        operator_profile,
        repository,
        runtime_config,
    )
    from portal.platform.retrieval import store

    r = Path(root).expanduser().resolve()
    used = {
        "compliance store": repository.DEFAULT_DB_PATH,
        "mapping store": mapping_store.STORE_PATH,
        "operator profile": operator_profile.PROFILE_PATH,
        "org graph": runtime_config._DEFAULT_ORG_GRAPH,
        "LanceDB": store.LANCE_DIR,
    }
    return [f"{k} would be {v}" for k, v in used.items() if r not in Path(str(v)).resolve().parents]


def _stage_planted(root: Path | str) -> Path:
    """The planted corpus without its ``<!-- PLANT {...} -->`` headers. Each header is
    that document's answer key (targets, control class, expected coverage); ingested
    as-is, any tool that reads the chunk hands a model the answer (N-32)."""
    import re

    out = Path(root).expanduser() / "planted_staged"
    out.mkdir(parents=True, exist_ok=True)
    for f in sorted(PLANTED.glob("*.md")):
        text = re.sub(r"<!--\s*PLANT\s+\{.*?\}\s*-->\s*", "", f.read_text(), flags=re.S)
        (out / f.name).write_text(text)
    return out


def _capture_planted(repo: Any, root: Path | str) -> list[str]:
    """Register, capture and return the logical ids of the planted documents.

    The retrieval index is a projection of the canonical section store, so a document
    that is only embedded (``ingest_folder``) hits nothing: ``compliance_read`` cannot
    resolve its id and every hit is excluded as not in ``source_sections``. Each document
    is therefore registered under its own id (the header's ``doc_id``), captured whole and
    stored, the way ``reader.store_answer`` stores a text-only source."""
    import json
    import re

    from portal.modules.compliance.core.capture import (
        CapturedDocument,
        CapturedUnit,
        store_capture,
    )
    from portal.modules.compliance.core.models import SourceDocument

    staged = _stage_planted(root)
    ids: list[str] = []
    for f in sorted(PLANTED.glob("*.md")):
        head = re.search(r"<!--\s*PLANT\s+(\{.*?\})\s*-->", f.read_text(), re.S)
        meta = json.loads(head.group(1)) if head else {}
        doc_id = meta["doc_id"]
        staged_file = staged / f.name
        body = staged_file.read_text()
        repo.upsert_source_document(
            SourceDocument(
                logical_id=doc_id,
                title=doc_id,
                issuer="operator",
                source_kind=str(meta.get("doc_class") or "policy"),
                jurisdiction="internal",
            )
        )
        revision = repo.add_document_revision(
            doc_id, str(staged_file), body.encode(), binding_effect="binding"
        )
        # Units tile the text: one per second-level heading, the first also holding the title.
        cuts = [0, *[m.start() for m in re.finditer(r"^## ", body, re.M) if m.start()], len(body)]
        units = []
        for n, (a, b) in enumerate(zip(cuts, cuts[1:], strict=False)):
            first = body[a:b].strip().splitlines()[0].lstrip("# ").strip()
            units.append(
                CapturedUnit(
                    ordinal=n,
                    unit_kind="prose",
                    heading_path=f"{doc_id} > {first}" if n else doc_id,
                    title=first,
                    page_start=1,
                    page_end=1,
                    char_start=a,
                    char_end=b,
                    text=body[a:b],
                )
            )
        store_capture(
            repo,
            revision.revision_id,
            CapturedDocument(
                path=staged_file,
                page_count=1,
                full_text=body,
                units=units,
                extractor="eval_instance",
                extractor_version="1",
                reader_strings=tuple(u.text for u in units),
            ),
        )
        ids.append(doc_id)
    return ids


def _capture_register(repo: Any, register: Any) -> list[str]:
    """Register, capture and anchor each standard revision's committed requirement text.

    The register tables answer ``nerc_cip_requirement``, but the dual-document payload and
    ``compliance_coverage`` read the standard from captured sections and the anchors into
    them. Without those, a coverage question for CIP-007-6 R2 Part 2.2 resolves its address
    and returns an empty standard side (``sections_in_standard: 0``). Each standard becomes a
    text-only source document, one unit per requirement node holding exactly the node's
    verbatim text, anchored by the same exact-match method production uses."""
    from collections import defaultdict

    from portal.modules.compliance.core.capture import (
        CapturedDocument,
        CapturedUnit,
        store_capture,
    )
    from portal.modules.compliance.core.models import SourceDocument
    from portal.modules.compliance.core.requirement_anchor import anchor_revision

    by_standard: dict[str, list[Any]] = defaultdict(list)
    for node in register.nodes:
        if str(node.verbatim_text or "").strip():
            by_standard[node.standard].append(node)
    ids: list[str] = []
    for standard, nodes in sorted(by_standard.items()):
        logical_id = f"NERC/{standard}"
        repo.upsert_source_document(
            SourceDocument(
                logical_id=logical_id,
                title=logical_id,
                issuer="NERC",
                source_kind="regulatory_standard",
                jurisdiction="US",
            )
        )
        body, units = "", []
        for n, node in enumerate(nodes):
            applies = str(getattr(node, "applicable_systems", "") or "").strip()
            block = f"{node.id}\n{str(node.verbatim_text).strip()}\n" + (
                f"Applicable systems: {applies}\n" if applies else ""
            )
            block += "\n"
            units.append(
                CapturedUnit(
                    ordinal=n,
                    unit_kind="prose",
                    heading_path=f"{logical_id} > {node.id}",
                    title=str(node.id),
                    page_start=1,
                    page_end=1,
                    char_start=len(body),
                    char_end=len(body) + len(block),
                    text=block,
                )
            )
            body += block
        revision = repo.add_document_revision(
            logical_id,
            f"{logical_id}.txt",
            body.encode(),
            binding_effect="binding",
            effective_date=min((str(n.valid_from) for n in nodes if n.valid_from), default=None),
        )
        store_capture(
            repo,
            revision.revision_id,
            CapturedDocument(
                path=Path(f"{logical_id}.txt"),
                page_count=1,
                full_text=body,
                units=units,
                extractor="eval_instance",
                extractor_version="1",
                reader_strings=tuple(u.text for u in units),
            ),
        )
        anchors = anchor_revision(repo, revision.revision_id, nodes)
        repo.record_anchors(anchors)
        # A text under the anchor's length floor is refused by design (a short string would
        # match unrelated text); any other miss means the capture and the register disagree.
        missed = [
            a
            for a in anchors
            if not a.anchored and a.relation == "governing" and "too short" not in str(a.reason)
        ]
        if missed:
            raise RuntimeError(f"{standard}: {len(missed)} requirement(s) did not anchor")
        ids.append(logical_id)
    return ids


def build(root: Path | str) -> dict[str, object]:
    """The evaluation store, from public, committed material only."""
    from portal.modules.compliance.core import section_index
    from portal.modules.compliance.core.cip_register import Register
    from portal.modules.compliance.core.migrate_legacy import import_register
    from portal.modules.compliance.core.repository import Repository
    from portal.modules.compliance.tools.compliance_retrieval import project_sections

    repo = Repository(os.environ["COMPLIANCE_DB_PATH"])
    repo.migrate()
    reg = import_register(repo, Register.load())
    ids = _capture_planted(repo, root)
    standards = _capture_register(repo, Register.load())
    plan = section_index.build_plan(repo, jurisdiction="internal")
    projected = asyncio.run(project_sections(plan.kb_id, plan.units, rebuild=True))
    if len(ids) != len(list(PLANTED.glob("*.md"))) or not plan.units:
        raise RuntimeError(f"the planted corpus did not capture: {len(ids)} documents, {plan}")
    standards_plan = section_index.build_plan(repo, jurisdiction="US")
    if not standards or not standards_plan.units:
        raise RuntimeError(f"the register did not capture: {len(standards)} standards")
    projected_standards = asyncio.run(
        project_sections(standards_plan.kb_id, standards_plan.units, rebuild=True)
    )
    return {
        "register": reg,
        "planted_documents": ids,
        "standards": len(standards),
        "projected": projected,
        "projected_standards": projected_standards,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("action", choices=("build", "serve"))
    ap.add_argument(
        "--root", default=os.environ.get("COMPLIANCE_EVAL_ROOT") or "~/.portal-data/compliance-eval"
    )
    ap.add_argument("--port", type=int, default=int(os.environ.get("COMPLIANCE_EVAL_PORT", "8948")))
    a = ap.parse_args(argv)
    os.environ.update(env_for(a.root, a.port))  # before any compliance module reads its paths
    Path(os.environ["COMPLIANCE_EVAL_ROOT"]).mkdir(parents=True, exist_ok=True)
    bad = verify(a.root)
    if bad:
        raise SystemExit("evaluation instance refuses to start: " + "; ".join(bad))
    if a.action == "build":
        print(build(a.root))
        return 0
    from portal.modules.compliance.tools import compliance_mcp

    compliance_mcp.mcp.run(transport="streamable-http", host="0.0.0.0", port=a.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
