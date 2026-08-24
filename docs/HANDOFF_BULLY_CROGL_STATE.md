# HANDOFF — Bully / Crogl, state as of 2026-08-21

**Repo HEAD at time of writing:** `TASK_BULLY_HUNT_SWEEP_V1` H.0–H.4 and H.6 are
landed on top of K.5 (`0868ef33`); H.5 (the actual 27-entry sweep run) has not.
See `docs/DESIGN_BULLY_HUNT_SWEEP_V1.md` for the errata on
`BULLY_SCORER_FEED_RUN_K4_V1.md`: **K.4's loop is valid and was deliberately
narrowed to one entry; its claim numbers describe that one six-event proof, not
the corpus.** A live-calibration pass (against the real lab Splunk, not mocked)
also surfaced and fixed a real defect in H.2's own `_anchor_for`: it fell back to
`rng.earliest` for every entry lacking a hand-curated `confirmed_at` (all 27),
so every hunt window landed at the SAME instant regardless of technique.
`_resolve_anchor_time` (one term search per entry) fixes it; live-verified on
T1558.004/botsv3: 9 records/14 units at the old index-earliest window vs 36,640
records/537 units at the corrected, entity-resolved window. H.1's calibration on
that corrected entry (10m span) returned **`COMMIT`, projected 0.19h across 27
entries** — well under the 4h budget. The sweep
(`docs/BULLY_HUNT_SWEEP_RUN_H5_V1.md`, run separately once preflight/calibration
commit — see `TASK_BULLY_HUNT_SWEEP_V1` H.5 for the exact command) is what widens
that proof to all 27 answer-key entries. §2.1a below (F.4's result) still
supersedes the "never assembled" framing further down this document.

> **READ THIS FIRST.** If `git log` at HEAD is beyond `bf35d192`, **HEAD wins over
> every statement in this document.** This captures where things stood on
> 2026-08-21. Anything since then supersedes it. **Code walks are required** —
> do not act on any claim here without re-reading the relevant module and the
> most recent run docs. Several findings below were only discovered by reading
> code that contradicted its own docstrings and by running things that
> contradicted their own reports.

---

## 1. The product, in one paragraph

A universal, source-agnostic security data reviewer that finds **things that are
not known but are same-or-similar to something known**, and raises them to an
analyst for verification. Known-bad matching is the **floor** — it is easy and
solved; if a thing is defined we can find it. The product is everything else.
The analyst's verdict (something / nothing / unsure) becomes knowledge, both
directions, so the system **matures** rather than being tuned. It must work on
universal data — hundreds of source types with varying levels of information —
or it is just another definition-matching engine.

### The four pieces, and their honest status

| piece | the claim | status at `bf35d192` |
|---|---|---|
| **Crogl** | the universal reviewer that ingests any source | proven on **40 invented schemas**; on real BOTS reached only **2 sourcetypes**, `cross_schema_fraction 0.25`. **The actual claim is unproven.** |
| **Bully** | the hunt loop finding same/similar | proven **mechanically**; `reach_recall 0.0` on the real BOTSv3 chain, `max_reached_distance 0`. **Never run on a haystack big enough for "needle" to mean anything.** |
| **The corpus** | the real ground: 281,069,416 events with published answer keys | connected, but best-ever run touched **0.076%**. Effectively **unused**. |
| **The generator** | cousins *of what is known to be in the corpus*, injected *into* it | produced **everything** — haystack and needles both. Now in-range, but planted **at the anchor**, so recovery measures planting position (`zero_hop_only: true`). |

**These four bullets are one sentence repeated four times: proven in a proxy,
never on the real thing.** Every diagnosis in this arc eventually reduced to it.

---

## 2. Where things actually stand

### 2.1 The decisive finding (most recent, and the reason for the next task)

Counted from the repo, not inferred:

```
ten run scripts, sixteen modules, NEVER MORE THAN 7/16 USED TOGETHER
```

`bully_analyst_loop_run` uses 7. `bully_investigation_run_a6` uses 6 — a
**different** 6. Every task in this arc built a module, proved it against a
hand-made fixture, wired it into a *new* run script that dropped half the
previous one, and back-loaded a token run as the last phase.

**The system exists as sixteen proven parts and zero assembled wholes.**

Scale, against 281,069,416 available records:

| run | processed | fraction |
|---|---|---|
| `INVESTIGATION_RUN_I6` | 213,311 | 0.076% |
| `REAL_TELEMETRY_RUN_T3` | 79,999 | 0.028% |
| `ADAPTIVE_REACH_RUN_A6` | 67,545 | 0.024% |
| `CORPUS_BED_RUN_C6` | 19,999 | 0.007% |
| six other runs | 2,000–3,500 | ~0.001% |

Six runs processed 2,000 records — the same number as before the corpus was ever
connected.

**Conclusion: we do not yet know which of the sixteen modules work, because none
has been tested on the real thing at real scale.**

### 2.2 The pending task file (written, not yet executed)

`TASK_BULLY_FULL_ASSEMBLY_V1.md` — assemble and run, **no new modules**:

- one run script wiring all sixteen
- load BOTS answer keys at scale (hundreds published; arc used 1–4)
- run with **no record / timeline / wall-clock cap** — hours or days expected
- report against the four claims with numbers from that run
- `full_pipeline.py` harness **refuses** any stage naming a module outside the
  sixteen (verified: raises), and a failing stage is **DEGRADED, run continues**

Floors it enforces: `integration_fraction >= 0.8` (prior best 0.44),
`corpus_fraction >= 0.10` (prior best 0.00076). Every historical run grades
`PARTIAL_ASSEMBLY` under it.

### 2.3 Written but deliberately NOT landed

`window_survey.py` — stratified real search (`| dedup n sourcetype`) + bare-term
pivot, to break entity-discovery circularity. **Held back on purpose**: landing
it before the assembled run would be the fifteenth iteration of
build-before-run. If the assembled run shows entity discovery is the binding
constraint, that is the evidence for landing it — with data, not argument.

---

## 3. The corpus and the lab

- **Lane A — BOTS v1/v2/v3**, indexes `botsv1` / `botsv2` / `botsv3`, installed
  via `scripts/lab_bots_install.py`. **281,069,416 records total**
  (botsv2 226.3M, botsv1 33.4M, portal5_lab 19.3M, botsv3 2.03M). Published
  answer keys. `answer_key_visibility: scorer_only` in
  `config/security_corpus.yaml`.
- **Index time ranges (discovered live, verified):** botsv1 Aug 2016,
  botsv2 Aug 2017, botsv3 **20 Aug 2018 – Sep 2019** (BOTSv3's scenario is a
  single day, activity 0900–1600).
- **Lane B** — ATT&CK corpora over HEC into `portal5_lab`.
- **Lane C** — Caldera / Atomic Red Team, **unlabelled**. Per the project's own
  wiki: Lanes A and B are pre-labelled and therefore *"useless for discovery
  work"*; **Lane C is the only source of genuine novelty.**
- **Lab**: agent-controlled via MCP (`proxmox`, `execute_bash` against
  `$LAB_TARGET_DC`/`$LAB_TARGET_SRV`), real tooling (impacket, netexec,
  certipy). Requires `LAB_SPLUNK_PASSWORD` sourced into the run environment —
  it lives in `.env` and was once absent from the shell, producing a silent
  fallback.

**BOTSv3 scenario shape (matters for chain reach):** Taedonggang vs Frothly.
Stages cross `aws:cloudtrail` (IAM abuse → `null_admin`, public
`frothlywebcode` bucket), `symantec:ep:*` (Monero miner), Windows endpoints,
VPN, Linux. **The stages share no identifier** — `web_admin` and `BSTOLL-L` are
different entities in one incident. Entity resolution cannot link them; only a
pivot chain can.

---

## 4. The sixteen modules

| module | what it does | proven? |
|---|---|---|
| `field_roles` | infer ENTITY/TIMESTAMP/ACTION from value behaviour, no name lists | 82% extraction on **40 never-seen schemas** |
| `correlation` | entity resolution + cross-source timelines | stitched one identity across 4 sources |
| `artifact_graph` | structural gradeable units (L1–L4) | 209 units from 126 artifacts |
| `baseline` | environment-relative rarity, fit from observed data never the library | works when fit/score levels match |
| `discovery` | data-intrinsic discovery + cousins among observations | attack cluster ranked #1 with an **empty library** |
| `behavior_inference` | behaviour classes **inferred**, unnamed (`ib-0`…) | 4 schemas, disjoint names, `cross_schema_fraction 1.0`, incl. a never-seen schema |
| `series_cousin` | cousinhood by ordered sequence alignment | insertion→COUSIN, reorder→NOVEL, single-log→NONE |
| `pyramid` | Pyramid-of-Pain level + robustness | cross-vocab cousin at L3 robustness 1.0 |
| `investigation_pivot` | anchor → bidirectional bounded expansion → recursive pivot | reconstructed BOTSv3 chain in 7 queries, `reach_recall 1.0` **in probe** |
| `adaptive_scope` | narrow-on-saturation, depth budget, distance recovery | budget spread across depths; I.6 re-measured `zero_hop_only` |
| `telemetry_behavior` | curated sourcetype→behaviour table (**validation instrument only**) | 13/13 on synthetic; **0% field-level on real** |
| `corpus_bed` | lane binding, cousin planning, floor/product/cost | D.4's numbers → `is_haystack False` |
| `analyst_loop` | 3-way verdict, write-back both ways, maturation | 25% quieter cycle-2 on identical telemetry |
| `unit_outcome` | outcome resolution | **currently library-first** (see §6) |
| `loop_grader` | maps grade → `CousinAssessment` loop contract | cross-vocab → SIMILAR at L3 |
| `inject_plane` | generate / inject / capture / seal | live lab verified, real tooling ran |

---

## 5. What works (verified, keep)

1. **`field_roles`** — universal extraction from value behaviour. The single
   most reusable thing built. **Fix that mattered:** recognise a *cohesive
   identifier column* by template-consistency at **any** cardinality (a busy
   source legitimately has hundreds of distinct hosts). Took 42% → 82%.
2. **Bare-term pivot** — `"<value>" OR host="<value>"`, in `live_connect`,
   **live-verified**. Splunk's segmenter indexes raw text, so searching a
   *value* finds it in any field of any sourcetype. **This is the universal
   reviewer's real mechanism.** Verified: `45.77.65.211` reachable across three
   sourcetypes under three different field names.
3. **Bounded time-scoped queries** — 950 rec/sec vs 53 for the old
   `earliest=0 | head N` scan. **18× gain.**
4. **Entity resolution on real data** — `entities_per_record 0.299`,
   **22.8% cross-source entities**. Real, and impossible on the synthetic
   universe.
5. **`SCATTER` cousin recovery 4/4** on real data — the cross-source
   transformation.
6. **`discovery` / `behavior_inference`** — data-intrinsic, library-free, work
   on never-seen schemas.
7. **`analyst_loop`** — 3-way verdicts, both answers written back, suppression
   via `BENIGN_CLOSE`, maturation demonstrated.
8. **The guards** — `truth_acceptance`, `scoreboard_conformance`, `corpus_bed`
   bed report. They now catch real failures and grade historical runs correctly.

---

## 6. What does not work (open defects at HEAD)

1. **Entity-discovery circularity (the binding constraint).**
   `investigation_pivot` extracts pivot candidates only from rows *already
   selected by an entity filter*. So it can only reach entities that literally
   co-appear in the anchor's own records. Causes: `n_entities` 1–2,
   `cross_schema_fraction 0.25`, `max_reached_distance 0`, `reach_recall 0.0`.
   Fix written (`window_survey`), deliberately not landed.
2. **`unit_outcome.resolve_unit_outcome` is library-first.** It consults the
   anchor library and only falls back to the baseline when nothing matched — a
   signature database with an anomaly fallback. Whichever way the library leans
   decides 100% of outcomes.
3. **`telemetry_behavior` field-level mappings are 0% on real data.**
   Sourcetype-level mappings hit 100% (`stream:dns`, `suricata`, `WinRegistry`);
   field-level hit 0% (`wineventlog:security` **0/85**) because `EventCode` is
   **not a top-level key** on captured Windows records — it lives in `_raw`.
4. **`suricata → evade` supplied 44.8% of all classified behaviour** from one
   sourcetype. Entropy (2.28 bits) passed it; concentration checks were the
   missing guard.
5. **Learned classifier prior-collapse.** With zero seen trigrams, naive Bayes
   reduces to `argmax(prior)` and `_MIN_CONFIDENCE` gates on the *prior*, so
   unrecognisable real verbs take the majority class (`collect`, 95.8%).
6. **Cousins planted at the anchor** → `zero_hop_only: true`. Recovery measures
   planting position, not reach.
7. **`floor_known_recall 0.0`** — the system has never recovered a documented
   BOTS technique.

---

## 7. Lessons learned — what NOT to do

These were each paid for with a wasted run. **Do not repeat them.**

### 7.1 Never let a fixed constant decide the answer
Every arbitrary limit became the finding:

| constant | what it decided |
|---|---|
| `--capture-limit 2000` | which records were ever seen |
| `--max-timelines 25` | the entire outcome distribution |
| `head 20000` | truncated 226M events to 20k |
| `MAX_EVENTS 20000` | consumed by query **one** → pivot ran **zero** times |
| `TARGET_MAX_ROWS 500` | pivot ran but starved — 1,265 events total |
| `MIN_CONFIDENCE 0.35` | gated on the class prior → majority-class labels |

**And note the trap:** replacing a flat cap with a "smarter" band reproduces the
bug at a smaller scale. Scope by **entity yield to plateau**, not row count.
Saturation is a signal to **narrow**, not to stop.

### 7.2 Never trust a metric whose name differs from its mechanism
Six runs, six different metrics, one invariant — **the headline was structurally
incapable of showing failure**:

- `confidence` was schema-presence **mass** (3 constants across 100 seeds)
- `scored` meant **reachability**, not correctness
- `precision 1.0` on a population with **no negatives**
- `anomalous_rate 0.0` while `ANOMALOUS_UNCLASSIFIED = 71`
- `absolute_recall 1.0` because misses weren't counted
- `discovery_bubbled_rate 0.88` rewarding **emission**, 0 confirmed
- `unknown_cousin_recall 0.973` — 75% of it was `NOVEL`, which never consults
  the library
- `learned_coverage 0.963` on synthetic tokens that **embed their own label**

### 7.3 Never assume the system uses the module you just read
Four layers of bypass, each found by reading the *caller*, not the module:

1. reporting layer bypassed `scoreboard` (published a block named `scoreboard`
   sharing **zero fields** with `scoreboard.update()`)
2. run scripts bypassed the orchestrator (`run_hunt_iteration` is **tests-only**)
3. the grading call bypassed the series engine (`relation.relate` still in use)
4. the compounding loop bypassed the reform pipeline entirely

**Verifying a component is correct is not evidence the system uses it.**
Import-scan it.

### 7.4 Never grep when you should read
Every serious misdiagnosis in this arc came from grepping for a hypothesis:
- "the scoreboard rewards bubbling" — **false**; trust axis existed all along
- "the classifier is the root cause" — **false**; the run had swapped graders
- "segmentation is the root cause" — true in principle, not what produced the
  numbers

### 7.5 Never let the generator make both the haystack and the needles
X.6's `implant_class_ground_truth` was `background` for **all 300** rows — 100%
false positives, 0% true positives, and it passed every acceptance check because
`both_classes_notified` compared the grader **against itself**.

### 7.6 Never inject needles outside the corpus's time range
Cousins shipped with "now" (2026) timestamps against a 2016–2018 corpus.
**Provably unreachable** by any time-bounded investigation.

### 7.7 Do not build a definition matcher
The pull toward a curated table is constant, because it is always the cheapest
fix. A table is a definition matcher. Curated mappings and answer keys are
**scorer-plane only** — they may measure, name and validate. **No discovery path
may consult them.**

### 7.8 `tstats` is a speed tool for indexed metadata, not a truth tool
Splunk docs: tstats *"operate[s] only on indexed terms stored in tsidx files,
not on `_raw` event data"*; non-indexed fields need data models or index-time
extraction. In BOTS, `user` / `src_ip` / `EventCode` are **search-time
extractions**.
- **Legitimate** (shipped, keep): `| tstats min(_time) max(_time) where index=X`
  in `inject_plane.discover_index_range` — `_time`/`index` are indexed.
- **Forbidden**: `tstats ... BY user, src_ip` — returns **silently incomplete
  results that look complete**.
- **Recommended guard:** CI check that no `tstats` has a `BY` clause naming a
  non-indexed identity field.

### 7.9 Assemble before building
Fourteen task files, each front-loading construction and back-loading a token
run. **No seventeenth module until the sixteen have run together on the corpus.**

---

## 8. How defenders actually work (research-grounded; the design must obey this)

- **The anchor is where you start searching, not where the incident started.**
  Incidents surface at the symptom stage; investigators work **backward** from
  visible damage to initial access.
- **Expansion is bidirectional and asymmetric** — reaches further backward than
  forward. Documented pattern: all operations by that user in the **preceding
  24 hours**, and in the **superseding 1 hour**.
- **Pivoting is recursive across entities** — IP → process → parent process →
  user → login time; each query's results feed the next. **This is what links
  stages sharing no identifier.**
- **An investigation is bounded work.** Nobody reads all the logs.
- **Dwell time** — ~14 days median, 122+ for espionage. BOTS compresses this to
  a single day, which is *why it is testable*. Backward reach is a **per-corpus
  parameter**, never a constant.

---

## 9. Working agreements

- **Fresh clone every session.** `git log` at HEAD is ground truth. Memory,
  summaries and stale docs all lose to HEAD.
- **Task files are self-contained**, agent does all writes, full heredoc
  payloads with collision-checked sentinels, four-backtick fences when bodies
  contain code fences.
- **Verify every `str_replace` anchor is unique (`count == 1`) against live
  HEAD** before shipping. Note: `pyramid.py`'s `_BEHAVIOR_TABLE` is
  ruff-formatted into multi-line tuples — single-line replaces **silently
  no-op**.
- **AST-validate every embedded Python payload**, and re-extract it from the
  finished file and re-run it before shipping.
- **Prose edits made after the payload block are not in the payload.**
  `MIN_SCORED_UNITS` was specified in prose after the heredoc and **never
  landed**, which is why C.6 scored 200 units against a 10,000 floor.
- **Adjacent broken things travel with the work.**
- `PROMOTE_POLICY: confirm` — nothing auto-promotes.
- **Honest-BLOCKED over faked-green.** Report what happened.

---

## 10. What to do next

1. **Execute `TASK_BULLY_FULL_ASSEMBLY_V1`.** Assemble all sixteen, load answer
   keys at scale, run uncapped on the full corpus. Expect it to break — a break
   at 40M records is worth more than fourteen clean runs at 2,000. **Fix in
   place, do not open a new task.**
2. **Read the assembled run against the four claims**, not against the last
   run's defects.
3. **Then**, and only with data: land `window_survey` if entity discovery proves
   binding; invert `unit_outcome` to discovery-first; parse `_raw` for Windows
   EventCodes; retire whichever of the sixteen proves redundant.
4. **Add the `tstats` boundary guard** (§7.8) so the finding survives.

### Open questions genuinely unresolved

- Does the assembled system find anything on real data? **Unknown.**
- Which of the sixteen earn their place? **Unknown** — built without
  integration feedback, overlap likely (`telemetry_behavior` vs
  `behavior_inference`, `adaptive_scope` vs survey scoping).
- Can it scale? 53–950 rec/sec observed; 281M records is 4–61 days at those
  rates. **Throughput is an open engineering question.**
- Does discovery work on *genuine* novelty? Lanes A/B are pre-labelled and
  cannot answer this. **Only Lane C can**, and it has not been used.

---

## 11. Reference

**Key paths**
- modules: `portal/modules/security/core/bully/` (86 files)
- runs: `docs/BULLY_*_RUN_*.{md,json}` (13)
- designs: `docs/DESIGN_BULLY_*.md` (12)
- corpus config: `config/security_corpus.yaml`
- BOTS installer: `scripts/lab_bots_install.py`
- corpus wiki: `portal_wiki/canonical/unit-corpus-injection-*`

**Pending task files (written, not executed)**
- `TASK_BULLY_FULL_ASSEMBLY_V1.md` — **execute this next**
- `TASK_BULLY_WINDOW_SURVEY_V1.md` — hold until the assembly runs

**Withdrawn (do not execute)**
- `TASK_BULLY_VERDICT_INTEGRITY_V1` — would have added a 4th scoring path
  beside a correct 3-axis one
- `TASK_BULLY_SERIES_COMPOUNDING_V1` — closed a real gap *around* the signature
  architecture
- the `tstats`-census design inside the window-census draft
