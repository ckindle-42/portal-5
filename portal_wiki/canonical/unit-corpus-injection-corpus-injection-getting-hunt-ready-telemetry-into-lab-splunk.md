---
id: unit-corpus-injection-corpus-injection-getting-hunt-ready-telemetry-into-lab-splunk
kind: what
title: "corpus_injection \u2014 Corpus Injection \u2014 getting hunt-ready telemetry\
  \ into lab Splunk"
sources:
- type: code
  path: scripts/corpus_ingest.py
- type: code
  path: scripts/lab_bots_install.py
- type: code
  path: scripts/caldera_emulate.py
- type: code
  path: config/security_corpus.yaml
claims: []
confidence: high
tags:
- verified-v1
created_at: 1784946220.581345
updated_at: 1784946220.581345
---

Blue and purple need adversary telemetry to hunt. Waiting for red bench runs to
produce it is the bottleneck. Three lanes fill the lab SIEM, each landing in
the same evidence-tagged, reversible fashion.

| Lane | Source | Lands in | Labeled? | Reversible |
|---|---|---|---|---|
| **A — BOTS** | Splunk Boss of the SOC v1/v2/v3 | `botsv1` / `botsv2` / `botsv3` | Yes (published answer keys) | Remove app dir + restart |
| **B — ATT&CK corpora** | splunk/attack_data, OTRF Security-Datasets, two EVTX sets | `portal5_lab`, `evidence_origin=corpus:*` | Yes (technique-tagged) | Tagged `\| delete` |
| **C — Live emulation** | Caldera + Atomic Red Team against owned lab targets | `portal5_lab`, `evidence_origin=live:caldera:*` | **No** — novel/unlabeled | Tagged `\| delete` |

Lane A is implemented by `scripts/lab_bots_install.py`: it untars pre-indexed
Splunk buckets into `$SPLUNK_HOME/etc/apps`, so it never touches HEC and each
dataset serves its own `botsvN` index. Lane B is `scripts/corpus_ingest.py`,
which reuses the HEC `ship_batch` primitive and tags every event
`evidence_origin=corpus:<src>:<label>` with no `episode_id`. Lane C is
`scripts/caldera_emulate.py`, which ships fresh, unlabeled activity stamped
`evidence_origin=live:caldera:<profile>` and carries the Caldera operation id
as `episode_id`. The lane provenance tags themselves are declared as named
sources in `config/security_corpus.yaml`.

Lanes A and B are finite and pre-labeled: every event already carries its
answer, which makes them ideal for detection coverage and hunt training but
useless for discovery work. Lane C is the only lane that generates genuinely
novel, unlabeled activity, which is what `ANOMALOUS_UNCLASSIFIED` / discovery
evaluation needs.

## Why

The three lanes are deliberately one interface: bench scoring, corpus data, and
live emulation all land in the same index and the same `evidence_origin`
namespace, so a single tagged search can attribute or remove any of them.
Keeping lanes A and B pre-labeled and finite while reserving lane C for
unlabeled novelty lets detection coverage be measured honestly without
conflating "data exists" with "the scenario ran".
