---
id: unit-corpus-injection-two-format-traps-that-silently-produce-useless-data
kind: what
title: "corpus_injection \u2014 Two format traps that silently produce useless data"
sources:
- type: code
  path: scripts/corpus_ingest.py
- type: code
  path: portal/modules/security/core/siem/collect.py
- type: code
  path: portal/modules/security/core/siem/capture_store.py
claims: []
confidence: high
tags:
- verified-v1
created_at: 1784946220.5836549
updated_at: 1784946220.5836549
---

Both traps were hit building Lane B, and neither fails loudly — they yield
events that index fine and match nothing.

1. **Multi-line records.** `attack_data`'s Windows logs are Splunk exports
   where one event spans many `key=value` lines under a `M/D/YYYY H:MM:SS AM`
   header. Iterating per line splits `EventCode=` away from the fields the SPL
   correlates with. The loader reassembles records on that header in
   `iter_events_text`, deciding the format once per file so a key=value line
   inside a record is never mistaken for a new event.
2. **JSON envelopes.** EVTX/Mordor records put the event id at
   `Event.System.EventID`, but `spl_detections.yaml` filters on `EventCode=...`
   fields. Shipping the JSON as-is indexes events with zero extractable
   `EventCode`. The loader renders Windows channels as flat
   `EventCode=... Field=value` text in `windows_kv`, mirroring
   `siem/collect.py::_normalize_windows_security_events`, so corpus events and
   live bench telemetry present identically to the detections. The same trap is
   documented at `siem/capture_store.py::replay_capture`.

Non-Windows JSON (for example `aws:cloudtrail`) keeps its structure, which
Splunk's native JSON extraction already handles.

**PCAP is deliberately out of scope.** Mordor bundles packet captures beside
its host telemetry. Reading them as text yields millions of junk lines, and
there are no network detections in `spl_detections.yaml` to hunt them with
(only `web:access` is network-side). The loader filters archive members to text
formats in `_TEXT_MEMBER_SUFFIXES`.

## Why

These two traps are the reason the loader reshapes data at all instead of
dumping it. Splunk indexes both a multi-line export split per line and a nested
JSON envelope without complaint, so nothing in the index signals the failure —
only the detection hit rate drops to zero. Encoding the reshape (record
reassembly, key=value flattening) into the loader is what converts "data
present" into "detections can fire".
