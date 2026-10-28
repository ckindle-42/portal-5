---
id: unit-ADMIN_GUIDE-pull-additional-models
kind: what
title: "ADMIN_GUIDE \u2014 Pull Additional Models"
sources:
- type: code
  path: launch.sh
- type: code
  path: portal/platform/inference/cli/models.py
- type: code
  path: portal/platform/inference/cli/update.py
claims: []
confidence: high
tags:
- ADMIN_GUIDE
- docs
- verified-v1
created_at: 1784950000.0
updated_at: 1784950000.0
---

# Pull additional models

Pull the Ollama model set for a fresh install or a re-sync of the model
registry.

```bash
./launch.sh pull-models
```

`pull-models` dispatches to `portal models pull`, which reads the `models:`
block of `config/portal.yaml`. A Hugging Face entry is imported only when it
pins `filename` and `sha256`: the CLI downloads that file, checks the digest,
and runs `ollama create` from a Modelfile that carries `FROM` and the entry's
`num_ctx`. After create, `ollama show --modelfile` must not contain a
`<think>` stop or any stop the entry does not list in `stops`. An entry
missing the pin is reported and skipped. `portal update` refreshes the model
ids on `type: ollama` backends in `config/backends.yaml`. A library tag is
`ollama pull`. A baked-context tag (`-ctxNk`, or `-ctxNk-agentic`) refreshes
its base, then `ollama create` writes `FROM` that base and `PARAMETER num_ctx`
— the same Modelfile as `portal models apply-params`. An entry `num_ctx` wins
over the suffix. An `hf.co/` base is created only when that base pins
`filename` and `sha256`; otherwise the derived tag is skipped. A `portal5/`
tag is skipped as a local tag with no upstream unless that entry has the pin.
A bare `hf.co/` id uses the same pin-and-create path.

## Why

Model acquisition stays in config. `config/portal.yaml` holds the Hugging Face
pull registry and `config/backends.yaml` holds the fleet ids that `portal update`
refreshes. Pins live on those entries, so the pull set stays the fleet the
operator edited.
