---
id: unit-security-siem-spl-detections
historical: true
kind: what
title: SPL detection library lookup layer
sources:
- type: code
  path: portal/modules/security/core/siem/spl_detections.py
claims: []
confidence: high
tags:
- verified-v1

---

`spl_detections.py` is the lookup layer that converts a MITRE ATT&CK technique identifier into the Splunk query and evidence signature used to confirm that technique during a detection exercise. Records load lazily from a sibling YAML document through `_load()` and are memoised in `_cache` so repeated lookups never reread disk; `_invalidate_cache()` exists purely so tests can force a reload after editing the document. `spl_for()` returns either the default query or a source-specific `spl_variants` entry, letting one technique carry both windows and linux flavours. `technique_reference()` appends `[DISTINGUISH:` and `[KEY:` markers drawn from `distinguishing_features` so callers can tell closely-related sub-techniques apart. `SplunkBackend` consumes these helpers when it executes a search.

## Why

The detection surface must stay declarative rather than embedded in query code, so an operator edits YAML instead of Python to add or correct a signature. Lazy loading keeps the module import cheap, and variant selection lets a single technique express per-telemetry-source queries without duplicating the technique entry, while the distinguishing markers give the harness a deterministic way to push the model toward the exact sub-technique instead of a sibling guess.
