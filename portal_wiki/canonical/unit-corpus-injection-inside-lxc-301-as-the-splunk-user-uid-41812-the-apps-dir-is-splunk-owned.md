---
id: unit-corpus-injection-inside-lxc-301-as-the-splunk-user-uid-41812-the-apps-dir-is-splunk-owned
kind: what
title: "corpus_injection \u2014 inside LXC 301, as the splunk user (uid 41812) \u2014\
  \ the apps dir is splunk-owned."
sources:
- type: doc
  path: docs/security/corpus_injection.md
  commit: 05e42ec2
  section: "inside LXC 301, as the splunk user (uid 41812) \u2014 the apps dir is\
    \ splunk-owned."
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.5825438
updated_at: 1784946220.5825438
---

docker cp scripts/lab_bots_install.py splunk:/tmp/
docker exec -u splunk splunk /opt/splunk/bin/python3 /tmp/lab_bots_install.py \
    --workdir /opt/splunk/var/p5corpus
```

The installer is idempotent (a dataset whose app dir exists is skipped) and
additive-only. Re-running it repairs retention on an already-installed dataset.

Operational notes learned installing this, worth keeping:

- **Sizing.** The three datasets are ~24 GB of download and roughly the same
  again extracted. The installer refuses to start a dataset it cannot fit and
  deletes each archive after a successful extract.
- **Retention is a time bomb.** Each dataset ships
  `frozenTimePeriodInSecs = 377395200` (~12y) measured from the *event*
  timestamps, and BOTS v1's events are from 2016. Left alone the buckets
  silently freeze and are deleted (no `coldToFrozenDir` is set). The installer
  writes a `local/indexes.conf` override raising the ceiling, without editing
  the shipped default.
- **Bucket compatibility.** BOTS was built on Splunk 6.5/7.x. The lab runs
  Splunk 10.2 and reads those buckets without conversion.
- **Registering a new index may need more than a restart.** Splunk only
  discovers a newly added app at startup, and a `splunk restart` will be
  *refused* while a KVStore upgrade is pending or failed. When that happens,
  register the index directly against the existing bucket paths instead:

  ```bash
  curl -ks -u "$LAB_SPLUNK_USER:$LAB_SPLUNK_PASSWORD" \
    -X POST "$LAB_SPLUNK_URL/services/data/indexes" \
    -d name=botsv2 \
    -d 'homePath=$SPLUNK_HOME/etc/apps/botsv2_data_set/var/lib/splunk/botsv2/db' \
    -d 'coldPath=$SPLUNK_HOME/etc/apps/botsv2_data_set/var/lib/splunk/botsv2/colddb' \
    -d 'thawedPath=$SPLUNK_HOME/etc/apps/botsv2_data_set/var/lib/splunk/botsv2/thaweddb'
  ```

Verify (counts are large; `tstats` avoids a full scan):

```bash
| tstats count where index=botsv1 OR index=botsv2 OR index=botsv3 by index
```

**Field extraction / Splunkbase add-ons.** BOTS ships raw events; the field
aliases and CIM normalization live in Splunkbase add-ons listed in each
dataset's README. Without them the data is still fully searchable, but
sourcetype-specific fields (Sysmon, Windows TA, Stream, Suricata) do not
extract, so the published BOTS hunt searches match nothing.

Splunkbase app *pages* are public but the **download endpoint returns 401** — it
needs a splunk.com account. `scripts/lab_splunkbase_install.py` handles the
whole flow; credentials come from the environment and are never written to disk:

`SPLUNKBASE_USERNAME` / `SPLUNKBASE_PASSWORD` live in `.env` (gitignored;
placeholders in `.env.example`), so sourcing it is all that is needed — there is
nothing to remember or paste:

```bash
set -a; . ./.env; set +a
docker cp scripts/lab_splunkbase_install.py splunk:/tmp/
docker exec -u splunk -e SPLUNKBASE_USERNAME -e SPLUNKBASE_PASSWORD \
    splunk /opt/splunk/bin/python3 /tmp/lab_splunkbase_install.py
```

These are **install-time only** — no runtime or serving path reads them, which
is why they are not part of the stack's env contract.

Its `BOTS_APP_IDS` is the union of every app id referenced across the v1/v2/v3
READMEs. It installs the **latest** release of each rather than the BOTS-era
version pinned in the README, because those are Splunk 6.5/7.1-era builds and
this lab runs Splunk 10.2. Two auth details that cost time:

- Basic auth against `api/account:login/` returns `Bad Request`; the endpoint
  wants the credentials as **POST form fields**, and returns the session token
  as `<id>` in an Atom feed. That token then goes in an `X-Auth-Token` header.
- App **2760** (TA-Suricata, named in the v1/v2 READMEs) is fully delisted —
  every version 404s. It is superseded by app **4242** ("TA for Suricata").

Add-ons load at splunkd startup, so restart afterwards. Extraction is
search-time, so add-ons installed *after* the data still apply retroactively —
there is no need to reinstall or re-index a dataset to pick up a new TA.
