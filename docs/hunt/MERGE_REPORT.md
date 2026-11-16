# MERGE report — one cross-generator ranking, chosen by leave-one-family-out

Answers two defects found in the first live misfit run (receipt snapshot
`snap_mf_1cb97f2`, code `1cb97f245`): a generator that was asked for and did not run,
and a final ranking that was generator blocks concatenated. Every number below was
computed offline from stored `notables.jsonl` receipts plus the on-disk corpora, using
the scoreboard's own coverage rule; no live run, no model, no synthetic data.

## 1. Bug 1 — similar_to_known vanished because it was never requested, and nothing said so

The live receipt (`snap_mf_1cb97f2/results/hunt/mf1/*/progress.json`, notables stage)
records `enabled: ['alerts','peer_rare','deviation']` — that was only the *standard
subset* `generate()` records; the stage never recorded the full requested list. misfit
ran (kept 59/33), so `--generators` was the CLI default `alerts,peer_rare,deviation,misfit`:
**`similar_to_known` was not in it, and `__main__` silently ignored the passed
`--knowledge-store`/`--knowledge-families` flags.** (Run 7 on `9235793` ran similar
because that invocation named it in `--generators`.)

Fix — a requested-but-not-run generator can no longer vanish:

- CLI exits **2** with a loud message when knowledge flags are passed without
  `similar_to_known` in `--generators` (and vice versa, as before).
- The notables receipt now records `enabled` (the full requested list) and a `merge`
  block; the CLI summary prints both.

## 2. Bug 2 — blocks are not a ranking: `merge.py`

Before: `notables.jsonl` order = `[similar…] [alerts…] [peer_rare…] [deviation…] [misfit…]`
— measured live as similar 0–299, alerts 300–329, peer_rare 330–629, deviation 630–929,
misfit 475+; kyoushi's reverse_shell sat at **misfit@475**. The judge then re-sorted
similar-first again (`_judge_order`), a second block hack.

Now: each generator keeps its own within-generator ranking, and one merge produces the
final order over the global priority `(similar_to_known, alerts, peer_rare, deviation,
misfit)` — a fixed constant, never per-corpus. Candidates (all evaluated below):

- `blocks` — the old concatenation (baseline);
- `interleave` — round-robin across generators by within-generator rank;
- `rrf` — reciprocal-rank fusion, k=60 (Cormack et al. 2009), which additionally fuses
  one finding raised by several generators (same `source_id` + first evidence line) into
  a single entry scoring `Σ 1/(k+rank)`.

`judge_stage` consumes the merged file order (the similar-first `_judge_order` hack is
removed), so the ranking survives the judge and the judge budget is spent in merged order.

## 3. Offline evaluation — recall before and after

Runs evaluated (stored receipts; coverage = the scoreboard rule over the gather logs):

| Run | Snapshot | Generators present | Steps |
|---|---|---|---|
| mf1/kyoushi | `snap_mf_1cb97f2/…/mf1/kyoushi` | alerts 7, peer_rare 300, deviation 164, misfit 59 | 12 |
| mf1/santos | `snap_mf_1cb97f2/…/mf1/santos` | alerts 30, peer_rare 300, deviation 300, misfit 33 | 21 |
| s3a/kyoushi | `snap_s3_9235793/…/knowledge_s3a/kyoushi` | similar 300, alerts 7, peer_rare 300, deviation 164 | 12 |
| s3a/santos | `snap_s3_9235793/…/knowledge_s3a/santos` | similar 300, alerts 30, peer_rare 300, deviation 300 | 21 |

**russell:** keys exist (`corpora/ait_lds_v21/russellmitchell_ingest/keys.jsonl`) but no
stored notables run exists for russell in any snapshot — it cannot be scored and did not
participate in the selection. Declared, not substituted.

Recall (steps covered within the top N of the final ranking):

| Run | Merge | @50 | @100 | @all |
|---|---|---|---|---|
| mf1/kyoushi | blocks (before) | 0/12 | 0/12 | 5/12 |
| | **interleave (after)** | **2/12** | **4/12** | 5/12 |
| | rrf | 2/12 | 4/12 | 5/12 |
| mf1/santos | blocks (before) | 0/21 | 0/21 | 2/21 |
| | **interleave (after)** | 0/21 | **2/21** | 2/21 |
| | rrf | 0/21 | 2/21 | 2/21 |
| s3a/kyoushi | blocks (before) | 7/12 | 10/12 | 11/12 |
| | **interleave (after)** | 7/12 | **8/12 (−2)** | 11/12 |
| | rrf (10 duplicates fused) | 7/12 | 8/12 | 11/12 |
| s3a/santos | blocks (before) | 6/21 | 6/21 | 9/21 |
| | **interleave (after)** | 6/21 | **8/21** | 9/21 |
| | rrf | 6/21 | 8/21 | 9/21 |

Leave-one-family-out selection (maximise covered steps at @50, then @100, then @all on
the training family's runs):

- hold out **kyoushi** → train on santos: interleave (6, 10, 11) > blocks (6, 6, 11) →
  **interleave chosen**; held-out result: mf1/kyoushi @50 0→2, @100 0→4; s3a/kyoushi
  @50 7→7, @100 10→8.
- hold out **santos** → train on kyoushi: interleave (9, 12, 16) > blocks (7, 10, 16) →
  **interleave chosen**; held-out result: mf1/santos @100 0→2; s3a/santos @100 6→8.

**Chosen and baked: `DEFAULT_MERGE = "interleave"`.** Both folds pick it; `rrf` ties on
recall in every run (cross-generator duplicates exist only in s3a/kyoushi — 10 fused
entries — and fusing them did not change any covered rank), so rrf remains available but
is degenerate with interleave while generators raise disjoint findings.

Concrete effect on the reported win: kyoushi's reverse_shell notable moves from
**rank 475 → rank 19**; the merged top-50 of mf1/kyoushi is peer_rare 15, deviation 14,
misfit 14, alerts 7.

## 4. Honest caveats

- **s3a/kyoushi @100 regresses 10→8**: similar_to_known loses its 300-slot head block
  (interleave gives it ~25 of the top 100). Both LOFO folds still choose interleave on
  aggregate; no per-corpus or per-generator-set constants were introduced, and nothing
  was tuned after seeing these numbers.
- recall@all is invariant by construction — the merge re-ranks the same kept set.
- No stored run has all five generators at once (mf1 lacks similar; s3a lacks misfit);
  the priority order covering all five is exercised only by tests until the next live run.
- The offline harness re-ranks stored notables; a live re-run can keep different sets
  (slices, budgets), though the merge itself is deterministic given the same notables.

## Appendix — reproduction (all offline)

Per run: read `notables.jsonl`; rebuild `Notable`s; compute per-notable coverage of
`keys.jsonl` lines once with `scoreboard._claim/_on_source/_covers/event_time` over
`<corpus>/<family>/gather`; then for each candidate call the real
`merge.merge_notables(notables, run.MERGE_PRIORITY, method)` and recompute each step's
first covered rank in the merged order. Keys:
`corpora/hunt_bed/kyoushi_s1_ingest/keys.jsonl`,
`corpora/ait_lds_v21/santos_ingest/keys.jsonl` (roots under `/Volumes/data01/portal5_hunt/`).
