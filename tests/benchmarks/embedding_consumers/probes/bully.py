"""Bully probes: hunt-memory projection (Arm D) and the novelty channel.

``bully_projection`` re-runs the adopted SA5 machinery (scripts/defensive_bully_p04_adoption.py
``run_arm``: dedup corpus -> version-tagged projection -> derived thresholds -> SA2 discovery lane
with identity as a diagnostic) for the incumbent (Arm A, MLX Qwen3 on :8917) and EG2 as Arm D
(:8946 /v1/embeddings, raw text), on the frozen SPECIMEN_CORPUS_V2. ``bully_novelty`` asks whether
distance-to-known-centroid separates a telemetry source the index has never seen (leave-one-
source-class-out) from held-out records of known classes.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

import httpx

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
from ._common import auc_roc, cos

CORPUS = Path(
    "/Volumes/data01/portal5_hunt/artifacts/specimen_corpus_sa1_v1/specimen_corpus_v2.json"
)
SCRATCH = Path("/Volumes/data01/portal5_scratch_eg2/bully")
A_URL = "http://localhost:8917/v1/embeddings"
D_URL = "http://localhost:8946/v1/embeddings"


def _p04() -> Any:
    p = REPO_ROOT / "scripts" / "defensive_bully_p04_adoption.py"
    spec = importlib.util.spec_from_file_location("p5_p04", p)
    assert spec and spec.loader
    m = importlib.util.module_from_spec(spec)
    sys.modules["p5_p04"] = m
    spec.loader.exec_module(m)
    return m


def _embed(url: str, texts: list[str]) -> list[list[float]]:
    out: list[list[float]] = []
    for i in range(0, len(texts), 32):
        r = httpx.post(
            url,
            json={
                "input": texts[i : i + 32],
                "model": "google/embeddinggemma-2" if ":8946" in url else "x",
            },
            timeout=600,
        )
        r.raise_for_status()
        out += [d["embedding"] for d in sorted(r.json()["data"], key=lambda d: d["index"])]
    return out


@probe("bully_projection")
async def projection(ctx: ProbeContext) -> ProbeResult:
    if not CORPUS.is_file():
        return blocked("bully_projection", f"SPECIMEN_CORPUS_V2 not found at {CORPUS}")
    if not ctx.live:
        return blocked("bully_projection", "needs --live (embedders :8917 and :8946)")
    p04 = _p04()
    from portal.modules.security.core.bully.cousin_calibration_bench import (
        corpus_parent_reference_record,
        load_specimen_corpus,
    )
    from portal.modules.security.core.bully.organ import _canonical_record_text

    corpus = load_specimen_corpus(CORPUS)
    corpus["_path"] = CORPUS
    parents = p04._dedupe_parents(corpus)
    version_d = await ctx.client.version_tag(768)
    p04.ARM_SPECS["arm-d"] = {"label": "eg2-768d", "embedding_version": version_d, "batch_size": 32}
    arms = {
        "arm-a": (A_URL, p04.ARM_SPECS["arm-a"]["embedding_version"]),
        "arm-d": (D_URL, version_d),
    }
    results: dict[str, Any] = {}
    for arm, (url, ver) in arms.items():
        d = SCRATCH / arm
        if d.exists():
            import shutil

            shutil.rmtree(d)
        SCRATCH.mkdir(parents=True, exist_ok=True)
        res = p04.run_arm(
            arm,
            parents=parents,
            corpus=corpus,
            output_dir=SCRATCH,
            embed_url=url,
            query_embed_url=None,
            embedding_version=ver,
            batch_size=32,
        )
        rep = res["report"]
        results[arm] = {
            "status": rep["status"],
            "discovery_precision": rep["discovery_precision"],
            "discovery_recall_proxy": rep.get("discovery_recall_proxy"),
            "controls_passed": (rep.get("controls") or {}).get("passed"),
            "identity_failures": ((rep.get("controls") or {}).get("identity") or {}).get("checked"),
            "thresholds": {k: res["thresholds"].get(k) for k in list(res["thresholds"])[:6]},
        }
    # the 4719/4688 near-twin the Arm A analysis flagged (cosine ~0.9998 under Qwen3)
    texts = {_canonical_record_text(corpus_parent_reference_record(s)) for s in parents}
    a = next((t for t in texts if "event-0:4719" in t), None)
    b = next((t for t in texts if "event-0:4688" in t or "4688" in t.split("|")[0]), None)
    twin: dict[str, Any] = {}
    if a and b:
        for arm, (url, _) in arms.items():
            va, vb = _embed(url, [a, b])
            twin[arm] = round(cos(va, vb), 4)
    ra, rd = results["arm-a"], results["arm-d"]
    inc = {"primary": ra["discovery_precision"], **ra}
    cand = {"primary": rd["discovery_precision"], **rd, "near_twin_4719_vs_4688_cosine": twin}
    return ProbeResult(
        "bully_projection",
        MEASURED,
        inc,
        cand,
        compare(float(inc["primary"]), float(cand["primary"]), parity_band=0.03),
        fixture={
            "deduplicated_parents": len(parents),
            "corpus": str(CORPUS.name),
            "sha": fixture_digest(sorted(texts)),
        },
        identity=version_d,
        notes=[
            "EG2 embeds the canonical record text raw through /v1/embeddings (no task prefix), as the Organ's embed client does for every arm"
        ],
    )


@probe("bully_novelty")
async def novelty(ctx: ProbeContext) -> ProbeResult:
    if not CORPUS.is_file():
        return blocked("bully_novelty", f"SPECIMEN_CORPUS_V2 not found at {CORPUS}")
    from portal.modules.security.core.bully.cousin_calibration_bench import (
        corpus_parent_reference_record,
        load_specimen_corpus,
    )
    from portal.modules.security.core.bully.organ import _canonical_record_text

    corpus = load_specimen_corpus(CORPUS)
    rows: dict[str, tuple[str, str]] = {}
    for s in corpus["specimens"]:
        if s["source_lane"] != "attack_data":
            continue
        t = _canonical_record_text(corpus_parent_reference_record(s))
        rows.setdefault(
            t, (str(s.get("source_class") or s.get("engine_view", {}).get("source_class")), t)
        )
    texts = [t for t, _ in rows.values()]
    classes = [c for c, _ in rows.values()]
    vecs = await ctx.client.embed_texts([t[:1800] for t in texts], task=Task.CLUSTERING, dim=768)
    import numpy as np

    x = np.asarray(vecs, dtype=np.float32)
    per: dict[str, float] = {}
    for c in sorted(set(classes)):
        idx_c = [i for i, k in enumerate(classes) if k == c]
        idx_k = [i for i, k in enumerate(classes) if k != c]
        if len(idx_c) < 10 or len(idx_k) < 40:
            continue
        # known pool = other classes; split into index set (80%) and held-out known (20%)
        rng = np.random.default_rng(7)
        perm = rng.permutation(idx_k)
        cut = int(0.8 * len(perm))
        index, held = perm[:cut], perm[cut:]
        cent = x[index].mean(0)
        cent /= np.linalg.norm(cent) + 1e-9
        idx_mat = x[index]

        def nn(ids: list[int], m: Any = idx_mat) -> list[float]:
            return [float(1 - (m @ x[i]).max()) for i in ids]

        per[c] = auc_roc(nn(idx_c), nn(held.tolist()))
        per[c + "|centroid"] = auc_roc(
            [float(1 - x[i] @ cent) for i in idx_c], [float(1 - x[i] @ cent) for i in held.tolist()]
        )
    knn = [v for k, v in per.items() if "|" not in k]
    cen = [v for k, v in per.items() if k.endswith("|centroid")]
    if not knn:
        return blocked("bully_novelty", "no source class has >=10 records with >=40 others")
    return ProbeResult(
        "bully_novelty",
        MEASURED,
        {
            "primary": None,
            "note": "no novelty channel exists (ANOMALOUS_UNCLASSIFIED has no ranking signal)",
        },
        {
            "primary": round(sum(knn) / len(knn), 4),
            "metric": "mean leave-one-source-class-out AUC of nearest-neighbour distance",
            "centroid_distance_mean_auc": round(sum(cen) / len(cen), 4),
            "per_class_auc": {k: v for k, v in per.items() if "|" not in k},
        },
        "INCONCLUSIVE",
        fixture={
            "deduplicated_parents": len(texts),
            "source_classes": len(set(classes)),
            "sha": fixture_digest(sorted(texts)),
        },
        identity=await ctx.client.version_tag(768),
        notes=[
            "proposes a ranking channel for ANOMALOUS_UNCLASSIFIED, never a verdict; 'novel' = an entire telemetry source class the index has not seen (the corpus has no benign/attack split)"
        ],
    )
