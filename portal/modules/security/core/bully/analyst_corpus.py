"""bully.analyst_corpus -- the analyst-grade corpus layer (TASK_BULLY_SA4).

The corpus stops being a benchmark and becomes the analyst's world: broad,
heterogeneous, mostly-unlabeled security data ingested without a label gate
(A1), benign/background volume as first-class context (A3), analyst-pivot
pairs from real co-occurrence as the near-twin ground truth (A6), proposed
structure recorded as hypotheses that never self-confirm (A2/A5), and
immutable hashed snapshots deduplicated on canonical embed text (A4/A5).

Cold (A9): no thresholds, weights, training, or refinement live here. This
module is pure compute over injected data plus the store integration seam
(caller supplies a ``store``); it never touches SQL or the network itself.

Label tiers (A1):

- ``T0`` authoritative  -- external per-entry/per-dataset labels. Scoreable.
- ``T1`` confirmed     -- reviewed and corroborated by an independent basis.
                        Scoreable.
- ``T2`` proposed      -- machine-clustered hypothesis, unconfirmed. Retrieval
                        only; a graded pair involving it is INDETERMINATE.
- ``T3`` unknown       -- context only (incl. benign/background). Retrieval
                        only; INDETERMINATE, never scored.

A machine-proposed relationship may never be promoted to ground truth by the
same system that proposed it (A2). ``HypothesisStore.confirm`` requires an
independent basis and records it; nothing auto-promotes.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
import uuid
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from . import config, signatures
from .organ import _canonical_record_text
from .source_adapters import adapt as adapt_source

T0_AUTHORITATIVE = "T0"
T1_CONFIRMED = "T1"
T2_PROPOSED = "T2"
T3_UNKNOWN = "T3"

LABEL_TIERS = (T0_AUTHORITATIVE, T1_CONFIRMED, T2_PROPOSED, T3_UNKNOWN)
SCOREABLE_TIERS = frozenset({T0_AUTHORITATIVE, T1_CONFIRMED})
# T2/T3 participate in retrieval (the haystack) but a graded pair involving
# them resolves INDETERMINATE -- never a hit or a miss (A1).
UNSCOREABLE_TIERS = frozenset({T2_PROPOSED, T3_UNKNOWN})

SOURCE_DOSSIER_SCHEMA = "SOURCE_DOSSIER_V1"
SOURCE_INGESTION_PLAN_SCHEMA = "SOURCE_INGESTION_PLAN_V1"
SNAPSHOT_SCHEMA = "ANALYST_CORPUS_SNAPSHOT_V1"

# Licenses that are a hard constraint for a self-hosted stack. Evaluation
# decides tier and priority -- NOT admission -- but an incompatible license
# is the one thing that gates admission (SA4.1, OTRF GPL-3.0 note).
_INCOMPATIBLE_LICENSE_MARKERS = ("gpl-3.0", "gpl-2.0", "agpl-3.0")

# Analyst-pivot pair bases (A6). Each basis is an independent, real
# co-occurrence signal -- never clustering output.
PIVOT_BASIS_SHARED_EXTERNAL_LABEL = "shared_external_technique_label"
PIVOT_BASIS_SHARED_ENTITY_WINDOW = "shared_entity_time_window"
PIVOT_BASIS_SIMULTANEOUS_CAPTURE = "simultaneous_multi_source_capture"
PIVOT_BASIS_VALUES = frozenset(
    {
        PIVOT_BASIS_SHARED_EXTERNAL_LABEL,
        PIVOT_BASIS_SHARED_ENTITY_WINDOW,
        PIVOT_BASIS_SIMULTANEOUS_CAPTURE,
    }
)

HYPOTHESIS_SCHEMA = "BULLY_HYPOTHESIS_V1"
PIVOT_LEDGER_SCHEMA = "BULLY_PIVOT_PAIRS_LEDGER_V1"

SNAPSHOT_CORPUS_NAME = "ANALYST_CORPUS_SNAPSHOT_V1"


# ---------------------------------------------------------------------------
# label tiers (A1)
# ---------------------------------------------------------------------------


def label_tier_for(labeling: str | None) -> str:
    """Map a declared labeling quality to a T0-T3 tier (A1).

    ``authoritative`` (external per-entry/per-dataset labels, e.g. attack_data
    ``data.yml``, per-entry ATT&CK sets) -> ``T0``;
    ``confirmed``/``reviewed``/``corroborated`` -> ``T1``;
    ``proposed``/``machine``/``clustered``/``unconfirmed`` -> ``T2``; anything
    else (unlabeled, benign/background, unknown) -> ``T3``.
    """
    normalized = str(labeling or "").strip().lower().replace("-", "_").replace("&", "_")
    if any(
        marker in normalized
        for marker in ("unconfirmed", "proposed", "machine", "clustered", "hypothesis")
    ):
        return T2_PROPOSED
    if any(
        marker in normalized for marker in ("authoritative", "per_entry", "per_dataset", "data_yml")
    ):
        return T0_AUTHORITATIVE
    if any(
        marker in normalized for marker in ("confirmed", "reviewed", "corroborated", "validated")
    ):
        return T1_CONFIRMED
    return T3_UNKNOWN


def tier_is_scoreable(tier: str) -> bool:
    """Only T0/T1 may serve as ground truth (A1)."""
    return tier in SCOREABLE_TIERS


def tier_resolution(probe_tier: str, reference_tier: str) -> str | None:
    """Resolve the scoreability of a graded pair by its label tiers.

    Returns ``None`` when both ends are scoreable (normal grading applies);
    returns ``"INDETERMINATE"`` when either end is T2/T3 -- such a pair can
    participate in retrieval but is never a hit or a miss (A1).
    """
    if probe_tier in SCOREABLE_TIERS and reference_tier in SCOREABLE_TIERS:
        return None
    return "INDETERMINATE"


def resolve_pair_band(
    probe_tier: str,
    reference_tier: str,
    relationship: str,
    response: str,
) -> str:
    """Discovery-lane band for a pair, honouring label-tier scoreability.

    When either end is T2/T3 the pair resolves INDETERMINATE regardless of
    the engine's relationship/response verdicts -- a benign-only or
    unconfirmed neighborhood can therefore never manufacture a DISCOVERY
    (A1/A3). Otherwise the ``DISCOVERY_BASELINE_V1`` band taxonomy applies.
    """
    tiered = tier_resolution(probe_tier, reference_tier)
    if tiered == "INDETERMINATE":
        return "INDETERMINATE"
    if relationship == "SAME" and response in ("MISSED", "NEAR_MISS"):
        return "REGRESSION"
    if response == "COVERED":
        return "FLOOR"
    if relationship in ("SIMILAR", "NEW", "ANOMALOUS_UNCLASSIFIED") and response in (
        "MISSED",
        "NEAR_MISS",
    ):
        return "DISCOVERY"
    if relationship == "DIFFERENT" and response in ("MISSED", "NEAR_MISS"):
        return "NO-RELATION"
    return "INDETERMINATE"


# ---------------------------------------------------------------------------
# source dossiers + ranked ingestion plan (SA4.1)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SourceDossier:
    """One evaluated candidate source: license/format/parse cost, achievable
    label tier, class contribution, benign volume, overlap. Evaluation decides
    tier and priority -- not whether the data is allowed in (SA4.1)."""

    source_id: str
    name: str
    source_class: str
    license: str
    license_compatible: bool
    format: str
    parse_cost: str  # LOW / MEDIUM / HIGH
    achievable_label_tier: str  # T0-T3
    class_contribution: str
    benign_volume: str
    overlap_with_existing: str
    notes: str = ""
    status: str = "ADMIT"  # ADMIT / FLAG

    def __post_init__(self) -> None:
        if not self.source_id:
            raise ValueError("source_id is required")
        if self.achievable_label_tier not in LABEL_TIERS:
            raise ValueError(f"unknown label tier: {self.achievable_label_tier!r}")
        if self.parse_cost not in {"LOW", "MEDIUM", "HIGH"}:
            raise ValueError(f"unknown parse cost: {self.parse_cost!r}")
        if self.status not in {"ADMIT", "FLAG"}:
            raise ValueError(f"unknown dossier status: {self.status!r}")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def license_is_compatible(license_name: str) -> bool:
    """A license is incompatible when it is copyleft for a self-hosted stack
    (SA4.1; the OTRF GPL-3.0 constraint)."""
    return not any(
        marker in str(license_name).strip().lower() for marker in _INCOMPATIBLE_LICENSE_MARKERS
    )


def validate_dossier_schema(dossier: SourceDossier) -> dict[str, Any]:
    """Validate a dossier against SOURCE_DOSSIER_V1 (schema + policy)."""
    errors: list[str] = []
    expected_keys = {
        "source_id",
        "name",
        "source_class",
        "license",
        "license_compatible",
        "format",
        "parse_cost",
        "achievable_label_tier",
        "class_contribution",
        "benign_volume",
        "overlap_with_existing",
    }
    payload = dossier.to_dict()
    for key in expected_keys:
        if key not in payload or payload.get(key) in (None, ""):
            errors.append(f"missing required field: {key}")
    if dossier.achievable_label_tier not in LABEL_TIERS:
        errors.append(f"unknown achievable_label_tier: {dossier.achievable_label_tier!r}")
    if dossier.license_compatible and not license_is_compatible(dossier.license):
        errors.append(
            f"license {dossier.license!r} is incompatible but marked compatible -- "
            "must be flagged, not silently admitted"
        )
    if not dossier.license_compatible and license_is_compatible(dossier.license):
        errors.append(f"license {dossier.license!r} is compatible but marked incompatible")
    return {
        "schema": SOURCE_DOSSIER_SCHEMA,
        "source_id": dossier.source_id,
        "valid": not errors,
        "errors": errors,
    }


def _tier_rank(tier: str) -> int:
    return LABEL_TIERS.index(tier)


def rank_ingestion_plan(dossiers: Iterable[SourceDossier]) -> dict[str, Any]:
    """Emit the ranked ingestion plan: every admissible source sorted by
    priority (achievable label tier, then class contribution, then overlap),
    and every hard-flagged source (incompatible license) separated out --
    never silently ingested (SA4.1)."""
    all_dossiers = list(dossiers)
    ranked: list[dict[str, Any]] = []
    flagged: list[dict[str, Any]] = []
    for dossier in sorted(all_dossiers, key=lambda item: item.source_id):
        entry = {
            **dossier.to_dict(),
            "priority": _tier_rank(dossier.achievable_label_tier),
            "dossier_valid": validate_dossier_schema(dossier)["valid"],
        }
        if not dossier.license_compatible:
            flagged.append(
                {
                    "source_id": dossier.source_id,
                    "name": dossier.name,
                    "license": dossier.license,
                    "reason": "license_incompatible",
                    "priority": None,
                }
            )
            continue
        if dossier.status == "FLAG":
            entry["advisory_flag"] = True
        ranked.append(entry)
    ranked.sort(key=lambda item: (item["priority"], item["source_class"], item["source_id"]))
    return {
        "schema": SOURCE_INGESTION_PLAN_SCHEMA,
        "ranked": ranked,
        "flagged": flagged,
        "evaluated": len(all_dossiers),
        "reconciled": len(ranked) + len(flagged) == len(all_dossiers),
    }


# Research findings for the candidate sources in the SA4 task (evaluation
# input, not bulk ingest -- the dossiers record the license call and tier.)
CANDIDATE_SOURCE_DOSSIERS: tuple[SourceDossier, ...] = (
    SourceDossier(
        source_id="splunk_attack_data",
        name="splunk/attack_data",
        source_class="endpoint",
        license="Apache-2.0",
        license_compatible=True,
        format="evtx/json/log + data.yml",
        parse_cost="MEDIUM",
        achievable_label_tier=T0_AUTHORITATIVE,
        class_contribution="endpoint (windows/linux/web/docker)",
        benign_volume="low",
        overlap_with_existing="backbone -- already in use",
        notes="keep as the endpoint backbone",
    ),
    SourceDossier(
        source_id="flaws_cloud_cloudtrail",
        name="flaws.cloud CloudTrail",
        source_class="cloud",
        license="public",
        license_compatible=True,
        format="json CloudTrail records",
        parse_cost="MEDIUM",
        achievable_label_tier=T0_AUTHORITATIVE,
        class_contribution="AWS cloud/identity",
        benign_volume="high",
        overlap_with_existing="none",
        notes="~3.5yrs, 240MB, real (non-simulated) attackers -- highest truth-we-did-not-plant value",
    ),
    SourceDossier(
        source_id="invictus_ir_aws_dataset",
        name="invictus-ir/aws_dataset",
        source_class="cloud",
        license="MIT",
        license_compatible=True,
        format="json (Stratus Red Team)",
        parse_cost="LOW",
        achievable_label_tier=T1_CONFIRMED,
        class_contribution="AWS cloud (tool-attributable)",
        benign_volume="medium",
        overlap_with_existing="none",
        notes="tool-attributable -> labels derivable",
    ),
    SourceDossier(
        source_id="arxiv_2606_18190",
        name="arXiv 2606.18190 multi-source",
        source_class="multi",
        license="CC-BY",
        license_compatible=True,
        format="parquet/json sessions",
        parse_cost="HIGH",
        achievable_label_tier=T0_AUTHORITATIVE,
        class_contribution="system+network+browser (870 sessions / ~2.3M events)",
        benign_volume="high",
        overlap_with_existing="partial (endpoint)",
        notes="per-entry ATT&CK, 12 tactics/53 techniques; simultaneous capture -> real cross-class pivot pairs (A6)",
    ),
    SourceDossier(
        source_id="otrf_security_datasets",
        name="OTRF Security-Datasets",
        source_class="multi",
        license="GPL-3.0",
        license_compatible=False,
        format="evtx/json + Sigma",
        parse_cost="MEDIUM",
        achievable_label_tier=T0_AUTHORITATIVE,
        class_contribution="multi-platform (sibling to attack_data)",
        benign_volume="medium",
        overlap_with_existing="high (sibling to attack_data)",
        notes="GPL-3.0 -- license review required before bulk ingest",
        status="FLAG",
    ),
    SourceDossier(
        source_id="cloudtrail_attack_research",
        name="CloudTrail ATT&CK research set",
        source_class="cloud",
        license="public",
        license_compatible=True,
        format="json CloudTrail records",
        parse_cost="LOW",
        achievable_label_tier=T0_AUTHORITATIVE,
        class_contribution="AWS (9 techniques / 8 tactics)",
        benign_volume="medium",
        overlap_with_existing="none",
        notes="small, precise",
    ),
    SourceDossier(
        source_id="darpa_optc_tc3",
        name="DARPA OpTC / TC3",
        source_class="multi",
        license="research (DARPA)",
        license_compatible=True,
        format="host+network provenance graph",
        parse_cost="HIGH",
        achievable_label_tier=T2_PROPOSED,
        class_contribution="host+network provenance (red-vs-blue engagement)",
        benign_volume="high",
        overlap_with_existing="partial (endpoint)",
        notes="large, deep provenance; labels from engagement are engagement-relative -> T2",
    ),
)


# ---------------------------------------------------------------------------
# broad ingestion with label tiering (SA4.2, A1/A7)
# ---------------------------------------------------------------------------


def stamp_specimen(
    specimen: dict[str, Any],
    *,
    label_tier: str,
    provenance: dict[str, Any],
    trust_tier: str,
    source_lane: str = "external_corpus",
) -> dict[str, Any]:
    """Stamp a specimen with its label tier (T0-T3), provenance, trust tier,
    and scoreability. Unmapped/unlabeled specimens are stamped, never dropped
    (A7)."""
    if label_tier not in LABEL_TIERS:
        raise ValueError(f"unknown label tier: {label_tier!r}")
    return {
        **specimen,
        "label_tier": label_tier,
        "scoreable": tier_is_scoreable(label_tier),
        "provenance": dict(provenance),
        "trust_tier": trust_tier,
        "source_lane": source_lane,
    }


def ingest_events(
    events: list[dict[str, Any] | str],
    *,
    specimen_id: str,
    sourcetype: str,
    techniques: tuple[str, ...] = (),
    labeling: str | None = None,
    label_tier: str | None = None,
    provenance: dict[str, Any] | None = None,
    trust_tier: str = "imported_observed",
    source_lane: str = "external_corpus",
    target_host: str = "corpus-external",
) -> dict[str, Any]:
    """Ingest one dataset's events into a tiered specimen.

    The class is resolved through the source-adapter seam: known shapes keep
    their class; an unmapped shape routes through the fallback adapter and the
    missing dimensions stay absent (honest completeness, never padded -- A7).
    The specimen is stamped with its label tier (from ``labeling`` unless
    ``label_tier`` is given explicitly) plus provenance and trust tier (A1).
    """
    tier = label_tier if label_tier is not None else label_tier_for(labeling)
    view = adapt_source(
        events,
        {
            "sourcetype": sourcetype,
            "techniques": techniques,
            "origin": str((provenance or {}).get("origin") or ""),
            "trust_tier": trust_tier,
        },
    )
    shape = dict(view.get("telemetry_shape") or {})
    source_class = shape.get("source_class") or ""
    if not source_class:
        sourcetypes = list(shape.get("sourcetypes") or ())
        if len(sourcetypes) == 1:
            source_class = str(sourcetypes[0])
    adapter_status = shape.get("adapter_status", "mapped")
    engine_view = {
        "episode_view": {"episode_id": specimen_id, "target_host": target_host},
        "telemetry_view": view,
        "evidence_origin": "external_corpus",
        "trust_tier": trust_tier,
        "provenance": "external_corpus",
    }
    entry = {
        "specimen_id": specimen_id,
        "source_lane": source_lane,
        "source_class": source_class,
        "adapter_status": adapter_status,
        "data_yml_techniques": list(techniques),
        "engine_view": engine_view,
        "evidence_ref": f"{specimen_id}.json",
    }
    return stamp_specimen(
        entry,
        label_tier=tier,
        provenance={
            "labeling": labeling or "unknown",
            "source": provenance.get("source_id") if provenance else None,
            **(provenance if provenance else {}),
        },
        trust_tier=trust_tier,
        source_lane=source_lane,
    )


def census_specimens(specimens: list[dict[str, Any]]) -> dict[str, Any]:
    """Census every ingested specimen: per-class, per-tier, per-lane, and
    unmapped counts. Reconciles to the input so nothing is silently dropped
    (A7)."""
    per_class: dict[str, int] = {}
    per_tier: dict[str, int] = {}
    per_lane: dict[str, int] = {}
    unmapped: list[str] = []
    for specimen in specimens:
        source_class = str(specimen.get("source_class") or "")
        per_class[source_class] = per_class.get(source_class, 0) + 1
        tier = str(specimen.get("label_tier") or T3_UNKNOWN)
        per_tier[tier] = per_tier.get(tier, 0) + 1
        lane = str(specimen.get("source_lane") or "external_corpus")
        per_lane[lane] = per_lane.get(lane, 0) + 1
        if specimen.get("adapter_status") == "unmapped":
            unmapped.append(str(specimen.get("specimen_id")))
    return {
        "schema": "ANALYST_CORPUS_CENSUS_V1",
        "total": len(specimens),
        "per_class_counts": dict(sorted(per_class.items())),
        "tier_distribution": dict(sorted(per_tier.items())),
        "per_lane_counts": dict(sorted(per_lane.items())),
        "unmapped_specimens": sorted(unmapped),
        "unmapped_count": len(unmapped),
        "reconciled": sum(per_class.values()) == len(specimens),
    }


# ---------------------------------------------------------------------------
# benign/background corpus (SA4.3, A3)
# ---------------------------------------------------------------------------


def ingest_benign(
    events: list[dict[str, Any] | str],
    *,
    specimen_id: str,
    sourcetype: str,
    provenance: dict[str, Any] | None = None,
    trust_tier: str = "imported_observed",
    techniques: tuple[str, ...] = (),
) -> dict[str, Any]:
    """Ingest benign/background volume deliberately (A3). Benign specimens are
    always ``T3`` -- context only, retrievable, never scoreable."""
    return ingest_events(
        events,
        specimen_id=specimen_id,
        sourcetype=sourcetype,
        techniques=techniques,
        label_tier=T3_UNKNOWN,
        provenance=provenance or {"origin": "benign_corpus", "labeling": "benign"},
        trust_tier=trust_tier,
        source_lane="benign",
    )


def benign_ratio(specimens: list[dict[str, Any]]) -> float:
    """The realized benign:attack ratio as a measured property of the corpus
    (A3) -- benign volume / total volume, never a target invented up front."""
    total = len(specimens)
    if not total:
        return 0.0
    benign = sum(1 for item in specimens if item.get("source_lane") == "benign")
    return round(benign / total, 6)


def per_class_benign_coverage(specimens: list[dict[str, Any]]) -> dict[str, Any]:
    """Benign count and fraction per source class (A3)."""
    per_class: dict[str, dict[str, int]] = {}
    for specimen in specimens:
        source_class = str(specimen.get("source_class") or "")
        bucket = per_class.setdefault(source_class, {"total": 0, "benign": 0})
        bucket["total"] += 1
        if specimen.get("source_lane") == "benign":
            bucket["benign"] += 1
    return {
        source_class: {
            "benign": bucket["benign"],
            "total": bucket["total"],
            "benign_fraction": round(bucket["benign"] / bucket["total"], 6)
            if bucket["total"]
            else 0.0,
        }
        for source_class, bucket in sorted(per_class.items())
    }


# ---------------------------------------------------------------------------
# analyst-pivot pairs (SA4.6->SA4.4, A6)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PivotPair:
    """A genuinely-related pair a human would pivot between, identified from
    REAL co-occurrence with its independent basis recorded -- never forged,
    never derived from clustering output (A2/A6)."""

    pair_id: str
    left_specimen_id: str
    right_specimen_id: str
    basis: str
    basis_detail: str
    cross_class: bool
    left_source_class: str = ""
    right_source_class: str = ""

    def __post_init__(self) -> None:
        if self.basis not in PIVOT_BASIS_VALUES:
            raise ValueError(f"unknown pivot basis: {self.basis!r}")
        if not self.basis_detail:
            raise ValueError("pivot pairs require an independent basis detail")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _specimen_tier(specimen: dict[str, Any]) -> str:
    return str(specimen.get("label_tier") or T3_UNKNOWN)


def _specimen_techniques(specimen: dict[str, Any]) -> frozenset[str]:
    mappings = (
        specimen.get("engine_view", {}).get("telemetry_view", {}).get("attack_mappings") or ()
    )
    return frozenset(
        str(item.get("technique_id"))
        for item in mappings
        if isinstance(item, dict) and item.get("technique_id")
    )


def _external_authoritative_labels(specimen: dict[str, Any]) -> frozenset[str]:
    """Independent external labels (T0/T1 only) -- a machine-proposed T2 label
    can never ground a pivot pair (A2)."""
    if _specimen_tier(specimen) not in SCOREABLE_TIERS:
        return frozenset()
    provenance = specimen.get("provenance") or {}
    if provenance.get("labeling") not in {"authoritative", "confirmed", "reviewed", "corroborated"}:
        return frozenset()
    techniques = specimen.get("data_yml_techniques") or _specimen_techniques(specimen)
    return frozenset(str(value) for value in techniques)


def _pairs_from_shared_external_labels(
    specimens: list[dict[str, Any]],
) -> list[PivotPair]:
    """Pairs grounded in a shared authoritative/confirmed external ATT&CK
    label (A6: shared external technique labels; A2: independent basis)."""
    by_technique: dict[str, list[dict[str, Any]]] = {}
    for specimen in specimens:
        labels = _external_authoritative_labels(specimen)
        if not labels:
            continue
        for technique_id in labels:
            by_technique.setdefault(technique_id, []).append(specimen)
    pairs: list[PivotPair] = []
    for technique_id in sorted(by_technique):
        members = sorted(by_technique[technique_id], key=lambda item: str(item["specimen_id"]))
        for left_index, left in enumerate(members):
            for right in members[left_index + 1 :]:
                pairs.append(
                    _build_pair(left, right, PIVOT_BASIS_SHARED_EXTERNAL_LABEL, technique_id)
                )
    return pairs


def _build_pair(
    left: dict[str, Any],
    right: dict[str, Any],
    basis: str,
    basis_detail: str,
) -> PivotPair:
    left_id = str(left["specimen_id"])
    right_id = str(right["specimen_id"])
    left_source = str(left.get("source_class") or "")
    right_source = str(right.get("source_class") or "")
    ordered = sorted((left_id, right_id))
    pair_id = hashlib.sha256(f"{basis}:{basis_detail}:{':'.join(ordered)}".encode()).hexdigest()[
        :16
    ]
    return PivotPair(
        pair_id=pair_id,
        left_specimen_id=ordered[0],
        right_specimen_id=ordered[1],
        basis=basis,
        basis_detail=basis_detail,
        cross_class=bool(left_source and right_source and left_source != right_source),
        left_source_class=left_source,
        right_source_class=right_source,
    )


def _pairs_from_co_occurrence(
    co_occurrence: dict[str, dict[str, Any]],
) -> list[PivotPair]:
    """Pairs from real shared-entity/time-window co-occurrence (A6). The
    caller supplies the observations from a real join (SIEM account/host/asset
    pivots, simultaneous multi-source capture), each mapping a basis detail to
    the specimen ids observed together."""
    pairs: list[PivotPair] = []
    for basis, detail in sorted(co_occurrence.items()):
        specimen_ids = [str(value) for value in (detail.get("specimen_ids") or ())]
        for left_index, left_id in enumerate(sorted(set(specimen_ids))):
            for right_id in sorted(set(specimen_ids))[left_index + 1 :]:
                pairs.append(
                    PivotPair(
                        pair_id=hashlib.sha256(
                            f"{basis}:{detail.get('detail', '')}:{left_id}:{right_id}".encode()
                        ).hexdigest()[:16],
                        left_specimen_id=left_id,
                        right_specimen_id=right_id,
                        basis=basis,
                        basis_detail=str(detail.get("detail") or basis),
                        cross_class=False,
                    )
                )
    return sorted(pairs, key=lambda item: item.pair_id)


def identify_pivot_pairs(
    specimens: list[dict[str, Any]],
    *,
    co_occurrence: dict[str, dict[str, Any]] | None = None,
) -> tuple[PivotPair, ...]:
    """Identify genuinely-related pairs from REAL co-occurrence only (A6):

    - shared authoritative/confirmed external ATT&CK labels (independent),
    - shared entity/time-window observations the caller supplies from a real
      telemetry join (``co_occurrence``),
    - simultaneous multi-source capture recorded in provenance.

    No pair derives from clustering output (A2): machine-proposed (T2)
    relationships are never accepted as a basis, and cross-class pairs are
    counted explicitly.
    """
    pairs: list[PivotPair] = []
    pairs.extend(_pairs_from_shared_external_labels(specimens))
    pairs.extend(_pairs_from_co_occurrence(co_occurrence or {}))

    by_capture: dict[str, list[dict[str, Any]]] = {}
    for specimen in specimens:
        provenance = specimen.get("provenance") or {}
        capture_id = provenance.get("capture_id")
        if capture_id:
            by_capture.setdefault(str(capture_id), []).append(specimen)
    for capture_id in sorted(by_capture):
        members = sorted(by_capture[capture_id], key=lambda item: str(item["specimen_id"]))
        for left_index, left in enumerate(members):
            for right in members[left_index + 1 :]:
                pairs.append(
                    _build_pair(
                        left,
                        right,
                        PIVOT_BASIS_SIMULTANEOUS_CAPTURE,
                        f"capture:{capture_id}",
                    )
                )

    deduped: dict[tuple[str, str], PivotPair] = {}
    for pair in sorted(pairs, key=lambda item: (item.pair_id, item.basis)):
        key = (pair.left_specimen_id, pair.right_specimen_id)
        if key not in deduped:
            deduped[key] = pair
    return tuple(sorted(deduped.values(), key=lambda item: item.pair_id))


class PivotPairLedger:
    """Append-only, hash-chained ledger sealing pivot pairs with their
    independent basis (A6). Mirror of ``specimen_ledger``'s sealing discipline
    for scorer-side pair truth."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = Path(root) if root is not None else config.hunt_dir() / "specimens"
        self.path = self.root / "pivot_pairs.jsonl"

    def _rows(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        rows: list[dict[str, Any]] = []
        previous = ""
        for sequence, line in enumerate(
            self.path.read_text(encoding="utf-8").splitlines(), start=1
        ):
            if not line.strip():
                continue
            row = json.loads(line)
            payload = {
                "schema": row.get("schema"),
                "sequence": row.get("sequence"),
                "previous_hash": row.get("previous_hash"),
                "pair": row.get("pair"),
            }
            expected = hashlib.sha256(
                json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest()
            if (
                row.get("schema") != PIVOT_LEDGER_SCHEMA
                or row.get("sequence") != sequence
                or row.get("previous_hash") != previous
                or row.get("record_hash") != expected
            ):
                raise RuntimeError(f"pivot-pair ledger seal broken at sequence {sequence}")
            previous = expected
            rows.append(row)
        return rows

    def record(self, pair: PivotPair) -> dict[str, Any]:
        body = pair.to_dict()
        rows = self._rows()
        existing = {row["pair"]["pair_id"]: row["pair"] for row in rows}.get(pair.pair_id)
        if existing is not None:
            if existing != body:
                raise ValueError(f"pivot pair already sealed with different truth: {pair.pair_id}")
            return dict(existing)
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        payload = {
            "schema": PIVOT_LEDGER_SCHEMA,
            "sequence": len(rows) + 1,
            "previous_hash": rows[-1]["record_hash"] if rows else "",
            "pair": body,
        }
        sealed = {
            **payload,
            "record_hash": hashlib.sha256(
                json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest(),
        }
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(sealed, sort_keys=True, separators=(",", ":")) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        self.path.chmod(0o600)
        return dict(body)

    def records(self) -> tuple[dict[str, Any], ...]:
        return tuple(dict(row["pair"]) for row in self._rows())

    def seal_pairs(self, pairs: Iterable[PivotPair]) -> int:
        sealed = 0
        for pair in pairs:
            self.record(pair)
            sealed += 1
        return sealed


# ---------------------------------------------------------------------------
# proposed-structure lane (SA4.5, A2)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Hypothesis:
    """A machine-proposed structure (cluster / candidate relationship /
    recurring type) recorded as a HYPOTHESIS, never as a label (A2)."""

    hypothesis_id: str
    kind: str  # cluster | candidate_relationship | recurring_type
    subject: str
    detail: dict[str, Any] = field(default_factory=dict)
    source_proposal: str = "machine"
    confirmed: bool = False
    basis: str | None = None
    basis_evidence: dict[str, Any] = field(default_factory=dict)
    promoted_to_tier: str | None = None
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class HypothesisStore:
    """Append-only store for proposed structure. A proposal NEVER auto-promotes;
    confirmation requires an independent basis and records it (A2). Only a
    confirmed hypothesis may promote T2->T1, and scored reports exclude
    unconfirmed proposals (SA4.5)."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = (
            Path(path) if path is not None else config.hunt_dir() / "specimens" / "hypotheses.jsonl"
        )
        self._rows_cache: list[dict[str, Any]] | None = None

    def _rows(self) -> list[dict[str, Any]]:
        if self._rows_cache is not None:
            return self._rows_cache
        if not self.path.exists():
            self._rows_cache = []
            return self._rows_cache
        rows = [
            json.loads(line)
            for line in self.path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        self._rows_cache = rows
        return rows

    def propose(
        self,
        *,
        kind: str,
        subject: str,
        detail: dict[str, Any],
        source_proposal: str = "machine",
    ) -> dict[str, Any]:
        """Record a proposed structure as an unconfirmed hypothesis."""
        if kind not in {"cluster", "candidate_relationship", "recurring_type"}:
            raise ValueError(f"unknown hypothesis kind: {kind!r}")
        hypothesis = Hypothesis(
            hypothesis_id=f"hyp-{uuid.uuid4().hex[:12]}",
            kind=kind,
            subject=subject,
            detail=dict(detail),
            source_proposal=source_proposal,
        )
        self._append(hypothesis)
        return hypothesis.to_dict()

    def _append(self, hypothesis: Hypothesis) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(
                json.dumps(hypothesis.to_dict(), sort_keys=True, separators=(",", ":")) + "\n"
            )
            handle.flush()
            os.fsync(handle.fileno())
        self.path.chmod(0o600)
        self._rows_cache = None

    def confirm(
        self, hypothesis_id: str, *, basis: str, basis_evidence: dict[str, Any]
    ) -> dict[str, Any]:
        """Confirm a proposed hypothesis. Requires an independent basis --
        a human confirmation, an external label, or corroborating evidence the
        clustering did not consume -- and records it (A2). No basis, no
        promotion."""
        if not basis or not str(basis).strip():
            raise ValueError("[GATE] hypothesis confirmation requires an independent basis")
        rows = self._rows()
        for row in rows:
            if row.get("hypothesis_id") != hypothesis_id:
                continue
            if row.get("confirmed"):
                raise ValueError(f"hypothesis already confirmed: {hypothesis_id}")
            row["confirmed"] = True
            row["basis"] = str(basis)
            row["basis_evidence"] = dict(basis_evidence)
            row["promoted_to_tier"] = T1_CONFIRMED
            self._rewrite(rows)
            return dict(row)
        raise KeyError(f"unknown hypothesis: {hypothesis_id}")

    def _rewrite(self, rows: list[dict[str, Any]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with self.path.open("w", encoding="utf-8") as handle:
            for row in rows:
                handle.write(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        self.path.chmod(0o600)
        self._rows_cache = None

    def proposals(self) -> tuple[dict[str, Any], ...]:
        return tuple(dict(row) for row in self._rows())

    def confirmed(self) -> tuple[dict[str, Any], ...]:
        return tuple(dict(row) for row in self._rows() if row.get("confirmed"))

    def unconfirmed(self) -> tuple[dict[str, Any], ...]:
        return tuple(dict(row) for row in self._rows() if not row.get("confirmed"))

    def scoreable_labels(self) -> tuple[dict[str, Any], ...]:
        """Only confirmed proposals may serve as scoreable (T1) ground truth;
        scored reports must exclude unconfirmed proposals (SA4.5)."""
        return tuple(
            dict(row)
            for row in self._rows()
            if row.get("confirmed") and row.get("promoted_to_tier") in SCOREABLE_TIERS
        )


# ---------------------------------------------------------------------------
# immutable hashed snapshot + dedupe (SA4.6, A4/A5/A8)
# ---------------------------------------------------------------------------


def canonical_embed_text(specimen: dict[str, Any]) -> str:
    """The canonical embed text a specimen projects to in the Organ
    projection (A5). Deduplication and identity controls run on this text --
    the same text the projection embeds, so distinct-text collapse is the
    exact property measured at SA3.5."""
    engine_view = specimen["engine_view"]
    signature = signatures.build_signature(
        engine_view["episode_view"], engine_view["telemetry_view"]
    )
    record = signatures.reference_record_fields(signature)
    return _canonical_record_text(record)


def snapshot_composition(
    specimens: list[dict[str, Any]], pairs: tuple[PivotPair, ...]
) -> dict[str, Any]:
    """Composition of a snapshot: per-class counts, tier distribution, benign
    ratio, distinct-text collapse (A5), and pivot-pair counts (A6)."""
    per_class: dict[str, int] = {}
    per_tier: dict[str, int] = {}
    distinct_texts: dict[str, list[str]] = {}
    for specimen in specimens:
        source_class = str(specimen.get("source_class") or "")
        per_class[source_class] = per_class.get(source_class, 0) + 1
        tier = str(specimen.get("label_tier") or T3_UNKNOWN)
        per_tier[tier] = per_tier.get(tier, 0) + 1
        distinct_texts.setdefault(canonical_embed_text(specimen), []).append(
            str(specimen["specimen_id"])
        )
    distinct_count = len(distinct_texts)
    duplicate_texts = sum(len(ids) - 1 for ids in distinct_texts.values() if len(ids) > 1)
    cross_class_pairs = sum(1 for pair in pairs if pair.cross_class)
    return {
        "specimen_count": len(specimens),
        "per_class_counts": dict(sorted(per_class.items())),
        "tier_distribution": dict(sorted(per_tier.items())),
        "benign_ratio": benign_ratio(specimens),
        "distinct_text_collapse": {
            "specimen_count": len(specimens),
            "distinct_texts": distinct_count,
            "duplicate_texts": duplicate_texts,
            "max_copies": max((len(ids) for ids in distinct_texts.values()), default=0),
        },
        "pivot_pair_counts": {
            "total": len(pairs),
            "cross_class": cross_class_pairs,
        },
    }


def take_snapshot(
    specimens: list[dict[str, Any]],
    *,
    pairs: tuple[PivotPair, ...] = (),
    name: str = SNAPSHOT_CORPUS_NAME,
) -> dict[str, Any]:
    """Take an immutable, hashed snapshot deduplicated on canonical embed text
    (A4/A5). The corpus itself is never frozen -- it stays appendable; the
    snapshot is the frozen view measurement runs against."""
    deduped: dict[str, dict[str, Any]] = {}
    for specimen in sorted(specimens, key=lambda item: str(item["specimen_id"])):
        deduped.setdefault(canonical_embed_text(specimen), specimen)
    distinct_specimens = [deduped[text] for text in sorted(deduped)]
    composition = snapshot_composition(specimens, pairs)
    payload = {
        "schema": SNAPSHOT_SCHEMA,
        "name": name,
        "composition": composition,
        "distinct_specimens": distinct_specimens,
        "pivot_pairs": [pair.to_dict() for pair in sorted(pairs, key=lambda item: item.pair_id)],
        "created_at": time.time(),
    }
    snapshot_hash = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return {**payload, "snapshot_hash": snapshot_hash}


def verify_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Verify a snapshot's hash and schema. Returns a verdict; a hash mismatch
    or unknown schema is a broken snapshot (A4)."""
    if snapshot.get("schema") != SNAPSHOT_SCHEMA:
        return {
            "schema": SNAPSHOT_SCHEMA,
            "valid": False,
            "errors": [f"unknown snapshot schema: {snapshot.get('schema')!r}"],
        }
    payload = {
        key: snapshot.get(key)
        for key in (
            "schema",
            "name",
            "composition",
            "distinct_specimens",
            "pivot_pairs",
            "created_at",
        )
    }
    observed = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    errors = []
    if observed != snapshot.get("snapshot_hash"):
        errors.append("snapshot hash mismatch")
    return {"schema": SNAPSHOT_SCHEMA, "valid": not errors, "errors": errors}


def save_snapshot(snapshot: dict[str, Any], output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"{snapshot.get('name') or SNAPSHOT_CORPUS_NAME}.json"
    path.write_text(json.dumps(snapshot, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def load_snapshot(path: Path) -> dict[str, Any]:
    snapshot: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    verdict = verify_snapshot(snapshot)
    if not verdict["valid"]:
        raise ValueError(f"corrupt analyst corpus snapshot: {verdict['errors']}")
    return snapshot


# ---------------------------------------------------------------------------
# corpus -> engine integration (SA4.6, A8)
# ---------------------------------------------------------------------------


def coverage_cell_for_class(
    source_class: str,
    *,
    scoreable_fraction: float,
    cost_ref: str = "hunt-1",
    scenario: str = "analyst corpus class coverage",
) -> dict[str, Any]:
    """One targeting coverage cell per ingested source class. The prior is the
    honest measured scoreable fraction of that class (how much of its corpus is
    trusted ground truth), clamped so every cell stays rankable."""
    prior = round(max(0.05, min(0.95, float(scoreable_fraction or 0.0))), 4)
    return {
        "cell_id": f"cell-corpus-{source_class}",
        "subject": source_class,
        "scenario": scenario,
        "cost_ref": cost_ref,
        "prior": prior,
        "authorized": True,
        "ready": True,
        "healthy": True,
        "locked": False,
        "corpus_sourced": True,
    }


def _scoreable_fraction(specimens: list[dict[str, Any]], source_class: str) -> float:
    members = [s for s in specimens if s.get("source_class") == source_class]
    if not members:
        return 0.5
    return sum(
        1 for s in members if tier_is_scoreable(str(s.get("label_tier") or T3_UNKNOWN))
    ) / len(members)


def populate_coverage_cells(
    store: Any,
    specimens: list[dict[str, Any]],
    *,
    cost_ref: str = "hunt-1",
) -> int:
    """Populate ``coverage_cells`` from ingested classes so ``targeting.select``
    can rank them (A8). Returns the number of cells written/updated."""
    classes = {str(s.get("source_class")) for s in specimens if s.get("source_class")}
    written = 0
    for source_class in sorted(classes):
        cell = coverage_cell_for_class(
            source_class,
            scoreable_fraction=_scoreable_fraction(specimens, source_class),
            cost_ref=cost_ref,
        )
        if store.coverage_cell_put(cell):
            written += 1
    return written


def populate_known_state(
    store: Any,
    specimens: list[dict[str, Any]],
    *,
    hunt_id: str | None = None,
    snapshot_ref: str = "",
) -> int:
    """Populate ``known_state`` with corpus-coverage entries per ingested class
    (A8). Entries are ``IMPORTED_OBSERVED`` context -- they never adjust a
    targeting posterior (only VALIDATED/OPERATOR_CONFIRMED does), which keeps
    corpus data honest as context, not validated truth."""
    classes = {str(s.get("source_class")) for s in specimens if s.get("source_class")}
    entries = 0
    for source_class in sorted(classes):
        members = [s for s in specimens if s.get("source_class") == source_class]
        scoreable = sum(
            1 for s in members if tier_is_scoreable(str(s.get("label_tier") or T3_UNKNOWN))
        )
        store.update_known_state(
            subject=source_class,
            kind="corpus_coverage",
            evidence={
                "corpus_snapshot_ref": snapshot_ref,
                "specimen_count": len(members),
                "scoreable_count": scoreable,
                "benign_count": sum(1 for s in members if s.get("source_lane") == "benign"),
                "tier_distribution": {
                    tier: sum(1 for s in members if s.get("label_tier") == tier)
                    for tier in LABEL_TIERS
                },
            },
            hunt_id=hunt_id,
            trust_tier="IMPORTED_OBSERVED",
        )
        entries += 1
    return entries
