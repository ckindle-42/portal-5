"""SA4.1 -- source evaluation dossiers + ranked ingestion plan.

Hermetic: dossier schema validation and license-policy enforcement over the
researched candidate sources. No network, no external data.
"""

from __future__ import annotations

import pytest

from portal.modules.security.core.bully.analyst_corpus import (
    CANDIDATE_SOURCE_DOSSIERS,
    SourceDossier,
    license_is_compatible,
    rank_ingestion_plan,
    validate_dossier_schema,
)


def test_all_candidate_dossiers_validate():
    for dossier in CANDIDATE_SOURCE_DOSSIERS:
        verdict = validate_dossier_schema(dossier)
        assert verdict["valid"], f"{dossier.source_id}: {verdict['errors']}"


def test_dossier_schema_requires_required_fields():
    dossier = SourceDossier(
        source_id="partial",
        name="",
        source_class="cloud",
        license="MIT",
        license_compatible=True,
        format="json",
        parse_cost="LOW",
        achievable_label_tier="T1",
        class_contribution="aws",
        benign_volume="low",
        overlap_with_existing="none",
    )
    verdict = validate_dossier_schema(dossier)
    assert verdict["valid"] is False
    assert any("name" in error for error in verdict["errors"])


def test_unknown_parse_cost_and_tier_rejected():
    with pytest.raises(ValueError):
        SourceDossier(
            source_id="bad",
            name="bad",
            source_class="cloud",
            license="MIT",
            license_compatible=True,
            format="json",
            parse_cost="FAST",
            achievable_label_tier="T1",
            class_contribution="aws",
            benign_volume="low",
            overlap_with_existing="none",
        )
    with pytest.raises(ValueError):
        SourceDossier(
            source_id="bad-tier",
            name="bad",
            source_class="cloud",
            license="MIT",
            license_compatible=True,
            format="json",
            parse_cost="LOW",
            achievable_label_tier="T9",
            class_contribution="aws",
            benign_volume="low",
            overlap_with_existing="none",
        )


def test_gpl_3_source_is_flagged_not_silently_ingested():
    """The OTRF GPL-3.0 constraint: an incompatible license is a hard flag --
    the source appears in `flagged`, never in the ranked/admitted list."""
    assert license_is_compatible("GPL-3.0") is False
    otrf = next(d for d in CANDIDATE_SOURCE_DOSSIERS if d.source_id == "otrf_security_datasets")
    assert otrf.license_compatible is False
    plan = rank_ingestion_plan(CANDIDATE_SOURCE_DOSSIERS)
    assert any(item["source_id"] == otrf.source_id for item in plan["flagged"])
    assert all(item["source_id"] != otrf.source_id for item in plan["ranked"])
    assert plan["reconciled"] is True


def test_dossier_marking_incompatible_license_compatible_is_invalid():
    """A dossier that claims an incompatible license is compatible must not
    validate -- the policy catch is structural, not just prose."""
    bad = SourceDossier(
        source_id="otrf-copy",
        name="OTRF (copy)",
        source_class="multi",
        license="GPL-3.0",
        license_compatible=True,  # wrong -- must be flagged
        format="evtx",
        parse_cost="MEDIUM",
        achievable_label_tier="T0",
        class_contribution="multi",
        benign_volume="medium",
        overlap_with_existing="high",
    )
    verdict = validate_dossier_schema(bad)
    assert verdict["valid"] is False
    assert any("incompatible" in error for error in verdict["errors"])


def test_ranked_plan_orders_by_achievable_tier_then_class():
    plan = rank_ingestion_plan(CANDIDATE_SOURCE_DOSSIERS)
    ranked = plan["ranked"]
    tiers = [item["achievable_label_tier"] for item in ranked]
    assert tiers == sorted(tiers)  # T0 before T1 before T2
    flagged_ids = {item["source_id"] for item in plan["flagged"]}
    assert not ({item["source_id"] for item in ranked} & flagged_ids)


def test_cloud_identity_and_multi_source_candidates_present():
    plan = rank_ingestion_plan(CANDIDATE_SOURCE_DOSSIERS)
    ids = {item["source_id"] for item in plan["ranked"]}
    for expected in (
        "flaws_cloud_cloudtrail",
        "invictus_ir_aws_dataset",
        "arxiv_2606_18190",
        "darpa_optc_tc3",
    ):
        assert expected in ids
