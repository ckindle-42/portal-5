---
id: unit-known-limitations-blue-detection-quality-wrong-mitre-id-reporting-on-correct-evidence
kind: what
title: "KNOWN_LIMITATIONS \u2014 Blue Detection Quality \u2014 Wrong MITRE ID Reporting\
  \ on Correct Evidence"
sources:
- type: doc
  path: KNOWN_LIMITATIONS.md
  commit: 05e42ec2
  section: "Blue Detection Quality \u2014 Wrong MITRE ID Reporting on Correct Evidence"
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.662762
updated_at: 1784946220.662762
---

- **ID**: P5-SEC-BLUE-MITRE-001
- **Description**: With the Splunk telemetry pipeline confirmed working end-to-end (commits
  `306df2a`/`cdf080e`), the root problem motivating this whole investigation is now isolated:
  blue models receive correct, live telemetry and still frequently report the wrong MITRE
  sub-technique ID. Diagnosed via `--replay-captured-red` (zero live lab time, 5 trials each
  condition on `kerberoast_to_da`): `sylink/sylink:8b` correctly identified `T1558.003`
  (Kerberoasting) in only 4/5 trials without any reference material in its prompt, with one
  clean miss (`T1543.002`, unrelated). Fixed (commit `8ee6d37`) by surfacing
  `siem/spl_detections.yaml`'s existing per-technique descriptions to the blue model via
  `BLUE_INITIAL_PROMPT` (previously only used to build red's evasion-feedback prompt, never
  shown to blue) — moved to 5/5 correct with the reference table present.
  **This is a real but modest improvement, not a fix for the underlying problem**: `T1003.006`
  (DCSync) was never correctly identified in either condition despite live evidence being
  present in both, and the false-positive rate (extra wrong techniques reported alongside the
  correct one) was unaffected by the fix.
- **Operator action**: Needs further diagnosis on why DCSync specifically never gets identified
  even with reference material present (event field naming? insufficient distinguishing detail
  in the normalized `EventCode=4662 Properties=... Account=...` telemetry line? model capability
  ceiling for an 8B model on this specific technique?), and separately, work on reducing false
  positives (the model over-reports plausible-but-wrong techniques alongside a correct one).
  `--replay-captured-red` makes this cheap to iterate on — no live lab time needed per trial.
