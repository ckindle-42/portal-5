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

    out = Path(root) / "planted_staged"
    out.mkdir(parents=True, exist_ok=True)
    for f in sorted(PLANTED.glob("*.md")):
        text = re.sub(r"<!--\s*PLANT\s+\{.*?\}\s*-->\s*", "", f.read_text(), flags=re.S)
        (out / f.name).write_text(text)
    return out


def build(root: Path | str) -> dict[str, object]:
    """The evaluation store, from public, committed material only."""
    from portal.modules.compliance.core.cip_register import Register
    from portal.modules.compliance.core.ingest import ingest_folder
    from portal.modules.compliance.core.migrate_legacy import import_register
    from portal.modules.compliance.core.repository import Repository

    repo = Repository(os.environ["COMPLIANCE_DB_PATH"])
    repo.migrate()
    reg = import_register(repo, Register.load())
    corpus = asyncio.run(ingest_folder(str(_stage_planted(root)), "operator_corpus", True))
    return {"register": reg, "planted_corpus": corpus}


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
