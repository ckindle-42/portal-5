---
id: unit-corpus-injection-lane-c-live-emulation-caldera-atomic-red-team
kind: what
title: "corpus_injection \u2014 Lane C \u2014 live emulation (Caldera + Atomic Red\
  \ Team)"
sources:
- type: doc
  path: docs/security/corpus_injection.md
  commit: 05e42ec2
  section: "Lane C \u2014 live emulation (Caldera + Atomic Red Team)"
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.586282
updated_at: 1784946220.586282
---

Caldera runs on lab-internal LXC 302 (`portal-lab-caldera`, 10.10.11.60:8888) as
a systemd unit, on the VLAN-60 lab bridge only. The Atomic Red Team ability
collection is included via Caldera's bundled `atomic` plugin.

`scripts/caldera_emulate.py` runs an adversary profile and then flows the
resulting telemetry through the **same** `collect_target → ship_batch →
wait_indexed` path the bench uses, stamped with the Caldera operation id as
`episode_id`:

```bash
python3 scripts/caldera_emulate.py --list
python3 scripts/caldera_emulate.py --adversary "Portal5 Linux Discovery" --group red
```

The driver refuses to target any host outside `LAB_TARGET_NETWORK`.

Deploying an agent onto a lab target:

```bash
