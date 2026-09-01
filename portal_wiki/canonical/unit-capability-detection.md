---
id: unit-capability-detection
kind: mixed
title: "Detection MCP — Sigma/YARA conversion + promoted live SIEM search"
sources:
- type: code
  path: config/portal.yaml
  section: mcp_fleet
- type: code
  path: portal/modules/detection/tools/detection_mcp.py
- type: code
  path: portal/modules/detection/tests/test_detection_mcp.py
- type: code
  path: scripts/native-mcp-service.sh
claims:
- probe: modules.enabled
  contains: detection
confidence: high
tags:
- capability
- mcp
- security
- detection
---

# Detection MCP — Sigma/YARA conversion + promoted live SIEM search

## What

The Detection MCP (`portal/modules/detection/tools/detection_mcp.py`, port
8938) is a read-only server, pipeline- and IDE-exposed, backing the `auto-spl`
workspace and the `auto-security` blueteam variant. It is host-native (stdlib
+ lazy pySigma / yara / the security-module SIEM primitives).

## How it's used

`convert_sigma` / `validate_sigma` run pySigma locally — Sigma to SPL, Lucene,
or KQL, with the parse serving as the structural validation. `compile_yara`
and `scan_yara` check and run a YARA rule against a single file confined to
`DETECTION_YARA_ROOT`. `query_splunk` and `query_windows_events` are the live
SIEM tools promoted out of the blue-eval harness (`blue.py`,
`blue_blue_tools.json`): `query_splunk` instantiates the security module's
`SplunkBackend`, reuses its `_run_search` REST primitive and re-applies its
subsearch / pipe-command allow-list; `query_windows_events` reuses
`_lab_mcp_call` and the lab DC credentials to issue one `Get-WinEvent` read.

## Why it exists

The purple pipeline could emit detection artifacts but not lint, convert, or
run them, and the live SIEM capability was unreachable outside the eval. This
server closes the loop. It unifies with the `detections_mcp` SPL library
rather than duplicating it — library search/validate stays there; conversion
and execution are new here. The promotion is additive: the eval keeps its own
copy, so reverting this module removes the promoted surface without disturbing
the eval.

## Value

An SPL engineer can take a Sigma rule from a threat report, convert it to the
lab's query language, run it against real telemetry, and iterate — all in one
workspace. Live execution stays read-only and lab-scoped; a write / response
action would be a separate operator `[GATE]`.
