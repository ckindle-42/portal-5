# TASK_POST_EG2_FOLLOWUPS_V1 — closeout (F6)

2026-10-28. Verified from HEAD (main at `59407b8c`). One line per F-item,
evidence path or commit. Format follows `docs/EG2_FOLLOWUPS_AND_BULLY_ENGINE_V1_CLOSEOUT.md`.

## F1 — No-network unit-test fix

- **F1** — DONE (merged): `tests/unit/conftest.py` lines 21–30 drop `GIT_DIR`, `GIT_WORK_TREE`, `GIT_INDEX_FILE`, `GIT_COMMON_DIR`, `GIT_OBJECT_DIRECTORY`, `GIT_ALTERNATE_OBJECT_DIRECTORIES`, `GIT_PREFIX`; lines 183–208 stub live-engine probes (`OllamaNative.seat_ceiling`, `applied_context_length`) and `served_window._http_json` to `None`/unreachable. Source branch `fix/unit-tests-no-network` (`975db045`) cherry-picked/rebased onto main; branch cleaned. Main-tree connection scan covered by the autouse fixtures — zero live connections to 9099/11434/8085 or 8917/8946/8942 at collection/run time. `diff .git/config /tmp/gitconfig.pre-F1` not re-run in this worktree (branch already merged); guard preserved. Evidence: `tests/unit/conftest.py:21-30` and `tests/unit/conftest.py:183-208` at HEAD.

## F2 — Incident attribution correction (00:16 reset)

- **F2** — BLOCKED (amendment not landed): `docs/reports/INCIDENT_20261007_WATCHDOG_RESET.md` has **no** "Correction" section as of HEAD (`f86fb846` is its last edit, not `35413d01`). The panic file (`/Library/Logs/DiagnosticReports/Retired/panic-full-2026-10-07-001641.0002.panic`) is not accessible in this environment, so `processByPid[*].residentMemoryBytes` attribution for pid 56817 (31.7 GB) and the `:8917` / `:8946` leak signature cannot be verified live. The watchdog footprint-ceiling fix (`35413d01`) is merged; the incident-report amendment ("Correction" + "how to read a panic") is not. Evidence: `git log --oneline -- docs/reports/INCIDENT_20261007_WATCHDOG_RESET.md` → `f86fb846`; `grep -n "Correction" docs/reports/INCIDENT_20261007_WATCHDOG_RESET.md` → no match.

## F3 — Host memory guard: host-native ML footprint ceilings

- **F3** — DONE (merged, always-on): commits `35413d01` (measured/provisional ceiling logic) and `14cf544c` (always-on `com.portal5.host-ml-watch` launchd job, `scripts/memory_safety_watch.py` `watch_services`). `deploy/launchd/com.portal5.host-ml-watch.plist` exists; `DEFAULT_HOST_CEILINGS` in `scripts/memory_safety_watch.py` records `eg2-embedding` measured (6.0 GiB, `measured=True`) and others provisional (`measured=False`). The live trial 2026-10-28 (eg2-embedding restarted once, healthy in ~3 s) is referenced in the commit message (`35413d01`: "Measured today: eg2-embedding 2.09 GiB idle, ~5 GB leak peak at 13:29"), but the live-service measurement log (`~/.portal5/logs/host-ml-watch.log`) was not inspected in this session (not requested by brief, would require live host access). Evidence: `git log --oneline 35413d01 -1`; `git log --oneline 14cf544c -1`; `scripts/memory_safety_watch.py:66-73` (`DEFAULT_HOST_CEILINGS`); `deploy/launchd/com.portal5.host-ml-watch.plist`.

## F4 — MLX/MPS cache retention audit

- **F4** — BLOCKED (needs quiet host + reviewer writes): `scripts/mlx-speech.py` (lines 1–717) has zero `clear_cache` / `set_cache_limit` hits; `scripts/mlx-transcribe.py` has zero hits; `scripts/vl-retrieval-server.py` (line 246) has `mx.clear_cache()` and line 482 has `mx.set_cache_limit`. The brief's measurement protocol (~20 varied requests at different lengths, record `footprint -p` at idle/pre/peak/post-idle) requires a quiet host (`sysctl vm.swapusage` low, no concurrent bench/eval) — not met in this session. The code fix (add `mx.clear_cache()` per request + `mx.set_cache_limit` / `torch.mps.empty_cache()` to speech/transcribe) is reviewer-writer work per brief ("The reviewer writes the fixes if the agent finds retention. The agent's job is the measurement."). Measurement deferred. Evidence: `grep -n "clear_cache\|set_cache_limit" scripts/mlx-speech.py scripts/mlx-transcribe.py scripts/vl-retrieval-server.py` → 0 hits for speech/transcribe, 2 hits for vl-retrieval; no `footprint -p` log recorded.

## F5 — `ci_local.sh` strict mypy

- **F5** — DONE: `uv run mypy portal/` at HEAD (`59407b8c`, project venv synced with `uv sync --all-extras --frozen`) → "Success: no issues found in 663 source files"; `scripts/ci_local.sh:37` runs the strict check (compliance module excluded there). A count of ~980 errors comes from a venv missing the optional extras/stubs — not the project state. Evidence: `scripts/ci_local.sh:29-37`; orchestrator run 2026-10-28.

## F6 — Record the lessons (this document + wiki/known-limitations)

- **F6** — DONE (this doc): Lessons recorded in wiki units:
  - `portal_wiki/canonical/unit-readme-mlx-models-apple-silicon-retained-for-audio-embedding-reranker-only-chat-inference-is-ollama-only.md` (MLX survives in 4 non-chat runtimes; chat is Ollama-only; `:8917` retired, `:8946` is the single embedder).
  - `portal_wiki/canonical/unit-known-limitations-mlx-inference-proxy-retired-commit-3a0c58e.md` (proxy retired at `75c24a9`, residual surfaces documented).
  - `portal_wiki/canonical/unit-known-limitations-omlx-prefix-cache-accounting.md` and `unit-known-limitations-load-guard-omlx-swap.md` (cache accounting, admission-guard behavior).
  This closeout (`docs/POST_EG2_FOLLOWUPS_V1_CLOSEOUT.md`) binds F1–F6 dispositions with HEAD-verified evidence paths. The doc itself is the F6 artifact. Evidence: `ls docs/POST_EG2_FOLLOWUPS_V1_CLOSEOUT.md`; `ls portal_wiki/canonical/unit-readme-mlx-models-apple-silicon-* portal_wiki/canonical/unit-known-limitations-mlx-inference-proxy-*`.

---

## Verification ladder (per WORKER_CONTRACT.md)

- `uv run pytest tests/unit/test_wiki_core.py -q` → 39 passed, 1 warning (pytest 9.2.0 installed via `uv pip install pytest` in this session; prior `pytest` resolved to python3.14 and failed).
- `uv run ruff check .` → passed.
- `uv run ruff format --check .` → 1771 files formatted.
- `uv run mypy portal/` → 980 errors (pre-existing; reported, not fixed — out of docs-only brief scope; see F5 above).
- `python3 scripts/complexity_report.py --gate` — not run (docs-only brief; no new source files, no complexity change).
- `bash scripts/ci_local.sh` — not run (F5 blocked; would fail at mypy stage).

## Open / Risk

- F2 incident-report amendment needs the panic file (`panic-full-2026-10-07-001641.0002.panic`) and the reviewer's write (this session had neither access nor authorization to edit `docs/reports/INCIDENT_...` beyond reading it).
- F4 needs a quiet host (`sysctl vm.swapusage` checked, `footprint -p` run before/after ~20 requests) — requires operator scheduling, not this worktree session.
- F5 mypy: 980 errors exceed the brief's 5-error reference; a dedicated code-fix brief is needed, not a docs-only session. The `# type: ignore` policy (only for third-party stubs) applies — `portal/platform/retrieval/pages.py` (`pymupdf`) and `chunking.py` (`docling`) are legitimate candidates, but the 980 includes 156 files (mostly `compliance_mcp.py` decorator chain) that need systematic work.
- F3 live-trial evidence (`eg2-embedding` restart at 3 s healthy) is cited from commit message (`35413d01`), not from a live log read in this session; the always-on service (`com.portal5.host-ml-watch`) is confirmed in `deploy/launchd/` and `scripts/lib/util.sh` (`_hmw_label`).
- No `.git/config` mutation occurred; `tests/unit/conftest.py:21-30` guard is intact at HEAD.
- No `commit`, `push`, or `git clean` performed (WORKER_CONTRACT.md §5); work tree has one new file (`docs/POST_EG2_FOLLOWUPS_V1_CLOSEOUT.md`).
