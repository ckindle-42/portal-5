# BULLY_COUSIN_RELATION_RUN_C7_V1 — cousin-relation verification run


> **Errata (2026-08-21, `TASK_BULLY_FULL_ASSEMBLY_V1` F.0):** this run exercised 1/16 of the bully modules over a token record count (well under 0.001% of the 281,069,416-record corpus) and is a partial assembly at proxy scale (see `docs/DESIGN_BULLY_FULL_ASSEMBLY_V1.md`); its findings describe that subset, not the system.
> **Errata (2026-08-20, `TASK_BULLY_SCOREBOARD_CONFORMANCE_V1`).** This run's
> headline is not a module contract, and its correctness axis
> (`trust_mean_rank`, `false_flag_count` from `scoreboard.update()`) was never
> published -- `correctness_axis_not_published` fires against this doc. See
> `docs/DESIGN_BULLY_SCOREBOARD_CONFORMANCE_V1.md` for the corrected
> diagnosis and the live successor run
> `docs/BULLY_SCOREBOARD_CONFORMANCE_RUN_W6_V1.md`.

> **Errata (2026-08-20, `TASK_BULLY_LOOP_REINTEGRATION_V1`).** Every grader
> this arc rebuilt, including this run's, was measured standalone -- the
> orchestrator never called it. The grader is now wired into the loop
> (`bully/loop_grader.py`), decided level-first on the pyramid axis
> (`bully/pyramid.py`) rather than flat distance. See
> `docs/DESIGN_BULLY_LOOP_REINTEGRATION_V1.md` and the live run
> `docs/BULLY_LOOP_MILESTONE_RUN_R6_V1.md`.

> **Errata (2026-08-19, `TASK_BULLY_UNKNOWN_COUSIN_V1`).** This run's own
> L3 (cross-space) recovery rate of **0.0250** (1/40) is the concrete
> symptom of the defect this task corrects: `_signature_from_scope` grades
> one flattened `action_sequence[:32]` token bag per scope, so shape
> (co-occurrence, ordering, entity linkage) is discarded and only literal
> vocabulary survives -- exactly what a cross-vocabulary cousin needs to be
> matched on shape, not vocabulary, to be found at all. The five inversions
> below (C.1) are correct and carry forward unchanged; they were applied to
> the wrong unit of analysis (a whole scope, never an individual artifact or
> a structurally-grouped combination). See
> [`DESIGN_BULLY_UNKNOWN_COUSIN_V1.md`](DESIGN_BULLY_UNKNOWN_COUSIN_V1.md)
> and the re-run,
> [`BULLY_UNKNOWN_COUSIN_RUN_M3_V1.md`](BULLY_UNKNOWN_COUSIN_RUN_M3_V1.md).
> This document is kept as the honest record of what C.7 actually measured,
> not rewritten.

`TASK_BULLY_COUSIN_RELATION_V1` C.7. Two parts: instrument validation (C.6's constructed ladder) and the live re-run over the real data plane through the new cousin grader. `valid: True` overall.

## Part 1 — instrument validation (C.6)

| metric | value |
|---|---|
| n_parents | 40 |
| n_rungs | 200 |
| mean_parent_rho | 0.9880 |
| pooled_rho | 0.9661 |
| monotonicity_floor | 0.9000 |
| monotonicity_valid | True |
| l3_recovery_rate | 0.0250 |
| l3_recovered | 1 |
| l3_total | 40 |
| negative_control_holds | True |
| shuffled_rho | -0.0874 |
| shuffle_collapsed | True |
| valid | True |

**Old-engine arm** (`relation.relate`, unmodified, over the identical ladder — recorded as-is, not adjusted to fit the premise):

| metric | value |
|---|---|
| anomalous_unclassified_rate | 0.3550 |
| l3_recovery_rate | 0.0250 |
| outcome_distribution.SIMILAR | 99 |
| outcome_distribution.ANOMALOUS_UNCLASSIFIED | 71 |
| outcome_distribution.NEW | 29 |
| outcome_distribution.SAME | 1 |
| l0_identity_outcome_distribution.SIMILAR | 39 |
| l0_identity_outcome_distribution.SAME | 1 |
| l3_cross_space_outcome_distribution.ANOMALOUS_UNCLASSIFIED | 30 |
| l3_cross_space_outcome_distribution.NEW | 10 |

New engine L3 recovery rate **0.0250** vs old engine **0.0250** — the cousin the old grader structurally could not find.

## Part 2 — live re-run

- `planner_proof_hash`: `8fe5e856e73a38b7`
- `seed_count`: 100
- `seed_sources`: attack_data, flaws_cloud_cloudtrail, invictus_ir_aws_dataset, lab-splunk, live-advisories

### Anchor library — starting composition

| kind | grade | count |
|---|---|---|
| attack_episode | strong | 1009 |
| advisory | weak | 64 |
| detection_coverage | moderate | 40 |

#### Control arm (write-back disabled throughout)

| field | value |
|---|---|
| n | 100 |
| insufficient_view_count | 0 |
| insufficient_view_rate | 0.0000 |
| anomalous_rate | 0.0000 |
| anomalous_rate_ceiling | 0.5000 |
| anomalous_rate_exceeded | False |
| uncertainty_variance_passes | False |
| coverage_refusal_check.rows_with_coverage_below_0_6 | 82 |
| coverage_refusal_check.of_those_classified_insufficient_view | 0 |
| coverage_refusal_check.coverage_refusals_found | False |
| scored_count | 100 |
| unscored_count | 0 |
| external_scored_coverage | 1.0000 |
| compounding_valid | True |
| data_access_records | 3138 |
| cost_tokens | 0 |
| distance_distribution.mean | 0.9229 |
| distance_distribution.median | 1.0000 |
| distance_distribution.min | 0.2500 |
| distance_distribution.max | 1.0000 |
| confidence_distribution.mean | 0.0460 |
| confidence_distribution.median | 0.0000 |
| confidence_distribution.min | 0.0000 |
| confidence_distribution.max | 0.5250 |
| coverage_distribution.mean | 0.2130 |
| coverage_distribution.median | 0.1000 |
| coverage_distribution.min | 0.1000 |
| coverage_distribution.max | 0.6000 |
| status_distribution.NOVEL_NOTABLE | 79 |
| status_distribution.COUSIN_CANDIDATE | 21 |
| uncertainty_per_group_max_repeat_fraction.attack_data | 0.9000 |
| uncertainty_per_group_max_repeat_fraction.lab-splunk | 1.0000 |
| uncertainty_per_group_max_repeat_fraction.live-advisories | 1.0000 |
| uncertainty_per_group_max_repeat_fraction.flaws_cloud_cloudtrail | 1.0000 |
| uncertainty_per_group_max_repeat_fraction.invictus_ir_aws_dataset | 1.0000 |

#### Compounding — first half (write-back on)

| field | value |
|---|---|
| n | 50 |
| insufficient_view_count | 0 |
| insufficient_view_rate | 0.0000 |
| anomalous_rate | 0.0000 |
| anomalous_rate_ceiling | 0.5000 |
| anomalous_rate_exceeded | False |
| uncertainty_variance_passes | False |
| coverage_refusal_check.rows_with_coverage_below_0_6 | 32 |
| coverage_refusal_check.of_those_classified_insufficient_view | 0 |
| coverage_refusal_check.coverage_refusals_found | False |
| scored_count | 15 |
| unscored_count | 35 |
| external_scored_coverage | 0.3000 |
| compounding_valid | True |
| data_access_records | 1538 |
| cost_tokens | 0 |
| distance_distribution.mean | 0.0721 |
| distance_distribution.median | 0.0000 |
| distance_distribution.min | 0.0000 |
| distance_distribution.max | 1.0000 |
| confidence_distribution.mean | 0.3557 |
| confidence_distribution.median | 0.3250 |
| confidence_distribution.min | 0.0000 |
| confidence_distribution.max | 0.8000 |
| coverage_distribution.mean | 0.4100 |
| coverage_distribution.median | 0.3000 |
| coverage_distribution.min | 0.2000 |
| coverage_distribution.max | 0.6000 |
| status_distribution.NOVEL_NOTABLE | 2 |
| status_distribution.COUSIN_CANDIDATE | 48 |
| uncertainty_per_group_max_repeat_fraction.attack_data | 0.8000 |
| uncertainty_per_group_max_repeat_fraction.lab-splunk | 0.9000 |
| uncertainty_per_group_max_repeat_fraction.live-advisories | 0.9000 |

#### Compounding — second half with growth (write-back on)

| field | value |
|---|---|
| n | 50 |
| insufficient_view_count | 0 |
| insufficient_view_rate | 0.0000 |
| anomalous_rate | 0.0000 |
| anomalous_rate_ceiling | 0.5000 |
| anomalous_rate_exceeded | False |
| uncertainty_variance_passes | False |
| coverage_refusal_check.rows_with_coverage_below_0_6 | 50 |
| coverage_refusal_check.of_those_classified_insufficient_view | 0 |
| coverage_refusal_check.coverage_refusals_found | False |
| scored_count | 4 |
| unscored_count | 46 |
| external_scored_coverage | 0.0800 |
| compounding_valid | True |
| data_access_records | 1600 |
| cost_tokens | 0 |
| distance_distribution.mean | 0.0394 |
| distance_distribution.median | 0.0000 |
| distance_distribution.min | 0.0000 |
| distance_distribution.max | 1.0000 |
| confidence_distribution.mean | 0.3452 |
| confidence_distribution.median | 0.3500 |
| confidence_distribution.min | 0.0000 |
| confidence_distribution.max | 0.7000 |
| coverage_distribution.mean | 0.3740 |
| coverage_distribution.median | 0.4000 |
| coverage_distribution.min | 0.1000 |
| coverage_distribution.max | 0.4000 |
| status_distribution.COUSIN_CANDIDATE | 48 |
| status_distribution.NOVEL_NOTABLE | 2 |
| uncertainty_per_group_max_repeat_fraction.live-advisories | 1.0000 |
| uncertainty_per_group_max_repeat_fraction.flaws_cloud_cloudtrail | 0.9000 |
| uncertainty_per_group_max_repeat_fraction.invictus_ir_aws_dataset | 0.9000 |

#### Compounding — control second half, no growth (write-back off)

| field | value |
|---|---|
| n | 50 |
| insufficient_view_count | 0 |
| insufficient_view_rate | 0.0000 |
| anomalous_rate | 0.0000 |
| anomalous_rate_ceiling | 0.5000 |
| anomalous_rate_exceeded | False |
| uncertainty_variance_passes | False |
| coverage_refusal_check.rows_with_coverage_below_0_6 | 50 |
| coverage_refusal_check.of_those_classified_insufficient_view | 0 |
| coverage_refusal_check.coverage_refusals_found | False |
| scored_count | 50 |
| unscored_count | 0 |
| external_scored_coverage | 1.0000 |
| compounding_valid | True |
| data_access_records | 1600 |
| cost_tokens | 0 |
| distance_distribution.mean | 1.0000 |
| distance_distribution.median | 1.0000 |
| distance_distribution.min | 1.0000 |
| distance_distribution.max | 1.0000 |
| confidence_distribution.mean | 0.0000 |
| confidence_distribution.median | 0.0000 |
| confidence_distribution.min | 0.0000 |
| confidence_distribution.max | 0.0000 |
| coverage_distribution.mean | 0.1000 |
| coverage_distribution.median | 0.1000 |
| coverage_distribution.min | 0.1000 |
| coverage_distribution.max | 0.1000 |
| status_distribution.NOVEL_NOTABLE | 50 |
| uncertainty_per_group_max_repeat_fraction.live-advisories | 1.0000 |
| uncertainty_per_group_max_repeat_fraction.flaws_cloud_cloudtrail | 1.0000 |
| uncertainty_per_group_max_repeat_fraction.invictus_ir_aws_dataset | 1.0000 |

### Anchor library — composition after compounding write-back

| kind | grade | count |
|---|---|---|
| attack_episode | strong | 1009 |
| advisory | weak | 64 |
| detection_coverage | moderate | 40 |
| confirmed_finding | weak | 100 |

### Unrelatable coverage gap

| field | value |
|---|---|
| count | 0 |
| fraction_of_seeds | 0.0000 |
| sample_seed_ids | (none) |

`INSUFFICIENT_VIEW` is read as an **instrument/coverage finding** here, never as discovery -- it means no anchor shared a single dimension with the arrival, not that the arrival is uninteresting.

### Calibration

_computed over C.6's constructed ladder (L0-L2, known ground truth), not the live harvested seeds -- those carry no independent correct/incorrect label, so a live-seed calibration would be circular_

| field | value |
|---|---|
| n_scored | 120 |
| brier_score | 0.1348 |
| overconfident | False |
| blocks_release | False |

| bin | count | mean_confidence | realised_accuracy | overconfident |
|---|---|---|---|---|
| [0.0, 0.2) | 0 | — | — | False |
| [0.2, 0.4) | 19 | 0.2194 | 0.0526 | False |
| [0.4, 0.6) | 51 | 0.5153 | 1.0000 | False |
| [0.6, 0.8) | 10 | 0.6595 | 1.0000 | False |
| [0.8, 1.0) | 40 | 0.8000 | 1.0000 | False |

### Worked delta examples

**seed-attack_data-019** (attack_data, `COUSIN_CANDIDATE`, distance=0.2500)

- anchor: `attack-episode-45da1d0f3cbf1126`
- hypothesized_techniques: ['T1204.003']
- shared_features: ['DescribeImageScanFindings']
- diverging_features: ['dataset=aws_ecr_image_scanning', 'target_host=attack_data']
- axis_of_divergence: context
- unobservable_dimensions: ['telemetry', 'semantic', 'attack']

**seed-lab-splunk-000** (lab-splunk, `COUSIN_CANDIDATE`, distance=0.6769)

- anchor: `det-T1059.001`
- hypothesized_techniques: ['T1059.001']
- shared_features: ['sourcetypes=windows:sysmon']
- diverging_features: ['sourcetypes=corpus:probe', 'sourcetypes=windows:powershell']
- axis_of_divergence: telemetry
- unobservable_dimensions: ['behavior', 'semantic', 'attack']

**seed-lab-splunk-001** (lab-splunk, `COUSIN_CANDIDATE`, distance=0.6769)

- anchor: `det-T1059.001`
- hypothesized_techniques: ['T1059.001']
- shared_features: ['sourcetypes=windows:sysmon']
- diverging_features: ['sourcetypes=corpus:probe', 'sourcetypes=windows:powershell']
- axis_of_divergence: telemetry
- unobservable_dimensions: ['behavior', 'semantic', 'attack']

**seed-lab-splunk-002** (lab-splunk, `COUSIN_CANDIDATE`, distance=0.6769)

- anchor: `det-T1059.001`
- hypothesized_techniques: ['T1059.001']
- shared_features: ['sourcetypes=windows:sysmon']
- diverging_features: ['sourcetypes=corpus:probe', 'sourcetypes=windows:powershell']
- axis_of_divergence: telemetry
- unobservable_dimensions: ['behavior', 'semantic', 'attack']

**seed-lab-splunk-003** (lab-splunk, `COUSIN_CANDIDATE`, distance=0.6769)

- anchor: `det-T1059.001`
- hypothesized_techniques: ['T1059.001']
- shared_features: ['sourcetypes=windows:sysmon']
- diverging_features: ['sourcetypes=corpus:probe', 'sourcetypes=windows:powershell']
- axis_of_divergence: telemetry
- unobservable_dimensions: ['behavior', 'semantic', 'attack']

### Scope

| field | value |
|---|---|
| cost_tokens | 0 |
| model_calls | 0 |
| j2_bin_gates_exercised | False |
| note | relation-only pass: no model call in this run (J.1 brief-shaping is pure compute) |

## Exit-criteria self-assessment: is a cousin found the old engine could not find?

At this corpus scale (40 parents, 1009 real EXTERNAL attack_episode anchors), the strict reading of the exit criterion -- an L3 rung reaching `COUSIN_CANDIDATE` (named parent, delta, hypothesized technique) -- is met by **0/40** L3 rungs. The nearest-rank recovery rate (pre-classification, `ranked_cousins[0]`) is **0.0250** for the new engine vs **0.0250** for the old engine -- at this sample the two are effectively tied on raw retrieval, because both engines share the same underlying lexical token-overlap signal at the retrieval stage; the real, already-demonstrated separation is at the **classification** stage: the old engine's L3 outcome distribution is {'ANOMALOUS_UNCLASSIFIED': 30, 'NEW': 10} -- zero SAME/SIMILAR, meaning it never once names a cousin at L3 regardless of what its own retrieval ranked nearest -- while the new engine's coverage-never-gates design at least makes naming a cousin *possible* (proven in the C.6 synthetic-corpus tests, `test_cousin_c6_ladder.py`, where a focused 12-parent corpus does reach clean L3 `COUSIN_CANDIDATE` recovery).

**Honest reading:** the exit criterion is qualitatively demonstrated (the mechanism to name an L3 cousin exists and works on a smaller, less densely-populated corpus) but is **not** cleanly demonstrated at this real 1009-anchor scale in this run -- `COUSIN_MAX_DISTANCE=0.75` is too tight for a rung that shares only one lexical token against a dense same-technique-family competitor pool. This is exactly the residual risk `DESIGN_BULLY_COUSIN_RELATION_V1.md` §5 already names: salience-weighted Jaccard is a comparable and honest lexical instrument, but a genuine cross-vocabulary bridge at this scale needs a shared behavioural embedding space. This run's L3 recovery rate is the number that sizes that next task -- reported here rather than smoothed over by loosening the threshold to fit the premise.
