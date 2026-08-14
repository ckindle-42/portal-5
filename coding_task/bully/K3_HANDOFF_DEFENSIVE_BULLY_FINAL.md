# HANDOFF — Defensive Bully (FINAL, for a fresh session)

## What was reviewed

The complete Defensive Bully design space: the three primary sources
(`BULLY_CONCEPT_SOURCE.md` — the Andy Gill offensive hunter writeup;
`BUILD_PROGRAM_DEFENSIVE_BULLY.md` — the prior build program;
`HANDOFF_DEFENSIVE_BULLY_CONTEXT.md` — its reasoning), Portal 5's current
source (security core end-to-end: Red, Blue/Purple, council, knowledge/RAG,
persistence, bench/eval, validation, model lifecycle), current configuration,
validation gates, recent git history, and reusable assets. Method: multi-pass
review; breadth-mapping assisted by read-only explorer agents; **every
load-bearing claim then personally re-verified by reading the cited code at
HEAD**. Full evidence: `REVIEW_DEFENSIVE_BULLY_CURRENT_STATE.md`.

## HEAD used

`47d3e884c8f0415ed26dbf77f5e817a22ce613ac` (main, clean vs origin). The prior
design referenced `ee9272e`; the delta is eval-gate instrumentation + spine
re-pins (no security-core changes), but all claims were re-verified anyway —
and several handoff claims turned out stale even at the older commit.

## Resulting design verdict

**DESIGN REQUIRES REFINEMENT** — not valid-as-written, not a material
redesign. The concept translation, thesis, invariants, and six-phase skeleton
of the prior program stand. Ten implementation-level corrections and four
missed assets change the component dispositions (REVIEW §1).

## Major changes from the previous design (and why)

1. **SUB is NEW, not "seeded from EvidenceStore."** Verified: `EvidenceStore`
   is in-memory, test/bench-only (`investigation/evidence.py:118-119`);
   `CaseNotebook` has no production callers. What transfers is the
   EvidenceRecord **schema** and the CaseNotebook **SQLite+supersede pattern**.
   SUB is `hunt_state.py` + `hunt_state.db` outside the git tree.
2. **ORG is a new security-side organ module, not a rag_mcp retrofit.**
   Verified: `rag_mcp` ingests document directories and returns rerank scores,
   not distances; no record-level upsert/filters. ORG (`hunt_organ.py`) reuses
   the same infra (LanceDB, embed :8917, rerank :8925) with a record-level,
   raw-distance, provenance-classed API. rag_mcp untouched (MCP independence).
3. **HEART keeps platform council mechanics and adds the objection gate.**
   Verified: `aggregate_opinions` counts votes and drops objections; the
   security adapter never even populates the objection fields
   (`council_agreement.py:44-66`). HEART's promotion condition is the absence
   of an unrebutted *material* objection — code gate, not vote.
4. **BIN2 reframed.** Verified: `multichain.consolidate` is already
   escalate-by-default (no-concluder → ESCALATE/ANOMALOUS; DISMISS requires
   unanimous benign + zero signal) and `council_agreement` zero-participation
   → ANOMALOUS. Suspect-by-default is implemented at the **finding level** in
   the bin's state machine — not as consolidation surgery.
5. **B/P is SPLIT, not wholesale REPLACED.** The bench-driver shell and
   scoring orientation retire; the section machinery (Retriever/Hunter/Expert,
   grounding gates, budgets, mentor), telemetry plane, and verdict semantics
   are load-bearing and are reused inside the new hunt loop.
6. **BR-DRIFT seeds from `drift_gate.py`** (rolling-baseline + canary
   machinery exists — the prior design missed it), retargeted from bench
   metrics to detection-firing signals, with a four-way drift classifier
   (telemetry failure / environmental / degradation / attacker evolution).
7. **G3 analyst-visibility is measured via `siem/blue_triage.py`** (existing
   Splunk→triage-report lane the prior design missed), under a queue-load
   corpus, against a configured priority/SLA.
8. **MUT has three seeds, not one:** deliberate scenario-overlay variants,
   the `--evasion` detection-feedback channel (`blue.py:2185-2255`), and
   deterministic `capture_recipes` re-execution (which is also BIN's G1b
   engine and HND's regression-test format).
9. **Cousin grading is a five-dimension composite with vetoes and mandatory
   decomposition** (semantic / ATT&CK-graph / telemetry-shape / behavioral-
   sequence / detection-response), config-thresholded; U1's token overlap
   survives only as the explanation layer and the documented baseline the
   composite must beat.
10. **PROMOTE_POLICY becomes machine-enforced config** (`hunt.yaml
    promote_policy: confirm` + queue actor checks) — verified prose-only today.
11. **Two-Episode reconciliation:** `episode.py` (truth plane) is canonical;
    `agentic_blue_eval.py`'s local Episode is documented as the capture-replay
    DTO (comment-level change only).
12. **Each of the six feeds has a named measurable-change instrument**
    (DESIGN §18) — compounding is falsifiable, not asserted.

## Architecture summary

Four planes, sixteen components (DESIGN §6). Knowledge plane: SUB (SQLite
hunt substrate), ORG (LanceDB semantic organ). Brain: LOOP (hunt driver),
BR-COUSIN, BR-DRIFT, MUT, TGT, PLT, SCORE. Promotion: BIN (G0→G1a/G1b→G2→
HEART→G3→operator), HEART (falsification council), HND (family-generalizing
exit). Flywheel: HARV, PLAY, TRAIN (LoRA via mlx-lm host-native; redeploy via
existing `ollama create` mechanism; acceptance via repositioned bench),
ROSTER (bounded, non-gating weighting). Red is directed via MutationSpec
overlays and never modified; the Episode is the sole Red→bully contract.

## Hard decisions (do not re-litigate without new evidence)

- Red boundary: directed, never edited. A required Red edit = stop and file.
- The objection gate, not votes, promotes. Quorum is a validity floor (BL).
- The organ is not the spine; the spine is not the organ. Runtime hunt state
  never enters the wiki spine (which keeps design facts only).
- Universal indexing + mandatory pre-hunt recall are LOOP **code**, not
  prompt instructions.
- The platform generic agent loop (`portal/platform/agent/loop.py`) was
  evaluated as LOOP's base and **rejected** — the hunt loop is
  security-specific; the discipline (caps, honest-BLOCKED) is mirrored.
- Training ships only on measured gain over all four non-trained arms; a
  no-gain result is a documented non-serve, not a failure of the build.
- No new MCP servers, ports, Docker services, or OWUI functions in this build.

## Important implementation discoveries

- `siem/spl_backend.py::query_episode` — episode-scoped, label-blind
  telemetry haystack via indexed HEC `episode_id`. The exact retrieval
  primitive the investigation arm needs.
- `_cite_or_drop` is label-blind since 2026-07-23 — production-safe grounding.
- `spl_detections.yaml` carries `distinguishing_features.discriminator_tokens`
  + `sibling_ids` + per-sourcetype `spl_variants` — machine-readable cousin
  explanation and sibling structure.
- The embedding service :8917 is CPU-pinned sentence-transformers (batch
  upserts); only the reranker :8925 is MLX. Env var names still say "MLX" —
  don't be misled.
- `growth_loop.prove_draft`'s placeholder-true legs are mitigated today only
  by the fact that `propose_draft` seeds `# TODO:` SPL which fails syntax
  validation. Do not copy the placeholder pattern; BIN gates execute for real.
- Validation suite has **74** lettered checks (CLAUDE.md says 72 — stale
  prose); all run pre-push.
- New modules under `portal/modules/security/core/*.py` cost **zero** spine
  units (`unit-surface-sec-core` glob). At most one authored design unit per
  phase; follow the two-commit re-pin sequence when BS stales a pin.

## Existing assets (reuse map)

Full table in REVIEW §11; the load-bearing ones: episode.py truth plane;
query_episode; telemetry plane (collect/hec_ship/index_wait/capture_store/
network_capture); grounding gates; blue_orchestrate section machinery;
platform council mechanics; analyst_verdict SectionOutput; notify_scoreboard
semantics; spl_detections discriminators/variants; capture_recipes; evasion
feedback; emergent_gaps; drift_gate; blue_triage; benign_corpus_bench;
recall_attribution (eval-side only, BM boundary); EvidenceRecord schema /
CaseNotebook pattern; playbooks container pattern; models.py import-gguf;
candidate_eval/intake/bench gates; notifications dispatcher; provenance
ledger.

## Invariants

DESIGN §37 (fifteen invariants) — including: cousin discovery is the product;
two surfaces (spatial+temporal); suspect-until-proven; static+dynamic
pairing; consumer-context measurement; code decides / model explains;
confirm-only promotion (machine-enforced); honest-BLOCKED; label-blind
production; spine stays light.

## Known traps (this review's additions to the prior handoff's list)

1. **Presence ≠ implementation** — the compounding-shaped modules
   (growth_loop, response_loop, continuous_eval, capability_graph,
   field_journal recall) are shape without behavior-change. Trace the
   retrieve→decide→change chain or it isn't a feed.
2. **Subagent summaries ≠ reading.** Breadth agents are navigation; verify
   load-bearing claims by reading the code yourself before designing on them.
   (Two handoff claims — multichain clear-by-default, EvidenceStore
   persistence — were stale and would have corrupted the build.)
3. Don't let BIN2 re-litigate multichain — it's already fail-safe; the
   suspect-default work is at the finding level.
4. Don't build the organ on rerank scores or document ingestion — record-
   level, raw distance, provenance classes.
5. Don't let the objection gate degrade to quorum — the platform aggregate is
   a vote counter; HEART's gate is new code.
6. Don't move or "fix" field_journal — out of scope; SUB supersedes its role
   for the bully without touching it.
7. Don't reopen P5-SEC-BENIGN-CORPUS-001 or the model-catalog re-pin tax.
8. Don't hardcode model ids — the fleet churns; resolve via config/registry.

## Assumptions

- Lab (10.10.11.0/24), Splunk HEC, attack image, and `SANDBOX_LAB_EXEC`
  remain the live-hunt substrate; live proofs are operator-invoked.
- Host remains M4 Pro 64GB; Ollama sole chat tier; LoRA-scale training is
  feasible on-host (mlx-lm), verified at the TRAIN phase.
- The operator works via self-contained TASK_*.md files executed by a coding
  agent; PROMOTE_POLICY=confirm is the working culture.

## Unresolved issues

None blocking. Watch items: (a) τ thresholds start at DESIGN §10 defaults and
calibrate on the fixture set — expect one tuning pass; (b) the G3 queue-load
corpus is a new small fixture family to author; (c) cousin-judgment bench set
materializes only after early hunts produce grading history (HARV bootstraps
it from labeled fixtures until then).

## What must be re-verified against the future HEAD

IMPLEMENTATION_REQUIREMENTS §23 — every cited anchor, check letters/count,
spine globs, fleet roster ids, lab/Splunk/attack-image readiness, and the
training toolchain (at the TRAIN phase). Drift is a finding: adjust the
implementation, never the invariants, without operator review.

## Authority order among documents

```text
DESIGN_DEFENSIVE_BULLY_FINAL.md              (WHAT — normative)
ARCHITECTURE_DEFENSIVE_BULLY.md              (implementation contracts)
INTERFACES_DEFENSIVE_BULLY.md                (implementation contracts)
DATA_MODEL_DEFENSIVE_BULLY.md                (implementation contracts)
MIGRATION_DEFENSIVE_BULLY.md                 (transition requirements)
VALIDATION_DEFENSIVE_BULLY.md                (proof requirements)
IMPLEMENTATION_REQUIREMENTS_DEFENSIVE_BULLY.md (build constraints)
HANDOFF_DEFENSIVE_BULLY_FINAL.md             (this file — orientation)
REVIEW_DEFENSIVE_BULLY_CURRENT_STATE.md      (evidence/rationale)
```

No contradictions between these documents are intentional; if one is found,
the higher document wins and the lower one is fixed.

## Intended next step

> **A fresh coding-agent planning session should read this design package
> completely, re-verify the referenced Portal implementation surfaces against
> current HEAD, then produce the complete build program and execution task
> files for implementing the entire accepted design.**

The build follows the phase skeleton in IMPLEMENTATION_REQUIREMENTS §14
(P1 spine → P2 bin&heart → P3 mutation&drift → P4 discovery/stopping → P5
exit → P6 flywheel), each phase closing with its mapped validation gates, the
repository operational at every commit, and the final end-to-end proof of
VALIDATION §14 as the program's exit criterion.
