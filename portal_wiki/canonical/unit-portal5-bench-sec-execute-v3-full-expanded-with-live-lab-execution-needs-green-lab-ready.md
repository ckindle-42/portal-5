---
id: unit-portal5-bench-sec-execute-v3-full-expanded-with-live-lab-execution-needs-green-lab-ready
kind: what
title: "PORTAL5_BENCH_SEC_EXECUTE_V3 \u2014 Full expanded with live lab execution\
  \ (needs green lab-ready)"
sources:
- type: doc
  path: tests/PORTAL5_BENCH_SEC_EXECUTE_V3.md
  commit: 05e42ec2
  section: Full expanded with live lab execution (needs green lab-ready)
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.708781
updated_at: 1784946220.708781
---

python3 -m portal.modules.security.core --full-expanded --lab-exec
```

`--full-expanded` runs every available security bench step: prompt-set
capability, attack-chain tool sequencing, execution workspaces
(`auto-security::pentest`, `auto-security::purpleteam-exec` — the
`EXECUTION_WORKSPACES` set), and blue-detection correlation if Wazuh is up.

---
