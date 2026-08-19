"""C.7 -- the verification run's markdown/JSON self-check: every published
column must appear in the rendered markdown, and omitting one must be
caught (this is precisely the M.3 defect, where the compounding table
silently dropped `coverage`/`scored`)."""

from __future__ import annotations

from scripts.bully_cousin_run_c7 import _render_markdown, _self_check_md_covers_json

_MINIMAL_PAYLOAD = {
    "schema": "BULLY_COUSIN_RELATION_RUN_C7_V1",
    "valid": True,
    "part1_instrument_validation": {
        "ladder": {
            "n_parents": 5,
            "n_rungs": 25,
            "mean_parent_rho": 0.95,
            "pooled_rho": 0.9,
            "monotonicity_floor": 0.9,
            "monotonicity_valid": True,
            "l3_recovery_rate": 0.2,
            "l3_recovered": 1,
            "l3_total": 5,
            "negative_control_holds": True,
            "shuffled_rho": 0.05,
            "shuffle_collapsed": True,
            "valid": True,
            "rung_records": [
                {
                    "level": 3,
                    "status": "COUSIN_CANDIDATE",
                    "parent_anchor_id": "p1",
                    "matched_anchor_id": "p1",
                }
            ],
        },
        "old_engine_arm": {
            "anomalous_unclassified_rate": 0.4,
            "l3_recovery_rate": 0.0,
            "outcome_distribution": {"ANOMALOUS_UNCLASSIFIED": 10, "SAME": 15},
            "l0_identity_outcome_distribution": {"SAME": 5},
            "l3_cross_space_outcome_distribution": {"ANOMALOUS_UNCLASSIFIED": 5},
        },
    },
    "part2_live_rerun": {
        "planner_proof_hash": "deadbeef",
        "seed_count": 10,
        "seed_sources": ["attack_data"],
        "anchor_library_starting_composition": {"attack_episode": {"strong": 5}},
        "control_arm": {
            "n": 10,
            "status_distribution": {"COUSIN_CANDIDATE": 3, "NOVEL_NOTABLE": 7},
            "distance_distribution": {"mean": 0.5, "median": 0.5, "min": 0.1, "max": 1.0},
            "confidence_distribution": {"mean": 0.3, "median": 0.3, "min": 0.0, "max": 0.7},
            "coverage_distribution": {"mean": 0.4, "median": 0.4, "min": 0.1, "max": 0.6},
            "insufficient_view_count": 0,
            "insufficient_view_rate": 0.0,
            "anomalous_rate": 0.0,
            "anomalous_rate_ceiling": 0.5,
            "anomalous_rate_exceeded": False,
            "uncertainty_variance_passes": True,
            "uncertainty_per_group_max_repeat_fraction": {"attack_data": 0.5},
            "coverage_refusal_check": {
                "rows_with_coverage_below_0_6": 8,
                "of_those_classified_insufficient_view": 0,
                "coverage_refusals_found": False,
            },
            "scored_count": 3,
            "unscored_count": 7,
            "external_scored_coverage": 0.3,
            "compounding_valid": True,
            "data_access_records": 100,
            "cost_tokens": 0,
        },
        "compounding_experiment": {
            "first_half": {
                "n": 5,
                "status_distribution": {"COUSIN_CANDIDATE": 4},
                "distance_distribution": {"mean": 0.1, "median": 0.1, "min": 0.0, "max": 0.2},
                "confidence_distribution": {"mean": 0.5, "median": 0.5, "min": 0.3, "max": 0.7},
                "coverage_distribution": {"mean": 0.5, "median": 0.5, "min": 0.3, "max": 0.7},
                "insufficient_view_count": 0,
                "insufficient_view_rate": 0.0,
                "anomalous_rate": 0.0,
                "anomalous_rate_ceiling": 0.5,
                "anomalous_rate_exceeded": False,
                "uncertainty_variance_passes": True,
                "uncertainty_per_group_max_repeat_fraction": {},
                "coverage_refusal_check": {
                    "rows_with_coverage_below_0_6": 0,
                    "of_those_classified_insufficient_view": 0,
                    "coverage_refusals_found": False,
                },
                "scored_count": 4,
                "unscored_count": 1,
                "external_scored_coverage": 0.8,
                "compounding_valid": True,
                "data_access_records": 50,
                "cost_tokens": 0,
            },
            "second_half_with_growth": {
                "n": 5,
                "status_distribution": {"COUSIN_CANDIDATE": 4},
                "distance_distribution": {"mean": 0.1, "median": 0.1, "min": 0.0, "max": 0.2},
                "confidence_distribution": {"mean": 0.5, "median": 0.5, "min": 0.3, "max": 0.7},
                "coverage_distribution": {"mean": 0.5, "median": 0.5, "min": 0.3, "max": 0.7},
                "insufficient_view_count": 0,
                "insufficient_view_rate": 0.0,
                "anomalous_rate": 0.0,
                "anomalous_rate_ceiling": 0.5,
                "anomalous_rate_exceeded": False,
                "uncertainty_variance_passes": True,
                "uncertainty_per_group_max_repeat_fraction": {},
                "coverage_refusal_check": {
                    "rows_with_coverage_below_0_6": 0,
                    "of_those_classified_insufficient_view": 0,
                    "coverage_refusals_found": False,
                },
                "scored_count": 1,
                "unscored_count": 4,
                "external_scored_coverage": 0.2,
                "compounding_valid": True,
                "data_access_records": 50,
                "cost_tokens": 0,
            },
            "control_second_half_no_growth": {
                "n": 5,
                "status_distribution": {"NOVEL_NOTABLE": 5},
                "distance_distribution": {"mean": 0.9, "median": 0.9, "min": 0.8, "max": 1.0},
                "confidence_distribution": {"mean": 0.0, "median": 0.0, "min": 0.0, "max": 0.0},
                "coverage_distribution": {"mean": 0.2, "median": 0.2, "min": 0.1, "max": 0.3},
                "insufficient_view_count": 0,
                "insufficient_view_rate": 0.0,
                "anomalous_rate": 0.0,
                "anomalous_rate_ceiling": 0.5,
                "anomalous_rate_exceeded": False,
                "uncertainty_variance_passes": True,
                "uncertainty_per_group_max_repeat_fraction": {},
                "coverage_refusal_check": {
                    "rows_with_coverage_below_0_6": 5,
                    "of_those_classified_insufficient_view": 0,
                    "coverage_refusals_found": False,
                },
                "scored_count": 0,
                "unscored_count": 5,
                "external_scored_coverage": 0.0,
                "compounding_valid": False,
                "data_access_records": 50,
                "cost_tokens": 0,
            },
            "anchor_library_composition_after": {"attack_episode": {"strong": 5}},
        },
        "unrelatable_coverage_gap": {
            "count": 0,
            "fraction_of_seeds": 0.0,
            "sample_seed_ids": [],
        },
        "calibration": {
            "n_scored": 15,
            "brier_score": 0.12,
            "overconfident": False,
            "blocks_release": False,
            "bins": [],
            "caveat": "computed over the constructed ladder",
        },
        "worked_delta_examples": [],
        "scope": {
            "cost_tokens": 0,
            "model_calls": 0,
            "j2_bin_gates_exercised": False,
            "note": "relation-only pass",
        },
    },
}


def test_clean_payload_has_no_missing_fields():
    md = _render_markdown(_MINIMAL_PAYLOAD)
    missing = _self_check_md_covers_json(_MINIMAL_PAYLOAD, md)
    assert missing == []


def test_omitting_a_published_field_is_caught():
    """Seeded violation: render the markdown, then delete a field's line
    from the text (simulating the M.3 defect, which silently dropped
    `coverage`/`scored` from its compounding table) and confirm the check
    flags it as missing. Uses `brier_score` (0.12 -> "0.1200"), a value
    distinctive enough not to coincidentally appear elsewhere in the doc."""
    md = _render_markdown(_MINIMAL_PAYLOAD)
    assert "| brier_score | 0.1200 |" in md
    mangled = md.replace("| brier_score | 0.1200 |", "")
    missing = _self_check_md_covers_json(_MINIMAL_PAYLOAD, mangled)
    assert any("brier_score" in m for m in missing)


def test_exit_criteria_section_present():
    from scripts.bully_cousin_run_c7 import _render_exit_criteria

    section = "\n".join(_render_exit_criteria(_MINIMAL_PAYLOAD))
    assert "Exit-criteria self-assessment" in section
    assert "0.2000" in section or "l3_recovery_rate" not in section
