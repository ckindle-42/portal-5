---
id: unit-readme-license
kind: what
title: "README \u2014 License"
sources:
- type: code
  path: pyproject.toml
claims:
- probe: repo.path.exists
  path: pyproject.toml
  equals: true
confidence: high
tags:
- docs
- verified-v1
---

Portal 5 is released under the MIT License — see [LICENSE](LICENSE) at the repo
root for the full text. MIT grants permission to use, copy, modify and distribute
the code for any purpose, including commercial use, subject to preserving the
copyright and permission notice.

## Why

MIT was chosen because the project is a local-first enhancement layer on top of
Open WebUI, and permissive licensing removes friction for operators who want to
fork or vendor it internally. The individual GGUF models and runtimes it
orchestrates carry their own licenses (for example gated HuggingFace repos
require `HF_TOKEN`), which are separate from the project license.
