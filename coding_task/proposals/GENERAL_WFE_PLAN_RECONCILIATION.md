# Proposed brief: Reconcile general WFE plans with current seats

## Objective

Keep general WFE task plans and candidate definitions aligned with current seat authority and actual candidate registrations, so passing graders compare the intended models on the intended workspace.

## Confirmed disk mismatches

- `tests/wfe/plans/general_decision_v1.yaml` still names an old Gemma QAT `auto-daily` root incumbent; current `config/portal.yaml` seats Nemotron and the cold-start question remains open under `docs/MODEL_SEAT_PROCESS.md`.
- The historical uncensored plan names a former Qwen challenger with an 8K context, while `auto-general-uncensored` is now Inkling at 262K.
- `tests/wfe/workloads.yaml` includes `huihui_ai/Qwen3.6-abliterated:27b-ctx8k`, which cannot match the current 262K seat. Its `qwen36-fable-fusion-711:Q4_K_M` candidate has no registration in `config/backends.yaml`.
- Most declared variants lack an exact workspace-context suite; security `auto-spl` rows do not establish general assistant behavior.

## Decisions and invariants

- Do not change current incumbents or close the auto-daily cold-start decision in this task.
- Do not claim results from missing/unregistered candidates or map security-specific rows to general-purpose claims.
- Preserve `BLOCKED`/missing coverage when a real candidate, task, or repeat is absent.
- Persona prompts and current route behavior must be captured from the live Open WebUI path before any rows count.

## Acceptance

- Every general plan's exact workspace, incumbent, challenger, backend mapping, context and grading purpose match current config or carry an explicit documented block.
- Add exact-variant coverage only where a named seat question and real tasks justify it; avoid broad generated fixtures and format-only pass criteria.
- An orchestrator-owned live setup task proves one real row per affected seat through Open WebUI and verifies its matching `/v1/trace/{correlation_id}` before running a campaign.
- Record task/repeat completeness, incumbent reproduction, row receipts, and explicit rollback route.
