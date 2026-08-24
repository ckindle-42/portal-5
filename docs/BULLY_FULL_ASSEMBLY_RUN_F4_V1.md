# BULLY_FULL_ASSEMBLY_RUN_F4_V1

## assembly_verdict: **PROXY_SCALE**

- integration_fraction: 1.0 (16/16 modules)
- corpus_fraction: 0.00128
- modules_missing: []
- degraded_stages: []
- reasons: ['corpus_fraction_0.00128<0.1: 359757 of 281069912 records -- this is another proxy']

## The four standing claims, answered by THIS run

```json
{
  "crogl": {
    "sourcetypes_reviewed": 325,
    "identity_coverage": 1.0,
    "claim": "ingests any source"
  },
  "bully": {
    "chain_reach_recall": 1.0,
    "max_pivot_distance": 0,
    "claim": "finds same/similar on a real haystack"
  },
  "corpus": {
    "records_processed": 359757,
    "records_available": 281069912,
    "fraction": 0.00128,
    "claim": "the real ground is actually used"
  },
  "generator": {
    "cousin_recall_at_distance": {
      "0": 1.0
    },
    "claim": "cousins of what is in the corpus, injected into it"
  }
}
```

## bed_acceptance (A5)

```json
{
  "floor_known_recall": 0.037037037037037035,
  "product_cousin_recall": 1.0,
  "cost_background_fp_rate": null,
  "n_answer_key": 27,
  "n_cousins_injected": 5,
  "n_background_sampled": 0,
  "verdict": "INVALID",
  "reasons": [
    "partial_read:359757/281069912 -- a capped read of a real corpus biases every downstream statistic toward whatever the cap selected",
    "scored_sample_too_small:70<10000 -- recall/FP figures computed on this scored population do not generalise"
  ]
}
```

## scoreboard.update() -- the correctness axis (W.2)

- trust_mean_rank: 1.0
- false_flag_count: 0
```json
{
  "hunt_id": "full_assembly_f4",
  "n_records": 1,
  "catch_count": 1,
  "catch_rate": 1.0,
  "trust_mean_rank": 1.0,
  "discovery_total": 0.6,
  "discovery_mean": 0.6,
  "false_flag_count": 0
}
```

- found_anchor: T1558.004 (botsv3)

## Per-stage timings and outputs

- **resolve_indexes** (corpus_bed) -- OK, 0.0s
- **discover_index_range** (inject_plane) -- OK, 7.581s
- **investigate_anchors** (investigation_pivot) -- OK, 1.612s
- **plant_and_measure_cousins** (adaptive_scope) -- OK, 6.63s
- **stream_corpus_sample** (corpus_bed) -- OK, 370.909s
- **infer_field_roles** (field_roles) -- OK, 0.031s
- **classify_telemetry** (telemetry_behavior) -- OK, 0.0s
- **infer_universal_behaviors** (behavior_inference) -- OK, 0.0s
- **build_artifact_graph** (artifact_graph) -- OK, 0.001s
- **resolve_entities_and_timelines** (correlation) -- OK, 0.0s
- **fit_baseline** (baseline) -- OK, 0.0s
- **discover_and_cluster** (discovery) -- OK, 0.001s
- **series_and_level** (series_cousin) -- OK, 0.0s
- **level_match** (pyramid) -- OK, 0.0s
- **grade_to_loop_contract** (loop_grader) -- OK, 0.0s
- **resolve_unit_outcomes** (unit_outcome) -- OK, 0.0s
- **raise_and_verdict_concerns** (analyst_loop) -- OK, 0.0s

Total duration: 386.77s

## Full stage outputs

```json
{
  "resolve_indexes": [
    "portal5_lab",
    "botsv1",
    "botsv2",
    "botsv3"
  ],
  "discover_index_range": {
    "n_indexes": 4
  },
  "investigate_anchors": {
    "n_investigations": 1,
    "n_events": 6,
    "n_answer_key_entries_tried": 1,
    "found_technique": "T1558.004",
    "found_dataset": "botsv3"
  },
  "plant_and_measure_cousins": {
    "n_planted": 5,
    "dry_run": false,
    "inject_reports": [
      {
        "cousin_id": "cz-botsv3-T1558.004-000-REVOCABULARY-00-d0",
        "sourcetypes_used": [
          "wineventlog:security"
        ],
        "n_events": 3,
        "ok": true
      },
      {
        "cousin_id": "cz-botsv3-T1558.004-000-RESCHEMA-10-d0",
        "sourcetypes_used": [
          "wineventlog:security"
        ],
        "n_events": 3,
        "ok": true
      },
      {
        "cousin_id": "cz-botsv3-T1558.004-000-REIDENTITY-20-d0",
        "sourcetypes_used": [
          "wineventlog:security"
        ],
        "n_events": 3,
        "ok": true
      },
      {
        "cousin_id": "cz-botsv3-T1558.004-000-SCATTER-30-d0",
        "sourcetypes_used": [
          "wineventlog:security"
        ],
        "n_events": 3,
        "ok": true
      },
      {
        "cousin_id": "cz-botsv3-T1558.004-000-REORDER_MINOR-40-d0",
        "sourcetypes_used": [
          "wineventlog:security"
        ],
        "n_events": 3,
        "ok": true
      }
    ],
    "by_distance": {
      "0": {
        "total": 5,
        "reached": 5,
        "recall": 1.0
      }
    },
    "max_reached_distance": 0,
    "zero_hop_only": true
  },
  "stream_corpus_sample": {
    "n_records_wide_fit": 359757,
    "n_records_last_batch": 63,
    "wide_fitted_units": 99033,
    "resumed_from_checkpoint": false,
    "n_sourcetypes_covered": 325,
    "n_sourcetypes_available": 430,
    "coverage_note": "this run optimizes sourcetype/event-type coverage, not raw corpus volume -- corpus_fraction will read low against F.4's literal 0.10 floor by design (operator decision); see stage docstring"
  },
  "infer_field_roles": {
    "extraction_valid": true,
    "n_fields": 17
  },
  "classify_telemetry": {
    "algorithm_version": "telemetry-behavior-v1",
    "n_records": 63,
    "n_classified": 0,
    "coverage": 0.0,
    "by_sourcetype": {
      "yum-too_small": {
        "records": 63,
        "classified": 0,
        "coverage": 0.0
      }
    },
    "class_distribution": {},
    "class_entropy_bits": 0,
    "degenerate": true,
    "unmapped_sourcetypes": [
      "yum-too_small"
    ],
    "class_concentration": {},
    "source_concentration": {},
    "concentration_reasons": [],
    "concentrated": false
  },
  "infer_universal_behaviors": {
    "algorithm_version": "behavior-inference-v1",
    "actions_profiled": 0,
    "schemas_seen": 0,
    "classes_inferred": 0,
    "cross_schema_classes": 0,
    "cross_schema_fraction": null,
    "largest_class_members": 0
  },
  "build_artifact_graph": {
    "n_artifacts": 63,
    "n_units": 70
  },
  "resolve_entities_and_timelines": {
    "n_entities": 1,
    "n_timelines": 1
  },
  "fit_baseline": {
    "fitted_units": 99103
  },
  "discover_and_cluster": {
    "algorithm_version": "discovery-v1",
    "units_examined": 70,
    "discovered": 7,
    "rejected_unremarkable": 63,
    "rejected_incoherent": 0,
    "discovery_rate": 0.1,
    "n_clusters": 1
  },
  "series_and_level": {
    "n_series": 1
  },
  "level_match": {
    "n_matches": 1
  },
  "grade_to_loop_contract": {
    "assessments": 1
  },
  "resolve_unit_outcomes": {
    "n_outcomes": 70,
    "by_outcome": {
      "NOVEL": 7,
      "NORMAL": 63
    }
  },
  "raise_and_verdict_concerns": {
    "n_concerns": 0
  }
}
```
