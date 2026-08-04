---
id: unit-corpus-injection-lane-a-bots-pre-indexed-datasets
kind: what
title: "corpus_injection \u2014 Lane A \u2014 BOTS pre-indexed datasets"
sources:
- type: code
  path: scripts/lab_bots_install.py
last_generated_commit: 2f35b5ad508cd284e75ad0735ab7db02961001dd
claims: []
confidence: high
tags:
- verified-v1
created_at: 1784946220.5822139
updated_at: 1784946220.5822139
---

BOTS ships as pre-indexed Splunk buckets, so it does **not** go through HEC.
`scripts/lab_bots_install.py` downloads each tarball (botsv1/botsv2/botsv3
from the published S3 URLs), verifies md5 where one is published, and untars it
into `$SPLUNK_HOME/etc/apps`; each dataset then serves its own `botsvN` index
queried directly with `index=botsvN`. The script must run on the Splunk host
because it writes `$SPLUNK_HOME` and shells out to `curl` for downloads (the
bundled python has no ssl module). It is idempotent and additive-only — a
dataset whose app dir already exists is skipped, and archives are deleted after
a successful extract unless `--keep-archives` is passed.

```bash
docker exec splunk /opt/splunk/bin/python3 /tmp/lab_bots_install.py --only botsv3
```

## Why

Pre-indexed buckets are the fastest way to stand up a large, well-known
labeled dataset: nothing needs to be parsed or re-shipped, the bucket files
already carry their own indexes, and Splunk reads them as-is. The tradeoff is
that the installer is a one-way, on-host operation — it mutates the Splunk
host's app directory directly, so retention pinning and restart are part of the
same script rather than a separate pipeline.
