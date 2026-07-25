---
id: unit-corpus-injection-corpus-injection-getting-hunt-ready-telemetry-into-lab-splunk
kind: what
title: "corpus_injection \u2014 Corpus Injection \u2014 getting hunt-ready telemetry\
  \ into lab Splunk"
sources:
- type: doc
  path: docs/security/corpus_injection.md
  commit: 05e42ec2
  section: "Corpus Injection \u2014 getting hunt-ready telemetry into lab Splunk"
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.581345
updated_at: 1784946220.581345
---

Blue and purple need adversary telemetry to hunt. Waiting for red bench runs to
produce it is the bottleneck. This document covers the three lanes that fill the
lab SIEM, what each is good for, and how to verify or reverse each one.

| Lane | Source | Lands in | Labeled? | Reversible |
|---|---|---|---|---|
| **A — BOTS** | Splunk Boss of the SOC v1/v2/v3 | `botsv1` / `botsv2` / `botsv3` | Yes (published answer keys) | Remove app dir + restart |
| **B — ATT&CK corpora** | splunk/attack_data, OTRF Security-Datasets, two EVTX sets | `portal5_lab`, `evidence_origin=corpus:*` | Yes (technique-tagged) | Tagged `\| delete` |
| **C — Live emulation** | Caldera + Atomic Red Team against owned lab targets | `portal5_lab`, `evidence_origin=live:caldera:*` | **No** — novel/unlabeled | Tagged `\| delete` |

Lanes A and B are finite and pre-labeled: every event already carries its answer,
which makes them ideal for detection coverage and hunt training but useless for
discovery work. Lane C is the only lane that generates genuinely novel, unlabeled
activity, which is what `ANOMALOUS_UNCLASSIFIED` / discovery evaluation needs.
