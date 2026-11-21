# S5 — generator weights measured by marginal contribution

Lane `lane/hunt-s5`, 2026-11-20. Offline score of the stored run
`/Volumes/data01/portal5_hunt/snap_neon_02cc2e3/results/hunt/neon/` (no Splunk, no live stack).

`merge.conditional_weights` (covered/existed, a global denominator) is replaced by a measured
marginal: for each family, re-merge the stored per-generator lists without one generator (same
method, the dropped share not redistributed), count the steps that leave the @50 head; LOFO
averages those losses, floors each generator at `UNMEASURED_WEIGHT`, and records
`attribution@50` beside it in the per-family generator table. `PORTAL_HUNT_MERGE_WEIGHTS`
remains the delivery mechanism.

## Measured marginal weights, stored run

Weight = mean `marginal@50` over families where the generator had candidates, floored at 1.

| generator | all | held-out botsv2 | held-out kyoushi | held-out russell | held-out santos |
|---|---|---|---|---|---|
| similar_to_known | 4 | 5 | 4 | 3 | 3 |
| deviation | 2 | 2 | 2 | 1 | 2 |
| misfit | 1 | 1 | 1 | 1 | 1 |
| alerts | 1 | 1 | 1 | 1 | 1 |
| peer_rare | 1 | 1 | 1 | 1 | 1 |
| relate | 1 | 1 | 1 | 1 | 1 |

Per-family `marginal@50` / `marginal@100` behind the mean:

| family | steps | similar | deviation | misfit | alerts | peer_rare |
|---|---|---|---|---|---|---|
| botsv2 | 14 | 0 / 0 | 2 / 2 | 0 / 0 | 0 / 0 | 0 / 0 |
| kyoushi | 12 | 3 / 3 | 1 / 1 | 0 / 0 | 0 / 0 | 0 / 0 |
| russell | 22 | 6 / 6 | 4 / 2 | 0 / 2 | 0 / 0 | 0 / 0 |
| santos | 21 | 5 / 5 | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 |

`alerts` and `relate` had zero candidates on every family and keep a unit weight; `misfit` on
russell is the acceptance case for "hit outside the head": `marginal@50 = 0`,
`marginal@100 = 2`, weight still 1.

The vector to deliver (all four families): `{"similar_to_known": 4, "deviation": 2, "misfit": 1,
"alerts": 1, "peer_rare": 1}` (plus `relate: 1` if the relate signal is merged).

## Reproduce

```bash
uv run python -m portal.modules.security.core.hunt.notables.scoreboard \
  --out /Volumes/data01/portal5_hunt/snap_neon_02cc2e3/results/hunt/neon \
  --keys botsv2=/Volumes/data01/portal5_hunt/corpora/botsv2_keys/keys.jsonl \
  --keys kyoushi=/Volumes/data01/portal5_hunt/corpora/hunt_bed/kyoushi_s1_ingest/keys.jsonl \
  --keys santos=/Volumes/data01/portal5_hunt/corpora/ait_lds_v21/santos_ingest/keys.jsonl \
  --keys russell=/Volumes/data01/portal5_hunt/corpora/ait_lds_v21/russellmitchell_ingest/keys.jsonl \
  --weights
```

The last block of the output is `C4 marginal generator weights (rule)`, one row per held-out
family. Scored in ~15 s on this host (read-only).
