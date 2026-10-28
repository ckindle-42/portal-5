---
id: unit-known-limitations-ollama40-model-store
kind: what
title: Ollama 0.40 Model Store — v2 Manifests, Hidden llamacpp Builds, and the Safe Blob-Deletion Reference Set
sources:
- type: code
  path: scripts/model_upstream.py
- type: code
  path: scripts/check_updates.py
- type: code
  path: scripts/model_autoupdate.py
claims: []
confidence: high
tags:
- known-limitations
- ollama
- storage
created_at: 1793220490
updated_at: 1793220490
---

#### Ollama 0.40 model store — v2 manifests, hidden llamacpp builds, and the safe blob-deletion reference set (2026-10-28)

- **ID**: P5-OLLAMA-STORE-001
- **Status**: OPEN. The store layout is engine behaviour, not a Portal defect; what has to hold is the reference-set rule below.
- **Description**: Ollama 0.40 keeps tag manifests in BOTH stores: `manifests/` (v1 layout, regular files) and `manifests-v2/` (0.40, every entry a symlink into `blobs/`). 50 of the 104 tags `ollama list` shows have their only manifest in `manifests-v2/`, so a walk of `manifests/` alone sees about half the installed tags (measured 2026-10-28). The engine also writes hidden engine builds at `manifests/registry.ollama.ai/library/llamacpp/<sha>` that `ollama list` never shows — four on this store, carrying their own weights blobs of 2.3–18.4 GiB each. `<sha>` is the config-blob digest of the tag the build was made from; when the source tag is removed the build is orphaned and is not pruned on restart — all four builds here are orphaned (each `<sha>` names an existing config blob, and no installed tag in either store has that config digest), and they outlived the 2026-10-28 11:00 daemon restart, the oldest dating from 2026-10-06.
- **Impact**: any blob-deletion pass that walks `manifests/` alone takes half the installed tags — and every blob only they name — for garbage. A manifests/-only walk deleted a live tag's weights on 2026-10-28 (rebuilt the same hour). The hidden llamacpp builds are a second blind spot: a tag-only reference set never sees their weights at all, and no restart reclaims them, so they accumulate.
- **Mitigation**: the safe reference set for any blob deletion is the union of (a) every `FROM /…/blobs/sha256-…` line in `ollama show <tag> --modelfile` for each installed tag — tag-to-blob facts taken from Ollama itself — and (b) every digest named by any manifest file in BOTH stores. That union is what the tooling encodes: `scripts/model_upstream.py` deletes a blob only when `ollama show` and both manifest stores leave it unnamed (refcounted delete), feeding the models component of `scripts/check_updates.py` and the weekly replace in `scripts/model_autoupdate.py`. Tags that differ only by a baked `num_ctx` (`-ctxNk`) share one weights blob (verified across the gemma4 26b, granite4.1 30b and qwen3-coder 30b families), so per-tag size accounting double-counts and tag-similarity heuristics are unsafe.
- **Evidence**: 2026-10-28 on the data01 store: `manifests/` = 58 regular files (54 tags + 4 llamacpp builds), `manifests-v2/` = 58 entries, all symlinks into `blobs/`; `ollama list` = 104 tags, of which 54 resolve in `manifests/` and 50 only in `manifests-v2/`, none unaccounted; each llamacpp filename exists as a 665–1160-byte config blob in `blobs/` while matching no installed tag's config digest; orphan mtimes 2026-10-06 through 2026-10-09 against daemon start 2026-10-28 11:00.

#### Why

Deletion is the one store operation that cannot be undone quietly: the file that goes missing is the weights blob behind a tag the operator still runs. 0.40 split the manifest store without changing the walk that every existing cleaner had hard-coded, so a v1-era reference set is silently half-sized, and the hidden llamacpp builds are a second blind spot on top of it. Deriving the safe set from `ollama show` plus both stores is the only union that names every live byte; anything smaller eventually deletes something live, as the 2026-10-28 deletion showed.
