# Trace WARN triage — 2026-11-19 sweep (33 WARNs)

Source: `/tmp/trace_full_20261119.log` (`SUMMARY PASS=231 FAIL=15 WARN=33`), lane
`lane/trace-revision-vision`. Verdicts below are from read-only live state (pipeline
receipts in the container's `/tmp/portal_traces`, `/opt/homebrew/var/log/ollama.log[.1.gz]`,
launchd plists/logs, boot time) plus repo config. "Fixed" means fixed in this lane's diff;
live re-run belongs to the orchestrator.

## A. launchd `runs=0` — 4 WARNs — EXPECTED (weekly jobs, counter reset by reboot)

| WARN | Schedule (repo plist) | Last successful run (job log) |
|---|---|---|
| `process com.portal5.model-update` | Mon 02:47 | `~/.portal5/logs/model-update.launchd.log`: Nov 2/9/16 02:47 |
| `process com.portal5.security-update` | Sun 03:17 | `security-update.launchd.log`: Nov 15 03:18 |
| `process com.portal5.update-check` | Mon 13:07 | `update-check.launchd.log`: Nov 16 13:08 |
| `process com.portal5.weekly-rebuild` | Sun 05:47 | `weekly-rebuild.launchd.log`: Nov 15 05:59 "OK in 13 min" |

Host booted Tue Nov 17 15:31 (`kern.boottime`); model/security/weekly-rebuild plists were
reinstalled Nov 19 11:45 (engine-update pass), which resets launchd's `runs` counter. No
scheduled fire time has occurred since the reboot — next are Sun Nov 22 / Mon Nov 23.
The jobs are healthy; the WARN is launchd's truthful "not since load". No trace change:
teaching `process_hop` calendar arithmetic would be new mechanism for a false positive
that resolves itself on the next fire.

## B. reasoning-only turns — 13 WARNs — REAL GAP, trace-side (fixed: MAX_TOKENS 24→256)

`auto`, `auto-coding::northmini`, `auto-coding::uncensored`, `auto-coding::lite`,
`auto-coding::gemma4-heretic-coder`, `auto-coding::glm-coder`, `tools-specialist`,
`auto-reasoning`, `auto-reasoning::math`, `auto-reasoning::glm-thinker`,
`auto-documents::extract-uncensored`, `auto-research`, `auto-vision`.

Every one of these receipts shows `reasoning_tokens=24, answer_tokens=0` — the trace's own
24-token cap ended the turn inside reasoning (pipeline receipts, e.g. `p5-feff3569c1ed`).
Measured reasoning decode rates 10.9–155 t/s; 256 tokens adds ≤24 s on the slowest seat,
inside the 180 s per-turn timeout. Seats that still exhaust 256 will WARN honestly.

## C. `resident council` unconfirmed — 1 WARN — REAL GAP, trace-side (fixed)

`ValueError: council is not declared in config/backends.yaml`. `council` is the router's
synthesized verdict backend (`router/handlers.py` emits `{workspace};council;{synth_model}`);
no engine holds it resident. `residency_hop` now PASSes it as router-synthesized; member
models are residency-checked on their own seats.

## D. `not run (budget)` — 15 WARNs — REAL GAP, trace-side (fixed: budget 900→1800 s + full-timeout rule)

`auto-vision::gemma_vision`, `security-reviewer`, `hunt-reasoning`, `auto-compliance`,
`auto-compliance::reading`, `compliance-mapping`, `compliance-council-qwen38`,
`compliance-council-granite41`, `compliance-council-deepseek-r1`,
`compliance-reading-overflow`, `auto-audio`, `auto-audio::image`, `auto-audio::video`,
`auto-audio::music`, `task-router`.

The sweep started 17:01:41Z with a 900 s budget; 61 of 77 seats graded by 17:16:40Z
(~14.4 s/seat). The 16 remaining seats include the media turns measured the same day in
the MEDIA section (image 24.8 s, video 57.6 s, music 145.8 s) — estimated ~450–600 s more,
plus ≤90 s extra reasoning decode from fix B. 1800 s covers the roster with headroom; a
seat now runs only when the remaining budget covers the full 180 s per-turn timeout,
otherwise it is reported `not run (budget)` with the shortfall — never issued a doomed
sliver (that is what FAILed `gemma4jangvision`, see the lane brief/report).

## FAILs (15) — for completeness

- 14× `revision … label=2dbaa400675c expected head=e006c3c3207e`: the copied-path set
  included `config/grafana/dashboards/…` (changed by the grafana merge e006c3c32), which
  only the stock grafana container consumes via bind mount. Fixed: runtime-mounted stock
  config is excluded from the staleness pathspec; offline recompute against the real repo
  now yields head=2dbaa4006=label → PASS for all 14.
- 1× `auto-vision::gemma4jangvision ReadTimeout`: budget sliver (~1.05 s), not the seat.
  Receipt `p5-160ed7f6f617` outcome=interrupted duration_ms=1050.7; ollama log 17:16:41Z
  "client connection closed before llama-server finished loading, aborting load". The
  seat is healthy: 11-18 log shows two complete trace-shape turns (182-token prompt,
  24-token answer), load 11.76/11.84 s, end-to-end ~16–17 s.