# OrcaCyber code review — the R2 hunt as built (2026-11-20)

Scope: a working threat hunter's walk of the whole pipeline — `cards → behaviours → generators →
ranked notables → relate → judge` under `portal/modules/security/core/hunt/notables/` — plus the
C1/C2/F additions on `lane/hunt-c1c2-ready` and the C0/C4 instrument on this lane. This is the
code-and-live companion to `PRACTITIONER_REVIEW.md` (2026-11-19, written without code access); it
says which of that review's assumptions the code confirms, which it breaks, and what to do next.
The build plan is `ORCACYBER_HUNT_PLAN.md`.

Evidence classes, per claim:

- **[code]** — read in the module and line named.
- **[live]** — measured by me in this session against the lab Splunk index or a stored DuckDB run.
  The exact commands are in §12.
- **[judgement]** — my opinion as a hunter, reasoned, not measured here.

Held-out sets: `hb_ait_wheeler`, `hb_cloudobs_aws`, `botsv1` were never read, queried or tuned
against. `PROOF_INDEXES` still raises [code `knowledge.py:27-29`, `relate.py:625-631`]. One
`| tstats count where index=* by index` (an inventory of the lab, run before I narrowed to the
training families) returned one event count per index, held-out names included. No event, key or
row from a held-out index was read; no constant or decision below uses those counts. Disclosed in
§13.

---

## 0. Verdict

**The detector is not the binding constraint; coverage and the unit of evidence are.** With the
new C0 instrument, the build families score **11/11, 14/15 and 11/12 of their *reachable* steps at
@50** — the ranker is at 91–100 % of what the run actually read [live]. What they miss is the
step whose evidence was never read. On the wide corpus, only **8 of 24 graded keys and 8 of 14
steps were in anything the run read**, and the deck is stacked further by a sampler that reads
0.118 % of 226.3M events, per source rather than by evidentiary value.

**C1 does not exist as delivered.** On the real `botsv2` index it ran 32 searches and returned
**0 values, 0 joints, 0 flows**; downstream it replaced **0** first-seen values and produced **0**
candidates [live]. It is not weak or partial — it is inert, for a mechanical reason: it asks
`tstats` to aggregate by card role fields, and those fields are search-time extractions this
Splunk cannot aggregate. That is a design-level miss, not a tuning miss.

**C2's flow half is dead for the same reason** (no flows → no flow-only case, `transitions` empty
in every case), but its case/promotion half runs and changes the head: 6 cases, 9 lifts, 4 raw
`relate` rows injected into the top 12 [live]. That half is worth keeping and fixing; in the
product path it is applied *after* the judge, so the rows it lifts are unjudged [code
`product_jobs.py:270-281`].

**Verdict: partial rebuild.** Keep the estate map, cards/parse, executor budget and coverage
discipline, misfit shape mining (with F), the C0 instrument and the LOFO harness. Replace the
read strategy (sample-by-default → localise-then-read), the unit of evidence (per-source
behaviour vocabulary → per-entity episodes), the value-enumeration mechanism (tstats-only →
field-aware, partition-aware aggregation that proves it returned a value column), the alert
path, and the ranking unit (flat notables → cases with members). Details and slices in the plan.

---

## 1. The pipeline as built

### 1.1 Cards — the estate map, and the closest thing to a hunter's first hour

`index_facts` runs one `| tstats count min(_time) max(_time) by sourcetype` plus `by sourcetype
source` and `by sourcetype host`, and a cadence aggregation; the card then holds volume, span,
host population, shared source names, active periods and count CV [code `sample.py:183-237`;
`cards.py:99-133`]. This is genuinely the hunter's step 1 and 2 of my review, and it is the part
most worth keeping. The LLM is asked one question per *structure* (not per source), with field
names, presence, distinct counts and examples, to name kind and roles [code
`cards.py:53-73, 334-380`]. Two properties matter:

- Cards are **structure-aware and content-blind**: the model sees field statistics and examples,
  not the attack. Blindness is preserved [judgement].
- The card's `kind` is a **format/behaviour judgement**, not an evidentiary one, and it is
  load-bearing for which generator may read the source [code `cards.py:38-43`]. That is how the
  estate's own detections end up in the wrong stream (§1.5).

On `botsv2` the card set is 147 cards over 104 sourcetypes: 117 activity, 27 other, 2
measurement, **1 alert** [live, `sources.json`]. The one alert card is
`ess_content_importer` (a CIM content-import stream), with `roles: {}`.

### 1.2 Behaviours — sampling first, and a vocabulary unit

The read budget is `400,000 // sources // 12`, capped at 2,500 per window [code
`behaviours.py:44-45, 585-588`]; with 85 eligible sources that is 392 events per window. Each
window is read with `| head N` — the *newest* events of the slice [code `sample.py:256-300`] — and
a source is read whole only when it fits the whole budget (`events <= per_window * 12`) [code
`behaviours.py:704-707`]. Burst windows are added for the rest, chosen by a residual-z over 4-hour
buckets [code `behaviours.py:710-789`]. The declared read is honest (share-of-source, windows,
notes on every receipt) and that discipline is worth keeping. But the estate dictates the
budget: 5.2k lines from a 47k-event EDR source and from a 55.5M-event registry source alike.

The unit is `(source, actor, action, object)` aggregated over the whole read [code
`behaviours.py:635-658`]. Field selection is deterministic: a field is a literal identity only if
`distinct >= 2`, `recurrence >= 2.0`, `bucket_share >= 0.5`, `distinct <= 2000`; otherwise the role
is either a constant (`distinct == 1`) or wildcarded to a shape [code `behaviours.py:200-238,
249-276`]. Consequences a hunter feels:

- A value seen **once** cannot be a behavior key; it survives only inside `example_raw` [code
  `behaviours.py:256-261`]. On `botsv2` that is 10,134 of 17,928 behaviours [audit], and my live
  run keeps 21,770 behaviours for 266,972 events read [live].
- **Order is lost**: the aggregate has no sequence, no distinct-object list, no transition. The
  168,004-event scanner becomes either one row or a wildcarded shape depending on the field plan.

### 1.3 Generators — five answers to the same question

All five rank *within* a source, over aggregated or sampled reads:

| generator | what it measures | code |
|---|---|---|
| `alerts` | distinct `(alert, entity)` pairs in sources the model labelled `kind=alert` | `generators.py:196-313` |
| `peer_rare` | host-share × actor-share of a behaviour, relative to source totals | `generators.py:316-415` |
| `deviation` | 4-hour source bursts/first-seen + behaviour first-seen/newest + behaviour bursts | `generators.py:552-807` |
| `misfit` | shapes that fit no card structure (F gate) | `misfit.py:28-110` |
| `similar_to_known` | embedding distance to labelled bad/good behaviour statements | `similar.py:376+` |

Three structural facts:

1. **No generator joins two sources.** Every measure is computed inside one `source_id`; the one
   cross-source construct (`relate`) runs after ranking, on 40 seeds [code `relate.py:38`].
2. **Novelty is still sample-first-seen** for almost every behaviour. C1 corrects it only when the
   behaviour's literal `(field, value)` set is *exactly* a joint key in `inventory.json` [code
   `inventory.py:508-533`], and on `botsv2` that happened 0 times [live].
3. **The alert stream is not the estate's detections.** `_add_alert` returns false unless the
   parsed row yields an `action` (or object) value [code `generators.py:158-168`]; the only
   `kind=alert` card on `botsv2` has no roles, so the generator read rows and produced
   `existed=0`. Meanwhile `suricata` and `pan:threat` — where the detections live — are
   `kind=activity`, so their alert events are behaviours, never alerts [live, `sources.json`].
   This is a different defect from the one `GENERATOR_WEIGHTS_REPORT.md` §3 fixed (part
   discovery), and it survives it.

### 1.4 Merge — deficit round-robin on weights that encode an absence

`merge_notables` groups per generator and allocates head slots by weight [code
`merge.py:52-71, 117-150`]. `DEFAULT_WEIGHTS` are `deviation 26, misfit 6, similar_to_known 31,
alerts 0, peer_rare 0` [code `merge.py:12-18`]. A zero weight does not drop a generator; it
pushes its whole list past the merged head, so `peer_rare`'s 300 notables are all "all" and none
is "@50". With `similar_to_known` absent (no embedder) my live run merged 604 rows and the top 50
was deviation/misfit only — the same shape as the stored reports.

### 1.5 Relate and promotion — the case layer, half-alive

`relate` pivots on identity-role values and addresses from up to 40 seeds, within each seed's own
activity span, ranks neighbours by within-source share, union-finds seeds into cases, and lifts
weak case members into the head [code `relate.py:210-424, 634-681, 855-930`]. Removing the
training-index gate is correct and verified: `relatable_index` refuses only proof indexes, and
relate ran on `botsv2` [code `relate.py:625-631`; live].

Live on `botsv2`: 40 seeds, 48 requests, 479 related events, **6 cases, 9 lifts**, and 4 of the
lifted rows are newly created `relate` rows sitting at positions 2, 3, 10 and 11 of
`notables.jsonl` [live]. Two problems:

- **Order-dependent judging.** `--stage all` runs relate *before* judge [code `run.py:66`], but
  the product job runs judge *before* relate [code `product_jobs.py:270-281`] and judges only
  `LEADS_LIMIT = 10` rows [code `product_jobs.py:47, 296`]. In the product path every row
  promotion inserts into the head is **unjudged**, and no later step judges it. The same feature
  behaves differently in two entry points; one of them is the product.
- **Coverage is declared incomplete.** 28 of 48 relate queries hit the row cap and 15 reported
  `reason: censored`; `coverage_complete=false` [live]. So even the case layer is a sample, and it
  says so — which is better than hiding it, but it means case recall has no ceiling.

And a measurement interaction that must be fixed before any case work is scored: a promoted
`relate` row's `what` is **the raw event line** [code `relate.py:581`]. The entity scoreboard
counts a key value anywhere in `what/basis/why/evidence` [code `scoreboard.py` RULE/mode table],
so promotion can *create* coverage credit from an unanalysed raw line. Any case-level metric must
credit a case only through a member that carries a hypothesis about the artefact.

### 1.6 Judge — a per-notable yes/no, on the head only

The judge asks one binary question per notable, with up to three evidence lines and the nearest
labelled items [code `judge_notables.py:22-31, 108-121`]. `p_yes` is used as an ordering feature
in Stage 2 [code `rerank.py:1-20`]. This is triage, not detection: it cannot recover a step that
is not in the file, and with `LEADS_LIMIT = 10` in the product path it sees 10 rows of 600+.

---

## 2. C1 as built versus what I meant

My review's C1 was: *"for each behaviour-eligible source, enumerate distinct values with count,
host count, first, last, and per-hour cadence for fields whose cardinality is small enough to
review. Sources with a handful of values are then read as a list, which is exhaustive by
construction."* The build is different in six ways, and on `botsv2` the difference is total.

### 2.1 It cannot enumerate the fields it selects — measured

`_value_query` is `| tstats count min(_time) max(_time) where index=… sourcetype=… by <field>`
[code `inventory.py:120-125`]. On this Splunk, a search-time field is not in the `tstats` output
at all: the query returns a single `lastrow` marker and no value column. Live, every one of the 32
selected fields came back `status: empty`, 0 values, 0 joints, 0 flows, in 16 s [live].
Reproduced directly:

```
| tstats count where index=botsv2 sourcetype=stream:http by http_method   -> 0 rows
| tstats count where index=botsv2 sourcetype=wineventlog:security by host -> 18 rows
```

So the mechanism works only for **default/indexed** fields (`host`, `source`, `sourcetype`,
`index`), and the role fields the cards name are search-time extractions. The stage cannot
succeed on wide telemetry as written. `_complete` reports both "the aggregation returned no
rows" and "the rows had no such column" as `empty` [code `inventory.py:152-172`], so the receipt
cannot tell a broken mechanism from a genuinely empty field — which is how this survived a unit
suite and two redesign docs.

### 2.2 It spends the budget on the least informative fields

`select_fields` rejects `variety == "free"` and `distinct > 32`, then sorts ascending by
`distinct` [code `inventory.py:81-117`]. A field with `distinct == 1` is accepted and sorts
first, so on `botsv2` all 32 searches went to **constant action fields** (sample distinct 1):
`stream:http http_method` (its card is partitioned on `accept`, and the 40-line sample holds one
method), `osquery_results action`, `wineventlog:security Authentication Package` [live,
`inventory.json`]. Even with a working aggregation this ordering reaches the
fields that can name an entity (actor/object with tens of values) last, and often never. The
review's instrument had the opposite intent: enumerate the *reviewable* fields, smallest sets
first because they are exhaustive, but never spend the whole budget on fields that cannot carry
an artefact.

### 2.3 It ignores the card partition

Cards can be partitioned on a low-variety field (one card per `event_type`/`http_method`/…) [code
`cards.py:145-147, 690-760`]. `select_fields` keys choices on `(source_id, field)` and merges
cards with `max(distinct)` [code `inventory.py:87-112`]; `_value_query` has no partition
predicate [code `inventory.py:120-125`]. So a partitioned source's list is aggregated across all
parts, and two cards naming the same field collide. The value list does not mean what the card
meant.

### 2.4 "Index-wide first-seen" is exact-match only

`apply_inventory` replaces `first_seen` only when the behaviour's sorted literal pairs equal a
joint key exactly [code `inventory.py:508-533`]; a three-field literal behaviour never matches a
one- or two-field joint. On `botsv2` the receipt is `first_seen_replaced: 0` [live]. My review's
§2 D fix ("make first-seen index-wide and the generator starts reporting novelty") is therefore
not delivered except for the handful of jointed pairs.

### 2.5 The candidate path is a rounding error, not a coverage strategy

Unseen joint rows become candidate `Behaviour`s, capped 8 per source and 32 per index, sorted
newest-first [code `inventory.py:536-576`]. On the wide corpus the newest 32 enumerable pairs are
unlikely to include a 1–12-event artefact (the artefacts measured at index-wide counts of 1, 3, 4
and 12 [live]) — and on `botsv2` the path produced 0 because joints were 0. A blind hunt cannot
bet its coverage on "the 32 newest values".

### 2.6 What C1 did get right

The *shape* is right and reusable: choose fields from the card's roles, run one bounded
aggregation per field, store `{value, events, first_seen, last_seen}` with status, run a joint
only when the product of list sizes is small, and keep flows over normalised values [code
`inventory.py:197-378`]. The failure is the execution primitive and the selection order, not the
data model.

---

## 3. C2 as built versus what I meant

### 3.1 Flows are computed correctly over an empty input

`_flows` groups casefolded values across complete field lists and keeps a value in 2..12 sources,
ordered by first-seen [code `inventory.py:274-312`]. The logic is sound and the guard (`>= 4`
chars, alpha or IPv4) prevents the worst noise. But the lists are empty (§2.1), so `flows = []`,
the relate receipt reports `flows: 0`, `_union_flows` has nothing to union, and every case carries
`transitions: []` [live]. The "only mechanism that sees an ingress→execution transition" is
therefore not yet tested by a run, let alone shown to work.

Two design caveats even once lists exist:

- The flow's source is `(index:sourcetype)`, not a host or an entity. "A value in two sources"
  is a cross-source fact, not a transition on an entity; two unrelated hosts sharing a filename
  create a flow. My review's C2 required a structural source-class pair (ingress vs
  execution/persistence); the build has no source class [code `inventory.py:270-312`].
- `_union_flows` links seeds only when the shared value is already one of the seed's *identity
  pivots* [code `relate.py:634-653`]. A filename that is not an actor/address never links
  anything — which is exactly the entity-less step the case layer was supposed to rescue.

### 3.2 Promotion works, and is the most valuable thing in this lane

Six cases on `botsv2` and nine lifts into the head is a real result on the first live run [live].
The rule (a case already inside `PROMOTE_HEAD = 50` lifts up to 3 weak members, 12 total) [code
`relate.py:42-44, 855-930`] is conservative and auditable. Fixes needed, not replacement:

1. Run order: relate must precede judge everywhere, or promotion must trigger a bounded re-judge
   of the lifted ids (`product_jobs.py:270-281`).
2. Credit: scoreboard must not count a promoted raw line as a finding (§1.5).
3. Coverage: the relate receipt must say what fraction of seeds/entities were read uncapped
   (`coverage_complete=False` today).
4. Duplicate injection: `_weak_members` gives a not-yet-written `relate` row the sentinel position
   `len(rows)+1` [code `relate.py:870-875`], so the "lift" creates a row rather than promoting
   one. That is defensible (the row is the case's evidence), but it means promotion can add
   findings that were never ranked by any generator. If kept, the metric and the UI must say so.

### 3.3 The case is still not the product's unit

`cases` only include components with `len(nodes) > 1` [code `relate.py:678-681`]; a single strong
episode is never a case, and the case has no hypothesis beyond `anchor_entity`, `score`, links and
transitions. The scoreboard scores notables, not cases [code `scoreboard.py` modes]. My review's
claim stands: the case is the product, and it is unmeasured.

---

## 4. F as built — correct, and mis-tiered

`_shape_decision` returns `novel` for a rare shape whose source exceeds the 1 % misfit share,
and `_trim_novel` keeps only the rarest shape of that source [code `misfit.py:28-53`]. The
unit case works live: my run kept the `osquery_warning` `.mkv.crypt` shape (1 of 1,035 lines),
which the stored run had dropped with its source, and it appears at **rank 74** as the
`macbook_file_encryption` carrier — moving that step from unreached to covered-at-@100, not @50
[live]. The gate no longer disqualifies novelty wholesale, which was the point. But:

- It is still a *share gate on a sampled slice*. A source read at 0.1 % whose novel lines are 2 %
  of that slice is still "poorly understood" as a statement about the source.
- Only the single rarest shape survives per novel source. For a mass-encryption step the signal is
  a *set* of novel shapes on one host; one shape is the right unit only by accident.
- `novel_source_trimmed: 779` on my run [live] — i.e. the gate still discards 779 shapes; the
  shape that matters got in, but the mechanism is a lottery on which single shape the rarest is.

Keep the direction; move the gate to parse coverage and report the novel share as a measure.

---

## 5. C0 and C4 as built

### 5.1 C0 works, and it changes the story

The instrument now reports, beside today's recall: which graded keys a read store actually held
(`reachable` ceiling), recall-of-reachable in loose/strict/line mode, a per-step cause
(covered / instrument / not_surfaced / unreached), median first rank, and the read counts behind
line families [code `scoreboard.py:77-100, 559-620, 1075-1140, 1270-1340, 2002-2050`]. It
reproduces the audit's botsv2 ceiling exactly on the stored run (5/24 keys reachable, 5/14 steps,
loose 3/5, strict 2/5) and gives the first honest reading of the build families:

| family | mode | scored @50 | reachable @50 | recall of reachable |
|---|---|---|---|---|
| kyoushi | line | 11/12 | 11/12 | **11/11** |
| santos | line | 18/21 | 12/21 | **11/12** |
| russell | line | 15/22 | 15/22 | **14/15** |
| botsv2 (stored) | entity loose | 3/14 | 5/14 | **3/5** |
| botsv2 (stored) | entity strict | 2/14 | 5/14 | **2/5** |

[live, stored `snap_neon_02cc2e3`]

This is the most important number in the project so far: **on the corpora the tool can nearly
read whole, the ranker is already at the ceiling**. The build-family misses are *unreachable*
lines (`santos/crack_passwords`, `russell/exfiltration-service`), not ranking failures. So C1's
value is not "find more in the sample"; it is "make reachability independent of the sample" —
which is a harder, more valuable and more expensive claim than the one C1 was sold on.

### 5.2 C4 as built reproduces the pathology it was meant to cure

`conditional_weights` divides a generator's covered steps by **the family's total steps**, not by
the generator's own candidate set [code `merge.py:23-49`; `scoreboard.py:2093-2125`]. So a
generator that ranks a genuine step at 51 has weight 0, regardless of how much it contributed.
The measured leaves-one-family-out table on the stored run:

| held out | deviation | misfit | similar_to_known | alerts | peer_rare | relate |
|---|---|---|---|---|---|---|
| all | 48 | **0** | 53 | **0** | **0** | 1 |
| botsv2 | 56 | 0 | 70 | 0 | 0 | 1 |
| kyoushi | 41 | 0 | 45 | 0 | 0 | 1 |
| russell | 50 | 0 | 54 | 0 | 0 | 1 |
| santos | 43 | 0 | 42 | 0 | 0 | 1 |

[live, `--weights`]

Three generators go to zero for reasons that are not "it found nothing": misfit covers 5 steps at
@100 on russell and 0 at @50; alerts has a discovery defect (§1.3); peer_rare's notables mostly
carry no index term in their evidence query (the report's own caveat). The fold variance is
small (41–56 / 42–70), which means this formula is mostly measuring *global rank position*, not
leave-one-family-out generality. The conditional denominator must be `covered / min(existed,
…)` — a generator's own opportunity — or the weight is a cut artefact. This is a P1 fix, and it
is cheap.

### 5.3 The instrument still has blind spots

- Reachability is a post-hoc substring test over the read stores [code `scoreboard.py` REACH_RULE].
  That is a defensible proxy, but it cannot see *why* a value was read (which query, which
  window), so it cannot distinguish "the sampler never touched this source" from "the source was
  read and the value was censored". The run should emit a read ledger (value → source → query →
  window) and the scoreboard should consume it.
- For entity families, line mode needs a keyed-events export that is not produced by any
  committed script [code `scoreboard.py:2183-2190`; docs `SCOREBOARD.md:78-81`]. So the most
  honest mode is unavailable by default.
- Case-level recall does not exist.

---

## 6. What my earlier review got right, and what it got wrong

**Confirmed by the code and the data**

- The read is 0.117–0.118 % of botsv2; the per-source budget is flat (`per_window_events`) [code
  `behaviours.py:585-588`; live: 266,972 / 226,317,740].
- `first_seen` for behaviours is sample-relative and sorted newest-first [code
  `generators.py:728-745`]; C1 corrects it only on exact joint matches, 0 times on botsv2.
- Singletons cannot key a behaviour; novelty is not a candidate class [code
  `behaviours.py:200-276`].
- Misfit treated novel sources as disqualifying; F fixed the unit case, not the gate's meaning
  [code `misfit.py:28-53`; live].
- `relate` was hard-gated to the training indexes; that is gone and the product path no longer
  fails at the case stage on botsv2 [code `relate.py:625-631`; live].
- Weights encode an absence: `alerts 0` [code `merge.py:12-18`], and the alert generator is still
  empty on botsv2 for a different reason.

**Broken by the code**

- I assumed a C1 "list" was one aggregation away. It is not: the fields a card names are
  search-time extractions, so `tstats` cannot aggregate them. The mechanism needs `stats` over a
  scan, or index-time extraction, or a change of which fields are asked. My cost estimate
  (~100–350 searches) priced the requests but not the scan volume of a search-time aggregation;
  that is the real price and it must be decided explicitly.
- I assumed the ranker was a major loss on the build families. It is not: 11/11, 14/15, 11/12 of
  reachable at @50. The loss is reachability. This *strengthens* the C1 direction but moves the
  goalposts: the win condition is coverage, not ranking.
- I called the case layer "unmeasured and hard-gated". The gate is gone and the case layer now
  *changes the head* (9 lifts), which the scoreboard cannot see. It is worse than unmeasured: it
  is measured as if it were not there, and it can inflate the entity mode through raw lines.
- I did not foresee the ordering split between the CLI and the product job, which silently
  discards promotion in production.

**Still open from that review**

- C3 (dominance as a first-class measure) is not built. `peer_rare` measures host-share ×
  actor-share, which on a one-host source ranks the dominant scanner as *not* rare [code
  `generators.py:316-337`]. The scanner IP in botsv2 is 168,004 events and top-2 % by volume.
- The read-slice ledger (S6) is not built; C0 is the post-hoc version of it.

---

## 7. What is sound and should be kept

1. **The estate map** (`index_facts`, cadence, shared source names) — the best part of the tool.
2. **Cards + parse** — structure discovery, partitions, template mining, per-source coverage.
   Fix `kind` semantics, don't replace the mechanism.
3. **The executor** — one budget, one deadline, censored coverage declared on every read, exact
   counts for kept candidates [code `executor.py:1-40`; `generators.py:431-459`]. This is better
   discipline than most commercial tools and it is the hardest thing to rebuild.
4. **Misfit shape mining** (letter/digit shape, no dictionary) and the F direction.
5. **The DuckDB stores and receipts** — `behaviours.duckdb`, `progress.json`, per-source receipt
   with `events_read/events_available`, `share_of_source`, `unparsed_share`. Every future stage
   should keep this standard.
6. **The C0 instrument and the LOFO harness** — the reachability ceiling is the right
   denominator; fix the reachability source (ledger) and add a case metric.
7. **The knowledge store + proof-index gate** — labels may build and tune; the proof sets stay
   closed; `PROOF_INDEXES` raises.
8. **Relate's distinctiveness-by-share and union-find** — the right instinct (dominance, not
   cross-host rarity), and cases do form on a wide corpus.

---

## 8. Where the implementation diverges from how a hunter works (ranked by cost)

| # | Divergence | Evidence | Cost |
|---|---|---|---|
| 1 | **Sample first, localise never.** Reads are uniform slices sized by source count; the estate is never asked where the rare thing is. | `behaviours.py:585-588`; `sample.py:256-300`; 8/24 keys reachable on botsv2 | the four unreached steps |
| 2 | **Value enumeration does not work.** C1 cannot aggregate the fields it selects; 0 values on botsv2. | §2.1 [live] | C1's entire claim |
| 3 | **No entity episode.** The unit is a per-source vocabulary row; sequence and transition are erased. | `behaviours.py:635-658` | the three "reached, not surfaced" steps |
| 4 | **Alert ingestion reads the wrong stream and needs the wrong field.** Detections are `activity`; the one alert card has no roles. | §1.3 [live] `alerts existed=0` | the cheapest lead in the estate |
| 5 | **Novelty is measured in the sample, and only partly corrected.** | `generators.py:699-745`; `inventory.py:508-533`; 0 replacements live | the generator's whole meaning |
| 6 | **The case layer is applied after the judge in production and injected raw text is unlabelled.** | `product_jobs.py:270-281`; `relate.py:581` | the one mechanism for entity-less steps |
| 7 | **Weights reward cut position, not contribution.** | §5.2 [live] | three generators at 0 |
| 8 | **Dominance is not measured where it can be decided.** | `generators.py:316-337` | the wide-corpus scanner |
| 9 | **Misfit still gates on the sample's share.** | `misfit.py:28-53` | novel-source lead, 779 shapes trimmed |
| 10 | **The judge sees 10 rows in the product path.** | `product_jobs.py:47, 296` | triage, not detection |

---

## 9. Measured baseline (what the next lanes must beat)

Stored run `snap_neon_02cc2e3` (pre-C1/C2/F, `similar_to_known` on), scored with the C0
instrument [live]:

| family | mode | @50 | @100 | all | reachable steps | recall of reachable @50 | causes |
|---|---|---|---|---|---|---|---|
| botsv2 | entity loose | 3/14 | 3/14 | 3/14 | 5/14 (B+P 5/11) | 3/5 | covered 2, instrument 1, not_surfaced 2, unreached 9 |
| botsv2 | entity strict | 2/14 | 2/14 | 2/14 | — | 2/5 | — |
| kyoushi | line | 11/12 | 11/12 | 11/12 | 11/12 | 11/11 | — |
| santos | line | 18/21 | 18/21 | 20/21 | 12/21 | 11/12 | — |
| russell | line | 15/22 | 17/22 | 17/22 | 15/22 | 14/15 | — |

Current-code probe (this lane, `botsv2`, cards reused from the stored run, `similar_to_known`
omitted, C1/F/relate active) [live]:

| mode | @50 | @100 | all | reachable steps | recall of reachable @50 | causes |
|---|---|---|---|---|---|---|
| entity loose | 3/14 | 4/14 | 4/14 | 8/14 (B+P 6/11) | 3/8 | covered 2, instrument 1, not_surfaced 5, unreached 6 |
| entity strict | 2/14 | 2/14 | 2/14 | — | 2/8 | — |

Reads: 266,972 events / 226,317,740 (0.118 %), 21,770 behaviours, 1,176 misfit shapes kept 33,
604 merged notables (608 after relate promotion) versus 890 in the stored run that included
`similar_to_known`, 6 cases, 9 lifts, 4 raw relate rows in the top 12.
Index-wide counts for the graded artefacts (whole-term `tstats`): `eidk.duckdns.org` 12,
`berkbeer.com` 4, `Frothly…pptx.crypt` 1, `mberk@berkbeer.com` 3, `45.77.65.211` 168,004,
`member.php` 16,429, `updatexml` 1,139. At 0.118 % read, a 1–12-event needle is seen 0.1–1.4 %
of the time by construction [live + arithmetic].

---

## 10. What "blind" still means, and whether the code keeps it

No generator names a value, extension, domain, protocol or dataset. Fields are chosen from card
roles and statistics; shapes are letter/digit classes; flows are value-in-≥2-sources; the
knowledge store is built from labels on *other* indexes and refuses proof indexes. The one
dataset-shaped thing left is the **source-kind taxonomy** (`activity/alert/measurement/other`),
which is a format judgement and is not dataset-specific. `similar_to_known` is label-trained, which
the brief permits ("labels may build and tune"), and its reliability is reported honestly
(0.904 / 0.443 / 0.418) [code `knowledge.py`, `similar.py`; docs `GENERATOR_WEIGHTS_REPORT.md`
§4]. Blindness is intact; the problem is coverage, not cheating.

The *evaluation* is the weaker link: three `su`-chain Linux families are one telemetry class, and
the only wide corpus is botsv2. As my earlier review said, LOFO across these three is one fold in
disguise; that has not changed and no amount of code will fix it. The plan therefore states the
generality claim as unproven and keeps the held-out sets for the end.

---

## 11. The one-sentence account of each stage a hunter would give

- **Cards**: good — you have mapped the estate; now use the map.
- **Behaviours**: you read a 0.12 % sample and turned each source into a vocabulary. You have not
  read the estate, and you have thrown away order.
- **Generators**: you rank five flavours of "unlike its own source" and never ask "who is doing
  something across sources, and what did they touch".
- **Merge**: you allocate slots by a weight that measures where a generator's best hit landed,
  not whether it found anything.
- **Relate**: the right idea (entity episodes, dominance) running on 40 seeds with a capped read;
  the cases it forms are real and the promotion works, but production judges first and then adds
  unjudged rows, and the flow half has no input.
- **Judge**: a binary triage of ten rows; keep it for ordering, never for proof.
- **Scoreboard**: the reachability ceiling is the best thing in the repo; it just showed that the
  ranker is not the problem.

---

## 12. Receipts (commands run in this session)

All Splunk reads were read-only against `https://10.0.1.30:8089`, credentials exported from the
live checkout's `.env` by name (`LAB_SPLUNK_USER`, `LAB_SPLUNK_PASSWORD`, `LAB_SPLUNK_URL`);
`.env` was never sourced. Training families only.

```bash
# 1. reproduce the stored-run score with the C0/C4 instrument
uv run python -m portal.modules.security.core.hunt.notables.scoreboard \
  --out /Volumes/data01/portal5_hunt/snap_neon_02cc2e3/results/hunt/neon \
  --keys botsv2=/Volumes/data01/portal5_hunt/corpora/botsv2_keys/keys.jsonl \
  --keys kyoushi=/Volumes/data01/portal5_hunt/corpora/hunt_bed/kyoushi_s1_ingest/keys.jsonl \
  --keys santos=/Volumes/data01/portal5_hunt/corpora/ait_lds_v21/santos_ingest/keys.jsonl \
  --keys russell=/Volumes/data01/portal5_hunt/corpora/ait_lds_v21/russellmitchell_ingest/keys.jsonl \
  --weights
# -> botsv2 ceiling keys 5/24, steps 5/14, loose 3/5 strict 2/5; kyoushi 11/11, russell 14/15,
#    santos 11/12 recall-of-reachable; C4 folds all 48/0/53/0/0

# 2. field aggregation is impossible for search-time fields (the C1 defect)
#    | tstats count where index=botsv2 sourcetype=stream:http by http_method   -> 0 rows
#    | tstats count where index=botsv2 sourcetype=wineventlog:security by host -> 18 rows

# 3. run the current code's behaviours stage on botsv2 (cards reused from the stored run)
uv run python -m portal.modules.security.core.hunt.notables \
  --index botsv2 --out coding_task/scratch/live-run/botsv2 --stage behaviours
# -> events_read=266972 existed=21770 misfit_shapes=1176 wall=206.874s
# -> inventory: searches 32, values 0, joints 0, flows 0, fields {'empty': 32}

# 4. notables stage (similar_to_known omitted: no embedder in this probe)
uv run python -m portal.modules.security.core.hunt.notables \
  --index botsv2 --out coding_task/scratch/live-run/botsv2 --stage notables \
  --generators alerts,peer_rare,deviation,misfit
# -> alerts existed=0; inventory {'first_seen_replaced': 0, 'candidates': 0, 'flows': 0};
#    total 604

# 5. relate stage
uv run python -m portal.modules.security.core.hunt.notables.relate \
  --out coding_task/scratch/live-run/botsv2
# -> seeds=40 requests=48 related_events=479 cases=6 coverage_complete=False
#    promotion lifted=9; 4 relate rows at positions 2,3,10,11 of notables.jsonl

# 6. score the current-code probe
uv run python -m portal.modules.security.core.hunt.notables.scoreboard \
  --out coding_task/scratch/live-run \
  --keys botsv2=/Volumes/data01/portal5_hunt/corpora/botsv2_keys/keys.jsonl --weights
# -> loose 3/14 @50, 4/14 @100; strict 2/14; reachable steps 8/14 (B+P 6/11);
#    recall-of-reachable loose 3/8, strict 2/8

# 7. index-wide counts for graded artefacts (whole-term tstats on botsv2 only)
#    eidk.duckdns.org 12; berkbeer.com 4; ...pptx.crypt 1; mberk@berkbeer.com 3;
#    45.77.65.211 168004; member.php 16429; updatexml 1139
```

Artifacts: `coding_task/scratch/score-c0c4-snap2cc2e3.txt`, `coding_task/scratch/live-score.json`,
`coding_task/scratch/live-run/botsv2/{progress.json,notables.jsonl,inventory.json,relate.json}`.
The probe's cards come from the stored run (`sources.json`, copied), so its card receipts are not
new evidence; every other number in this document is from the new run or the stored store.

---

## 13. Unproven / limits of this review

- **Only one wide corpus and three build families were exercised.** No held-out set was read.
  Generality across telemetry classes remains unproven; a single unseen corpus cannot prove it.
- **The current-code botsv2 probe is not a like-for-like baseline.** It reuses the stored cards,
  omits `similar_to_known` (no embedder in the probe), and its sampler landed on a slightly
  different read set (266,972 vs 259,900 events). Compare shapes, not the exact counts.
- **C1/C2 were never measured on the build families.** Their `tstats` defect is proven only on
  botsv2. The same failure is expected wherever the card's role fields are search-time
  extractions, but that was not run on kyoushi/santos/russell.
- **The C0 reachability rule is a proxy** (substring over stores). It cannot distinguish "not
  sampled" from "censored"; the read-ledger proposal is unbuilt.
- **Case quality is not judged.** 6 cases formed on botsv2; whether they are *good* cases is a
  hunter's read of `relate.json`, not a number, and I did not grade them.
- **Cost of a real enumeration is estimated, not measured.** A search-time `stats` over a 55.5M
  event source was not run; the scan volume is the open question in the plan.
- One `| tstats count where index=* by index` listed all indexes, including the three held-out
  names, before I narrowed to the training families. Only event counts were returned; no rows,
  keys or content from a held-out index were read, and no decision uses those counts.
- The judge, `rerank.py`, `stage2.py` and `investigate.py` were read only for their interface and
  placement in the pipeline; their internals are not reviewed here. `manifest.py`,
  `window_activity.py` and `knowledge.py` loaders likewise.
