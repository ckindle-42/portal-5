"""Bully probes: hunt-memory projection (Arm D) and the novelty channel.

``bully_projection`` re-runs the adopted SA5 machinery (scripts/defensive_bully_p04_adoption.py
``run_arm``: dedup corpus -> version-tagged projection -> derived thresholds -> SA2 discovery lane
with identity as a diagnostic) for the incumbent (Arm A, MLX Qwen3 on :8917) and EG2 as Arm D
on the frozen SPECIMEN_CORPUS_V3. Arm D runs twice: with the EG2 contract's ``sentence similarity``
prefix (primary; a local proxy prefixes the Organ's raw ``/v1/embeddings`` calls) and raw
(diagnostic: what a bare repoint of the Organ's URL would give). ``bully_novelty`` asks whether
distance-to-known-centroid separates a telemetry source the index has never seen (leave-one-
source-class-out) from held-out records of known classes.
"""

from __future__ import annotations

import contextlib
import importlib.util
import json
import sys
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import httpx

from portal.platform.embedding.contract import Role, Task, format_text

from ..framework import (
    MEASURED,
    REPO_ROOT,
    ProbeContext,
    ProbeResult,
    blocked,
    fixture_digest,
    probe,
)
from ._common import auc_roc, cos

# SPECIMEN_CORPUS_V3: V2 plus the behavior values each parent's source dataset carries
# (scripts/build_specimen_corpus_v3.py --attack-data-root ... --window 2000). V2 kept field
# names only, so every arm was comparing schema.
CORPUS = Path(
    "/Volumes/data01/portal5_hunt/artifacts/specimen_corpus_sa1_v1/specimen_corpus_v3_final.json"
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


@contextlib.contextmanager
def _prefix_proxy(upstream: str, task: Task) -> Iterator[str]:
    """Loopback proxy for the Organ's ``{"input": [...]}`` calls: applies the EG2 contract prefix
    for ``task`` and forwards to ``upstream`` (the raw passthrough endpoint)."""

    class H(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            raw = body.get("input")
            texts = [raw] if isinstance(raw, str) else list(raw or [])
            body["input"] = [format_text(str(t), task, Role.QUERY) for t in texts]
            body.pop("model", None)  # the upstream serves one model; callers' names are for :8917
            r = httpx.post(upstream, json=body, timeout=600)
            out = r.content
            self.send_response(r.status_code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(out)))
            self.end_headers()
            self.wfile.write(out)

        def log_message(self, *a: object) -> None:
            pass

    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    try:
        yield f"http://127.0.0.1:{srv.server_address[1]}/v1/embeddings"
    finally:
        srv.shutdown()


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


def mcnemar_exact(a_only: int, b_only: int) -> float:
    """Two-sided exact McNemar (binomial on the discordant pairs)."""
    import math

    n = a_only + b_only
    if n == 0:
        return 1.0
    tail = sum(math.comb(n, k) for k in range(min(a_only, b_only) + 1))
    return min(1.0, 2 * tail / 2**n)


def _eligible_truth(
    arm_dir: Path, url: str, version: str, corpus: dict
) -> tuple[dict[str, bool], dict[str, bool]]:
    """Per-probe truth_related, re-graded against an arm's seeded projection: (DISCOVERY set, all
    graded probes). The engine sees each probe blind (``discovery_bench.probe_signature``), so the
    all-probes set is a fair paired comparison and the hint uses it; DISCOVERY alone is ~50 probes.

    ``run_discovery_bench`` persists only aggregate counts, and both arms grade the SAME probes
    (coverage outcomes are embedder-independent), so the comparison is paired and needs the
    per-probe outcomes. An unpaired two-proportion test on the two precisions is the wrong test:
    it under-reported this consumer's regression as p = 0.13 when the paired p is 0.039.
    """
    from portal.modules.security.core.bully.discovery_bench import (
        real_probe_specimens,
        run_real_pairs,
    )
    from portal.modules.security.core.bully.organ import Organ
    from portal.modules.security.core.bully.store import Store

    with Store(arm_dir / "snapshot_state.db") as store:
        snap = Organ(
            store=store,
            db_path=arm_dir / "organ_snapshot",
            embed_url=url,
            query_embed_url=None,
            embedding_version=version,
            embed_client=httpx.Client(timeout=600.0),
        )
        try:
            verdicts = run_real_pairs(real_probe_specimens(corpus), snap, corpus=corpus)
        finally:
            snap.close()
    graded = [
        v
        for v in verdicts
        if v.relationship != "ANOMALOUS_UNCLASSIFIED" and v.reference_signature_id
    ]
    return (
        {v.specimen_id: bool(v.truth_related) for v in graded if v.discovery_band == "DISCOVERY"},
        {v.specimen_id: bool(v.truth_related) for v in graded},
    )


def _paired(inc: dict[str, bool], cand: dict[str, bool]) -> dict[str, Any]:
    shared = sorted(set(inc) & set(cand))
    a_only = sum(inc[k] and not cand[k] for k in shared)
    c_only = sum(cand[k] and not inc[k] for k in shared)
    return {
        "shared_probes": len(shared),
        "incumbent_only_related": a_only,
        "candidate_only_related": c_only,
        "both_related": sum(inc[k] and cand[k] for k in shared),
        "neither_related": sum(not inc[k] and not cand[k] for k in shared),
        "mcnemar_exact_p": round(mcnemar_exact(a_only, c_only), 4),
    }


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
    for arm, label in (("arm-d", "eg2-768d-raw"), ("arm-d-sim", "eg2-768d-sentence-similarity")):
        p04.ARM_SPECS[arm] = {"label": label, "embedding_version": version_d, "batch_size": 32}
    stack = contextlib.ExitStack()
    sim_url = stack.enter_context(_prefix_proxy(D_URL, Task.SENTENCE_SIMILARITY))
    arms = {
        "arm-a": (A_URL, p04.ARM_SPECS["arm-a"]["embedding_version"]),
        "arm-d-sim": (sim_url, version_d),
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
    # paired significance on the shared DISCOVERY probes (the proxy must still be up for arm-d-sim)
    truth = {
        arm: _eligible_truth(SCRATCH / arm, url, ver, corpus) for arm, (url, ver) in arms.items()
    }
    stack.close()
    paired = _paired(truth["arm-a"][1], truth["arm-d-sim"][1])
    paired_raw = _paired(truth["arm-a"][1], truth["arm-d"][1])
    paired_disc = _paired(truth["arm-a"][0], truth["arm-d-sim"][0])
    ra, rd = results["arm-a"], results["arm-d-sim"]
    inc = {"primary": sum(truth["arm-a"][1].values()), **ra}
    cand = {
        "primary": sum(truth["arm-d-sim"][1].values()),
        **rd,
        "raw_no_prefix": {
            **results["arm-d"],
            "related_all": sum(truth["arm-d"][1].values()),
            "paired_vs_incumbent": paired_raw,
        },
        "paired_vs_incumbent": paired,
        "paired_discovery_band_only": paired_disc,
        "near_twin_4719_vs_4688_cosine": twin,
    }
    # The hint comes from the paired test, not a precision band: the arms grade the same probes.
    if paired["mcnemar_exact_p"] < 0.05:
        hint = (
            "WORSE"
            if paired["incumbent_only_related"] > paired["candidate_only_related"]
            else "BETTER"
        )
    else:
        hint = "INCONCLUSIVE"
    return ProbeResult(
        "bully_projection",
        MEASURED,
        inc,
        cand,
        hint,
        fixture={
            "deduplicated_parents": len(parents),
            "corpus": str(CORPUS.name),
            "sha": fixture_digest(sorted(texts)),
        },
        identity=version_d,
        notes=[
            "primary candidate = EG2 with the contract 'sentence similarity' prefix (proxy over the Organ's raw /v1/embeddings calls); raw_no_prefix = a bare URL repoint",
            "thresholds are derived per space by run_arm (embedding_spaces.derive_thresholds)",
            "primary = probes whose chosen reference is truth-related, over all graded probes; the engine sees each probe with its truth labels stripped (discovery_bench.probe_signature)",
            "hint = exact McNemar on per-probe truth_related over all shared graded probes (paired: both arms grade the same probes)",
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
