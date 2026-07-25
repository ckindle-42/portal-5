---
id: unit-corpus-injection-two-format-traps-that-silently-produce-useless-data
kind: what
title: "corpus_injection \u2014 Two format traps that silently produce useless data"
sources:
- type: doc
  path: docs/security/corpus_injection.md
  commit: 05e42ec2
  section: Two format traps that silently produce useless data
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.5836549
updated_at: 1784946220.5836549
---

Both were hit building this lane. Neither fails loudly — they yield events that
index fine and match nothing.

1. **Multi-line records.** `attack_data`'s Windows logs are Splunk exports where
   one event spans many `key=value` lines under a `M/D/YYYY H:MM:SS AM` header.
   Iterating per line splits `EventCode=` away from the fields the SPL correlates
   with, inflating counts ~25× while making every detection match zero. The
   loader reassembles records on that header, deciding the format once per file.
2. **JSON envelopes.** EVTX/Mordor records put the event id at
   `Event.System.EventID`, but `spl_detections.yaml` filters on
   `EventCode=4769 TicketEncryptionType=0x17`. Shipping the JSON as-is indexes
   12k events with *zero* extractable `EventCode`. The loader renders Windows
   channels as flat `EventCode=... Field=value` text, mirroring
   `siem/collect.py::_normalize_windows_security_events`, so corpus events and
   live bench telemetry present identically to the detections. This is the same
   trap `siem/capture_store.py::replay_capture` documents.

Non-Windows JSON (`aws:cloudtrail`, `o365:...`) keeps its structure, which
Splunk's native JSON extraction already handles.

**PCAP is deliberately out of scope.** Mordor bundles `.pcap`/`.pcapng` beside
its host telemetry. Reading those as text yields millions of binary junk lines,
and there are no network detections in `spl_detections.yaml` to hunt them with
(only `web:access` is network-side). The loader filters archive members to text
formats. Ingesting flow data you cannot hunt is negative ROI until a
Zeek/Suricata lane exists.
