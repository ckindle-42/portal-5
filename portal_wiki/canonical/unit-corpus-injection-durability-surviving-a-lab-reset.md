---
id: unit-corpus-injection-durability-surviving-a-lab-reset
kind: what
title: "corpus_injection \u2014 Durability \u2014 surviving a lab reset"
sources:
- type: doc
  path: docs/security/corpus_injection.md
  commit: 05e42ec2
  section: "Durability \u2014 surviving a lab reset"
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.5875359
updated_at: 1784946220.5875359
---

Everything these three lanes produce lives **only in the lab**, not in git. The
scripts are versioned; the ~275M indexed events are not. A rollback of the
Splunk container to an older snapshot silently erases all of it, and the
bench's own reset paths roll lab guests back to named snapshots routinely
(`LAB_CLEAN_SNAPSHOT`, `LAB_MBPTL_SNAPSHOT`).

Restore points covering this work, on `proxmox3`:

| Guest | Snapshot | Covers |
|---|---|---|
| LXC 301 `portal-lab-splunk` | `corpus-loaded` | BOTS v1/v2/v3, the `portal5_lab` corpus, all Splunkbase add-ons, the `can_delete` grant, the grown rootfs |
| LXC 302 `portal-lab-caldera` | `caldera-ready` | Caldera + Go + Node 22 + magma build, systemd unit, adversary profile |

```bash
pct listsnapshot 301                 # confirm the restore point still exists
pct snapshot 301 <name> -description # take a new one after materially adding data
```

Take the Splunk snapshot with the `splunk` container **stopped** (`docker stop
splunk`, then snapshot, then `docker start`) so bucket files are consistent
rather than crash-state.

What is *not* covered, and why it does not matter much:

- The **sandcat agent** on a target lives in `/tmp` and does not survive a
  reboot or a target rollback. Redeploy it with the one-liner in Lane C; it is
  a single curl.
- Nothing else is stateful. If both containers were lost entirely, the three
  scripts rebuild the whole thing unattended — that is the point of keeping the
  installers idempotent rather than hand-installing.

Rebuild cost if a restore point is lost: ~25 GB of BOTS download plus a
multi-hour HEC re-ship for Lane B. The snapshots are cheap copy-on-write; the
rebuild is not.
