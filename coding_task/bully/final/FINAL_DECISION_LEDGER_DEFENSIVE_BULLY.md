# FINAL DECISION LEDGER — Defensive Bully

Every major final architectural choice, derived from the three source plans
(K3 / O48 / SOL) plus repository evidence at HEAD
`47d3e884c8f0415ed26dbf77f5e817a22ce613ac`. This ledger explains **why** the
final design differs from each source plan. Comparative evidence:
`FINAL_COMPARATIVE_REVIEW_DEFENSIVE_BULLY.md`. Normative design:
`FINAL_DESIGN_DEFENSIVE_BULLY.md`.

---

## DEC-01

TOPIC: Product definition and thesis

K3 POSITION: Cousin discovery is the product; `ANOMALOUS_UNCLASSIFIED` is
first-class; known-bad catch is the floor.
O48 POSITION: Same; emphasizes "reorient, don't rebuild" — Portal already
computes the miss primitive (`episode.derive_verdict` FAILED).
SOL POSITION: Same thesis, but the product is precisely `(SIMILAR|NEW) ×
(NEAR_MISS|MISSED)`; `SAME×MISSED` is a regression.

SHARED GROUND: The thesis is identical across all three and inherited from the
prior build program: surface the cousins we don't know, graded by distance
from known.

KEY DIFFERENCES: Only the *operational* definition of the product band
(DEC-02).

REPOSITORY EVIDENCE: `episode.py:146-183` (FAILED = red-landed-blue-missed,
synthetic never PROVEN at :171-172); `notify_scoreboard.py:21`
(ANOMALOUS_UNCLASSIFIED is a catch); BN check
(`scripts/validation/blue_orchestration.py:1289-1348`).

ANALYSIS: Unanimous + code-supported. O48's observation that the miss
primitive already exists in code strengthens feasibility; SOL's 2-D product
band sharpens it.

FINAL DECISION: Adopt the shared thesis verbatim: **unknown-cousin discovery
is the product; known-bad detection is the floor; ANOMALOUS_UNCLASSIFIED is
first-class, valued by cousin distance.** The finding seed is the existing
deterministic Episode miss verdict (FAILED) and cousin grading, not a new
primitive.

WHY THIS IS BETTER: Keeps the concept's product framing intact while anchoring
it in a verified deterministic code primitive.

WHAT WAS REJECTED: Nothing.

CONFIDENCE: HIGH.

---

## DEC-02

TOPIC: The cousin model (grade space, distance composition, novelty control)

K3 POSITION: Five-dimension composite `D = w1·semantic(.30) + w2·attack(.20) +
w3·telemetry(.20) + w4·behavior(.20) + w5·detection(.10)`; bands τ_same .15 /
τ_similar .45 / τ_new .70; discriminator-contradiction veto; per-dimension
decomposition; ANOMALOUS = not-SAME/SIMILAR-to-covered ∧ detection-blind ∧
benign-deviant (**the product**); NEW = distance band, neighborhood-anchored.

O48 POSITION: Five axes (behavioral-sequence, ATT&CK-graph via MITRE MCP,
telemetry-shape, detection-response, semantic); NEW = near ATT&CK/behavioral ∧
large detection-response distance (**the product**); ANOMALOUS = resists
all-axis classification; detection-response movement separates real novelty
from arbitrary semantic distance.

SOL POSITION: Two axes. Structural `D = .30·behavior + .25·event_telemetry_graph
+ .15·semantic + .15·attack_graph + .15·context_topology` (detection-response
**excluded**); relationship grades SAME ≤.10 / SIMILAR ≤.35 / NEW .35–.60 /
DIFFERENT >.60 / ANOMALOUS = unplaced credible anomaly; ≥2 non-semantic
channels required for SIMILAR/NEW; candidate absence never establishes
novelty; defense response is an independent axis
(COVERED/NEAR_MISS/MISSED/INDETERMINATE); product = `(SIMILAR|NEW) ×
(NEAR_MISS|MISSED)`; `SAME×MISSED` = regression.

SHARED GROUND: Multi-dimensional, code-computed, feature-explained; semantic
similarity alone is never a cousin; detection response is the novelty signal
that matters; U1's lexical overlap survives only as the explanation layer.

KEY DIFFERENCES: (a) Is detection-response *inside* the distance (K3/O48) or a
separate axis (SOL)? (b) Which grade is "the product" — ANOMALOUS (K3) or NEW
(O48) or a 2-D band (SOL)? (c) Weights — K3's semantic-heavy (.30) vs SOL's
structure-heavy (.30 behavior).

REPOSITORY EVIDENCE: `episode.py::DetectionCorrelation:80-106` (rule/hit/
row_count/window/target — the response axis's data); `spl_detections.yaml`
(discriminator_tokens, 11 sibling_ids links, spl_variants);
`unknown_defense.py:112-128` (lexical containment scored a real variant 0.09 —
documented failure); `spl_backend.py::query_episode:161-205` (label-blind
episode-scoped telemetry for field signatures); MITRE MCP :8929 live.

ANALYSIS: SOL's critique is decisive on (a): if detection-response contributes
to D, then an unrelated attack our detection misses becomes *distant* — and
distance is the novelty currency — so a blind spot manufactures "cousins" of
whatever it is compared against. Relationship and coverage are independent
questions. On (b): the concept's own text names ANOMALOUS_UNCLASSIFIED the
primary product, and BN makes it a catch; but O48's NEW (near + detection
misses) is the *directional* discovery case the mutation engine targets. Both
are products of the 2-D band; neither alone suffices. On (c): semantic text is
the weakest adjudicator (U1's failure) though the best retriever — SOL's
structure-dominant weights are safer; K3's .30 semantic lets vocabulary drive
grading.

FINAL DECISION: **Two-axis cousin model.** Axis 1 — structural relationship:
`D = .30·behavior_sequence + .25·telemetry_event_shape + .15·semantic +
.15·attack_graph + .15·context_topology` over canonical BehaviorSignatures,
with vetoes (discriminator contradiction downgrades; ≥2 non-semantic channels
required for SIMILAR/NEW; missing dimensions never renormalized). Bands:
SAME (fingerprint or D≤τ_same=.10 ∧ discriminators match), SIMILAR (D≤.35 ∧
two channels ∧ meaningful delta), NEW (.35<D≤.60 ∧ two channels ∧
security-relevant delta), DIFFERENT (D>.60 ∨ no family relation),
ANOMALOUS_UNCLASSIFIED (credible anomaly without stable family placement).
Axis 2 — defense response: COVERED / NEAR_MISS / MISSED / INDETERMINATE
derived in code from DetectionCorrelation + Episode verdict machinery.
**Product = (SIMILAR|NEW)×(NEAR_MISS|MISSED), and ANOMALOUS×blind remains
first-class (the concept's product; BN catch); SAME×MISSED is a detection
regression — high priority, not a discovery.** Every grading emits the full
per-dimension decomposition + feature-overlap citations + nearest-known refs.

WHY THIS IS BETTER: Resolves the three-way grade fork without voting; removes
the miss-inflates-distance failure mode none of K3/O48 avoided; preserves the
concept's ANOMALOUS product status; gains the regression case; keeps every
anti-astrology control all three independently invented (veto, two-channel
rule, response-axis arbiter).

WHAT WAS REJECTED: K3's detection-response-inside-D; O48's NEW-vs-ANOMALOUS
boundary; K3's semantic weight .30; pure-embedding grading (all three rejected
this already).

CONFIDENCE: HIGH.

---

## DEC-03

TOPIC: Persistent substrate (SUB)

K3 POSITION: NEW `hunt_state.py`; SQLite WAL at `PORTAL5_HUNT_DIR`
(default `/Volumes/data01/portal5_hunt/`); 15 tables; supersede never deletes;
append-only decision log; idempotent natural keys.
O48 POSITION: `core/substrate/` package seeded from the investigation store
pinned durable + capability_graph entities; seven-memory-kinds invariant;
SourceAuthority.
SOL POSITION: One migration-managed SQLite WAL authority; content-addressed
evidence; hash-chained decision events; transactional outbox; trust tiers;
retention classes; leases/CAS.

SHARED GROUND: NEW durable store; append-mostly; supersede-not-delete;
provenance on everything; the investigation-store schema/pattern is the seed,
not the store.

KEY DIFFERENCES: Rigor of the transaction model (SOL ≫); env convention
(PORTAL5_HUNT_DIR vs PORTAL_DATA_DIR); package layout.

REPOSITORY EVIDENCE: `evidence.py:111-119` (in-memory), `case_notebook.py:53`
(:memory: default; supersede :162; seven kinds :1-17);
`PORTAL5_LANCE_DIR` convention (`rag_mcp.py:33`, `memory_mcp.py:27`).

ANALYSIS: SOL's machinery (outbox, leases, idempotency keys, trust tiers) is
what makes the compounding claims auditable and crash-safe; K3's env
convention follows the existing naming; O48's seven-kinds + SourceAuthority
map cleanly onto SOL's trust tiers.

FINAL DECISION: One migration-managed SQLite WAL authority at
`PORTAL5_HUNT_DIR/hunt_state.db` (new env var, default
`/Volumes/data01/portal5_hunt/`, following the `PORTAL5_LANCE_DIR`
convention); content-addressed evidence references; append-only hash-chained
decision events; supersede-never-delete; idempotent natural keys + CAS
coordination fields; trust tiers `VALIDATED / OPERATOR_CONFIRMED / SUSPECT /
IMPORTED_UNVERIFIED / SUPERSEDED`; retention classes
AUDIT/EVIDENCE/DERIVED/TRAINING; the seven-memory-kinds doctrine honored
(no agent long-term memory at inference). Seeded from the EvidenceRecord
schema + CaseNotebook SQLite/supersede pattern.

WHY THIS IS BETTER: SOL's rigor at K3's convention cost; O48's doctrine
preserved as data policy.

WHAT WAS REJECTED: SOL's `${PORTAL_DATA_DIR}` (invents a second convention);
any reuse of the in-memory stores as authority.

CONFIDENCE: HIGH.

---

## DEC-04

TOPIC: Knowledge organ (ORG)

K3 POSITION: NEW `hunt_organ.py` on existing infra (LanceDB, :8917, :8925);
record-level API, raw cosine distance, provenance classes; rag_mcp untouched.
O48 POSITION: RETROFIT rag_mcp — new hunt-memory corpus + thin wrapper;
retrieval internals unchanged.
SOL POSITION: Security-owned rebuildable LanceDB projection; SQL is authority;
outbox-coupled indexing; recall receipts; stale-row rejection.

SHARED GROUND: Same infra (LanceDB + embed :8917 + rerank :8925); hunt corpus
distinct from doc corpus; mandatory pre-hunt recall + universal indexing
enforced in code; rerank scores are never the cousin metric.

KEY DIFFERENCES: Whether ORG is "a rag_mcp retrofit" (O48) or a new
security-owned module (K3/SOL); transactional guarantee depth (SOL).

REPOSITORY EVIDENCE: `rag_mcp.py:60-80` (chunk schema), `:216-310`
(directory ingest), `:412-464` (returns rerank_score only — no distances, no
metadata filters, no record-level upsert); `embedding-server.py:37-51` (CPU
sentence-transformers harrier — batch upserts); `reranker_mcp.py:30` (MLX
Qwen3 reranker).

ANALYSIS: O48's retrofit cannot yield distances or record-level filters
without bypassing the MCP API — i.e., it becomes K3/SOL's module anyway. The
infantry reuse is real (LanceDB, services, fallback patterns); the corpus and
API are new.

FINAL DECISION: ORG is a new security-owned module (in the bully package)
owning the `hunt_memory` LanceDB projection under the existing LANCE dir.
Raw cosine distances returned; record-level upsert keyed by content-derived
record_id; metadata/provenance/trust-tier filters; batch embedding; reranker
for presentation only, with dense fallback. Indexing is coupled to SUB by a
**transactional outbox** — a required unindexed emission blocks hunt closure
(dead-letter remediation is operator-visible). Pre-hunt recall is mandatory
and produces a **RecallReceipt**; downstream consumers record a
**DecisionImpact**. rag_mcp/memory_mcp are untouched independent services.

WHY THIS IS BETTER: K3's correct API shape + SOL's auditability + O48's
infra-reuse instinct, all honored; the "retrofit rag_mcp" framing is dropped
because the code refutes it.

WHAT WAS REJECTED: O48's rag_mcp-corpus retrofit; any use of rerank scores as
distance; spine/wiki as runtime memory.

CONFIDENCE: HIGH.

---

## DEC-05

TOPIC: The hunt loop (LOOP)

K3 POSITION: NEW `hunt_loop.py`; platform agent loop evaluated and rejected;
blue_orchestrate section machinery reused as the investigation arm.
O48 POSITION: RETROFIT `loop.py` + `loop_cli.py`; COMPOSE
`portal/platform/agent` decide/rank.
SOL POSITION: Platform `run_loop` as a bounded inner executor (after adding
budget hooks); a security-owned orchestrator owns stages, transactions,
recovery.

SHARED GROUND: The loop enforces recall-before-direction and indexing-after
in code; hard budgets; checkpoint/resume; honest-BLOCKED.

KEY DIFFERENCES: Build-new vs retrofit-loop.py vs compose-platform-loop.

REPOSITORY EVIDENCE: `loop.py:176-216` (playbook runner; journal recall feeds
only `len(prior)` into reports — `:452,471`); `platform/agent/loop.py:30-89`
(generic bounded decide/execute/fold; enforces only max_iterations +
max_wall_clock_sec — **no max_lab_actions**); `blue_orchestrate.py` section
runners (`:496,662,1098,1263`), `_run_three_section:1970`,
`capture_expert_handoff:1779`; `spl_backend.py::query_episode:161-205`.

ANALYSIS: The hunt iteration is a fixed stage pipeline (LOAD→RECALL→SELECT→
DIRECT→INVESTIGATE→GRADE→GATE→RECORD→STOP?), not an open-ended
decide-execute-fold search — K3's rejection of the platform loop as base is
sound. But loop.py's operational discipline (caps incl. lab actions,
checkpoint/resume, notify-with-resume-cmd) is exactly what a new loop must
reproduce — O48's respect for it is sound. SOL's insistence that the
orchestrator itself enforces every budget (incl. lab actions) is the verified
gap of both existing loops.

FINAL DECISION: LOOP is a NEW security-owned orchestrator in the bully
package implementing the stage pipeline with SUB-transactional state, leases,
and idempotent re-drive (SOL); it enforces the full budget triple
(iterations / wall-clock / lab-actions) itself (SOL's correction); it carries
loop.py's checkpoint/resume and notify-with-resume-command discipline via the
existing notification dispatcher (O48); its per-Episode investigation arm
reuses blue_orchestrate's section runners over the label-blind
`query_episode` haystack (K3). Platform `run_loop` is not used as the base
(decision recorded: evaluated, rejected — K3); `loop.py`/`loop_cli.py` remain
the red-side engagement runner, untouched. CLI surface: a `hunt` subcommand
following the `__main__.py` dispatch pattern.

WHY THIS IS BETTER: Combines all three plans' verified strengths; avoids both
the under-powered generic loop and the over-credited engagement loop.

WHAT WAS REJECTED: O48's compose-on-platform.agent as the base; any edit to
loop.py's red-side behavior; a hunt daemon (documented future extension).

CONFIDENCE: HIGH.

---

## DEC-06

TOPIC: Alert bin (BIN) — gates, ordering, state machine

K3 POSITION: SUSPECT → G0 evidence (observed-origin) → G1a static replay →
G1b dynamic re-execution → G2 not-benign → HEART → G3 analyst-visible
(triage lane) → PENDING_OPERATOR → PROMOTED|KILLED.
O48 POSITION: G0 → G1 (clean-snapshot re-run; static+dynamic) → G2 benign
corpus → G3 console visibility → then HEART.
SOL POSITION: G-1 authorization → G0 evidence integrity → G1 reproduction
(fresh + clean replay or 2-of-3) → G2 causality/alternatives → G3 SOC
visibility (consumer-query receipt) → G4 adversarial clearance → G5 operator;
append-only state machine; new evidence ⇒ new alert version.

SHARED GROUND: Suspect-until-proven; executable gates; static+dynamic pairing;
benign discipline (BQ); analyst-visibility measured; operator confirms.

KEY DIFFERENCES: Gate inventory (SOL adds authorization + causality); council
placement (K3: before SOC; SOL: after SOC; O48: after all gates); SOC
semantics precision.

REPOSITORY EVIDENCE: `telemetry.py:26-37` (OBSERVED_EVIDENCE_ORIGINS);
`capture_recipes.py` (deterministic re-execution); `capture_store` (replay);
`benign_corpus_bench.py`; `blue_orchestrate.py:91-103`
(_VERDICT_GROUNDING_POLICY counter-evidence); `siem/blue_triage.py:38-80`
(the G3 measurement lane); BQ check.

ANALYSIS: SOL's gate inventory is the most complete — authorization before
creation and causality-with-controls before visibility are real proof
obligations the other two fold into neighbors. K3's G1a/G1b split is the
right reproduction structure (static = signature on replayed capture; dynamic
= behavior chain re-executed). On ordering: running the SOC lane *before*
adversarial clearance (SOL) writes unvetted candidates to an analyst-visible
surface — that fights BQ (alert fatigue); the council is also cheaper than
the lane. K3's order (council, then SOC) is correct; SOL's state machine
formalism and version-invalidation rule are adopted regardless of order.
G3 semantics: SOL's delivery-receipt precision (the *Bully finding's*
delivery is validated, not the missed detector) + K3's measurement vehicle
(the existing triage lane under a queue-load corpus, priority/SLA).

FINAL DECISION: BIN owns an append-only promotion state machine:
`CREATED(SUSPECT) → EVIDENCE_READY(G0) → REPRODUCED(G1a+G1b) →
CAUSALLY_VALIDATED(G2) → ADVERSARIAL_CLEAR(G4/HEART) → SOC_VISIBLE(G3) →
AWAITING_OPERATOR → PROMOTED`; terminals DISPROVED / BENIGN / BLOCKED /
SUPERSEDED. Gates: G-1 authorization (scope, mutation class, budgets —
recorded pre-creation); G0 evidence integrity (≥1 observed-origin ref,
manifest + hashes, healthy telemetry; synthetic never passes); G1a static
replay (candidate signature fires on the replayed capture, right window +
target); G1b dynamic re-execution (capture_recipes where one exists, else
directed red re-run within MUT budget; expected artifact contract; 2-of-3
nondeterministic policy where declared); G2 causality/not-benign (matched
benign/telemetry/environment controls + benign-corpus zero-fire + verdict-
contract counter-evidence); HEART (G4) falsification council; G3 SOC
visibility (candidate shipped as a notable; the blue_triage lane runs under
the queue-load corpus; pass = consumer-side report ≤ configured priority
within SLA with content intact); G5 operator promotion. Changed evidence
creates a new alert version and invalidates downstream passes.

WHY THIS IS BETTER: SOL's completeness + K3's ordering and measurement
vehicle + O48's snapshot discipline; BQ-safe by construction.

WHAT WAS REJECTED: SOL's council-after-SOC ordering; O48's council-last
placement; any signature-only promotion.

CONFIDENCE: HIGH.

---

## DEC-07

TOPIC: The self-bullying council (HEART)

K3 POSITION: New `heart_council.py` in security core; platform mechanics
reused; falsification seats (≤1/model family); deterministic materiality
(evidence contradiction ∨ covering detection ∨ benign counter-evidence);
unrebutted material objection blocks; rebuttal round; votes never promote;
participation floor = validity floor.
O48 POSITION: Objection gate beside `aggregate_opinions` (new
`council_objection.py` in the platform router); materiality = names missing
evidence/unmet condition checked in code; unrebutted material ⇒ BLOCK,
**otherwise the vote/quorum result stands**; council_agreement refactored not
discarded.
SOL POSITION: New adversary module; durable objection objects with enumerated
materiality categories; rebuttal → re-review of the same evidence version;
withdrawal by originating seat; **operator waiver as a separate audited
command**; ≥2 independent model families; ROSTER reliability never outweighs
a veto.

SHARED GROUND: Platform council execution/isolation/parse/participation
reused; `aggregate_opinions` untouched; objections gate promotion;
participation floor is a validity floor (BL); dissent persisted.

KEY DIFFERENCES: Placement (platform dir vs security core); residual role of
votes (O48 keeps them as a pass condition; K3/SOL reject); objection
lifecycle depth (SOL ≫).

REPOSITORY EVIDENCE: `council.py:77-96` (opinion fields), `:147-187`
(parse_opinion), `:190-237` (aggregate_opinions counts votes, ESCALATEs on
sub-floor — never reads objections); `council_agreement.py:44-66` (adapter
never populates objection fields); BO/BL/BE/BP checks exist.

ANALYSIS: Placement: the platform primitive must stay general (all three
agree); a security-specific gate inside the platform tree (O48) violates that
instinct — security-core placement (K3/SOL) wins. Votes: O48's
"objection-gate-else-vote" keeps a democratic pass condition the concept
explicitly rejects ("adversarial, not democratic"); the promotion condition
is the *absence of unrebutted material objection* with participation above
floor — votes are telemetry. SOL's durable-objection lifecycle (rebuttal
re-review, seat withdrawal, operator waiver) is the audit machinery the
concept's "it bullying itself" needs at fleet scale.

FINAL DECISION: HEART is a new module in the bully package. Seats are
role-typed falsifiers (evidence-integrity, causal/benign-alternative,
detection-engineering, SOC-consumer, safety/scope), ≥3 seats, ≥2 independent
model families, isolated, same frozen evidence packet. Platform council
execution/parse/participation mechanics are reused; `aggregate_opinions` is
untouched. Objections are durable objects; materiality is code-validated
against enumerated categories (evidence contradiction, covering-detection id,
benign counter-evidence per the verdict contract, scope/safety,
reproducibility, telemetry health, classification, analyst visibility,
regression risk). An unrebutted material objection blocks; rebuttal requires
cited evidence and a falsification re-pass on the same evidence version;
withdrawal by the originating (or equally independent) seat; an authorized
operator may waive with a reason — a separate audited command, visible in the
handoff. Participation floor is a validity floor (BL); sub-floor → operator
escalation, never auto-pass. Vote counts are recorded for telemetry only.
`council_agreement.py` and `multichain.py` are LEFT ALONE on the legacy bench
lane; HEART does not route through them.

WHY THIS IS BETTER: The concept's falsification semantics with fleet-scale
audit machinery; zero regression risk to the platform primitive and the
legacy bench lane.

WHAT WAS REJECTED: O48's platform-dir placement and vote-fallback; any use of
`aggregate_opinions` as the Bully's decision; council_agreement refactor
(unnecessary — it stays legacy).

CONFIDENCE: HIGH.

---

## DEC-08

TOPIC: Mutation (MUT)

K3 POSITION: MutationSpec {base_scenario, variant_params{timing, tool_args,
artifacts, sub_technique_adjacency[], evasion_directive}, target, budget,
artifact contract} consumed via scenario overlay; three seeds (overlay,
evasion-feedback channel `blue.py:2185-2214`, capture_recipes) +
emergent_gaps; budget in code.
O48 POSITION: Scenario-dict perturbation across ten dimensions (params,
timing, ordering, command form, lineage, identity/host, protocol, artifact/
encoding, sub-technique); budget dial; emergent_gaps + response_loop
reverse-gen seeds.
SOL POSITION: Typed MutationPlan with invariants, expected deltas,
observables, matched controls, replay policy, cleanup, risk, approval;
code-validated, compiled to Red orders; operator confirms new/widened
classes; multi-dimension mutations need constituent controls (causal
isolation).

SHARED GROUND: Structural validity + adversarial variation (the grammar-
fuzzing insight); scenario data as the only bully→Red interface; budget in
code; scope guard unchanged; Red execution never edited.

KEY DIFFERENCES: Formality of the plan object; operator-approval surface;
control requirements.

REPOSITORY EVIDENCE: `exec_chain.py::_prepare_scenario:3071-3151` (scenario
dicts are data; set_scenario loads them); `SCENARIOS:221` + mission merge
`:2332`; `fallback_techniques` (`:2722-2723`); `blue.py:2185-2214` evasion
feedback; `capture_recipes.py`; `emergent_gaps.py:32-80`;
`response_loop.py` reverse-gen; `perception.py:17,46-53` (LAB_CIDR guard).

ANALYSIS: All compatible. SOL's typed plan + validation + approval-for-new-
classes is the safety formalism; K3's overlay mechanics + seed inventory is
the implementation path; O48's dimension list is the operator vocabulary.

FINAL DECISION: MUT emits typed **MutationPlans** (operators: ordering,
technique/sub-technique substitution, protocol/transport, identity/privilege,
host/topology, timing, artifact form, observable-behavior) with declared
invariants, expected deltas/observables, matched controls, replay policy,
cleanup, and approval references. Code validates (unknown operator, invariant
conflict, unauthorized target/tool, missing control/evidence → reject) and
compiles to a scenario overlay dict consumed by the unchanged Red machinery.
Budgets in code (`max_variants_per_neighborhood`, `max_perturbation`).
`perception.assert_in_lab` unchanged. Operator confirms any new/widened
mutation class. Seeds: emergent_gaps (off-script supply), evasion-feedback
channel (detection-feedback directive), fallback_techniques, response_loop
reverse-gen, capture_recipes (deterministic re-execution). A required Red
edit is a stop-and-file condition.

WHY THIS IS BETTER: SOL's safety formalism over K3's verified mechanics with
O48's operator vocabulary; all five seeds wired.

WHAT WAS REJECTED: Free-text/shell mutation; model-driven scope expansion;
multi-dimension mutation without controls.

CONFIDENCE: HIGH.

---

## DEC-09

TOPIC: Temporal cousins (BR-DRIFT)

K3 POSITION: drift_gate machinery retargeted to per-detection baselines;
four classes; DEGRADATION = weaker/later/partial firing; EVOLUTION =
behavior shifted, technique persists → routed to BR-COUSIN.
O48 POSITION: Same retarget; EVOLUTION = weaker/later/partial with sources
intact; DEGRADATION = rule/version changed (lineage event); model-canary
holds the model constant.
SOL POSITION: Matched baselines keyed by procedure family/detection-version/
environment/telemetry-schema; rolling median/MAD + EWMA + distribution tests;
three consecutive breaches (or configured critical breach); deterministic
attribution order: telemetry → environment → attacker → detection →
UNCLASSIFIED; baselines reset on version change.

SHARED GROUND: drift_gate engine seed; temporal cousin = detection drifting
from its own baseline; telemetry failure is ops, not a cousin.

KEY DIFFERENCES: Class boundary semantics (what "degradation" means);
attribution rigor.

REPOSITORY EVIDENCE: `drift_gate.py:35-51` (TRACKED_METRICS, NOISE_FLOOR .03,
MIN_BASELINE_RUNS 3, WINDOW 7, scipy, canary; flags-never-verdicts);
`drift_cli.py` (drift-check + model-canary CLIs).

ANALYSIS: O48's "degradation = rule/version changed" and K3's "evolution =
behavior shifted" are the defensible class boundaries; O48's
"evolution = weaker/later/partial" conflates degradation symptoms with
attacker change; K3's "degradation = weaker/later/partial" lacks the lineage
discriminator. SOL's deterministic attribution order + matched controls +
reset-on-version-change is the rigorous frame. Model-canary (O48) prevents
model drift being misread as attacker evolution.

FINAL DECISION: BR-DRIFT maintains per-detection rolling baselines in SUB
(fire rate, hit latency, row shape, clause-level partial satisfaction,
sourcetype completeness), keyed by detection/version + environment +
telemetry schema, using drift_gate's statistics. Deterministic attribution
order: (1) sourcetype collapse/index gaps → TELEMETRY_DEGRADATION (ops);
(2) environment fingerprint/population shift → ENVIRONMENT_CHANGE;
(3) behavior/fields shifted, technique persists, controls healthy →
ATTACKER_EVOLUTION — the temporal cousin, routed to BR-COUSIN for spatial
grading and the bin; (4) stable attack signature + degraded/changed rule →
DETECTION_DEGRADATION (tuning lead, detection lineage event); (5) else
UNCLASSIFIED. Model-canary evidence holds the model constant. Version changes
reset baselines through explicit supersession. Three consecutive breaches or
a configured critical breach to alert.

WHY THIS IS BETTER: SOL's attribution rigor + corrected class semantics from
the K3/O48 clash + O48's canary control, all on verified existing machinery.

WHAT WAS REJECTED: K3's and O48's individual class-boundary readings;
model-chosen cause codes.

CONFIDENCE: HIGH.

---

## DEC-10

TOPIC: Scoring (SCORE)

K3 POSITION: REUSE+EXTEND notify_scoreboard; ANOMALOUS == full catch; add
distance-graded discovery axes.
O48 POSITION: Distance-weighted value; far NEW ≥ known-bad; "never demote
ANOMALOUS below CONFIRMED (BN)".
SOL POSITION: Calibrated target value/cost/outcome scoring.

SHARED GROUND: notify_scoreboard semantics preserved; distance-graded
discovery value added; BN stays green.

KEY DIFFERENCES: Precise BN semantics.

REPOSITORY EVIDENCE: `notify_scoreboard.py:21` (catch set), `:32-37` (trust
ordinal, ordinal-only); BN check (`blue_orchestration.py:1289-1348`: anomaly
is an Axis-1 catch ∧ confirmed-correct > honest-anomaly > confirmed-wrong).

ANALYSIS: The code carries two axes already (catch, trust). The plans' shared
goal — a far NEW cousin out-values a known-bad catch — is a **third** axis
(discovery value). K3's "equal to CONFIRMED" and O48's "never below
CONFIRMED" are both imprecise readings of BN; what BN requires is: anomaly
remains a catch, and the trust ordinal stays confirmed-correct >
honest-anomaly > confirmed-wrong.

FINAL DECISION: SCORE keeps notify_scoreboard's catch semantics and trust
ordinal untouched (BN green) and adds a separate **discovery-value axis**:
value grows with cousin distance and product band (SIMILAR×miss <
NEW×miss < far-NEW×miss; ANOMALOUS×blind first-class). A far NEW cousin can
exceed a known-bad catch *in discovery value*; nothing reorders the trust
ordinal. Benign false-flags stay typed for BQ.

WHY THIS IS BETTER: Satisfies every plan's intent without violating the
verified check semantics.

WHAT WAS REJECTED: Both plans' imprecise BN paraphrases.

CONFIDENCE: HIGH.

---

## DEC-11

TOPIC: Target selection (TGT) and ROI

K3 POSITION: value × Π known-state penalties / cost; all factors from
SUB/ORG; declines logged.
O48 POSITION: risk-reduction-value / test-cost; multiplicative
deprioritisation; uncertainty-as-targeting signal (council dissent → TGT).
SOL POSITION: Hard eligibility gates first; Beta posteriors with conservative
lower bounds; correlated signals never double-multiplied; known-state adjusts
the posterior (not another multiplier); versioned pricing; missing cost
blocks ROI; deterministic tie-break; full candidate/exclusion recording.

SHARED GROUND: Pessimistic value/cost ranking; known-benign/covered/dead
cells steer away; everything logged.

KEY DIFFERENCES: Statistical rigor; eligibility as gates vs features;
double-counting risk.

REPOSITORY EVIDENCE: nothing persists today (all three agree);
`capability_graph.classify_gap:76-123` (deterministic cell classes);
`config/lab_targets.yaml` (asset metadata).

ANALYSIS: SOL's is the audit-grade frame; K3's formula is the readable shape;
O48's uncertainty signal is a real input (council dissent about a
neighborhood raises its information value).

FINAL DECISION: TGT applies hard eligibility first (authorization, readiness,
telemetry health, resource/lease availability), then ranks by
`priority = value / (estimated_cost + ε)` with `value = criticality ×
technique_relevance × lower_bound(uncovered_yield posterior) ×
novelty_confidence × remediation_leverage × realism`. Known-state records
adjust the uncovered posterior (never a second multiplier); correlated
features are recorded separately and never double-counted. Cost comes from a
versioned pricing profile over typed measured quantities; **missing material
cost blocks the ROI claim** (not zero). Deterministic tie-break (higher
uncertainty reduction → lower cost → stable id). Every candidate, exclusion,
factor snapshot, and decline (incl. known-benign declines) is recorded as a
decision event. Council-dissent uncertainty is a recorded novelty-confidence
input.

WHY THIS IS BETTER: SOL's auditability + K3's legibility + O48's uncertainty
input; the double-multiply bug the concept's "multiplicative penalty" invites
is designed out.

WHAT WAS REJECTED: Naive multiplicative penalty stacking; score-only
eligibility.

CONFIDENCE: HIGH.

---

## DEC-12

TOPIC: Plateau (PLT) and cost model

K3 POSITION: Marginal discovery rate < floor (0.2) for patience (3)
iterations ∧ known-state saturation > ceiling (0.8); plateau recorded, steers
TGT; cost-per-promoted-cousin headline series.
O48 POSITION: Rate of new gap-classification transitions per unit cost below
floor for a window (drift engine reused).
SOL POSITION: ≥8 valid trials spanning ≥2 mutation dimensions; no promotions;
<1 unique defense-response marginal gain; 95% upper yield bound <5%;
blocked/infra trials excluded; version changes reset; neighborhood-local.

SHARED GROUND: Stop on marginal-discovery exhaustion; never on embedding
cluster stability; cost-per-cousin tracked and shown falling.

KEY DIFFERENCES: Statistical formality; reset semantics.

FINAL DECISION: Adopt SOL's statistical plateau rule wholesale (≥8 valid
trials, ≥2 dimensions, no promotions, <1 unique response-state gain, upper
95% discovery-yield bound < configured 5% default; blocked/infrastructure
trials excluded; detection/telemetry/environment/ATT&CK/algorithm/evidence
version changes reset the neighborhood through an explicit event; plateau is
neighborhood-local, never system-wide), with K3's known-state saturation
recorded as a secondary signal and the plateau record steering TGT away until
known-state changes (K3). Cost: typed quantities (lab minutes, tokens/time,
analyst minutes, replay work, storage, training allocation) × versioned
pricing profile (SOL); headline series = cost per promoted cousin over hunt
count (K3) — the falsifiable compounding claim.

WHY THIS IS BETTER: Statistical stopping beats heuristic floors; the reset
semantics prevent permanent abandonment of neighborhoods the world changes
under.

WHAT WAS REJECTED: Cluster-stability stops (all three rejected); K3's bare
floor/patience as the primary rule.

CONFIDENCE: HIGH.

---

## DEC-13

TOPIC: Detection handoff (HND)

K3 POSITION: 10-part family-generalizing package; regression recipe in
capture_recipes format; operator-confirmed spl_detections.yaml change through
validation (BQ/AZ green).
O48 POSITION: New sibling to response_loop; growth_loop's three legs
(fires-on-attack / quiet-on-benign / no-regression) are the generalized-rule
proof, made real.
SOL POSITION: Versioned proposal lifecycle; never auto-deploys;
KNOWN_COVERED only after deployment receipt + post-deploy Purple replay;
dispositions feed learning.

SHARED GROUND: Family-generalizing exit; operator-confirmed; regression test;
FP analysis.

FINAL DECISION: HND emits the family-generalizing package (generalized SPL +
variants, Sigma rule, required-telemetry statement, ATT&CK delta, evidence
package, reproduction = new capture recipe, FP analysis from G2, known
limitations, IR implications from response_loop's RESPONSE_PRIMITIVES map,
coverage-impact preview). The generalized rule must pass the three detection
proof legs **made real**: fires-on-attack (recipe replay), quiet-on-benign
(benign corpus), no-regression (BQ/AZ and detection lanes). The detection
change is an operator commit through normal validation; `KNOWN_COVERED` is
recorded only after a deployment receipt + successful post-deploy replay
(SOL). `response_loop.py` is KEPT-SIBLING (O48): reverse-gen seeds MUT,
primitives seed HND's IR section, intake seeds the future external-cadence
extension. `growth_loop.py` retires once HND is live with its shapes +
`validate_spl_syntax` extracted and tests ported (K3's retirement, O48's
mapping).

WHY THIS IS BETTER: O48's correct reading of growth_loop + K3's package
completeness + SOL's deployment lifecycle.

WHAT WAS REJECTED: K3's extract-and-retire of response_loop; auto-deployment
of any rule.

CONFIDENCE: HIGH.

---

## DEC-14

TOPIC: Training harvest (HARV)

K3 POSITION: Role-tagged pairs (hunter/analyst/disprover/cousin-smeller);
objection↔rebuttal exchanges + distance judgments + kill rationales
first-class; versioned JSONL; label-blind (BM); recall_attribution eval-side.
O48 POSITION: Same harvest; recall_attribution as offline labeler.
SOL POSITION: Quarantined examples; provenance-locked; leakage tags; dedup by
behavior/evidence fingerprint; family/campaign/time splits; test set frozen
before harvest; consent/licensing; dataset release = separate approval.

SHARED GROUND: Role-tagged corpus from real hunts; adversarial exchanges are
the richest signal; label-blind production boundary (BM); versioned datasets.

FINAL DECISION: K3's corpus content + SOL's governance: every example carries
source hashes, role, trust tier, family/campaign/time groups, leakage/oracle
flags; dedup by behavior/evidence fingerprint; splits by family/campaign/time
with the test set frozen before the harvest window; eval-side honest-miss
labels only via recall_attribution (BM import-boundary test on new modules);
dataset release is its own operator approval, distinct from model promotion.

CONFIDENCE: HIGH.

---

## DEC-15

TOPIC: Training (TRAIN) and model lifecycle

K3 POSITION: Install mlx-lm + llama.cpp host-native (believed absent);
fuse→GGUF→ollama create→bench gate (5 arms); PENDING_MODEL_VERDICTS confirm;
non-serve on no gain is honest.
O48 POSITION: mlx-lm **present** (verified `pyproject.toml:78`); only
llama.cpp GGUF convert is new; candidate_eval + model-canary acceptance;
never concurrent with a live hunt.
SOL POSITION: Offline isolated exclusive lock; 9B-class ceiling; frozen
five-arm suite; +5 macro-F1 with bootstrap 95% CI > 0 over
base+retrieval+playbook; ≤2pt regressions (benign FPR, calibration, tool
reliability, known-bad recall); 30% replay mix; canary + atomic alias
promotion/rollback; production serving stays Ollama; training deps never
imported at runtime.

SHARED GROUND: Fleet-local LoRA-scale training; redeploy via existing
import-gguf; acceptance gate before serving; operator confirm; decline-on-no-
gain is honest.

REPOSITORY EVIDENCE: `pyproject.toml:78`; `cli/models.py:218-259`;
`candidate_eval.py`; `intake.py:16` (TPS_FLOOR); `drift_cli.py`
model-canary; PENDING_MODEL_VERDICTS + execute_pending_verdicts discipline.

FINAL DECISION: Corpus (HARV) → `mlx_lm.lora` (host-native, present) →
`mlx_lm.fuse` (present) → llama.cpp `convert_hf_to_gguf` + quantize (the one
tool to install — TRAIN phase owns install + verification) → `ollama create`
via the existing import-gguf mechanism → acceptance = SOL's frozen five-arm
suite (+5 macro-F1 cousin-judgment over base+retrieval+playbook, CI > 0,
regression bounds, replay mix) + intake floors + candidate delta +
model-canary → operator confirm via PENDING_MODEL_VERDICTS → role-alias
canary → atomic promotion; rollback = re-point alias. Exclusive resource
lock; never concurrent with a live hunt; training deps isolated from runtime
imports; production serving stays Ollama.

WHY THIS IS BETTER: O48's verified toolchain fact shrinks the build; SOL's
acceptance statistics make "improvement" falsifiable; K3's operator-flow
integration reuses the existing promotion culture.

WHAT WAS REJECTED: K3's "install the whole toolchain" premise (partially
stale); serving MLX artifacts directly; training without frozen controls.

CONFIDENCE: HIGH.

---

## DEC-16

TOPIC: Playbook memory (PLAY)

K3 POSITION: New learned per-scenario-class instruction sets in SUB; static
red-side YAMLs untouched; operator-confirmed activation; injected by LOOP.
O48 POSITION: Retrofit playbooks.py (authored, wired) + add the learning leg.
SOL POSITION: Lifecycle DRAFT→REPLAY_VALIDATED→CANARY→AWAITING_OPERATOR→
ACTIVE→RETIRED; auto-revert on failure; decision-effect recorded.

FINAL DECISION: PLAY = learned per-scenario-class playbook records in SUB
(K3's defensive per-campaign CLAUDE.md), using playbooks.py's container +
validation pattern (O48), with SOL's lifecycle and auto-revert, injected by
LOOP into the investigation arm's context for that class, effectiveness
tracked (budget consumption, time-to-conclusion) and fed to ROSTER/TRAIN.
The static `playbooks/security/*.yaml` red-side engagement playbooks are
untouched.

CONFIDENCE: HIGH.

---

## DEC-17

TOPIC: Roster weighting (ROSTER)

K3 POSITION: Bounded [0.5, 2.0] weights from objection-validity +
cousin-call correctness; advisory only; the objection gate ignores weights.
O48 POSITION: Correlation-group caps (shared base model ⇒ shared group;
group share of effective weight capped); floored; never override a correct
minority.
SOL POSITION: Reliability governs eligibility/probation/additional-review
only; never weights truth; updated only from outcomes unavailable at decision
time.

SHARED GROUND: Retrospective learning about seats exists; it never gates
truth; diversity is config-enforced.

FINAL DECISION: SOL's model is authoritative: ROSTER records per-seat
objection precision/recall, cousin-call correctness, citation validity,
abstention quality, latency/cost, independence family — updated only from
later outcomes — and drives **eligibility, probation, and additional-review
requirements**. K3's bounded weight survives only as a seat-selection
*ordering* hint; O48's group cap survives as a diversity constraint (max
effective seats per model family/correlation group, config-enforced at roster
load). The objection gate structurally ignores all of it: any seat's standing
material objection blocks.

CONFIDENCE: HIGH.

---

## DEC-18

TOPIC: Package layout and spine

K3 POSITION: ~17 flat modules in `core/` (zero new spine units).
O48 POSITION: Sub-packages (`core/substrate/`, `core/cousin/`, `core/bin/`…).
SOL POSITION: One `core/bully/` package + deliberate recursive spine coverage.

REPOSITORY EVIDENCE: `spine_surfaces.yaml:360-376` (sec-core globs are
`core/*.py` + `core/commands/*.py`; siem/ and investigation/ have their own
surfaces); core/ already holds 70 flat `.py` files.

FINAL DECISION: One nested package `portal/modules/security/core/bully/`
(SOL's layout; module names per the ARCHITECTURE doc) + one new three-line
surface entry `unit-surface-sec-bully` covering
`portal/modules/security/core/bully/*.py` (precedent: unit-surface-siem,
unit-surface-investigation). Tests under the existing security test surface
glob.

WHY THIS IS BETTER: 20+ new modules don't belong as flat clutter in a 70-file
directory; the surface entry is trivially cheap and precedented.

WHAT WAS REJECTED: K3's flat layout (works but cluttering); O48's
many-subpackages split (gratuitous fragmentation).

CONFIDENCE: HIGH.

---

## DEC-19

TOPIC: Configuration

K3 POSITION: `config/security/hunt.yaml` + `config/security/heart.yaml`;
machine-enforced `promote_policy: confirm`; registry-resolved model ids.
O48 POSITION: portal.yaml source-of-truth for fleet; component params under
config/security/; no hardcoded names/ports/counts.
SOL POSITION: Versioned `config/security/defensive_bully.yaml`; per-hunt
config snapshot; roles/aliases never model literals; secrets env-managed.

FINAL DECISION: `config/security/hunt.yaml` (organ, distance weights/taus,
mutation budgets, hunt budgets, plateau, costs/pricing, triage SLA,
`promote_policy: confirm` machine-enforced) + `config/security/heart.yaml`
(seats, families, floors, materiality version) — YAML config files, not
load_data JSON (these are operator-edited *config*, not data fixtures).
Model references are role aliases resolved through the backends registry.
Effective non-secret config snapshotted per hunt (SOL). portal.yaml is not
touched unless workspace addressing proves necessary (prefer not to; derived
files only via sync-config if ever).

CONFIDENCE: HIGH.

---

## DEC-20

TOPIC: Migration strategy

K3 POSITION: Bridge rule — retire only when replacement is live;
honest-BLOCKED otherwise; Red never sees the change.
O48 POSITION: Additive first; eight-step retirement order; all CLI keeps
working; gates green each step.
SOL POSITION: Shadow-first — feature flags (off/shadow/authoritative);
dual-write Episodes; dual-run classifications with disagreement adjudication;
trust-conservative backfill; per-component cutover gates; rollback drills.

SHARED GROUND: Red continuity; Episode bridge; bench repositioned not
deleted; no orphaned callers; gates green throughout.

FINAL DECISION: SOL's shadow framework + K3's bridge rule + O48's
compatibility guarantees, merged: every new capability lands dark
(feature-flagged), dual-runs against the legacy path with disagreements
persisted and adjudicated as evidence, and cuts over per-component only after
its validation gates pass; retirements land only when the replacement is live
and exercised; every existing CLI subcommand and check family keeps working
until its mapped replacement phase; backfill imports only hash-verified
records (rest = IMPORTED_UNVERIFIED); rollback = disable consumption, never
delete. Per-component dispositions in `FINAL_MIGRATION_DEFENSIVE_BULLY.md`.

CONFIDENCE: HIGH.

---

## DEC-21

TOPIC: Validation philosophy

K3 POSITION: Semantic success; component/integration/live-behavioral proofs;
six-feed instrument series; final recorded hunt series.
O48 POSITION: Same bar; CP1 — a second hunt observably different because of
the first; honest-BLOCKED path proof.
SOL POSITION: Claim-ID rigor (C/I/B/M/A/H/T/R/F/D/L/P/G/E2E); required-skip
= failure; zero-tolerance safety; thresholds frozen before held-out final
eval; one linked audit graph.

FINAL DECISION: SOL's claim framework + zero-tolerance + frozen-calibration
rule, carrying K3's per-feed measurable instruments and O48's paired-hunt
compounding proof as named claims. Final proof = a recorded hunt series
containing the full lifecycle plus a later hunt's demonstrated decision
delta. Structure in `FINAL_VALIDATION_DEFENSIVE_BULLY.md`.

CONFIDENCE: HIGH.

---

## DEC-22

TOPIC: Beyond-all-three additions (justified)

FINAL DECISION: Exactly three operational additions no plan fully specified,
each justified by comparative evidence: (1) **hunt/bench contention guard** —
LOOP admission control checks for active bench-supervisor/engagement lab
locks before lab actions (the repo's nightly bench cadence is observable in
the worktree; SOL's admission control extended to it); (2) **promotion-queue
notifications** via the existing dispatcher (K3's I-20); (3) **emergency
stop** — config flag halting new Red direction + lease revocation (K3+SOL).
No new components, MCP servers, ports, or services are added.

CONFIDENCE: HIGH.

---

## DEC-23

TOPIC: Two-Episode reconciliation

REPOSITORY EVIDENCE: `episode.py:45-74` (truth plane) and
`agentic_blue_eval.py:82-91` (replay DTO: scenario/target/techniques/
telemetry) are two dataclasses named Episode.
FINAL DECISION (K3): truth-plane Episode is canonical; the agentic local
Episode is documented/renamed in comments as the "capture replay DTO" — no
behavior change to replay benches. The investigation-arm adapter inside LOOP
accepts a live Episode (not only the replay DTO).
CONFIDENCE: HIGH.

---

## DEC-24

TOPIC: Verdict on the prior build program (severity)

K3/O48: REFINEMENT. SOL: MATERIAL REDESIGN.
FINAL DECISION: Both framings are true at different layers: the prior
program's WHAT (thesis, sixteen components, invariants, six feeds, phasing
skeleton) is adopted — refinement; its HOW (state machinery, cousin
adjudication, gate formalism, council semantics, migration rigor) is
materially corrected by this synthesis. The final package is not any plan
plus patches; it is the merged strongest design per this ledger.

CONFIDENCE: HIGH.
