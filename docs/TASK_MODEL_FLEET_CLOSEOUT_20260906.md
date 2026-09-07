# Task: close every model disposition and retire the pending-model backlog

**Objective:** leave the project with only models that are integrated into a supported role or deliberately retained for a documented purpose. Remove unwanted artifacts from disk, record their removal permanently in project knowledge, and eliminate the standing “pending models” category.

**Execution status:** prepared for planning only. The user requested filesystem inspection while another job is active. This task does not authorize disrupting that job or starting a competing evaluation during this audit.

Read the [verified landscape report](MODEL_LANDSCAPE_AUDIT_20260906.md), its [evidence snapshot](MODEL_LANDSCAPE_AUDIT_20260906.evidence.json), and the [per-item closeout worklist](MODEL_FLEET_CLOSEOUT_20260906.tasks.json). The worklist is the concrete checklist for execution. Its open decision fields are temporary task state; they are not a new permanent model status.

## Required final state

Every model/checkpoint and every installed alias must end with exactly one of these dispositions:

| Final disposition | Required record | Required project/disk state |
|---|---|---|
| **INTEGRATED** | Named production or supported manual role, exact tag/checkpoint/runtime/context, config references, applicable acceptance evidence, known limits. | Required weights and aliases present; routing/persona/group wiring intentional; relevant acceptance passes on the intended serving path. A manual-only variant must say manual-only. |
| **RETAINED_FOR_PURPOSE** | A specific reason for keeping it, responsible owner, intended use, evidence/limitations, storage cost, and whether it is manual-only, fallback, reference, or reproducibility material. | Deliberately retained and accurately documented. It need not be promoted. “Pending,” “might be useful,” “investigate,” and an unexplained bench workspace are insufficient reasons. |
| **REMOVED_CLOSED** | Exact removed identity, why it was rejected/retired, evidence, superseding model if any, removal date, and what aliases/weights remain elsewhere. | Unwanted manifests/artifacts removed after dependency review; stale active config/pull entries retired; durable catalog/decision record remains so it is not silently downloaded and reconsidered again. |

An intentionally kept comparison/reference model can be closed as RETAINED_FOR_PURPOSE without inventing a new test. A previously removed tag can be closed as REMOVED_CLOSED after confirming the exact identity is absent and documenting the reason or, if history cannot establish it, explicitly saying the historical reason is unknown. Do not fabricate a benchmark failure to explain a deletion.

Final dispositions apply to **identities and roles**, not just families. A base tag can be retired while its weights remain required by a supported context alias. Closing a removed GGUF tag does not imply removal of its MLX counterpart.

## Verified starting inventory

- 138 Ollama manifests in the inspected store; all are in the worklist.
- 17 oMLX directory entries, including 2 dangling symlinks; all are in the worklist.
- 33 exact tags from the old pending ledger absent from the inspected Ollama store; all have historical-closeout rows.
- The 29 still-present historical pending tags are included among the 138 installed rows, not duplicated.
- The worklist therefore starts with **188 identity rows**. These are not 188 models to benchmark: aliases, existing supported models, absent tags, broken links and checkpoint/draft dependencies need different actions.
- The audit also found substantial non-chat assets in the Hugging Face cache. Include them in storage reconciliation by owner/subsystem; do not classify speech, OCR, embedding, image/video weights as abandoned chat candidates simply because they lack an Ollama workspace.

Before executing, refresh metadata after the active job completes. The current numbers are a dated baseline; they must not override subsequent legitimate work.

## Phase 1 — preserve evidence and establish dependencies

1. Let the active job finish. Preserve its final raw captures, scorer version, runtime/model identities and completion/failure record. Reconcile fresh results before adding any tests.
2. Reconcile the worklist with current manifests and oMLX/Hugging Face targets. Group aliases by shared model-layer digests; preserve separate context/template/quantization identities. Capture allocated and logical bytes without summing shared files twice.
3. Build the complete dependency graph from workspace/variant hints, council members, expert/reasoning model fields, persona pins, backend aliases/fallbacks, router settings, pull/setup registry, service configuration and current operational ownership. The audit's non-bench reference list is a useful starting point, not the complete graph.
4. Associate each remaining artifact with a project role or an explicit retention reason. Include MLX draft checkpoints, multimodal projectors, embedding/reranking/speech models, media model caches and manually selected IDE variants.

**Exit:** no deletion candidate is identified solely by “not a primary workspace hint,” no actively used model is orphaned by the classifier, and current-job inputs/results are preserved.

## Phase 2 — resolve each decision with the least necessary work

For each worklist row, first read existing raw evidence and the current catalog. Fill `decision_reason`, `purpose_or_replacement`, `evidence_refs`, and the proposed final disposition. Where evidence is insufficient, state **one bounded question whose answer changes keep/integrate/remove**, the specific test that answers it, and a stop rule. If no intended role or retention purpose exists, a fresh benchmark is not required just to justify retirement.

Use this order:

| Cohort | What to do | What not to restart |
|---|---|---|
| 33 absent historical tags | Resolve stale references and historical disposition; record absent exact identity and any surviving siblings. | Do not repull the old list to evaluate it again. |
| Already supported models/aliases | Confirm role and adequate role-specific evidence; close as integrated, or retained reference/fallback where appropriate. | Do not rebench the whole fleet because a legacy report says pending. |
| 29 present historical entries | Protect current roles; make a final per-checkpoint/role decision from existing evidence; test only a material unresolved question. | Do not interpret checked investigate/keep-open labels as closure or deletion permission. |
| Newer installed candidates | Fold in September judgment evidence, OCR/CAD/media results and real IDE use; record a concrete purpose or close removal. | Do not infer untested from absence in the August ledger. |
| oMLX copies and acceleration drafts | Confirm the existing files, serving intent, parser/alias correctness and acceleration evidence. Decide whether parallel GGUF/MLX copies are deliberately needed. | Do not repeat six conversions merely because the old task said their directories were empty. |
| Broken symlinks | Decide whether the target has a supported purpose. Repair only if wanted; otherwise remove the stale link/config record and close it. | Do not count dangling links as downloaded checkpoints or reclaimed model GB. |
| Retained media/service caches | Name the owning subsystem and supported capability; use its acceptance evidence and dependency records. Retire unused caches separately. | Do not sweep them into a chat benchmark campaign. |

### Specific decisions already identified

- **Aquila ctx16k, Mistral Small 3.2, Foundation-Sec:** currently referenced in non-bench configuration despite appearing in the old pending list. Resolve as supported roles or deliberately replace/retire those roles before removal.
- **Granite4.1:30b-ctx16k, Qwen3.6:27b-q4_K_M-ctx16k, SuperGemma security aliases:** old blanket declines conflict with current roles and/or fresh results. Review exact aliases; no family-wide sweep.
- **September judgment cohort:** consolidate scorer versions. Phi4 Q4 has 30 HTTP 500 errors and needs runtime diagnosis if still wanted. Earlier Granite4.2-30B Q8 and Granite4.1-8B Q8 captures need comparable rescoring or explicit exclusion. A score table alone does not decide the intended production role.
- **Completed MoE coding trio:** 210 raw samples already exist. Decide current roles using those results and only the missing current-context/tool-flow evidence.
- **Qwen3.8 GGUF/MTP/DFlash2:** separate checkpoints/runtime modes. Close each with its actual intended role; the GGUF judgment pass does not prove an acceleration mode's correctness or benefit.
- **REAP-288:** recorded restriction against an auto default remains. Either retain for a precise bounded manual use with documented memory limits, or remove it if that use does not earn its ~68.5 GiB. Do not leave it indefinitely in a promotion queue.
- **CAD:** the August 27 partial is superseded. If a CAD candidate still has a plausible role, use a corrected gauntlet; otherwise close the candidate based on the lack of a desired role, not the invalidated score.
- **Cascade-2:** recorded dropped/closed; retire stale task references. Do not reopen its canceled challenger run.
- **OLMo:** older plans disagree. Resolve the explicit retention/role choice rather than treating either plan as a final current inventory instruction.

**Exit:** each identity has a proposed final disposition and reason. Any remaining test has a named decision it will settle; no open-ended evaluation campaign remains.

## Phase 3 — execute the selected final dispositions

### Integrate

Make the minimal configuration/persona/alias changes for the chosen role. Run the required role-specific acceptance when the host is available, record the actually served identity, and reconcile the model catalog plus affected canonical fact-units. Retire superseded routing/pull choices in the same closeout. Do not claim integration solely because the ID is registered in a backend group.

### Retain for a named purpose

Record the purpose in the model's canonical catalog unit and the final disposition register. State explicitly whether it is a supported manual model, an emergency fallback, a comparison baseline, or evidence needed for reproducibility. Document known nonworking capabilities and invocation constraints. No promotion promise, “under evaluation” title, or unspecified follow-up is needed to keep something intentionally.

### Remove and close

1. Name the exact tags/directories and all affected references; confirm the active job no longer needs them.
2. Preserve the evidence and decision record. Estimate unique reclaimable blobs for the complete proposed removal set, subtracting all surviving aliases and shared cache dependencies.
3. Remove the unwanted model artifacts through the appropriate store mechanism; remove stale aliases/dangling links and unwanted automatic pull entries. Do not directly delete a shared blob still referenced by a survivor.
4. Verify exact targets are absent, surviving dependencies are intact, and actual storage change is recorded. An absent alias with surviving shared weights may reclaim almost nothing; that is still a valid alias cleanup.
5. Mark the model REMOVED_CLOSED in its durable catalog/decision record, including reason and replacement. Remove active registrations/workspaces that no longer serve a purpose. Keep historical raw results as evidence unless a separate retention policy calls for their removal.

The audit's **259.232 GiB** is only an upper bound exclusive to the entire present old-pending set. It is not an approved deletion list, and deleting only declined members may recover much less. The previous “~150 GB” plan also needs exact recalculation.

## Phase 4 — close the project knowledge and retire old task state

Create an authoritative final disposition register, with one model identity/role record per outcome, grounded in canonical `portal_wiki/canonical/unit-model-catalog-*.md` units where applicable. This is the project memory that prevents forgotten/repeated intake. Reconcile generated catalog views through the project's normal documented workflow when execution is authorized.

For each record store:

`identity`, `aliases/checkpoint digest`, `runtime`, `final disposition`, `purpose or rejection reason`, `role/config references`, `evidence and scorer/runtime provenance`, `limitations`, `replacement if any`, `decision date`, `removal/retention verification`, `storage effect`.

Then:

- Replace `config/PENDING_MODEL_VERDICTS.md` with a concise historical pointer to the closed register, or archive/retire it with all references updated. Do not leave the 62-model headline active.
- Change the cleanup-reporting workflow so it reports explicit final dispositions and true unresolved task exceptions instead of mechanically regenerating the old pending category. Exclude plans, self-referential reports and metadata mentions from benchmark evidence.
- Close/supersede completed or canceled portions of the reasoning overhaul, oMLX conversion task, rewire plan and UAT action register. Preserve their historical rationale.
- Reconcile all active model pulls, backend aliases, persona pins and bench workspaces with the retained inventory. A retained bench workspace must have a named purpose; an absent retired model must not be silently reinstalled by setup.
- Keep future intake in a bounded task with an owner and terminal decision, rather than an enduring “pending model” catalog title.

## Acceptance checklist

- [ ] Active job's final evidence is reconciled and preserved.
- [ ] Refreshed inventory accounts for all Ollama tags, oMLX targets/drafts and service/media cache owners.
- [ ] All worklist identities have one terminal disposition, a concrete reason, evidence/limitations and a durable project record.
- [ ] Every retained artifact has an intentional purpose; every integrated role has appropriate serving/acceptance evidence.
- [ ] Removed identities are verified absent; shared survivor weights and supported roles remain intact.
- [ ] Old absent tags are closed without unnecessary repulls or invented decline reasons.
- [ ] Configuration, pull registries, aliases/personas, canonical knowledge and generated views agree with the final inventory.
- [ ] Old pending ledger/headlines and superseded task instructions are retired; no indefinite investigate/keep-open state remains.
- [ ] Storage report distinguishes tag totals, unique files and actual reclaimed space.
- [ ] Final handoff lists integrated models, deliberately retained models with reasons, and removed models with reclaimed bytes and closure records.

**The task is complete only when those outcomes are recorded and verified. Producing another analysis report, checking boxes without decisions, or merely running all benches does not complete it.**
