#!/usr/bin/env python3
"""B1 -- why blind discovery is same-source-only, and whether a weight variant fixes it
(TASK_EG2_FOLLOWUPS_AND_BULLY_ENGINE_V1).

One retrieval pass per probe on a SEEDED projection (the EG2 cutover's arm-d-sim scratch
snapshot, embed queries re-issued through the live contract endpoint -- identical texts, so
identical vectors), then every variant is graded on that identical candidate set: exactly
paired, no re-embedding between arms.

Per probe the script records, per variant:
  * the chosen reference (lowest weighted composite) and its full channel decomposition,
  * the best truth-related candidate inside the candidate set and its rank
    (retrieved-but-outranked vs never-retrieved),
  * twin flagging (identical raw evidence under two labels).

Variants:
  base             cousin-v1 weights (pinned), behavior = Jaccard on action_sequence
  f1_*             review F1: unit-mass (1.00) variants of the adopted cousin-v2
  down_tele_ctx    telemetry/context at 0.05 instead of 0.20/0.10
  behavior_values  behavior = Jaccard on artifacts.behavior_values value terms
  down_plus_values down_tele_ctx + behavior_values combined

Usage:
    uv run python scripts/bully_b1_engine_variants.py \
        --corpus /Volumes/data01/portal5_hunt/artifacts/specimen_corpus_sa1_v1/specimen_corpus_v3.json \
        --arm-dir /Volumes/data01/portal5_scratch_eg2/bully/arm-d-sim \
        --embed-url http://localhost:8946/embed \
        --out reports/bully_b1/<stamp>
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path
from typing import Any

import httpx

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT))

# ruff: noqa: E402

from portal.modules.security.core.bully import cousin_engine, discovery_bench  # noqa: E402
from portal.modules.security.core.bully.cousin_calibration_bench import (  # noqa: E402
    load_specimen_corpus,
)
from portal.modules.security.core.bully.organ import Organ  # noqa: E402
from portal.modules.security.core.bully.store import Store  # noqa: E402

# Pinned cousin-v1 weights: the base arm must stay v1 after the engine adopted v2 (reading
# `cousin_engine._WEIGHTS` here would silently turn "base" into the adopted variant).
BASE_WEIGHTS = {
    "behavior": 0.30,
    "telemetry": 0.20,
    "semantic": 0.25,
    "attack": 0.15,
    "context": 0.10,
}
# cousin-v2 as adopted in 1ee68f4b (total mass 1.15), and the review follow-up F1 arms that
# hold total mass at 1.00 -- separating the ranking gain from the confidence-mass inflation.
V2_WEIGHTS = {
    "behavior": 0.40,
    "semantic": 0.40,
    "telemetry": 0.10,
    "context": 0.10,
    "attack": 0.15,
}
V2_MASS = sum(V2_WEIGHTS.values())
ADOPTED = "values_fallback_mass_preserving"

VARIANTS: dict[str, dict[str, Any]] = {
    "base": {"weights": dict(BASE_WEIGHTS), "behavior_channel": "action_sequence"},
    "down_tele_ctx": {
        "weights": {**BASE_WEIGHTS, "telemetry": 0.05, "context": 0.05},
        "behavior_channel": "action_sequence",
    },
    "behavior_values": {
        "weights": dict(BASE_WEIGHTS),
        "behavior_channel": "behavior_values",
    },
    # Mass-preserving down-weight (telemetry+context 0.30 -> 0.20, freed mass to
    # behavior+semantic): the engine never renormalizes, so the raw down-weight's total
    # mass 0.40 falls under MIN_CONFIDENCE_FOR_CLASSIFICATION and classifies everything
    # ANOMALOUS regardless of ranking. This variant keeps the classification ladder live.
    "mass_preserving_down": {
        "weights": {
            "behavior": 0.40,
            "semantic": 0.40,
            "telemetry": 0.10,
            "context": 0.10,
            "attack": 0.15,
        },
        "behavior_channel": "action_sequence",
    },
    "down_plus_values": {
        "weights": {**BASE_WEIGHTS, "telemetry": 0.05, "context": 0.05},
        "behavior_channel": "behavior_values",
    },
    # Mass-preserving down-weight + the behavior_values channel: the adoption candidate that
    # keeps the classification ladder live (mass 1.00) if the values channel is what carries
    # the cross-source signal.
    "values_mass_preserving": {
        "weights": {
            "behavior": 0.40,
            "semantic": 0.40,
            "telemetry": 0.10,
            "context": 0.10,
            "attack": 0.15,
        },
        "behavior_channel": "behavior_values",
    },
    # Fallback channel (values when both sides carry them, else action-sequence Jaccard):
    # no mass loss on values-less pairs, so the classification ladder stays live.
    "values_fallback_base": {
        "weights": dict(BASE_WEIGHTS),
        "behavior_channel": "values_fallback",
    },
    "values_fallback_mass_preserving": {
        "weights": {
            "behavior": 0.40,
            "semantic": 0.40,
            "telemetry": 0.10,
            "context": 0.10,
            "attack": 0.15,
        },
        "behavior_channel": "values_fallback",
    },
    # F1: v2 scaled to unit mass -- identical ranking to v2 (every composite / 1.15), so any
    # difference is classification only (confidence gate + band scale).
    "f1_v2_unit_scaled": {
        "weights": {k: v / V2_MASS for k, v in V2_WEIGHTS.items()},
        "behavior_channel": "values_fallback",
    },
    "f1_unit_35_35_10_05": {
        "weights": {
            "behavior": 0.35,
            "semantic": 0.35,
            "telemetry": 0.10,
            "context": 0.05,
            "attack": 0.15,
        },
        "behavior_channel": "values_fallback",
    },
    "f1_unit_35_35_05_10": {
        "weights": {
            "behavior": 0.35,
            "semantic": 0.35,
            "telemetry": 0.05,
            "context": 0.10,
            "attack": 0.15,
        },
        "behavior_channel": "values_fallback",
    },
    "f1_unit_375_375_05_05": {
        "weights": {
            "behavior": 0.375,
            "semantic": 0.375,
            "telemetry": 0.05,
            "context": 0.05,
            "attack": 0.15,
        },
        "behavior_channel": "values_fallback",
    },
}


def _action_sequence_behavior(subject: Any, reference: dict[str, Any]) -> float | None:
    """cousin-v1's behavior channel: Jaccard over action_sequence, None when unavailable.

    Re-implemented here because the engine's `_decompose` is values-first since cousin-v2;
    mirrors its `available("action_sequence", ...)` presence rule exactly."""
    subject_actions = getattr(subject, "action_sequence", None) or []
    ref_action = set(
        reference.get("action_sequence") or reference.get("behavior_sequence", "").split()
    )
    declared = getattr(subject, "present_dimensions", None)
    ref_declared = reference.get("present_dimensions")
    subject_ok = "action_sequence" in declared if declared is not None else bool(subject_actions)
    ref_ok = "action_sequence" in ref_declared if ref_declared is not None else bool(ref_action)
    if not (subject_ok and ref_ok):
        return None
    return cousin_engine._jaccard_distance(set(subject_actions), ref_action)  # noqa: SLF001


def _behavior_values_set(obj: dict[str, Any] | None) -> set[str]:
    return {str(v) for v in ((obj or {}).get("behavior_values") or ())}


def decompose_variant(
    subject: Any,
    reference: dict[str, Any],
    *,
    semantic_distance: float | None,
    behavior_channel: str,
) -> dict[str, float | None]:
    """The engine's `_decompose`, with the behavior channel switchable.

    action_sequence: exactly `cousin_engine._decompose`. behavior_values: Jaccard over the
    value terms both sides carry in `artifacts.behavior_values`; None when either side lacks
    them (missing dimension -> no distance, no weight mass -- the engine's I-6 semantics).
    values_fallback: Jaccard over value terms when BOTH sides carry them, else the
    action-sequence Jaccard -- the same graceful degradation `semantic_query` applies when a
    signature predates the values capture.
    """
    decomp = cousin_engine._decompose(  # noqa: SLF001 -- measurement harness
        subject, reference, semantic_distance=semantic_distance
    )
    if behavior_channel == "action_sequence":
        decomp["behavior"] = _action_sequence_behavior(subject, reference)
        return decomp
    subj_values = _behavior_values_set(getattr(subject, "artifacts", None) or {})
    ref_values = _behavior_values_set(reference.get("artifacts") or {})
    if behavior_channel == "behavior_values":
        decomp["behavior"] = (
            cousin_engine._jaccard_distance(subj_values, ref_values)  # noqa: SLF001
            if subj_values and ref_values
            else None
        )
    elif behavior_channel == "values_fallback":
        decomp["behavior"] = (
            cousin_engine._jaccard_distance(subj_values, ref_values)  # noqa: SLF001
            if subj_values and ref_values
            else _action_sequence_behavior(subject, reference)
        )
    return decomp


def grade_candidates(
    signature: Any,
    candidates: cousin_engine.CandidateSetReceipt,
    *,
    weights: dict[str, float],
    behavior_channel: str,
) -> list[dict[str, Any]]:
    """Rank a candidate set under one variant; returns candidates ordered by composite."""
    scored = []
    for candidate in candidates.candidates:
        record = candidate["record"]
        decomp = decompose_variant(
            signature,
            record,
            semantic_distance=candidate.get("semantic_distance"),
            behavior_channel=behavior_channel,
        )
        composite, confidence, nonsemantic = cousin_engine._weighted_composite(  # noqa: SLF001
            decomp, weights
        )
        scored.append(
            {
                "record_id": str(record.get("record_id") or record.get("signature_id") or ""),
                "source_class": str(record.get("source_class") or ""),
                "composite": composite,
                "confidence": confidence,
                "nonsemantic": nonsemantic,
                "decomposition": dict(decomp),
                "axes": sorted(
                    key[len("from_") :]
                    for key in candidate
                    if key.startswith("from_") and candidate[key]
                )
                + (["semantic_knn"] if candidate.get("semantic_distance") is not None else []),
            }
        )
    scored.sort(key=lambda row: row["composite"])  # same stable sort as cousin_engine.grade
    for rank, row in enumerate(scored):
        row["rank"] = rank
    return scored


def mcnemar_exact(a_only: int, b_only: int) -> float:
    n = a_only + b_only
    if n == 0:
        return 1.0
    tail = sum(math.comb(n, k) for k in range(min(a_only, b_only) + 1))
    return min(1.0, 2 * tail / 2**n)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--arm-dir", type=Path, required=True)
    parser.add_argument("--embed-url", default="http://localhost:8946/embed")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--max-probes", type=int, default=None)
    args = parser.parse_args(argv)

    corpus = load_specimen_corpus(args.corpus)
    thresholds = json.loads((args.arm_dir / "space_thresholds.json").read_text())
    print(
        "arm thresholds:",
        {
            k: thresholds[k]
            for k in ("same_max_distance", "similar_max_distance", "new_max_distance")
        },
    )
    probes = discovery_bench.real_probe_specimens(corpus)
    if args.max_probes:
        probes = probes[: args.max_probes]
    index_by_id = {
        s["specimen_id"]: s for s in corpus["specimens"] if s["source_lane"] == "attack_data"
    }

    # Per-probe truth (scorer-only join inputs) and raw evidence, for twin flagging.
    truth = {}
    for probe in probes:
        truth[probe["specimen_id"]] = {
            "techniques": sorted(discovery_bench._specimen_technique_ids(probe)),  # noqa: SLF001
            "family": discovery_bench._specimen_family(probe),  # noqa: SLF001
            "source_class": discovery_bench._specimen_source_class(probe),  # noqa: SLF001
            "events": json.dumps(
                (probe["engine_view"]["telemetry_view"].get("event_graph") or {}).get("ordered")
                or [],
                sort_keys=True,
            ),
            "values": sorted(
                _behavior_values_set(probe["engine_view"]["telemetry_view"].get("artifacts") or {})
            ),
        }

    with Store(args.arm_dir / "snapshot_state.db") as store:
        snapshot = Organ(
            store=store,
            db_path=args.arm_dir / "organ_snapshot",
            embed_url=args.embed_url,
            query_embed_url=None,
            embedding_version="google/embeddinggemma-2:768d:sentence-similarity",
            embed_client=httpx.Client(timeout=600.0),
        )
        try:
            t0 = time.time()
            probe_signatures = {
                p["specimen_id"]: discovery_bench.probe_signature(p) for p in probes
            }
            queries = [
                q
                for sig in probe_signatures.values()
                for q in cousin_engine.candidate_axis_queries(sig)
            ]
            print(f"prepare_knn: {len(queries)} axis queries ...", flush=True)
            snapshot.prepare_knn(queries, k=8, batch_size=32)
            print(f"prepare_knn done in {time.time() - t0:.0f}s", flush=True)

            per_variant = {name: [] for name in VARIANTS}
            instrumentation: list[dict[str, Any]] = []
            for i, probe in enumerate(probes):
                pid = probe["specimen_id"]
                signature = probe_signatures[pid]
                candidates = discovery_bench._exclude_self(  # noqa: SLF001
                    cousin_engine.retrieve_candidate_axes(signature, snapshot), pid
                )
                t = truth[pid]
                # truth-join every candidate record once (variant-independent)
                candidate_truth: dict[str, bool] = {}
                candidate_events: dict[str, str] = {}
                candidate_values: dict[str, list[str]] = {}
                for candidate in candidates.candidates:
                    record = candidate["record"]
                    rid = str(record.get("record_id") or record.get("signature_id") or "")
                    ref_specimen = index_by_id.get(rid)
                    if ref_specimen is not None:
                        ref_tech = sorted(discovery_bench._specimen_technique_ids(ref_specimen))  # noqa: SLF001
                        ref_family = discovery_bench._specimen_family(ref_specimen)  # noqa: SLF001
                    else:
                        ref_tech = sorted(str(record.get("attack_ids_text") or "").split())
                        ref_family = str(record.get("family") or "")
                    candidate_truth[rid] = discovery_bench.independent_truth_related(
                        frozenset(t["techniques"]), frozenset(ref_tech), t["family"], ref_family
                    )
                    candidate_events[rid] = json.dumps(
                        (record.get("event_graph") or {}).get("ordered") or [], sort_keys=True
                    )
                    candidate_values[rid] = sorted(_behavior_values_set(record.get("artifacts")))

                # base arm doubles as the instrumentation pass
                base_rows = grade_candidates(
                    signature,
                    candidates,
                    weights=VARIANTS["base"]["weights"],
                    behavior_channel=VARIANTS["base"]["behavior_channel"],
                )
                chosen = base_rows[0] if base_rows else None
                truth_rows = [row for row in base_rows if candidate_truth[row["record_id"]]]
                instrumentation.append(
                    {
                        "specimen_id": pid,
                        "source_class": t["source_class"],
                        "technique_ids": t["techniques"],
                        "candidate_set_size": len(base_rows),
                        "truth_in_set": len(truth_rows),
                        "chosen": chosen
                        and {
                            "record_id": chosen["record_id"],
                            "source_class": chosen["source_class"],
                            "rank": chosen["rank"],
                            "composite": round(chosen["composite"], 6),
                            "decomposition": _round_decomp(chosen["decomposition"]),
                            "axes": chosen["axes"],
                            "truth_related": candidate_truth[chosen["record_id"]],
                            "cross_class": bool(
                                chosen["source_class"]
                                and chosen["source_class"] != t["source_class"]
                            ),
                            "twin": _is_twin(t, chosen, candidate_events, candidate_values),
                        },
                        "best_truth_candidate_in_set": truth_rows
                        and {
                            "record_id": truth_rows[0]["record_id"],
                            "source_class": truth_rows[0]["source_class"],
                            "rank": truth_rows[0]["rank"],
                            "composite": round(truth_rows[0]["composite"], 6),
                            "decomposition": _round_decomp(truth_rows[0]["decomposition"]),
                            "axes": truth_rows[0]["axes"],
                            "cross_class": bool(
                                truth_rows[0]["source_class"]
                                and truth_rows[0]["source_class"] != t["source_class"]
                            ),
                        },
                    }
                )
                if (i + 1) % 100 == 0:
                    print(f"  graded {i + 1}/{len(probes)}", flush=True)

                for name, spec in VARIANTS.items():
                    rows = (
                        base_rows
                        if name == "base"
                        else grade_candidates(
                            signature,
                            candidates,
                            weights=spec["weights"],
                            behavior_channel=spec["behavior_channel"],
                        )
                    )
                    verdict = _verdict(
                        rows, candidate_truth, t, candidate_events, candidate_values, thresholds
                    )
                    verdict["specimen_id"] = pid
                    per_variant[name].append(verdict)
        finally:
            snapshot.close()

    args.out.mkdir(parents=True, exist_ok=True)
    summary = _summary(per_variant)
    (args.out / "b1_summary.json").write_text(
        json.dumps(
            {
                "corpus": str(args.corpus),
                "arm_dir": str(args.arm_dir),
                "embed_url": args.embed_url,
                "probes": len(probes),
                "variants": dict(VARIANTS),
                "summary": summary,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    (args.out / "b1_instrumentation.json").write_text(
        json.dumps(instrumentation, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    for name, verdicts in per_variant.items():
        (args.out / f"b1_verdicts_{name}.json").write_text(
            json.dumps(verdicts, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    print(json.dumps(summary, indent=2, sort_keys=True))
    print(f"\nwritten under {args.out}")
    return 0


def _is_twin(
    probe_truth: dict[str, Any],
    chosen: dict[str, Any],
    candidate_events: dict[str, str],
    candidate_values: dict[str, list[str]],
) -> bool:
    """Evidence twin: identical raw evidence (events, or value terms) under two labels."""
    rid = chosen["record_id"]
    return candidate_events.get(rid) == probe_truth["events"] or (
        candidate_values.get(rid) == probe_truth["values"] and bool(probe_truth["values"])
    )


def _verdict(
    rows: list[dict[str, Any]],
    candidate_truth: dict[str, bool],
    probe_truth: dict[str, Any],
    candidate_events: dict[str, str],
    candidate_values: dict[str, list[str]],
    thresholds: dict[str, float],
) -> dict[str, Any]:
    if not rows:
        return {
            "graded": False,
            "related": False,
            "cross_source_related": False,
            "twin": False,
            "relationship": "ANOMALOUS_UNCLASSIFIED",
        }
    chosen = rows[0]
    relationship = cousin_engine._classify_relationship(  # noqa: SLF001 -- measurement harness
        chosen["composite"],
        chosen["confidence"],
        chosen["nonsemantic"],
        vetoed=False,
        thresholds=thresholds,
    )
    related = candidate_truth[chosen["record_id"]]
    cross = bool(chosen["source_class"] and chosen["source_class"] != probe_truth["source_class"])
    return {
        "graded": True,
        "related": related,
        "cross_source_related": related and cross,
        "cross_source_chosen": cross,
        "same_source_related": related and not cross,
        "relationship": relationship,
        "reference_id": chosen["record_id"],
        "twin": related and _is_twin(probe_truth, chosen, candidate_events, candidate_values),
    }


def _summary(per_variant: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    base = per_variant["base"]
    base_related = {v["specimen_id"]: v["related"] for v in base}
    base_cross = {v["specimen_id"]: v["cross_source_related"] for v in base}
    base_graded_rel = {
        v["specimen_id"]: v["related"] and v.get("relationship") != "ANOMALOUS_UNCLASSIFIED"
        for v in base
    }
    for name, verdicts in per_variant.items():
        # `related_graded` matches the cutover's primary definition (relationship not
        # ANOMALOUS_UNCLASSIFIED and a reference chosen); `related_all` counts every probe
        # whose top-ranked candidate is truth-related regardless of classification.
        out[name] = {
            "graded": sum(v["graded"] for v in verdicts),
            "related_all": sum(v["related"] for v in verdicts),
            "related_graded": sum(
                v["related"] for v in verdicts if v.get("relationship") != "ANOMALOUS_UNCLASSIFIED"
            ),
            "cross_source_related": sum(v["cross_source_related"] for v in verdicts),
            "same_source_related": sum(v.get("same_source_related", False) for v in verdicts),
            "cross_source_chosen": sum(v.get("cross_source_chosen", False) for v in verdicts),
            "twin_hits": sum(v.get("twin", False) for v in verdicts),
            "relationship_distribution": {
                k: sum(1 for v in verdicts if v.get("relationship") == k)
                for k in sorted({v.get("relationship") for v in verdicts})
            },
        }
    for name, verdicts in per_variant.items():
        if name == "base":
            continue
        rel = {v["specimen_id"]: v["related"] for v in verdicts}
        grel = {
            v["specimen_id"]: v["related"] and v.get("relationship") != "ANOMALOUS_UNCLASSIFIED"
            for v in verdicts
        }
        cro = {v["specimen_id"]: v["cross_source_related"] for v in verdicts}
        shared = sorted(set(base_related) & set(rel))

        def _paired_block(
            base_map: dict[str, bool], var_map: dict[str, bool], keys: list[str]
        ) -> dict[str, Any]:
            return {
                "base_only": sum(base_map[k] and not var_map[k] for k in keys),
                "variant_only": sum(var_map[k] and not base_map[k] for k in keys),
                "mcnemar_exact_p": round(
                    mcnemar_exact(
                        sum(base_map[k] and not var_map[k] for k in keys),
                        sum(var_map[k] and not base_map[k] for k in keys),
                    ),
                    5,
                ),
            }

        out[name]["paired_vs_base"] = {
            "related_all": _paired_block(base_related, rel, shared),
            "related_graded": _paired_block(base_graded_rel, grel, shared),
            "cross_source_related": _paired_block(base_cross, cro, shared),
        }
        if name != ADOPTED and ADOPTED in per_variant:
            adopted = per_variant[ADOPTED]
            a_rel = {v["specimen_id"]: v["related"] for v in adopted}
            a_grel = {
                v["specimen_id"]: v["related"] and v.get("relationship") != "ANOMALOUS_UNCLASSIFIED"
                for v in adopted
            }
            a_cro = {v["specimen_id"]: v["cross_source_related"] for v in adopted}
            out[name]["paired_vs_adopted"] = {
                "related_all": _paired_block(a_rel, rel, shared),
                "related_graded": _paired_block(a_grel, grel, shared),
                "cross_source_related": _paired_block(a_cro, cro, shared),
            }
    return out


def _round_decomp(decomp: dict[str, float | None]) -> dict[str, float | None]:
    return {k: (round(v, 6) if isinstance(v, float) else v) for k, v in decomp.items()}


if __name__ == "__main__":
    raise SystemExit(main())
