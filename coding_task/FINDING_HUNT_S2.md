# HUNT S2 — entity spine and episodes (lane `lane/hunt-s2`, 2026-11-20)

Slice S2 of `docs/hunt/ORCACYBER_HUNT_PLAN.md` §4, built and proven on the stored run
`/Volumes/data01/portal5_hunt/snap_neon_02cc2e3/results/hunt/neon/` (copied to
`coding_task/scratch/s2/` — the snapshot itself was read-only). No live Splunk search was made,
no held-out set (`hb_ait_wheeler`, `hb_cloudobs_aws`, `botsv1`) was opened, `.env` was not sourced.

## 1. What S2 added

| file | change |
|---|---|
| `portal/modules/security/core/hunt/notables/spine.py` (new) | `entities.duckdb`: `entities` rows, cadence-segmented `episodes`, `episode_links`, and an `event_index` for verification. Entity kinds are shape classes (`address`, `hostname`, `domain`, `file`, `process`, `hash`, `registry`) plus a user kind from a card's actor/to/object field whose values recur and are not addresses — no value list, no extension/domain/process dictionary. |
| `portal/modules/security/core/hunt/notables/behaviours.py` | reads anchored to the source's own stored value spans when its lists exist (`anchor_windows`); `read_mode` (`whole\|anchored\|sampled`) recorded on every source receipt; the existing whole-read tier is reused, not changed. |
| `portal/modules/security/core/hunt/notables/run.py` | the behaviours stage writes `entities.duckdb` and `spine.json` beside the behaviour store and records the spine receipt. |
| `portal/modules/security/core/hunt/notables/__main__.py` | prints read-mode counts and the spine line. |
| `tests/unit/test_hunt_spine.py` (new), `tests/unit/test_hunt_notables_behaviours.py` | 4 acceptance tests (one per property). |

Episode rule: within `(entity, source, part)`, sort events and split where the gap exceeds
`min(4 h, max(5 min, 4 × median gap))`; a gap below 5 min never splits. Neighbours are the nearest
earlier and later episode of another source on the same host inside ±4 h (`prev_source`,
`next_source`, `delta`, and `episode_links` rows).

Run it on any stored run:

```bash
uv run python -m portal.modules.security.core.hunt.notables.spine --out <run dir> \
  --family <family> --keys <keys.jsonl> --logs <corpus>/<family>/gather
```

## 2. Acceptance properties and their proof

Command (per family; this is what produced the table):

```bash
uv run python -m portal.modules.security.core.hunt.notables.spine \
  --out coding_task/scratch/s2/<family> --family <family> \
  --keys /Volumes/data01/portal5_hunt/corpora/<...>/keys.jsonl \
  --logs /Volumes/data01/portal5_hunt/corpora/<...>/gather
```

Every run step is a graded label in the per-line keys. "read" = a labelled line of that step is in
the run's stored `events` table (the same evidence `C0` uses for `steps_reachable`). A line passes
when one of the entity values it carries has an episode whose `event_ids` contains that event.

| family | steps | steps with a read line | steps pass | labelled lines read | lines in an episode | lines with no entity |
|---|---|---|---|---|---|---|
| kyoushi | 12 | 11 | **11 / 11** | 5,628 | 5,628 | 0 |
| santos | 21 | 12 | **12 / 12** | 2,741 | 2,741 | 0 |
| russell | 22 | 15 | **15 / 15** | 2,602 | 2,602 | 0 |

Every step that did not pass is `unreached`, never a miss: kyoushi `reverse_shell` (its single
line, `bash: 196: Bad file descriptor`, was never read — matching the C0.2 ceiling 11/12), santos
9 steps, russell 7 steps. The per-step causes are in `spine_steps.json`.

Read receipt (property 3):

| family | whole | anchored | sampled |
|---|---|---|---|
| kyoushi | 16 | 0 | 13 |
| santos | 19 | 0 | 28 |
| russell | 31 | 0 | 26 |
| botsv2 | 20 | 0 | 67 |

Adjusted property 2 (links): on every built store, `episode_links` has no pair with
`abs(delta) > 4 h`, no pair whose endpoints share a source, and no dangling neighbour id
(kyoushi 62,181 links; santos 70,882; russell 131,651; botsv2 187,440). The 4 h boundary is also a
unit test.

## 3. C0.2 measures on the stored run (no regression)

Scoreboard over the same key files, before (`/Volumes/.../neon`) and after (scratch dirs with the
spine): the only diff is the new store name in the ceiling line.

```
botsv2    C0 ceiling keys 5/20 reachable  steps 5/14 (B+P 5/11)  stores {behaviour, events, misfit, spine}
kyoushi   C0 ceiling steps 11/12 reachable   recall-of-reachable line @50 11/11
santos    C0 ceiling steps 12/21 reachable   recall-of-reachable line @50 11/12
russell   C0 ceiling steps 15/22 reachable   recall-of-reachable line @50 14/15
```

`diff` of the two scoreboard captures: one line changed, and it is the addition of `'spine': 4` to
botsv2's store list. The spine can never raise reachability by construction: it is built from the
events already in the read store.

Cost (spine build alone, this machine, one process):

| family | stored events | entities | episodes | links | seconds |
|---|---|---|---|---|---|
| kyoushi | 140,200 | 6,410 | 34,433 | 62,181 | 60 |
| santos | 194,749 | 5,931 | 38,540 | 70,882 | 116 |
| russell | 174,437 | 5,525 | 68,618 | 131,651 | 125 |
| botsv2 | 259,900 | 11,949 | 106,848 | 187,440 | 131 |

Events a spine carries no entity for: kyoushi 4,611 (3.3 %), santos 4,537 (2.3 %), russell 1,066
(0.6 %), botsv2 61,075 (23 %). The build families' graded lines all carry one; the botsv2 share is
measurement-style lines whose fields are numbers.

## 4. Orchestrator proof

1. Live run (no code change): `RUN_HUNT_REDESIGN.sh` — the behaviours stage now writes
   `entities.duckdb` + `spine.json` per family and every source receipt carries `read_mode`.
   Pass: the printed `read_mode per source` line and a non-empty `spine:` line, and `entities.duckdb`
   in the run directory.
2. Offline S2 proof, per build family. Work on a copy so the snapshot stays read-only
   (`cp`, not symlinks — a symlink under `coding_task/` breaks
   `test_wiki_truth_claims.py::test_module_toggle_and_mcp_addition_leave_bs_pass_with_no_doc_edits`):

```bash
data=/Volumes/data01/portal5_hunt/corpora
snap=/Volumes/data01/portal5_hunt/snap_neon_02cc2e3/results/hunt/neon
run=coding_task/scratch/s2
hunt=portal.modules.security.core.hunt.notables

for f in kyoushi santos russell; do
  mkdir -p "$run/$f"
  cp "$snap/$f/behaviours.duckdb" "$snap/$f/sources.json" "$snap/$f/progress.json" "$run/$f/"
done

uv run python -m "$hunt".spine --out "$run/kyoushi" --family kyoushi \
  --keys "$data/hunt_bed/kyoushi_s1_ingest/keys.jsonl" \
  --logs "$data/hunt_bed/kyoushi_s1/gather"
uv run python -m "$hunt".spine --out "$run/santos" --family santos \
  --keys "$data/ait_lds_v21/santos_ingest/keys.jsonl" \
  --logs "$data/ait_lds_v21/santos/gather"
uv run python -m "$hunt".spine --out "$run/russell" --family russell \
  --keys "$data/ait_lds_v21/russellmitchell_ingest/keys.jsonl" \
  --logs "$data/ait_lds_v21/russellmitchell/gather"
```

   Pass: `steps=.. read=.. pass=..` with `pass == read` (unreached steps are listed, not failed),
   and `lines_without_entity=0` for every read step. Expected on this snapshot:
   kyoushi `steps=12 read=11 pass=11`, santos `steps=21 read=12 pass=12`,
   russell `steps=22 read=15 pass=15`.
3. C0.2: the scoreboard command in `RUN_HUNT_REDESIGN.sh`; pass is the numbers in §3 unchanged and
   the store list containing `spine`.

## 5. Unproven / limits

- **Anchored reads were not exercised on the stored run.** The snapshot predates S1 and has no
  `inventory.json`, so every stored source is `whole` or `sampled`. The anchored path is code plus a
  unit test (`anchor_windows` + `read_mode_of`) and needs a live behaviours run with lists to be
  seen end to end.
- **Read modes on the stored run are derived** from the old receipt's `selection` string
  (`read_mode_source: selection`). Fresh runs record `read_mode` directly.
- **The spine covers the `events` table** (keyed events), not every row the stage read. The
  behaviour receipts' `events_parsed` is larger than `events_keyed`; keyless lines are not in the
  spine. All three families' graded read lines are in it.
- **Entity precision** is structural but not perfect: a bare dotted token is hostname-vs-file
  ambiguous (`system.cpu.log` reads as a hostname; `Type.php` as a file). Card field names resolve
  it where they exist.
- **Cost**: the spine re-parses the store; on botsv2 that is 131 s on top of the behaviours stage.
  Feeding the spine from the already-parsed events would remove the second parse.
- **botsv2 5/20 keys** is the S0 baseline (5/14 steps), not the plan's older C0.1 8/24; S2 does not
  move it, as designed.
