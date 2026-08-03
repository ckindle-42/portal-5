---
id: unit-tool-preselect-cli-probe
kind: mixed
title: "Tool preselector CLI probe \u2014 legible ranking inspection"
sources:
- type: code
  path: portal/platform/inference/tool_preselect/cli_probe.py
  commit: 50d41b55
last_generated_commit: 50d41b55
claims: []
confidence: high
tags:
- authored-v1
- platform
- tool-preselect
created_at: 1785796809.048102
updated_at: 1785796809.048102
---

`cli_probe.py` is the interactive probe harness for the tool preselector: it
lets an operator feed a user turn and see exactly which tools the ranker
would select, with the outcome label and latency, without going through a
full pipeline request.

## Why

Preselection behaviour is hard to debug through the request path — the 
narrowing happens and the response arrives, but what was selected and why is
invisible. The probe makes the ranking decision legible: an operator testing
a new workspace or a new ranker model sees the prompt, the selected subset,
and the outcome on one screen, which is how a preselector regression is
spotted before it ships.

## Interfaces

`main` parses the probe flags and `_run` drives the loop: build the prompt,
call the ranker, parse, and print the outcome. It reuses the package's real
config, parser, and preselector code rather than a probe-specific copy.

## Gotchas

The probe calls the real ranker over Ollama, so it needs the stack up — it
is a debugging tool, not a unit test, and its output should not be mistaken
for a benchmark.
