---
id: unit-tool-preselect-parser
kind: mixed
title: "Tool preselector parser \u2014 noisy ranker output to indices"
sources:
- type: code
  path: portal/platform/inference/tool_preselect/parser.py
  commit: 50d41b55
last_generated_commit: 50d41b55
claims: []
confidence: high
tags:
- authored-v1
- platform
- tool-preselect
created_at: 1785796788.475729
updated_at: 1785796788.475729
---

`parser.py` converts the preselector model's raw text output into ranked tool
indices. It extracts the numbers, validates them against the valid range, and
maps them back to tool names.

## Why

A small ranker model produces noisy output — extra text, out-of-range
numbers, repeats — and the parse layer is the contract between the model's
free text and the downstream tool set. `_extract_numbers` deliberately
tolerates this noise, and `parse_ranked_indices` validates every index
against `valid_max` so an index pointing at a nonexistent tool is dropped
rather than crashing or silently selecting the wrong tool.

## Interfaces

`_extract_numbers(text)` pulls integer sequences out of the response;
`parse_ranked_indices(raw_output, valid_max)` returns the deduplicated,
in-range indices in order; `indices_to_tool_names(indices, tool_names_ordered)`
maps them to the ordered tool list.

## Gotchas

Indices are 1-based against the ordered tool list (the prompt says "the
numbers of the tools"), so the parser must convert to 0-based before
indexing — a one-off error here selects the wrong tool silently.
