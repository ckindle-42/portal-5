# OMLX evaluation — CANCELED (P5-FUT-013)

This directory archives the OMLX (`github.com/jundot/omlx`) evaluation
configuration from the 2026-04-25 bake-off. The bake-off concluded
**RETIRE** on the same day because the headline KV-cache persistence
feature was not functioning (warm TTFT 21% slower than cold).

See `OMLX_DECISION.md` at the repo root for the full rationale,
benchmark numbers, and evidence summary.

## What's archived

| File | Purpose |
|---|---|
| `config.yaml` | OMLX server + KV-cache config for the bake-off |

## Status: archive-only

OMLX is not installed or referenced anywhere in the live stack as of
HEAD. The mlx-proxy reference baseline that this config was compared
against is itself archived at
`scripts/_archive/mlx-retired-3a0c58e/` (retired 2026-06-09).

## When to consult these

- A future operator considers an OMLX-like KV-cache architecture and
  wants to read the prior eval's config shape.
- Someone wonders whether KV cache persistence was ever measured —
  yes, and the OMLX decision doc records that it wasn't working.

## See also

- `OMLX_DECISION.md` (repo root) — operator decision record + evidence
- `scripts/_archive/mlx-retired-3a0c58e/` — the mlx-proxy baseline
  OMLX was evaluated against; itself retired 2026-06-09
