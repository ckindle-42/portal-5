---
id: unit-corpus-injection-inside-lxc-301-as-the-splunk-user-uid-41812-the-apps-dir-is-splunk-owned
kind: what
title: "corpus_injection \u2014 inside LXC 301, as the splunk user \u2014 the apps\
  \ dir is splunk-owned."
sources:
- type: code
  path: scripts/lab_bots_install.py
- type: code
  path: scripts/lab_splunkbase_install.py
claims: []
confidence: high
tags:
- verified-v1
created_at: 1784946220.5825438
updated_at: 1784946220.5825438
---

The BOTS installer must run on the Splunk host, where `$SPLUNK_HOME` and
network egress both exist. For Portal 5 that is the `splunk` Docker container
inside LXC 301, run as the `splunk` user so the apps dir stays splunk-owned:

```bash
docker cp scripts/lab_bots_install.py splunk:/tmp/
docker exec -u splunk splunk /opt/splunk/bin/python3 /tmp/lab_bots_install.py \
    --workdir /opt/splunk/var/p5corpus
```

The installer is idempotent and additive-only: `already_installed` skips any
dataset whose app dir exists, and re-running `install` repairs the retention
pin on an already-installed dataset via `pin_retention`. Nothing is ever
deleted.

Operational notes that come from the installer's own behavior:

- **Sizing.** `install` computes the archive size and its extracted copy, and
  refuses to start a dataset it cannot fit; each archive is removed after a
  successful extract unless `--keep-archives` is passed.
- **Retention is a time bomb.** Each dataset ships `frozenTimePeriodInSecs =
  377395200` (~12y) measured from the *event* timestamps, and BOTS v1's events
  are old. Left alone the buckets silently freeze and are deleted because no
  `coldToFrozenDir` is set. `pin_retention` writes a `local/indexes.conf`
  override raising the ceiling to 100y without editing the shipped default.
- **Verification is tstats, not a scan.** Bucket counts are large, so the
  recommended check is `| tstats count where index=botsv1 OR index=botsv2 OR
  index=botsv3 by index`.

Field extraction for BOTS ships separately: the raw events carry no aliases or
CIM normalization. `scripts/lab_splunkbase_install.py` installs the Splunkbase
add-ons the READMEs reference. It is idempotent and additive-only, reads
`SPLUNKBASE_USERNAME` / `SPLUNKBASE_PASSWORD` from the environment (never
disk), logs in via POST form fields because basic auth returns Bad Request, and
uses the returned session token in an `X-Auth-Token` header. Its `BOTS_APP_IDS`
is the union of every app id referenced across the v1/v2/v3 READMEs, and it
installs the latest release of each rather than the BOTS-era pin. App 2760
(TA-Suricata) is delisted and superseded by 4242 (TA for Suricata), so 2760 is
absent from the list and 4242 carries the note. Apps load at splunkd startup,
and extraction is search-time, so add-ons installed after the data apply
retroactively.

## Why

BOTS is pre-indexed, which is fast, but it makes the installer a one-way,
on-host mutation: everything lives in `$SPLUNK_HOME/etc/apps` and nothing in
git. The idempotence, the retention pin, and the archive cleanup are all
defenses against that one-way-ness — they let the same script both install and
repair without ever deleting, so a reset can be followed by a safe re-run.
