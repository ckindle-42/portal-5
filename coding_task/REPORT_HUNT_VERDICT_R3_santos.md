# REPORT — Hunt Round-3 live proof & verdict for **santos** (`hb_ait_santos_v2`)

**santos: pending (run in flight)**

Lane `lane/hunt-proof-r3-santos`, worktree `/Users/chris/projects/portal-5-hunt-proof-r3-santos`,
base `a62f9bc45` (all eight slices E0–E7 merged: E0, E1, E2, E3, E5, E6, E7 via `fc7d84cc3`;
E4 via `a62f9bc45`). Brief `coding_task/BRIEF_HUNT_PROOF_R3_santos.md`; acceptance
`docs/hunt/ORCACYBER_DEEP_DIVE_3.md` §6–§7.

No code, no Splunk configuration and no `launch.sh` was changed or run. Held-out sets
(`hb_ait_wheeler`, `hb_cloudobs_aws`, `botsv1`) were never opened, queried or read. `.env` was
read by key name only (six named keys, no `source`); no secret appears in this report.

## 0. Preflight (before the run)

| check | receipt |
|---|---|
| Splunk | `https://10.0.1.30:8089` answered `services/server/info`, version **10.2.5**, build `1d180ea50aed` |
| target index | `hb_ait_santos_v2` present (index list read with `count=0`; no held-out index queried) |
| Pipeline judge | `GET /v1/models` lists `hunt-reasoning`; a 1-token probe answered `Yes`, served `gemma-4-26b-a4b-it-QAT-4bit` |
| Pipeline embedding | `POST /v1/embeddings model=google/embeddinggemma-2` returned **768** dims |
| inputs | `keys.jsonl` 7,799,762 B; `knowledge_v2_20261116.duckdb` 8,925,184 B; neon baseline dir present |
| merge weights | `PORTAL_HUNT_MERGE_WEIGHTS={"alerts":1,"deviation":2,"misfit":1,"peer_rare":1,"relate":1,"similar_to_known":5}` (brief-supplied neon 3-family vector) |
| output | `/Volumes/data01/portal5_hunt/hunt_proof_r3_santos/v3/santos` |

## 1. Run

In flight. Receipts to be filled from `run.log`, `progress.json`, `sources.json`,
`behaviours.duckdb` and the scoreboard.

## 2. Per-slice table (E0–E7)

To be filled.

## 3. Scoreboard vs neon baseline

To be filled.
