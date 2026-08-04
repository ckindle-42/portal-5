---
id: unit-corpus-injection-lane-c-live-emulation-caldera-atomic-red-team
kind: what
title: "corpus_injection \u2014 Lane C \u2014 live emulation (Caldera + Atomic Red\
  \ Team)"
sources:
- type: code
  path: scripts/caldera_emulate.py
- type: code
  path: .env.example
last_generated_commit: 2f35b5ad508cd284e75ad0735ab7db02961001dd
claims: []
confidence: high
tags:
- verified-v1
created_at: 1784946220.586282
updated_at: 1784946220.586282
---

`scripts/caldera_emulate.py` is the Lane C driver. It talks to Caldera's API
at `CALDERA_URL` (default `http://10.10.11.60:8888`), lists adversaries and
checked-in agents, and runs one adversary profile against an agent group. After
the operation, it flows the resulting telemetry through the same
`collect_target -> ship_batch -> wait_indexed` path the bench uses, stamped
with the Caldera operation id as `episode_id` and provenance
`evidence_origin=live:caldera:<profile>`. Because those events carry an
`episode_id`, blue and purple consume them exactly like bench telemetry,
including via `SplunkBackend.query_episode`.

```bash
python3 scripts/caldera_emulate.py --list
python3 scripts/caldera_emulate.py --adversary "Portal5 Linux Discovery" --group red
```

The driver refuses to target any host outside `LAB_TARGET_NETWORK` (default
`10.10.11.0/24`): `in_lab` rejects non-lab IPs before any operation starts, and
`resolve_agent_hosts` only returns checked-in agents on the lab network. Known
lab targets map to collect kinds and LXC ids in `HOST_COLLECTORS`.

## Why

Lane C exists because lanes A and B are dead ends for discovery: every corpus
event already carries its answer, so it can train detection recall but can
never surface something the library does not know. Only fresh, unlabeled
emulation against owned lab targets produces the novel-threat signal that
`ANOMALOUS_UNCLASSIFIED` discovery needs, and reusing the bench's own
collect/ship/wait primitives keeps that signal in the exact shape blue already
consumes.
