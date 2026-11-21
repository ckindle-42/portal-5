# D7 — the merge consumes the measured marginal

Lane `lane/hunt-d7`, 2026-11-21. Slice D7 of `docs/hunt/ORCACYBER_DEEP_DIVE_2.md` §5 (RC6 in §3.6).
Offline only: stored runs under
`/Users/chris/projects/portal-5-hunt-proof-run/coding_task/scratch/hunt_proof_20261120T232700/`,
no Splunk, no stack, no held-out index.

## The defect

The scoreboard already measures each generator's marginal (`marginal@50`, LOFO-averaged) and
prints it. Nothing delivered that vector to a run: `PORTAL_HUNT_MERGE_WEIGHTS` was never set by
the only script that runs the plan, and `merge.py` recorded `weights_source: "default"` whether or
not a measured vector was ever offered. So the head was filled by `DEFAULT_WEIGHTS`
(`similar_to_known` 31, `deviation` 26) while the same run's own table measured `similar_to_known`
at **1** step and `deviation` at **9**.

## What changed

- `scoreboard.py` — `--weights-out PATH` writes the all-fold measured vector (plus its rule, folds
  and source) in the form the merge consumes; `--weights` is implied. The per-generator table now
  prints **head@50** (that generator's share of the merged head) beside `attribution@50` /
  `marginal@50` and **used** (the weight the run actually merged with), so the measured-vs-used gap
  is visible in the report rather than inferable from `progress.json`.
- `run.py` — `PORTAL_HUNT_MERGE_WEIGHTS` now takes either a JSON vector (hand override) or a path
  to a `--weights-out` file (measured). A named file that is absent or not JSON **fails the run**;
  it never falls back to `DEFAULT_WEIGHTS` silently.
- `merge.py` — records `weights_source` as `default` / `measured` / `override`; a declared vector
  that is empty raises; a generator the vector never measured keeps its `DEFAULT_WEIGHTS` value
  (not a unit share) and is named in `weights_defaulted`.
- `coding_task/RUN_HUNT_REDESIGN.sh` — runs the scoreboard's marginal pass over `HUNT_WEIGHTS_FROM`
  (an earlier scored run of the same families) first, writes `merge_weights.json` into the new run
  dir and exports `PORTAL_HUNT_MERGE_WEIGHTS`; without it, prints that the run merges on defaults.

## Property, proven offline on the stored `_v2` run

Property: `progress.json:stages.notables.merge.weights_source != "default"` once the measured
vector is delivered, and the head's composition is reported beside `attribution@50`/`marginal@50`.

Stored run, as found (three `_v2` families):

```
merge weights_source="default" weights={deviation 26, similar_to_known 31, misfit 6, alerts 0, peer_rare 0}
```

Measured by the scoreboard's marginal pass over the same stored run (`--weights-out`):

```
all        deviation 6   misfit 1   similar_to_known 2   alerts 1   peer_rare 1   relate 1
  held out kyoushi   7/1/2/1/1/1
  held out russell   6/1/2/1/1/1
  held out santos    4/1/3/1/1/1
```

The santos `_v2` run alone measures `{deviation 9, similar_to_known 1, …}` — the deep dive's §3.6
numbers, re-derived.

Re-merging the stored rows with that vector (read-only; `PORTAL_HUNT_MERGE_WEIGHTS` pointing at the
written file, `merge_notables` from the product code):

| family | head@50 as stored | head@50 re-merged on the measured vector |
|---|---|---|
| santos `_v2` | deviation 22, similar_to_known 24, misfit 4 | deviation 34, similar 4, alerts 4, misfit 4, peer_rare 4 |
| kyoushi `_v2` | deviation 24, similar_to_known 22, misfit 4 | deviation 26, similar 9, others 5 each |
| russell `_v2` | deviation 25, similar_to_known 21, misfit 4 | deviation 26, similar 9, others 5 each |

Receipt under the delivered vector: `weights_source="measured"`, weights
`{alerts 1, deviation 6, misfit 1, peer_rare 1, relate 1, similar_to_known 2}`.

The run's own report now carries both halves of the gap, e.g. santos `_v2`:

```
generator marginal (candidates kept head@50 attribution@50 marginal@50/@100 measured used)
  deviation              16694    123     22       9          9/7         9    26
  similar_to_known       16669    300     24       7          1/1         1    31
```

## Reproduce

```bash
cd /Users/chris/projects/portal-5-hunt-d7
run=/Users/chris/projects/portal-5-hunt-proof-run/coding_task/scratch/hunt_proof_20261120T232700
out=coding_task/scratch/d7

# 1. measure + write the vector (read-only score of a stored run)
uv run python -m portal.modules.security.core.hunt.notables.scoreboard --out "$run/v2" \
  --keys kyoushi=/Volumes/data01/portal5_hunt/corpora/hunt_bed/kyoushi_s1_ingest/keys.jsonl \
  --keys santos=/Volumes/data01/portal5_hunt/corpora/ait_lds_v21/santos_ingest/keys.jsonl \
  --keys russell=/Volumes/data01/portal5_hunt/corpora/ait_lds_v21/russellmitchell_ingest/keys.jsonl \
  --weights --weights-out "$out/merge_weights_v2_3fam.json"

# 2. the same stored rows, merged through the product code with that file delivered
PORTAL_HUNT_MERGE_WEIGHTS="$out/merge_weights_v2_3fam.json" \
  uv run python coding_task/scratch/d7/prove_d7.py v2/santos
```

Step 2 prints `env source='measured'` and, per merge, `weights_source` and `head@50`.

## Caveats

- Re-merging a stored `notables.jsonl` is **not** bit-identical to the order it was written in
  (first divergence at index 7 on santos), so head composition is reported from the stored file
  (`head@50` reads `rows[:50]`) and the "measured" column is that same row set re-merged.
- The measured vector is only as good as the run it was measured on: a first run on a new index
  routes through `DEFAULT_WEIGHTS` unless `HUNT_WEIGHTS_FROM` names an earlier scored run.
- No live run was made (operator hold). The end-to-end `progress.json` claim is offline
  (unit-level through `main()`) plus code inspection; the orchestrator's live run closes it.
