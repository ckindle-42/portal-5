---
id: unit-tool-preselect-test-parser
kind: mixed
title: "Preselector parser tests \u2014 noisy-output index contract"
sources:
- type: code
  path: portal/platform/inference/tool_preselect/tests/test_parser.py
  commit: 50d41b55
last_generated_commit: 50d41b55
claims: []
confidence: high
tags:
- authored-v1
- platform
- tool-preselect
- tests
created_at: 1785796854.75889
updated_at: 1785796854.75889
---

This test file pins the ranker-output parser: extracting numbers from noisy
model text, validating them against the valid range, and mapping them back to
tool names.

## Why

The parser is the contract between a 1B-model's free text and the tool set,
and its failure modes are the silent kind: an out-of-range index dropped, a
duplicate collapsed, an index off by one selecting the wrong tool. The tests
cover the noise the model actually produces — extra text around the numbers,
values beyond `valid_max`, repeats — so a parser regression that starts
selecting the wrong tool fails here with a clear name.

## Interfaces

The suite exercises `_extract_numbers`, `parse_ranked_indices`, and
`indices_to_tool_names` with the messy outputs the ranker genuinely emits.

## Gotchas

The 1-based-to-0-based conversion is the highest-value assertion in this
file — an off-by-one here is invisible in a happy-path test and only shows
when the wrong tool gets selected downstream.
