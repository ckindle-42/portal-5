"""Probe: tool-schema preselection (consumer ``tool_preselect``).

Fixture: ``tests/toolpreselect/scenarios.json`` (the preselector's own labelled
scenarios: positives, compound, decoys). Candidate: rank the workspace tool
catalogue by EG2 SEARCH similarity between the user turn (query) and each
tool's ``name`` + description (document). The incumbent LLM preselector is
recorded from a prior ``tests/toolpreselect/run_bench.py`` JSONL when supplied
(``--opt toolpreselect_llm_results=PATH``); KNOWN_LIMITATIONS P5-TOOLPRESELECT-001
already records it as unable to rank, so the operative baseline is "no
preselection" (all schemas shipped). Preselection is viable only at
recall@k >= 0.95 — a ranker that hides a needed tool is worse than none.
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from portal.platform.embedding.contract import Role, Task

from ..framework import (
    MEASURED,
    REPO_ROOT,
    ProbeContext,
    ProbeResult,
    Stopwatch,
    fixture_digest,
    probe,
    recall_at_k,
    top_k_by_cosine,
)

SCENARIOS = REPO_ROOT / "tests" / "toolpreselect" / "scenarios.json"
VIABLE_RECALL = 0.95


@probe("tool_preselect")
async def run(ctx: ProbeContext) -> ProbeResult:
    data = json.loads(SCENARIOS.read_text())
    tools = data["tools"]
    scenarios = [s for s in data["scenarios"] if s.get("acceptable_tools")]
    dim = int(ctx.opt("tool_dim", 768))
    names = [t["name"] for t in tools]
    vecs = await ctx.client.embed_texts(
        [t.get("description", "") or t["name"] for t in tools],
        task=Task.SEARCH,
        role=Role.DOCUMENT,
        dim=dim,
        titles=names,
    )
    docs = dict(zip(names, vecs, strict=True))
    sw = Stopwatch()
    ranked: list[list[str]] = []
    for s in scenarios:
        with sw.time():
            [q] = await ctx.client.embed_texts(
                [s["user_turn"]], task=Task.SEARCH, role=Role.QUERY, dim=dim
            )
        ranked.append(top_k_by_cosine(q, docs, len(docs)))
    rel = [s["acceptable_tools"] for s in scenarios]
    ks = (1, 3, 5, 8, 12)
    overall = {f"recall@{k}": round(recall_at_k(ranked, rel, k), 4) for k in ks}
    by_cat: dict[str, dict[str, float]] = {}
    groups: dict[str, list[int]] = defaultdict(list)
    for i, s in enumerate(scenarios):
        groups[s.get("category", "?")].append(i)
    for cat, idx in sorted(groups.items()):
        by_cat[cat] = {
            f"recall@{k}": round(recall_at_k([ranked[i] for i in idx], [rel[i] for i in idx], k), 4)
            for k in (3, 5, 8)
        }
    smallest_viable = next((k for k in ks if overall[f"recall@{k}"] >= VIABLE_RECALL), None)
    incumbent: dict[str, Any] = {
        "primary": f"no preselection: all {len(names)} schemas every turn",
        "llm_preselector": "exhausted (KNOWN_LIMITATIONS P5-TOOLPRESELECT-001)",
    }
    llm = ctx.opt("toolpreselect_llm_results")
    if llm and Path(llm).is_file():
        incumbent["llm_run_bench_rows"] = sum(1 for _ in Path(llm).open())
    # the incumbent ships every schema (recall 1.0 by construction), so a recall gap is a schema-
    # budget tradeoff, not a regression: BETTER only when 0.95 recall fits k<=8, else undecided
    hint = "BETTER" if smallest_viable is not None and smallest_viable <= 8 else "INCONCLUSIVE"
    return ProbeResult(
        consumer="tool_preselect",
        status=MEASURED,
        incumbent=incumbent,
        candidate={
            "primary": overall.get("recall@5"),
            **overall,
            "by_category": by_cat,
            "smallest_k_at_recall_0.95": smallest_viable,
            "schema_reduction_at_that_k": (
                round(1 - smallest_viable / len(names), 3) if smallest_viable else None
            ),
            **sw.summary(),
        },
        hint=hint,
        fixture={"scenarios_sha": fixture_digest(data), "n": len(scenarios), "tools": len(names)},
        identity=await ctx.client.version_tag(dim),
        notes=[
            "preselect() keeps its fallback invariant: on any miss or abstain the full set ships"
        ],
    )
