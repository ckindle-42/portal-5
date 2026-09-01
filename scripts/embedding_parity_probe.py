#!/usr/bin/env python3
"""Embedding parity probe (TASK_VL_RUNTIME_LANDING_V4 Phase 3).

Captures a fingerprint of what the live :8917 embedding server produces for a
fixed corpus, so a before/after comparison across a dependency change can decide
whether a re-embed is required.

Usage:
    python3 scripts/embedding_parity_probe.py capture  --tag pre-sync  --out reports/runtime/parity/
    python3 scripts/embedding_parity_probe.py capture  --tag post-sync --out reports/runtime/parity/
    python3 scripts/embedding_parity_probe.py compare  reports/runtime/parity/pre-sync.json reports/runtime/parity/post-sync.json

Decision rules (Phase 3):
    dim changed                                   -> re-embed
    self_cos_min >= 0.9999 and top1_agreement==1  -> identical, no re-embed
    self_cos_min >= 0.99   and top10_overlap>=0.95 -> quantisation noise, no re-embed
    otherwise                                     -> re-embed from source text
Ranking stability is primary, cosine secondary. Never average them.
"""

from __future__ import annotations

import argparse
import json
import math
import pathlib
import sys
import urllib.request

FIXTURE = (
    pathlib.Path(__file__).parent.parent / "tests" / "fixtures" / "embedding_parity_probe.jsonl"
)
DEFAULT_URL = "http://localhost:8917/v1/embeddings"


def _load_corpus() -> list[dict]:
    rows = []
    for line in FIXTURE.read_text().splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def _embed(url: str, texts: list[str]) -> list[list[float]]:
    body = json.dumps({"input": texts, "model": "parity-probe"}).encode()
    req = urllib.request.Request(url, data=body, headers={"content-type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        payload = json.load(resp)
    return [d["embedding"] for d in payload["data"]]


def _cos(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def capture(args: argparse.Namespace) -> int:
    corpus = _load_corpus()
    texts = [r["text"] for r in corpus]
    ids = [r["id"] for r in corpus]
    vecs = _embed(args.url, texts)
    dim = len(vecs[0])
    # ranking: for every query row, cosine against every doc row
    q_idx = [i for i, r in enumerate(corpus) if r.get("role") == "query"]
    d_idx = [i for i, r in enumerate(corpus) if r.get("role") == "doc"]
    rankings = {}
    for qi in q_idx:
        scored = sorted(((_cos(vecs[qi], vecs[di]), ids[di]) for di in d_idx), reverse=True)
        rankings[ids[qi]] = [name for _, name in scored]
    out = {
        "tag": args.tag,
        "url": args.url,
        "dim": dim,
        "ids": ids,
        "vectors": vecs,
        "rankings": rankings,
    }
    dest = pathlib.Path(args.out)
    dest.mkdir(parents=True, exist_ok=True)
    path = dest / f"{args.tag}.json"
    path.write_text(json.dumps(out))
    print(f"captured {len(ids)} rows, dim={dim} -> {path}")
    return 0


def compare(args: argparse.Namespace) -> int:
    a = json.loads(pathlib.Path(args.before).read_text())
    b = json.loads(pathlib.Path(args.after).read_text())
    if a["ids"] != b["ids"]:
        print("FAIL: corpus id lists differ")
        return 2
    dim_changed = a["dim"] != b["dim"]
    self_cos = [_cos(va, vb) for va, vb in zip(a["vectors"], b["vectors"], strict=True)]
    self_cos_min = min(self_cos)
    self_cos_med = sorted(self_cos)[len(self_cos) // 2]
    # ranking stability
    top1_hits = top10_overlaps = n = 0
    for qid, ra in a["rankings"].items():
        rb = b["rankings"][qid]
        n += 1
        top1_hits += int(ra[0] == rb[0])
        top10_overlaps += len(set(ra[:10]) & set(rb[:10])) / 10.0
    top1_agreement = top1_hits / n if n else 1.0
    top10_overlap = top10_overlaps / n if n else 1.0

    print(f"dim: {a['dim']} -> {b['dim']}  (changed={dim_changed})")
    print(f"self_cos min={self_cos_min:.6f} median={self_cos_med:.6f}")
    print(f"top1_agreement={top1_agreement:.4f}  top10_overlap_mean={top10_overlap:.4f}  (n={n})")

    if dim_changed:
        verdict = "RE-EMBED (dim changed)"
    elif self_cos_min >= 0.9999 and top1_agreement == 1.0:
        verdict = "IDENTICAL — no re-embed"
    elif self_cos_min >= 0.99 and top10_overlap >= 0.95:
        verdict = "QUANTISATION NOISE — record, no re-embed"
    else:
        verdict = "RE-EMBED from source text"
    print(f"VERDICT: {verdict}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("capture")
    c.add_argument("--tag", required=True)
    c.add_argument("--out", default="reports/runtime/parity/")
    c.add_argument("--url", default=DEFAULT_URL)
    c.set_defaults(func=capture)
    p = sub.add_parser("compare")
    p.add_argument("before")
    p.add_argument("after")
    p.set_defaults(func=compare)
    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
