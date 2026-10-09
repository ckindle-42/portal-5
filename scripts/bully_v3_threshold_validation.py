#!/usr/bin/env python3
"""T1 of TASK_BULLY_V3_THRESHOLD_VALIDATION_V1 -- is the SAME band (same_max) fitted to a
bench-only artifact?

Sibling of scripts/bully_b1_engine_variants.py; reuses its variant machinery (decomposition,
grading, McNemar) and adds two scorer-side measurements under cousin-v3 weights:

  identity   every probe graded against its OWN indexed record (not excluded). Reported
             twice: ``asymmetric`` (the record keeps ``context_topology.family``, the probe
             had it stripped -- the B1.4 measurement) and ``symmetric`` (``family`` /
             ``scenario_family`` also removed from the indexed record, scorer-side only).
  sweep      the blind discovery set (self excluded, exactly as the B1 harness) graded under
             both context modes, with same_max swept over SAME_MAX_VALUES. Paired McNemar
             against the adopted 0.055 asymmetric arm.

Engine code is never modified: the symmetric arm changes only the reference record handed to
the scorer's decomposition. The engine still sees no truth (``discovery_bench.probe_signature``).

Per-probe rows contain corpus-derived specimen ids, so they are written to ``--scratch``
(outside the public tree); only the summary is written to ``--out``.

Usage:
    uv run python scripts/bully_v3_threshold_validation.py \
        --corpus /Volumes/data01/portal5_hunt/artifacts/specimen_corpus_sa1_v1/specimen_corpus_v3_final.json \
        --arm-dir /Volumes/data01/portal5_scratch_eg2/bully/arm-d-sim \
        --scratch /Volumes/data01/portal5_scratch_eg2/bully/t1_scratch \
        --out reports/bully_v3_threshold_validation/<stamp>_t1
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

# ruff: noqa: E402

import bully_b1_engine_variants as b1

from portal.modules.security.core.bully import cousin_engine, discovery_bench
from portal.modules.security.core.bully.cousin_calibration_bench import load_specimen_corpus
from portal.modules.security.core.bully.organ import Organ
from portal.modules.security.core.bully.store import Store

# cousin-v3 as shipped (fea93168): v2 proportions / 1.15. Ranking-identical to the B1 arm
# `f1_v2_unit_scaled`; the distinction that matters here is classification (unit mass).
V3_WEIGHTS = dict(cousin_engine._WEIGHTS)  # noqa: SLF001 -- the adopted weights, read once
V3_CHANNEL = "values_fallback"
SAME_MAX_VALUES = (0.015, 0.02, 0.026, 0.0435, 0.05, 0.055)
IDENTITY_N = 100
_TRUTH_TOPOLOGY_KEYS = ("family", "scenario_family")


def symmetric_record(record: dict[str, Any]) -> dict[str, Any]:
    """Indexed record with the probe's truth-stripped context keys removed too (scorer-side)."""
    out = dict(record)
    for key in _TRUTH_TOPOLOGY_KEYS:
        out.pop(key, None)
    context = dict(record.get("context_topology") or {})
    for key in _TRUTH_TOPOLOGY_KEYS:
        context.pop(key, None)
    out["context_topology"] = context
    return out


def _candidate_rows(candidates: Any, *, symmetric: bool) -> SimpleNamespace:
    if not symmetric:
        return candidates
    return SimpleNamespace(
        candidates=[{**c, "record": symmetric_record(c["record"])} for c in candidates.candidates]
    )


def _quantiles(values: list[float]) -> dict[str, float]:
    if not values:
        return {}
    ordered = sorted(values)
    p95 = ordered[min(len(ordered) - 1, round(0.95 * (len(ordered) - 1)))]
    return {
        "n": len(values),
        "median": round(statistics.median(ordered), 6),
        "p95": round(p95, 6),
        "max": round(ordered[-1], 6),
    }


def _open_snapshot(arm_dir: Path, embed_url: str) -> tuple[Store, Organ]:
    store = Store(arm_dir / "snapshot_state.db")
    snapshot = Organ(
        store=store,
        db_path=arm_dir / "organ_snapshot",
        embed_url=embed_url,
        query_embed_url=None,
        embedding_version="google/embeddinggemma-2:768d:sentence-similarity",
        embed_client=httpx.Client(timeout=600.0),
    )
    return store, snapshot


def identity_pass(probes: list[dict[str, Any]], snapshot: Any) -> dict[str, Any]:
    """Self-pair composite under cousin-v3, asymmetric and symmetric."""
    asym: list[float] = []
    sym: list[float] = []
    missing: list[str] = []
    per_probe: list[dict[str, Any]] = []
    for probe in probes:
        pid = probe["specimen_id"]
        signature = discovery_bench.probe_signature(probe)
        candidates = cousin_engine.retrieve_candidate_axes(signature, snapshot)
        own = [c for c in candidates.candidates if discovery_bench._record_id(c["record"]) == pid]  # noqa: SLF001
        if not own:
            missing.append(pid)
            continue
        cand = own[0]
        row: dict[str, Any] = {"specimen_id": pid}
        for label, record in (
            ("asymmetric", cand["record"]),
            ("symmetric", symmetric_record(cand["record"])),
        ):
            decomp = b1.decompose_variant(
                signature,
                record,
                semantic_distance=cand.get("semantic_distance"),
                behavior_channel=V3_CHANNEL,
            )
            composite, _conf, _nonsem = cousin_engine._weighted_composite(  # noqa: SLF001
                decomp, V3_WEIGHTS
            )
            row[label] = {
                "composite": round(composite, 6),
                "decomposition": b1._round_decomp(decomp),
            }  # noqa: SLF001
            (asym if label == "asymmetric" else sym).append(composite)
        per_probe.append(row)
    return {
        "asymmetric": _quantiles(asym),
        "symmetric": _quantiles(sym),
        "missing_self_in_candidates": len(missing),
        "rows": per_probe,
    }


def sweep_pass(
    probes: list[dict[str, Any]],
    snapshot: Any,
    corpus: dict[str, Any],
    *,
    base_thresholds: dict[str, float],
) -> dict[str, Any]:
    """Blind sweep: self excluded; every (context mode, same_max) verdict per probe."""
    index_by_id = {
        s["specimen_id"]: s for s in corpus["specimens"] if s["source_lane"] == "attack_data"
    }
    modes = [(False, "asymmetric"), (True, "symmetric")]
    rows: list[dict[str, Any]] = []
    for probe in probes:
        pid = probe["specimen_id"]
        signature = discovery_bench.probe_signature(probe)
        candidates = discovery_bench._exclude_self(  # noqa: SLF001
            cousin_engine.retrieve_candidate_axes(signature, snapshot), pid
        )
        probe_tech = frozenset(discovery_bench._specimen_technique_ids(probe))  # noqa: SLF001
        probe_family = discovery_bench._specimen_family(probe)  # noqa: SLF001
        probe_source = discovery_bench._specimen_source_class(probe)  # noqa: SLF001
        entry: dict[str, Any] = {"specimen_id": pid, "source_class": probe_source, "modes": {}}
        for symmetric, label in modes:
            cset = _candidate_rows(candidates, symmetric=symmetric)
            ranked = b1.grade_candidates(
                signature, cset, weights=V3_WEIGHTS, behavior_channel=V3_CHANNEL
            )
            if not ranked:
                entry["modes"][label] = None
                continue
            top = ranked[0]
            ref = index_by_id.get(top["record_id"])
            if ref is not None:
                ref_tech = frozenset(discovery_bench._specimen_technique_ids(ref))  # noqa: SLF001
                ref_family = discovery_bench._specimen_family(ref)  # noqa: SLF001
            else:
                record = next(
                    c["record"]
                    for c in cset.candidates
                    if str(c["record"].get("record_id")) == top["record_id"]
                )
                ref_tech = frozenset(str(record.get("attack_ids_text") or "").split())
                ref_family = str(record.get("family") or "")
            related = discovery_bench.independent_truth_related(
                probe_tech, ref_tech, probe_family, ref_family
            )
            top_record = next(
                c["record"]
                for c in cset.candidates
                if str(c["record"].get("record_id")) == top["record_id"]
            )
            twin_events = (top_record.get("event_graph") or {}).get("ordered") or []
            probe_events = (
                probe.get("engine_view", {}).get("telemetry_view", {}).get("event_graph") or {}
            ).get("ordered") or []
            probe_values = {
                str(v)
                for v in (probe["engine_view"]["telemetry_view"].get("artifacts") or {}).get(
                    "behavior_values"
                )
                or ()
            }
            ref_values = {
                str(v) for v in (top_record.get("artifacts") or {}).get("behavior_values") or ()
            }
            twin = {
                "identical_events": bool(probe_events) and twin_events == probe_events,
                "identical_values": bool(probe_values) and probe_values == ref_values,
                "trivial": len(probe_events) < 2,
            }
            contrib = {
                k: round(top["decomposition"][k] * V3_WEIGHTS[k], 6)
                for k in V3_WEIGHTS
                if top["decomposition"].get(k) is not None
            }
            per_thr = {}
            for thr in SAME_MAX_VALUES:
                thresholds = {**base_thresholds, "same_max_distance": thr}
                relationship = cousin_engine._classify_relationship(  # noqa: SLF001
                    top["composite"],
                    top["confidence"],
                    top["nonsemantic"],
                    vetoed=False,
                    thresholds=thresholds,
                )
                per_thr[str(thr)] = {
                    "relationship": relationship,
                    "related": related,
                    "cross_source": bool(
                        top["source_class"] and top["source_class"] != probe_source
                    ),
                    "twin": twin,
                    "contrib": contrib,
                }
            entry["modes"][label] = {
                "twin": twin,
                "contrib": contrib,
                "composite": round(top["composite"], 6),
                "confidence": round(top["confidence"], 6),
                "reference_source_class": top["source_class"],
                "by_same_max": per_thr,
            }
        rows.append(entry)
    return {"rows": rows}


def summarise_sweep(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Per (mode, same_max): SAME-band chosen pairs split truth-related / not; paired movers vs
    the adopted asymmetric 0.055 arm."""
    baseline_key = ("asymmetric", str(0.055))
    out: dict[str, Any] = {}

    def verdict(entry: dict[str, Any], mode: str, thr: str) -> dict[str, Any] | None:
        m = entry["modes"].get(mode)
        return None if m is None else m["by_same_max"][thr]

    for mode in ("asymmetric", "symmetric"):
        for thr in (str(v) for v in SAME_MAX_VALUES):
            same = same_rel = same_unrel = related_graded = cross_rel = 0
            movers = {"discovery_to_regression": 0, "regression_to_discovery": 0}
            for entry in rows:
                v = verdict(entry, mode, thr)
                if v is None:
                    continue
                if v["relationship"] == "SAME":
                    same += 1
                    if v["related"]:
                        same_rel += 1
                    else:
                        same_unrel += 1
                if v["related"] and v["relationship"] != "ANOMALOUS_UNCLASSIFIED":
                    related_graded += 1
                if (
                    v["related"]
                    and v["cross_source"]
                    and v["relationship"] != "ANOMALOUS_UNCLASSIFIED"
                ):
                    cross_rel += 1
                base = verdict(entry, *baseline_key)
                if base is None:
                    continue
                now_same = v["relationship"] == "SAME"
                was_same = base["relationship"] == "SAME"
                if was_same and not now_same and v["related"]:
                    movers["discovery_to_regression"] += 1  # SAME lost on a truth-related pair
                if now_same and not was_same and not v["related"]:
                    movers["regression_to_discovery"] += 1  # SAME gained on an unrelated pair
            out[f"{mode}@{thr}"] = {
                "same_band_chosen": same,
                "same_band_truth_related": same_rel,
                "same_band_not_truth_related": same_unrel,
                "related_graded": related_graded,
                "cross_source_related_graded": cross_rel,
                "movers_vs_asymmetric_0.055": movers,
            }
    out["same_band_breakdown"] = same_breakdown(rows)
    return out


def same_breakdown(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """For SAME-band chosen pairs at each cut-off: twin status and dominant channel."""
    result: dict[str, Any] = {}
    for mode in ("asymmetric", "symmetric"):
        for thr in (str(v) for v in SAME_MAX_VALUES):
            buckets: dict[str, Any] = {
                "not_related": {
                    "n": 0,
                    "identical_events": 0,
                    "identical_values": 0,
                    "trivial": 0,
                    "dominant": {},
                },
                "related": {
                    "n": 0,
                    "identical_events": 0,
                    "identical_values": 0,
                    "trivial": 0,
                    "dominant": {},
                },
            }
            for entry in rows:
                m = entry["modes"].get(mode)
                if m is None:
                    continue
                v = m["by_same_max"][thr]
                if v["relationship"] != "SAME":
                    continue
                b = buckets["related" if v["related"] else "not_related"]
                b["n"] += 1
                b["identical_events"] += m["twin"]["identical_events"]
                b["identical_values"] += m["twin"]["identical_values"]
                b["trivial"] += m["twin"]["trivial"]
                dom = max(m["contrib"], key=lambda k: m["contrib"][k]) if m["contrib"] else "none"
                b["dominant"][dom] = b["dominant"].get(dom, 0) + 1
            result[f"{mode}@{thr}"] = buckets
    return result


def paired_mcnemar(
    rows: list[dict[str, Any]], mode_a: str, mode_b: str, thr: str
) -> dict[str, Any]:
    a_only = b_only = 0
    for entry in rows:
        va = entry["modes"].get(mode_a)
        vb = entry["modes"].get(mode_b)
        if va is None or vb is None:
            continue
        ra = (
            va["by_same_max"][thr]["related"]
            and va["by_same_max"][thr]["relationship"] != "ANOMALOUS_UNCLASSIFIED"
        )
        rb = (
            vb["by_same_max"][thr]["related"]
            and vb["by_same_max"][thr]["relationship"] != "ANOMALOUS_UNCLASSIFIED"
        )
        a_only += ra and not rb
        b_only += rb and not ra
    return {
        "a_only": a_only,
        "b_only": b_only,
        "mcnemar_exact_p": round(b1.mcnemar_exact(a_only, b_only), 5),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--arm-dir", type=Path, required=True)
    parser.add_argument("--embed-url", default="http://localhost:8946/embed")
    parser.add_argument("--scratch", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--identity-n", type=int, default=IDENTITY_N)
    parser.add_argument("--max-probes", type=int, default=None)
    parser.add_argument("--skip-sweep", action="store_true")
    args = parser.parse_args(argv)

    corpus = load_specimen_corpus(args.corpus)
    base_thresholds = {**cousin_engine.DEFAULT_THRESHOLDS}
    probes = discovery_bench.real_probe_specimens(corpus)
    if args.max_probes:
        probes = probes[: args.max_probes]
    identity_probes = probes[: args.identity_n]

    store, snapshot = _open_snapshot(args.arm_dir, args.embed_url)
    try:
        t0 = time.time()
        queries = [
            q
            for p in probes
            for q in cousin_engine.candidate_axis_queries(discovery_bench.probe_signature(p))
        ]
        print(f"prepare_knn: {len(queries)} axis queries ...", flush=True)
        snapshot.prepare_knn(queries, k=8, batch_size=32)
        print(f"prepare_knn done in {time.time() - t0:.0f}s", flush=True)

        identity = identity_pass(identity_probes, snapshot)
        print(
            "identity asym:",
            identity["asymmetric"],
            "sym:",
            identity["symmetric"],
            "missing:",
            identity["missing_self_in_candidates"],
            flush=True,
        )
        sweep = (
            {"rows": []}
            if args.skip_sweep
            else sweep_pass(probes, snapshot, corpus, base_thresholds=base_thresholds)
        )
    finally:
        snapshot.close()
        store.close()

    args.scratch.mkdir(parents=True, exist_ok=True)
    (args.scratch / "identity_rows.json").write_text(
        json.dumps(identity.pop("rows"), indent=1) + "\n", encoding="utf-8"
    )
    (args.scratch / "sweep_rows.json").write_text(
        json.dumps(sweep["rows"], indent=1) + "\n", encoding="utf-8"
    )

    summary: dict[str, Any] = {
        "schema": "BULLY_V3_T1_SAME_BAND_V1",
        "weights": V3_WEIGHTS,
        "channel": V3_CHANNEL,
        "same_max_values": list(SAME_MAX_VALUES),
        "identity": identity,
        "blind_probes": len(probes),
        "sweep": summarise_sweep(sweep["rows"]) if sweep["rows"] else None,
        "mcnemar_symmetric_vs_asymmetric": {
            str(thr): paired_mcnemar(sweep["rows"], "asymmetric", "symmetric", str(thr))
            for thr in SAME_MAX_VALUES
        }
        if sweep["rows"]
        else None,
    }
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "t1_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
