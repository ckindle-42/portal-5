# Rebase — lane/hunt-d5 onto origin/main (D0, D1, D2, D3, D4, D6, D7 merged)

Branch rebased from `1507c3506` onto `0d1ed95ac`. main advanced three times during the run
(D8 + D10 at `23b86c139`, D9 at `0d1ed95ac`); each hop was taken onto the newest main, so the
branch is linear on `0d1ed95ac`. Two conflicts on the D2 x D5 hop, one on the D9 x D5 hop.

## Conflicts and how they were resolved

| hunk | D2 (main) | D5 | resolution |
|---|---|---|---|
| `inventory.py` header | probe budgets, `VOCABULARY_QUERY`, `_EVENT_METADATA` | drops `INVENTORY_ACCEL_MIN_EVENTS`, new `ACCEL_QUERY` | both kept; D5's `ACCEL_QUERY` replaces D2's, the min-events budget stays dropped |
| `inventory.py` helpers | `_declared_indexed`/`_probe_names`/`_presence_query`/`_absent` | `_model_root`/`_covers`/`_span` | both kept, D5's helpers appended |
| `_enumerate_fields` | `parse_only` short-circuit before any query | accelerated rung attempted first, before `_mechanism` | `parse_only` first, then accelerated, then `_mechanism` — a name the presence probe proved absent is labelled, never queried (D2's contract); every other name takes rung 1 first (D5) |
| `collect_inventory` | vocabulary + presence probes build `select_fields` input | `_Prober(..., _span(cards, start, end))` | D5's span-aware prober, then D2's vocabulary/presence/selection order |
| `test_hunt_inventory.py` | no raw-stats fallback for a summary list | `model_probes == 1`, no `by user` query | both assertion sets kept; D5's "no stats search" assertion dropped because D2's presence probe is itself a stats search |
| `inventory.py` constants | D9's `FLOW_MAX_GAP_SECONDS` / `FLOW_MAX_FLOWS` / `FLOW_MAX_PROBES` / `FLOW_HOST_ROWS` | D5's `ACCEL_QUERY` replacing the datamodel one | both kept, D9's flow budgets above D5's `ACCEL_QUERY`; nothing else of D9's flow logic touched |

## What is new in this commit pair

- `test_a_parse_only_name_never_reaches_a_summary_aggregate` pins the one behaviour the merge
  decides rather than inherits: a card whose field the events do not carry is `parse_only` with
  `model_probes == 0` and no `summariesonly=true` query, even when a covering summary exists.
- `docs/hunt/SLICE_D5_RUNG1.md`: the cost receipt is labelled as taken before D2 merged; D2's
  selection changes which fields rung 1 is tried for, so that receipt has to be re-taken.

## Not re-measured

No hunt run (brief: no hunt runs). Both cost receipts on the branch now describe a tree that
predates the other slice: D5's (228 searches, `model_probes` 192) predates D2; D2's (123
queries, 109 s) predates D5; D9's flow receipt predates both. The merged cost is unmeasured and
needs one run on the merged tree.

## Gate

See the dispatch RESULT block. `uv run mypy portal/` reports 650 errors in `scripts/`/`tests/`
in this environment **and the identical set on `origin/main`** (`coding_task/scratch/mypy_main.txt`
vs `mypy_head.txt`, error lines diffed with line numbers stripped), zero in `portal/` —
pre-existing, not from this rebase.
