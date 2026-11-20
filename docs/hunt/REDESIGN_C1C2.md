# Hunt redesign C1/C2 — value inventory, value-flow cases, rare-shape keep

Lane `lane/hunt-redesign-c1c2`. Blind hunt only: no signatures, IOCs, dataset names, or keyword lists. New numbers below are effort budgets, the same kind as `BEHAVIOUR_WINDOWS` and `MAX_SEEDS`. They were not LOFO-measured. Offline replay of stored runs was not used to choose them.

`docs/hunt/PRACTITIONER_REVIEW.md` and `docs/hunt/INSTRUMENT_AUDIT_BOTSV2.md` are not in this worktree. C1 and C2 follow the brief. F is the misfit source-share drop. D, with the review absent, is taken to mean a labelled step that was scored and ranked below the head. That reading is unconfirmed.

## What changed

C1 runs inside the behaviours stage, before behaviour sampling, on the same search executor. Low-cardinality role fields come from understood cards (`action`, `actor`, `object`; variety not `free`; sample distinct 1..32). Each selected field is one `tstats count min(_time) max(_time) ... by <field>` over the index window. A second `tstats` runs only when two or more of those lists are complete and the product of their lengths is at most 64. The document is `{out}/inventory.json`.

Index-wide first-seen replaces a behaviour's sample first-seen only when the behaviour's literal `(field, value)` pairs are exactly that joint key and the joint first-seen is positive. A one-field list is stored as a joint with reason `field_list` and is not an extra search. Value rows the behaviour sample never emitted become candidate `Behaviour` rows for the existing generators. Generators and `DEFAULT_WEIGHTS` are unchanged. The behaviour DuckDB table is not rewritten, so relate share metrics stay sample-based.

C2 removes the relate training-index allow-list. `relatable_index` accepts any non-empty index and raises on a proof index (`hb_ait_wheeler`, `hb_cloudobs_aws`, `botsv1`, and the short names in `PROOF_INDEXES`). `stage2.py` is unchanged. A value seen on 2..12 sources becomes a flow: ingress is the earliest source, later is the last, ordered by each source's first-seen. Modal values are kept; a value that is only digits or shorter than 4 characters is not, unless it is an IPv4 address. Flows link seeds on different sources without a time overlap, and a flow with no pivot events is still a case. A case with any seed inside the first 50 notables lifts up to 3 weak members (file index >= 50, or a related notable missing from the file), at most 12 lifts in the run, inserted immediately after that case's best in-head member. `--stage all` is cards, behaviours, notables, relate, judge. The product job still judges and then relates. Judge keeps file order, so a promotion written before the judge is still the order the scoreboard reads.

F: `MISFIT_MAX_SHARE` stays 0.01. A source whose misfit share is over that cap still contributes the shapes whose own share is within the cap, then only the rarest of those shapes. The stored botsv2 `osquery_warning` line (`...GoT.S07E02.BOTS.BOTS.BOTS.mkv.crypt`, 1 of 1035 lines) is the unit case; an 11-event shape in that source stays out.

## LOFO

No constant in this lane was measured leave-one-family-out. Do not treat the hold line as a prediction.

| Constant | Value | Where | Measurement |
| --- | --- | --- | --- |
| `INVENTORY_MAX_SAMPLE_DISTINCT` | 32 | `inventory.py` | unmeasured effort budget |
| `INVENTORY_MAX_VALUES` | 64 | `inventory.py` | unmeasured effort budget |
| `INVENTORY_MAX_FIELD_SEARCHES` | 32 | `inventory.py` | unmeasured effort budget |
| `INVENTORY_MAX_JOINT_SEARCHES` | 16 | `inventory.py` | unmeasured effort budget |
| `INVENTORY_CANDIDATES_PER_SOURCE` | 8 | `inventory.py` | unmeasured effort budget |
| `INVENTORY_CANDIDATE_TOTAL` | 32 | `inventory.py` | unmeasured effort budget |
| `FLOW_MAX_SOURCES` | 12 | `inventory.py` | unmeasured effort budget |
| `PROMOTE_HEAD` | 50 | `relate.py` | scoreboard's smallest cut, not refit |
| `PROMOTE_PER_CASE` | 3 | `relate.py` | unmeasured effort budget |
| `PROMOTE_TOTAL` | 12 | `relate.py` | unmeasured effort budget |
| `MISFIT_MAX_SHARE` | 0.01 | `misfit.py` | unchanged; not retuned |

Ceiling per family: 32 field searches + 16 joint searches. A `field_list` joint adds no search. Wall time is whatever those searches take.

## Cost readback

Per family, after the orchestrator run:

- `progress.json` → `stages.behaviours.inventory`: `searches`, `seconds`, `fields` by status, `values`, `joints`, `flows`, `fields_selected`
- `progress.json` → `stages.notables.inventory`: `first_seen_replaced`, `candidates`, `flows`
- `progress.json` → `stages.relate`: `flows`, `promotion.lifted`, `promotion.ids`
- `{family}/inventory.json` holds the value lists

No per-family search count is known until that run. The script prints the behaviour inventory block to `$run_dir/$family.inventory.log`.

## Predicted live numbers

Unproven. This lane did not run a hunt. The regression bar, from merge `defd357bc` and the brief, is the number a live run must not fall below. It is not a forecast of this code.

| Family | Scoreboard mode | top50 hold | top100 | all |
| --- | --- | --- | --- | --- |
| kyoushi | line (`recall top50`) | 12/12 | unproven | unproven |
| santos | line | 15/21 | unproven | unproven |
| russell | line | 15/22 | unproven | unproven |
| botsv2 | entity (`steps top50`, `scenarios top50`) | 4/15 steps, 3/4 scenarios on that merge | unproven | unproven |

Relate before/after lines are also unproven. A drop at top50 on kyoushi, santos, or russell is a failure. A botsv2 gain is not claimed.

## Tests

Unit tests use stored shapes, not a live index: kyoushi `audit.log` card fields `type`/`uid` and the behaviour `uid=0` `type=USER_END` from `snap_neon_02cc2e3`, and the botsv2 `osquery_warning` crypt shape (1 event of 1035). They check field selection, the search cap, joint first-seen replacement, an unseen pair as a candidate, flow order, flow-only cases, botsv2 being relatable, proof-index refusal by name, promotion to just after the anchor, and the rare misfit shape.
