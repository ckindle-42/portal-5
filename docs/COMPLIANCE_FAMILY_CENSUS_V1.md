# Compliance Family Census V1 — uncovered, separated from unread

**Date:** 2026-09-19 · **Task:** TASK_COMPLIANCE_DELIVER_AND_SETTLE_ENGINE_V1 §A1 · **Base:** `6ff98738`

The family-sweep question "family mapping coverage is zero" was three situations
hypothesised in `PROVE_THEN_SCALE_V1` §8.1 — quote discipline, checker
strictness, or nothing to map. This census answers it per standard with live
population queries (no sweep re-run): which standards' populations hold no
operator sections at all (**UNCOVERED** — zero determinations are *correct*),
which hold them but the sweep proposed nothing (**COVERED-BUT-UNREAD** — a
defect), and which made proposals that were all refused (**COVERED-AND-REFUSED**
— the §8.1 question, scoped). It also reports the inverse orphan: operator
sections that appear in **no** population.

## Method

* Population side: `requirement_scope.population()` for every register node
  (`cip_register.Register.load()`, 258 nodes across 14 standards), counted by
  operator-side sections per node. Live store, no mocks.
* Sweep side: per-standard `determined` / `corroborated` / `rejected` tallies
  from the recorded family sweep (`reports/compliance/prove_then_scale/p7_family_sweep.json`,
  seat `gemma4:26b-a4b-it-q4_K_M-ctx32k`).
* Inverse orphan: every `internal`-jurisdiction section in the store vs the set
  of operator sections appearing in any population.

## The census

| standard | register nodes | nodes with operator sections | op sections in populations | sweep determined | sweep corroborated | sweep refused | bucket |
|---|---:|---:|---:|---:|---:|---:|---|
| CIP-002-5.1a | 33 | 1 | 5 | 0 | 0 | 0 | COVERED-BUT-UNREAD |
| CIP-003-8 | 39 | 3 | 15 | 0 | 0 | 12 | COVERED-AND-REFUSED |
| CIP-003-9 | 44 | 3 | 15 | 0 | 0 | 1 | COVERED-BUT-UNREAD |
| CIP-004-7 | 19 | 19 | 95 | 0 | 0 | 11 | COVERED-AND-REFUSED |
| CIP-005-7 | 12 | 12 | 60 | 0 | 0 | 0 | COVERED-BUT-UNREAD |
| CIP-006-6 | 14 | 13 | 65 | 0 | 0 | 1 | COVERED-BUT-UNREAD |
| CIP-007-6 | 20 | 20 | 73 | 13 | 8 | 13 | COVERED-AND-WORKING |
| CIP-008-6 | 12 | 12 | 56 | 0 | 0 | 3 | COVERED-BUT-UNREAD |
| CIP-009-6 | 10 | 10 | 50 | 0 | 0 | 2 | COVERED-BUT-UNREAD |
| CIP-010-4 | 12 | 11 | 55 | 0 | 0 | 1 | COVERED-BUT-UNREAD |
| CIP-011-3 | 4 | 4 | 20 | 0 | 0 | 2 | COVERED-BUT-UNREAD |
| CIP-012-2 | 6 | 1 | 5 | 0 | 0 | 1 | COVERED-BUT-UNREAD |
| CIP-013-2 | 11 | 3 | 15 | 0 | 0 | 0 | COVERED-BUT-UNREAD |
| CIP-014-3 | 19 | 2 | 10 | 0 | 0 | 1 | COVERED-BUT-UNREAD |

## Findings

### 1. UNCOVERED is empty — the hypothesised third situation does not exist

Every one of the fourteen standards' populations holds operator sections. The
true finding is the opposite of a corpus gap: **the operator corpus covers the
whole CIP family, and the sweep mapped one standard of fourteen.** No standard
gets to publish "we have no documented procedures for X" off this census; every
zero is unread, not absent.

### 2. COVERED-BUT-UNREAD is the modal situation — nine standards

CIP-005-7 is the sharpest: 60 operator sections across **all twelve** of its
requirements' populations, zero proposals, zero refusals. The sweep never said
anything. CIP-002-5.1a's five operator sections sit behind its addressability
problem (see `COMPLIANCE_FAMILY_CENSUS_V1` §5 / A5): only 1 of 33 nodes
resolves operator sections through a parseable address, so its unread-ness is
partly the Attachment-grammar defect, not purely the sweep's.

### 3. The one-case defect read — CIP-005-7 R1 Part 1.1

Rendered the requirement's material (`reading_material.render`, shared body
first, 5 operator sections in scope) and ran the proving protocol's one-call,
no-tools read on the proven seat (gemma4). Wall 33.4 s. The read returned six
pairings — four IMPLEMENTS, one EVIDENCES, one REFERENCES — each with a
verbatim quote from the operator section (firewall-rules evidence, the ESP
residency rule, the ESP-commissioning procedure's own restatement of
Part 1.1, the patch-management scope naming ESP Access Points). Receipt:
`reports/compliance/census/census_defect_read_cip005_r1p11.json`.

**Verdict: fabricated absence at sweep scale.** The material supports mappings;
the sweep produced none. This is not quote discipline (nothing was refused) and
not checker strictness — the sweep's map pass simply proposed nothing for nine
standards whose populations hold mappable operator sections. The §8.1
remediation question survives only for the COVERED-AND-REFUSED pair (CIP-003-8,
CIP-004-7), where proposals were made and refused.

Caveat carried from the read: the answer's section-id spellings drifted
(two ids quoted with dropped characters), so automated re-use of this
particular answer's citations would fail resolution — the quoted *sentences*
are the load-bearing output and those are verbatim. The sweep's own
verbatim-quote guard is what keeps such drift out of the store.

### 4. COVERED-AND-REFUSED — the §8.1 question, scoped to two standards

CIP-003-8 (12 refusals) and CIP-004-7 (11) made proposals that were all
refused. A6 re-runs these with reasons retained and separates quote discipline
from checker strictness. One-apiece refusals (CIP-003-9, CIP-006-6, CIP-010-4,
CIP-011-3, CIP-012-2, CIP-009-6, CIP-008-6, CIP-014-3) read as noise against
their requirement counts and travel with the same re-run.

### 5. The inverse orphan: 2,392 of 2,636 operator sections are in no population

The store holds 2,636 `internal`-jurisdiction sections; 244 appear in at least
one register population; **2,392 are orphans** — reachable by no requirement's
scope. They are not junk: they sit in the operator's real procedure documents
(CIP-008 Incident Response V14: 107; CIP-007 Patch Management WI v7: 61; CIP-009
Network Device Build WI v4: 59; the full twelve-document spread mirrors the
corpus). The population join reaches only what an anchor or a recorded edge
names, so the operator's corpus is ~91% invisible to requirement-scoped
reading. Widening coverage is a link-creation problem (the sweep's own job),
not a corpus problem — recorded here so the queue treats the orphans as
headroom, not as a defect of `requirement_scope`.

## What this changes

* "Zero determinations" is per-standard **unread**, not per-corpus
  **uncovered** — no true gap analysis falls out of this census; all of them
  were fabricated absences waiting to be confirmed as such.
* A6.3 (the refusals) is scoped to CIP-003-8 and CIP-004-7.
* The CIP-002-5.1a bucket is jointly owned by A5 (addressability) and the
  sweep defect.
* The 2,392 orphan sections are the size of the mapping work ahead — the
  sweep, working, is the instrument that closes it.
