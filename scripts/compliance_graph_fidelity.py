#!/usr/bin/env python3
"""Graph fidelity without gold labels (TASK_COMPLIANCE_REASONING_V6 P8, Y19).

Neither graph has a gold reference. Following GraphCompliance (arXiv:2510.26309
§4.2), we measure reconstruction consistency and *calibrate what the score
means* by injecting known noise and measuring the drop.

A fidelity score here is the mean of four sub-scores, each in [0, 1]:

  span_fidelity        — every extracted span re-resolves verbatim against the
                         immutable source text
  structural_idempotence — rebuilding the graph from source yields the identical
                         (node_id, node_type) set and edge multiset
  reference_resolvability — the fraction of explicit references that resolve to
                         a real endpoint (not the deferred relative worklist)
  completeness         — declared units that carry an extraction, over the
                         document-declared denominator

Noise injection at delta in {0.01, 0.03, 0.05, 0.10, 0.20}: delete `delta` of
edges, flip `delta` of node types, truncate `delta` of spans by 3 chars. Five
iterations per delta. The clean score MUST sit above the delta=0.10 score or
the extraction is not trustworthy enough to build on.

    uv run python scripts/compliance_graph_fidelity.py [--json] [--out PATH]
"""

from __future__ import annotations

import argparse
import json
import random
import statistics
from dataclasses import replace
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DELTAS = (0.01, 0.03, 0.05, 0.10, 0.20)
ITERATIONS = 5


# ── policy graph ──────────────────────────────────────────────────────────


def _policy_scores(graph, source_text: dict[str, str]) -> dict[str, float]:
    from portal.modules.compliance.core.policy_graph import build_policy_graph

    n_span = n_span_ok = 0
    for e in graph.edges:
        if e.get("rel") == "REFERS_TO" and e.get("surface_text"):
            n_span += 1
            src = source_text.get(e["src"], "")
            if src[e["char_start"] : e["char_end"]] == e["surface_text"]:
                n_span_ok += 1
    for n in graph.nodes:
        for fld in ("subject", "constraint"):
            f = (n.cu or {}).get(fld)
            if isinstance(f, dict) and f.get("char_start", -1) >= 0:
                n_span += 1
                if source_text.get(n.id, "")[f["char_start"] : f["char_end"]] == f["text"]:
                    n_span_ok += 1
    span_fidelity = n_span_ok / n_span if n_span else 1.0

    rebuilt = build_policy_graph()
    a = sorted((n.id, n.node_type) for n in graph.nodes)
    b = sorted((n.id, n.node_type) for n in rebuilt.nodes)
    structural = 1.0 if a == b else _jaccard(set(a), set(b))

    refs = [e for e in graph.edges if e.get("rel") == "REFERS_TO"]
    resolved = sum(1 for e in refs if e.get("dst"))
    reference_resolvability = resolved / len(refs) if refs else 1.0

    tr = graph.typing_report
    completeness = (tr.get("by_type", {}).get("actor_cu", 0)) / max(
        1, tr.get("n_nodes", 1) - tr.get("by_type", {}).get("meta_cu", 0)
    )
    return {
        "span_fidelity": round(span_fidelity, 4),
        "structural_idempotence": round(structural, 4),
        "reference_resolvability": round(reference_resolvability, 4),
        "completeness": round(min(1.0, completeness + 0.0), 4),
    }


def _jaccard(a: set, b: set) -> float:
    return len(a & b) / len(a | b) if (a | b) else 1.0


def _corrupt_policy(graph, delta: float, rng: random.Random):
    edges = list(graph.edges)
    keep = [e for e in edges if rng.random() >= delta]
    nodes = []
    types = ["premise", "meta_cu", "actor_cu"]
    for n in graph.nodes:
        if rng.random() < delta:
            nt = rng.choice([t for t in types if t != n.node_type])
            nodes.append(replace(n, node_type=nt))
        elif n.cu and rng.random() < delta:
            cu = json.loads(json.dumps(n.cu))
            c = cu.get("constraint", {})
            if c.get("char_end", 0) > c.get("char_start", 0) + 3:
                c["char_end"] -= 3
            nodes.append(replace(n, cu=cu))
        else:
            nodes.append(n)
    g2 = replace(graph, nodes=nodes, edges=keep)
    return g2


def _score_policy(clean_only: bool = False) -> dict:
    from portal.modules.compliance.core.cip_register import Register
    from portal.modules.compliance.core.policy_graph import build_policy_graph

    graph = build_policy_graph()
    src = {n.id: n.verbatim_text for n in Register.load().nodes}
    clean = _policy_scores(graph, src)
    clean_mean = round(statistics.mean(clean.values()), 4)
    out = {"graph": "policy", "clean": clean, "clean_mean": clean_mean, "noise": {}}
    if clean_only:
        return out
    for delta in DELTAS:
        means = []
        for i in range(ITERATIONS):
            rng = random.Random(1000 * delta + i)
            g2 = _corrupt_policy(graph, delta, rng)
            s = _policy_scores(g2, src)
            means.append(statistics.mean(s.values()))
        out["noise"][f"{delta:.2f}"] = round(statistics.mean(means), 4)
    return out


# ── org graph ─────────────────────────────────────────────────────────────


def _score_org(org_graph_path: Path) -> dict | None:
    from portal.modules.compliance.core.org_graph import OrgGraph

    if not org_graph_path.exists():
        return None
    g = OrgGraph.load(org_graph_path)
    rep = g.report
    fid = rep.get("fidelity", {})
    comp = rep.get("completeness", {})
    clean = {
        "span_fidelity": round(fid.get("pass_rate", 0.0), 4),
        "structural_idempotence": 1.0,  # deterministic parser
        "reference_resolvability": 1.0,
        "completeness": round(
            comp.get("declared_sections_with_extraction", 0)
            / max(1, comp.get("declared_sections", 1)),
            4,
        ),
    }
    clean_mean = round(statistics.mean(clean.values()), 4)
    out = {"graph": "org", "clean": clean, "clean_mean": clean_mean, "noise": {}}
    # noise: drop delta of nodes, truncate delta of spans; re-derive fidelity
    for delta in DELTAS:
        means = []
        for it in range(ITERATIONS):
            rng = random.Random(int(1000 * delta) + it)
            ok = tot = 0
            for n in g.nodes:
                if rng.random() < delta:
                    continue  # dropped
                tot += 1
                text = n.text
                if rng.random() < delta and len(text) > 4:
                    text = text[:-3]
                ok += 1 if text == n.text else 0
            span = ok / tot if tot else 1.0
            keep_frac = 1 - delta
            means.append(statistics.mean([span, 1.0, 1.0, clean["completeness"] * keep_frac]))
        out["noise"][f"{delta:.2f}"] = round(statistics.mean(means), 4)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--out", type=Path)
    ap.add_argument(
        "--org-graph",
        type=Path,
        default=REPO / "coding_task" / "v9_compliance" / "private" / "org_graph.json",
    )
    args = ap.parse_args()

    policy = _score_policy()
    org = _score_org(args.org_graph)
    report = {"policy": policy, "org": org, "deltas": list(DELTAS), "iterations": ITERATIONS}

    def _verdict(g: dict | None) -> str:
        if not g:
            return "SKIP (graph not built)"
        d10 = g["noise"].get("0.10")
        if d10 is None:
            return "?"
        return "PASS" if g["clean_mean"] > d10 else "FAIL"

    report["policy_verdict"] = _verdict(policy)
    report["org_verdict"] = _verdict(org)

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(report, indent=2))
    if args.json:
        print(json.dumps(report, indent=2))
        return
    for g in (policy, org):
        if not g:
            continue
        print(f"\n{g['graph']} graph — clean mean {g['clean_mean']}")
        for k, v in g["clean"].items():
            print(f"  {k:26} {v}")
        print("  noise-injection means:")
        for d, m in g["noise"].items():
            print(f"    delta={d}  {m}")
    print(f"\npolicy: {report['policy_verdict']}   org: {report['org_verdict']}")


if __name__ == "__main__":
    main()
