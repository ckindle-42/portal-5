# ONE_REGULATORY_EXTRACTION_V1 — the graph and the corpus, finally joined

Base `4631a269`. Every number below is from a live query or a live run on this
machine. `reports/compliance/requirement_anchor_rates.json` holds the raw
per-standard, per-relation census including every unanchored requirement by
name, and `ONE_REGULATORY_EXTRACTION_V1_measurements.json` the §4.1 latency
sweep and the §4.2 recall re-run; the embedder ran at `:8942` throughout.

---

## §0 — The finding, verified by execution

Both halves of the original ask were built. Neither could do its job, because
they shared no key.

| | verified |
| --- | --- |
| the graph | `nerc_cip_register.json`: **255 requirement nodes**, 14 standards, **255/255 carrying `verbatim_text`**, 101 with `measure_text`, 202 with `applicable_systems`. Node id is literally `CIP-007-6 R2 Part 2.2`. |
| the corpus | `source_sections`: total-cover fidelity capture, three properties asserted by `fidelity_report` and **enforced by `assert_faithful`, which raises**. |
| the join | `'section_id' in RegisterNode` → **False**. `'revision_id' in RegisterNode` → **False**. `source_sections` carries **no requirement reference of any kind**. |

The only overlap was `source_pdf` + `source_pages` — page granularity, where a
page holds many sections and a Part spans pages. So *"the sections constituting
R2 Part 2.2"* was not a question this store could answer, and everything
unexplained for weeks follows from that one absence. `reading_assembly`
gathered by heading-path proximity because proximity was the only option
available. `resolve_governing_bundle` re-parsed the PDF at call time to obtain
text for an identity it already held.

**One correction to §0's premise, on the record.** §0 said the reading path was
confined to *3 of 36* documents. The live store says something more specific
and more useful: **13 of the Register's 14 standards were already in
`document_revisions` with matching content hashes**, and every one had
`source_sections` rows — but written by `pymupdf` with `char_start = -1`.
Structure with no coordinate space. They were not missing; they were
unprojectable and unanchorable, which looks identical from the reading path and
is a different problem to fix. All 14 PDFs were on disk and all 14 sha-verified
against the Register on the first try.

---

## §1 — The anchor

The Register carries each requirement's exact `verbatim_text`.
`document_texts.full_text` is the captured revision's character space with a
byte-exact reconstruction guarantee, and every section carries
`char_start`/`char_end` in it. Locate the verbatim text by exact match; the
sections whose half-open span overlaps the located range **are** that
requirement's sections.

Nothing is fuzzy, anywhere. A text that does not occur is `UNANCHORED` with a
named reason, never approximated — a fuzzy match produces citations that look
correct, cannot be checked afterwards, and get built on.

### 1.1 The substitutions, and the test each had to pass

`_SUBSTITUTIONS` is a closed list of rendering artefacts between two readers.
An addition is **mechanical, not a judgment**: re-run with and without the
candidate and require (a) zero change to any already-anchored range and (b) at
least one `UNANCHORED` converted. Five candidates were tested. Three were
admitted; two were rejected by the rule, and the rejections are the evidence
that the rule works.

| candidate | ranges changed | anchors lost | converted | verdict |
| --- | --- | --- | --- | --- |
| `U+F0B7 → "-"` — Symbol-font bullet in the PUA; docling keeps the codepoint, pymupdf renders the glyph as `-` | 0 | 0 | 9 | **ACCEPT** |
| `'"' → "'"` — the same typographic double quote; pymupdf gives U+201C/U+201D, docling gives ASCII `'` | 0 | 0 | 7 | **ACCEPT** |
| `U+2022 → ""` — a list bullet docling folds into structure (`list_item`) and drops | 0 | 0 | 7 | **ACCEPT** |
| `" - " → " "` — the Register's heading/body cell join | **14** | **14** | 17 | **REJECT** |
| `"- " → "-"` — the `(CIP- 010)` line-break artefact | **23** | **23** | 1 | **REJECT** |
| `" i. " → " "` — a roman-numeral list marker docling drops | 0 | 0 | **0** | **REJECT** |

The two rejections are the interesting ones. Each would have *raised* a
headline rate — the dash candidate takes `applicable_systems` from 177 to 190 —
while breaking 14 and 23 anchors that were already exact. That is the rule
catching a text edit dressed as a rendering reconciliation, which is precisely
what it exists for. The third converted nothing and earned nothing.

---

## §2 — The corpus, completed

`scripts/capture_register_standards.py --verify-sha --all`: **14 of 14
captured**, each sha-verified against the Register's recorded digest, each
passing `assert_faithful` at **100.0% character coverage, no gaps, no overlaps,
no missing pages, clean reconstruction**. A sha mismatch would have been a STOP
for that document; none occurred.

`store_capture` scopes its rebuild to the capture's own extractor, so the
existing `pymupdf` and `regulatory-bundle/1` sections were left exactly where
they were. `source_sections` went from 3,660 to 7,477 — all 3,817 new rows are
`docling` captures of documents that previously had no coordinate space.

---

## §3 — The join, per standard and per relation

`scripts/anchor_requirements.py --all --report`. Rates are stated per relation
because the relations are not equally costly to lose: an unanchored `governing`
requirement is one the reading path cannot retrieve at all; an unanchored
`measure` is a smaller loss, and one blended rate would hide the difference.

| standard | nodes | governing | measure | applicable_systems | TB sections | GTB section |
| --- | --- | --- | --- | --- | --- | --- |
| `CIP-002-5.1a` | 33 | 30/33 | — | 1/26 | 93 | present |
| `CIP-003-8` | 39 | 37/39 | — | 35/35 | 138 | present |
| `CIP-003-9` | 44 | 42/44 | — | 40/40 | 0 | absent |
| `CIP-004-7` | 19 | 18/19 | 18/19 | 19/19 | 0 | absent |
| `CIP-005-7` | 12 | 12/12 | 12/12 | 12/12 | 0 | absent |
| `CIP-006-6` | 14 | 13/14 | 13/13 | 13/13 | 27 | present |
| `CIP-007-6` | 20 | **20/20** | **20/20** | **20/20** | 89 | present |
| `CIP-008-6` | 12 | 12/12 | 12/12 | 12/12 | 0 | absent |
| `CIP-009-6` | 10 | 10/10 | 10/10 | 10/10 | 39 | present |
| `CIP-010-4` | 12 | 12/12 | 11/11 | 11/11 | 0 | absent |
| `CIP-011-3` | 4 | 4/4 | 3/4 | 4/4 | 0 | absent |
| `CIP-012-2` | 6 | 6/6 | — | — | 0 | absent |
| `CIP-013-2` | 11 | 11/11 | — | — | 0 | absent |
| `CIP-014-3` | 19 | 15/19 | — | — | 15 | present |
| **fleet** | **255** | **242/255 = 0.949** | **99/101 = 0.9802** | **177/202 = 0.8762** | **401** | 7 present |

`CIP-007-6 R2 Part 2.2` — the discriminator — anchors to
`csection-7700dd5499cead0994ec`, its own `table_row`, in one occurrence.

Live table state: **252 of 255 requirements joined**, 268 `governing` rows over
266 sections, 183 `measure`, 177 `applicable_systems`, 1,780 `technical_basis`
over 401 sections, and **39 misses recorded in `requirement_anchor_misses`** —
queryable facts, not lines in a report nobody re-reads.

### 3.1 Every miss, by cause

All 40 unanchored (requirement, relation) pairs fall into two named reasons,
and reading them is how the substitution work above got done.

| cause | n | what it is |
| --- | --- | --- |
| `text does not occur in the captured revision` | 30 | the two readers disagree about the text itself |
| `text too short to anchor safely` | 10 | 21–22 characters, under `MIN_ANCHOR_CHARS = 24` — **refused, not risked** |

The 30 break down further, and none is fixable by a licensed substitution:

* **18 are CIP-002-5.1a Attachment 1 `applicable_systems`**, where the Register
  joins an impact-rating heading to its body with `" - "` and the capture does
  not. That is the rejected dash candidate — correcting it would break 14
  anchors elsewhere, so it stays unanchored.
* **Cell-order divergence** (CIP-002-5.1a Part 2.9): the two readers read the
  same table's cells in different orders. §0 predicted exactly this and called
  it correct behaviour to record, not work around.
* **Line-break artefacts in the Register's own text** — `(CIP- 010)`,
  `CIP -006 -6 Table R3`, a space before a full stop.
* **Roman-numeral list markers** the capture folds into structure.
* **One case where the Register's text is the defective side:** `CIP-014-3 R5`
  carries the running page header `CIP-014-3 - Physical Security` spliced
  mid-sentence, because pymupdf reads a page header as inline text. The capture
  is clean. This is a Register-side extraction finding worth its own look.

---

## §4 — Retrieval and closure scope by identity

`compliance_search(requirement="CIP-007-6 R2 Part 2.2")` resolves through the
join to exact section ids and pushes `chunk_id IN (…)` **before** ranking,
composed with the clock clauses by `AND`. Not a predicate column and not a
`LIKE`: `'CIP-007-6 R2'` is a substring of `'CIP-007-6 R2 Part 2.2'`, so
substring matching is wrong here rather than merely inelegant, and repeated
index rows would break `chunk_id = section_id`. The payload reports
`requirement_pool` — the candidate pool the arms scored — so identity-scoping
is checkable rather than inferred from a result count.

`enumeration.population_for_requirement` is the closure-side twin, and the
structural walk survives as a **named** fallback: `population_method` is
`"join"` or `"proximity"`, and `reading_assembly.assemble` reports which it
used. Live: `CIP-007-6 R2 Part 2.2` → `join`, one section, by exact match;
`CIP-014-3 R5` → `proximity`, *"not anchored into the captured revision (text
does not occur) — gathered by heading-path proximity, which is a weaker basis
than the join and is reported as such."*

### 4.1 The `IN`-list ceiling — the measurement says something else

§P4.1 asked for the cap to be set from where latency turns. Timed against the
live 4,477-row `nerc_corpus`, prefiltered, five reps, median:

| ids | median | min | max | clause chars |
| --- | --- | --- | --- | --- |
| clock only | 4.9 ms | 4.8 | 6.3 | — |
| 10 | 7.5 ms | 7.4 | 9.4 | 342 |
| 100 | 5.9 ms | 5.7 | 6.2 | 3,312 |
| 500 | 8.5 ms | 7.9 | 9.2 | 16,512 |
| 1,000 | 12.0 ms | 11.3 | 12.9 | 33,012 |
| 2,000 | 19.7 ms | 18.7 | 20.7 | 66,012 |
| 3,000 | 26.0 ms | 25.2 | 27.1 | 99,012 |
| 4,000 | 32.4 ms | 31.9 | 32.7 | 132,012 |

**Latency does not turn.** It is linear at roughly 7.3 µs per id all the way to
an id list naming every row in the table. There is no knee to set a cap from,
and saying otherwise would have been the easy, wrong write-up.

So the cap comes from the population instead. Across the 252 joined
requirements, sections-per-requirement is **median 3, p90 35, max 97**.
`MAX_REQUIREMENT_SECTION_IDS = 500` sits five times above the observed maximum
at 8.5 ms, so it never refuses a real requirement — it refuses a request that
has stopped being a requirement and become a whole standard. Above it the tool
returns `honest-BLOCKED` naming the count, because a silent fallback to an
unfiltered search would *look* filtered.

### 4.2 The re-run of the measurement that came back flat

`SUBSTRATE_PROPERTIES_V1` §2.2 measured recall 1.000 at `top_k = 10` with and
without pushdown, and concluded — correctly, but for a reason it could not see
— that there was nothing to filter. The NERC corpus is now **4,477 rows, up
from 1,903**, and both corpora re-projected FRESH with zero unprojectable
sections (605 s and 1,090 s). Same query, same hand-judged three-section
discriminator (READING_SEAT_RESEARCH_V1 §2.1), the real corpus:

| k | unscoped | `valid_at` | `requirement=` (governing) | `requirement=` (all relations) |
| --- | --- | --- | --- | --- |
| 3 | 0.667 | 0.667 | 0.333 | 0.333 |
| 5 | 0.667 | 0.667 | 0.333 | 0.333 |
| 10 | **1.000** | **1.000** | 0.333 | 0.333 |
| 15 | 1.000 | 1.000 | 0.333 | 0.333 |

**`top_k = 10` survives.** Recall saturates at exactly the same k it did on a
corpus less than half the size, and the 5-slot point is still short. The default
stands, and now stands on a real corpus.

**The 0.333 is not a regression, and reporting it as one would be wrong.** The
discriminator spans *both* corpora — a NERC section, an operator procedure
section and an operator note — and scoping to one requirement's `governing`
sections can only return the one that belongs to that requirement. It returns
exactly that one. Requirement scoping is the wrong instrument for a question
whose answer is bilateral by construction; it is the right instrument for *what
does R2 Part 2.2 say, and what governs it*.

The number that does tell us whether P1's pushdown was worth building is this
one:

| | rank of the `CIP-007-6 R2 Part 2.2` row |
| --- | --- |
| unscoped, `top_k=10` | **8** |
| `requirement="CIP-007-6 R2 Part 2.2"` | **1** |

On the three-document corpus that difference could not appear. On the real one
the governing row is eighth out of ten in an unscoped search — inside the
window, but only just, and nothing about the ranking guarantees it stays there
as the corpus grows. Scoped, it is first, out of a pool of one, carrying
`requirement_id`, `relations`, `vrf` and `time_horizon` on the hit. That is what
the join bought.

---

## §5 — Measures and the Technical Basis, independent of the verdict engine

`regulatory_bundle` owns the whole semantic content of a revision, and all of it
was reachable only through `resolve_governing_bundle`, re-parsed from the PDF at
call time. The GTB text is **already captured** — it sits in `full_text` as
prose under its own heading path — so `anchor_bundle_spans` adds **nothing** to
`source_sections` and locates each span in the captured character space,
writing a `requirement_sections` row pointing at the sections that already
contain it.

Live, over the whole anchor pass: `source_sections` **7,477 before, 7,477
after, delta 0**, and `assert_faithful` still passes. Zero new sections; 1,780
`technical_basis` rows over 401 sections.

### 5.1 Does the join reach what re-parsing reaches?

The precondition for file D, measured by `--verify-bundle-equivalence`. The
measure is **by section, not by byte** — the two readers render the same bytes
differently, so byte equality between their outputs would fail for reasons that
have nothing to do with reachability, and that is a test worth not writing.

| standard | pieces covered / located | rate |
| --- | --- | --- |
| `CIP-002-5.1a` | 594 / 598 | 0.9933 |
| `CIP-003-8` | 503 / 503 | **1.0** |
| `CIP-006-6` | 310 / 310 | **1.0** |
| `CIP-007-6` | 1,147 / 1,147 | **1.0** |
| `CIP-009-6` | 227 / 227 | **1.0** |
| `CIP-014-3` | 65 / 65 | **1.0** |
| **total** | **2,846 / 2,850** | **0.9986** |

The seven standards absent from this table record
`technical_basis_section: absent` — their interpretive context lives in
separately acquired technical rationale documents. That is a recorded revision
shape fact, not a failure.

### 5.2 Why this matters for the product

Half the questions an operator asks about CIP-007 R2 are answered by the GTB,
not the requirement text: that R2 is not strictly an install-every-patch
obligation, that 2.3 timeframes may use event designations such as the next
scheduled outage of at least two days, that 2.4 carries no maximum timeframe,
that Measures are not an all-inclusive list. A procedure that hardcodes calendar
days into 2.3, or invents a deadline for 2.4, is using less latitude than NERC
grants — a finding worth reporting. That material has been in the module the
whole time, behind the tool file D was going to delete.

---

## §6 — Bugs and findings

1. **The two halves shared no key.** The founding defect, fixed. Not a bug in
   either half — each did its own job correctly — but the absence of the thing
   that made either useful.
2. **`record_anchors` cleared per anchor instead of per call.** One requirement
   legitimately receives several anchors under one relation (a Technical Basis
   region arrives as paragraph-sized pieces), and clearing per anchor left only
   the last piece joined. Fixed; the insert also upserts on the composite key.
3. **A Measures lead-in span runs through the entire requirements table.**
   `regulatory_bundle` bounds a lead-in at the start of the next region.
   Anchoring the raw span produced **1,061** measure joins attaching Part 2.1's
   Measures cell to Part 2.4 — citations that look correct and cannot be
   checked. Scoped to the `M<n>` statement: 18.
4. **pymupdf reads a running page header as inline text.** It splices
   *"Guidelines and Technical Basis"* and *"CIP-014-3 - Physical Security"*
   mid-sentence into the Register's and the bundle's prose. This is why a long
   span is anchored as line-grouped pieces with a line-level retry, and it is
   the sole cause of `CIP-014-3 R5` not anchoring.
5. **The §P1.3 probe's own SQL was wrong**, and it mattered. `logical_id LIKE
   '%CIP-007-6%' ORDER BY recorded_from DESC LIMIT 1` selects the
   *implementation plan*, not the standard. The first run reported
   `governing 0/20` and looked like a capture-fidelity crisis. It was a `LIKE`
   in a probe — the same hazard §P4.1 refuses to build into the product.
6. **The three-of-36 framing understated what was there.** 13 of 14 standards
   were already in the store with matching hashes and unprojectable sections.

---

## §7 — What is still missing, plainly

* **Revision history is thin.** One revision per standard except CIP-003;
  `valid_to` is populated on 39 of 255 nodes, all CIP-003-8. `valid_at` queries
  into the past are answerable only where a prior revision was captured.
* **CIP-007-7.1 is captured and is not in the Register**, so the 6 → 7.1 diff
  has fidelity on both sides and structure on one. Anchoring 7.1 needs a
  Register build for it.
* **Older-revision URLs are still unsolved.** NERC's per-version URLs for
  superseded revisions do not resolve. This phase does not claim otherwise; the
  backlog was never 33 unreachable PDFs, and this is the part of it that is
  real.
* **13 governing requirements and 25 applicable-systems columns do not anchor**,
  every one named in §3.1 and in `requirement_anchor_misses`. They are not
  rounded away and they are not fuzzily matched.
* **Mapping ground truth is still empty** — 1,427 proposed, 0 approved. File C
  is still blocked on it; the join makes the review cheaper, not unnecessary.

---

## §8 — The corrected sequence

* **A (landed)** `SUBSTRATE_PROPERTIES_V1`. Its P1 columns are now *carriers*
  for Register facts rather than independent derivations:
  `section_index.resolve_sections` reads `vrf`, `time_horizon`,
  `applicable_systems`, `lifecycle_state` and the Register's `authority_tier`
  off the requirement a section carries, and **reports a tier disagreement
  rather than resolving it** — two derivations of one fact silently differing is
  the identity-space failure this module has already had twice.
* **A′ (this file)** the join, the complete regulatory corpus, GTB reachable.
* **B** `ONE_ANSWER_PATH_V1` — the agentic reader. **Rewrite required:** it
  assumed a 3-of-36 corpus and proximity neighbourhoods. Its `[GATE]` on
  CIP-007 stands and is now worth passing, because the reader can retrieve by
  requirement.
* **C** `MODEL_GOVERNANCE_V1` — still blocked on ground truth. Batch review is
  the unblocking work, and the join makes it cheaper: a proposal can now be
  shown with its requirement's verbatim text, Measures **and** Technical Basis
  beside the operator's candidate section.
* **D** `RETIRE_THE_VERDICT_ENGINE_V1` — **reissued with §P2.4 reversed.**
  `compliance_bundle` / `resolve_governing_bundle` is **not** deleted. §5 makes
  its content independent of the engine and §5.1 measures that at 0.9986, which
  is the precondition D needed. `regulatory_bundle.py`, `cip_extract.py` and
  `cip_register.py` come off every deletion list — they are the regulatory
  extractor. The rest of D's shape holds.
