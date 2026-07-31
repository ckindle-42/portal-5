---
id: SEC_BENCH-combined-corpus-validation-20260731
kind: what
title: Combined corpus blue validation and detection-design backlog (2026-07-31)
sources:
- type: bench-security
  path: bench-run:combined-corpus-blue-validation:2026-07-31
- type: code
  path: portal/modules/security/core/corpus_coverage.py
- type: code
  path: portal/modules/security/core/blue_orchestrate.py
- type: config
  path: config/security_corpus.yaml
last_generated_commit: ''
confidence: high
tags:
- security
- agentic-blue
- purple-team
- detection-design
- corpus
- provenance
- validation
created_at: 1785540000.0
updated_at: 1785540000.0
---

The live-probed combined-corpus gate passed before this run. Eleven of 93 lab
scenarios had replayable, scenario-valid Portal captures. The live lane covered
5 target techniques, the external labeled lane covered 16, and their union
covered 18 of 29. This means the available data is safe to use for detection
design; it does not mean blue quality passed, and external data remains
ineligible as lab-scenario proof.

The source-stratified strong three-section validation produced:

| Lane | Cells | Confirmed | Exact | Parent | Tactic |
| --- | ---: | ---: | ---: | ---: | ---: |
| Portal live capture replay | 11 | 0 | 0 | 0 | 0 |
| Public labeled corpus | 16 | 5 | 1 | 2 | 3 |

The external exact hit was T1190. T1003.003 was reported only as parent T1003;
T1189 was reported as same-tactic T1190. The other confirmed cells,
T1552.005 and T1595, were misclassified. The live verdict distribution was
eight `RULED_OUT`, two `ANOMALOUS_UNCLASSIFIED`, and one `UNRESOLVED`.

The three Meta3 captures had stale stored target metadata (`10.10.11.10`) after
DHCP repair moved vmid 113 to `10.10.11.13`. Replay now resolves the current
catalog target and reports the stale metadata as a warning. A corrected rerun
verified all three cells queried `.13`; all remained `RULED_OUT`, so target
drift was a real correctness defect but not the dominant recall failure.

The packet captures themselves contain the expected discriminators: the
phpMyAdmin capture includes `/phpmyadmin/`, `pma_username`, and
`nt authority\local service`; Rails includes `/missing404`, `web_console`, and
`nt authority\system`. The retriever instead returned benign leading ICMPv6
records as its representative packet sample, then repeatedly requested
irrelevant Windows log data. HugeGraph also reached decoded `uid=0(root)`
response evidence but exhausted orchestration without classification. The
primary failure is therefore evidence selection and convergence, not missing
red execution proof.

Detection design proceeds in this order:

1. Relevance-rank decoded HTTP request/response and packet evidence before
   representative sampling; preserve scenario-neutral operation while making
   T1190 and T1059 discriminators retrievable.
2. Stop host-log fallback when the requested source is absent and strong
   network/application evidence is already available; prevent repeated
   irrelevant Windows queries for Linux/web episodes.
3. Add deterministic convergence for high-confidence execution response
   evidence such as `uid=... gid=...`, then validate HugeGraph and the other
   web exploit captures.
4. Improve exact technique discrimination for T1552.005, T1595, T1189, and
   T1003.003.
5. Design the Windows/AD discriminators for T1558.003, T1558.004, T1110.003,
   T1078, T1550.002, and T1557.001; then convert T1053.005, T1083, and T1552
   from anomaly-only outcomes to classified findings.
6. Acquire or produce valid data before scoring the remaining coverage gaps:
   T1003.001, T1003.006, T1021.002, T1059.004, T1078.004, T1203, T1210,
   T1505.003, T1537, T1548.001, and T1592.

Spine-coverage expansion remains deferred until this design and validation
backlog is complete.
