# HUNT S7 — judge over cases (lane `lane/hunt-s7`, 2026-11-20)

Slice S7 of `docs/hunt/ORCACYBER_HUNT_PLAN.md` §4, judging S3's cases. Proven on the stored run
`snap_neon_02cc2e3` (copied to `coding_task/scratch/s7/`, the snapshot stayed read-only): the
spine was rebuilt per S2 and the cases per S3, and the counts reproduce S3 exactly. No live Splunk
search, no held-out set (`hb_ait_wheeler`, `hb_cloudobs_aws`, `botsv1`), no `.env`, no Splunk
configuration change.

## 1. What S7 added

| file | change |
|---|---|
| `notables/judge_notables.py` | Deterministic case verification first (`CaseFacts` from the run's own `behaviours.duckdb`/`entities.duckdb`; `verify_case`), then one cached model call per **case** with a bounded timeline (`case_prompt`, `judge_cases`). `_rate_budget` is the one rate-measured budget shared by the notable and case judges. |
| `notables/rerank.py` | `case_order` (p_yes orders the head only, unjudged sinks, nothing is dropped), `judged_only_cases` (a view without unjudged members), and `judge_case_runs` plus `--cases`/`--case-budget`/`--case-deadline` on the existing rerank CLI. Writes the judged cases back to `cases.json`, or to `relate.json` when that is the run's case payload. |
| `tests/unit/test_hunt_notables_judge.py`, `tests/unit/test_hunt_rerank.py` | one test per acceptance property. |

Net test lines: **+123 / −0** (3 tests; the existing notable-prompt test is kept).

The model is a Portal seat from env (`PORTAL_HUNT_JUDGE_URL`, `PORTAL_HUNT_JUDGE_MODEL`, key via
`PORTAL_HUNT_JUDGE_KEY_ENV`), the same contract `__main__` and `jobs.py` use; no model name or
endpoint is in code. The lane made **zero** model calls (§5 is the orchestrator's command).

## 2. The rule implemented

- **Deterministic verification first, against the run's own store.** Every case member is checked
  before any model call: an episode anchor must exist in the spine, at least one of its
  `event_ids` must resolve in the stored `events` table, and the member's value must appear in one
  of those resolved raw rows (`value_in_raw`); a signal member's `notable_id` must exist and one of
  its evidence lines must resolve to a stored row holding the value (`notable_line`); a flow member
  must be held by a stored row on each endpoint source. A failure marks the **member**
  `unverified: true` with a `verify_reason`, and an unverified **anchor** marks the **case**
  `verification: "unverified"`. Unverified cases are not sent to the model — a deterministic check
  that fails is not a model question.
- **One call per case.** The prompt carries the anchor, window, up to six evidence rows, up to 20
  linked members and up to 30 timeline rows inside the same 6,000-char seat budget as a notable;
  the cache is keyed by `case_id` (`cache/judge_cases.json`, `CASE_CACHE_VERSION`).
- **`p_yes` only orders.** `case_order` sorts the first 50 cases by `p_yes` descending; the tail
  keeps the S3 five-term order. The case list is never filtered: a low `p_yes` sinks within the
  head, an unjudged case sinks to the bottom of the head, and every case keeps its `case_id`,
  `score` and members.
- **`unjudged` never rejects.** A case with no model answer keeps `p_yes: null`,
  `judge.reason: case_budget_exhausted | unverified_anchor | <transport reason>`, and stays in the
  file. `judged_only_cases` is the explicit judged view: it drops only members carrying
  `unjudged: true`; a case whose only members were unjudged drops out of *that view*, not the run.

## 3. Acceptance properties and their proof

Command (offline, no model, ~4 s for four families):

```bash
uv run python -m portal.modules.security.core.hunt.notables.rerank \
  --run kyoushi=coding_task/scratch/s7/kyoushi --run santos=coding_task/scratch/s7/santos \
  --run russell=coding_task/scratch/s7/russell --run botsv2=coding_task/scratch/s7/botsv2 \
  --cases --case-budget 0
```

Receipt (`cases.json` `receipt.case_judge`) on the stored run:

| family | cases | verified | unverified | unverified members | judged | unjudged | judged-only cases | judged-only members | dropped members | order moved | model requests |
|---|---|---|---|---|---|---|---|---|---|---|---|
| kyoushi | 4963 | 4961 | 2 | 10 | 0 | 4963 | 4962 | 25157 | 197 | 0 | 0 |
| santos | 4204 | 4204 | 0 | 3 | 0 | 4204 | 4202 | 23150 | 276 | 0 | 0 |
| russell | 4187 | 4179 | 8 | 174 | 0 | 4187 | 4186 | 55696 | 341 | 0 | 0 |
| botsv2 | 4509 | 4509 | 0 | 2 | 0 | 4509 | 4508 | 46131 | 124 | 0 | 0 |

**Property 1 — a case with an unverified anchor is reported `unverified`.** Ten real anchors fail
the deterministic check, all in the tail, none in the top 50:

| family | case | reason | anchor |
|---|---|---|---|
| kyoushi | `83430844b4c72d45` | `evidence_not_resolved` | signal `151.101.193.105` |
| kyoushi | `c71740e964b7c81b` | `evidence_not_resolved` | signal `151.101.194.110` |
| russell | `8270b2bc3b9a70c1`, `e3b0aa3f789a9284` | `evidence_not_resolved` | signal services |
| russell | `8a372efc…`, `4c249d41…`, `a0cf29d7…`, `f46a6c18…`, `d73acfa4…` | `value_absent` | episode `systemd-fsck@dev-disk-by\x2dlabel-UEFI.service` |
| russell | `9d88d79c1f74b1b6` | `value_absent` | episode `dev-disk-by\x2dlabel-UEFI.service` |

The `value_absent` family is a real representation gap, not a scoring miss: the parsed entity value
carries one `\` while the raw JSON row carries the escaped `\\x2d`, so the value string is not in
the returned row. Under the plan's rule that member is unverified. The case still exists; it is
simply not put to the model. Verified count plus unverified count equals the case count on every
family (`4961 + 2 = 4963`, `4179 + 8 = 4187`, …).

**Property 2 — judged-only views exclude unjudged members.** `judged_only_cases` on the same
payload returns 25,157 / 23,150 / 55,696 / 46,131 members and zero members with `unjudged: true`.
The dropped counts (197 / 276 / 341 / 124) are exactly the signal members whose `p_yes` is null on
this unjudged snapshot; episode evidence (all deterministic) stays. The unit test also proves a
mixed case keeps its judged members and excludes the unjudged one without mutating the source list.

**Property 3 — no case is dropped by model answer.** The four case counts after judging equal S3's
counts exactly (4,963 / 4,204 / 4,187 / 4,509), and ranks are `0..n-1`. The unit test drives a
three-case run with a yes answer, a **no** answer and a transport failure: all three `case_id`s are
still present, the `no` case keeps its place in `case_order`, and the failed case is `p_yes: null`,
not removed. On the stored run every case is unjudged (budget 0) and `order_moved 0` — the no-answer
path also drops nothing.

## 4. Gate

```
uv run pytest tests/unit/ -q              3028 passed, 22 skipped
uv run ruff check .                       All checks passed!
uv run ruff format --check .              1737 files already formatted
uv run mypy portal/                       650 pre-existing errors in 70 files, none in the changed files
python3 scripts/complexity_report.py --gate   GATE OK (god_lines 68,007 <= 71,202)
```

## 5. Orchestrator live proof

The one thing this lane cannot do is ask the seat. After a live run (or against
`coding_task/scratch/s7`, which is this snapshot rebuilt), with the Pipeline serving the judge
workspace:

```bash
export PORTAL_HUNT_JUDGE_URL=http://localhost:9099
export PORTAL_HUNT_JUDGE_MODEL=<the seated workspace id>
export PORTAL_HUNT_JUDGE_KEY_ENV=PIPELINE_API_KEY
run=coding_task/scratch/s7
uv run python -m portal.modules.security.core.hunt.notables.rerank \
  --run kyoushi=$run/kyoushi --run santos=$run/santos \
  --run russell=$run/russell --run botsv2=$run/botsv2 \
  --cases --case-budget 50 --case-deadline 720 --json
```

Pass: `judged == 50` per family (or the cached count on a rerun), `requests > 0`, the case count
unchanged, `unverified` equal to the deterministic table above, `judged_only` dropping only
unjudged signal members, and `order.moved` non-zero only if the seat's p_yes disagrees with the S3
score order. Fail: a case count below S3's, `unverified` above ten without a `verify_reason`, or
`requests == 0` with a live URL. The written `cases.json` carries per-case `p_yes`, `judge`,
`verified`/`verification` and per-member `unverified`/`verify_reason`.

## 6. Unproven / limits

- **No live model answer exists in this lane.** Every `judged` figure above is 0 by design
  (`--case-budget 0`). The answered path (yes, no, transport failure, cache hit) is unit-proven;
  whether the seat's p_yes is useful is the orchestrator's live run, and the S3 bias note (yes-always
  on notables) makes a flat ordering a plausible outcome, not a bug.
- **The live run had no judge cache** (`snap_neon_02cc2e3/cache/` does not exist), so cache hits
  are unit-proven only.
- **Prompt truncation.** A case with >20 members and >30 timeline rows truncates at 6,000 chars;
  the timeline is chronological, so the latest rows of a large case are the ones lost. The evidence
  rows are placed before the timeline so they always survive.
- **Signal verification is line-prefix based.** A notable evidence line that is a truncated raw
  row (`EVIDENCE_CHARS`) still matches by prefix; a line re-formatted after the read would not.
- **Cost.** Verification loads the run's event table once (~140 k rows kyoushi, ~260 k botsv2) and
  runs in 1–2 s per family; 4,963 cases at the seat's measured rate is thousands of calls, which is
  why `--case-budget` (default: deadline-derived) and the head-first order matter.
- **The product's `judge` stage is unchanged.** The entry point is `rerank --cases`; a full live
  hunt that wants cases judged must run it after `relate`.
