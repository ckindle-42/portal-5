---
id: unit-security-combined-corpus-validation
kind: why
title: Combined red corpus gate for detection design
sources:
- type: code
  path: portal/modules/security/core/corpus_coverage.py
- type: code
  path: portal/modules/security/core/corpus_replay_bench.py
- type: code
  path: portal/modules/security/core/agentic_blue_eval.py
- type: code
  path: portal/modules/security/core/siem/capture_store.py
- type: code
  path: scripts/security_corpus_report.py
- type: code
  path: portal/modules/security/tests/test_corpus_coverage.py
- type: code
  path: tests/unit/test_security_corpus_contract.py
- type: config
  path: config/security_corpus.yaml
- type: doc
  path: docs/security/corpus_injection.md
  section: Combined corpus validation gate
last_generated_commit: ''
confidence: high
tags:
- security
- red-data
- blue-team
- purple-team
- detection-design
- corpus
- provenance
created_at: 1785519600.0
updated_at: 1785519600.0
---

Live Portal captures and outside corpora are one detection-development input,
but they prove different things. A schema-v2, episode-scoped Portal capture
with scenario-specific validity and a real PCAP proves an end-to-end lab
scenario. BOTS/ATT&CK-labeled corpus data broadens technique coverage; it must
never be counted as proof that the corresponding Portal attack scenario ran.

`config/security_corpus.yaml` is the source contract. It keeps theory outside
capture modes, makes answer keys scorer-only, requires source-stratified
results, and forbids external scenario substitution. New live captures record
their data mode, evidence origin, and answer-key visibility. Replay rejects
hollow captures even when they contain telemetry, preventing a request without
execution proof from becoming blue/purple ground truth. Agentic-blue replay
uses an opaque model-visible scenario name so catalog labels such as an exploit
name cannot leak the scorer's answer into the investigation prompt. Capture
save, replay, and agentic load also resolve target metadata through the current
scenario catalog; a capture made before DHCP-driven target repair cannot send
blue back to the obsolete address.

Run the readiness gate against the current lab before validation:

```bash
python3 scripts/security_corpus_report.py --probe-external \
  --output /tmp/security_corpus_report.json
```

The report derives live scenario coverage, live/external/combined technique
coverage, provenance per technique, and uncovered techniques from the current
scenario catalog and lab state. A committed curated inventory alone cannot
pass: external data must be probed successfully after a reset. Blue/purple
result records carry `data_mode`, `evidence_origin`, and
`answer_key_visibility`, so metrics can be compared per source before any
combined summary is used for detection design.
