# FINDING — Hunt E7: judge measurement (stratified AUC) and prompt

Slice E7 of `docs/hunt/ORCACYBER_DEEP_DIVE_3.md` §6. Offline work only: the scoreboard and
prompt were exercised over the stored Round-2 runs on disk; no Splunk, no `launch.sh`, no
held-out sets.

## Change

- `scoreboard.py` `_judge_block`: added `auc_pooled` over the comparable generators
  (`deviation`, `misfit`, `peer_rare`, `alerts`, `set_novelty`), `auc_by_generator` (per
  generator: judged/bad/good/auc/yes-rate), and `ranked_judged`/`ranked_yes_rate` for
  `similar_to_known`. The legacy generator-blind pooled AUC is kept as `auc_all`.
- `scoreboard.py` `_judge_lines`: prints the legacy line as `AUC all`, then `judge auc_pooled`
  with the declared stratum, a per-generator table, and the ranked generator's yes-rate as its
  own line.
- `judge_notables.py` `_known_lines`: nearest known items are now score + family only
  (`- matched item 0.986 (kyoushi)`); `label`, `label_kind` and `label_basis` (attack-step
  names / `known_bad` labels) are no longer rendered, and duplicate score/family lines are
  collapsed.
- `judge_notables.py` `notable_body`: renders the decision statistic — `measure: <name> = <value>`
  generally, and `margin = <known_bad_minus_good> (threshold 0)` for `similar_to_known`.
- `similar.py` `_ranked_notables`: the notable's measure is now the known-bad-minus-known-good
  margin (threshold 0) and `why` states that margin, the matched family and cosine, and the
  measured AUC, without the attack-step label or the literal `known-bad` wording.

## Offline proof (stored Round-2 runs, read-only)

Command (family substituted):

```bash
uv run python -m portal.modules.security.core.hunt.notables.scoreboard \
  --out /Volumes/data01/portal5_hunt/hunt_proof_r2_santos/v2/santos \
  --keys /Volumes/data01/portal5_hunt/corpora/ait_lds_v21/santos_ingest/keys.jsonl
```

santos (531 judged):

```
judge  judged 531  bad 36  good 495  AUC all 0.151  ...
judge auc_pooled 0.3 over deviation,misfit,peer_rare,alerts,set_novelty
judge auc_by_generator alerts n/a  (judged 47 bad 0 good 47 yes-rate 0.8936...)
judge auc_by_generator deviation 0.399  (judged 119 bad 31 good 88 yes-rate 0.2941...)
judge auc_by_generator misfit n/a  (judged 9 bad 0 good 9 yes-rate 0.4444...)
judge auc_by_generator peer_rare n/a  (judged 60 bad 0 good 60 yes-rate 0.6666...)
judge auc_by_generator similar_to_known 0.008  (judged 296 bad 5 good 291 yes-rate 0.9966...)
judge similar_to_known yes-rate 0.9966216216216216  (judged 296, excluded from auc_pooled)
```

kyoushi (438 judged): `AUC all 0.403`, `auc_pooled 0.417`, `similar_to_known yes-rate
0.9798... (judged 248)`.

russell (576 judged): `AUC all 0.332`, `auc_pooled 0.628`, `similar_to_known yes-rate 1.0
(judged 300)`.

The new pooled figures reproduce §5.2's non-similar-only figures exactly (santos 0.300,
kyoushi 0.417, russell 0.628), while the saturated ranked stratum stays visible as its own
yes-rate.

## Acceptance mapping

| property | test |
|---|---|
| separation reported per generator | `test_judge_separation_is_reported_per_generator` |
| pooled figure excludes the ranked list generator; its yes-rate is separate | `test_the_pooled_judge_auc_excludes_a_rank_list_generator` |
| prompt carries the measure and not the label | `test_the_notable_prompt_carries_the_measure_and_not_the_label` |

## Unproven here (orchestrator runs)

- The live acceptance line: a fresh `_v2` scoreboard prints the table above and the pooled
  figure moves ≤ 0.02 when the run is repeated without `similar_to_known`. That needs the
  orchestrator's live stack and Splunk; this lane only re-read the stored runs.
- `./scripts/smoke_stream.sh` was not run (worker lanes do not run the live stack; no
  streaming code changed).
