---
id: unit-known-limitations-granite-8b-mxfp8-tool-garbling
kind: what
title: "KNOWN_LIMITATIONS — oMLX granite-4.1-8b-mxfp8 emits U+200B and splits names when tools are present"
sources:
- type: code
  path: scripts/wfe_garble_probe.py
- type: code
  path: config/backends.yaml
- type: code
  path: tests/unit/test_wfe_garble_probe.py
claims: []
confidence: high
tags:
- docs
- inference
- omlx
---

### oMLX granite-4.1-8b-mxfp8 emits U+200B and splits names when tools are present (RESOLVED — no seat aliased)

- **ID**: OMLX-GRANITE-8B-MXFP8-GARBLE-001
- **Status**: RESOLVED (2026-11-09, operator-approved): the `granite4.1:8b-ctx8k` alias is removed
  from `omlx-general` and `omlx-security` too, so no seat is served by the conversion. Trigger: the
  security-reviewer tool set grew the hunt tools (`hunt_status`/`hunt_leads`/`hunt_case` take a
  12-hex job id); direct to oMLX the model wrote `"job_id": "hunt- c6b38fef36aa"` inside a
  text-form `<tool_call>` with malformed JSON and no native `tool_calls` (0/4 exact; the streamed
  request returned empty), while the seat's own Ollama GGUF returned native tool calls with the
  exact id 4/4. Through Open WebUI after the change: tool-call ids exact 8/8. Evidence:
  `docs/HUNT_P1_RESULTS_20261109.md`. Earlier history: MITIGATED (2026-10-17). The `granite4.1:8b-ctx16k` seat tag is no longer aliased onto
  the conversion in `omlx-general` or `omlx-reasoning`, so auto-documents, auto-video and
  auto-image are served by the Ollama GGUF. The `granite4.1:8b-ctx8k` alias (compliance fan-out
  and security lanes) is kept: probed clean with those lanes' own tool sets.
- **Symptom**: with tools in the request, the nightmedia `granite-4.1-8b-mxfp8` MLX conversion
  puts U+200B inside paths it repeats (`/app/​data/​generated/…`) and mangles names and arguments
  (`create_ powerpoint`, `volume..xlsx`, `file_name` for `file_path`). Seen as a Download line in
  the answer and as unknown-tool and missing-file errors in WFE documents rows (campaigns
  `wfe_documents_*_20261016`, all void).
- **Evidence**: a logging proxy between the pipeline and oMLX shows the character in the raw SSE
  deltas, so it is not the pipeline. Replaying the captured request
  (`tests/wfe/fixtures/granite8b_mxfp8_zwsp_hop2_request.json`) direct to oMLX: 10/10 corrupted
  (stream and non-stream, any `tool_choice`); the same request with tools removed: 10/10 clean;
  Ollama `granite4.1:8b-ctx16k` and `granite4.1:30b-ctx96k`, and oMLX `granite-4.1-30b-4bit`:
  10/10 clean. With auto-research's or auto-compliance's tool set the conversion is also 10/10
  corrupted; with tools-specialist's, security-reviewer's or auto-security's tool set, or with no
  tools, it is clean, so the trigger depends on the tool set.
- **Probe**: `uv run python scripts/wfe_garble_probe.py <request.json> --engine omlx --model
  granite-4.1-8b-mxfp8 -n 10 [--workspace <id> | --no-tools]`.
- **Guard**: `tests/unit/test_wfe_garble_probe.py` fails if `config/backends.yaml` aliases any id
  onto `granite-4.1-8b-mxfp8` outside the probed set. Re-probe, then update that set and this
  entry, before adding an alias.
- **Do not** re-add a shadow-shift of the 8b seat tags for coexistence without that evidence.

## Why

A coexistence optimisation (serving the seat from oMLX) silently changed model output for the
tool-using lane, and the symptom looked like model weakness. Recording the proxy-level evidence
and a one-command probe, and failing a test when the alias returns, keeps the next shadow-shift
from repeating it.
