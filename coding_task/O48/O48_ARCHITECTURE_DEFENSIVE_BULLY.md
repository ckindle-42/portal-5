# ARCHITECTURE_DEFENSIVE_BULLY

Implementation-level architecture: where each component lives in the tree, what
it reuses vs. builds, its call paths, and how it wires to the existing platform.
Authoritative on *how* (subordinate to `DESIGN_DEFENSIVE_BULLY_FINAL.md` on
*what*). All paths verified at HEAD `47d3e884`; `path::symbol` cited for every
reuse. A fresh session must re-verify against `git log`/`ollama show` before
building.

Legend: **[R]** reuse as-is · **[X]** retrofit existing · **[C]** compose from
existing · **[N]** new code · **[T]** new tool/dependency.

---

## Where the Bully lives

- Core logic: `portal/modules/security/core/` (thick logic; existing home).
- Persistent substrate: `portal/modules/security/core/substrate/` **[N]** (new
  package) seeded from `core/investigation/` and `core/capability_graph.py`.
- Cousin space: retrofit `core/unknown_defense.py` **[X]** on top of
  `research/tools/rag_mcp.py` **[X]**.
- Loop: retrofit `core/loop.py` + `core/loop_cli.py` **[X]**, composing
  `portal/platform/agent/` **[C]**.
- Council gate: new pure module beside `portal/platform/inference/router/council.py`;
  refactor `core/council_agreement.py` **[X]**.
- Training: `portal/platform/inference/cli/models.py` **[R]** + new
  `core/training/` **[N]** + llama.cpp convert **[T]**.
- CLI: new subcommands under `core/__main__.py` (the existing subcommand
  surface), never a new entrypoint.
- Config: `config/portal.yaml` (source of truth) → generated `backends.yaml`/
  `.mcp.json` via `sync_config`; component params under `config/security/`.

MCP-isolation rule preserved: MCP tool modules and `portal.platform.inference`
never import each other; the Bully's logic sits in `core/` and is invoked by
thin MCP/CLI surfaces.

---

## Component architecture

### SUB — persistent substrate **[X]/[N]**
- **Home:** `core/substrate/` (new): `store.py`, `coverage.py`, `known_cells.py`,
  `cost_ledger.py`, `decision_log.py`, `baselines.py`, `plateau_state.py`.
- **Reuses:** `core/investigation/evidence.py::EvidenceStore` (immutable append-
  only, `SourceAuthority`, supports/contradicts, `supersede`) as the record
  engine; `core/capability_graph.py` entities (`Procedure`, `Detection`, `Gap`,
  `CoverageSummary`) as the coverage schema.
- **New:** a durable backing store (SQLite file under a configured state dir; the
  investigation store currently defaults to `:memory:` — SUB pins a file path)
  and the cross-hunt tables (known-cells, cost, decisions, baselines, plateau).
- **Call paths:** written by LOOP (post-hunt), BIN (gate outcomes), HND
  (promotions), TRAIN (model versions); read by TGT (pre-hunt) and PLT.
- **Invariant:** honors the seven-memory-kinds taxonomy (`core/investigation/
  case_notebook.py`); append-only + supersede, never delete.

### ORG — cousin-space organ **[X]**
- **Home:** retrofit `research/tools/rag_mcp.py` (MCP :8921); new thin wrapper
  `core/org/hunt_memory.py` for the security corpus + enforcement.
- **Reuses:** `rag_mcp` hybrid retrieval (MLX mxbai embed :8917 → LanceDB vector
  + tantivy FTS → Qwen3 reranker :8925, `kb_ingest`/`search`).
- **New:** a hunt-memory corpus (episodes, findings, verdicts, objections, cousin
  judgments, plateaus) distinct from the doc corpus; a `require_recall()`
  precondition and an `index_emission()` postcondition **enforced in the tool**
  (a hunt cannot start without a recall call and cannot close without indexing).
- **Call paths:** `LOOP` calls `require_recall` at hunt start and `index_emission`
  at each emission; `BR-COUSIN` calls `nearest(k)` for candidate references.

### BR-COUSIN — spatial cousin engine **[X]**
- **Home:** `core/cousin/spatial.py` **[N]**; retrofit `core/unknown_defense.py`.
- **Reuses:** `unknown_defense.py` grade space + `overlapping_features` (as the
  *explanation* layer); `capability_graph` technique tags; MITRE MCP (:8929) for
  the ATT&CK lattice; `episode.py::DetectionCorrelation` for telemetry-shape.
- **New:** the five-axis composite distance `D=Σwᵢdᵢ` and the code-deterministic
  banding (SAME/SIMILAR/NEW/DIFFERENT/ANOMALOUS); embedding-finds + structured-
  grades pattern (replaces token-overlap-as-decision, which `unknown_defense`'s
  own comments show fails).
- **Call path:** `LOOP` → `spatial.classify(episode)` → `{band, D, per_axis,
  explanation, nearest_ref}`.

### BR-DRIFT — temporal cousin engine **[X]**
- **Home:** `core/cousin/temporal.py` **[N]**; reuse `core/drift_gate.py` engine.
- **Reuses:** `drift_gate.py` rolling-baseline stats (trailing window, noise
  floor 0.03, scipy z-score, min-baseline 3, window 7, INSUFFICIENT-BASELINE
  handling); `drift_cli.py` CLI shape; `model-canary` to hold the model constant.
- **New:** retarget the tracked series from `(scenario, blue_model)→bench metric`
  to `(technique, detection)→firing signature`; the four-way classifier
  (attacker-evolution / telemetry-failure / environmental / detection-
  degradation) reading `spl_detections` state + telemetry-source presence.
- **Call path:** `LOOP`/scheduled → `temporal.update(technique, detection,
  firing)` → `{drift?, cause}`; a detection-lineage change routes to SUB, not
  the bin.

### LOOP — hunt loop **[X]/[C]**
- **Home:** retrofit `core/loop.py` + `core/loop_cli.py`; compose
  `portal/platform/agent/decide.py` + `rank.py` via
  `core/goal_decide.py::_SecurityCapabilityProvider`.
- **Reuses:** `loop.run_engagement`/`resume_engagement` (perceive/decide/act/
  verify/learn), checkpoint+resume, notify (`ENGAGEMENT_ESCALATED/STUCK/
  COMPLETE` with `resume_cmd`), hard caps (50 iters / 7200 s / 200 actions);
  `field_journal` (learn recall + write-back); `playbooks.resolve_phases`
  (decide); `oracles` (verify).
- **New/retarget:** the decide-step chooses a **cousin neighborhood** (from TGT)
  and hunts distance-graded findings, not known playbook phases; act-step
  directs MUT→RED; verify-step consumes the Episode + BR grade; learn-step writes
  SUB + indexes ORG.
- **Call path:** `core loop run` → `loop_cli.loop_main` → `loop.run_engagement`
  (retrofit) → MUT/RED/Episode/BR/BIN/HEART/SCORE → SUB/ORG/HARV/PLT.

### BIN — alert bin (real gates) **[N]**
- **Home:** `core/bin/gates.py` **[N]**.
- **Reuses:** `lab.py::snapshot_lab_vms`/`restore_lab_vms` (G1 clean-snapshot
  replay); benign corpus harness `core/benign_corpus_bench.py` (G2); `core/siem/`
  notable creation + index-wait (G3); `episode.py` evidence refs + `used_synthetic`
  (G0). `growth_loop.prove_draft` is **not** the bin — it moves to HND.
- **New:** the G0→G3 state machine and the static+dynamic pairing rule
  (signature match alone caps at G0).
- **Call path:** `LOOP` → `gates.admit(finding)` → runs G0..G3 → `{promotable |
  non_finding(reason)}`; non-findings feed SUB known-cells.

### HEART — self-bullying council **[R]+[N]/[X]**
- **Home:** new pure fn `portal/platform/inference/router/council_objection.py::
  evaluate_with_objection_gate` **[N]** *beside* `council.py`; refactor
  `core/council_agreement.py` **[X]**.
- **Reuses:** `council.py::aggregate_opinions` (roster-denominator quorum, ESCALATE/
  ABSTAIN, code-decides/model-explains), `CouncilOpinion.strongest_objection/
  missing_evidence/conditions_to_change` (already produced by every seat).
- **New:** deterministic materiality check (objection names missing evidence /
  unmet condition vs. `evidence_refs`/correlation) → unrebutted material ⇒ BLOCK;
  refactor `council_agreement` to route per-seat objections into the gate while
  keeping detection↔review translation + disagreement→ANOMALOUS mapping.
- **Constraint:** the gate is *beside* `aggregate_opinions`; the platform
  primitive is unchanged so other council workspaces don't regress (check BL).

### MUT — red cousin-generator **[R]+[N]**
- **Home:** `core/mutation/generator.py` **[N]**.
- **Reuses:** `exec_chain.py::SCENARIOS` (grammar) + `_prepare_scenario`
  (already imported by `candidate_eval.py`, proving scenarios pass as dicts);
  `emergent_gaps.py` (accidental off-script cousins); `response_loop.py` reverse
  red-scenario generator (directed seeds from a detection).
- **New:** the perturbation operators (params/timing/order/command-form/lineage/
  identity/host/protocol/artifact/sub-technique) producing valid scenario dicts,
  bounded by the operator mutation budget. **Executor + lab untouched.**
- **Call path:** `LOOP` → `generator.cousins(reference, budget)` → `[scenario
  dict]` → existing runner.

### SCORE — distance-graded scoring **[R]+[X]**
- **Home:** extend `core/notify_scoreboard.py` + `core/scoring.py` (pure fns).
- **Reuses:** `notify_scoreboard` ordinal trustworthiness + ANOMALOUS-as-catch;
  `scoring.py` deterministic math.
- **New:** distance-weighted value so a far NEW cousin can exceed a known-bad,
  **without** demoting ANOMALOUS below CONFIRMED (respect check BN).

### TGT — target selection **[N]**
- **Home:** `core/targeting/select.py` **[N]**.
- **Reuses:** `capability_graph` gaps/coverage; SUB known-cells + prior yield +
  cost; ORG neighborhood density.
- **New:** risk-reduction-value / test-cost ranking with multiplicative
  deprioritisation of known-benign/covered/dead cells.

### PLT — plateau + cost meter **[N]/[R-engine]**
- **Home:** `core/targeting/plateau.py` **[N]**; reuse `drift_gate` engine for
  the rate baseline.
- **New:** plateau on the rate of new gap-classification transitions per unit
  cost; cost-per-cousin from SUB cost ledger, shown falling.

### HND — detection-engineering exit **[N sibling]**
- **Home:** `core/handoff/detection.py` **[N]**, sibling to `response_loop.py`.
- **Reuses:** `growth_loop.prove_draft` three legs (fires-on-attack / quiet-on-
  benign / no-regression) as the generalized-rule proof; `siem/spl_detections`
  for the SPL/correlation change; MITRE MCP for ATT&CK mapping; benign corpus
  for FP analysis.
- **New:** family generalization (Sigma over the cousin family), log-source
  onboarding spec, coverage-impact delta, regression test emission; operator-
  confirm deploy. `response_loop` kept as-is.

### HARV — training-pair harvest **[N]+[R-labeler]**
- **Home:** `core/training/harvest.py` **[N]**.
- **Reuses:** `recall_attribution.py` (label-blind honest-miss oracle, World A/B
  split, check BM) to label pairs offline.
- **New:** role-tagged jsonl extraction from hunts/council/cousin judgments
  (positive + adversarial + distance pairs); label-blind boundary preserved (the
  offline harvest may read labels; the production hunt/grader may not).

### TRAIN — fleet-local fine-tune **[X]+[T]**
- **Home:** `core/training/train.py` **[N]** orchestrating existing tools.
- **Reuses:** `mlx_lm.lora` (train adapter — tool present via `mlx-lm>=0.31`),
  `mlx_lm.fuse` (fuse — present), `platform/inference/cli/models.py::import-gguf`
  / `_pull_hf_model` (Modelfile → `ollama create`), `candidate_eval.py` +
  `model-canary` (acceptance).
- **New tool [T]:** llama.cpp `convert_hf_to_gguf` + quantize (the one genuinely
  missing tool) to turn the fused HF model into a GGUF Ollama can serve.
- **Call path:** `HARV corpus → mlx_lm.lora → mlx_lm.fuse → convert_hf_to_gguf +
  quantize → ollama create → candidate_eval + model-canary → confirm serve`.

### PLAY — playbook memory **[X]**
- **Home:** retrofit `core/playbooks.py`.
- **Reuses:** the versioned YAML methodology (phases/scope/budget/stop/escalate),
  already wired into `loop`.
- **New:** the learning leg — accumulate/refine class instruction sets from
  outcomes (which mutations yielded cousins, which cells were dead), versioned +
  operator-confirmed.

### ROSTER — council learning **[N over council]**
- **Home:** `core/council_roster.py` **[N]**.
- **Reuses:** `council` participation/quorum model + BL floor.
- **New:** retrospective seat weighting (objections that held), correlated-seat
  grouping/cap, floor so no seat reaches zero, no override of correct minority
  dissent.

---

## Key call sequences

### Hunt (spatial cousin)
```
core loop run
 └─ loop_cli.loop_main → loop.run_engagement            [X]
     ├─ TGT.select() ← SUB.read + ORG.density           [N]/[X]
     ├─ ORG.require_recall()  (tool-enforced)            [X]
     ├─ platform.agent.decide(goal, caps)               [C]
     ├─ MUT.cousins(ref, budget) → [scenario dict]       [N]
     ├─ RED: exec_chain._run_exec_chain(scenario)        [R, untouched]
     │        lab.lab_dispatch(...) (Proxmox)            [R]
     ├─ purple → episode.derive_verdict → Episode        [R]
     ├─ BR-COUSIN.spatial.classify(episode)              [X]
     ├─ BR-DRIFT.temporal.update(tech,det,firing)        [X]
     ├─ if FAILED/NEW/ANOMALOUS → BIN.gates.admit()      [N]
     │     G0 evidence → G1 replay(snapshot) → G2 benign → G3 analyst-visible
     ├─ HEART: council.aggregate_opinions + evaluate_with_objection_gate [R+N]
     ├─ SCORE.notify_scoreboard (distance-weighted)      [R+X]
     ├─ OPERATOR confirm → HND.detection.package()       [N]
     ├─ SUB.write(outcome,cost,decision)                 [X]
     ├─ ORG.index_emission(...) (tool-enforced)          [X]
     ├─ HARV.extract_pairs(...)                          [N]
     └─ PLT.check(neighborhood)                          [N]
```

### Training (offline)
```
core train (new subcommand)
 └─ HARV.corpus → mlx_lm.lora → mlx_lm.fuse
     → llama.cpp convert_hf_to_gguf + quantize   [T]
     → models.import-gguf → ollama create        [R]
     → candidate_eval + model-canary             [R]
     → OPERATOR confirm → fleet config serve
```

---

## Integration points with the existing platform

- **Council:** consume via `aggregate_opinions`; add the gate beside it; keep the
  primitive general (multiple council workspaces depend on it).
- **Agent loop:** consume `platform.agent.decide`/`rank` via the existing
  `CapabilityProvider` (`goal_decide._SecurityCapabilityProvider`).
- **ORG MCP:** consume `rag_mcp` over MCP :8921; embeddings/rerank on MLX
  :8917/:8925 (off the Ollama chat path).
- **MITRE MCP (:8929):** ATT&CK lattice for the graph-distance axis and HND
  mapping.
- **Detections MCP (:8932) + `siem/`:** detection state, notable creation, SPL.
- **Model CLI:** redeploy via `platform/inference/cli/models.py`.
- **Config:** all params via `config/portal.yaml` → `sync_config`; no hardcoded
  model names/ports/counts.
- **CLI:** new subcommands hang off `core/__main__.py`'s existing subcommand
  dispatch, not a new entrypoint.
- **Validation:** register new checks via `@register(...)` in `scripts/
  validation/*.py`; hold AW/BR/AZ/BL/BM/BN/BQ green.

---

## Concurrency / resource architecture

- Single-box, 64 GB unified memory, Ollama single-model ~15.5–20 GiB. **Bound the
  council roster** and **serialize reviewer calls** under a configured memory cap;
  the loop's hard caps already bound a hunt.
- **Training never runs concurrently with a live hunt** (unified-memory
  contention); the `train` subcommand checks for an active engagement and
  refuses/queues.
- ORG embed/rerank on MLX keeps semantic work off the chat backend.
- Lab actions are serialized by the loop's 200-action cap and Proxmox snapshot
  discipline (clean snapshot per replay).

---

## What is explicitly NOT changed

- `exec_chain._run_exec_chain` / `_run_model_turn` and `lab.py` dispatch/lifecycle
  (Red executor + lab).
- `council.py::aggregate_opinions` internals (gate is beside it).
- `research/tools/rag_mcp.py` retrieval internals (new corpus + wrappers only).
- The doc spine / wiki (`portal_wiki/`) — new files under `security/core/*` are
  covered by the manifest surface, costing zero new units (check BR).
- `benign_corpus_bench` semantics (reused for G2; `P5-SEC-BENIGN-CORPUS-001`
  stays RESOLVED).
