# DATA_MODEL_DEFENSIVE_BULLY

Every persistent and transient structure the Defensive Bully relies on. Each
entry gives: **OWNER · IDENTITY · FIELDS · LIFECYCLE · PROVENANCE · RETENTION ·
MUTATION · SUPERSESSION.** Field lists are logical (the coding session maps them
to `dataclass`/table columns and re-verifies existing shapes at HEAD). Existing
shapes reused: `episode.py::Episode`/`DetectionCorrelation`, `investigation/
evidence.py::EvidenceStore`+`SourceAuthority`, `capability_graph.py::Procedure`/
`Detection`/`Gap`/`CoverageSummary`, `council.py::CouncilOpinion`.

Global rules:
- **Append-only + supersede, never delete.** Correction is a new record that
  supersedes the old; history is preserved (audit + poisoning-resistance).
- **Provenance on everything.** `SourceAuthority ∈ {AUTHORITATIVE_STRUCTURED,
  LIVE, ANNOTATED, REFERENCE, EXTERNAL_UNVERIFIED}` + origin (which hunt/episode/
  operator produced it).
- **Seven memory kinds** honored: agent-scratch (transient, discarded) ·
  case-notebook · case-evidence · prior-incident library · confirmed-org
  knowledge · analyst-feedback · **no agent long-term memory at inference.**
- **Storage tier tag** on each structure: PERSISTENT(SUB) · SEMANTIC(ORG) ·
  CASE(investigation) · TRANSIENT(per-hunt).

---

## PERSISTENT (SUB) — cross-hunt state

### Hunt (engagement record)
- **OWNER:** SUB. **IDENTITY:** `hunt_id` (uuid). **TIER:** PERSISTENT.
- **FIELDS:** neighborhood_id, playbook_version, goal, budget/caps, start/end,
  terminal_status (COMPLETE/ESCALATED/STUCK), iteration_count, action_count,
  findings[finding_id], cost_ref, decision_refs[], resume_cmd.
- **LIFECYCLE:** created at loop start; updated per iteration (checkpoint);
  finalized at terminal status.
- **PROVENANCE:** operator/CLI origin; links to TGT decision.
- **RETENTION:** permanent (program history is the compounding evidence).
- **MUTATION:** append checkpoints; terminal status set once.
- **SUPERSESSION:** none (a hunt is a historical fact).

### Episode reference
- **OWNER:** SUB (ref) / value produced by purple path. **IDENTITY:** `episode_id`.
- **FIELDS:** verdict, correlations[DetectionCorrelation], evidence_refs[],
  used_synthetic, source, red_trajectory_ref, scenario_ref.
- **LIFECYCLE:** immutable once derived; SUB stores a reference + a snapshot for
  audit. **PROVENANCE:** `source` tag (live/synthetic-fallback/synthetic).
- **RETENTION:** permanent. **MUTATION:** none (immutable). **SUPERSESSION:** none.

### Evidence record
- **OWNER:** investigation `EvidenceStore` (CASE) + SUB refs. **IDENTITY:**
  `evidence_id`. **TIER:** CASE (immutable append-only).
- **FIELDS:** content_ref (raw telemetry pointer), authority (`SourceAuthority`),
  supports[]/contradicts[], observed_at, technique_tag.
- **LIFECYCLE:** appended during a hunt; never edited.
- **PROVENANCE:** authority hierarchy + origin hunt/episode.
- **RETENTION:** permanent within case; case-evidence memory kind.
- **MUTATION:** none. **SUPERSESSION:** a later record may contradict; both kept.

### Cousin representation (finding + distance)
- **OWNER:** SUB + ORG (embedded). **IDENTITY:** `finding_id`. **TIER:**
  PERSISTENT + SEMANTIC.
- **FIELDS:** episode_id, band (SAME/SIMILAR/NEW/DIFFERENT/ANOMALOUS), D,
  per_axis{behavioral,attack,telemetry,detection_response,semantic}, nearest_ref,
  overlapping_features[], explanation, embedding_ref, gate_state, council_ref,
  score_value, trustworthiness_rank.
- **LIFECYCLE:** created when a suspect finding forms; enriched through BIN/HEART/
  SCORE; indexed into ORG.
- **PROVENANCE:** cites nearest known reference + axis that made it NEW.
- **RETENTION:** permanent. **MUTATION:** state fields advance monotonically
  (SUSPECT→…→PROMOTED/KILLED). **SUPERSESSION:** a re-graded finding supersedes
  its prior grade (both retained).

### Known-defence / known-benign / known-covered / dead-cell record
- **OWNER:** SUB. **IDENTITY:** `cell_key` = (technique/sub-technique × log-source
  × detection). **TIER:** PERSISTENT.
- **FIELDS:** classification ∈ {benign, covered, dead, open}, evidence_ref,
  deprioritisation_weight (multiplicative), observed_count, last_seen.
- **LIFECYCLE:** written when a hunt/BIN concludes a cell benign/covered/dead;
  read by TGT to steer away.
- **PROVENANCE:** the finding/benign-corpus result that justified it.
- **RETENTION:** permanent. **MUTATION:** weight/count updated on re-observation.
- **SUPERSESSION:** a cell can be re-opened (a benign mark superseded) if a later
  cousin proves it exploitable — the correction is a new superseding record.

### Detection state
- **OWNER:** SUB (mirror of `siem/spl_detections`). **IDENTITY:** `detection_id`.
- **FIELDS:** technique_id, spl, status (active/draft/disabled), version,
  expected_signal, coverage_tag.
- **LIFECYCLE:** seeded from `spl_detections.yaml`; updated by HND on confirm.
- **PROVENANCE:** author/version; HND finding that changed it.
- **RETENTION:** permanent with version history. **MUTATION:** via versioned
  edits. **SUPERSESSION:** a new detection version supersedes the prior (lineage
  kept for BR-DRIFT detection-degradation classification).

### Temporal baseline (firing signature series)
- **OWNER:** SUB. **IDENTITY:** `(technique_id, detection_id)`. **TIER:**
  PERSISTENT.
- **FIELDS:** series[{ts, confidence, latency, event_population, seq_len,
  partial_rule_fraction, telemetry_sources[]}], window, noise_floor,
  min_baseline, model_constant_ref (canary).
- **LIFECYCLE:** appended each observation; INSUFFICIENT_BASELINE until
  min_baseline. **PROVENANCE:** `model-canary` proof that the model was held
  constant. **RETENTION:** rolling window retained + full history archived.
- **MUTATION:** append-only points. **SUPERSESSION:** a detection-version change
  starts a new baseline lineage (old archived, not deleted).

### Decision event
- **OWNER:** SUB (append-only decision log). **IDENTITY:** `decision_id`.
- **FIELDS:** kind (target-pick, gate-result, council-decision, promotion, kill,
  supersession, model-serve, playbook-promote), inputs_ref[], outcome, actor
  (code/operator), ts.
- **LIFECYCLE:** written at every consequential decision.
- **PROVENANCE:** the inputs that drove it (the audit spine).
- **RETENTION:** permanent. **MUTATION:** none (append-only). **SUPERSESSION:**
  a reversing decision is a new event referencing the prior.

### Plateau record
- **OWNER:** SUB. **IDENTITY:** `(neighborhood_id, ts)`.
- **FIELDS:** transition_rate, window, cost_per_cousin, plateaued (bool),
  transitions[]. **LIFECYCLE:** written by PLT post-hunt. **PROVENANCE:** the
  discovery-transition history + cost ledger it read. **RETENTION:** permanent.
  **MUTATION:** none. **SUPERSESSION:** a re-opened neighborhood gets a new record.

### Cost-ledger entry
- **OWNER:** SUB. **IDENTITY:** `cost_id` (per hunt/neighborhood).
- **FIELDS:** compute_seconds, lab_wall_clock, analyst_effort, cousins_found,
  cost_per_cousin. **LIFECYCLE:** accrued during a hunt; aggregated by PLT.
- **PROVENANCE:** measured, not estimated. **RETENTION:** permanent (the
  economic-compounding proof). **MUTATION:** append. **SUPERSESSION:** none.

### Target score
- **OWNER:** SUB / TGT. **IDENTITY:** `(neighborhood_id, ts)`.
- **FIELDS:** risk_reduction_value, test_cost, novelty, prior_miss_rate,
  detection_confidence, deprioritisation, final_score, inputs_ref[].
- **LIFECYCLE:** computed pre-hunt; recorded as a decision. **PROVENANCE:** cites
  inputs. **RETENTION:** permanent. **MUTATION:** none (recompute = new record).
  **SUPERSESSION:** latest score is authoritative; history retained.

### Promotion / supersession records
- **OWNER:** SUB. **IDENTITY:** `promotion_id` / `supersession_id`.
- **FIELDS:** subject_ref (finding/detection/model/playbook/roster), from→to,
  operator_confirm (bool + ts), reason. **LIFECYCLE:** written on confirm.
- **PROVENANCE:** operator identity + the decision event. **RETENTION:**
  permanent. **MUTATION:** none. **SUPERSESSION:** a rollback is a superseding
  promotion referencing the prior.

---

## SEMANTIC (ORG) — embedded hunt memory

### Hunt-memory emission (indexed document)
- **OWNER:** ORG (LanceDB + FTS). **IDENTITY:** `emission_id`.
- **FIELDS:** kind (episode/finding/verdict/objection/cousin-judgment/plateau),
  text, embedding, metadata{technique_tags, band, source, hunt_id}, origin.
- **LIFECYCLE:** indexed by LOOP at emission (universal-indexing invariant);
  queried by BR-COUSIN + LOOP recall.
- **PROVENANCE:** origin hunt/episode + authority.
- **RETENTION:** permanent; decay is a *ranking* policy (age down-weights), never
  deletion. **MUTATION:** re-index overwrites by `emission_id` (no dup).
- **SUPERSESSION:** a superseded finding's emission is re-ranked, not removed.
- **BOUNDARY:** feeds hunt-loop context only — never model inference-time
  long-term memory (seven-kinds rule #7); production grading is label-blind.

---

## COUNCIL structures (transient decision, persisted transcript)

### Council opinion
- **OWNER:** HEART (from `council.py::CouncilOpinion`). **IDENTITY:**
  `(finding_id, seat_id)`. **TIER:** TRANSIENT → transcript persisted to SUB.
- **FIELDS:** seat_id, vote/verdict, rationale, strongest_objection,
  missing_evidence[], conditions_to_change[], model_ref.
- **LIFECYCLE:** produced per review; retained as transcript.
- **PROVENANCE:** which model/seat, isolated. **RETENTION:** transcript permanent.
- **MUTATION:** none. **SUPERSESSION:** a re-review is a new opinion set.

### Objection
- **OWNER:** HEART. **IDENTITY:** `objection_id`.
- **FIELDS:** seat_id, text, material (bool, code-determined), names_missing[],
  unmet_conditions[], rebuttal_ref?. **LIFECYCLE:** extracted from opinions;
  materiality computed against evidence. **PROVENANCE:** seat + evidence check.
- **RETENTION:** permanent (ROSTER learns from objections that held).
- **MUTATION:** none. **SUPERSESSION:** a rebuttal links, doesn't erase.

### Rebuttal
- **OWNER:** HEART. **IDENTITY:** `rebuttal_id`.
- **FIELDS:** objection_id, added_evidence_ref[], satisfies (bool, code-checked),
  author (model/operator). **LIFECYCLE:** produced to answer a material objection;
  the gate re-checks satisfaction in code. **PROVENANCE:** added evidence origin.
- **RETENTION:** permanent. **MUTATION:** none. **SUPERSESSION:** none (a failed
  rebuttal is retained; a new one is a new record).

---

## TRAINING structures

### Training example (pair)
- **OWNER:** HARV. **IDENTITY:** `example_id`. **TIER:** PERSISTENT (dataset).
- **FIELDS:** role_tag (positive/adversarial/distance), prompt, completion,
  source_emission_ref, attribution (`recall_attribution` outcome), label
  (offline-only).
- **LIFECYCLE:** extracted offline from emissions; assembled into a dataset.
- **PROVENANCE:** source emission + attribution. **RETENTION:** permanent with
  dataset version. **MUTATION:** none. **SUPERSESSION:** a corrected pair is a new
  version.
- **BOUNDARY:** labels live only here (offline); never in the production grader.

### Dataset version
- **OWNER:** HARV. **IDENTITY:** `dataset_version` (+ content hash).
- **FIELDS:** examples[], counts by role, content_hash, source hunt range,
  min-size-met (bool). **LIFECYCLE:** frozen at train time. **PROVENANCE:** hunt
  range. **RETENTION:** permanent. **MUTATION:** none (immutable version).
  **SUPERSESSION:** a new version references its predecessor.

### Trained model
- **OWNER:** TRAIN. **IDENTITY:** `model_version`.
- **FIELDS:** base_model, dataset_version, adapter_ref, fused_ref, gguf_ref,
  ollama_name, hyperparams, seed, acceptance_report_ref, canary_report_ref,
  served (bool). **LIFECYCLE:** train→fuse→convert→create→accept→(confirm)serve.
- **PROVENANCE:** full chain model←dataset←emissions. **RETENTION:** permanent;
  prior served model retained for rollback. **MUTATION:** `served` toggled on
  confirm. **SUPERSESSION:** serving a new model supersedes the prior in fleet
  config (reversible).

---

## CASE / TRANSIENT structures

### Case notebook + evidence store
- **OWNER:** `investigation` (CASE). **IDENTITY:** `case_id`.
- **FIELDS:** notebook entries, evidence store (immutable), memory-kind tags.
- **LIFECYCLE:** per investigation; **must be pinned to a durable path** (default
  `:memory:` is insufficient for compounding). **PROVENANCE:** authority
  hierarchy. **RETENTION:** promoted to prior-incident library on confirm.
- **MUTATION:** append-only. **SUPERSESSION:** `supersede` links.

### EngagementState / checkpoint (per-hunt)
- **OWNER:** LOOP (TRANSIENT). **IDENTITY:** `hunt_id`.
- **FIELDS:** iteration, observations, pending actions, budget remaining, resume
  token. **LIFECYCLE:** checkpointed each iteration; discarded (agent-scratch)
  after terminal status except the persisted Hunt record. **PROVENANCE:** n/a
  (scratch). **RETENTION:** until resume/finalize. **MUTATION:** overwritten per
  checkpoint. **SUPERSESSION:** n/a.

### Candidate scenario dict (per-hunt)
- **OWNER:** MUT (TRANSIENT). **IDENTITY:** `scenario_dict.name` + parent_ref.
- **FIELDS:** the `SCENARIOS` shape + `parent_ref` + mutated_dimensions[] + seed.
- **LIFECYCLE:** generated, dispatched, lineage recorded if it lands. **PROVENANCE:**
  parent reference + mutation lineage. **RETENTION:** landed mutants recorded in
  SUB; non-landing discarded. **MUTATION:** none. **SUPERSESSION:** n/a.

---

## VALIDATION structures

### Validation result
- **OWNER:** validation harness (`scripts/validation/*`). **IDENTITY:**
  `check_id` (letter) + run ts.
- **FIELDS:** check_id, name, status (pass/fail), evidence, semantic_meaning
  (what a fail means). **LIFECYCLE:** produced per validation run; a fail blocks.
- **PROVENANCE:** the check + its inputs. **RETENTION:** per run. **MUTATION:**
  none. **SUPERSESSION:** the latest run is authoritative.

---

## Identity, keys, and joins

- **Technique IDs are coverage TAGS, not join keys** (per `capability_graph`):
  the join keys are stable ids (`hunt_id`, `finding_id`, `episode_id`,
  `detection_id`, `cell_key`, `model_version`, `dataset_version`).
- **Cell_key** = (technique/sub-technique × log-source × detection) is the
  coverage-cell primary key and the unit TGT/PLT reason over.
- **Cousin lineage:** `finding.nearest_ref` + `scenario.parent_ref` +
  `model_version.dataset_version` + `detection.version` form the four lineages
  that make compounding auditable.

## Retention / decay / poisoning posture

- Nothing is deleted; corrections supersede. Decay is a ranking down-weight in
  ORG and a deprioritisation weight in SUB known-cells, never removal.
- Poisoning resistance: production grading/gating is label-blind; ORG never
  becomes inference-time long-term memory; every record carries authority so a
  low-authority or contradicted record cannot silently drive a promotion.
