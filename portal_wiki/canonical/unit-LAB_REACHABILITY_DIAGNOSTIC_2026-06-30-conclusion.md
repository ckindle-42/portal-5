---
id: unit-LAB_REACHABILITY_DIAGNOSTIC_2026-06-30-conclusion
kind: why
title: "LAB_REACHABILITY_DIAGNOSTIC_2026-06-30 \u2014 Conclusion"
sources:
- type: design
  path: docs/LAB_REACHABILITY_DIAGNOSTIC_2026-06-30.md
  section: Conclusion
last_generated_commit: ''
confidence: high
tags:
- docs
- LAB_REACHABILITY_DIAGNOSTIC_2026-06-30
created_at: 1783195000.867479
updated_at: 1783195000.867479
---


**Confirmed: unreachable-lab was the root cause of the 2026-06-29 `lab_success=0/24`**. The gate now prevents this — the first real (non-dry-run) `--lab-exec` run aborted with the DC/SRV UNREACHABLE message, exactly as designed.

The forced run (via `--force-unreachable-lab`) produced `lab_success=False` with `open_ports=[]`, replicating the original failure mode. The raw log confirms: zero ports open on the lab targets from the sandbox container's network path.

---
