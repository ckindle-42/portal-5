# GENERATOR WEIGHTS report — the merge now spends its top slots where a generator was measured to work

Answers the three defects found in the first live russell run (receipt snapshot
`snap_ru_e4d914d`, code `e4d914d66`): `similar_to_known` reliability at chance with
top-50 coverage 0, true notables stranded at 51–100, and `alerts existed=0` on a corpus
that carries 12,558 IDS detections. Every number below was computed offline from the
stored `notables.jsonl` receipts, the on-disk corpora and the knowledge store, using the
scoreboard's own coverage rule; no live run, no model, no synthetic data.

Runs: kyoushi and santos at `snap_full_b21884a/results/hunt/full/<family>`, russell at
`snap_ru_e4d914d/results/hunt/ru/russell`; keys under
`corpora/hunt_bed/kyoushi_s1_ingest/` and `corpora/ait_lds_v21/{santos,russellmitchell}_ingest/`.

## 1. What occupied the top 50

The merge was an equal round-robin over five generators, so each got a fifth of the
budget regardless of whether it had ever covered a labelled step:

| family | steps | @50 | @100 | @all | similar | deviation | misfit | peer_rare | alerts |
|---|---|---|---|---|---|---|---|---|---|
| kyoushi | 12 | 10 | 12 | 12 | 7/8/10 | 5/6/8 | 2/2/3 | 0/0/0 | 0/0/0 |
| santos | 21 | 11 | 11 | 17 | 7/7/11 | 4/4/12 | 0/0/0 | 0/0/0 | 0/0/0 |
| russell | 22 | 4 | 16 | 17 | 0/12/14 | 4/8/12 | 0/0/0 | 0/0/0 | 0/0/0 |

`peer_rare` covered no step in any of the 55 steps across the three families, at any cut,
and `alerts` covered none of the 33 steps in the two families where it ran — yet each held
a quarter of every top 50. Two causes are separable:

- **`similar_to_known`'s own head was uninformative.** 14 behaviours in the russell run
  (13 in its stored notables) carry a statement that is nothing but role words and masks —
  `to * * * * * *`, `to * * * *`, `actor *`. The santos knowledge family holds two such
  statements, so those behaviours match a "known bad" at cosine 1.000 and sort to the top
  of the similarity list. They are one third of the top 56 merged slots and cover nothing:
  the real match, `program sudo` (escalated_command, escalated_sudo_command,
  escalated_sudo_session), sat at merged rank 52. Dropping statements with no content
  token — they cannot describe a behaviour, so they are not embedded — moves russell's
  top-50 from 4/22 to 14/22 and kyoushi's from 10/12 to 11/12.
- **Every other generator got an equal share whatever its measurement.** See §2.

## 2. Weighting by measured leave-one-family-out reliability

Reliability is measured in the currency the scoreboard already uses: steps whose first
covering notable at top 50 comes from that generator, over the steps in the family. It is
computed from the *other* families' receipts and applied to the held-out one.

`merge.merge_notables(..., "weighted")` is a deficit round-robin: the next slot goes to the
group furthest behind `taken/weight`, so each generator's share of the merged head follows
its weight. `alerts` and `peer_rare` carry weight 0 and keep their within-generator order
at the tail, so `@all` recall is unchanged by construction. A generator that is not named
in the vector keeps a unit weight (it was never measured, not measured at zero).

Candidate schemes, each with the uninformative-statement fix applied first:

| held out | scheme | @50 | @100 | @all |
|---|---|---|---|---|
| kyoushi | equal | 11 | 12 | 12 |
| | measured@50 | 11 | 11 | 12 |
| | measured@100 | 11 | 11 | 12 |
| santos | equal | 11 | 11 | 17 |
| | measured@50 | 12 | 15 | 17 |
| | measured@100 | 11 | 16 | 17 |
| russell | equal | 14 | 16 | 17 |
| | measured@50 | 16 | 16 | 17 |
| | measured@100 | 16 | 16 | 17 |
| **total** | equal | 36 | 39 | 46 |
| | **measured@50** | **39** | **42** | **46** |
| | measured@100 | 38 | 43 | 46 |

Selection rule as in `MERGE_REPORT.md` — maximise @50, then @100, then @all: **measured@50
wins**. The scheme is chosen out of fold; the baked vector is then fitted on all three
families, as averaged rates × 100:

```python
DEFAULT_WEIGHTS = {"similar_to_known": 31, "deviation": 26, "misfit": 6,
                   "alerts": 0, "peer_rare": 0}
```

Predicted recall of the shipped code (stored receipts replayed through the new ranking):

| family | before @50 | after @50 | before @100 | after @100 | @all |
|---|---|---|---|---|---|
| kyoushi | 10 | **12** | 12 | 12 | 12 |
| santos | 11 | **12** | 11 | **16** | 17 |
| russell | 4 | **16** | 16 | 16 | 17 |

Generator mix of the first 50 (russell): before similar 13, peer_rare 13, deviation 12,
misfit 12; after similar 24, deviation 21, misfit 5.

## 3. `alerts existed=0` on a corpus with 10,457 detections

The russell corpus carries 10,457 `event_type=alert` JSON events across seven hosts'
`suricata/eve.json`, and 2,101 Suricata fast-log lines — the same `vpn` and `mail` events
in text form. Neither path reached the generator:

- **The eve.json alert part was never discovered.** Cards are partitioned on `event_type`,
  and a part needs 4 sampled events. The sample is 3 equal time windows × 40 events and the
  probe re-read the *same* 3 windows at 400 — so 3,605 sampled eve.json events in the
  behaviours store contain zero alerts, and `event_type=alert` never became a part. The
  probe now asks the index for the detection marker directly
  (`… source="/suricata/eve.json" event_type="alert" | head 400`) for JSON sources, and
  keeps the wider read as the fallback when that returns nothing.
- **`fast.log` was an activity source.** `is_alert_event` only recognised JSON
  `event_type=alert`, and `_template_card` hard-coded `kind="activity"`, so every fast-log
  alert line became a behaviour and was never seen by the alerts generator. `is_alert_line`
  now reads the Suricata fast-log shape (`MM/DD/YYYY-HH:MM:SS.micro  [**] [gid:sid:rev]`),
  and a template card whose sample is entirely alert lines is `kind="alert"` with
  `kind_note="fast_log_alert_lines"`.

## 4. `similar_to_known` reliability: what was measured, and what it means

The store (`knowledge_v2_20261116.duckdb`, families kyoushi/santos/russell, 2 557 items,
1 252 distinct statements) does not separate its two labels across families:

| run | pooled, as recorded | equal pools | per-fold macro | shipped: contradiction + uninformative dropped, equal pools, macro |
|---|---|---|---|---|
| kyoushi | 0.836 | 0.838 | 0.861 | 0.904 (bad-only 0.828) |
| santos | 0.487 | 0.508 | 0.502 | 0.443 (bad-only 0.495) |
| russell | 0.466 | 0.470 | 0.444 | 0.418 (bad-only 0.421) |

Shipped values are the measured AUC of the score the ranking actually uses
(`known_bad_minus_good`, the contrast, for all three runs — the same mode the recorded
receipts used).

Three estimator defects were real and are fixed: candidates were capped at 512 bad rows
against 44–64 good ones, so `max` was taken over pools of very different size; the two
family folds were pooled into one AUC although their cosine scales differ; and the
reported number was the maximum of two metrics measured on the same rows. Each fold is now
scored separately, averaged, and reported (`reliability.folds`). The score mode is no
longer re-selected on noise: the contrast keeps the ranking unless it measures at or below
chance while bad-only measures above it, which would otherwise have flipped the mode on
santos and russell between runs.

Fixing the estimator does not rescue santos or russell, because the defect is in the
labels, not the arithmetic: 19 statements carry **both** `known_bad` and `known_good`
somewhere in the store (80 cross-family pairs; 99, 62 and 81 item rows dropped per run), and 30–53% of each family's own known-good
items sit at cosine ≥ 0.95 from its own known-bad items — `actor 0 did USER_START` is a
labelled attack step in one family and background in another. Such a statement can no
longer enter the reference pool as either class (`load_for_run` drops every contradicted
statement and reports the count). The fold direction still flips the answer
(`kyoushi→russell` 0.258 against `russell→kyoushi` 0.628), which is the signature of a
composition mismatch rather than missing signal — so the number is reported honestly as
near chance on these two families and is **not** used as a merge weight. The merge weights
above come from measured step coverage, which is the same currency for every generator.

## 5. Honest caveats

- `peer_rare`'s zero is partly a measurement artefact: 281 of its 300 notables carry an
  evidence query with no index term, so the coverage rule can only attribute them by time
  window. It is weighted 0 on that measurement; a term-carrying peer_rare notable would not
  be, because it would cover.
- All numbers replay *stored* notables. A live run keeps its own slices and budgets, so
  the identical sets are not guaranteed; the ranking given the same notables is
  deterministic. The replay is faithful because the score mode is unchanged (contrast for
  all three runs), so the within-generator order of the stored similar notables is what a
  new run would produce; the one difference is that the 300 kept now come from a pool with
  the uninformative behaviours removed, so a few entries at the tail can differ.
- Adding the alert cards (russell) and the extra parts (kyoushi/santos) sends new notables
  into the merge. Their effect is not in the table above and cannot be predicted offline.
- The weight vector was fitted on three families; a fourth family's generator mix may
  differ, and `alerts` in particular is weighted 0 from two families where it covered
  nothing.
