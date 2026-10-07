"""Probe: harmful-intent gate (consumer ``harmful_intent``).

Incumbent: ``routing.detect_harmful_intent`` (121-keyword weighted substring gate), called for real.
Candidate: EG2 CLASSIFICATION anchors (harmful vs standard, kNN mean-of-top-3), alone and UNIONED
with the keyword gate. Metric: recall on harmful asks at the incumbent's false-positive rate on
benign-SECURITY asks (authorized pentest/redteam must keep going to the abliterated lanes);
paraphrase recall (zero keyword hits) is reported separately — the gap substring cannot close.
"""

from __future__ import annotations

import json
from typing import Any

from portal.platform.embedding.classifier import AnchorClassifier, AnchorSet, leakage
from portal.platform.embedding.contract import Task

from ..framework import (
    MEASURED,
    REPO_ROOT,
    ProbeContext,
    ProbeResult,
    blocked,
    compare,
    fixture_digest,
    probe,
)
from ._common import load_fixture, threshold_sweep

ANCHORS = "harmful_intent_anchors.json"


def _gate(text: str) -> bool:
    from portal.platform.inference.router.routing import detect_harmful_intent

    return detect_harmful_intent([{"role": "user", "content": text}])


@probe("harmful_intent")
async def run(ctx: ProbeContext) -> ProbeResult:
    fx = load_fixture("harmful_intent.json")
    rows = fx["rows"]
    anchors = load_fixture(ANCHORS)["labels"]
    extra = [
        e["message"]
        for e in json.loads((REPO_ROOT / "config" / "routing_examples.json").read_text()).get(
            "examples", []
        )
        if e.get("posture") == "harmful"
    ]
    eval_texts = [r["text"] for r in rows] + extra
    leaks = leakage([t for v in anchors.values() for t in v], eval_texts)
    if leaks:
        return blocked("harmful_intent", f"anchor leakage: {len(leaks)} eval texts in anchors")
    clf = await AnchorClassifier.build(
        AnchorSet("harmful", Task.CLASSIFICATION, 256, anchors, 0.0, 0.0, 3), ctx.client
    )

    async def score(texts: list[str]) -> list[float]:
        vecs = await ctx.client.embed_texts(texts, task=Task.CLASSIFICATION, dim=256)
        out = []
        for v in vecs:
            s = clf.score_labels(v)
            out.append(s["harmful"] - s["standard"])
        return out

    scores = await score(eval_texts)
    for r, s in zip(rows, scores[: len(rows)], strict=True):
        r["score"] = s
    harmful = [r for r in rows if r["label"] == "harmful"]
    para = [r for r in harmful if r["kind"] == "paraphrase"]
    direct = [r for r in harmful if r["kind"] == "direct"]
    bsec = [r for r in rows if r["kind"] == "benign_security"]
    bgen = [r for r in rows if r["kind"] == "benign_general"]
    extra_scores = scores[len(rows) :]

    def rate(sel: list[dict[str, Any]]) -> float:
        return round(sum(r["gate_hit"] is True for r in sel) / len(sel), 4)

    for r in rows:
        r["gate_hit"] = _gate(r["text"])
    inc_fp = rate(bsec)
    inc = {
        "primary": rate(harmful),
        "recall_all": rate(harmful),
        "recall_direct": rate(direct),
        "recall_paraphrase": rate(para),
        "fp_benign_security": inc_fp,
        "fp_benign_general": rate(bgen),
        "extra_positives_hit": sum(_gate(t) for t in extra),
        "llm_posture": "not measured: needs the abliterated router model on the request path (rule 10 keeps it resident); counted as incumbent cost in the router row",
    }
    pos_all = [r["score"] for r in harmful]
    neg = [r["score"] for r in bsec]
    cand: dict[str, Any] = {}
    for label, budget in (
        ("fp0", 0.0),
        ("fp<=incumbent", inc_fp),
        ("fp<=5pct", 0.05),
        ("fp<=10pct", 0.10),
    ):
        sw = threshold_sweep(pos_all, neg, fp_budget=budget)
        t = sw["threshold"]

        def eg2(sel: list[dict[str, Any]], t: float = t) -> float:
            return sum(r["score"] >= t for r in sel) / len(sel)

        def union(sel: list[dict[str, Any]], t: float = t) -> float:
            return sum(r["score"] >= t or r["gate_hit"] for r in sel) / len(sel)

        union_fp = sum(r["score"] >= t or r["gate_hit"] for r in bsec) / len(bsec)
        cand[label] = {
            "threshold": t,
            "eg2_recall": sw["recall"],
            "eg2_recall_paraphrase": round(eg2(para), 4),
            "union_recall": round(union(harmful), 4),
            "union_recall_paraphrase": round(union(para), 4),
            "union_fp_benign_security": round(union_fp, 4),
            "fp_benign_general": round(sum(r["score"] >= t for r in bgen) / len(bgen), 4),
            "extra_positives_hit": sum(s >= t for s in extra_scores),
        }
    key = "fp<=incumbent" if inc_fp > 0 else "fp0"
    cand["primary"] = cand[key]["union_recall"]
    return ProbeResult(
        consumer="harmful_intent",
        status=MEASURED,
        incumbent=inc,
        candidate=cand,
        hint=compare(inc["primary"], cand["primary"]),
        fixture={
            "rows": len(rows),
            "sha": fixture_digest(fx),
            "anchors": {k: len(v) for k, v in anchors.items()},
        },
        identity=clf.version,
        notes=[
            "FP budget is the incumbent's FP rate on benign-security asks (0 when it flags none); union = EG2 OR keyword gate",
            "threshold chosen on the eval set (optimistic); anchors are disjoint from it (leakage-checked)",
        ],
    )
