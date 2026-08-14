# BUILD_PROGRAM_DEFENSIVE_BULLY

**This is THE design — the complete defensive bully, all parts in the initial
design.** It is not a V1 with deferrals. Phasing below is *build sequence only*:
what to build first so each phase stands on a working predecessor. Nothing in
the concept is parked to a later version. Where a capability is large, it is
split into ordered phases, but it is in scope from the start.

## The thesis

Modern offense hunts the *shape* of a weakness and chases everything
structurally adjacent — the bully's move: found the TIFF-parser OOM, go break
the SFNT parser for the same class of bug. Cousins. Same / similar / new /
different. The defensive bully is the mirror: **given everything we know,
surface the cousins we don't** — the near-neighbor attack one mutation from a
covered one that our detection won't catch — and alarm on it, graded by distance
from known. `ANOMALOUS_UNCLASSIFIED` ("cousin-of-X but not X, and nothing catches
it") is the primary product.

**Red (R) is the means and is left alone.** It manufactures attacks in the lab
and lands telemetry; the bully directs *which* attack R runs but never modifies
R. **Blue and Purple (B/P) are the new brain and heart** — the current ~7,300-line
bench-scoring B/P is replaced. The one part of B/P kept is the platform council
primitive, reused as the self-adversarial heart.

**The bully is a compounding organism, and compounding = feeding + learning +
training.** This is the part every prior draft under-built. The concept does not
just hunt — it *gets smarter and sharper every run* through six feeding
mechanisms and a real train-redeploy flywheel. Those are first-class here, not a
tail-end afterthought.

**Reference commit:** HEAD `ee9272e` (2026-08-13). Every task re-verifies HEAD
and reads named symbols live.

---

## The complete offense→defense translation

The concept is an offensive 0-day hunter. This is the full, line-by-line
translation of every offensive primitive into its defensive equivalent — the
map that proves nothing in the concept is left behind and every piece has a
defensive home. Each row names the component of this build that carries it.

| # | Concept (offense) | Portal defensive equivalent | Built as |
|---|---|---|---|
| 1 | Hunt a target binary for an exploitable bug | Hunt a (TTP × log-source × detection) coverage cell for a gap | LOOP + TGT |
| 2 | **Finding = a working 0-day PoC** | **Finding = a missed/near-missed detection: red landed (or a cousin of a covered TTP landed) and blue did not catch it** | BIN + BR |
| 3 | Hallucination bin: PoC compiles → reproduces → exploitable → low-priv | Alert bin: G0 has-evidence → G1 replay-reproduces (static+dynamic) → G2 not-benign → G3 analyst-visible | BIN |
| 4 | Known-defence DB (AM-PPL blocked us → deprioritise target) | Known-defence / known-benign / known-covered DB (legit, or already caught → deprioritise cell) | SUB + TGT |
| 5 | ROI = bounty payout / hunt hours (chase the payout) | ROI = risk-reduction value / test cost (chase the biggest blind spot) | TGT |
| 6 | Low-priv gate (worthless if only triggers as SYSTEM) | SOC-analyst-context gate (worthless if only visible to the eval harness, not the real console under queue load) | BIN G3 |
| 7 | Reporting exit = bounty submission | Detection-engineering handoff: family-generalizing Sigma diff + correlation change + log-source onboard + IR/ATT&CK deltas | HND |
| 8 | **Grammar fuzzing — structurally *valid* files with adversarial field values** (random bytes just get "invalid format"; validity is what reaches the parser) | **Atomic mutation — structurally *valid* TTPs with adversarial params/timing/artifacts** (random noise just gets dropped; a valid-but-perturbed technique is what reaches the detection and exposes the cousin gap) | MUT |
| 9 | Personal FAISS of a decade of notes, queried inline | Hunt-knowledge organ — our own hunt history embedded and queried before every hunt; distance = the cousin metric | ORG + BR |
| 10 | One model bullying itself to disprove a finding | The fleet council bullying a finding adversarially — many diverse models trying to break it (exceeds the concept) | HEART |
| 11 | Fine-tune Qwen on my own hunts | Fleet-local fine-tune on our own hunt corpus, served back into the fleet | HARV + TRAIN |
| 12 | Variant analysis — found one, hunt its cousins | Spatial cousins (near-neighbor in the organ) **and** temporal cousins (a detection drifting from its own baseline) | BR-COUSIN + BR-DRIFT |
| 13 | Knowledge loop — query priors before, record outcome after, everything indexed | Same, enforced in the tool (not model discretion); universal indexing of every emission, positive and negative | ORG (invariant) |
| 14 | Coverage plateau — stop when new signal stops, record it | Plateau on gap-classification deltas stops an exhausted neighborhood; cost-per-cousin-found tracked and falling | PLT |
| 15 | Per-campaign CLAUDE.md tuned each run, offloading to local models | Per-scenario-type playbook memory — learned instruction sets per investigation class that shape small trained fleet models | PLAY |

### Hardware translation — Portal's assets are the concept's rig

| Concept rig | Portal asset |
|---|---|
| The hunter/analyst models | The Ollama fleet |
| The Proxmox hunt range (5 VMs, isolated segment) | Portal's Proxmox + Splunk + AD lab (10.10.11.0/24) |
| The MCP tool surface (8 servers, 300+ tools) | Portal's MCP fleet (ports 8910–8931) |
| The local FAISS + sentence-transformer embeddings | MLX embedding 8917 + reranker 8925 (the organ's engine) |
| One researcher's self-bullying | The council across the fleet |
| Claude Max doing the orchestration | The pipeline (:9099) driving Ollama, with fleet-local training added |

Every offensive primitive (rows 1–15) and every piece of the concept's rig has a
named defensive home in this build. That completeness is the point: this is the
project translated offense→defense in full, not in part.

---

## The boundary: stays / consumed / kept / replaced

- **R — stays untouched.** `exec_chain` `red_order`, red execution, R→telemetry.
  Directed (told which cousin to make), never modified.
- **R's Episode — consumed.** `episode.py` `Episode` (evidence_refs, telemetry
  landed) is the bully's input contract. REUSE.
- **Platform council — kept as the heart.** `portal/platform/inference/router/
  council.py` (556 lines): fleet-of-models review with `strongest_objection`/
  `missing_evidence`/`conditions_to_change` already in the data model. REUSE,
  made adversarial. Its vote-flattening security adapter `council_agreement.py`
  is part of old B — REPLACE.
- **B/P — replaced (new brain/heart).** `blue.py`, `blue_orchestrate.py`,
  `multichain.py`, `agentic_blue_eval.py`, `analyst_verdict.py`,
  `council_agreement.py`, `response_loop.py`. Bench-scoring brain → hunting brain.
- **Retrofit into the new BP:** `unknown_defense` (cousin engine, off its
  wiki-token matcher onto a semantic organ), `notify_scoreboard` (already scores
  `ANOMALOUS_UNCLASSIFIED` as a full catch — REUSE, extend by distance),
  `emergent_gaps` (red off-script → deliberate mutation-probe), `rag_mcp`
  (`kb_ingest`/`kb_search` on local MLX 8917/8925 → cousin-space organ),
  `investigation/` `EvidenceStore`/`CaseNotebook` (persistent-state seed),
  `capability_graph` (persistent coverage), `field_journal` (behaviour-changing
  recall).
- **Doc spine — shrinks** to design-facts-only once the organ exists.
- **Bench harness — repositioned** as the acceptance gate for models the bully
  trains (not deleted).

---

## The six feeding mechanisms (the concept's compounding, in full)

The bully's intelligence compounds through six distinct feeds. All six are in
this design; none are optional.

1. **Semantic hunt memory (the organ)** — every known-bad, benign pattern, past
   finding, plateau embedded and queried before every hunt. Distance in this
   space *is* the cousin metric. Infra exists (`rag_mcp` `kb_ingest`); the feed
   from hunts is built.
2. **Known-defence / known-benign / known-covered DB** — negative results
   multiplicatively steer future hunts away from waste (this cell is benign /
   already caught / a dead end). Built in the substrate.
3. **ROI / target intelligence** — risk-reduction-per-cost ranking steers toward
   the biggest blind spot. Built as target selection.
4. **Training-pair harvest** — every hunt auto-extracts (evidence → verdict +
   rationale) pairs; the council's adversarial exchanges and the cousin-distance
   judgments are the richest signal. Built.
5. **Fleet-local fine-tune** — pairs train a role-specialist model that *smells
   cousins* better; fused → GGUF → `ollama create` → bench-gated → served. The
   train leg is genuinely new; the feed leg (`kb_ingest`) and the redeploy leg
   (`models.py` `ollama create`/Modelfile) already exist and are wired in.
6. **Per-scenario-type playbook memory** — accumulated, learned instruction sets
   per investigation class (ransomware / credential-theft / lateral-movement)
   that tune the loop and give small fleet models a narrow shape they can be
   competent in. This is the concept's per-campaign `CLAUDE.md`, defensive. Built.

Feeds 1–3 make the *hunt* smarter each run; feeds 4–6 make the *fleet* sharper
each run. Together they are why the twentieth hunt beats the first.

---

## Components of the complete design

### Substrate & knowledge

**SUB — persistent compounding state** (NEW; seeds from `EvidenceStore`).
One evolving store: cousin-neighborhood state, coverage cells, known-defence/
known-benign/known-covered DB (feed 2), plateau state, cost ledger,
decision-event log. Read before every hunt, written after.

**ORG — cousin-space organ** (retrofit `rag_mcp`; shrink spine).
Embeds and indexes hunt memory via MLX 8917/8925 (feed 1). Distance = cousin
metric. Mandatory pre-hunt query enforced **in the tool**, not model discretion.
**Invariant: universal indexing — nothing the hunt emits is un-indexed,
positive and negative.**

### The brain

**BR-COUSIN — the cousin engine** (retrofit `unknown_defense` onto ORG).
EXACT/SIMILAR/NEW grading by semantic k-NN distance in ORG; hybrid
explainability (embedding *finds*, feature-overlap *explains* — the old
matcher's citation value preserved as the explanation layer). The heart of
same/similar/new discovery.

**BR-DRIFT — the temporal-cousin instrument** (NEW; the N-1 idea, defensive).
Rolling baseline of how each detection *normally* fires; drift — fires weaker,
later, differently than baseline — is first-class signal, catching a TTP that
evolved into a cousin of itself. Spatial cousins (BR-COUSIN) and temporal
cousins (BR-DRIFT) are two detection surfaces, both in scope.

**LOOP — the hunt loop** (NEW; replaces `blue_orchestrate` bench driver).
Read ORG+SUB → pick a cousin-neighborhood by ROI → direct R to manufacture the
cousin → consume R's Episode → BR grades distance → BIN gates → HEART bullies →
alarm/kill → write outcome+cost to SUB+ORG → stop on plateau.

### The alert bin & the heart

**BIN — the alert bin** (retrofit `growth_loop` gates; replace default).
Suspect-until-proven, real gates:
- G0 has-evidence
- G1 replay-reproduces in a clean SIEM snapshot **(static+dynamic pairing: a
  signature match alone is G0 at best; promotion requires the chain actually
  completed and left the expected artifacts)**
- G2 not-benign (the concept-native home for alert-fatigue)
- G3 analyst-visible **as its own gate** — evaluated as-seen-by-the-SOC-analyst
  in the real console under real queue load, not the eval harness's god-view. A
  finding visible only to the harness is not promotable. (The defensive
  translation of the bully's low-priv lesson.)
Replace `multichain.consolidate` clear-by-default with suspect-by-default.

**HEART — the self-bullying fleet council** (REUSE platform primitive; new gate).
Seats tasked to *break* a candidate cousin; the emitted `strongest_objection`
becomes a **promotion gate** — no alarm while an unrebutted objection stands.
Fleet-of-disprovers, exceeding the one-model concept.

### Red as means

**MUT — red as cousin-generator** (retrofit `emergent_gaps` + new probe).
Directs R to produce near-neighbors of a chosen known (perturbed params/timing/
artifacts, adjacent sub-techniques) + reuses red's off-script emergent misses. A
bounded **mutation budget** (operator policy dial) governs how far red wanders.
R's execution is untouched — only its target is chosen.

### Discovery, selection, stopping

**SCORE — discovery-first, distance-graded** (REUSE `notify_scoreboard`; extend).
Keep `ANOMALOUS_UNCLASSIFIED == full catch`; extend so a *far* NEW cousin scores
≥ a known-bad catch. First-in-class, not coverage-complete.

**TGT — ROI + known-defence target selection** (NEW; feed 3).
Rank cousin-neighborhoods by risk-reduction/cost; multiplicatively deprioritise
known-benign/known-covered cells from SUB (feed 2).

**PLT — plateau + compounding-cost meter** (NEW).
A hunt stops when gap-classification deltas flatline; plateau recorded, steers
scheduling; cost-per-cousin-found tracked and shown falling. The compounding
proof.

### The exit

**HND — family-generalizing detection handoff** (retrofit `response_loop`; new
exit). A promoted cousin exits as a fix that closes the *family* — a generalized
Sigma rule, a correlation change, a log-source onboard — plus IR/ATT&CK deltas,
actionable without translation.

### The training flywheel (feeds 4–6 — first-class, not a tail)

**HARV — training-pair harvest** (NEW; feed 4).
Auto-extract role-tagged (evidence → verdict + rationale) pairs from every hunt.
Council adversarial exchanges (finding + the objection that did/didn't kill it)
and BR cousin-distance judgments are the highest-value pairs. Versioned jsonl per
role (hunter / analyst / disprover / cousin-smeller), label-blind (BM). Reuses
`recall_attribution` as the honest-miss labeler.

**PLAY — per-scenario-type playbook memory** (NEW; feed 6).
Accumulated, learned instruction sets per investigation class, tuning the loop
and giving small fleet models a competent narrow shape. The defensive
per-campaign `CLAUDE.md`. The runtime container a trained specialist executes
inside — which is why it pairs with TRAIN.

**TRAIN — fleet-local fine-tune** (NEW; feed 5; the genuinely-missing leg).
The flywheel's five legs, three of which already exist:
- FEED (exists): `rag_mcp kb_ingest` indexes the corpus.
- HARVEST (HARV): produces the SFT jsonl.
- TRAIN (**new build, includes toolchain install**): install and set up the
  local training toolchain (`mlx_lm.lora` / adapter-fuse / GGUF-convert), then
  train a role-specialist adapter from the pairs. The toolchain not existing
  today is a setup task the phase owns, not a risk to assess.
- FUSE→GGUF→REDEPLOY (exists): `models.py` `ollama create` + Modelfile already
  imports GGUFs into the fleet — wired into the loop.
- ACCEPT (exists): the repositioned bench harness gates the trained candidate
  before any serve.
PROMOTE_POLICY=confirm — a trained model serves only on operator confirm.

**ROSTER — retrospective council weighting** (NEW).
Seats whose cousin-calls/objections held gain weight; consistently-wrong seats
lose it. Floored. The council learns which fleet models smell cousins best —
closing feed 4/5 back onto the heart.

---

## Parts inventory

| Part | Verdict | Note |
|---|---|---|
| `exec_chain` red_order, red execution | LEAVE ALONE | R is the means |
| `episode.py` Episode | REUSE | input contract |
| platform `council.py` | REUSE→HEART | made adversarial |
| `council_agreement.py` (vote adapter) | REPLACE | flattens the objection signal |
| `blue.py`/`blue_orchestrate.py`/`agentic_blue_eval.py`/`analyst_verdict.py` | REPLACE | bench brain → hunt brain |
| `multichain.consolidate` default | REPLACE | clear→suspect |
| `response_loop.py` | REPLACE→HND | family-generalizing exit |
| `unknown_defense` | RETROFIT→BR-COUSIN | semantic distance, not wiki tokens |
| `notify_scoreboard` | REUSE+EXTEND | ANOMALOUS==catch, add distance |
| `emergent_gaps` | RETROFIT→MUT | deliberate mutation-probe |
| `rag_mcp` (kb_ingest/search, MLX) | RETROFIT→ORG | hunt memory, not docs; FEED leg |
| `models.py` ollama create/Modelfile | REUSE | REDEPLOY leg of TRAIN |
| `recall_attribution` | REUSE | honest-miss labeler for HARV |
| `investigation/` EvidenceStore/CaseNotebook | REUSE | SUB seed |
| `capability_graph`, `field_journal` | RETROFIT | persistent graph; behaviour-changing recall |
| doc spine as knowledge store | REPLACE→shrink | knowledge moves to ORG |
| bench harness | REPOSITION | TRAIN acceptance gate |
| fleet-local train (LoRA/adapter) | NEW | the one absent flywheel leg |

---

## Build phasing (sequence, not scope)

All components above are in the design. Phases order the build so each stands on
a working predecessor.

**Phase 1 — spine (brain substrate).**
SUB1 state store · SUB2 decision-event log · ORG1 cousin-space organ + spine
shrink · BR1 cousin engine on semantic distance · LOOP1 hunt loop (replaces
blue/purple orchestration, consumes R's Episode).

**Phase 2 — bin & heart.**
BIN1 real gates G0–G3 (incl. static+dynamic G1 and analyst-visible G3 as real
gates) · HRT1 self-bullying fleet council (objection gate) · BIN2 suspect-by-
default.

**Phase 3 — red as means & the second cousin surface.**
MUT1 red cousin-generator + mutation budget · BRDRIFT1 temporal-cousin drift
instrument.

**Phase 4 — discovery, selection, stopping.**
SC1 distance-graded scoring · TGT1 ROI + known-defence selection · PLT1 plateau
+ compounding-cost meter.

**Phase 5 — the exit.**
HND1 family-generalizing detection handoff.

**Phase 6 — the feed/learn/train flywheel (feeds 4–6).**
HARV1 training-pair harvest + SFT corpus · PLAY1 per-scenario-type playbook
memory · TRAIN1 fleet-local LoRA train step (the new leg) · TRAIN2 wire
FUSE→GGUF→ollama-create→bench-gate (existing legs) into the loop · ROSTER1
retrospective council weighting.

### Dependency spine
- Phase 1 is the hard gate: BR1 needs ORG1; LOOP1 needs BR1+SUB. Nothing lands
  before LOOP1, which is where old B/P orchestration is replaced.
- BIN1→HRT1→BIN2 (gates before objection-gate before suspect-default, or false
  flags spike BQ/AZ).
- MUT1 needs BR1; BRDRIFT1 needs SUB (baseline store) + LOOP1.
- SC1 needs BR1; TGT1 needs SUB+BR1; PLT1 needs BR1+SUB.
- HND1 needs BIN1+HRT1.
- HARV1 needs SUB2+HRT1+BR1 (adversarial + distance pairs); PLAY1 needs LOOP1;
  TRAIN1 needs HARV1; TRAIN2 needs TRAIN1 + bench harness + `models.py` redeploy;
  ROSTER1 needs SUB2+HRT1.

### Replacement bridge
LOOP1 consumes the same Episode R produces, so R never sees the change. Old B/P
retires component-by-component as the new one takes its role: `council_agreement`
at HRT1; `multichain.consolidate` default at BIN2; `blue`/`blue_orchestrate`/
`agentic_blue_eval` analysis at LOOP1+BR1; `response_loop` at HND1. Each
retirement is deliberate and leaves the arm working (honest-BLOCKED if a retired
path has no replacement yet).

---

## Grounding contract (per task)

1. Re-verify HEAD and `git log --oneline -3`; treat every verdict as a claim to
   re-confirm. A retrofit that needs a full replace (or vice-versa) is a finding.
2. Rediscover live: R boundary (`exec_chain` red_order, `episode.py`), platform
   `council.py`, the B/P being replaced, `unknown_defense`, `notify_scoreboard`,
   `emergent_gaps`, `rag_mcp` (`kb_ingest`, MLX 8917/8925), `models.py`
   (`ollama create`/Modelfile), `recall_attribution`, `investigation/`,
   `growth_loop`, `capability_graph`, `field_journal`, checks BQ/AZ/BM/BL/BN/BR,
   `config/spine_surfaces.yaml`. TRAIN1 installs and sets up the local training
   toolchain (`mlx_lm.lora` / adapter-fuse / GGUF-convert) as an explicit
   requirement of the phase — it does not exist today and its installation is
   part of the build, not a precondition to discover. The redeploy leg
   (`models.py` `ollama create`/Modelfile) and the feed leg (`rag_mcp
   kb_ingest`) already exist and are wired to it.
3. Re-derive motivating facts at the task's HEAD; record drift.
4. Cousin knowledge in ORG, runtime state in SUB, never the spine. New
   security-core files under existing globs. ORG1 shrinks spine scope. Universal
   indexing invariant: every hunt emission — positive and negative — is indexed.
5. R is directed, never modified. MUT changes which attack runs, not red
   execution. Editing red execution is scope creep — stop and file.
6. Pre-hunt organ recall is enforced in the tool, not left to model discretion.
7. Live gates: BIN/HRT hold BQ/AZ; SC1 must not demote `ANOMALOUS_UNCLASSIFIED`
   below CONFIRMED (BN); HARV1 holds BM; ROSTER1 holds BL. TRAIN2 candidates pass
   the bench gate before any serve; PROMOTE_POLICY=confirm on served models.

---

## Invariants

- **Same/similar/new is the product; known-bad catch is the floor.**
- **`ANOMALOUS_UNCLASSIFIED` is first-class, valued by cousin-distance.**
- **Two cousin surfaces** — spatial (BR-COUSIN) and temporal (BR-DRIFT) — both in
  scope.
- **R is the means and is left alone.**
- **The council is the heart** — reused, made adversarial; vote-adapter replaced.
- **The system compounds through six feeds** — all six built; feeds 4–6 (harvest,
  playbook, train) are first-class, not a tail.
- **Universal indexing** — nothing the hunt emits is un-indexed, positive or
  negative.
- **Pre-hunt recall enforced in the tool**, not model discretion.
- **Static+dynamic pairing** — signature alone is G0; promotion needs the chain
  completed.
- **Consumer-context** — analyst-visible is a real gate, not a word.
- **Confirm-only throughout** — findings, detections, trained models, roster,
  playbook promotions: operator confirms.
- **Code decides, model explains** — distance by code, objection-presence gates,
  models supply content.
- **Honest-BLOCKED over faked-green** — a killed cousin is a correct non-finding;
  a retired path with no replacement blocks honestly; a corpus too small to train
  is a documented non-build (not a skipped feed — the feed exists, the data isn't
  there yet).
- **The spine gets lighter; benches survive as the train gate; label-blind cousin
  grading in production.**

---

## Success criteria

The complete defensive bully exists, hunts cousins, and compounds through all six
feeds:

1. **Phase 1** — a hunt consumes R's Episode, BR grades cousin-distance in ORG, a
   second hunt starts from the enriched neighborhood; a NEW cousin surfaces that
   the old wiki-token matcher scored ~0.
2. **Phase 2** — a manufactured cousin is suspect-by-default, gated G0–G3 (incl.
   static+dynamic and analyst-visible), and the fleet council kills or promotes
   it via unrebutted objection.
3. **Phase 3** — red produces a near-neighbor blue misses within budget and the
   system alarms; drift catches a detection firing differently than baseline.
4. **Phase 4** — far NEW cousin scores ≥ known-bad; ROI selection declines a
   known-benign cell; cost-per-cousin falling; plateau stops an exhausted
   neighborhood.
5. **Phase 5** — a promoted cousin exits as a family-generalizing fix.
6. **Phase 6 — the flywheel closes** — SFT corpus incl. adversarial + distance
   pairs (HARV); playbooks accumulate and shape small-model runs (PLAY); a
   fleet-local LoRA adapter trains from the corpus (TRAIN1), fuses→GGUF→
   `ollama create`→passes the bench gate→serves on confirm (TRAIN2); the council
   reweights on retrospective correctness (ROSTER). Demonstrated end-to-end: a
   hunt's output trains a model that a later hunt uses and that is measurably
   better at smelling cousins.

The criterion is that Portal runs a defensive hunt that alarms on the unknown
cousin, bullies its own findings with the fleet, closes them with
family-generalizing fixes, and **feeds its own output back through all six
mechanisms so the hunt gets smarter and the fleet gets sharper every run** —
including training its own cousin-specialist models on its own hunt history and
serving them. That full loop, demonstrable on the program's own artifacts, is the
design.

---

## Status

Phase 1 — spine
- [ ] SUB1 — State store (known-defence/benign/covered DB, cost ledger)
- [ ] SUB2 — Decision-event log
- [ ] ORG1 — Cousin-space organ (retrofit rag_mcp) + spine shrink + universal-index invariant
- [ ] BR1 — Cousin engine (semantic distance, hybrid explain)
- [ ] LOOP1 — Hunt loop (replaces blue/purple orchestration)
Phase 2 — bin & heart
- [ ] BIN1 — Real gates G0–G3 (static+dynamic G1, analyst-visible G3)
- [ ] HRT1 — Self-bullying fleet council (objection gate)
- [ ] BIN2 — Suspect-by-default
Phase 3 — red as means & second cousin surface
- [ ] MUT1 — Red cousin-generator + mutation budget
- [ ] BRDRIFT1 — Temporal-cousin drift instrument
Phase 4 — discovery, selection, stopping
- [ ] SC1 — Distance-graded discovery scoring
- [ ] TGT1 — ROI + known-defence selection
- [ ] PLT1 — Plateau + compounding-cost meter
Phase 5 — exit
- [ ] HND1 — Family-generalizing detection handoff
Phase 6 — feed/learn/train flywheel
- [ ] HARV1 — Training-pair harvest + SFT corpus
- [ ] PLAY1 — Per-scenario-type playbook memory
- [ ] TRAIN1 — Fleet-local LoRA train step (new leg)
- [ ] TRAIN2 — Fuse→GGUF→ollama-create→bench-gate wired into the loop
- [ ] ROSTER1 — Retrospective council weighting

---

## Beyond the initial build (natural extensions, not deferred scope)

These are genuine future directions the design enables, distinct from the
complete build above:
- **Persistent hunt daemon** — continuous cousin-hunting rather than
  invocation-driven; the loop is built to allow it.
- **Auto-promotion of cousin-specialist models** — once the train→serve loop has
  a track record, a tighter-than-confirm gate.
- **External cadence** — ATT&CK/KEV/SigmaHQ into ORG so new public techniques
  auto-become cousins-to-chase (`response_loop` intake is the seed).
- **Cousin-of-cousin recursion** — recursive neighborhood expansion when plateau
  shows first-order neighborhoods exhaust.
- **Model-catalog spine remediation** — the config-fan-out re-pin tax; separate,
  smaller now that ORG shrinks spine scope.
