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
  path: scripts/security_replay_verify.py
- type: code
  path: scripts/security_capture_recipes.py
- type: code
  path: portal/modules/security/core/capture_recipes.py
- type: code
  path: config/security_corpus.yaml
last_generated_commit: 2f35b5ad508cd284e75ad0735ab7db02961001dd
claims: []
confidence: high
tags:
- blue-team
- corpus
- detection-design
- provenance
- purple-team
- red-data
- security
- verified-v1
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

The 93-entry scenario catalog is not itself the live denominator. The corpus
contract explicitly identifies theory or unbacked exercises that have no
deployed target contract; they remain visible, with reasons, but cannot count
as missing or valid lab replay. `security_replay_verify.py --live` re-ships
every scoreable capture and requires Splunk indexing confirmation, closing the
gap between a locally valid JSON artifact and a capture blue can actually query.

At the 2026-07-31 stopping point, 36 of the 72 backed lab exercises have a
valid live capture. The combined live-probed gate is ready for blue/purple
validation and detection design: the live lane covers 9 target techniques,
the external labeled lane covers 14, and their union covers 18 of the 25
backed target techniques. These are source-stratified figures; outside data
still supplements detection coverage and never substitutes for live lab proof.

Deterministic capture recipes now own target readiness, host-side setup,
execution, target-side postconditions, PCAP collection, enrichment, indexing,
validity, replay checks, and teardown as one certification transaction. A
recipe cannot certify from an exploit-shaped request alone. Where execution is
claimed, correlated response or target-side state must prove it; externally
observable callbacks may certify initial access only when that is the declared
ground truth.

## Why

The combined-corpus gate exists to keep two different kinds of proof from
being confused: a live Portal capture proves a lab scenario ran
end-to-end, while a BOTS/ATT&CK-labeled corpus entry only broadens
technique coverage and must never be counted as scenario proof. Every
mechanism in this unit — the source contract in
`config/security_corpus.yaml`, the source-stratified report from
`corpus_coverage.py`, the replay gate in `security_replay_verify.py`, the
opaque model-visible scenario name in `agentic_blue_eval.py`, and the
capture-recipe transaction — is grounded in the cited code so the
distinction stays enforceable rather than aspirational. The corpus
section it used to cite is a rendered block of this very unit, so it is
not a source; the code it cites is.
