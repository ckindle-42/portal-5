# HUNT S3 — flows, cases, promotion (lane `lane/hunt-s3`, 2026-11-20)

Slice S3 of `docs/hunt/ORCACYBER_HUNT_PLAN.md` §4, built on S2's spine and proven on the stored
run `snap_neon_02cc2e3` (copied to `coding_task/scratch/s3/`; the snapshot itself stayed
read-only). No live Splunk search was made, no held-out set (`hb_ait_wheeler`,
`hb_cloudobs_aws`, `botsv1`) was opened, `.env` was not sourced, no Splunk configuration was
changed.

## 1. What S3 added

| file | change |
|---|---|
| `notables/relate.py` | `CaseUnit` (episode \| signal \| flow) and a case builder over the spine: union-find on an entity key and on flow values, the two-evidence rule, the plan's five-term score, member ranking, promotion scoped to a case, and a case receipt. `cases.json` is written beside the run; `--cases` assembles it with no searches. `_identity_fields` now also records each card's full role plan; `promotion` receives `judged_only` and records `unjudged` per lifted id. |
| `notables/scoreboard.py` | reads `cases.json` (falling back to `relate.json`), and reports `case_quality` (evidence pieces and violations, `coverage_complete`, `uncapped_fraction`, censored counts, promotion shape), `case_member_recall` (B/P steps and the dataset-level scenario verdict), and a B/P filter for the entity-mode `case_recall`. The per-case printout is bounded to the head. |
| `tests/unit/test_hunt_relate.py`, `tests/unit/test_hunt_inventory.py` | replaced the old seed-pair case tests with four tests, one per acceptance property. |

Net test lines: **+111 / −332 = −221** (4 tests replace 8).

## 2. The rule implemented

- **Units.** Episodes come from `entities.duckdb` (S2). Signals are the run's notables plus any
  relate pivot rows, one unit per entity key a notable carries; their span is the evidence
  line's moment. Flows come from `inventory.json`; a flow is kept only when its endpoint role
  vectors differ and at least one endpoint role is a *deciding* one (`actor`/`from`/`to`).
- **Link.** Two units of one entity key chain when the next span is within 4 h of the previous
  (the spine's adjacency window) and the chain's span stays under 24 h. A flow unions the
  episodes at its own endpoint sources inside the same window. A gap beyond 4 h and a span
  beyond 24 h are counted as **censored**, never silently dropped.
- **Case.** Two independent pieces of evidence: two sources, two signals, or an episode plus a
  flow. One signal alone is a notable. A case also keeps at least one reproducible evidence row.
- **Score.** `sources + distinct generators + anchor strength + max within-source share +
  coherence` — the plan's §2.5 five terms, weights `(1,1,1,1,1)` (LOFO selection is the
  orchestrator's step 2, not this lane's). Anchor strength is the merged-rank strength of the
  highest-share member. Members are ranked within the case by their own measure.
- **Promotion.** Only a case already inside the head lifts its own weak members, to sit just
  after its anchor. With `judged_only` the planner drops every unjudged row and the builder
  never admits one, so a judged-only view cannot gain one.

## 3. Acceptance properties and their proof

Command (offline; 0.5–1.3 s per family, one process):

```bash
for f in kyoushi santos russell botsv2; do
  uv run python -m portal.modules.security.core.hunt.notables.relate \
    --out coding_task/scratch/s3/$f --cases
done
uv run python -m portal.modules.security.core.hunt.notables.scoreboard \
  --out coding_task/scratch/s3 --keys botsv2=$DATA/corpora/botsv2_keys/keys.jsonl \
  --keys kyoushi=$DATA/corpora/hunt_bed/kyoushi_s1_ingest/keys.jsonl \
  --keys santos=$DATA/corpora/ait_lds_v21/santos_ingest/keys.jsonl \
  --keys russell=$DATA/corpora/ait_lds_v21/russellmitchell_ingest/keys.jsonl
```

Case receipt per family (stored run):

| family | units | episodes | signals | flows | cases | links | censored gap / window | uncapped | coverage_complete | violations |
|---|---|---|---|---|---|---|---|---|---|---|
| kyoushi | 35,083 | 34,433 | 650 | 0 | 4,963 | 24,275 | 5,816 / 528 | 0.7928 | false | 0 |
| santos | 39,226 | 38,540 | 686 | 0 | 4,204 | 28,917 | 5,572 / 655 | 0.8228 | false | 0 |
| russell | 68,980 | 68,618 | 362 | 0 | 4,187 | 60,683 | 3,977 / 1,364 | 0.9191 | false | 0 |
| botsv2 | 107,218 | 106,848 | 370 | 0 | 4,509 | 60,785 | 35,686 / 691 | 0.6256 | false | 0 |

**Property 1 — ≥ 1 case in the top 50 per scenario that contains a B/P member.**
Per *scenario*: kyoushi, santos and russell each carry one attack scenario, and each has a case
in the top 50 whose evidence holds a labelled line of that scenario (`scenario covered yes`).
botsv2 does not: 1 of its 4 scenarios is covered at the top 50 (`case members top50 1/4`), which
matches its C0.2 ceiling of 5/20 reachable keys.

Per *graded step* (the stronger reading, reported for the reviewer):

| family | read steps | step in a top-50 case | step in any case | step in no case |
|---|---|---|---|---|
| kyoushi | 11 | 5 | 6 | `escalated_command`, `escalated_sudo_command`, `escalated_sudo_session` |
| santos | 12 | 3 | 7 | `attacker_vpn`, `escalate`, `escalated_command`, `escalated_sudo_command`, `escalated_sudo_session` |
| russell | 15 | 7 | 8 | `attacker_change_user`, `escalated_sudo_session` |

The steps in *no* case are a formation fact, not a scoring one: their carrier is a single-source
entity with no signal on it (kyoushi's `process:sudo` lives only in `auth.log`, while
`process:/usr/bin/sudo` lives only in `system.journal`, and no notable carries either), so the
two-evidence rule never admits them. The plan's case rule cannot reach a step whose carrier has
one source and no signal.

The top of the ranking is the attack: kyoushi case 0 anchors `172.16.100.151` over 11 sources;
santos case 0 `172.21.128.119` over 9; russell case 0 `172.19.131.174` over 10 — the same
carriers S2's spine table lists.

**Property 2 — every case has ≥ 2 pieces of evidence.** `case evidence pieces min 2 violations 0`
and `evidence_violations: 0` in every family's receipt (4,963 + 4,204 + 4,187 + 4,509 cases).

**Property 3 — `coverage_complete` reported and the uncapped fraction > 0.** Reported per family
above: `coverage_complete False` with the censored counts that make it false (the 4 h gap and the
24 h window), and `uncapped_fraction` 0.63–0.92. The inventory-list coverage is reported beside it
(`lists`), and is `null` on this snapshot because it predates S1 and holds no `inventory.json`.

**Property 4 — promotion cannot add an unjudged row to a judged-only view.** Unit test
`test_promotion_never_lifts_an_unjudged_row_into_a_judged_view`: with `judged_only=True` the
unjudged weak member is not lifted (`lifted == 0`, order unchanged); without it the same member
is lifted and the receipt records `unjudged: True`. The run receipt reports
`promotion judged_only … unjudged_lifted 0`; on this snapshot there is no judge, so the live shape
is `judged_only no`.

## 4. C0.2 on the same four runs (no regression)

```
botsv2    C0 ceiling keys 5/20 reachable  steps 5/14 (B+P 5/11)  stores {behaviour, events, misfit, spine}
kyoushi   C0 ceiling steps 11/12 reachable   line @50 11/11
santos    C0 ceiling steps 12/21 reachable   line @50 11/12
russell   C0 ceiling steps 15/22 reachable   line @50 14/15
```

Identical to S2's §3, which is the S0 baseline. The case builder is downstream of the read store
and cannot move reachability.

## 5. Orchestrator proof

1. **Offline (as above)** — `--cases` needs no Splunk. Pass: `cases=…` non-zero, `evidence_violations=0`,
   and the scoreboard's `case members … scenario covered yes` for each build family. Fail: a case
   count of 0, a violation above 0, or `scenario covered no` on a build family.
2. **Live** — `coding_task/RUN_HUNT_REDESIGN.sh` (images rebuilt since `portal/` moved). The relate
   stage now builds cases from the spine; pass is `relate: … cases=<n>` with `cases.json` in each
   family directory and the scoreboard lines of §3. With a judged run, add
   `--stage relate --judged-only` (or the product path's judged flag) and pass is
   `promotion judged_only yes  unjudged_lifted 0`.

## 6. Unproven / limits

- **The flow path is not exercised on this snapshot.** It has no `inventory.json`, so every
  family reports `flows 0`. Flow linking (role vectors, deciding endpoint) is code plus a unit
  test; a live run after S1's lists is the first place it will be seen end to end.
- **The case count is high** (4.2–5.0 k per family). The §2.5 rule is permissive: a busy benign
  entity with two sources is two independent pieces of evidence and admits a case. The head is
  where the product lives; a formation rule anchored on signals would shrink the count but
  departs from the specified rule.
- **Evidence is a bounded sample.** Each case keeps at most 20 evidence rows (round-robin across
  members), so `case_member_recall` and purity measure what the sample holds. A labelled line
  inside a case whose sample misses it reads as uncovered — the per-step table above is the
  measured floor, not the case's true content.
- **Cost.** `cases.json` is 41–72 MB per family on this snapshot (44.6 k evidence rows for
  kyoushi), written compact but still the largest text artefact a run produces. Build time is
  0.5–1.3 s.
- **Promotion/judged-only is unit-proven only.** The snapshot holds no judge result, so no live
  judged-only view exists to read.
- **`uv run mypy portal/` is not clean on this worktree** (653 errors in 72 files, 650 of them in
  `scripts/validation`, `tests/wfe`, `tests/uat_catalog`, `scripts`) — all pre-existing and outside
  the diff; the three errors my change did introduce were fixed, and the two touched portal files
  are clean under mypy.
