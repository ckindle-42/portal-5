"""Probe: workspace auto-routing (consumer ``router``).

Incumbent: the production keyword layer (``routing._detect_workspace``) offline,
plus the LLM layer's accuracy from a ``bench_router.py`` results file for the
production router model (``--opt router_llm_results=PATH``). Candidate: an
EG2 anchor classifier (CLASSIFICATION task) whose anchors come from
``config/routing_descriptions.json``, ``config/routing_examples.json`` and the
UAT catalog prompts — never from the golden set (leakage is checked and
invalidates the run). Comparison is at the BASE workspace level: the LLM layer
emits base ids, variants are a separate keyword-layer concern.
"""

from __future__ import annotations

import glob
import json
from pathlib import Path
from typing import Any

from portal.platform.embedding.classifier import AnchorClassifier, AnchorSet, leakage
from portal.platform.embedding.contract import Task

from ..framework import (
    MEASURED,
    REPO_ROOT,
    ProbeContext,
    ProbeResult,
    Stopwatch,
    accuracy,
    blocked,
    compare,
    fixture_digest,
    macro_f1,
    probe,
)

GOLDEN = REPO_ROOT / "tests" / "data" / "bench_router_golden_set.json"
FALLBACK = "auto"


def base(ws: str | None) -> str:
    return (ws or FALLBACK).split("::", 1)[0]


def load_golden() -> list[tuple[str, str, str]]:
    rows = json.loads(GOLDEN.read_text())
    return [(r[0], base(r[1]), r[2]) for r in rows]


def build_labels(label_space: set[str]) -> dict[str, list[str]]:
    labels: dict[str, list[str]] = {lab: [] for lab in label_space if lab != FALLBACK}
    desc = json.loads((REPO_ROOT / "config" / "routing_descriptions.json").read_text())
    for ws, text in desc.items():
        if not ws.startswith("_") and base(ws) in labels and isinstance(text, str):
            labels[base(ws)].append(text)
    ex = json.loads((REPO_ROOT / "config" / "routing_examples.json").read_text())
    for e in ex.get("examples", []) if isinstance(ex, dict) else ex:
        # harmful-posture examples are routed to the standard lane BECAUSE they
        # are harmful; they belong to the harmful_intent anchors, not the topic.
        if (
            isinstance(e, dict)
            and e.get("posture", "standard") != "harmful"
            and base(e.get("workspace")) in labels
        ):
            labels[base(e["workspace"])].append(str(e["message"]))
    for f in sorted(glob.glob(str(REPO_ROOT / "tests" / "data" / "uat_catalog_g_*.json"))):
        for rec in json.loads(Path(f).read_text()):
            slug = base(rec.get("model_slug"))
            if slug in labels and rec.get("prompt"):
                labels[slug].append(str(rec["prompt"])[:1000])
    return labels


def keyword_route(message: str) -> str:
    from portal.platform.inference.router.routing import _detect_workspace

    return base(_detect_workspace([{"role": "user", "content": message}]))


@probe("router")
async def run(ctx: ProbeContext) -> ProbeResult:
    golden = load_golden()
    label_space = {g for _, g, _ in golden}
    labels = build_labels(label_space)
    empty = sorted(k for k, v in labels.items() if not v)
    leaks = leakage([t for v in labels.values() for t in v], [m for m, _, _ in golden])
    fixture = {
        "golden_sha": fixture_digest(golden),
        "n": len(golden),
        "labels_without_anchors": empty,
    }
    if leaks:
        return blocked(
            "router",
            f"anchor leakage: {len(leaks)} golden messages present in anchors",
            fixture=fixture,
        )
    retired = sorted(g for g in label_space if g != FALLBACK and g not in _live_workspace_ids())
    if retired:
        return blocked(
            "router",
            f"golden set names retired workspace ids {retired} — canonicalize (Phase 1 F-ROUTER-GOLDEN)",
            fixture=fixture,
        )

    gold = [g for _, g, _ in golden]
    sw_kw = Stopwatch()
    kw_pred = []
    for m, _, _ in golden:
        with sw_kw.time():
            kw_pred.append(keyword_route(m))
    incumbent: dict[str, Any] = {
        "keyword_accuracy": round(accuracy(kw_pred, gold), 4),
        "keyword_macro_f1": round(macro_f1(kw_pred, gold), 4),
        **{f"keyword_{k}": v for k, v in sw_kw.summary().items()},
    }
    llm_path = ctx.opt("router_llm_results")
    if llm_path and Path(llm_path).is_file():
        incumbent["llm_bench_router"] = _llm_summary(Path(llm_path))
    incumbent["primary"] = incumbent.get("llm_bench_router", {}).get(
        "accuracy", incumbent["keyword_accuracy"]
    )

    dim = int(ctx.opt("router_dim", 256))
    sweep: dict[str, Any] = {}
    best: tuple[float, dict[str, Any]] = (-1.0, {})
    for margin in (0.0, 0.01, 0.02, 0.04):
        aset = AnchorSet(
            "router",
            Task.CLASSIFICATION,
            dim,
            {k: v for k, v in labels.items() if v},
            0.0,
            margin,
            3,
        )
        clf = await AnchorClassifier.build(aset, ctx.client)
        sw = Stopwatch()
        pred, chain = [], []
        for m, _, _ in golden:
            with sw.time():
                d = await clf.classify_text(m, ctx.client)
            p = d.label or FALLBACK
            pred.append(p)
            chain.append(p if d.label else keyword_route(m))  # abstain -> existing keyword layer
        row = {
            "accuracy": round(accuracy(pred, gold), 4),
            "chain_accuracy_eg2_then_keywords": round(accuracy(chain, gold), 4),
            "macro_f1": round(macro_f1(pred, gold), 4),
            "abstain_rate": round(sum(p == FALLBACK for p in pred) / len(pred), 4),
            **sw.summary(),
        }
        sweep[f"margin={margin}"] = row
        if row["chain_accuracy_eg2_then_keywords"] > best[0]:
            best = (row["chain_accuracy_eg2_then_keywords"], {"margin": margin, **row})
    candidate = {
        "primary": best[0],
        "best": best[1],
        "sweep": sweep,
        "dim": dim,
        "version": clf.version,
    }
    return ProbeResult(
        consumer="router",
        status=MEASURED,
        incumbent=incumbent,
        candidate=candidate,
        hint=compare(float(incumbent["primary"]), float(best[0])),
        fixture=fixture,
        identity=clf.version,
        notes=[
            "candidate needs no resident LLM (incumbent pins the router model with keep_alive=-1)",
            *([f"labels with no anchors (cannot be predicted): {empty}"] if empty else []),
        ],
    )


def _live_workspace_ids() -> set[str]:
    import yaml

    cfg = yaml.safe_load((REPO_ROOT / "config" / "portal.yaml").read_text())
    ws = cfg["workspaces"]
    ids = ws.keys() if isinstance(ws, dict) else [w.get("id") for w in ws]
    return {str(i) for i in ids}


def _llm_summary(path: Path) -> dict[str, Any]:
    """Best-effort read of a bench_router.py results JSON (production model row)."""
    data = json.loads(path.read_text())
    models = data.get("models") or {}
    if not models:
        return {"error": f"no 'models' in {path}"}
    model, body = next(iter(models.items()))
    stats = body.get("stats") or {}
    return {
        "model": model,
        **{k: stats.get(k) for k in ("accuracy", "security_accuracy", "p50_ms", "p95_ms")},
    }
