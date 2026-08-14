# Handoff — Defensive Bully build program (context for a fresh instance)

## What this is

This document hands off the design work for **the defensive bully**: a
ground-up rebuild of Portal 5's Blue/Purple security capability, taking the
autonomous-hunt concept from `blog.zsec.uk/bullyingllms/` and building it
natively for Portal as a top-tier defensive system. The deliverable already
produced is `BUILD_PROGRAM_DEFENSIVE_BULLY.md` (the complete build program).
This file is the *context* behind that program — what was decided, why, what was
verified against the code, and the traps a fresh instance must not fall back
into.

**Read `BUILD_PROGRAM_DEFENSIVE_BULLY.md` as the spec. Read this to understand
how it was arrived at and what not to undo.**

---

## The one-paragraph thesis

Modern offense doesn't hunt signatures — it hunts the *shape* of a weakness and
chases everything structurally adjacent to it (found the TIFF-parser bug → go
break the SFNT parser for the same class of bug). "Cousins." Same / similar /
new / different. **The defensive bully is the mirror: given everything we know,
surface the cousins we don't** — the near-neighbor attack one mutation from a
covered one that our detection won't catch — and alarm on it, graded by distance
from known. `ANOMALOUS_UNCLASSIFIED` ("cousin-of-X but not X, and nothing catches
it") is the **primary product**, not an edge case. The system **compounds**: it
feeds, learns, and trains on its own hunt history so the twentieth hunt beats the
first, including training its own cousin-specialist models on the local fleet.

---

## Hard-won framing decisions (do not re-litigate these)

These took many iterations to land. A fresh instance will be tempted to undo
them; don't.

1. **The concept is the design; the current RBP code is a parts inventory.**
   Do NOT retrofit the concept onto the existing code as the skeleton. Design
   the concept for Portal, then decide per existing part: REUSE / REFIT /
   REPLACE / NEW. The default for the current Blue/Purple brain is REPLACE.

2. **R (red) is left alone. B/P is the new brain and heart.** Red already
   manufactures attacks in the lab and lands telemetry; the bully *directs which
   attack red runs* (via a mutation-probe) but never modifies red's execution.
   Editing red execution is scope creep. The current ~7,300-line Blue/Purple
   bench-scoring stack is what gets replaced.

3. **This is THE design, not a V1.** All parts are in the initial design.
   "Phases" are build *sequence* only — nothing is deferred to a hypothetical
   V2. The "Beyond the initial build" section lists genuine future extensions,
   which is different from deferred scope.

4. **The feed/learn/train flywheel is first-class, not a tail.** Every earlier
   draft under-built this and it was the repeated correction. Compounding =
   feeding + learning + training. There are **six feeding mechanisms** and a
   real train→redeploy flywheel; all six are in scope from the start (see below).

5. **Cousin discovery is the product; known-bad catch is the floor.** Do not let
   the plan collapse back into "did our detection fire on this known TTP" —
   that's the known-bad trap and it's what the current arm mostly measures.

6. **The council is the heart, made adversarial.** It is NOT a vote-aggregator.
   The concept's "me bullying it → it bullying itself" becomes the fleet of
   models trying to *disprove* a finding before it promotes.

---

## The offense→defense translation (the backbone — keep it intact)

The full 15-row translation table lives in the build program. The critical rows
a fresh instance tends to lose:

- **A finding is a missed/near-missed detection** (red or a cousin landed, blue
  was blind) — not a coverage checkmark.
- **Grammar fuzzing → atomic mutation**: the insight is *structural validity* —
  random bytes get "invalid format"; structurally-valid-but-perturbed inputs
  reach the parser. Defensively: valid TTPs with adversarial params/timing/
  artifacts, not noise.
- **Low-priv gate → SOC-analyst-context gate**: a finding visible only to the
  eval harness's god-view (not the real console under queue load) is not
  promotable.
- **Two cousin surfaces**: spatial (near-neighbor in the knowledge organ) AND
  temporal (a detection drifting from its own baseline — a TTP that evolved into
  a cousin of itself). The temporal one (baseline drift / the "N-1" idea) was
  repeatedly dropped; it is in scope.
- **Hardware maps 1:1**: Ollama fleet = hunter models; Proxmox+Splunk+AD lab =
  hunt range; MCP fleet = tool surface; MLX 8917/8925 = the organ's embed/rerank;
  council = the fleet's self-bullying.

---

## The six feeding mechanisms (all in scope)

1. **Semantic hunt memory (the organ)** — every known-bad, benign pattern, past
   finding, plateau embedded and queried before every hunt. Distance in this
   space IS the cousin metric.
2. **Known-defence / known-benign / known-covered DB** — negative results
   multiplicatively steer future hunts away from waste.
3. **ROI / target intelligence** — risk-reduction-per-cost ranking steers toward
   the biggest blind spot.
4. **Training-pair harvest** — every hunt auto-extracts (evidence → verdict +
   rationale) pairs; the council's adversarial exchanges and cousin-distance
   judgments are the richest signal.
5. **Fleet-local fine-tune** — pairs train a role-specialist model that smells
   cousins better; served back into the fleet.
6. **Per-scenario-type playbook memory** — learned instruction sets per
   investigation class (the defensive per-campaign `CLAUDE.md`); the runtime
   shape a small trained model executes inside.

Feeds 1–3 make the hunt smarter each run; feeds 4–6 make the fleet sharper.

---

## What was VERIFIED against the code (HEAD `ee9272e`, github.com/ckindle-42/portal-5)

A fresh instance MUST re-verify these against its own fresh clone — HEAD wins
over this document. But these were checked and are load-bearing:

**The current RBP arm is a benchmark harness, not a compounding organism.**
- Central object is `BenchConfig`; entry points `run_bench`/`run_blue_chain_tests`/
  `run_blue_orchestration`; output is 62 per-invocation scored JSON files under
  `portal/modules/security/core/results/`. 57 of 70 core `.py` files are
  eval/score/corpus.
- Every run starts cold: the capability graph rebuilds per invocation (no
  persist path); no scheduler; nothing reads prior-run state to change what this
  run does.
- The compounding-shaped modules (`growth_loop`, `response_loop`,
  `continuous_eval`, `capability_graph`, `unknown_defense`, `recall_attribution`)
  are almost entirely **unwired**: `loop.py` references one of them
  (`field_journal`), once, for context only. They are libraries waiting for an
  orchestrator that was never built (`run_growth_loop` has no CLI wrapper).

**The two places the current code CONTRADICTS the concept (must be fixed):**
- `growth_loop.prove_draft` gates are **placeholder-true**
  (`result.fresh_positive = True  # placeholder — real check in lab`). The
  hallucination bin exists in shape only — the gates don't execute.
- `multichain.consolidate` defaults to **clear-by-default** (no signal →
  DISMISS/RULED_OUT). The concept requires **suspect-by-default**.

**What already MATCHES the concept and must be kept:**
- `notify_scoreboard` already scores `ANOMALOUS_UNCLASSIFIED` as a **full catch,
  equal to CONFIRMED** ("surfacing a cousin you can't name" is already a win).
- `PROMOTE_POLICY=confirm` throughout (human at the noise-producing points).
- `investigation/` `EvidenceStore`/`CaseNotebook`: append-only, immutable,
  case-scoped, `supersede` (the demote-equivalent). The seed of persistent state.

**The parts to retrofit (right shape, wrong wiring/corpus):**
- `unknown_defense` (U1–U6) is the **cousin engine in embryo**: EXACT/SIMILAR/NONE
  grading, "possible variant of X," anomaly-vs-baseline, confirmed/variant/anomaly/
  missed outcome space. BUT its similarity is **hand-tuned token-overlap against
  the wiki** (its own comment records it silently scoring ~0 for real variants),
  not semantic distance. Retrofit onto an embedding organ; hybrid explainability
  (embedding finds, feature-overlap explains).
- `rag_mcp` (`kb_ingest`/`kb_search`, local MLX embed 8917 / rerank 8925) is the
  **FAISS-equivalent knowledge organ** — but it indexes a doc folder. Retrofit to
  index hunt memory. This is the concept's knowledge organ; the doc spine is a
  DIFFERENT thing (see spine note below).
- `emergent_gaps` already turns red's **off-script** misses into gaps — red-as-
  cousin-generator in embryo. Retrofit into a deliberate mutation-probe.
- `models.py` already has `ollama create` + Modelfile generation — the **redeploy
  leg** of the training flywheel exists.
- The platform council `portal/platform/inference/router/council.py` (556 lines)
  already carries the adversarial primitive in its data model: every
  `CouncilOpinion` has `strongest_objection` / `missing_evidence` /
  `conditions_to_change`. BUT `aggregate_opinions` **counts votes and discards
  the objections**. Make the objection a promotion gate. The security-side
  adapter `council_agreement.py` (which flattens to a vote) is part of the old B
  and gets replaced.

**The training flywheel — three of five legs already exist:**
- FEED (index corpus): `rag_mcp kb_ingest` — EXISTS.
- REDEPLOY (model into fleet): `models.py ollama create`/Modelfile — EXISTS.
- ACCEPT (gate candidate): the bench harness, repositioned — EXISTS.
- HARVEST (pairs from hunts): build it.
- TRAIN (produce adapter): **genuinely absent** — no `mlx_lm.lora`, no LoRA/
  adapter code anywhere. **Installing/setting up the local training toolchain is
  an owned build step of the TRAIN phase, not a risk to assess.** It doesn't
  exist today = it gets installed; that's a known setup task.

---

## The B/P surface being replaced (honest scope)

~7,300 lines: `blue.py` (2303), `blue_orchestrate.py` (2904), `multichain.py`
(238), `agentic_blue_eval.py` (1226), `analyst_verdict.py` (91),
`council_agreement.py` (199), `response_loop.py` (321). Retired
component-by-component via a **replacement bridge** — the new hunt loop consumes
the same `Episode` red produces, so red never sees the change, and each old
module retires only when its replacement is live (arm stays working every commit;
honest-BLOCKED if a retired path has no replacement yet).

---

## The wiki/spine issue (recurring; understand it precisely)

The operator has flagged the spine as a maintenance chore. The verified reality:

- The **per-file spine era is over** (`TASK_PORTAL_SIMPLIFY_V1` Phase R3
  collapsed ~570 per-file units into manifest surfaces in
  `config/spine_surfaces.yaml`, check BR). `unit-surface-sec-core` covers all of
  `security/core/*.py` under one glob; `unit-surface-investigation` exists too.
  **New files in those globs cost ZERO new units.** Do not claim this program
  will "explode the spine" — false.
- The **real spine tax** is re-pin churn: ~190 hand-authored model-catalog/module/
  readme units each cite `config/portal.yaml` + `config/backends.yaml`, which
  change on every model-fleet action, so one config edit stales ~190 units and
  forces a mass hand re-pin (18 of the last 60 commits are `chore(spine):
  re-pin`). This is a **model-catalog citation-fan-out problem, separate from
  this program**, and content-digest pinning would NOT fix it (the config
  genuinely changes). It is explicitly out of scope; noted as a separate task.
- **What this program does about the spine:** the hunt-knowledge organ (embedded
  hunt memory) is the concept's knowledge store — NOT the doc spine. Once the
  organ exists, the doc spine **shrinks to design-facts-only** and stops being a
  knowledge dumping ground. Runtime hunt state lives in the persistent substrate
  and the organ, never the spine. At most one design-fact unit per phase, inside
  existing globs.
- **Do NOT confuse the doc spine with the knowledge organ.** They are different
  organs. The spine is hand-pinned human-audited design docs (checks AW/BR/BS/AJ).
  The organ is the auto-fed semantic hunt memory. The concept needs the latter;
  Portal has the infra (`rag_mcp`) pointed at the wrong corpus.
- **The retired doc-ledger:** memory snapshots may say `docs/.doc_ledger.yaml` +
  `check AL. doc currency` exist. They DON'T at HEAD — the ledger was retired,
  `AL` is now "capability index consistency," doc currency is check `AW`. Verify
  before citing.

---

## Live validation gates to respect (verified present at HEAD)

`scripts/validation/*.py` registers ~60 checks. The ones this program must hold
green (verify at your HEAD):
- **BQ** benign alert-fatigue semantics · **AZ** detection recall vs emergent
  corpus — the alert-bin phases must not regress these.
- **BM** recall-attribution label-blind boundary — the harvest must stay
  label-blind (production cousin-grading may not read the eval answer key).
- **BL** council participation floor (non-voter counts against quorum) — roster
  weighting must respect it.
- **BN** hunt-and-notify scoreboard semantics — distance-scoring must not demote
  `ANOMALOUS_UNCLASSIFIED` below `CONFIRMED`.
- **BR** spine coverage ratchet · **AW** wiki facts current — don't add
  high-fan-out units.

`P5-SEC-BENIGN-CORPUS-001` is RESOLVED (2026-07-30) for the representative
corpus; the alert bin's G2 not-benign gate is its concept-native home. Do NOT
re-open it.

---

## Traps this conversation fell into (so you don't repeat them)

1. **Feature-presence instead of concept-fit.** A placeholder that returns `True`
   is "present" but the promotion spine is theater. Measure whether our version
   *embodies* the concept, not whether the word matches.
2. **Retrofitting onto the current code as the skeleton.** The concept is the
   skeleton; the code is inventory.
3. **Under-building the flywheel.** "Note it and move on" is the failure. Feeds
   4–6 (harvest, playbook, train) are first-class.
4. **Collapsing to known-bad coverage.** Cousins/same-similar-new is the product.
5. **Losing the temporal cousin (baseline drift), the consumer-context gate, and
   the atomic-mutation structural-validity insight** — all repeatedly dropped
   across rewrites. They are in the final and must stay.
6. **Inventing spine problems** (unit explosion) or **wrong spine fixes**
   (content-digest pinning). Get the real tax right (model-catalog fan-out) and
   keep it out of scope.
7. **Over-hedging known setup tasks as risks.** The training toolchain not
   existing = install it as part of the build, not "discover if it's possible."
8. **Trusting stale memory over HEAD.** Re-clone, `git log --oneline -3`, verify
   symbols live. Several memory facts (doc-ledger, check letters) are stale.

---

## Working method for the next instance

- The project uses self-contained task files (`TASK_*.md`) that a coding agent
  executes autonomously on the live system. Claude authors task files / review
  docs; it does not apply changes directly. `PROMOTE_POLICY=confirm` — nothing
  promoted/deleted without operator action.
- Fresh clone every session; HEAD wins over memory; `git log --oneline -3` after
  cloning to orient. Re-verify every symbol against live code before trusting any
  claim in the build program or in this handoff.
- Repo: `github.com/ckindle-42/portal-5`. Portal 5 is self-hosted on an M4 Pro
  Mac Mini (64GB). Ollama is the sole chat inference backend; MLX for audio/
  embed/rerank/transcription (embed 8917, rerank 8925). ~24 MCP servers on
  8910–8931. Security lab: Proxmox + Splunk SIEM + AD, subnet 10.10.11.0/24.
- The build program's phases each become one or more `TASK_*.md` files. Phase 1
  (SUB1→SUB2→ORG1→BR1→LOOP1) is the hard gate; nothing lands before LOOP1, which
  is where the old Blue/Purple orchestration is replaced.

---

## Deliverables in hand

- `BUILD_PROGRAM_DEFENSIVE_BULLY.md` — THE complete build program (the spec):
  thesis, full 15-row offense→defense translation + hardware mapping, the six
  feeds, all components (substrate, organ, cousin engine, drift instrument, hunt
  loop, alert bin, self-bullying council, mutation-probe, scoring, target
  selection, plateau/cost meter, handoff, harvest, playbook, train, roster),
  parts inventory, 6-phase build sequence, dependency spine, replacement bridge,
  grounding contract, invariants, success criteria, status checklist.
- This handoff context file.

Next concrete step when work resumes: author the Phase-1 task files, starting
with SUB1 (persistent state store on `EvidenceStore`) — the gate everything
else depends on — after a fresh clone and HEAD verification.
