---
id: unit-tool-preselect-preselector
kind: mixed
title: "Tool preselector \u2014 ranking pass with total fallback"
sources:
- type: code
  path: portal/platform/inference/tool_preselect/preselector.py
  commit: 50d41b55
last_generated_commit: 50d41b55
claims: []
confidence: high
tags:
- authored-v1
- platform
- tool-preselect
created_at: 1785796803.282781
updated_at: 1785796803.282781
---

`preselector.py` is the ranking pass itself: given the effective tool set and
the user turn, it resolves the workspace config, short-circuits when there is
nothing to gain, builds the prompt, calls the ranker model over Ollama, parses
the output, and returns the narrowed subset with an outcome. It *never
raises* — every error path is a fallback that returns the full tool set.

## Why

Preselection sits on the request hot path, so its failure mode must be
"return everything, let the request proceed" — never a crash that kills a
request because a ranker timed out. The `bypass_low_tools` short-circuit
(tools <= 5) exists because narrowing five tools saves nothing and only adds
latency; the `bypass_disabled` path covers workspaces not opted in. The
outcome labels map to the metrics so every fallback is visible, and the
calls to Ollama use the ranker model configured for the preselector rather
than the workspace's own model.

## Interfaces

`preselect(effective_tools, user_turn_content, workspace_id, workspace_config, ollama_url)`
returns `(subset, PreselectOutcome)` where subset is always a subset of the
input and equals it on any fallback. `PreselectOutcome` carries the reason
label and latency.

## Gotchas

The tool descriptions come from the live `tool_registry`, so a tool the
registry does not know has an empty description — the ranker then ranks it
on name alone, which is a real (if noisy) signal.
