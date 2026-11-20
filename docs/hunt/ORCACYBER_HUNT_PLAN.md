# OrcaCyber hunt plan — partial rebuild

Companion to `ORCACYBER_CODE_REVIEW.md` (the evidence and file:line citations live there). Written
so a capable coding model with no hunting background can implement it slice by slice. Every
constant named here is an effort budget unless a slice says it is LOFO-selected; nothing is fitted
to a corpus.

---

## 1. Verdict

**Partial rebuild.** Not "keep and fix" — the coverage model and the unit of evidence are wrong —
and not "start over": the estate map, the parser, the executor's budget/coverage discipline, the
misfit shape miner and the C0 instrument are good and expensive to rebuild.

What is wrong, in one paragraph each:

- **The read model is a census, not a search.** Every source gets the same slice
  (`400k / sources / 12`, newest events per equal window), so the estate is never asked where the
  rare thing is. On botsv2 the run read 0.118 % of 226.3M events; in my live probe 8 of 24 graded
  keys were in anything it read (5 of 24 on the pre-F stored run). A 12-event artefact is seen
  1.4 % of the time by construction. Meanwhile the families it can nearly read whole score
  **11/11, 14/15, 11/12 of their reachable steps** — the ranker is not the loss.
- **The unit of evidence is a vocabulary item.** `(source, actor, action, object)` aggregated
  over a read has no sequence, no objects list, no transition, and cannot key a singleton. A
  hunter's unit is an episode: one entity, ordered events, a bounded window.
- **Value enumeration does not work.** C1 asks `tstats` to aggregate card role fields, which are
  search-time extractions; on botsv2 it returned 0 values, 0 joints, 0 flows and replaced 0
  first-seen values. C2's flow half therefore has no input; its case/promotion half works but is
  applied after the judge in production and injects unjudged raw lines.
- **The measurement now shows the real problem.** With the C0 reachability ceiling, the build
  families are at 91–100 % of what they read. The work is coverage and case construction, not
  re-weighting the same five ranks.

The rebuild keeps the spine of the repo and replaces four things: **how the estate is localised
before reading, what an episode is, how a case is assembled and ranked, and how the estate's own
detections are ingested.** Everything else is repaired.

### Why not "start over"

Cards already answer "what is in this estate and what can each source be asked" from structure
alone; `parse.py` already splits JSON/KV/CSV/template and mines templates; the executor already
enforces one budget, one deadline and declares censored coverage on every read; `misfit.py` already
learns shape without a dictionary; the scoreboard already has an honest ceiling. A rewrite would
re-earn all of that. The missing parts are design, not code volume.

### Why not "keep and fix"

Because the two properties the tool is sold on — *a needle only has to be a value in a list* and
*the case is the product* — are both inert today (0 values; cases unmeasured and, in production,
unjudged). Patching thresholds would not create either property.

---

## 2. Target architecture

```
estate map → localise (value lists + entity spine) → episodes → signals → cases → rank → judge
             ^                                ^
             |                                └── estate detections (alerts) as a signal
             └── read ledger (what was actually read, per query/window)
```

### 2.1 Stage 0 — Estate map (keep, extend)

Keep `index_facts`: per sourcetype, events, first/last, hosts, indexed sources, shared source
names, cadence. Add two things:

- **Evidentiary roles, structurally.** For each source, derive from the card and the parse what it
  can *decide*: `has_actor`, `has_host`, `has_process` (parent/child or image/cmdline),
  `has_file` (path/name), `has_transfer` (bytes + src/dst, or mail attachment), `has_auth`
  (user + outcome/logon type), `has_registry` (path/key), `has_detection` (alert event shape).
  These are booleans from field names/types and parse structure — no source names, no values.
  A source's role vector is what the flow signal and the read budget use instead of its size.
- **A ladder of cadence widths** (5 m, 1 h, 4 h, 24 h) over one `tstats … _time span=` grid, so a
  20-minute campaign is visible without guessing the bucket. Report per source which width best
  separates it from its own baseline.

Acceptance: every source in the map has a role vector; every width's query is one aggregation;
the receipt says rows/seconds per width. No behaviour change: nothing is ranked from this stage.

### 2.2 Stage 1 — Localise (new; replaces "sample first")

Two products, both over the whole index and both required to be *exhaustive within a declared
budget*:

**(a) Value lists** (`inventory.json`, rewritten). For each source, for each field whose values
are *reviewable*, one aggregation returning `value, count, first, last, dc(host)`:

- Field choice: from card roles (actor/action/object/from/to/outcome) plus parse fields with
  structural meaning (path, image, cmdline, parent, user, src, dest, query, url, registry). Not
  "all fields"; the fields that can carry an artefact.
- Reviewability: the aggregation is run when the *sample* suggests ≤ 5,000 distinct values (one
  effort budget, `LIST_MAX`), and the list is *complete* only when the aggregation returned
  ≤ `LIST_MAX` rows. Above that it is a **capped** list: keep per-host top-k and the rarest
  values, never pretend it is exhaustive.
- **Mechanism (the hard requirement):** the query must return the value column, **and it must use
  the name that path accepts**. On this Splunk role fields are search-time, so the fallback is
  `stats` over the source route, not `tstats`:
  `index=… sourcetype=<raw-path name> | stats count min(_time) as first max(_time) as last
  dc(host) as hosts by <field>`. `tstats … by` is used only when the field is in the tsidx *and*
  the sourcetype is the tsidx name. Both are chosen per `(source, field)` by a cheap probe:
  `| tstats count where index=I sourcetype="S"` vs `search index=I sourcetype="S" | head 1`
  (a measured example where they differ is in `SPLUNK_REALISM_AND_SETUP.md` §4.2, and each wrong
  choice costs a full scan before returning zero). `tstats` must be probed **one field per
  query** — one non-indexed field in a `by` list zeroes the whole group-by. A query that returns
  no value column is recorded as `unavailable:<mechanism>` or `unavailable:<name>`, never as
  `empty`, and the receipt counts it.
- **Partition-aware:** when the card is partitioned (`part.field=value`), the query includes the
  predicate and the record is keyed `(source, part, field)`.
- Cost control: one search per selected (source, field); budget the count (e.g. 64 per run, but
  the number is an effort budget, not a law) by *role first, then smallest list*, never by
  cardinality ascending alone. Report searches, seconds, and bytes/rows per list.

**(b) Entity spine** (new `spine.py`, store `entities.duckdb`). One row per `(entity, source,
part)` with `entity_kind`, `value`, `events`, `first_seen`, `last_seen`, `hosts`, `sources`,
`class_token` where a class exists (file extension class, url path shape, process basename
shape — derived, no dictionary). Entity kinds and how they are recognised *structurally*:

| kind | recognised by |
|---|---|
| `address` | IPv4/IPv6 shape |
| `hostname` | dotted label shape, ≥ 2 labels, not an address |
| `user` | role `actor`/`to` on auth-shaped sources, or a field whose values recur and are not addresses |
| `file` | path/name field, or basename shape in a file-writing source |
| `process` | image/parent/cmdline fields |
| `hash` | hex of length 32/40/64 |
| `registry` | backslash-separated key shape |
| `domain` | hostname that appears in a DNS/query field |

This is type classification, not a value list: no domain, extension or process name is named in
code. The spine is the join key for everything after it.

Acceptance (S1): on a training family, the spine contains the carrier entity of every graded
step; on botsv2, at least one *complete* list exists for a source that carries a graded artefact
and `first_seen_replaced > 0` in the notables receipt. Search-time enumeration cost is measured
and recorded.

### 2.3 Stage 2 — Episodes (replaces aggregate behaviours)

Keep the read receipts and the `events` table. Add an **episode** builder:

- **Segmentation by the entity's own cadence**, not fixed buckets: within `(entity, source)`,
  sort events; split when the gap exceeds `max(5 min, 4 × median gap)` and at 4 h; merge
  segments separated by < 5 min. Each segment is an episode with `start, end, events`.
- Each episode carries: the entity, the source, hosts, the **ordered event ids**, the distinct
  objects touched (files, addresses, URLs), and its neighbour episodes on the same host inside
  ±4 h (`prev_source`, `next_source`, `delta`). That neighbour list is the raw material for
  ingress→execute adjacency without needing a shared value.
- Read policy: a source whose full event count fits the allocated row budget is read **whole**
  (a whole-read tier); otherwise reads are anchored to localised candidates — the entity's own
  activity span and its burst windows from the ladder — never "newest per equal slice".
- The behaviour table stays as a *summary* for compatibility, not as the unit.

Acceptance: for every graded build-family step, the carrier entity has an episode whose window
contains the labelled line; episodes on the same host at adjacent sources are linked when they
are within 4 h; the receipt reports episodes per source and the read fraction per source.

### 2.4 Stage 3 — Signals (the generators, redefined)

Each signal is a *measure over the spine/episodes/value lists* and must report `candidates`
(opportunities), `kept`, and the attribution of its kept rows. All are cross-source where the
evidence allows; none names a value.

1. **Novelty** — index-wide first-seen per `(entity, host, source)` and per value, from the lists
   and spine. "This host has never executed this process before" is now a fact about the index.
2. **Dominance** — per source and per peer group (hosts with the same role vector), the entity's
   share, top-1 share, distinct-object count, and egress asymmetry when the source has bytes.
   Answers the wide-corpus scanner and the 99.5 % build attacker; complements rarity.
3. **Rarity / peer distance** — keep `peer_rare`'s idea, but the peer group is the source's
   entity population, and the measure is per-episode, not per aggregate.
4. **Flow / transition** — a value (file, hash, domain, address, user) appearing in ≥ 2 sources
   whose role vectors are different (ingress vs execution/persistence/egress), bounded by the
   value's own span. A flow is only a signal when at least one endpoint source can *decide* the
   step (role vector), not merely hold the value.
5. **Set novelty** — per host and window: N distinct values sharing a class token the host has
   never produced (e.g. a same-extension class, a same-parent process set, a same-path-shape set).
   This is the mass-encryption/staging shape and survives renaming.
6. **Misfit** — keep shape mining and F; gate on *parse coverage*, report novel share as the
   measure, keep a per-source cap. Never drop a source because it is novel.
7. **Detections (alerts)** — ingest the estate's own judgements. Recognition is structural:
   `event_type=alert` JSON, Suricata fast-log shape, or a card whose sample is detection-shaped
   with signature/severity + src/dest. Entity is `src`/`dest`/`user`/`host`; **never require an
   `action` field**.

### 2.5 Stage 4 — Cases (the product unit)

A **notable** is a signal occurrence: `signal, entities, source, window, measure, evidence
query, why`. A **case** is:

```
case = { case_id, anchor_episode, members[episode|notable], entities[], sources[],
         start, end, timeline[], why, score, links[] }
```

Assembly: union-find over episodes/signals that share an entity or a flow value, bounded by a
window (the union of member spans, capped at 24 h), then require the case to contain **at least
two independent pieces of evidence** (two sources, or two signals, or an episode + a flow) — a
single signal is a notable, not a case.

Case score (weights are LOFO-selected, none per-corpus):

```
score = w1 * independent_source_count
      + w2 * independent_signal_count
      + w3 * anchor_strength          # the anchor signal's own measure, normalised
      + w4 * entity_distinctiveness   # dominance/share, the relate instinct
      + w5 * coherence                # compactness in time; fewer hosts per step
```

Ranking: rank **cases**; within a case, rank members by their own measure. Report both
`case@k` and `member@k`. Promotion is retained but only *within* a case (a case in the head may
lift its own weak members), and any lifted member is re-judged if the judge has a budget, or
marked `unjudged: true` in the file and excluded from judged-only views.

### 2.6 Stage 5 — Judge (keep, re-scope)

Deterministic checks first: every member's evidence query must resolve to ≥ 1 event, and the
entity/value must appear in the returned row — otherwise the member is `unverified`, not a lead.
Then one model call per **case** (timeline + anchor + why, truncated), asking only for an ordering
opinion. `p_yes` orders within the head; it is never a pass gate, and a case is never dropped
because the model said no.

### 2.7 How it stays blind

No signature, IOC, extension, domain, process name, dataset name or keyword list. Fields are
chosen from card roles and parse structure; entity kinds are *shape* classes; flows are
value-in-≥2-sources-with-different-role-vectors; set novelty is class-token-without-history;
weights are LOFO step coverage; the knowledge store is labels on other indexes and refuses proof
indexes. `PROOF_INDEXES` must keep raising in every new entry point.

---

## 3. Measurement first (C0.2 — the honest instrument)

Nothing in §4 is accepted on the old metric. Define C0.2 precisely:

**Inputs**
- `ledger.jsonl` (new, emitted by the run): one row per read —
  `{stage, source_id, part, query, window_start, window_end, rows, capped, reason, values_extracted}`.
  This is the ground truth for *what was read*, replacing the post-hoc substring proxy.
- `inventory.json` value lists (S1) with status `complete|capped|unavailable:<reason>`.
- `entities.duckdb` spine + episodes.
- keys (deduped; class B/P/T; credit flag; `requires`).
- notables/cases with `rank`, `case_id`, `unjudged`.

**Reported numbers, per family, always side by side**
1. `keys` graded; `keys_reachable` (value appears in a ledger read row, a spine row, or a complete
   list); `steps` graded; `steps_reachable`; `steps_reachable_B+P`.
2. `recall` @50/@100/all in **loose**, **strict** (what/basis/why/entities only) and **line**
   modes; `recall_of_reachable` for each; `median_first_rank` of the first covering notable.
3. `case_recall` @50/@100: a scenario counts when a case in the head contains a member that
   *names* a graded artefact in its hypothesis (strict rule; promoted raw text never counts).
4. `promotion_effect`: every number with and without promoted rows, so promotion can never again
   inflate a score invisibly.
5. `cause` per step: `covered | instrument | not_surfaced | unreached | censored`, derived and
   overridable by an audit file.
6. `generator` table: `candidates (existed)`, `kept`, `attribution@50` (exclusive first-cover
   share), `marginal@50` (steps lost from the head when this generator is re-merged without it),
   and the LOFO fold values. The merge weight is the marginal, floored at `UNMEASURED_WEIGHT`.
7. `cost`: searches, requests, seconds, events read, read fraction, per stage.

**Baseline to beat (measured 2026-11-20, stored `snap_neon_02cc2e3`, C0.1)** — reproduce these
first, then improve:

| family | mode | @50 | reachable steps | recall of reachable @50 |
|---|---|---|---|---|
| botsv2 | entity loose / strict | 3/14 / 2/14 | 5/14 (B+P 5/11) | 3/5 / 2/5 |
| kyoushi | line | 11/12 | 11/12 | 11/11 |
| santos | line | 18/21 | 12/21 | 11/12 |
| russell | line | 15/22 | 15/22 | 14/15 |

C4 fold table (C0.1, same run): deviation 41–56, similar 42–70, **misfit 0, alerts 0,
peer_rare 0** in every fold, because the denominator is all steps and the cut is 50. C0.2 must
report the marginal (re-merge) weight and may report 0 only when removing the generator changes
no step in the head.

**Acceptance for the instrument itself**
- The stored-run numbers above reproduce exactly (for the fields that already exist).
- A promoted raw `relate` row cannot increase `strict` recall or `case_recall` (test with a
  synthetic promoted row naming an artefact).
- A generator that adds a step at @50 gets a non-zero marginal weight in the fold where it does;
  a generator whose only hit is at 51 is reported with `marginal@50 = 0` and a non-zero
  `marginal@100`, not silently zeroed from all steps.
- The ledger can distinguish "source never read" from "read and censored" for one graded step of
  each kind (test fixture + one live family).

### 3.1 The time budget, measured (2026-11-20, lab Splunk 10.2.5, idle VM)

Full detail and receipts: `SPLUNK_REALISM_AND_SETUP.md` §3. The numbers a budget has to be built
from:

| read | cost on this hardware |
|---|---|
| `tstats` on a default indexed field (`by host`), whole index | **1.0–3.0 s** (index-size independent) |
| `tstats` from an **accelerated** model | ~0.1 s (none exists in the lab yet) |
| `tstats` from an **unaccelerated** model, whole index | **200 s** for `Authentication`; **240 s** and 0 rows for an *empty* model |
| `tstats` from an unaccelerated model, **one day** | **4.3 s** |
| search-time `stats`, full index, botsv2 Windows (2.18 M) | **72.8 s** |
| search-time `stats`, full index, AIT `eve.json` (1.1 M) | **5.1 s** |
| search-time `stats`, one **day** of botsv2 Windows | **3.1 s** |
| search-time `stats`, one **hour** of `eve.json` | **1.0 s** (1,540 events) |
| a wrong field name or wrong sourcetype name in a `stats` route | **57–68 s** of scan to return zero |
| `\| eventcount summarize=false index=…` | **0.03–0.16 s** |

Derived rates: **~30 k events/s** on botsv2 Windows/stream data, **~220 k events/s** on the AIT
JSON streams, **~21 k events/s** through an unaccelerated data model.

Therefore the plan's existing budgets mean:

- `query_seconds: 30` (`executor.py:27`) = **≤0.9 M botsv2 events**, i.e. 0.4 % of that index and
  less than half of one security sourcetype. Any whole-index question is censored by the cap
  before the code is even slow.
- `job_seconds: 720` (`executor.py:28`) = **~22 M events**: 10 % of botsv2, ~90 % of an AIT family.
- 32 enumeration searches at 72 s each (the C1 shape) = **38 min** on one sourcetype — 38× the
  whole job deadline.

So the budgets are kept as *safety* caps and a second, explicit budget is added: **events read per
query and per run**, 250 k for botsv2-class data and 2 M for JSON/accelerated data, with the read
fraction reported (§4 S1, S6). No recall target may be met by raising these.

---

## 4. Work breakdown (lane-sized slices)

Order matters. Dependencies and parallelism are stated; the acceptance property is the merge
condition, and the live proof is what the orchestrator runs.

### S0 — Truthful measurement and one path (**do first, blocks scoring**)

- **Build:** `scoreboard.py` — add the C0.2 fields (case_recall, promotion_effect,
  conditional weight denominator `covered/existed`), keep all old fields; `relate.py` — emit
  `ledger` rows and a real `unjudged` flag; `run.py`/`sample.py` — write `ledger.jsonl` on every
  read; `product_jobs.py` — run relate **before** judge (or re-judge lifted ids) so the product
  path matches `--stage all`; `judge_notables.py` — mark rows that were never judged;
  **`siem/spl_backend.py` — drop `preview:true` export rows** (measured defect: a 104-row
  `tstats … by sourcetype` arrives as 307 rows with partial values and sums to 3× the index
  total, `SPLUNK_REALISM_AND_SETUP.md` §2.8; every stored number from an aggregate is suspect
  until this is fixed).
- **Files:** `notables/scoreboard.py`, `notables/relate.py`, `notables/run.py`,
  `notables/sample.py`, `notables/judge_notables.py`, `product_jobs.py`,
  `siem/spl_backend.py`, tests.
- **Acceptance:** stored-run baseline reproduces; the two synthetic tests above pass; `git grep`
  shows one stage order for both entry points; a recorded export body with 205 preview + 104 final
  rows yields exactly 104 rows.
- **Test:** unit (`tests/unit/test_hunt_scoreboard.py`, `test_hunt_run_injection.py`,
  `test_hunt_notables_merge.py`, plus a preview-filter test with a recorded body), plus the live
  rescore command.
- **Parallel:** no. Everything downstream is scored by this.

### S1 — Enumeration that works (**P0**; **Tier A starts now**, Tier B waits on Splunk setup)

- **Build:** rewrite `inventory.py`: field selection from roles + structural fields; partition
  predicate; **name probe + field probe**; mechanism choice (`tstats` if the field is in the
  tsidx, else `stats`); value-column assertion; statuses
  `complete|capped|unavailable:<mechanism>|unavailable:<name>`; per-list cost receipt
  (`mechanism`, `name_used`, `events_scanned`, `accel_window`); keep joints/flows data model.
  Wire the lists into the spine (S2) and the receipt.
- **Files:** `notables/inventory.py`, `notables/run.py`, `tests/unit/test_hunt_inventory.py`.
- **Why the mechanism probe is not enough (measured 2026-11-20, `SPLUNK_REALISM_AND_SETUP.md`
  §4.2):** on botsv2 the same Windows events have two sourcetype names — `WinEventLog` on the
  raw/search path, `wineventlog:security` on the tsidx/`tstats` path — and each path accepts only
  its own. `search … sourcetype="wineventlog:security" | stats count` returns **0 events** after
  scanning 2.15 M; `| tstats … sourcetype="WinEventLog" by host` returns **0 rows**. The stored
  cards carry the tsidx name, so swapping `tstats` for `stats` alone returns a silent zero.
  Also: one non-indexed field in a `tstats` `by` list zeroes the whole group-by, so the field
  probe must be **one field per query**.
- **Acceptance — Tier A (achievable today, no Splunk change):** on `botsv2` a complete list over
  a KV sourcetype (`linux_audit.exe`, 455 k events, measured 10.1 s) **or** `stream:http.accept`;
  on an AIT family a complete list over `eve.json.src_ip` (1.03 M, measured 5.1 s). Prove
  `values > 0`, `status: complete`, `first_seen_replaced > 0` on at least one behaviour, the
  query is `stats` with `events_scanned` recorded, and `unavailable` is never reported as `empty`.
  The 32-constant-action selection cannot recur (unit test: 40 constant action fields + 3 actor
  fields → the actor fields are selected).
- **Acceptance — Tier B (blocked on Splunk setup, `SPLUNK_REALISM_AND_SETUP.md` §5 Stage 3/4):** a
  complete list over a wide source (`wineventlog:security` 2.18 M or `winregistry` 55.5 M) in
  ≤ 5 s, via `tstats from datamodel=…` or `tstats by <indexed entity>`. Not achievable today:
  the same list costs 72.8 s as a `stats` scan.
- **Test:** fixture where `tstats` returns no value column (regression for today's bug); fixture
  where the tsidx name and the event name differ (must produce `unavailable:<name>`, not
  `empty`); fixture where the same field exists on two partitions (lists do not merge); fixture
  proving a `preview:true` export row is dropped (see S0).
- **Parallel:** with S4.

### S2 — Entity spine and episodes (**P0**)

- **Build:** new `spine.py` (`entities.duckdb`: entity rows + episode rows + episode-neighbour
  links); segmentation by the entity's cadence; whole-read tier; read anchors from localised
  candidates.
- **Files:** new `notables/spine.py`, `notables/behaviours.py` (read policy hooks),
  `notables/run.py`, tests.
- **Acceptance:** for each build family, every graded step's carrier entity has an episode
  containing its labelled line; adjacent-source episodes on one host within 4 h are linked; the
  read receipt reports `read_mode: whole|anchored|sampled` per source.
- **Test:** stored rows → deterministic episode boundaries; a gap fixture splits, a burst does
  not; one unit test that a singleton value becomes an entity but never a behaviour key.
- **Parallel:** after S1 (needs lists) but its reader can start on stored stores.

### S3 — Flows, cases, promotion (**P0**)

- **Build:** `relate.py` → case builder over the spine: flow signal with role-vector endpoints;
  union-find over entities/values; two-evidence rule; case score; member ranking; promotion
  within a case with `unjudged` marking; case receipt with coverage and censored counts.
- **Files:** `notables/relate.py`, `notables/scoreboard.py` (case metrics), tests.
- **Acceptance (live):** on each build family, ≥ 1 case in the top 50 per scenario that contains a
  B/P member; every case has ≥ 2 pieces of evidence; `coverage_complete` reported and the
  uncapped fraction > 0; promotion cannot add an unjudged row to a judged-only view.
- **Test:** case with one signal is not a case; two sources with the same value but adjacent
  role vectors do link; a promoted raw row does not credit a graded step in strict mode.
- **Parallel:** after S2. S5 can run alongside.

### S4 — Estate detections (**P1, small, can run first**)

- **Build:** structural alert recognition in `cards.py`/`generators.py` (JSON `event_type=alert`,
  Suricata fast-log, detection-shaped cards); entity from `src/dest/user/host`; drop the
  `action`-required rule; the alerts signal reports `existed` even when it keeps nothing.
- **Files:** `notables/cards.py`, `notables/generators.py`, tests.
- **Acceptance (live):** `alerts existed > 0` on botsv2 and russell; a Suricata alert card is
  read as a detection stream even when its `kind` was guessed `activity`; no alert notable is
  raised without an entity.
- **Test:** fast-log line fixture → alert event; `event_type=alert` fixture → alert; card with no
  action but with `signature` + `src` → notable.
- **Parallel:** with S1.

### S5 — Weights by marginal contribution (**P1, zero cost**)

- **Build:** replace `merge.conditional_weights` with a measured marginal: for each family and
  each generator, re-merge the stored per-generator lists without that generator (same method,
  weights renormalised) and count the steps that leave the @50 head; LOFO across families; the
  weight is the mean marginal, floored at `UNMEASURED_WEIGHT`. Record `attribution@50` beside it.
  Keep `PORTAL_HUNT_MERGE_WEIGHTS` as the delivery mechanism.
- **Files:** `notables/merge.py`, `notables/scoreboard.py`, tests.
- **Acceptance:** weights are derived from a re-merge, not from a global denominator; the fold
  table is reported; a generator whose hit is at 51 is reported `marginal@50 = 0`,
  `marginal@100 > 0` and is not zeroed on absence; a generator with `existed == 0` keeps a unit
  weight.
- **Test:** pure function fixtures on a synthetic three-generator ranking (removing one drops a
  known step → positive weight; removing one changes nothing → 0 but not negative).
- **Parallel:** anywhere after S0.

### S6 — Localise-then-read (**P0, the coverage win**; **rungs 2–3 start now**, rung 1 waits on Splunk setup)

- **Build:** `sample.py`/`behaviours.py` read policy as a **three-rung ladder**, each rung guarded
  by a probe:
  1. **accelerated aggregate** — `tstats summariesonly=true … from datamodel=…` when a model
     covers the source *and* the time range is inside its acceleration window; record
     `accel_window` in the receipt (a range outside it is a scan, not a miss);
  2. **indexed-field aggregate** — `tstats … by host, _time span=<width>` on the default fields
     (1–3 s whole index): yields *where* and *when*, never *who*;
  3. **narrowed scan** — `search` restricted to the host **and** time window rung 2 produced, with
     a declared events cap and `stats` for the value list.
  Plus: whole-read tier only for sources ≤ 10 M events; structured-depth cap (parse fields kept
  whole, raw prefix for unstructured only).
- **Why by time, not by host (measured, `SPLUNK_REALISM_AND_SETUP.md` §3):** on botsv2 Windows data
  restricting to the busiest host saved only 24 % (55.6 s vs 72.8 s) because the tsidx `host` is
  the collector, not the endpoint; restricting to one day saved 96 % (3.1 s). A 1-hour `eve.json`
  window is 1.0 s / 1,540 events against 5.1 s / 1.03 M for the whole source.
- **Files:** `notables/sample.py`, `notables/behaviours.py`, tests.
- **Acceptance — now:** no build-family regression; the read fraction reported per source; on
  botsv2 the `keys_reachable` ceiling holds at the current 8/24 **with the per-key cause recorded**
  (`unreached | censored | name_mismatch | instrument`), and every read carries `events_scanned`.
- **Acceptance — after Splunk setup (Stage 3 or 4):** `keys_reachable` ≥ 12/24 and
  `steps_reachable` ≥ 10/14, read fraction reported and not more than a declared multiple of
  today's budget. A ceiling that does not rise from 8/24 is a finding about read policy, not a
  reason to raise the budget.
- **Test:** the same source with 47 k vs 55 M events gets whole vs anchored; a 20-minute burst is
  selected by the 5 m width and missed by the 4 h width (fixture); a read outside the acceleration
  window is labelled `scan` in the receipt, not `empty`.
- **Parallel:** after S2 (same files); S5 can run alongside.

### S7 — Judge over cases (**P2**)

- **Build:** one call per case with the timeline; deterministic verification first; `p_yes` only
  orders; `unjudged` never counts as rejected.
- **Files:** `notables/judge_notables.py`, `notables/rerank.py`, tests.
- **Acceptance:** a case with an unverified anchor is reported `unverified`; judged-only views
  exclude unjudged members; no case is dropped by model answer.
- **Parallel:** last.

**Parallel map:** S0 → (S1 ‖ S4) → S2 → (S3 ‖ S5 ‖ S6) → S7.

### 4.1 What needs the Splunk setup, and what can start now

The setup is `SPLUNK_REALISM_AND_SETUP.md` §5 (Stage 1 sourcetype reindex → Stage 2 TAs/CIM →
Stage 3 acceleration → Stage 4 index-time extraction). Nothing below changes the order; it says
which acceptance criteria are actually reachable before the setup lands.

| slice | needs Splunk setup? | can start now | what the setup unlocks |
|---|---|---|---|
| S0 instrument + `preview` fix | no | **yes** | nothing — prerequisite for every other number |
| S5 marginal weights | no (stored runs) | **yes** | nothing |
| S4 estate detections | partly (Stage 2 enables `TA-suricata-4`, so the AIT `eve.json` gets detection fields; botsv2's `suricata` already has them) | **yes** | detection-shaped cards on the families |
| S2 spine/episodes | no to build; Stage 4 to derive it by aggregate | **yes** on stored stores | spine from `tstats` instead of scans |
| S1 Tier A | no | **yes** | — |
| S1 Tier B (wide-source list ≤5 s) | **yes** (Stage 3 or 4) | no | the whole C1 claim at botsv2 scale |
| S6 rungs 2–3 (indexed aggregate + narrowed scan) | no | **yes** | — |
| S6 rung 1 (accelerated aggregate) | **yes** (Stage 3) | no | whole-index localisation in seconds |
| S6 botsv2 acceptance (12/24 keys) | **yes** (Stage 3 or 4) | no | a rise in the reachability ceiling |
| S3 cases/promotion | no | **yes** | better cases via the spine, not via config |
| S7 judge over cases | no | **yes** | nothing |

Revised order:

```
start now:  S0 (preview fix + instrument) → S5 → S4  ‖  S2 on stored stores
            → S1 Tier A (family + cheap botsv2 lists) → S3 on family output
blocked:    S1 Tier B, S6 rung 1, the botsv2 12/24 acceptance   ← after Stage 1–3
then:       S2 re-derivation by aggregate → S6 full ladder → S7
```

**If the operator declines the setup entirely**, the honest position is written in
`SPLUNK_REALISM_AND_SETUP.md` §8: on a Splunk with no index-time entity fields and no accelerated
model, the wide-corpus ceiling cannot rise, and C1 must be stated as "a value list on a source
whose fields are already extracted", not as the general mechanism.


---

## 5. Live proof plan for the orchestrator

**Preconditions.** Images rebuilt if `portal/` moved; `.env` keys exported by name only
(`PIPELINE_API_KEY`, `LAB_SPLUNK_*`); the Pipeline (:9099) serving the judge/embedding seats; the
lab Splunk reachable; scratch under `coding_task/scratch/`.

**Step 1 — Rescore the stored runs (no Splunk).** Reproduce §3's baseline; confirm the instrument
before any new run. Pass: exact match on the existing fields, the new fields present.

**Step 2 — LOFO on the training families.** Four runs with knowledge/weights held out per family
(the existing `RUN_HUNT_REDESIGN.sh` loop already passes `--knowledge-families`; add
`--weights` and the new `--causes`/case report). Constants under test — promotion caps, episode
gap multiplier, per-list caps, set-novelty window — are chosen by leave-one-family-out over
kyoushi/santos/russell, **never** on botsv2, and frozen before step 3.

```bash
# per family F, held-out knowledge = the other two build families
uv run python -m portal.modules.security.core.hunt.notables \
  --index "$IDX" --out coding_task/scratch/lofo/$F --stage all \
  --family "$F" --knowledge-store "$STORE" --knowledge-families "$OTHERS"
uv run python -m portal.modules.security.core.hunt.notables.scoreboard \
  --out coding_task/scratch/lofo --weights --json \
  --keys botsv2=… --keys kyoushi=… --keys santos=… --keys russell=…
```

**Step 3 — Wide-corpus run (botsv2), same code, no tuning.** The only wide test available before
the proof sets. Pass bar, all four:

1. **No build-family regression:** recall-of-reachable @50 ≥ the §3 values on each of the three
   families, in their own mode.
2. **Coverage:** botsv2 `keys_reachable` ≥ 12/24 and `steps_reachable` ≥ 10/14; the ceiling is
   reported even if recall is flat. **Conditional on the Splunk setup** (`SPLUNK_REALISM_AND_SETUP.md`
   §5 Stage 3 or 4). Measured 2026-11-20, a full-index value list on a 2.18 M-event botsv2
   sourcetype costs 72.8 s and the 55.5 M-event `winregistry` ~46 min, so on today's untuned index
   this bar is unreachable by construction. Until the setup lands, the bar is "ceiling reported
   with a per-key cause and no regression", and reaching 12/24 after tuning is a separate claim.
3. **Cases:** ≥ 3 of 4 botsv2 scenarios have a case in the top 50 that contains a B/P member
   naming an artefact (strict rule), with `promotion_effect` reported separately.
4. **Honesty:** every weight is a measured marginal, not a global denominator; `alerts existed
   > 0`; no number rises when promoted rows are removed; each generator's `attribution@50` and
   `marginal@50` are reported beside its weight.

A pass on 1–3 is a real result. A ceiling that does **not** rise from 8/24 to ≥ 12/24 is a finding
about enumeration/read policy, not a reason to raise the budget.

**Step 4 — Held-out proof, once, at the very end.** Only after steps 1–3 are green and every
constant is frozen. Run the four training-family models' final code against
`hb_ait_wheeler`, `hb_cloudobs_aws` and `botsv1`, score, and report as-is. Any change made after
seeing the numbers voids the proof. `PROOF_INDEXES` stays in the code path; the run script may
name the index, the code must still refuse it outside the sanctioned end step.

**Step 5 — Report.** One table per family: mode, @50/@100/all, reachable, recall of reachable,
case recall, causes, cost, generator weights. Plus the read ledger summary and the holdout result.
State explicitly which numbers are on learned data and which on the proof sets.

---

## 6. Risks and open questions

| # | Risk / question | Why it matters | Owner |
|---|---|---|---|
| 1 | **Search-time enumeration cost — measured** (`SPLUNK_REALISM_AND_SETUP.md` §3): 5.1 s per 1.1 M JSON events, 10.1 s per 455 k KV events, 72.8 s per 2.18 M Windows events; a 32-list run over one Windows sourcetype is ~38 min. | It is the mechanism the whole rebuild rests on; the budget is events, not queries (§3.1). | Lanes; S1 receipts |
| 2 | **Index-time extraction.** Adding index-time fields makes `tstats` cheap and exact, but needs a reindex and grows tsidx (+40–100 % estimate). | Converts S1 from a scan problem into an aggregation problem; it is the only change that raises the ceiling on today's corpus. | Operator |
| 3 | **One wide corpus.** botsv2 is the only wide index that is not held out; a design that passes it may still not generalise. Also: botsv2 is the **only** corpus with CIM tags (`Authentication`/`Web`/`Intrusion_Detection` populate; `Network_Traffic`/`Endpoint.Processes` are empty), so it flatters the CIM path. | The pass bar cannot prove generality; exercise the degradation on a family. | Operator (accept the claim as unproven) |
| 4 | **Sampling remains for the tail.** Anchored reads are still a fraction of a 55M-event source; host pruning on Windows data saves only 24 %. | Ceiling will rise, not reach 24/24; say so in the pass bar. | Lanes |
| 5 | **Label noise.** The knowledge store has contradicted statements; `similar_to_known` is at chance on two families. | A label-trained generator must not carry the head. | S5 / operator |
| 6 | **Judge bias.** `p_yes` yes-always was measured as model bias. | Keep it out of the pass bar; ordering only. | S7 |
| 7 | **Case promotion vs the metric.** Promotion can lift a member whose carrier is a raw line. | Without strict case credit, the scoreboard will report a win that is not one. | S0/S3 |
| 8 | **Cost ceiling.** More lists and anchored reads raise searches and wall time; the hunt job has a 720 s deadline (~22 M events at the measured rate). | A design that cannot complete in the budget is not a design. | S1/S6 receipts |
| 9 | **Two names per source.** botsv2 Windows events answer to `WinEventLog` (raw) and `wineventlog:security` (tsidx); a mechanism swap without a name probe returns 0 silently. | Any C1/S1/S6 read can be a paid-for zero. | S0/S1 |
| 10 | **Preview rows inflate every aggregate** (`spl_backend.py` keeps `preview:true`). | Stored card events, `index_facts` and value lists can be 2–3× wrong and non-reproducible. | S0 |

### The decision that was open, and its answer (2026-11-20)

The open question was: **may the hunt run full-index search-time aggregations (`stats`), and/or
add index-time field extraction?** The operator answered: *tstats is preferred, but use what will
work; measure the speed; and tune the stock Splunk so it is a realistic deployment.*

Measurement (`SPLUNK_REALISM_AND_SETUP.md` §3) turns that into a rule rather than a permission:

- **Both mechanisms are allowed, and the hunt must choose per field by probing**: `tstats` where
  the field is in the tsidx, `stats` where it is not. On this lab that means `stats` for every
  role field and `tstats` for `host`/`source`/`sourcetype` only.
- **Search-time `stats` is affordable on a family and not on a corpus**: 5.1 s over 1.03 M
  `eve.json` events, 10.1 s over 455 k `linux_audit`, but 72.8 s over 2.18 M Windows events and
  ~46 min extrapolated over `winregistry`'s 55.5 M. So S1's wide-source lists need Stage 3 or 4.
- **Index-time extraction is the only change that makes `tstats` see entities on the existing
  corpus**, and it needs a reindex plus roughly +40–100 % tsidx (estimate). It is now a question
  of ops cost, not of design.

Decision handed back to the operator is now the *setup* set in
`SPLUNK_REALISM_AND_SETUP.md` §8: reindex for sourcetypes, index-time entity fields, acceleration
scope and window, whether one index stays untuned as a degradation control, and which deployment
the pass bar measures. Everything in §4 except S1 Tier B and S6 rung 1 can be built while those
are decided.

---

## 7. What not to build

- Any rule keyed to a literal value, extension, filename, hash, domain, provider, cookie or
  password. It buys one scoreboard row and teaches the tool nothing.
- More read budget as a standalone change: at 0.118 % a 4× budget is still sampling.
- A sixth within-source rarity generator. The estate already has five; it needs cross-source
  transitions and dominance.
- Per-corpus weights. LOFO or nothing; a constant that only exists on one family is a bug.
- A signature/feed import. The estate's *own* detections are the only external judgement allowed,
  and they are events, not a rule list.
- A case UI or narrative layer before case recall is measured.
