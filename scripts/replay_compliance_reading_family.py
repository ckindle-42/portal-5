"""Replay the L-document family (10, 19, 20, 25) through the real reading module.

Live models, the real `read_and_judge`, the real governing text from the
register and the real candidate fixtures. Graded against each case's own
`expected` block — no expectation is edited, and duty count is deliberately not
graded (qwen38 read case 10 as two duties, granite as one; both are correct).
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, ".")

from portal.modules.compliance.core.cip_register import Register  # noqa: E402
from portal.modules.compliance.core.determination import (  # noqa: E402
    AssessmentContext,
    AssessmentRequest,
    CandidateRecord,
    CandidateSet,
    GoverningBundle,
    SourceSlice,
)
from portal.modules.compliance.core.reading import (  # noqa: E402
    _READING_BUDGET,
    read_and_judge,
)
from portal.modules.compliance.core.reading_transport import chat  # noqa: E402

SUITE = "tests/data/compliance_reading_acceptance.json"
OUT = (
    "/private/tmp/claude-501/-Users-chris-projects-portal-5/"
    "1b525fee-2da3-4c48-9fe7-350c7b5f0f78/scratchpad/replay_family.json"
)
MODELS = {
    "qwen38": "hf.co/unsloth/Qwen3.8-27B-GGUF:Q4_K_M-ctx32k",
    "granite": "granite4.1:30b-ctx16k",
    "mistral": "mistral-small3.2:24b-instruct-2506-q4_K_M",
}

LEAD_IN = (
    "Each Responsible Entity shall implement one or more documented process(es) that "
    "collectively include each of the applicable requirement parts in CIP-007-6 "
    "Table R2 - Security Patch Management."
)


def register_part(part: str):
    reg = Register.load()
    for node in reg.nodes:
        if node.standard == "CIP-007-6" and node.requirement == "R2" and (node.part or "") == part:
            return node
    raise SystemExit(f"no register node for Part {part}")


def build(case: dict, fixtures: dict) -> AssessmentRequest:
    part = case["requirement_id"].rsplit(" ", 1)[-1]
    node = register_part(part)
    gov = GoverningBundle(
        ref=case["requirement_id"],
        part_text=node.verbatim_text,
        lead_in=LEAD_IN,
        source_slices=[
            SourceSlice(
                slice_id="gov-part",
                ref=case["requirement_id"],
                document_id="cip-007-6.pdf",
                revision_hash="h",
                chunk_id="gov",
                text=node.verbatim_text,
                role="governing",
            ),
            SourceSlice(
                slice_id="gov-leadin",
                ref="CIP-007-6 R2",
                document_id="cip-007-6.pdf",
                revision_hash="h",
                chunk_id="lead",
                text=LEAD_IN,
                role="lead_in",
            ),
        ],
    )
    gov.measures = node.measure_text
    records = []
    for entry in case["candidates"]:
        label = entry["label"]
        text = fixtures[label]["text"]
        records.append(
            CandidateRecord(
                candidate_id=label,
                document_id=fixtures[label]["document_id"],
                chunk_id=fixtures[label]["chunk_id"],
                text=text,
                locator=fixtures[label]["section"],
                source_slice=SourceSlice(
                    slice_id=f"cand-{label}",
                    ref=fixtures[label]["section"],
                    document_id=fixtures[label]["document_id"],
                    revision_hash="h",
                    chunk_id=fixtures[label]["chunk_id"],
                    text=text,
                    role="candidate",
                ),
            )
        )
    # These cases declare boundary "complete", so the real pipeline supplies a
    # completed boundary receipt. Without one the OMISSION rule correctly voids
    # any absence claim — which would measure my harness, not the reading.
    from portal.modules.compliance.core.determination import CorpusSnapshot

    sections = [r.chunk_id for r in records]
    snapshot = CorpusSnapshot(
        snapshot_id="snap-fixture",
        kb_id="fixture",
        completeness="COMPLETE",
        fingerprint="fp-fixture",
    )
    candidate_set = CandidateSet(records=records)
    candidate_set.acquisition_receipt = {
        "boundary_receipt": {
            "complete": True,
            "acquisition_mode": "EXPLICIT_SET",
            "eligible_sections": sections,
            "examined_sections": sections,
            "document_revision_hashes": {r.chunk_id: "h" for r in records},
            "omissions": [],
        }
    }
    return AssessmentRequest(
        requirement_id="CIP-007-6 R2",
        governing=gov,
        snapshot=snapshot,
        candidate_set=candidate_set,
    )


def grade(case: dict, judgment) -> dict[str, bool]:
    exp = case["expected"]
    spec = case["report"]
    covering = {i for c in judgment.covered for i in c.internal_slice_ids}
    gap_counter = {i for g in judgment.gaps for i in g.internal_counterevidence_slice_ids}
    cited = covering | gap_counter
    want_cov = {f"cand-{e['internal'][0]}" for e in spec["covered"] if e.get("internal")}
    want_counter = {f"cand-{lbl}" for g in spec["gaps"] for lbl in (g.get("counter") or [])}
    return {
        "coverage": judgment.documentary_coverage == exp["documentary_coverage"],
        "gap_kinds": sorted({g.kind for g in judgment.gaps}) == sorted(set(exp["gap_kinds"])),
        "covered_cites": want_cov <= covering,
        "counter_cites": want_counter <= gap_counter,
        "required_citations": {f"cand-{c}" for c in exp["required_citations"]} <= cited,
        "citations_resolve": not any(d.unverified_citations for d in judgment.duties),
    }


def main() -> int:
    data = json.loads(Path(SUITE).read_text())
    cases = {c["id"]: c for c in data["cases"]}
    fixtures = data["controlled_fixtures"]
    ids = sys.argv[1].split(",") if len(sys.argv) > 1 else ["10", "19", "20", "25"]

    rows = []
    for cid in ids:
        case = cases[cid]
        request = build(case, fixtures)
        exp = case["expected"]
        print(
            f"\n=== case {cid}  {case['requirement_id']}  "
            f"expect {exp['documentary_coverage']} / {exp['gap_kinds']} ===",
            flush=True,
        )
        for name, model in MODELS.items():

            def transport(m: str, s: str, u: str, _model=model) -> str:
                return chat(_model, s, u, budget=_READING_BUDGET, fmt="json").content

            started = time.time()
            try:
                judgment = read_and_judge(
                    request,
                    AssessmentContext(seats=[{"id": "s", "label": "l", "model": model}]),
                    transport=transport,
                )
            except Exception as exc:  # noqa: BLE001
                print(f"  ERR  {name:<8} {exc!r}", flush=True)
                continue
            checks = grade(case, judgment)
            score = sum(checks.values())
            mark = "PASS" if score == len(checks) else "FAIL"
            print(
                f"  {mark} {name:<8} {time.time() - started:6.1f}s {score}/{len(checks)} "
                f"coverage={judgment.documentary_coverage} duties={len(judgment.duties)} "
                f"gaps={[g.kind for g in judgment.gaps]}",
                flush=True,
            )
            for key, ok in checks.items():
                if not ok:
                    print(f"           miss: {key}")
            for u in judgment.uncertainties:
                print(f"           unc[{u.code}]: {u.reason[:95]}")
            rows.append(
                {
                    "case": cid,
                    "model": name,
                    "score": score,
                    "of": len(checks),
                    "checks": checks,
                    "coverage": judgment.documentary_coverage,
                    "duties": [
                        {"statement": d.statement[:120], "finding": d.finding}
                        for d in judgment.duties
                    ],
                    "gaps": [
                        {"kind": g.kind, "counter": g.internal_counterevidence_slice_ids}
                        for g in judgment.gaps
                    ],
                    "elapsed": round(time.time() - started, 1),
                    "failure": judgment.failure,
                }
            )
            Path(OUT).write_text(json.dumps(rows, indent=2))
    print(f"\nwrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
