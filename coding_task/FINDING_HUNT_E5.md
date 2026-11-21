# FINDING — E5: the notables contract (alert cards, skip tally)

Lane `lane/hunt-e5`, slice E5 of `docs/hunt/ORCACYBER_DEEP_DIVE_3.md` §6 (§4.2 is the defect).
Offline only: no Splunk, no model, no `launch.sh`, no held-out set touched.

## Property implemented

1. A candidate behaviour is minted only for a source whose card feeds a generator that reads
   behaviours — a complete inventory list on an alert-kind source (`botsv2:pan:threat`) no longer
   produces one.
2. `similar_to_known` skips a behaviour source whose card does not consume it and tallies the skip
   (`skipped_sources: {source: behaviours}`) in its receipt instead of raising `SimilarityError`;
   the notables receipt carries the same tally as a top-level key.

## Change

- `inventory.py`: `_consumers(cards)` unions `card_consumers` per source across its parts;
  `_unseen_candidates(document, seen, facts, consumers)` drops a joint whose source consumes none
  of `ROLE_CONSUMERS` (the card consumers that read behaviour rows: behaviours / peer_rare /
  similar_to_known / manifest). `apply_inventory` takes `cards` and builds that map.
- `similar.py`: `_ranked_notables` computes `eligible_sources`, counts every ineligible behaviour
  into `skipped` and `continue`s instead of raising; it returns `(notables, skipped)` and
  `generate_similar` puts `skipped_sources` in its receipt (`kinds_by_source` is gone with the
  error message that used it).
- `run.py`: `_stored_inventory` passes `cards`; the notables receipt always carries
  `skipped_sources` (`{}` when `similar_to_known` is off, the tally when it ran).

## Why `ROLE_CONSUMERS` and not the raw `--generators` list

The stage's generator names do not line up with `CARD_KIND_CONSUMERS`: `deviation` and `misfit`
consume behaviour rows but declare no consumer name, and `alerts` consumes alert cards — which is
exactly what lets an alert-card candidate through. `ROLE_CONSUMERS` is the existing constant for
"consumers that need roles", i.e. the set that can use a `Behaviour`, and it is what
`behaviours.py`/`deviation` already gate on (`"behaviours" in card_consumers(card)`).

## Offline proof — same inputs, HEAD vs this change

`uv run python coding_task/scratch/e5_proof.py` (needs `PYTHONPATH=.` from a worktree: without it
`portal` resolves to the shared `/Users/chris/projects/portal-5/.venv` copy of the live checkout).

Inputs: one complete inventory joint on `botsv2:pan:threat` with role `object`/field `dest` and a
row `dest=203.0.113.99` (the R2 run's own joint shape), one alert card for that source, no stored
behaviour from it.

HEAD (`e522dfa47`, before this change):

```
apply_inventory signature: 3-arg (HEAD)
candidates minted for the alert card: 1
  candidate source=botsv2:pan:threat object=203.0.113.99
RAISED SimilarityError: behaviour sources need an activity card with roles: botsv2:pan:threat (kinds: alert)
```

This change:

```
apply_inventory signature: 4-arg (fixed)
candidates minted for the alert card: 0
returned notables=0 skipped_sources={}
fed one hand-minted alert behaviour: notables=0 skipped={'botsv2:pan:threat': 1}
```

The second line of each block is the whole slice: the candidate is not minted, and a behaviour from
the same source that reaches `_ranked_notables` any other way is skipped and counted, not fatal.

## Tests (net +113 lines, three new; one replaced)

- `tests/unit/test_hunt_inventory.py::test_a_complete_list_on_an_alert_card_mints_no_candidate`
- `tests/unit/test_hunt_notables_similarity.py::test_similar_skips_a_source_no_generator_consumes_and_records_it`
  (replaces `test_similarity_error_names_source_and_actual_card_kind`, which asserted the removed raise)
- `tests/unit/test_hunt_run_injection.py::test_notables_completes_with_an_alert_card_candidate_present`
  — real `main()` notables stage with an alert card in `sources.json` and the alert joint in
  `inventory.json`; asserts exit 0, `notables.jsonl` written, `skipped_sources == {}`,
  `inventory.candidates == 0`. Against HEAD it exits non-zero on the `SimilarityError`.

## Gates (this tree)

```
uv run pytest tests/unit/ -q            -> 3059 passed, 22 skipped
uv run ruff check .                     -> All checks passed!
uv run ruff format --check .            -> 1737 files already formatted
python3 scripts/complexity_report.py --gate -> GATE OK (god_lines 68,591 <= 71,202)
uv run mypy portal/                     -> 650 errors, all in scripts/**, portal_channels/**,
                                           tests/benchmarks/** files this change does not touch,
                                           and none in the three changed files (pre-existing)
```

## Live proof — orchestrator runs

Re-run the stage that crashed in R2 (its `run_b` dir keeps the cards, inventory and behaviour
store; keep the run dir, the fix is code-only):

```
export PORTAL_HUNT_JUDGE_URL=... PORTAL_HUNT_JUDGE_MODEL=...
export PORTAL_HUNT_EMBEDDING_URL=http://localhost:9099
export PORTAL_HUNT_EMBEDDING_MODEL=google/embeddinggemma-2
export PORTAL_HUNT_EMBEDDING_KEY_ENV=PIPELINE_API_KEY
hunt=portal.modules.security.core.hunt.notables
run=$PWD/coding_task/scratch/hunt_proof_r2_botsv2

uv run python -m $hunt --index botsv2 --out $run/run_b/botsv2 --stage notables --family botsv2 \
  --knowledge-store /Volumes/data01/portal5_hunt/knowledge/knowledge_v2_20261116.duckdb \
  --knowledge-families kyoushi,santos,russell
```

Expected: exit 0 (the R2 run exited 1 in 4:08 with `SimilarityError: behaviour sources need an
activity card with roles: botsv2:pan:threat (kinds: alert)`), `run_b/botsv2/notables.jsonl` exists,
and

```
uv run python -c "
import json; r=json.load(open('$run/run_b/botsv2/progress.json'))['stages']['notables']
print(r['skipped_sources'], r['inventory']['candidates'], r['similar_to_known']['kept'])"
```

prints `{} 31 <kept>` — `{}` because the alert candidate is never minted (the R2 run minted 32), and
`similar_to_known` still present and non-empty. A non-empty `skipped_sources` on botsv2 means a
behaviour from a non-consuming source reached the similar generator by some other path: that is the
skip firing, not a failure, but it should be named in the report.

Tuned families (`--stage notables` on santos/kyoushi/russell runs): `skipped_sources` must be `{}`
and `inventory.candidates` unchanged from their previous runs — no activity source loses a
candidate.

## Not proven here

- Any live Splunk/notables run: none was executed from this worktree (orchestrator-only).
- That no other live path mints a behaviour from an alert-kind source (e.g. a store written by an
  older tree): the similar-side skip covers it, but only a live run shows the tally.
- botsv2's `pan:threat` joint is still enumerated and queried by the inventory (the fix drops the
  candidate, not the query); its cost is unchanged from R2.
