# Hunt live acceptance runbook — 2026-11-28

**Status:** prepared, not executed. Every live run, verdict and merge is the orchestrator's; this
document is the command reference it executes. No live hunts, no tuning, no Splunk writes from me.

## What acceptance means

Three steps, in order:

1. **Families no-regression** — leave-one-family-out runs on kyoushi, santos, russell; each family's
   stored run is held out of the knowledge store and the run must not fall below its stored baseline.
2. **botsv2 leave-one-family-out** — botsv2 is the untuned control; kyoushi/santos/russell are held
   out of its knowledge store. The product defects D1 (stage clock) and D3 (sort-before-head) must
   not regress; `alerts existed > 0` must hold.
3. **Held-out botsv1 proof** — final code run once against `botsv1` (and, at the plan's very end,
   `hb_ait_wheeler` / `hb_cloudobs_aws`), `--allow-proof`, scored and reported as-is; nothing after
   it may change a constant.

The pass bars, baseline numbers and receipts come from
`coding_task/FINDING_HUNT_BOTSV2_ROOT.md` (§9 stored `_v2` rescored baselines, §10 live proof) and
`docs/hunt/SCOREBOARD.md` (pass bar). botsv2's own root-finding diagnosis is in
`coding_task/FINDING_HUNT_BOTSV2_ROOT.md`; its loss/carrier table is `docs/hunt/BOTSV2_DIAGNOSIS.md`.

No code path may tune on botsv1 or any `PROOF_INDEXES` member — see the guard citation in §5.

## Environment (set once, before any step)

Run from the repo root. `PIPELINE_API_KEY` is exported **by name** from `.env` — never `source .env`.
The helper is `scripts/lib/host_dotenv.sh` (`portal_export_dotenv_keys`).

```bash
cd /Users/chris/projects/portal-5-hunt-accept-prep
if [[ -z "${PIPELINE_API_KEY:-}" ]]; then
  source scripts/lib/host_dotenv.sh
  portal_export_dotenv_keys "$PWD/.env" PIPELINE_API_KEY
fi
: "${PIPELINE_API_KEY:?Set PIPELINE_API_KEY in the environment or .env}"

export PORTAL_HUNT_JUDGE_URL=http://localhost:9099
export PORTAL_HUNT_JUDGE_MODEL=hunt-reasoning
export PORTAL_HUNT_JUDGE_KEY_ENV=PIPELINE_API_KEY
export PORTAL_HUNT_EMBEDDING_URL=http://localhost:9099
export PORTAL_HUNT_EMBEDDING_MODEL=google/embeddinggemma-2
export PORTAL_HUNT_EMBEDDING_KEY_ENV=PIPELINE_API_KEY

hunt=portal.modules.security.core.hunt.notables
data=/Volumes/data01/portal5_hunt
store=$data/knowledge/knowledge_v2_20261116.duckdb   # persisted labelled-behaviour store (build split only)
out=$(mktemp -d "$PWD/coding_task/scratch/hunt-live-accept.XXXXXXXX")
echo "Run directory: $out"

keys=(
  --keys "botsv2=$data/corpora/botsv2_keys/keys.jsonl"
  --keys "kyoushi=$data/corpora/hunt_bed/kyoushi_s1_ingest/keys.jsonl"
  --keys "santos=$data/corpora/ait_lds_v21/santos_ingest/keys.jsonl"
  --keys "russell=$data/corpora/ait_lds_v21/russellmitchell_ingest/keys.jsonl"
)
```

The modules entry point is `python -m portal.modules.security.core.hunt.notables`
(`notables/__main__.py`); its CLI accepts `--index`, `--out`, `--stage`, `--family`,
`--knowledge-store`, `--knowledge-families`, `--generators`, `--allow-proof`.

## Preflight (read-only, run before step 1; re-check index presence before steps 2–3)

| # | Check | Command | Expected |
|---|-------|---------|----------|
| P1 | Review service health (:8943) | `curl -s http://localhost:8943/health` | `{"status": "ok", "service": "review-mcp", ...}` (HTTP 200) |
| P2 | Lab Splunk reachability | `curl -sk -u "$LAB_SPLUNK_USER:$LAB_SPLUNK_PASSWORD" "$LAB_SPLUNK_URL/services/server/info" \| head -c 200` | JSON, `version` starts `10.2` |
| P3 | Index presence | `` \| tstats count where index=* by index `` (via Splunk REST) | `botsv2`, `hb_kyoushi_s1[_v2]`, `hb_ait_santos[_v2]`, `hb_ait_russellmitchell[_v2]` all present |
| P4 | Image freshness vs HEAD | `docker images | grep portal5` vs `git log --oneline -1` | Every portal image built at/after HEAD; else `./launch.sh rebuild` |
| P5 | Required inputs exist | `ls "$store" "$data/corpora/botsv2_keys/keys.jsonl" ...` | All four keys files + the store present |

- P1 uses the review-mcp `:8943` HTTP surface (`/health` and `/ready` both return `{"status": "ok"}`). The CLI hunt path judges through the Pipeline (`PORTAL_HUNT_JUDGE_URL=http://localhost:9099`), not :8943; :8943 is the R2 product hunt service (`hunt_sources`/`hunt_start`/`hunt_status`/`hunt_leads`/`hunt_case`) and is checked because the brief names it.
- P3 decides the step-1 index form: acceptance runs on the tuned `<index>_v2` indexes (finding §10, `SPLUNK_SETUP_RUNBOOK.md` §7). If a `_v2` index is absent, setup stages 1–3 of `docs/hunt/SPLUNK_SETUP_RUNBOOK.md` must land first — the step is **blocked until then**, not run on the untuned original as if the bar still applied.
- P4: `./launch.sh rebuild` (then `./launch.sh up`) only via `launch.sh` — never bare `docker compose`; the image must post-date HEAD before any live run.

## Step 1 — Families no-regression (leave-one-family-out)

Each family runs `--stage all` on its own index with the other two families held out of the
knowledge store (`--knowledge-families`). Store = build split only; no proof index may enter it
(§5 guard).

**kyoushi** (~12 min):
```bash
uv run python -m "$hunt" --index hb_kyoushi_s1_v2 --out "$out/kyoushi" --stage all \
  --family kyoushi --knowledge-store "$store" --knowledge-families santos,russell \
  2>&1 | tee "$out/kyoushi.run.log"
```
**santos** (~17 min):
```bash
uv run python -m "$hunt" --index hb_ait_santos_v2 --out "$out/santos" --stage all \
  --family santos --knowledge-store "$store" --knowledge-families kyoushi,russell \
  2>&1 | tee "$out/santos.run.log"
```
**russell** (~15 min):
```bash
uv run python -m "$hunt" --index hb_ait_russellmitchell_v2 --out "$out/russell" --stage all \
  --family russell --knowledge-store "$store" --knowledge-families kyoushi,santos \
  2>&1 | tee "$out/russell.run.log"
```

Then score all three against their keys:
```bash
uv run python -m "$hunt.scoreboard" --out "$out" "${keys[@]}" \
  | tee "$out/score.log"
```

**Pass criterion (no-regression vs stored `_v2` baselines, rescored):**
Compare each family's step recall at @50 and its `alerts existed` count against
`coding_task/FINDING_HUNT_BOTSV2_ROOT.md` §9:

| family | recall-of-reachable @50 | recall @50 | alerts existed | censored behaviours reads |
|---|---|---|---|---|
| kyoushi | 10/11 | 11/12 | 27 | 0 |
| santos | 10/13 | 14/21 | 46 | 0 |
| russell | 11/15 | 13/22 | 22 | 0 |

Rule: no family may score **lower** than its stored baseline; equal-or-better passes. `alerts existed`
is the D1-sensitive number — 0 there means the notables stage was clock-starved again (a D1
regression). The plan's original-index bar (kyoushi 11/11, santos 14/15, russell 11/12) is what
`coding_task/RUN_HUNT_REDESIGN.sh` measures against the untuned originals; it is not the acceptance
bar while the `_v2` indexes exist.

`docs/hunt/SCOREBOARD.md` defines the modes (entity strict/loose, line mode, deduped, B/P/T) and the
proposed pass bar; the operator picks the bar per family kind. All modes print on every score.

**Receipts to read:** `<out>/<family>/progress.json`, `ledger.jsonl` (per-source `events_read`,
`censored` reasons), `notables.jsonl`, `sources.json` (cards), `$out/score.log`.

**Failure handling:** a family below baseline is a no-regression failure — report the per-step diff
(`--baseline` against the prior scored run) and stop; do not tune weights to recover.

## Step 2 — botsv2 leave-one-family-out

botsv2 is the untuned control; all three families are held out of its knowledge store.
`--stage all` runs cards, behaviours, notables, relate, judge on one 720 s job clock.

```bash
uv run python -m "$hunt" --index botsv2 --out "$out/botsv2" --stage all \
  --family botsv2 --knowledge-store "$store" --knowledge-families kyoushi,santos,russell \
  2>&1 | tee "$out/botsv2.run.log"
```
**Expected duration:** ~29 min plus the notables reads (finding §10).

Score it:
```bash
uv run python -m "$hunt.scoreboard" --out "$out/botsv2" "${keys[@]:0:1}" \
  --keys "botsv2=$data/corpora/botsv2_keys/keys.jsonl" \
  | tee "$out/botsv2/score.log"
```

**Pass criteria (all must hold; from finding §10):**
- `stages.notables.clock.remaining_s` in `progress.json` equals the job seconds (`720.0`) — the
  notables stage began with a live clock (D1 fixed: it calls `executor_for(search).budget.restart_clock()`
  like relate/behaviours already do).
- `stages.notables.alerts.existed > 0` (pass-bar item 4).
- No `job_deadline_exceeded` note anywhere in the notables receipt, no notables ledger row with that
  reason, and `deviation.series` carries no `error`.
- The behaviours ledger holds **no read containing** `| sort - _time |` (D3 fixed: per-file reads
  issue `… | head N`, never a leading `sort`).
- `wineventlog:security`, `winregistry`, `mysql:transaction:details` each have `events_read > 0`
  (the three widest carriers were read as 0 rows before the D3 fix).
- Coverage item 2 (reachability ceiling on botsv2) stays **BLOCKED, not failed**, until the setup
  steps of `docs/hunt/SPLUNK_SETUP_RUNBOOK.md` §6 land; a ceiling that does not rise is a read-policy
  finding, not a reason to raise the budget.

botsv2's stored baseline (HEAD scoreboard): keys 8/20, steps 8/14 (B+P 6/11), loose 0/14 @50,
strict 0, cases 0/4, `alerts existed` 0. D1 alone moved `alerts existed` from 0 to >0; recall still
needs Splunk. The ceiling (8/20 keys reachable on this untuned index) is setup, not product — the
plan's own bar says so (`docs/hunt/ORCACYBER_HUNT_PLAN.md` Step 3 item 2).

**Receipts to read:** `$out/botsv2/progress.json` (notables clock + alerts), `ledger.jsonl`
(read reasons), `notables.jsonl`, `$out/botsv2/score.log`.

**Failure handling:** `alerts existed == 0`, a `job_deadline_exceeded` notables row, or a
`| sort - _time |` ledger read = D1/D3 regression → report and stop. Anything else on botsv2 is
bounded by the untuned ceiling; report the ceiling, do not raise the budget.

## Step 3 — Held-out botsv1 proof (plan Step 4)

Run once, at the very end, after steps 1–3 are green and every constant is frozen. Any change made
after seeing the numbers voids the proof.

Sanctioned blind harness (no knowledge store, no `similar_to_known`, no Stage 4 verdicts —
`validate_blind_mode` refuses all three):
```bash
uv run python -m scripts.hunt_bed.prove_universal_blind --index botsv1 --out-dir "$out/proof-botsv1"
```
Equivalent direct CLI form (cards → behaviours → notables → relate with `--allow-proof`; judge
requires the `PORTAL_HUNT_JUDGE_*` env above):
```bash
uv run python -m "$hunt" --index botsv1 --out "$out/botsv1" --stage all --allow-proof
```

**Pass criterion:** the run completes and is **scored and reported as-is**. botsv1 has no published
answer key (BOTS v1/v3 answers are sent on request; see `docs/review_decisions/D-T11-ANSWER-KEY.md`),
so there is no recall bar — report the run receipts and the read ledger, and state which numbers are
on held-out proof data (none of it may have entered the knowledge store or been seen during
development).

`PROOF_INDEXES` stays in the code path; the run script may name the index, the code must still
refuse it outside this sanctioned end step (§5).

## §5 Guard — no code path tunes on botsv1 / PROOF_INDEXES

`botsv1` is a member of `PROOF_INDEXES` (`portal/modules/security/core/hunt/notables/knowledge.py`,
lines 27–45). Every entry point enforces it:

- `knowledge.py:119–120` — `KnowledgeItem.validate()` raises `KnowledgeError` when a knowledge item's
  `index` is in `PROOF_INDEXES`: a proof index can never enter the knowledge store.
- `stage2.py:400` — relate restricts itself to `TRAINING_INDEXES` and raises on any
  `PROOF_INDEXES` member.
- `relate.py:671` — relate raises on a proof index unless `--allow-proof` is passed.
- `spine.py:929` — `verify_steps()` raises `ValueError` for a proof-index family.
- `scoreboard.py:484` and `scoreboard.py:1338` — `ScoreboardError("… is a proof index; it is never
  scored here")` unless `--allow-proof`; entity keys citing a proof-index dataset are likewise
  rejected (line 1342).
- `scripts/hunt_bed/prove_universal_blind.py` — `validate_blind_mode()` refuses `knowledge_store`,
  `similar_to_known`, `PORTAL_HUNT_KNOWLEDGE_STORE`, `PORTAL_HUNT_KNOWLEDGE_FAMILIES` and
  `PORTAL_HUNT_STAGE4_VERDICTS`; `resolve_key_path()` only accepts proof-index names.

Confirmed by reading code: no code path writes botsv1 (or any proof index) into a knowledge store,
merges its weights into a training-family run, or scores it outside `--allow-proof`. The hunt's
knowledge store is build-split only (`knowledge.py:116` rejects any split != `build`).

## D1 / D3 status (setup-failure fixes, already in HEAD)

Both product defects from the botsv2 root finding are fixed and tested on this branch
(`9d5ce6386` is an ancestor of HEAD):

- **D1 — notables stage starts its own clock in `--stage all`**: `notables/__main__.py:416`
  calls `executor_for(search).budget.restart_clock()` before `notables_stage`, as relate
  (`relate.py:1582`) and behaviours (`run.py:562`) already do. Test:
  `tests/unit/test_hunt_bounded.py::test_a_notables_run_after_an_expired_stage_starts_its_own_clock`.
- **D3 — per-file reads stream, no leading sort**: `notables/sample.py` `read_files` and
  `read_card_sample` issue `… | head N` (no `sort - _time`); docstrings state why. Test:
  `tests/unit/test_hunt_bounded.py::test_per_file_reads_stream_the_newest_rows_without_a_leading_sort`.

Both tests pass in `uv run pytest tests/unit/ -q`. No further setup-fix is required: the CLI
invocation matches the stage signatures (`notables_stage`, `relate_stage`, `judge_stage`),
`--allow-proof` is wired to the relate stage, and `scripts/lib/host_dotenv.sh` provides
`portal_export_dotenv_keys`. The one documented deviation — `coding_task/RUN_HUNT_REDESIGN.sh` names
the untuned originals while the stored baselines are on the `_v2` indexes — is not a step failure
(it runs); preflight P3 decides which index form is valid, and §1/§2 above point `--index` at
`<index>_v2` once setup stages 1–3 have landed.

## What "done" looks like for the orchestrator

- Step 1: all three families at or above their §9 baseline; score log shows no regressing family.
- Step 2: botsv2 notables receipt shows a live clock, `alerts.existed > 0`, no
  `job_deadline_exceeded`, no `| sort - _time |` reads, three wide carriers reading rows.
- Step 3: botsv1 proof run completes, reported as-is, no knowledge-store writes.
- Gate green: `uv run pytest tests/unit/ -q && uv run ruff check . && uv run ruff format --check . && uv run mypy portal/`.

If any preflight check (P1–P5) fails, stop and report exactly what is missing (review service,
lab Splunk, `_v2` indexes, stale images, or the env key) — that is an operator/setup decision, not
a code change.
