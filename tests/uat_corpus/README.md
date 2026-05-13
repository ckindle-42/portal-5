# UAT Response Corpus

This directory holds per-run JSONL response corpora produced by `tests/portal5_uat_driver.py`. Each UAT run emits one file named `uat_<UTC>.jsonl`. The `.jsonl` files themselves are gitignored — they are run artifacts, not version-controlled. This README, the schema documentation, is tracked.

## Purpose

The corpus decouples **response capture** from **grading**. The UAT driver continues to run its existing rule-based assertions and emit PASS/WARN/FAIL verdicts, but every test response (full text, with all metadata) is also written here so that:

1. Assertion design changes can be re-evaluated against the existing corpus without re-running models (~hours of compute saved per iteration).
2. Different grading methodologies (rule-based, LLM-as-judge, human review) can be developed and compared in parallel.
3. Questions outside today's assertions become queryable (response length distributions, model-by-persona behavior, prose-to-code ratios, etc.).

See `TASK_UAT_CORPUS_CAPTURE_V1.md` for design rationale and tradeoffs.

## Schema (v1)

Each line is one JSON object. Fields:

| Field | Type | Notes |
|---|---|---|
| `schema_version` | int | Always `1` for V1 |
| `corpus_run_id` | str | UTC timestamp `YYYYMMDDTHHMMSSZ` shared across all rows from one run |
| `test_id` | str | UAT test ID (e.g. `P-D04`) |
| `test_name` | str | Human-readable test name |
| `section` | str | UAT phase / section |
| `workspace` | str | Routed workspace (e.g. `auto-coding`) |
| `expected_models` | dict | `{mlx: <id>, ollama: <id>}` per test expectation |
| `routed_model` | str | Actual model that served the request (from OWUI metadata) |
| `prompt` | str | Verbatim prompt sent |
| `response_text` | str | Verbatim full model response |
| `chat_url` | str | OWUI chat URL for spot-check audit |
| `status` | str | Rule-based grader verdict: `PASS`, `WARN`, `FAIL`, `SKIP`, `MANUAL` |
| `assertions_result` | list of `[label, passed, detail]` | Per-assertion outcomes |
| `elapsed_seconds` | float | Wall-clock prompt-to-response time |
| `timestamp` | str | ISO-8601 UTC when this row was written |

### Two-chat tests

Tests that exercise multiple chats (currently only `A-08` cross-session memory) carry the composite prompt and response with delimiters:

- `prompt`: `<chat1 prompt>\n\n[NEW CHAT]\n<chat2 prompt>`
- `response_text`: `=== Chat 1 ===\n<chat1 response>\n\n=== Chat 2 (recall) ===\n<chat2 response>`

A grader can split on these delimiters; most graders will not need to.

## Reading the corpus

Standard Unix tooling works directly:

```bash
# How many rows in the latest run?
wc -l tests/uat_corpus/uat_$(ls tests/uat_corpus | grep jsonl | tail -1 | sed 's/uat_//;s/.jsonl//').jsonl

# Distribution of statuses in the latest run:
jq -c '.status' tests/uat_corpus/uat_*.jsonl | sort | uniq -c

# All FAIL rows for the auto-coding workspace:
jq -c 'select(.status == "FAIL" and .workspace == "auto-coding")' tests/uat_corpus/uat_*.jsonl

# Average response length per model:
jq -c '{model: .routed_model, len: (.response_text | length)}' tests/uat_corpus/uat_*.jsonl
```

Python:

```python
import json
with open("tests/uat_corpus/uat_<UTC>.jsonl") as f:
    rows = [json.loads(line) for line in f]
# rows is a list of dicts with the schema above
```

## Adding new fields

Forward-compatible additions: bump `schema_version` to 2 (or higher), add fields to new rows, and document them here. Readers should treat unknown fields as optional. Removing or changing the type of an existing field is a breaking change and requires coordinating downstream graders.
