"""Probes for the memory layer: salience, dedup, entities, recall, recall floor.

Fixtures are authored (tests/data/embedding_consumers/memory_*.json, provenance inside); the
live memory tables are never touched — every probe works on in-memory scratch data.
"""

from __future__ import annotations

from typing import Any

from portal.platform.embedding.classifier import AnchorClassifier, AnchorSet, leakage
from portal.platform.embedding.contract import Role, Task

from ..framework import MEASURED, ProbeContext, ProbeResult, blocked, compare, fixture_digest, probe
from ._common import (
    auc_roc,
    best_f1,
    binary_prf,
    cos,
    historical_incumbent,
    load_fixture,
    overlap,
    retrieval_ab,
    threshold_sweep,
)

# anchors for salience: disjoint from memory_salience.json by construction (leakage-checked)
_DURABLE = [
    "I'm allergic to latex so please avoid suggesting it.",
    "My sister Elena lives in Portland and we talk every Sunday.",
    "I started a new job as a nurse last month.",
    "I'm lactose intolerant, so no dairy recipes.",
    "My husband's name is Marcus and he is an architect.",
    "I always use dark mode and large fonts because of my eyesight.",
    "We have a golden retriever called Honey.",
    "I'm preparing for the bar exam in July.",
    "I moved to Austin in March.",
    "I run a small bakery on weekends.",
    "I live with my parents and two younger brothers.",
    "I'm learning to play the cello.",
    "My son's birthday is on August 3rd.",
    "I don't eat pork for religious reasons.",
    "I work from home on Wednesdays and Fridays.",
    "I'm saving up for a wedding next autumn.",
    "I use Linux on my laptop and macOS on my desktop.",
    "My doctor said I have to avoid caffeine.",
    "I'm a left-handed person and bad at maths.",
    "I'm planning a trip to Peru in November.",
]
_EPHEMERAL = [
    "what's the capital of Peru",
    "please summarize the text above",
    "thanks that works",
    "can you make the font bigger in this snippet",
    "explain quicksort with an example",
    "write a limerick about cats",
    "how many days until Christmas",
    "what does this error mean",
    "continue",
    "translate that to Portuguese",
    "give me three title ideas",
    "I wonder how big the sun is",
    "let me think about it",
    "add a docstring to the function",
    "what is the square root of 144",
    "try again with fewer words",
    "I'm looking at the second option right now",
    "I guess that could work",
    "show the same thing in JavaScript",
    "who invented the telephone",
]


def _salient(text: str) -> bool:
    from portal.platform.inference.router.context_inject import _salient_user_text

    return _salient_user_text([{"role": "user", "content": text}], "__none__") is not None


@probe("memory_salience")
async def salience(ctx: ProbeContext) -> ProbeResult:
    rows = load_fixture("memory_salience.json")["rows"]
    texts = [r["text"] for r in rows]
    gold = [bool(r["durable"]) for r in rows]
    leaks = leakage(_DURABLE + _EPHEMERAL, texts)
    if leaks:
        return blocked("memory_salience", f"anchor leakage: {len(leaks)} rows")
    clf = await AnchorClassifier.build(
        AnchorSet(
            "salience",
            Task.CLASSIFICATION,
            256,
            {"durable": _DURABLE, "ephemeral": _EPHEMERAL},
            0,
            0,
            3,
        ),
        ctx.client,
    )
    vecs = await ctx.client.embed_texts(texts, task=Task.CLASSIFICATION, dim=256)
    scores = [clf.score_labels(v)["durable"] - clf.score_labels(v)["ephemeral"] for v in vecs]
    marker = [_salient(t) for t in texts]
    best = best_f1(scores, gold)
    # 2-fold: pick the threshold on one half, score the other (removes the optimism of best_f1)
    folds = []
    for a in (0, 1):
        tr = [i for i in range(len(rows)) if i % 2 == a]
        te = [i for i in range(len(rows)) if i % 2 != a]
        t = best_f1([scores[i] for i in tr], [gold[i] for i in tr])["threshold"]
        folds.append(binary_prf([scores[i] >= t for i in te], [gold[i] for i in te])["f1"])
    union = binary_prf(
        [m or s >= best["threshold"] for m, s in zip(marker, scores, strict=True)], gold
    )
    implicit = [i for i, r in enumerate(rows) if r["durable"] and not marker[i]]
    cand = {
        "primary": round(sum(folds) / 2, 4),
        "best_threshold_f1": best,
        "union_with_markers": union,
        "recall_on_implicit_facts": round(
            sum(scores[i] >= best["threshold"] for i in implicit) / len(implicit), 4
        )
        if implicit
        else None,
        "auc": auc_roc(
            [s for s, g in zip(scores, gold, strict=True) if g],
            [s for s, g in zip(scores, gold, strict=True) if not g],
        ),
    }
    inc = {
        "primary": binary_prf(marker, gold)["f1"],
        **binary_prf(marker, gold),
        "implicit_facts": len(implicit),
    }
    return ProbeResult(
        "memory_salience",
        MEASURED,
        inc,
        cand,
        compare(inc["primary"], cand["primary"]),
        fixture={"rows": len(rows), "durable": sum(gold), "sha": fixture_digest(rows)},
        identity=clf.version,
        notes=[
            "candidate primary = 2-fold cross-validated F1; markers kept as an OR in 'union_with_markers'"
        ],
    )


@probe("memory_dedup")
async def dedup(ctx: ProbeContext) -> ProbeResult:
    pairs = load_fixture("memory_dedup.json")["pairs"]
    a = await ctx.client.embed_texts(
        [p["a"] for p in pairs], task=Task.SENTENCE_SIMILARITY, dim=768
    )
    b = await ctx.client.embed_texts(
        [p["b"] for p in pairs], task=Task.SENTENCE_SIMILARITY, dim=768
    )
    sims = [cos(x, y) for x, y in zip(a, b, strict=True)]
    dup = [s for s, p in zip(sims, pairs, strict=True) if p["label"] == "duplicate"]
    non = [s for s, p in zip(sims, pairs, strict=True) if p["label"] != "duplicate"]
    rel = [s for s, p in zip(sims, pairs, strict=True) if p["label"] == "related"]
    n = len(non)
    sweep = {
        f"fp<={int(f * 100)}pct": threshold_sweep(dup, non, fp_budget=f) for f in (0.0, 0.02, 0.05)
    }
    hist = historical_incumbent("memory_dedup")
    cand = {
        "primary": sweep["fp<=2pct"]["recall"],
        "sweep": sweep,
        "auc_dup_vs_nondup": auc_roc(dup, non),
        "auc_dup_vs_related": auc_roc(dup, rel),
        "legacy_8917_at_fp<=2pct": hist["legacy_8917_at_fp<=2pct"],
        "legacy_8917_auc": hist["legacy_8917_auc"],
        "min_dup_sim": round(min(dup), 4),
        "max_related_sim": round(max(rel), 4),
        "false_merge_budget_pairs": round(0.02 * n, 2),
    }
    inc = {
        "primary": 0.0,
        "note": "no dedup exists today (memory_writeback_all's comment assumes one); every restatement is stored",
    }
    return ProbeResult(
        "memory_dedup",
        MEASURED,
        inc,
        cand,
        "BETTER" if cand["primary"] > 0.5 else "INCONCLUSIVE",
        fixture={"pairs": len(pairs), "sha": fixture_digest(pairs)},
        identity=await ctx.client.version_tag(768),
        notes=[
            "metric = duplicate suppression (recall) at <=2% false merges across related+unrelated pairs"
        ],
    )


def _norm_name(s: str) -> str:
    return " ".join(s.lower().split())


@probe("memory_entities")
async def entities(ctx: ProbeContext) -> ProbeResult:
    fx = load_fixture("memory_entities.json")
    al, ds = fx["aliases"], fx["distinct"]

    async def sim(pairs: list[dict[str, str]]) -> list[float]:
        x = await ctx.client.embed_texts(
            [p["a"] for p in pairs], task=Task.SENTENCE_SIMILARITY, dim=768
        )
        y = await ctx.client.embed_texts(
            [p["b"] for p in pairs], task=Task.SENTENCE_SIMILARITY, dim=768
        )
        return [cos(p, q) for p, q in zip(x, y, strict=True)]

    pos, neg = await sim(al), await sim(ds)
    inc_pos = [_norm_name(p["a"]) == _norm_name(p["b"]) for p in al]
    inc_neg = [_norm_name(p["a"]) == _norm_name(p["b"]) for p in ds]
    sweep = {
        f"fp<={int(f * 100)}pct": threshold_sweep(pos, neg, fp_budget=f) for f in (0.0, 0.05, 0.10)
    }
    s5 = sweep["fp<=5pct"]
    prec = (
        s5["recall"] * len(pos) / (s5["recall"] * len(pos) + s5["fp_rate"] * len(neg))
        if s5["recall"]
        else 0.0
    )
    cand = {
        "primary": s5["recall"],
        "sweep": sweep,
        "precision_at_fp5": round(prec, 4),
        "auc": auc_roc(pos, neg),
        "note": "candidates only: a merge needs the gated threshold; never auto-merge on this evidence alone",
    }
    inc = {"primary": round(sum(inc_pos) / len(pos), 4), "exact_name_false_merges": sum(inc_neg)}
    return ProbeResult(
        "memory_entities",
        MEASURED,
        inc,
        cand,
        compare(inc["primary"], cand["primary"]),
        fixture={"aliases": len(al), "distinct": len(ds), "sha": fixture_digest(fx)},
        identity=await ctx.client.version_tag(768),
        notes=[
            "alias recall at <=5% false merges; incumbent = exact normalized name equality (graph_memory._upsert_entity)"
        ],
    )


def _memory_fx() -> tuple[dict[str, str], list[dict[str, Any]]]:
    fx = load_fixture("memory_recall.json")
    return fx["memories"], fx["queries"]


@probe("memory_recall")
async def recall(ctx: ProbeContext) -> ProbeResult:
    mems, qs = _memory_fx()
    qs = [q for q in qs if q["gold"]]
    worst = max(overlap(q["query"], mems[q["gold"][0]]) for q in qs)
    res = await retrieval_ab(
        ctx,
        [q["query"] for q in qs],
        [q["gold"] for q in qs],
        list(mems),
        list(mems.values()),
    )
    # the :8917 arm is retired; its committed scorecard block is the incumbent
    inc = {k: v for k, v in historical_incumbent("memory_recall").items() if k != "provenance"}
    cand = res["candidate"]
    return ProbeResult(
        "memory_recall",
        MEASURED,
        {"primary": inc["recall@4"], **inc},
        {"primary": cand["recall@4"], **cand},
        compare(inc["recall@4"], cand["recall@4"]),
        fixture={
            "memories": len(mems),
            "queries": len(qs),
            "max_query_overlap": round(worst, 3),
            "sha": fixture_digest(qs),
        },
        identity=await ctx.client.version_tag(768),
        notes=[
            "incumbent = FIXED historical :8917 arm (reports/embedding_consumers/20261007T224205Z, "
            "service retired at the EG2 cutover); candidate = EG2 SEARCH 768d, live",
        ],
    )


@probe("memory_recall_floor")
async def recall_floor(ctx: ProbeContext) -> ProbeResult:
    mems, qs = _memory_fx()
    ids = list(mems)
    dv = await ctx.client.embed_texts(
        list(mems.values()), task=Task.SEARCH, role=Role.DOCUMENT, dim=768
    )
    qv = await ctx.client.embed_texts(
        [q["query"] for q in qs], task=Task.SEARCH, role=Role.QUERY, dim=768
    )
    ranked = [sorted(range(len(ids)), key=lambda j: -cos(v, dv[j])) for v in qv]
    sims = [[cos(v, dv[j]) for j in range(len(ids))] for v in qv]

    def evaluate(floor: float) -> dict[str, float]:
        inj = rel_inj = covered = need = tok = 0
        none_inj = 0
        for qi, q in enumerate(qs):
            picked = [ids[j] for j in ranked[qi][:4] if sims[qi][j] >= floor]
            inj += len(picked)
            tok += sum(len(mems[p].split()) for p in picked)
            gold = set(q["gold"])
            rel_inj += len(set(picked) & gold)
            if gold:
                need += 1
                covered += bool(set(picked) & gold)
            elif picked:
                none_inj += 1
        n_none = sum(1 for q in qs if not q["gold"])
        return {
            "precision": round(rel_inj / inj, 4) if inj else 0.0,
            "recall_any": round(covered / need, 4),
            "injected_per_turn": round(inj / len(qs), 2),
            "words_injected_per_turn": round(tok / len(qs), 1),
            "irrelevant_injection_rate_on_no_memory_turns": round(none_inj / n_none, 4),
        }

    inc = evaluate(-1.0)  # top-4 every turn, no floor
    sweep = {
        f"{f:.2f}": evaluate(f) for f in (0.2, 0.3, 0.4, 0.5, 0.6, 0.65, 0.7, 0.75, 0.8, 0.85, 0.9)
    }
    ok = [f for f, r in sweep.items() if r["recall_any"] >= inc["recall_any"] - 1e-9]
    best = max(ok, key=float) if ok else None
    cand = {
        "primary": sweep[best]["precision"] if best else 0.0,
        "chosen_floor": best,
        "at_chosen": sweep[best] if best else None,
        "sweep": sweep,
        "tokens_saved_pct": round(
            100 * (1 - sweep[best]["words_injected_per_turn"] / inc["words_injected_per_turn"]), 1
        )
        if best
        else 0.0,
    }
    return ProbeResult(
        "memory_recall_floor",
        MEASURED,
        {"primary": inc["precision"], **inc},
        cand,
        compare(inc["precision"], cand["primary"]),
        fixture={
            "turns": len(qs),
            "no_memory_turns": sum(1 for q in qs if not q["gold"]),
            "sha": fixture_digest(qs),
        },
        identity=await ctx.client.version_tag(768),
        notes=[
            "sweep extends past the 0.2-0.6 in the spec because EG2 SEARCH cosines for on-topic pairs sit at 0.6-0.9; floor = highest sweep value that keeps recall_any >= the incumbent's; decides whether AUTO_RAG_ENABLED can turn on"
        ],
    )
