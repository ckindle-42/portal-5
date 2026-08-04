---
id: unit-tool-preselect-prompts
kind: mixed
title: "Tool preselector prompts \u2014 plain-text ranker template"
sources:
- type: code
  path: portal/platform/inference/tool_preselect/prompts.py
  commit: 50d41b55
last_generated_commit: 50d41b55
claims: []
confidence: high
tags:
- authored-v1
- platform
- tool-preselect
created_at: 1785796782.756188
updated_at: 1785796782.756188
---

`prompts.py` holds the single prompt template for the tool preselector. It is
deliberately simple: the preselector *ranks*, it does not reason, and it does
not use MiniCPM5's native XML tool-call format — the model is asked to return
the numbers of the most relevant tools, one per line, in order.

## Why

The ranker model is a 1B parameter model doing a ranking task, and asking it
to use a full tool-call grammar would be asking for more than the task needs.
The template keeps the model's job minimal — pick the relevant numbers — which
is exactly the shape the parser expects and the easiest output for a small
model to produce correctly. The user turn is truncated to the first 500
characters because relevance ranking needs the request's intent, not its full
text, and a bounded input keeps the ranker's own prefill cost low.

## Interfaces

`build_prompt(user_turn_content, tool_names_ordered, tool_descriptions, k, slack)`
assembles the template with the tool list and the k-plus-slack instruction.
The `slack` term is how many extra tools beyond k the ranker may nominate, a
hedge against a too-tight ranking.

## Gotchas

The `{k_plus_slack}` slot is why the parser must tolerate more returned
numbers than k — the model is deliberately allowed to over-nominate and the
truncation happens downstream.
