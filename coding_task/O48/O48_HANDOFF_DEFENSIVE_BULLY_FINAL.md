# HANDOFF_DEFENSIVE_BULLY_FINAL

Orientation for a fresh session that has none of this conversation's context.
Read this first, then the package in the authority order below, then re-verify
HEAD. This design session produced *design only* — no production code, no
`TASK_*.md`, no commits.

---

## What was reviewed

The Defensive Bully proposal for Portal 5: a defensive attack-hunting system
that finds the *cousins* of known attacks that our detections miss, grades them
by distance from known, has the fleet adversarially disprove them, exits them as
family-generalizing detections, and compounds through six feeds including
fleet-local model training. Inputs reviewed: the offensive concept
(`BULLY_CONCEPT_SOURCE`), the prior build program (`BUILD_PROGRAM_DEFENSIVE_
BULLY`), the prior handoff (`HANDOFF_DEFENSIVE_BULLY_CONTEXT`), and the Portal 5
codebase itself, traced end-to-end.

## HEAD reviewed

`47d3e884c8f0415ed26dbf77f5e817a22ce613ac` (main, clean, 2026-08-13). The prior
design's reference commit `ee9272ee` is 5 commits back; **zero RBP `.py` files
changed** between them (the 5 commits are wiki/eval/report only), so the prior
code claims were structurally sound — but all were re-verified directly at HEAD.

## Verdict

**DESIGN REQUIRES REFINEMENT.** The thesis is sound and well-matched to Portal;
this is refinement, not replacement or material redesign. The prior design
systematically under-credited existing Portal capability.

## Changes made to the prior design (and why)

1. **Reclassify several "NEW" components to RETROFIT/REUSE** — the autonomous
   loop, playbooks, drift/canary, platform agent loop, model-acceptance gate, and
   learn-recall journal already exist and are wired. *Why:* verified in code;
   lowers the build materially.
2. **Reorient, don't rebuild, the miss-primitive** — `episode.derive_verdict`
   already computes FAILED = red-landed-blue-missed with synthetic-never-PROVEN
   in code. *Why:* the finding seed exists.
3. **Correct two dispositions:** `growth_loop.prove_draft` is the *detection-exit
   proof*, not the finding bin; `response_loop.py` has distinct value (response
   IR + reverse-gen + intake) and is **kept** — HND (detection generalization) is
   a new sibling. *Why:* reading the code showed the prior mapping was wrong.
4. **Council delta is small and precise** — add an objection gate *beside*
   `aggregate_opinions` (not inside); refactor `council_agreement` keeping its
   translation + disagreement-as-novelty. *Why:* the primitive already delegates
   quorum and must stay general for other workspaces (check BL).
5. **Training gap is narrower than stated** — `mlx-lm` (lora+fuse) is already a
   dependency and redeploy+acceptance exist; only llama.cpp GGUF conversion is
   genuinely missing. *Why:* verified `pyproject.toml` + `models.py`.
6. **Three handoff claims corrected at HEAD:** `multichain` is not naively
   clear-by-default (do not flip it); `notify_scoreboard` ranks ANOMALOUS ordinal
   *below* CONFIRMED (so distance-scoring is more necessary, but must not demote
   ANOMALOUS — check BN); the RBP arm is not "only a bench harness" (a wired
   engagement loop exists).

## Architecture summary

TGT picks a cousin-neighborhood → LOOP forms a goal and hunts → MUT directs Red
(scenario dicts only; Red untouched) → the purple path produces an immutable
Episode → BR-COUSIN grades 5-axis distance in ORG and BR-DRIFT checks the firing
baseline → suspect findings run BIN gates G0–G3 → HEART (fleet council) tries to
disprove them, unrebutted material objection blocks → SCORE values by distance →
operator confirms → HND exits a family-generalizing detection. Every emission
persists in SUB and indexes into ORG; HARV harvests training pairs; TRAIN fuses a
cousin-specialist to GGUF and serves on confirm; PLAY/ROSTER refine over time;
PLT stops exhausted neighborhoods and meters falling cost-per-cousin.

## Hard decisions made

- Cousin distance is a **5-axis composite**, code-graded, feature-explained; the
  **detection-response axis** is what distinguishes real novelty from arbitrary
  semantic distance.
- The objection gate is **beside** the platform council, never inside it.
- BIN G1 requires **static + dynamic** pairing (signature match alone caps at
  G0); G3 is **analyst-visible in the real console**, not the harness god-view.
- MUT emits **scenario dicts as data**; the executor/lab are never modified.
- BR-DRIFT reuses the drift engine but **retargets** it to per-detection firing
  and adds a 4-way cause classifier; `model-canary` holds the model constant.
- TRAIN adds exactly **one new tool** (llama.cpp GGUF convert); everything else
  is present.
- SCORE rewards novelty by distance but **never demotes ANOMALOUS below
  CONFIRMED** (BN).
- Suspect-by-default lives at **finding-vs-red-landed**, not in `multichain`.

## Key discoveries (verified in code)

- `episode.py:156` enforces synthetic-never-PROVEN in code.
- `loop.py`/`loop_cli.py`, `drift_gate`/`drift_cli`, `candidate_eval`, `goal`,
  `field_journal`, `playbooks` are all PRODUCTION_WIRED.
- `portal/platform/agent/` (decide/rank) exists; `goal_decide`/`decision_engine`
  are shims over it.
- `research/tools/rag_mcp.py` is a full hybrid retrieval MCP (MLX embed + LanceDB
  + tantivy + reranker) — ORG infrastructure is present.
- `investigation/` has an immutable evidence store + a **seven-memory-kinds
  taxonomy** (a hard invariant); it defaults to `:memory:` (must be pinned).
- `capability_graph.py` is non-persistent (rebuilds cold) — the compounding gap.
- `unknown_defense.py`'s own comments document that token-overlap scored a real
  variant 0.09 (< 0.15 floor) — the embedding+structured retrofit is well-founded.
- `mlx-lm>=0.31` is a dependency (lora+fuse ship); no GGUF-convert tool exists.

## Reusable assets

`episode`, `council`, `rag_mcp`, `investigation` (evidence+notebook),
`capability_graph` entities, `loop`+`loop_cli`, `platform.agent`, `playbooks`,
`drift_gate`+`drift_cli`, `unknown_defense` (as explanation), `notify_scoreboard`
+`scoring`, `recall_attribution`, `emergent_gaps`+`trajectory_score`,
`response_loop` (sibling), `models.py`, `candidate_eval`, `siem/*`, the SCENARIOS
grammar + `exec_chain`/`lab` (Red, untouched).

## Invariants that must hold

Same/similar/new is the product; known-bad is the floor. ANOMALOUS is first-
class, valued by distance, never below CONFIRMED. Spatial + temporal cousins both
in scope. Red is the means, left alone (scenario-data direction only). The
council is adversarial (unrebutted material objection ⇒ BLOCK). Six feeds all
built and *demonstrated* (storage that does not change behavior is not a feed).
Pre-hunt recall + universal indexing enforced in the tool. Static+dynamic G1;
analyst-visible G3. Synthetic never PROVEN; production grading label-blind.
Code decides, model explains. Operator confirms consequential promotion. Honor
the seven memory kinds. Hold AW/BR/AZ/BL/BM/BN/BQ green.

## Traps (things that look right and are not)

- Do **not** flip `multichain.consolidate`'s default (breaks the benign path,
  spikes BQ/AZ; wrong layer for suspect-by-default).
- Do **not** put the objection gate inside `aggregate_opinions` (regresses every
  council workspace, BL).
- Do **not** replace `response_loop` (loses response IR + reverse-gen + intake).
- Do **not** treat `growth_loop` as the finding bin (it is the detection-exit
  proof).
- Do **not** build a second knowledge store (ORG is `rag_mcp` retrofitted; the
  doc spine stays facts-only).
- Do **not** infer tool/reasoning/ctx/vision support from model cards — direct
  preflight only.
- A signature match is **not** dynamic reproduction (G0, not G1).
- The training gap is **not** "install the whole toolchain" — only GGUF convert.
- `capability_graph` writing Navigator/heatmap artifacts is **not** persistence.

## Assumptions made (flag if wrong at build HEAD)

- The RBP surface is unchanged since `ee9272ee` (re-diff at build HEAD).
- `mlx-lm` remains a dependency and its `lora`/`fuse` subcommands work on the
  fleet.
- The investigation store default is still `:memory:` and `capability_graph`
  still non-persistent (the two things this design changes).
- The named validation checks keep their letters (letters can be reassigned).
- Single-box 64 GB envelope and Ollama-sole-chat-backend hold.

## Unresolved / deferred (explicitly out of scope here)

- Exact per-axis cousin weights + band thresholds (config; tune empirically).
- The always-on daemon (a listed extension; the loop is built to allow it).
- External-cadence intake breadth (ATT&CK/KEV/CVE) beyond `response_loop`'s seed.
- The 66.7% benign false-flag rate on the alert-fatigue axis (documented in
  `KNOWN_LIMITATIONS.md`, deferred — do not try to fix inside this build).
- The model-catalog spine re-pin fan-out (separate concern, out of scope).

## What to re-verify at HEAD (before writing any task file)

`git log --oneline -5` + HEAD SHA; diff `portal/modules/security/**` and
`router/*` vs. `ee9272ee`; `ollama show` for assumed models; `mlx-lm` version +
llama.cpp convert availability; `config/portal.yaml` workspace/MCP counts; the
seven check letters; the investigation-store default path and `capability_graph`
persistence status. **HEAD wins over every document in this package.**

## Authority order (on any conflict)

1. Repo at build HEAD (code facts).
2. `DESIGN_DEFENSIVE_BULLY_FINAL.md` (what).
3. `ARCHITECTURE` / `INTERFACES` / `DATA_MODEL` (how).
4. `MIGRATION` (transition).
5. `VALIDATION` (proof).
6. `IMPLEMENTATION_REQUIREMENTS` (constraints).
7. This handoff (orientation).
8. `REVIEW_DEFENSIVE_BULLY_CURRENT_STATE.md` (evidence/why).

## The next step (explicit)

A fresh **coding-agent planning session** takes this package as input, clones the
repo fresh, runs `git log --oneline -3` to orient, re-verifies the HEAD facts
above, and then produces (a) a build program sequencing the components under the
ordering + migration constraints in `IMPLEMENTATION_REQUIREMENTS`, and (b) the
self-contained `TASK_*.md` files that a local coding agent executes on the live
system under `PROMOTE_POLICY=confirm`. Task-file discipline applies: self-
contained single files, agent does all writes via heredoc, per-part verify/
rollback/commit, AST-validate embedded Python, verify anchor uniqueness, and
build any missing prerequisite inside the task rather than deferring it. This
design session deliberately stopped at design; the next session owns planning and
implementation.
