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
  rare thing is. On botsv2 the run read 0.118 % of 226.3M events; 8 of 24 graded keys were in
  anything it read. A 12-event artefact is seen 1.4 % of the time by construction. Meanwhile the
  families it can nearly read whole score **11/11, 14/15, 11/12 of their reachable steps** — the
  ranker is not the loss.
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
- Reviewability: the aggregation is run when the *sample* suggests ≤ 2,000 distinct values
  (cheap to list) and the list is *complete* only when the aggregation returned ≤ 5,000 rows.
  Above that it is a **capped** list: keep per-host top-k and the rarest values, never pretend
  it is exhaustive.
- **Mechanism (the hard requirement):** the query must return the value column. On this Splunk,
  role fields are search-time, so the default is `stats` over the source route, not `tstats`:
  `index=… sourcetype=… | stats count min(_time) as first max(_time) as last dc(host) as hosts
  by <field>`. `tstats … by` is used only for default/indexed fields and is chosen per field by a
  cheap probe. A query that returns no value column is recorded as `unavailable:<reason>`, never
  as `empty`, and the receipt counts it.
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
  (`read_wholetier`); otherwise reads are anchored to localised candidates — the entity's own
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
6. `generator` table: `candidates (existed)`, `kept`, `covered@50`, `covered/existed` (the
   conditional weight), and the LOFO fold values.
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
peer_rare 0** in every fold. C0.2 must show a non-zero weight for any generator with
`existed > 0`.

**Acceptance for the instrument itself**
- The stored-run numbers above reproduce exactly (for the fields that already exist).
- A promoted raw `relate` row cannot increase `strict` recall or `case_recall` (test with a
  synthetic promoted row naming an artefact).
- A generator with candidates but a 51st-place hit gets a non-zero conditional weight.
- The ledger can distinguish "source never read" from "read and censored" for one graded step of
  each kind (test fixture + one live family).

---

## 4. Work breakdown (lane-sized slices)

Order matters. Dependencies and parallelism are stated; the acceptance property is the merge
condition, and the live proof is what the orchestrator runs.

### S0 — Truthful measurement and one path (**do first, blocks scoring**)

- **Build:** `scoreboard.py` — add the C0.2 fields (case_recall, promotion_effect,
  conditional weight denominator `covered/existed`), keep all old fields; `relate.py` — emit
  `ledger` rows and a real `unjudged` flag; `run.py`/`sample.py` — write `ledger.jsonl` on every
  read; `product_jobs.py` — run relate **before** judge (or re-judge lifted ids) so the product
  path matches `--stage all`; `judge_notables.py` — mark rows that were never judged.
- **Files:** `notables/scoreboard.py`, `notables/relate.py`, `notables/run.py`,
  `notables/sample.py`, `notables/judge_notables.py`, `product_jobs.py`, tests.
- **Acceptance:** stored-run baseline reproduces; the two synthetic tests above pass; `git grep`
  shows one stage order for both entry points.
- **Test:** unit (`tests/unit/test_hunt_scoreboard.py`, `test_hunt_run_injection.py`,
  `test_hunt_notables_merge.py`), plus the live rescore command.
- **Parallel:** no. Everything downstream is scored by this.

### S1 — Enumeration that works (**P0**)

- **Build:** rewrite `inventory.py`: field selection from roles + structural fields; partition
  predicate; mechanism probe (`tstats` if the column appears, else `stats`); value-column
  assertion; statuses `complete|capped|unavailable:<reason>`; per-list cost receipt; keep
  joints/flows data model. Wire the lists into the spine (S2) and the receipt.
- **Files:** `notables/inventory.py`, `notables/run.py`, `tests/unit/test_hunt_inventory.py`.
- **Acceptance (live, botsv2):** ≥ 1 complete list whose values are parse-derived role values
  (not constant template actions); `unavailable` never reported as `empty`; `first_seen_replaced`
  > 0; the 32-constant-action selection cannot recur (unit test with a fixture of 40 constant
  action fields + 3 actor fields → the actor fields are selected).
- **Test:** fixture where `tstats` returns no value column (regression for today's bug); fixture
  where the same field exists on two partitions (lists do not merge).
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

### S5 — Conditional weights (**P1, zero cost**)

- **Build:** `merge.conditional_weights` denominator = the generator's own candidates
  (`covered / existed`), a floor of `UNMEASURED_WEIGHT` when `existed == 0`, and LOFO folds per
  family; merge receipt records the denominator; `PORTAL_HUNT_MERGE_WEIGHTS` unchanged.
- **Files:** `notables/merge.py`, `notables/scoreboard.py`, tests.
- **Acceptance:** no `existed > 0` generator gets 0 unless it covered 0 *of its own candidates*;
  the fold table is reported; a generator whose first hit is at 51 keeps a non-zero weight.
- **Test:** pure function fixtures (candidates 100, covered 1 → weight 1 not 0; candidates 0 →
  unit).
- **Parallel:** anywhere after S0.

### S6 — Localise-then-read (**P0, the coverage win**)

- **Build:** `sample.py`/`behaviours.py` read policy: whole-read tier; anchored reads on the
  entity/value spans; cadence ladder for burst windows; structured-depth cap (parse fields are
  kept whole; raw prefix for unstructured only).
- **Files:** `notables/sample.py`, `notables/behaviours.py`, tests.
- **Acceptance (live, botsv2):** `keys_reachable` ≥ 12/24 and `steps_reachable` ≥ 10/14 (from
  8/24 and 8/14), with the read fraction reported and not more than a declared multiple of today's
  budget; no build-family regression.
- **Test:** the same source with 47k vs 55M events gets whole vs anchored; a 20-minute burst is
  selected by the 5 m width and missed by the 4 h width (fixture).
- **Parallel:** after S2 (same files); S5 can run alongside.

### S7 — Judge over cases (**P2**)

- **Build:** one call per case with the timeline; deterministic verification first; `p_yes` only
  orders; `unjudged` never counts as rejected.
- **Files:** `notables/judge_notables.py`, `notables/rerank.py`, tests.
- **Acceptance:** a case with an unverified anchor is reported `unverified`; judged-only views
  exclude unjudged members; no case is dropped by model answer.
- **Parallel:** last.

**Parallel map:** S0 → (S1 ‖ S4) → S2 → (S3 ‖ S5 ‖ S6) → S7.

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
   reported even if recall is flat.
3. **Cases:** ≥ 3 of 4 botsv2 scenarios have a case in the top 50 that contains a B/P member
   naming an artefact (strict rule), with `promotion_effect` reported separately.
4. **Honesty:** every generator with `existed > 0` has a non-zero conditional weight; `alerts
   existed > 0`; no number rises when promoted rows are removed.

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
| 1 | **Search-time enumeration cost.** Role fields are search-time; listing them means `stats` scans, not `tstats` aggregates. 64 lists over wide sources could be hours of index time. | It is the mechanism the whole rebuild rests on; the cost is unmeasured. | Operator decides; S1 measures. |
| 2 | **Index-time extraction.** Adding index-time fields for the lab/training indexes makes tstats cheap and exact, but is an ops change to Splunk. | Converts S1 from a scan problem into an aggregation problem. | Operator |
| 3 | **One wide corpus.** botsv2 is the only wide index that is not held out; a design that passes it may still not generalise. | The pass bar cannot prove generality; only a second telemetry class can. | Operator (accept the claim as unproven) |
| 4 | **Sampling remains for the tail.** Anchored reads are still a fraction of a 55M-event source. | Ceiling will rise, not reach 24/24; say so in the pass bar. | Lanes |
| 5 | **Label noise.** The knowledge store has contradicted statements; `similar_to_known` is at chance on two families. | A label-trained generator must not carry the head. | S5 / operator |
| 6 | **Judge bias.** `p_yes` yes-always was measured as model bias. | Keep it out of the pass bar; ordering only. | S7 |
| 7 | **Case promotion vs the metric.** Promotion can lift a member whose carrier is a raw line. | Without strict case credit, the scoreboard will report a win that is not one. | S0/S3 |
| 8 | **Cost ceiling.** More lists and anchored reads raise searches and wall time; the hunt job has a 720 s deadline. | A design that cannot complete in the budget is not a design. | S1/S6 receipts |

### The one decision needed from the operator first

**May the hunt run full-index search-time aggregations (`stats`), and/or add index-time field
extraction for the lab and training indexes?**

- **Yes to search-time `stats`** (recommended): S1 as written; cost measured in S1's receipt; the
  budget is index time, not code.
- **Yes to index-time extraction** (preferred if ops allows): S1 becomes cheap `tstats`; the
  inventory is exact and the run faster.
- **No** (tstats-only on default fields): S1 must be narrowed to the default indexed fields
  (host/source/sourcetype/user/src/dest); the value-inventory claim then covers far less, and the
  plan's coverage target (12/24 keys) is probably unreachable — in which case the honest move is
  to say the wide-corpus ceiling cannot be raised without extraction, and stop claiming C1 as the
  fix.

Everything else in §4 can be built while that is decided, but S1 and S6 are shaped by the answer.

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
