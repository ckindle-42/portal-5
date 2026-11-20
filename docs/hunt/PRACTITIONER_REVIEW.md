# A practitioner's review of the R2 hunt — properties and method

Scope: a working threat hunter's answer to four questions about the blind hunt
(`cards → behaviours → generators → ranked notables → relate → judge`) over an index it has
never seen. **No Splunk search was run and no event data was accessed for this review.** Every
number below is quoted from a committed document or read out of the code; every claim carries
its source class:

- **[code]** — read directly in the module named (`file:line`).
- **[audit]** — `docs/hunt/INSTRUMENT_AUDIT_BOTSV2.md` (2026-11-19). That file is committed on
  `lane/hunt-instrument-audit` (commit `9ef9297f8`) and is **not on `main`**; it was read with
  `git show 9ef9297f8:docs/hunt/INSTRUMENT_AUDIT_BOTSV2.md`. (An untracked, byte-identical copy
  appeared in this shared checkout while the review was being written — `shasum`
  `3ea7b780…c564` both ways — and is left untracked for its own lane.)
- **[docs]** — `BOTSV2_DIAGNOSIS.md`, `GENERATOR_WEIGHTS_REPORT.md`, `MISFIT_REPORT.md`,
  `RELATE_LINKAGE_REPORT.md`, `OPEN_PROBLEM_*`.
- **[judgement]** — my opinion as a hunter, reasoned but not measured here.

One correction to the brief's framing, because the arithmetic below depends on it: the audit
measured **226,317,740** events in 104 sourcetypes (twice, with `| tstats count where
index=botsv2`), and **266,058** is what the run *read* [audit]. This review uses 226.3M as
the index and 0.117 % as the read fraction.

---

## 0. The standard I am holding the pipeline to

A hunt is not a sample. It is a **search over the estate for a small number of entities that
have done something nobody can explain**, and the artefact of a hunt is a case: an ordered
account of what an entity did, across sources, that a human can accept or reject. Three
properties follow, and they are the yardstick for everything below:

1. **Coverage is a property of the question, not of the budget.** A source is worth reading
   because of what it can *decide* (did a process run? did a user authenticate? did a file
   leave?), not because it holds events.
2. **Localise before you read.** Full-index aggregation tells you *where* and *when*; raw
   reads answer *what*. Sampling before localising measures the background, not the attack.
3. **A step is a transition.** The unit of evidence is (entity, ordered events, bounded
   window), not (source, value-class, whole-run aggregate).

Today's instrument is **source-centric**: per-source read budget [code
`notables/behaviours.py:585-588`], per-source behaviours, per-source misfit shapes, and five
generators that never join two sources [code `notables/generators.py`, `notables/misfit.py`,
`notables/similar.py`]. A hunter is **entity-centric**. That is the single largest structural
divergence in this review, and most of the findings below are instances of it.

---

## 1. Q1 — how a skilled hunter works an unfamiliar 104-sourcetype, 226M-event index blind

### 1.1 Map the estate before reading a single row

The first hour is aggregations, not events. In this order, because each one bounds the next:

| # | Aggregation | The question it answers |
|---|---|---|
| 1 | `tstats count min(_time) max(_time) by sourcetype host` | Who is in the estate, how big is each population, when did each source start and stop? Gaps and brand-new sources are findings in themselves. |
| 2 | `tstats count by sourcetype _time span=1h` | Cadence: which sources are mechanical (flat), which are human-paced (business hours), which are bursty by nature (auth storms, batch jobs). A 4-hour bucket is a *choice* about cadence, and the estate must tell you whether it is right. |
| 3 | field coverage per source (which fields exist, `dc(field)`) | What can this source be asked? A source whose only fields are `from`/`to` cannot name an actor; a source with 166 half-empty XML attributes is wide but shallow. |
| 4 | value inventory for low-cardinality fields (`stats count min(_time) max(_time) by <field>`) | The list of processes, filenames, attachments, services, registry paths, domains, user agents. When a field has 6 distinct values you read **all of them**, and recall stops being probabilistic. |
| 5 | top-k entity volume per source (top-1 share, top-decile share) | Who dominates each source. The attack entity is often the dominant one, not the rare one (99.5 % of one build access log's requests; the wide-corpus scanner sits in the top 2 % by volume; see §2 E). |
| 6 | first-seen per entity across the whole index (`stats min(_time) by value`) | Index-wide novelty. This is the only defensible meaning of "new" — novelty measured inside a read slice is a sampling artefact (§2 D). |
| 7 | execution/auth inventories: parent→child process pairs, user×logon-type, session/terminal | The two chains an intrusion actually travels: privilege and process lineage. |
| 8 | per-entity hourly cadence for the top ~100 entities | Beacon periodicity, dwell time, and "this entity is behaving unlike itself" — at a time scale the hunter chooses, not one baked into the bucket width. |

Nothing here returns raw events, and all of it is cheap relative to a raw read: 1 and 2 are
one `tstats` each; 3 is one aggregation per source; 4 is one aggregation per (source, field) but
returns only a value list. **The pipeline already does 1 and 2** (and does them well — [code
`notables/sample.py:183-236`, `notables/generators.py:552-567`]). It uses the index elsewhere
only to **count individual candidates it has already chosen** (`exact_counts`, `_exact_count`
[code `generators.py:431-459`]) — never to enumerate values, and never to establish index-wide
first-seen. It does not do 3–6 at the estate level at all. In one sentence: **the pipeline knows
how to ask the index for an exact count; it has never asked it for an exact list.**

### 1.2 Decide where to read deeply — selectivity × consequence

A hunter allocates raw reads by two factors multiplied together, not by source size:

- **Selectivity**: can "unusual" even be decided in this source? A source with 2 hosts and 200
  distinct values gives a hard yes/no per value. A source with 55M events and millions of keys
  gives a noisy ranking until you aggregate first.
- **Consequence**: does the source witness a human or machine *decision*? Authentication,
  process execution, file write, mail/transfer ingress, egress (DNS, proxy, TLS), persistence
  writes. These are the sources that can name a step. Performance counters, bulk OS inventory
  and registry churn mostly cannot.

Practical consequences, all general:

- **Read the small sources whole.** 47K events, 1.5K FTP events, a 4-line error log: these are
  the sources where a human-scale decision leaves one line, and reading them exhaustively
  costs almost nothing. (Existing direction, right one: [docs `OPEN_PROBLEM_hunt-open-astra.md`].)
- **Aggregate the big ones, then read a slice chosen by the aggregation.** Never the newest
  events of equal time slices — that is a background survey, and it concentrates reads on the
  tail of each slice, which is exactly where an on-the-hour batch job lives [code
  `sample.py:256-300`].
- **Cluster sources by evidentiary role, not by name.** The pipeline's `kind`
  (`activity/alert/measurement/other` [code `notables/cards.py:34`]) is a format judgement. A
  hunter's taxonomy is: does this source name a host and a user, and can it witness a
  transition (ingress→execute→persist→egress)? Sources that name neither host nor user cannot
  carry a step and should not consume ranking slots.

### 1.3 The first ten queries, generically

```
| tstats count min(_time) max(_time) by sourcetype host
| tstats count by sourcetype _time span=1h
index=X sourcetype=Y | stats dc(<field>) as d | where d<=50000            # candidate fields
index=X sourcetype=Y | stats count min(_time) max(_time) dc(host) by <field> | sort -count
index=X sourcetype=Y | stats min(_time) as first by <entity> | sort -first   # index-wide novelty
index=X sourcetype=Y | stats sum(<bytes>) by <src>,<dst> | sort -sum        # dominance/egress
index=X sourcetype=Y | stats count by <parent>,<child>                      # execution lineage
index=X sourcetype=Y | stats count by <user>,<logon_type>,<src_ip>          # auth shape
index=X sourcetype=Y | stats earliest(_time) latest(_time) by <source-file> # gaps/new sources
index=X | stats count by sourcetype | sort -count                           # budget sanity
```

The ordering matters: query 1–2 defines the estate, 3–4 defines what any source can be asked,
5–8 defines the candidate entities, and only then does a raw read have a hypothesis attached to
it.

### 1.4 What the pipeline already gets right

- The metadata stage is genuinely full-index and understands shared source names, cadence and
  host populations [code `sample.py:183-236`; docs `OPEN_PROBLEM_hunt-open-astra.md`].
- Misfit shape mining is a real hunter's instinct: structure is learned, novelty is surfaced,
  and no dictionary is involved [code `notables/behaviours.py:182-189`, `notables/misfit.py`].
- Exact whole-index counts for kept candidates, and declared coverage/censoring on every read
  [code `executor.py`, `generators.py:462-505`] — this is better discipline than most commercial
  tools.
- LOFO selection instead of per-corpus tuning is the right *form* of discipline, even where the
  folds are weak (§2 H).

---

## 2. Q2 — where the pipeline diverges, and which assumptions a hunter would reject

Ordered by how much recall each costs, on the audit's own accounting (11 misses: 3 "reached but
not surfaced", 3 "design limit", 3 "keys", 2 "instrument" [audit]).

### A. Sampling first — the 0.117 % read

**Assumption.** A uniform slice of the index is a fair miniature of it, so ranking the slice
ranks the index.

**What the code does.** 400,000 parsed events are divided by the number of behaviour-eligible
sources, then by 12 windows, capped at 2,500 per window [code `behaviours.py:44-45`,
`behaviours.py:585-588`]. With 85 eligible sources that is ~392 events per window, ~5.2k lines
per source **regardless of whether the source holds 47 thousand or 55 million events** — which
is exactly the flat 5,152 median the audit measured [audit].

**What the measurement says.** 0.117 % of the index read; 94.7 % of all events sit in sources
read at under 0.5 % [audit]. Under uniform reads a 20-event step has a 2.3 % chance of being
seen at all [audit]. The scanner IP in `access_combined` has 4,854 index-wide events and the
slice held **zero** of them [docs `BOTSV2_DIAGNOSIS.md`].

**A hunter's objection.** Uniform sampling is a *census of the background*, not a search. It is
defensible when the index is small enough that sampling ≈ reading (the build families read
2.5–3.3 % of 5–6M events; that is 150k events, i.e. they are nearly exhaustive) [audit]. The
method's validity does not transfer to 226M events; the measured collapse is the method failing,
not the budget being small. **Aggregate to localise, then read the localised slice
exhaustively.** That is not "more budget"; it is a different use of the same budget (§4 C1).

### B. The budget is flat per source, not weighted by evidentiary value

**Assumption.** All sources deserve the same read share.

**What the code does.** `per_window_events(sources)` divides the total by the source count
[code `behaviours.py:585-588`]; the only filter is "behaviour-eligible" (has roles).

**Why a hunter rejects it.** The 55M-event registry churn source and the 47K-event EDR/query
source get the same 5.2k lines. One can decide "a run key appeared on this host for the first
time"; the other is a haystack where a 4-event key is invisible at 0.0095 % coverage [audit].
Budget should follow (a) whether the source can name an entity, (b) how many distinct entities
it has, (c) how much of it is human-paced. A source with 2 hosts and 200 values is *readable*;
a source with millions of values is not, and should be *aggregated*.

### C. The behaviour unit is a vocabulary item, not an episode — and rarity is filtered out before ranking

**Assumption.** `(source, actor, action, object)` aggregated over the whole run is the unit of
behaviour.

**What the code does.** `identity_stats` defines an *identity* as `distinct >= 2` **and**
`recurrence >= 2.0` **and** `bucket_share >= 0.5` **and** `distinct <= 2000` [code
`behaviours.py:229-234`]. Any field that fails is wildcarded to `"*"` in the behaviour key
[code `behaviours.py:192-197`, `256-261`]. So **a value seen once — the single new registry key,
the one-off encrypted file, the twice-seen DDNS name — is structurally excluded from being an
identity at all**, and survives only in an example raw line.

**Why a hunter rejects it.** Two separate problems:

1. *The singleton is the first thing a hunter looks at.* It is also 10,134 of 17,928 behaviours
   (57 %) [audit] — so the honest conclusion is not "key singletons", it is "**route singletons
   to an enumeration stage instead of discarding them**". Today they are neither ranked nor
   listed; they are wildcarded.
2. *The aggregate erases sequence.* `45.77.65.211 did TRAFFIC to ssl` as one row with 2,452
   sampled events in a bucket [docs `OPEN_PROBLEM_hunt-open-kimi.md`] is simultaneously the
   strongest and least informative summary available: the row does not say that this actor
   produced 168,004 events index-wide, nor which objects it touched, because the object is
   wildcarded and the events are summed. A hunter wants the ordered slice, the distinct objects,
   and the transition into the next behaviour.

The measured consequence is the haystack: 876 notables, 10,134 singleton behaviours, and a rank
cut that five generators divide by global weight [audit; code `merge.py:12-18`].

### D. "First seen" means first seen *in the sample*, not in the index

**Assumption.** `deviation/behaviour_first_seen` reports novelty.

**What the code does.** `_behaviour_first_notable` measures `behaviour.first_seen -
index_start` [code `generators.py:699-716`], and `_behaviour_deviations` sorts candidates
**newest-first** before cutting [code `generators.py:736`]. `first_seen` is computed from the
sampled rows in the read windows, not from the index.

**What the measurement says.** `access_combined` took 6 of 7 top-50 `behaviour_first_seen`
slots with final-minute timestamps [docs `OPEN_PROBLEM_hunt-open-neon.md`] — i.e. the generator
ranked the *tail of the last read window*, which is a property of the sampler.

**Why a hunter rejects it.** "New" is a fact about the estate (`min(_time)` over the whole
index for that value), and it is one aggregation away (§1.1 #6). A novelty generator that
measures the sample's edge will always be dominated by whatever the window boundary cuts, and
it is weighted 26 into the merged head [code `merge.py:12-18`]. This is the cheapest real
detection win available: make first-seen index-wide, and the generator starts reporting
"this value has never been seen on this host before" instead of "this value appeared late in my
slice".

### E. Anomaly-only framing, and no measure of dominance

**Assumption.** The attack is the deviation: rare, unusual, unlike its source's history.

**What the data says.** In the build corpora the attacker can be the **dominant** entity: one
access log is 99.5 % attacker requests (406,469 of 408,395) and the attacker is the only client
with its user agent [docs `RELATE_LINKAGE_REPORT.md` §1]. In the wide index the scanner IP is
in the **top 2 % by volume** and 94.8 %/96.6 % of DNS values are as rare or rarer than the
beacon [audit]. Both of the pipeline's rarity-shaped signals therefore point the wrong way:
`peer_rare` = host-share × actor-share ranks a 1-host source's dominant IP as *not* peer-rare
[code `generators.py:316-337`; docs `BOTSV2_DIAGNOSIS.md` cause 3], and count-rarity in DNS
does not isolate a beacon [audit].

**Why a hunter rejects it.** A hunter runs **both** tails and treats them as different
hypotheses: the *one-off* (new process, new filename, new registry key — enumeration, §4 C1)
and the *dominant* (top talker, top scanner, top egress — aggregation, §4 C3). The pipeline's
five generators are three variants of the first tail (`deviation`, `misfit`, `peer_rare`), one
similarity-to-labelled-store measure, and `alerts` — weighted **0** [code `merge.py:12-18`].
Dominance is only measured at sourcetype granularity (`source_burst`), which is the one
granularity at which it is not actionable.

### F. Novelty treated as disqualification (`MISFIT_MAX_SHARE`)

**Assumption.** A source whose read slice is >1 % structurally novel is "poorly understood" and
should be dropped.

**What the code does.** `generate_misfit` skips *every* shape from a source when
`misfit_lines / lines_read > 0.01`, where both numbers come from the **read slice** [code
`misfit.py:15`, `52-53`]. The botvs2 run dropped 1,042 of 1,299 shapes this way and lost the
source that carried an artefact it had already read [docs `BOTSV2_DIAGNOSIS.md` cause 4; audit].

**Why a hunter rejects it.** That gate inverts the meaning of the signal. A source that is 13 %
structurally unseen is the *most* interesting source in the estate, not the least — it is either
a format the model failed to learn (a bug) or a place where new things are happening (a lead).
The correct gate is on **parse coverage** ("can I explain 90 % of this source?"), with the novel
share carried as the *measure* and a per-source shape cap for cost. Dropping the source throws
away both the bug and the lead.

### G. Notables-then-relate, and a case layer that cannot run blind

**Assumption.** Rank first; build cases from the head; that is enough.

**What the code does.** `relate` takes at most 40 notables as seeds [code `relate.py:36`], pulls
≤20 rows per identity query [code `relate.py:38`], union-finds seeds into cases, and writes
`relate.json`. Three structural facts:

1. **It is hard-gated to the three training indexes**
   (`TRAINING_INDEXES = {kyoushi, santos, russellmitchell}`), and `relate_stage` raises
   `ValueError` on anything else [code `relate.py:40`, `752-755`].
2. The **product path appends `relate` unconditionally** to `cards, behaviours, notables,
   [judge], relate` [code `product_jobs.py:46`, `281`], and the outer handler turns any
   exception into a failed job [code `product_jobs.py:442-447`]. So on a genuinely unseen index
   the product hunt **does all its work and then fails at the case stage**.
3. The scoreboard scores **notables**, not cases. A case can never promote a weak member into
   the head, and the case layer is unmeasured.

**Why a hunter rejects it.** The case *is* the product. And the report that motivated the
current design already showed that a pure entity pivot cannot reach the entity-less quiet step
(one line, no timestamp, no user, no IP) — the only link was *host + source file* [docs
`RELATE_LINKAGE_REPORT.md` §4]. That is not an argument against cases; it is an argument that
**case membership is evidence in its own right**: if a case is strong (an upload, a privilege
transition, an egress burst on the same host), its weak members should inherit enough of that
strength to enter the head. That is the mechanism that surfaces an artefact with no entity, and
it needs no pivot at all.

Also fatal to the "blind" claim: a training-index gate is a dataset dependency in the one place
the tool is supposed to be universal. It is a policy gate, not a technical one — the code below
it is generic.

### H. The evaluation itself, which a hunter would reject first

This is where I am bluntest, because the numbers above are all filtered through it.

- **The keys are partly not huntable.** Of 15 steps, 3 are trivia (a Unix-epoch cookie value,
  an executive's e-mail address, a competitor domain), 1 is a duplicate key (the same IP scores
  two steps), and 6 more are partly trivia (filenames, a zip password, a hash) [audit]. A blind
  behaviour hunt is being asked to surface a value that collides with every epoch in the corpus.
- **The pass bar is inflated and deflated at the same time.** 2 of the 4 credited passes come
  from a single incidental evidence line in an unrelated notable; a strict scorer gives 2/15
  [audit]. Meanwhile the families' own rule credits steps whose labelled lines were **never
  read** (4 santos steps at @50 with zero labelled lines read) [audit]. So @50 is not a recall
  measure across corpora; it is two different measures wearing one name.
- **The reachability ceiling is the right denominator.** 11 of 15 steps had at least one key
  string somewhere in what the run read; 8 in the behaviour event table; 4 had nothing [audit].
  Reporting "4 of 15" without the ceiling conflates sampler failure with ranker failure. Report
  **recall of reachable** and the ceiling itself as a first-class number.
- **LOFO over three families is one fold, not three.** All three build families are Linux/syslog,
  5–6M events, 33–64 sources, and share an authoring process — the same `www-data → su <user> →
  sudo` escalation appears in two of them [docs `RELATE_LINKAGE_REPORT.md` §1–2]. Constants
  selected on that basis transfer because the telemetry class is held constant, not because the
  method is general. The first evidence of this is in the audit's own table: russell puts 52 %
  of its events in sources read at <0.5 %, kyoushi and santos 0 % [audit] — the families already
  disagree about the property the sampler depends on, and nobody noticed because the step counts
  were similar.
  **Honest statement today: generality across *wide* telemetry is unproven, and one unseen
  corpus cannot prove it either.**
- **The weights encode one absence as a global law.** `alerts` and `peer_rare` are 0 because
  they covered no step in two families where the alert part was never even discovered
  (`alerts existed=0` on a corpus holding 10,457 detections) [docs `GENERATOR_WEIGHTS_REPORT.md`
  §3]. Weight 0 from a measurement bug is not a measurement. `similar_to_known` is at chance on
  two of three families (AUC 0.443 / 0.418) [same report §4] yet carries the largest weight (31).
  A conditional weight — *this generator's measured coverage among runs where it had
  candidates* — is the honest form.

---

## 3. Q3 — the "reached but not surfaced" steps: what a hunter would have keyed on

The audit assigns three misses to "reached, not surfaced": a removable-media delivery, a
document exfiltration visible only as a misfit shape, and a mail attachment that was read four
times [audit; docs `BOTSV2_DIAGNOSIS.md`]. In all three the data was *in the read slice* and the
instrument did not turn it into a ranked, entity-bearing finding. The general signals, in the
order a hunter would reach for them:

### S1 — Cross-source value flow (the strongest missing signal in the tool)

A file name, hash, domain, URL, or user that appears in an **ingress** source and later in an
**endpoint/execution** source is a transition, and the pipeline has no generator that can see
it: every generator is within one source [code `generators.py`, `misfit.py`, `similar.py`].

- *Generic realisation:* join the value inventories (§4 C1) and the behaviour store on the
  normalised value (casefold, basename, extension class, IP), require ≥2 sources, require at
  least one source whose structure is an ingress (message/attachment field, transfer record,
  web request) and one that is execution/persistence (process, file write, registry), and bound
  the window by the value's own first→last span.
- *Why it fixes the class of miss:* the delivery step, the attachment step and the exfiltration
  step are all "the same value in two places". None of them requires the value to be *rare*.
- *Status:* [judgement] on the mechanism; the absence of any cross-source join is [code].

### S2 — Field depth: a structured event is its fields, not its first 2,400 characters

A mail event of 40 KB with the attachment name at character 178 and the password at 12,735
[audit] is not an event you sample; it is an event you *parse*. The generic property: when a
source is structured (JSON, KV, XML, CSV), the decisive value has a **name**, and the name is
what to key on. A raw prefix cap converts a fielded record into a lossy text sample, and the
loss is silent.

- *Generic realisation:* for structured formats, promote parsed fields into the behaviour/entity
  layer (the cards stage already parses them [code `parse.py`]); keep raw prefixes for
  unstructured lines only; report per-source "value-bearing depth" so a cap that hides a field
  is visible in the receipt.
- *Status:* the 2,400-char cap and the offset measurement are [audit]; the general rule is
  [judgement].

### S3 — Set-level file-class anomaly per host

A single encrypted file is not interesting; **N distinct files sharing a novel extension class
written on one host inside one hour** is the generic shape of a mass-encryption or staging step,
and it is robust to renaming, to which extension it is, and to the count being small.

- *Generic realisation:* derive a class token from the extension/format (no whitelist — the
  class is whatever the host had not written before), and score per host: distinct values in
  the class, first-seen of the class on that host, entropy of names. This is "novelty of a
  *set*" rather than "rarity of a value", and it is exactly the kind of measure that survives a
  new corpus.
- *Why it fixes the class of miss:* the exfiltration artefact reached the misfit store as one
  shape and was then dropped with its whole source; a per-host class count would have carried
  it independently of the misfit gate (§2 F).
- *Status:* [judgement]; card/parse support exists [code `parse.py`, `cards.py`].

### S4 — Novelty as evidence, never as disqualification

This is S1–S3's shared precondition. A source that is 13 % structurally unseen is a lead, and
the instrument should say so with a number ("this source produced 137 shapes seen nowhere else
in the estate, 2 of them on a single host"), not drop it [code `misfit.py:52-53`]. A hunter
reads the novel-shape list *first* on an unfamiliar index — it is how you find the format you
did not know existed.

### S5 — Ingress → execute adjacency on one host, even without a shared value

Mail/transfer/media event on host H at *t*, then a process or file event on H within minutes,
where H rarely executes anything from that path. The *sequence* is the signal; the shared value
is a bonus. This needs an ordered per-host timeline (episode), which the aggregate behaviour
unit cannot express (§2 C). It is also the only generic route to the delivery step when the
file name was never re-used.

### S6 — The read-slice ledger (governance signal, and the one that finds this class of miss *during* a run)

Every distinctive value read — new in the window, low count, in a role-bearing field — is a
candidate. Emit, per run, the list of candidates that did **not** reach the head, with the
reason (dropped by generator, below the cut, wildcarded as non-identity). That is the audit's own
"reached but not surfaced" category, computed by the pipeline instead of by a reviewer weeks
later, and it turns selection bias into a rate: **recall of the read**. It is also the cheapest
possible change — a ledger over data already in `behaviours.duckdb`.

---

## 4. Q4 — design changes, in priority order

Ranked by (recall gained × generality) / risk. Each carries the property it adds, how to measure
it LOFO, its cost, and the condition under which it is unfit.

### C0 — Fix the instrument before tuning the detector (zero cost, do first)

- **Property:** every later number is comparable.
  - Dedupe shared keys (one IP is one step, not two); grade steps B/P/T and report B+P
    separately; report the reachability ceiling and **recall of reachable**; run the strict
    (what/basis/why/entities) and line-mode scores side by side; fold `source=` case
    [audit §2].
  - Replace the undifferentiated @50 with: steps @50 among reachable B+P steps, plus scenario
    coverage, plus median rank of the first covering notable.
  - Emit the **read-slice ledger** from §3 S6: every distinctive value read that reached no
    notable, with the reason (dropped by generator, below the cut, wildcarded as non-identity).
    That is the pipeline measuring its own selection bias instead of a reviewer doing it.
- **LOFO measurement:** re-score every stored run. Pass = the new numbers reproduce the audit's
  (6/7 line-mode, 2/15 strict, ceiling 11). No detector change is accepted on the old metric.
- **Cost:** no Splunk. A scoring script change.
- **Unfit if:** it is used to *raise* the absolute bar ("N of 15") rather than to report
  fractions honestly.

### C1 — Full-index value inventory, before any sampling (P0)

- **Property:** a needle only has to be a *value in a low-cardinality field*, not a *sampled
  event*. For each behaviour-eligible source, enumerate distinct values with count, host count,
  first, last, and per-hour cadence for fields whose cardinality is small enough to review.
  Sources with a handful of values are then **read as a list**, which is exhaustive by
  construction.
- **What it adds:** index-wide first-seen (§2 D) for free; the value lists that the
  mail-attachment and transfer steps live in, and the field-level substrate S2/S3 need; and the
  end of the 0.117 % dependence for list-valued fields. It is not a universal fix — the
  removable-media step is a field-depth case (S2), and the two registry-carried steps that were
  never reached need a parsed class token, not a value list.
- **LOFO measurement:**
  1. *Field discovery* (the real risk): does the stage discover the artefact-bearing field from
     structure alone? Test per fold: build the inventory on two families, ask whether the third
     family's labelled artefact values appear in it. Bar: the field is discovered, not named.
  2. *Ranking:* new notables from the inventory, measured @50 / reachable; bar = no fold
     regresses and the pooled build-family sum rises.
  3. *No-op test:* on the two families used to build it, the notables produced by the existing
     generators must be unchanged (ordering included).
- **Cost (estimate, not measured here):** one aggregation search per (source, field class);
  ~1–4 per behaviour-eligible source, so **~100–350 searches**, returning only aggregate rows.
  That is *fewer requests* than the current behaviour stage (85 sources × 24 requests ≈ 2,040
  [docs `OPEN_PROBLEM_hunt-open-neon.md`]) but each scans a whole source, so budget ~2–4
  full-index passes: hours of index time on 226M events, not minutes. Structured sources can be
  parsed in-search (`spath`/`kv`); unstructured ones need a `rex` per source and are the slow
  tail. Treat it as the replacement for a share of the raw-read budget, not an addition.
- **Unfit if:** it names the fields to inventory (that is a dataset-specific list) or enumerates
  a high-cardinality field (bounded by `dc`, which is itself an aggregation).

### C2 — Cross-source value flow + case-level promotion (P0)

- **Property:** a step is a transition. Emit chain notables when a normalised value crosses
  source boundaries (ingress→execution, execution→egress, user→process), bounded by the value's
  own span; and let a strong case promote its weak members into the head (this is what makes an
  entity-less quiet line rankable).
- **LOFO measurement:** marginal steps gained per fold from chain notables alone; the
  promotion rule's effect on @50 and on the *rank of the first covering notable* for steps whose
  carrier is a weak member; regression test on the other two folds. Build families have real
  chains to measure (upload → `su`/`sudo`; download → crack → egress), so no wide corpus is
  needed for selection.
- **Cost:** the join is over stores already on disk — **0 new searches**. One bounded reachback
  (`| head 20`) per surviving chain, ~50–100 chains, to attach adjacent lines. Deduplicate
  chains aggressively; the risk is combinatorial value×source explosion, so require ≥2 sources
  and a source-class pair.
- **Unfit if:** the chain rules name protocols, extensions or suffixes. The classes must be
  structural (has a message/file field; has a parent/child field).

### C3 — Dominance as a first-class measure, and conditional weights (P1)

- **Property:** the attack is often the *dominant* entity, and dominance is measurable exactly
  where rarity fails: top-k share per source, entity volume against its peer group, egress
  volume asymmetry, distinct-object count per entity. Emit these as notables with a peer group
  (same source, same host role) so a backup job does not outrank a scanner.
- **Why it is general:** the build families contain a dominant attacker entity (99.5 % of one
  access log's requests [docs `RELATE_LINKAGE_REPORT.md`]) and the wide corpus's scanner sits in
  the top 2 % by volume [audit], so the constant can be selected LOFO on the families alone.
- **LOFO measurement:** steps gained at @50 by dominance notables; false-positive count per run
  (dominance notables that are mechanical sources — should be suppressible by cadence); no
  regression.
- **Cost:** near zero — derivable from `events`/`behaviours` and the existing 4-hour series.
- **Unfit if:** the peer group is a hardcoded host list or a per-source threshold.

### C4 — Conditional generator weights (P1, paired with C3)

- **Property:** a generator's weight reflects its measured coverage **where it had candidates**
  (`alerts existed > 0`), and a generator that has never been exercised on a telemetry class
  keeps a unit weight rather than inheriting 0 [cf. code `merge.py:19`].
- **LOFO measurement:** re-run the weight selection with the conditional denominator and with the
  alert-discovery bug fixed; report both. Bar: pooled @50 ≥ current, with `alerts` weight > 0
  only in runs where the alert stream exists.
- **Cost:** zero.
- **Unfit if:** it becomes per-corpus weights.

### C5 — Read-whole tier, field-aware depth, multi-scale buckets (P1)

- **Property:** read *all* of a source when reading all of it is cheaper than sampling it (small
  sources), keep structured events whole enough that named fields survive (no 2,400-char
  cliff), and evaluate bursts at a **ladder** of scales (5 min / 1 h / 4 h) rather than one
  bucket width — a 20-minute campaign is invisible at 4 h, and a 4-hour bucket is a cadence
  guess about the estate.
- **LOFO measurement:** small sources' read fraction (should be 1.00) and steps whose carrier is
  small; regression on the families for the bucket ladder (a scale is added only if it does not
  reduce pooled @50); receipt field for value-bearing depth.
- **Cost:** reallocation, not more budget — small sources cost a handful of searches; the ladder
  adds 2 series per scale over one source×time grid.
- **Unfit if:** the scales are fitted to a known campaign's duration.

### C6 — Remove the training-index gate; score the case layer (P2)

- **Property:** the tool is universal where it claims to be. Delete the `TRAINING_INDEXES` gate
  [code `relate.py:40`, `752-755`], and add a case-level metric (case contains a labelled step,
  case rank @k) so the case layer stops being unmeasured. Keep relate's current within-source
  share ranking — it is already the dominance signal C3 formalises.
- **LOFO measurement:** family case recall @k plus notable recall unchanged; on the unseen corpus
  the run must reach COMPLETE rather than fail at the relate stage.
- **Cost:** zero searches; it is a policy deletion.
- **Unfit if:** "training index" is load-bearing for a *data* reason (it is not — nothing below
  line 755 depends on family labels).

### What I would **not** build (unfit — needs dataset-specific knowledge)

- Any rule keyed to a literal value, extension, suffix, filename, hash, cookie, or password:
  e.g. "encrypted extension", "dynamic-DNS provider list", the zip password, the epoch cookie.
  These improve one scoreboard row and teach the tool nothing.
- Thresholds transplanted from three small Linux corpora as if they were laws:
  `MISFIT_MAX_SHARE = 1 %`, `MIN_PARTITION_DISTANCE = 0.18`, burst allowance 2, a 4-hour bucket.
  Keep them only if a *second telemetry class* agrees, not a fourth syslog corpus.
- An imported rule/signature feed. Note the distinction: consuming the index's **own** alert
  events is not a signature — it is the estate's own judgement and the cheapest lead there is;
  weighting it 0 because two families never discovered their alerts is a measurement artefact,
  not a finding [docs `GENERATOR_WEIGHTS_REPORT.md` §3].
- "More budget" as a standalone change. At 0.117 % a 4× budget is still sampling; at family
  coverage (2.5 %) you would read 5.7M events and still miss a 12-event needle 74 % of the time
  [reasoned from the audit's 1-(1-f)^n]. The budget is not the lever; the *order* is.

### One falsifiable prediction, so the plan can fail honestly

If C1 + C2 land as described, the **reachable ceiling** on the unseen corpus should rise from
11/15 in two steps, and the accounting is testable:

- **12/15 from the value inventory alone** — one of the four unreached steps is carried by a
  field that is enumerable as a list (a DNS query field with 34,194 distinct values [audit §4]),
  so it becomes reachable as soon as the field is discovered from structure.
- **14/15 if the parsed registry class token is also built** — two more unreached steps live in a
  55M-event registry source where no value list is reviewable; only a per-host path/name *shape*
  can carry them.
- **The fourth stays unreachable by design** — its key is one of the three trivia keys (a value
  that collides with every other one of its kind), and it should be removed from the
  denominator rather than counted as a detector failure.

Steps at @50 among reachable B+P should reach ≥8 with no build-family fold regressing. If the
ceiling does not rise, the failure is in **field discovery** (or in the registry class token),
not in ranking — and that is the finding to report, not a reason to raise the read budget.

---

## RESULT

The instrument's binding constraint is no longer the ranker: 11 of 15 steps were in what the run
read and only 4 were credited, so 7 of the 11 misses are instrument, keys or surfacing rather
than coverage. But the deeper divergence is structural: the hunt is **source-centric and
anomaly-only**, while the estate's attacks are **entity-centric transitions**, often *dominant*
rather than rare. Uniform per-source sampling at 0.117 %, sample-relative "first seen", wildcarding
every singleton identity, and a misfit gate that discards a source *because* it is novel are four
independent ways the same mistake is made: rarity is treated as the search space, so the rarest
thing in the estate — a two-event artefact — is the least likely to be represented. The case
layer, the one mechanism that could carry an entity-less step, is hard-gated to the training
indexes and is never scored.

Three properties are worth more than any threshold: (1) aggregate first — enumerate low-cardinality
value lists over the whole index, because a needle in a list needs no sampling; (2) transitions,
not aggregates — join values across sources and promote a strong case's weak members; (3) measure
honestly — reachable ceiling, recall of reachable, deduped non-trivia keys, and a conditional
weight for a generator with no candidates.

## TOP 3 CHANGES

1. **C1 — full-index value inventory for low-cardinality fields, before sampling.** Makes the
   enumerable unreached step reachable and gives the value lists the three "reached but not
   surfaced" steps live in, plus index-wide first-seen for free; ~100–350 aggregation searches
   (fewer requests than today's behaviour stage, more scan volume). LOFO bar: field discovered
   from structure, artefact values present, no fold regression.
2. **C2 — cross-source value-flow chains plus case-level promotion.** The only mechanism that
   sees an ingress→execution transition and the only way an entity-less quiet line can reach the
   head; zero new searches (joins over stores already written). LOFO bar: marginal steps per
   fold, rank of first covering notable, no regression.
3. **C0 + C4 — honest measurement and conditional weights.** Deduped, graded keys; reachable
   ceiling and recall-of-reachable; strict and line-mode side by side; weight a generator by its
   coverage *where it had candidates*. Zero cost, and without it none of the above can be
   demonstrated — today's 4/15 is 2/15 strict and 6/15 by the families' own rule, which is not a
   measurement a design should be tuned against.

## UNPROVEN

- Every number here is quoted from a committed document or is a code reading; **I ran no query
  and read no event data**, so no figure has been re-measured in this review.
- The audit's per-step cause assignment, B/P/T classes and line-mode scores are its author's
  judgement, quoted as such.
- The cost estimates for C1 (~100–350 searches, 2–4 full-index passes, hours) are arithmetic on
  the audit's event counts and source count, **not** a bench. Index scan rate on this lab host is
  unknown to me.
- The prediction in §4 — ceiling 11 → 12 from the value inventory, 14 with a parsed registry
  class token, and ≥8 of reachable B+P at @50 — is reasoned from the audit's carrier table and
  its field-cardinality probes; it is untested and could fail on field discovery.
- C2/C3/S3 are design judgements from a hunter's practice; I have not shown that any of them
  emits a notable on these corpora, and the chain/class rules I propose are structural sketches,
  not specifications.
- I did not review the judge, the embedding store's construction, or the `investigate.py` /
  `observations.py` path; findings are confined to `notables/*` and its docs.
- The statement that the three build families share an authoring process rests on the identical
  `www-data → su → sudo` chain and the identical Apache/webshell shape in two of them [docs], not
  on provenance.
