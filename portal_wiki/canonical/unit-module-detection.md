---
id: unit-module-detection
kind: mixed
title: "Detection-as-Code Module — Sigma convert/validate, YARA, live SIEM search"
sources:
- type: code
  path: portal/modules/detection/tools/detection_mcp.py
- type: code
  path: portal/modules/security/core/siem/spl_backend.py
- type: code
  path: portal/platform/wiki/adapters/modules.py
- type: code
  path: config/portal.yaml
claims:
- probe: modules.enabled
  contains: detection
confidence: high
tags:
- detection
- sigma
- yara
- splunk
- security
- module
- verified-v1
---

# Detection-as-Code Module

## Tools

`detection_mcp` (:8938) — closes the author -> convert -> run -> tune loop.
`convert_sigma` runs pySigma to turn a Sigma rule into SPL / Lucene / KQL (the
parse is the validation); `validate_sigma` validates without converting.
`compile_yara` checks a YARA rule; `scan_yara` compiles and scans a single
file under a sandboxed root (`DETECTION_YARA_ROOT`, default `~/AI_Output`) —
no arbitrary filesystem scan. `query_splunk` and `query_windows_events` are
the previously eval-siloed live SIEM tools promoted to a first-class,
read-only, lab-scoped surface: `query_splunk` reuses `SplunkBackend`'s REST
connection primitive and the same subsearch / pipe-command guardrails;
`query_windows_events` reuses the lab exec primitive and DC credentials for a
single `Get-WinEvent` read. Neither ever writes.

## Workspaces

- `auto-spl` — Sigma/YARA authoring and conversion, plus live SIEM search
- `auto-security` (blueteam) — detection engineering

## Module State

```yaml
enabled: true
```

## Why

The purple-team pipeline emitted Sigma / Wazuh XML / YARA / SPL / KQL as text
but nothing linted, converted, or ran them, and the one live capability was
locked inside the blue-team eval harness (`blue.py`, `blue_blue_tools.json`),
unreachable by the human-facing SPL-engineer and detection personas. This
module unifies with — does not duplicate — the `detections_mcp` SPL library
(library search/validate stays there; conversion and live execution are new).
The promotion is additive: the blue-eval harness keeps its own copy. Any
write / response action (disable account, isolate host) is a separate operator
`[GATE]`.
