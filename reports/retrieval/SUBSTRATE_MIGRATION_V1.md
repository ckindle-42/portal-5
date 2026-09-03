# SUBSTRATE_MIGRATION_V1 — status

`TASK_RAG_SUBSTRATE_MIGRATION_V1` (program `PROGRAM_RETRIEVAL_AND_COMPLIANCE_V1`
track T2). Built on T1's byte-identical seam + stage-set stamp.

**Status: P1 and P2 delivered and pushed. P0 complete. P3–P5 `honest-BLOCKED` —
there are no production KBs on this machine to migrate.**

| phase | state | commit |
|---|---|---|
| P0 discovery | done (findings below) | — |
| P1 defects (O1, O10, import sweep) | **done** | `fix(deps,cad): declare CAD render deps …` |
| P2 payload (O2, O3) | **done** | `feat(rag): return citable locators …` |
| P3 substrate changes (O7/O5/O4/O6, S0, τ) | **blocked** — needs live stack + per-KB corpora | — |
| P4 gates/claims (O9), verdict comments | partial — see below | — |
| P5 empirical rollup | blocked with P3 | — |

---

## P0 — Discovery

### Part 1 re-verified at HEAD

| defect | HEAD state |
|---|---|
| **O1** `matplotlib` undeclared | **confirmed.** Imported at `cad_render_mcp.py:104` inside `_render_mesh_to_png`'s CPU fallback, present in `Dockerfile.mcp:86` but not `pyproject.toml`. Fixed in P1. |
| **O10** `check_updates` drift advice | **already fixed at HEAD** by `TASK_VL_RETRIEVAL_HARDENING_AND_CLOSEOUT_V2 D1`. `check_updates.check_python_deps` reports drift direction (`venv_ahead` via `-`/`~` lines), refuses `uv sync` when the venv is ahead, and its `except` path sets `rep.status = "error"`. `scripts/lib/venv_preflight.sh` carries the same direction-aware logic for the launchd services. Confirmed, not re-fixed. |
| **O7** visual arm indexes every page | **confirmed.** `pipeline._ingest_pages` renders + VL-embeds to `pages.MAX_PAGES` (500); `figure_pages` is applied only inside `_ingest_page_transcripts`. |
| **O5** docling `HybridChunker` unused | **confirmed.** `extraction.py` calls `rag_mcp._docling_convert` for a markdown string; `chunking.py` regexes section boundaries over the export. `DoclingDocument` (with `prov.page_no`) is discarded. |
| **O2** text hits carry no page/offsets | **confirmed at HEAD, fixed in P2.** `char_start`/`char_end` were in the store schema (`store.py:135-136`) and never surfaced by `fusion.py`. |
| **O3** visual hit ships a placeholder | **confirmed at HEAD, fixed in P2.** `fusion.py` emitted `text: "[page image f.pdf p3]"`; `context_inject._extract_snippets` injected it as grounding. |
| **O4** no sparse arm | **confirmed.** `pipeline.py:202` hardcodes `"fts_index": False`; `create_fts_index` is never called. |
| **O6** `contextualize` unused | **confirmed.** No heading-path concatenation reaches the embedded text in `chunking.py`. |

### KB inventory — **BLOCKED**

`PORTAL5_LANCE_DIR` = `/Volumes/data01/portal5_lance` (mounted). Its `rag/`
subtree contains **one** KB:

```
rag/kb_kb1.meta.json  ->  {"embed_model": "model-A-2048", "vl_dim": 2048}
```

`model-A-2048` is a test-fixture embedding id, not a real VL model. **There are
no production KBs on this machine.** The 14 consumer KBs the task migrates do not
exist locally — they would each have to be built first from their persona's
source corpus, against a running VL retrieval server (`:8942`), at real ingest
cost (minutes to hours per KB).

Consequently the following P0 deliverables cannot be produced:

- KB inventory with row counts / size / ingest cost — nothing to inventory
- per-KB query sets — no KBs to attach them to
- `_figure_pages` impact per KB — no corpora
- baseline captures for the per-KB migration protocol

The task's own instruction covers this: *"A KB with no query set cannot be
migrated with evidence; say so now rather than at P5."* Said here.

### docling availability

`docling` is pinned at `>=2.99.0` in the `rag` extra with an explicit ceiling
comment: `docling >= 2.100` pulls `docling-core[chunking]` which caps
`transformers < 5.9.0` against the `>= 5.16.1` the `qwen3_vl` path needs. The
`chunking` extra (which provides `HybridChunker`) is **not currently resolved** —
adding it is itself a dependency decision gated on the transformers pin, per the
`pyproject.toml` comment and the task's own anti-pattern list (*"Do not
`pip install docling` bare"*). This is a prerequisite to P3.2, not done here.

---

## P1 — Defects (delivered)

- **O1** — new `cad` optional-dependency group (`trimesh[easy]`, `pyrender`,
  `matplotlib`, `numpy-stl`, `jsonschema`) mirroring the pip half of
  `Dockerfile.mcp`'s CAD deps, with a comment naming the fallback.
  `cadquery`/`build123d`/`ocp` stay conda-forge-only. `uv.lock` regenerated,
  venv synced. `test_cad_render_fallback.py` forces `scene.save_image` to raise
  and asserts the matplotlib path writes a real (signature-checked) PNG.
- **O10** — verified already fixed (above); no code change.
- **Import sweep (P1.2)** — imported every first-party `portal.*` module and
  extracted every third-party import (including in function bodies) from
  `scripts/*.py`. No new O1-class latent-fallback defect in first-party runtime
  code. `scripts/` third-party misses: `bench_lab_exec` / `bully_*_run` / `lib` /
  `alias_census` / `complexity_report` are sibling-script modules (false
  positives from a top-level-name match); `tomli` is the pre-3.11 `tomllib`
  fallback; `sentence_transformers` is imported only by the retired CPU
  `scripts/embedding-server.py`; `ruamel`/`evtx` are lazy deps of non-runtime
  tooling. None are a matplotlib-style "fallback raises when it's needed" bug.

## P2 — Payload (delivered)

- **O2** — text hits now return `char_start`, `char_end` (from the stored row)
  and `page`. `page` is `null` until the docling chunker (P3.2) supplies it —
  the field is present-but-absent, never fabricated.
- **O3** — visual hits return `text: null`, `content_available: false`,
  `locator: {source_file, page}`, `pointer_note`. The placeholder string is
  gone. `context_inject._extract_snippets` skips any row with
  `content_available is False`, so a page-image pointer never reaches the model
  as grounding.
- `fusion._text_payload` / `_visual_payload` are the single shaping point for
  both fusion modes. T1's contract test extended for the new fields; unknown-field
  tolerance intact; `test_retrieval_payload.py` covers the shapers + the snippet
  filter directly. No index change.

## P4 — partial

- **Verdict comments (Part 2 table)** — left unchanged. Every one of them
  (`VL_TEXT_GATE` τ, `structured` vs `fixed`, S0, `VL_FUSION=unified`, rerank
  depth) is void *pending a re-run on a real corpus*. With no KBs to re-run
  against, correcting them now would replace one unverified claim with another.
  They stay as-is with this report as the pointer to why.
- **O9** (`unit-capability-rag` nominal probe) — not done; deferred with P3 since
  part of the intended binding is "stage set stamped and matching the running
  composition", which needs a live composition.

---

## What P3–P5 needs to proceed

1. A running VL retrieval server (`:8942`, `Qwen3-VL-Embedding-2B`) and Ollama.
2. Each of the 14 consumers' source corpora staged under their KB's ingest path.
3. Per-KB query sets (from persona traffic or authored fixtures) — the task
   flags "a KB with no query set" as a finding, and several will have none.
4. The `docling[chunking]` dependency decision (transformers pin) resolved.
5. Time budget for per-KB re-ingest + before/after measurement — the task
   forbids migrating more than one KB at a time and forbids aggregate-only
   reporting.

None of that is a code blocker — it is an environment and evidence blocker, and
the task is explicit that nothing in P3 lands without the consumer's own
evidence. P1 and P2 (which the task groups as "land immediately", no re-ingest)
are complete.
