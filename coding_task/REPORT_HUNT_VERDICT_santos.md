# Hunt verdict — **santos**

**santos: falls short.**

Graded at `83f72271e` (`origin/main`, the `_v2` family-label scoreboard fix) against
`docs/hunt/ORCACYBER_HUNT_PLAN.md` §3–§4. Two stored runs were re-scored, and the two
missing offline acceptance checks were run against them:

- tuned index: `…/hunt_proof_20261120T232700/v2/santos` (`hb_ait_santos_v2`)
- original-index negative control: `…/hunt_proof_20261120T232700/control/santos` (`hb_ait_santos`)

No live Splunk search, no Pipeline/judge call, no `.env`, no `launch.sh`, no held-out set
(`hb_ait_wheeler`, `hb_cloudobs_aws`, `botsv1`) was opened. Everything below reads the stored
run files plus the labelled corpus at `/Volumes/data01/portal5_hunt/corpora/ait_lds_v21/santos/`.

## 1. Headline

| run | index | recall line @50 / @100 / all | ceiling reachable | of-reachable @50 / @100 / all | read fraction | cases | case members @50 |
|---|---|---|---|---|---|---|---|
| §3 baseline (`snap_neon_02cc2e3`) | `hb_ait_santos` | 18/21 / 18/21 / 20/21 | 12/21 | 11/12 / 11/12 / 12/12 | — | — | — |
| **control** (original index) | `hb_ait_santos` | 15/21 / 15/21 / 17/21 | 12/21 | **11/12** / 11/12 / 11/12 | 0.014434 | 3,467 | 3/21 |
| **`_v2`** (tuned index) | `hb_ait_santos_v2` | 16/21 / 17/21 / 18/21 | **11/21** | **8/11** / 9/11 / 10/11 | 0.057489 | 461 | 3/21 |

The stored baseline reproduces exactly (`18/21`, `12/21`, `11/12`). The tuned `_v2` run does
**not** hold the build-family bar: `recall-of-reachable @50` is `8/11 = 0.727` against the
§3 value `11/12 = 0.917`, and its reachability ceiling *fell* from `12/21` to `11/21` rather
than rising. The original-index control does hold it (`11/12`).

## 2. Slice acceptance

### S0 — truthful measurement (**partial**)

| acceptance | result | receipt |
|---|---|---|
| stored-run baseline reproduces exactly | **pass** | `snap_neon` rescore: `recall top50 18/21 top100 18/21 all 20/21`, `C0 ceiling steps 12/21 reachable`, `C0 recall-of-reachable line @50 11/12` |
| C0.2 fields present (case_recall, promotion_effect, marginal, ledger, unjudged) | **pass** | scoreboard prints `case members`, `relate recall before/after`, `generator marginal`, `C0 ceiling`; `ledger.jsonl` 785 / 1,994 rows; judge `unjudged` 9 / 81 |
| ledger distinguishes never-read from read-and-censored | **pass** | read rows carry `window_start`, `window_end`, `capped`, `reason`; reasons seen: `None`, `row_cap` (1 in `_v2`), `censored` (300 per run) |
| per-step cause (`covered \| instrument \| not_surfaced \| unreached \| censored`) | **fail** | line-mode output has no `C0 causes` block; every `ceiling.per_step[*].cause` is `""` in both runs (`cause_rule` only reached on the entity-key branch) |

### S1 — enumeration (**pass**)

Tier A is satisfied on both indexes and the indexed (Tier B) mechanism is proven on `_v2`:

| run | complete `src_ip` list | mechanism | name used | events scanned | seconds | status / values |
|---|---|---|---|---|---|---|
| control | `eve.json` `src_ip` (dns) | `stats` | `eve.json` | 1,129,009 | 3.587 | complete / 17 |
| control | `eve.json` `src_ip` (flow) | `stats` | `eve.json` | 1,129,009 | 4.652 | complete / 126 |
| `_v2` | `suricata` `src_ip` (dns) | **`tstats`** | `suricata` | 192,480 | **0.440** | complete / 17 |
| `_v2` | `suricata` `src_ip` (flow) | **`tstats`** | `suricata` | 334,566 | **0.442** | complete / 126 |
| `_v2` | `suricata` `src_ip` (alert) | **`tstats`** | `suricata` | 50,028 | **0.439** | complete / 1,285 |

- `first_seen_replaced` > 0 on at least one behaviour: `22` (`_v2`), `44` (control).
- `values` > 0, `status: complete`, `events_scanned` recorded, `probe_failures: []`.
- Inventory totals: `_v2` 1,495 values / 11 complete / 1 capped / 20 empty, `stats` 24 + `tstats` 8;
  control 1,479 values / 13 complete / 19 empty, `stats` 32.
- `unavailable` vs `empty` was **not exercised** on this family: no list reached status
  `unavailable`, so the name-mismatch regression is unit-proven only.

### S2 — entity spine and episodes (**pass on control, fail on `_v2`**)

Offline per-step verification (`spine.verify_steps`, stored events + keys + labelled corpus):

| run | steps read | steps pass | lines read | lines with an episode | lines without entity |
|---|---|---|---|---|---|
| control | 12 | **12 / 12** | 2,591 | 2,591 | 0 |
| `_v2` | 11 | **9 / 11** | 8,990 | 8,988 | 2 |

The two `_v2` failures are read steps with exactly one read line carrying no recognised
carrier entity (therefore no episode):

- `attacker_change_user`: 9 read, 8 with an episode; carriers `process:/bin/su`,
  `process:/lib/systemd/systemd`, `user:gmorgan`.
- `escalate`: 21 read, 20 with an episode; carriers `file:/var/www/intranet.smith.santos.com/wp-content/uploads/2022/01`,
  `process:/bin/su`, `process:/lib/systemd/systemd`, `process:/usr/bin/sudo`, `process:sudo`.

Spine receipts: `_v2` events 137,574 / entities 6,175 / episodes 19,296 / links 25,037 /
`fields_typed` 5; control events 182,083 / entities 5,686 / episodes 34,499 / links 62,928 /
`fields_typed` 31.

Link property passes on both: 0 links with `abs(delta) > 4 h`, 0 same-source pairs, 0 dangling
neighbours. Every source carries `read_mode` (`_v2` whole 5 / anchored 9; control whole 20 /
anchored 28).

### S3 — flows, cases, promotion (**pass on the stated acceptance**)

| acceptance | `_v2` | control |
|---|---|---|
| ≥ 1 case in the top 50 per scenario with a B/P member | `case members top50 3/21 … scenario covered yes` | `case members top50 3/21 top100 6/21 all 7/21 … scenario covered yes` |
| every case has ≥ 2 evidence pieces | `violations 0` | `violations 0` |
| `coverage_complete` reported, uncapped fraction > 0 | `False`, `0.586439` | `False`, `0.811193` |
| promotion never adds an unjudged row to a judged-only view | `promoted 12`, `promoted_unjudged 12`; offline judged-only drops them | same |

Cases: `_v2` 461, control 3,467. The flow signal is inert on both: `_v2` inventory flows 0;
control inventory flows 17 but `flows_skipped: 17` with `censored.flow_roles: 17`, so no case
carries a flow.

### S4 — estate detections (**pass for the santos part**)

- `_v2`: `alerts existed 76, kept 76`; control: `existed 47, kept 47`.
- Both alert sources report `events_without_entity: 0` (Suricata `eve.json` alert part and
  `fast.log`).
- The `_v2` `suricata:fast` card is skipped in the behaviour stage as `kind:alert` and is still
  consumed by the alerts generator — i.e. it is read as a detection stream.
- The named `botsv2` / `russell` acceptance was not re-run here (out of this family).

### S5 — weights by marginal contribution (**partial: instrument pass, run did not deliver**)

- Scoreboard marginal table for santos: `deviation` `marginal@50 9` (`@100 7`), `similar_to_known`
  `1`, `misfit`/`alerts`/`peer_rare`/`relate` `1`. A generator with candidates but nothing in the
  head (`relate`, 417 candidates, 0 kept) keeps a unit weight; `existed == 0` keeps unit weight.
- But the live run's merge is `weights_source: "default"` with
  `{deviation 26, misfit 6, similar_to_known 31, alerts 0, peer_rare 0}` — the old
  `DEFAULT_WEIGHTS`, not the measured marginal. `PORTAL_HUNT_MERGE_WEIGHTS` was not set for
  either run, so the plan's "every weight is a measured marginal" is not true of the run.
- A single-family `--weights` invocation cannot produce real LOFO folds; the fold row printed
  for `santos` is the fallback `DEFAULT_WEIGHTS`, so the fold table is not exercised here.

### S6 — localise-then-read (**pass on control, fail on `_v2`**)

| acceptance | `_v2` | control |
|---|---|---|
| no build-family regression: of-reachable @50 ≥ §3 `11/12` | **fail** `8/11` | pass `11/12` |
| read fraction reported per source | pass (`spine.sources[*].read_fraction`) | pass |
| every read carries `events_scanned` | pass (0 of 14 receipts missing) | pass (0 of 48 missing) |

Localisation receipts: `_v2` `windows 4`, `width 3600`, `mechanism "indexed"`, `coverage "scan"`,
`accel_window [1616425563.0, 1642485717.000001]`; control `windows 1`, `width 1441`,
`mechanism "indexed"`, `coverage "scan"`, `accel_window null`. Rung 1 (accelerated aggregate)
did **not** fire on either run (`accelerated: []`, `model_probes: 0`) — expected only after
Stage 3, so it is not exercised, not failed.

### S7 — judge over cases (**not exercised by the run; deterministic half passes offline**)

The live run's judge stage judged **notables**, not cases: `case_judge: null` in `cases.json`
and all cases unjudged (`unjudged cases` 97 `_v2` / 64 control; `promotion judged_only no`).

Running the missing offline case judge (`rerank --cases --case-budget 0`, on copies under
`coding_task/scratch/verdict-santos/s7/`):

| run | cases | verified | unverified | unverified members | judged-only cases / members / dropped | order moved | model requests |
|---|---|---|---|---|---|---|---|
| `_v2` | 461 | 425 | 36 | 977 | 441 / 1,858 / 977 | 0 | 0 |
| control | 3,467 | 3,444 | 23 | 809 | 3,462 / 18,791 / 809 | 0 | 0 |

Deterministic verification and judged-only exclusion work; `p_yes` ordering is unexercised
(0 model calls), so the plan's "one call per case, `p_yes` orders" cannot be graded from either
run.

## 3. Failing design layers

1. **S2 — spine (episode containment on the tuned index).** On `_v2`, 2 of 11 read steps
   (`attacker_change_user`, `escalate`) each have one read line with no carrier entity, so the
   plan's "every graded step's carrier entity has an episode containing its labelled line" is
   9/11, not 11/11. The control is 12/12. The `_v2` spine types far fewer fields
   (`fields_typed` 5 vs 31); the two failing lines carry no recognised entity at all.
2. **S6 — localisation/read (no build-family regression).** The tuned `_v2` run's
   `recall-of-reachable @50` is `8/11` against the §3 `11/12`; its reachability ceiling is
   `11/21` against the control's `12/21`. The tuned index is cheaper (785 searches / 1,208 s vs
   1,994 / 1,595 s; `tstats` lists 0.44 s vs 3.6–4.7 s) and reads a larger fraction (5.75 % vs
   1.44 %), but it did not hold the recall-of-reachable bar and did not raise the ceiling.
3. **S0 — measurement gap.** Line-mode families do not report a per-step cause; every
   `per_step[*].cause` is empty and the `C0 causes` block is absent. The plan requires the cause
   classification per family.
4. **S5 — weights not delivered.** The run merged on `DEFAULT_WEIGHTS` (`weights_source:
   "default"`), not the measured marginal the scoreboard reports.

## 4. Not exercised

- S1 Tier B on `botsv2` / `winregistry` (the plan's named wide-source proof) — this family only.
- S6 rung 1 (accelerated aggregate) and the `botsv2` `12/24` / `10/14` ceiling — no accelerated
  model in this index.
- S7 model ordering of cases — the run never called the case judge.
- S1 `unavailable` vs `empty` — no unavailable list arose on santos.

## 5. Reproduce

```bash
cd /Users/chris/projects/portal-5-hunt-verdict-santos
run=/Users/chris/projects/portal-5-hunt-proof-run/coding_task/scratch/hunt_proof_20261120T232700
keys=/Volumes/data01/portal5_hunt/corpora/ait_lds_v21/santos_ingest/keys.jsonl
logs=/Volumes/data01/portal5_hunt/corpora/ait_lds_v21/santos/gather

uv run python -m portal.modules.security.core.hunt.notables.scoreboard \
  --out "$run/v2/santos" --keys "santos=$keys"
uv run python -m portal.modules.security.core.hunt.notables.scoreboard \
  --out "$run/control/santos" --keys "santos=$keys"
# baseline:
uv run python -m portal.modules.security.core.hunt.notables.scoreboard \
  --out /Volumes/data01/portal5_hunt/snap_neon_02cc2e3/results/hunt/neon/santos \
  --keys "santos=$keys"

# S2 per-step (read-only; does not rebuild the spine):
uv run python coding_task/scratch/verdict-santos/verify_spine.py

# S7 deterministic case verification on copies (writes only under scratch):
uv run python -m portal.modules.security.core.hunt.notables.rerank \
  --run v2=coding_task/scratch/verdict-santos/s7/v2 \
  --run control=coding_task/scratch/verdict-santos/s7/control \
  --cases --case-budget 0 --json
```

Scratch outputs: `coding_task/scratch/verdict-santos/*.score/rescore/weights/json`,
`verify_spine.py`, `verify_spine2.py`, `s7-casejudge.json`.
