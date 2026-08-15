# Defensive Bully cousin-calibration policy v1

`CALIB_DISTANCE_POLICY_V1` is the frozen construction-distance x-axis for
the eval-only cousin bench. It sums typed MUT operator-class weights and caps
at 1.0. It does not import or call BR-COUSIN's weighted composite. The frozen
`CALIB_PARENTS_V1` set contains four labeled `exec_chain` parents spanning
Active Directory, web injection, lateral movement, and cloud metadata, each
with a covering detection. Its snapshot hash is emitted in every report.

Children are compiled through MUT, graded blind through
`build_signature → Organ.knn → candidate_set → grade`, and never indexed.
Response-axis NEAR_MISS attribution comes from the eval-only
`recall_attribution` discriminator oracle. Reports separate anomalous or
indeterminate rows from passes and failures.

## First recorded run

The frozen v1 sweep ran against a real isolated four-parent Organ snapshot at
`/Volumes/data01/portal5_hunt/artifacts/calibration/20260815T163102Z/`.
All 32 children were blind-graded and the snapshot remained at four rows
(`children_indexed: 0`). The result was an honest **FAIL**: six covered
mid-band variants graded NEW and eight threshold-crossing deviations were
recorded; monotonicity, negative controls, response attribution, and parent
assignment were clean. The report includes CSV/SVG curve artifacts and the
operator-gated `bully-cousin-thresholds-v2-proposal`:

- `same_max_distance: 0.1285`
- `similar_max_distance: 0.5967`
- `new_max_distance: 0.6101`

The proposal is not applied to this reported set. If an operator adopts it,
it becomes a new policy version and must be evaluated on a fresh frozen sweep.
