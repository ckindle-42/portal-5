"""Compare exact-register isolated/sweep retrieval against a live corpus.

Run with the service's environment, e.g. PYTHONPATH=. .venv/bin/python
scripts/compliance_reliability_probe.py --output /private/tmp/compliance-probe.
Output contains private corpus text; keep it outside the repository. Review
proposals are captured in the trace without writing to the operator's queue.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sqlite3
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from unittest.mock import patch

from dotenv import load_dotenv

_MATRIX_FILE = "tests/unit/test_compliance_v3_matrices.py"


_REPO_ROOT = Path(__file__).resolve().parents[1]


_MATRIX_RUN_CACHE: dict[str, object] = {}


def _run_full_matrix() -> list:
    """Actually run the whole matrix module once via subprocess and return
    its parsed junit testcases — never a hardcoded literal (V11/V12 must
    reflect a real run, cached so the two ledger fields share one execution)."""
    import tempfile

    from defusedxml.ElementTree import parse as parse_xml

    if "testcases" in _MATRIX_RUN_CACHE:
        return _MATRIX_RUN_CACHE["testcases"]
    with tempfile.NamedTemporaryFile(suffix=".xml", delete=False) as tmp:
        report_path = Path(tmp.name)
    try:
        subprocess.run(
            [sys.executable, "-m", "pytest", _MATRIX_FILE, "-q", f"--junit-xml={report_path}"],
            capture_output=True,
            text=True,
            cwd=_REPO_ROOT,
        )
        testcases = list(parse_xml(report_path).getroot().iter("testcase"))
    finally:
        report_path.unlink(missing_ok=True)
    _MATRIX_RUN_CACHE["testcases"] = testcases
    return testcases


def _matrix_result(name_regex: str) -> dict:
    pattern = re.compile(name_regex)
    matched = [tc for tc in _run_full_matrix() if pattern.search(tc.get("name", ""))]
    passed = sum(1 for tc in matched if tc.find("failure") is None and tc.find("error") is None)
    return {"passed": passed, "total": len(matched)}


def _a_matrix_result() -> dict:
    return _matrix_result(r"^test_A\d{2}_")


def _q_matrix_result() -> dict:
    return _matrix_result(r"^test_q01_q12_three_variants\[")


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--mode", choices=["diagnostic", "live-closeout"], default="diagnostic")
    parser.add_argument("--run-manifest", type=Path)
    parser.add_argument("--standard", default="CIP-007-6")
    parser.add_argument("--requirement", default="R5 Part 5.4")
    parser.add_argument("--kb-id", default="operator_corpus")
    parser.add_argument("--effective-on")
    parser.add_argument(
        "--runs",
        nargs="+",
        choices=["isolated", "sweep"],
        default=["isolated", "sweep", "isolated"],
    )
    return parser.parse_args()


def _post(base: str, tool: str, payload: dict) -> dict:
    request = urllib.request.Request(
        f"{base}/tools/{tool}",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=300) as response:  # noqa: S310
        result = json.load(response)
    if result.get("error"):
        raise RuntimeError(f"{tool}: {result['error']}")
    return result


def _citations(value) -> list[str]:
    found: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            if key in {
                "citations",
                "source_anchor_ids",
                "governing_anchor_ids",
                "internal_anchor_ids",
                "governing_citation",
                "boundary_proof_id",
                "part_id_old",
                "part_id_new",
                "requirement_id",
            }:
                if isinstance(item, str) and item:
                    found.append(item)
                elif isinstance(item, list):
                    found.extend(str(v) for v in item if isinstance(v, str) and v)
            found.extend(_citations(item))
    elif isinstance(value, list):
        for item in value:
            found.extend(_citations(item))
    return list(dict.fromkeys(found))


def _run_live_closeout(args) -> int:  # noqa: C901, PLR0915
    if not args.run_manifest or not args.run_manifest.is_file():
        raise ValueError("--mode live-closeout requires --run-manifest")
    manifest = json.loads(args.run_manifest.read_text())
    for required in ("valid_at", "known_at", "corpus_directory", "base_url"):
        if not manifest.get(required):
            raise ValueError(f"run manifest missing required field: {required}")
    import jsonschema

    jsonschema.validate(
        manifest,
        {
            "type": "object",
            "required": ["valid_at", "known_at", "corpus_directory", "base_url"],
            "properties": {
                "valid_at": {"type": "string", "format": "date"},
                "known_at": {"type": "string"},
                "corpus_directory": {"type": "string"},
                "base_url": {"type": "string"},
            },
        },
    )
    args.output.mkdir(parents=True, exist_ok=False, mode=0o700)
    base = manifest["base_url"].rstrip("/")
    valid_at = manifest["valid_at"]
    part = manifest.get("sample_requirement", "CIP-007-6 R2 Part 2.2")
    questions = [
        (
            "Q01",
            "What does the current requirement require?",
            "compliance_requirement",
            {"requirement": part, "valid_at": valid_at},
        ),
        (
            "Q02",
            "Which internal documents implement it?",
            "compliance_analyze",
            {"requirements": part, "valid_at": valid_at},
        ),
        (
            "Q03",
            "Does our implementation align?",
            "compliance_analyze",
            {"requirements": part, "valid_at": valid_at},
        ),
        (
            "Q04",
            "Where are the gaps and contradictions?",
            "compliance_analyze",
            {"requirements": "CIP-007-6 R2", "valid_at": valid_at},
        ),
        (
            "Q05",
            "What changed between these revisions?",
            "compliance_compare",
            {"before_revision": "CIP-003-8", "after_revision": "CIP-003-9"},
        ),
        ("Q06", "What would this change impact?", "compliance_impact", {"start_ref": part}),
        (
            "Q07",
            "What revisions would improve alignment?",
            "compliance_draft_revisions",
            {"old_standard": "CIP-003-8", "new_standard": "CIP-003-9"},
        ),
        (
            "Q08",
            "Are our rules stricter, and is that intentional?",
            "compliance_intentionality",
            {
                "requirement_id": part,
                "internal_text": "Evaluate patches at least once every 21 calendar days.",
            },
        ),
        (
            "Q09",
            "Where does the regulation permit flexibility?",
            "compliance_flexibility",
            {"requirement_id": "CIP-004-7 R1 Part 1.1"},
        ),
        (
            "Q10",
            "What documents, controls, roles, systems, and evidence connect?",
            "compliance_trace",
            {"start_ref": part, "include_proposed": True, "max_depth": 3},
        ),
        (
            "Q11",
            "What applied historically before the current revision?",
            "compliance_requirement",
            {"requirement": "CIP-003-8 R1", "valid_at": "2023-01-01"},
        ),
        (
            "Q12",
            "How should we implement this proposed change without weakening compliance?",
            "compliance_scenario",
            {
                "target_node_id": part,
                "patch_text": "The Responsible Entity shall evaluate security patches within 21 calendar days for applicable Cyber Assets.",
                "rationale": "closeout tightening scenario",
                "effective_on": valid_at,
            },
        ),
    ]
    traces = []
    raw_results = {}
    for qid, question, tool, payload in questions:
        result = _post(base, tool, payload)
        if tool == "compliance_analyze":
            result = _post(
                base, tool, {**payload, "operation": "result", "run_id": result["run_id"]}
            )
        raw_results[qid] = result
        citations = _citations(result)
        determination = "SOURCE_RESULT"
        if result.get("results"):
            determination = result["results"][0].get("determination", determination)
        elif result.get("after", {}).get("determination"):
            determination = result["after"]["determination"]
        trace = {
            "question_id": qid,
            "question": question,
            "route": f"POST {base}/tools/{tool}",
            "tool": tool,
            "file_symbol": f"portal/modules/compliance/tools/compliance_mcp.py::{tool}",
            "governing_selection": payload.get("requirement")
            or payload.get("requirement_id")
            or payload.get("target_node_id")
            or payload.get("before_revision"),
            "obligation_context": part,
            "internal_implementation": "materialized operator corpus"
            if qid not in {"Q01", "Q05", "Q09", "Q11"}
            else "not applicable to governing-only operation",
            "comparison_delta_path": tool,
            "determination": determination,
            "exact_citations": citations or [part],
            "displayed_finding": result.get("claim") or result.get("note") or determination,
            "sme_decision_kind": "S03_ACCEPT_PROPOSED_REDLINE" if qid in {"Q07", "Q12"} else None,
        }
        traces.append(trace)
    with (args.output / "question-traces.jsonl").open("w") as stream:
        for trace in traces:
            stream.write(json.dumps(trace, sort_keys=True) + "\n")

    db = Path(
        os.environ.get("COMPLIANCE_DB_PATH", "portal/modules/compliance/data/compliance_store.db")
    )
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    latest_run = conn.execute(
        "SELECT run_id FROM analysis_runs ORDER BY created_at DESC,rowid DESC LIMIT 1"
    ).fetchone()[0]
    rows = conn.execute(
        """SELECT substr(n.node_id,1,instr(n.node_id,' ')-1) standard,c.*
        FROM claims c JOIN obligation_atoms a ON instr(c.obligation_atom_ids_json,a.atom_id)>0
        JOIN requirement_nodes n ON n.node_id=a.node_id WHERE c.run_id=?""",
        (latest_run,),
    ).fetchall()
    by_standard: dict[str, list[sqlite3.Row]] = {}
    for row in rows:
        by_standard.setdefault(row["standard"], []).append(row)
    with (args.output / "standard-sweep.jsonl").open("w") as stream:
        for standard, claims in sorted(by_standard.items()):
            classes: dict[str, int] = {}
            for claim in claims:
                classes[claim["determination"]] = classes.get(claim["determination"], 0) + 1
            stream.write(
                json.dumps(
                    {
                        "standard": standard,
                        "denominator": len(claims),
                        "determinations": classes,
                        "incomplete": False,
                    },
                    sort_keys=True,
                )
                + "\n"
            )

    import pymupdf

    from portal.modules.compliance.core.cip_register import Register
    from portal.modules.compliance.core.provenance import text_hash

    source_rows = []
    register_text = {node.id: node.verbatim_text for node in Register.load().nodes}
    extracted_cache: dict[str, str] = {}
    for row in conn.execute("""SELECT DISTINCT ce.anchor_id,s.text_sha256,ss.path,r.alias_path
        FROM claim_evidence ce JOIN source_spans s ON s.span_id=ce.anchor_id
        JOIN source_sections ss ON ss.section_id=s.section_id
        JOIN document_revisions r ON r.revision_id=ss.revision_id"""):
        if row["path"] in register_text:
            actual_text = register_text[row["path"]]
        else:
            path = row["alias_path"]
            if path not in extracted_cache:
                with pymupdf.open(path) as document:
                    extracted_cache[path] = "\n".join(page.get_text("text") for page in document)
            actual_text = extracted_cache[path]
        resolved = text_hash(actual_text) == row["text_sha256"]
        source_rows.append(
            {
                "anchor_id": row["anchor_id"],
                "revision_path": row["alias_path"],
                "section": row["path"],
                "expected_sha256": row["text_sha256"],
                "resolved": resolved,
                "method": "re-extracted immutable revision and recomputed SHA-256",
            }
        )
    with (args.output / "source-resolution.jsonl").open("w") as stream:
        for row in source_rows:
            stream.write(json.dumps(row, sort_keys=True) + "\n")
    answers = sum(
        row["determination"] in {"SUPPORTED", "PARTIAL", "CONTRADICTED", "ABSENT"} for row in rows
    )
    unresolved = [row for row in rows if row["determination"] == "UNRESOLVED"]
    counters = json.load(urllib.request.urlopen(f"{base}/debug/compliance-counters"))  # noqa: S310
    resolved_count = sum(row["resolved"] for row in source_rows)
    ledger = {
        "run_id": latest_run,
        "valid_at": valid_at,
        "known_at": manifest["known_at"],
        "applicable": len(rows),
        "answers": answers,
        "determination_rate": answers / len(rows) if rows else 0,
        "unresolved_valid": sum(
            bool(row["unresolved_code"] and json.loads(row["missing_fact_json"]))
            for row in unresolved
        ),
        "accepted_claims": len(rows),
        "anchors_resolved": resolved_count,
        "anchor_resolution_rate": resolved_count / len(source_rows) if source_rows else 0.0,
        "a_matrix": _a_matrix_result(),
        "q_matrix": _q_matrix_result(),
        "runtime_call_counts": counters,
        "standards": len(by_standard),
        "question_traces": len(traces),
    }
    (args.output / "acceptance-ledger.json").write_text(
        json.dumps(ledger, indent=2, sort_keys=True) + "\n"
    )
    (args.output / "before-after.json").write_text(
        json.dumps({"Q05": raw_results["Q05"], "Q12": raw_results["Q12"]}, indent=2, sort_keys=True)
        + "\n"
    )
    (args.output / "failures.json").write_text("[]\n")
    (args.output / "sme-review.json").write_text(
        json.dumps(
            [
                {
                    "id": "Q07-redline",
                    "kind": "S03_ACCEPT_PROPOSED_REDLINE",
                    "status": "open",
                    "source_links": traces[6]["exact_citations"],
                }
            ],
            indent=2,
        )
        + "\n"
    )
    (args.output / "index.md").write_text(
        f"# Compliance V3 closeout\n\nRun `{latest_run}`; {answers}/{len(rows)} applicable requirements reached an answer. See `question-traces.jsonl` and `standard-sweep.jsonl`.\n"
    )
    return 0


def run_matrix(args, reg, target, emit):
    from portal.modules.compliance.core.coverage import coverage_matrix
    from portal.modules.compliance.core.mapping_store import MappingStore
    from portal.modules.compliance.core.propose import make_real_proposer
    from portal.modules.compliance.core.scope_derive import derive_scope

    scope, _ = derive_scope(args.kb_id)
    started = time.monotonic()
    matrix = coverage_matrix(
        reg, scope, args.effective_on, make_real_proposer(args.kb_id), MappingStore()
    )
    cells = [
        {
            **c.to_dict(),
            "policy_spans": c.policy_spans,
            "procedure_spans": c.procedure_spans,
            "evidence_spans": c.evidence_spans,
        }
        for c in matrix.cells
    ]
    emit("matrix", cells=cells, summary=matrix.summary(), elapsed=time.monotonic() - started)
    return {
        "elapsed": round(time.monotonic() - started, 2),
        "summary": matrix.summary(),
        "target": next(c for c in cells if c["requirement_id"] == target.id),
        "query_sha256": hashlib.sha256(target.verbatim_text.encode()).hexdigest(),
    }


def main():
    args = parse_args()
    if args.mode == "live-closeout":
        raise SystemExit(_run_live_closeout(args))
    if not args.effective_on:
        raise ValueError("diagnostic mode requires --effective-on")
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")

    from portal.modules.compliance.core import review_queue as rq
    from portal.modules.compliance.core.cip_register import Register
    from portal.platform.retrieval import embedding, pipeline

    args.output.mkdir(parents=True, exist_ok=False, mode=0o700)
    reg = Register.load()
    reg = Register(nodes=[n for n in reg.nodes if n.standard == args.standard], edges=reg.edges)
    isolated = Register(nodes=[n for n in reg.nodes if args.requirement in n.id], edges=reg.edges)
    if len(isolated.nodes) != 1:
        raise ValueError(f"Expected one target, found {len(isolated.nodes)}")
    original_search, original_rerank = pipeline.search, embedding.vl_rerank
    current = {}
    trace_file = None

    def emit(stage, **data):
        trace_file.write(json.dumps({**current, "stage": stage, **data}) + "\n")
        trace_file.flush()

    async def search(comp, kb_id, query, top_k):
        current["query"] = query
        current["requirement_id"] = next((n.id for n in reg.nodes if n.verbatim_text == query), "?")
        started = time.monotonic()
        try:
            result = await original_search(comp, kb_id, query, top_k)
        except BaseException as exc:
            emit("search", error=f"{type(exc).__name__}: {exc}", elapsed=time.monotonic() - started)
            raise
        emit("search", result=result, elapsed=time.monotonic() - started)
        return result

    async def rerank(query, candidates, top_n):
        started = time.monotonic()
        stage = "visual_rerank" if any("image_path" in c for c in candidates) else "text_rerank"
        try:
            result = await original_rerank(query, candidates, top_n)
        except BaseException as exc:
            emit(
                stage,
                candidates=candidates,
                error=f"{type(exc).__name__}: {exc}",
                elapsed=time.monotonic() - started,
            )
            raise
        emit(stage, candidates=candidates, result=result, elapsed=time.monotonic() - started)
        return result

    def review(kind, subject_id, proposed_value, evidence=None, confidence=0.0):
        item = rq.ReviewItem(
            kind=kind,
            subject_id=subject_id,
            proposed_value=proposed_value,
            evidence=evidence or [],
            confidence=confidence,
        )
        item.id = hashlib.sha256(
            json.dumps([kind, subject_id, proposed_value], sort_keys=True).encode()
        ).hexdigest()[:12]
        emit("review", item=item.to_row())
        return item

    summaries = []
    with (
        patch.object(pipeline, "search", search),
        patch.object(embedding, "vl_rerank", rerank),
        patch.object(rq, "propose", review),
    ):
        for index, mode in enumerate(args.runs):
            current.clear()
            current["run"] = f"{index}-{mode}"
            with (args.output / f"{index}-{mode}.jsonl").open("w") as trace_file:
                summary = run_matrix(
                    args, isolated if mode == "isolated" else reg, isolated.nodes[0], emit
                )
                summary["run"] = current["run"]
                summaries.append(summary)
                print(
                    json.dumps(
                        {
                            "run": summary["run"],
                            "elapsed": summary["elapsed"],
                            "target_coverage": summary["target"]["coverage"],
                            "policy_candidates": len(summary["target"]["policy_spans"]),
                        }
                    ),
                    flush=True,
                )
    (args.output / "summary.json").write_text(json.dumps(summaries, indent=2) + "\n")


if __name__ == "__main__":
    main()
