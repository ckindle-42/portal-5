# Proposed brief: General seat fallback contract audit

## Objective

Make a general workspace's served model and context limit agree with its configured seat when the preferred engine is unavailable. Prevent a request from silently reaching an unrelated `backend.models[0]` because no candidate resolves the workspace hint.

## Scope

- `auto-general-uncensored`: configured 262K Inkling seat versus the current Ollama fallback alias baked at 32K.
- `auto-spl`: Qwen3.8 hint has exact oMLX mappings but no exact Ollama candidate.
- The streaming and non-streaming last-candidate behavior that accepts a mismatched model.
- Add mocked/offline tests that exercise healthy, unavailable, alias mismatch, and no-exact-model cases; preserve the metadata-only trace policy.

## Decisions and invariants

- Do not repoint either seat or change the open `auto-daily` decision.
- A fallback is valid only if its resolved model family and effective context can satisfy the workspace contract.
- If no valid candidate remains, return a clear failure and record it in `/v1/trace`; do not serve an unrelated model.
- Any new Ollama tag/alias requires confirmation that its context is genuinely supported, not just a request-time `num_ctx` value.

## Acceptance

- Candidate selection rejects the current 32K alias for a 262K request and rejects an unrelated model for `auto-spl`.
- Streaming and non-streaming paths agree on the fail-closed result and selected-model trace fields.
- Unit tests pass; the orchestrator then verifies with one normal and one fallback Open WebUI request per seat, recording the correlation IDs and checking actual engine/model/context.

## Suggested sequence

1. Preflight current HEAD, seat cards, `config/portal.yaml`, `config/backends.yaml`, and running route/trace behavior.
2. Build the narrow candidate eligibility/fail-closed change and tests.
3. Verify the exact returned error and trace in offline tests, then run the four live scenarios above from the orchestrator-owned stack.
4. Roll back only the owned candidate-selection diff if a valid seat is rejected; never delete unrelated aliases.
5. Commit only after unit, lint, type, complexity and live route evidence are recorded.
