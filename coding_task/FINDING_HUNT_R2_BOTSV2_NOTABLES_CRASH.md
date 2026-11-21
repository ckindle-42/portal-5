# FINDING — R2 botsv2: `notables` crashes on the untuned control (inventory candidate for an alert card)

Lane `lane/hunt-proof-r2-botsv2`, HEAD `26aee7eee`, 2026-11-21 18:39Z. Grading only: no code
or Splunk change; the run is the brief's own command split by stage (see
`coding_task/FINDING_HUNT_R2_BOTSV2_RUN_A.md` for why `--stage all` cannot run).

## The crash

`--stage notables` on the run whose behaviours stage completed (`run_b`, `events_read=259769`)
exits 1 in 4:08 with:

```
File ".../hunt/notables/similar.py", line 303, in _ranked_notables
    raise SimilarityError(
portal.modules.security.core.hunt.notables.similar.SimilarityError:
behaviour sources need an activity card with roles: botsv2:pan:threat (kinds: alert)
```

`similar.py:_ranked_notables` demands that **every** behaviour in the working set come from a
card that consumes `similar_to_known`; a behaviour from an **alert** card is a hard error, not
a skip.

## Where the alert-card behaviour comes from

`run_b`'s behaviour store holds 18,668 behaviours over 75 sources, **none from `pan:threat`**
(`behaviours.duckdb`: `pan:traffic` 198, `pan:system` 15, no `pan:threat` row). The
`pan:threat` behaviour is added in memory by the notables stage's own
`apply_inventory` (`run.py:548`, `inventory.py:1511`), from the inventory joint this R2 run
now produces for that sourcetype:

```json
{"source_id": "botsv2:pan:threat", "card_id": "botsv2:pan:threat", "sourcetype": "pan:threat",
 "fields": [{"role": "object", "field": "dest"}], "status": "complete", "mechanism": "stats",
 "events_scanned": 2, ...}
```

Reproduced offline against the same run dir (no Splunk, no model):

```
store behaviours 18668
after inventory 18700 replaced 0 candidates 32
sources only after inventory: {'botsv2:pan:threat': 1}
```

So exactly one candidate — one behaviour from one 2-event alert source — aborts the whole
notables stage.

## Why this is new on `main`, not a pre-existing condition

The 2026-11-21 morning verdict run (`REPORT_HUNT_VERDICT_botsv2.md`, HEAD `83f72271e`)
completed `--stage notables` and wrote 876 notables; its inventory had 13 complete lists and
`pan:threat` was not among them (`unavailable:mechanism` for the wide lists). The R2 slice D2
gave the inventory a field vocabulary and 32 complete lists, `pan:threat`'s included; D2/D3's
candidate path then feeds an alert card into `similar_to_known`. Both the vocabulary growth
(`fields: complete 32` vs 13) and the candidate count (`candidates 32` vs 13) are in this
run's receipts.

## What it blocks

`notables.jsonl` is never written, so `relate`, `judge` and every scoreboard recall number
have no input. The brief's acceptance checks D8 (`promoted_unjudged == 0`) and the
scoreboard's `C0 modes`/`case` blocks cannot be produced from the brief's own command path on
current `main`.

The two repairs are both code changes and out of this lane's scope (the brief forbids them):

1. `inventory._unseen_candidates` should not create a candidate for a card whose `kind` its
   generators do not consume (an alert card), or
2. `similar._ranked_notables` should skip a behaviour whose card does not consume
   `similar_to_known`, as every other generator does, rather than raising.

Option 2 is the narrower fix: the store already contains alert-kind sources in other runs
(`ess_content_importer`, `pan:threat`) and the check is on the caller's whole behaviour list,
so any future complete list for an alert source reproduces this.
