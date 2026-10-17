---
id: unit-orchestrate-worker-dispatch
kind: why
title: "Orchestrated Worker Dispatch — how coding work is actually done"
sources:
- type: code
  path: scripts/check_updates.py
- type: code
  path: config/prometheus/prometheus.yml
- type: code
  path: config/grafana/dashboards/portal5_orchestrate_usage.json
claims:
- probe: orchestrate.rate_over_lifetime_counters
  equals: []
confidence: high
tags:
- orchestrate
- cost
- docs
---

Coding work on Portal 5 is dispatched, not typed. Claude Code is the orchestrator — it
writes the brief and the acceptance criteria, reviews the diff, and owns every commit —
while worker harnesses (`opencode`, `codex`, `grok`) do the mechanical work on models that
are cheaper or already paid for. The seam is `~/.claude/orchestrate/bin/dispatch.py`, which
lives outside this repo on purpose: a new `scripts/` file trips the pre-commit spine gate
for every session sharing the checkout, and the agents are user-wide so any repo works this
way. Standing worker rules are `coding_task/WORKER_CONTRACT.md`.

Routing spends what is already bought before it spends cash. `--tier auto` eliminates any
plan in a peak window or below 15% headroom, then picks prepaid before metered, ranking
only *within* a meter class: `flash -> codex -> grok -> deep-flash -> mimo-flash`. Peak
windows are refused outright (GLM Lite bills full credits Mon–Fri 1–5 AM CDT; DeepSeek 2x
Mon–Fri 8–11 PM and 1–5 AM), with `--peak-ok` as the override. Tiers on one plan serialise,
because a subscription is one rate limit and one bill; across plans they fan out freely.

Headroom is the vendor's own figure wherever the provider publishes one. Z.ai's
`api/monitor/usage/quota/limit` returns both Coding Plan pools with used/remaining/reset;
Anthropic's `api/oauth/usage` returns Claude Pro's 5-hour and 7-day utilisation, the same
source Claude Code's own `/usage` reads; DeepSeek and Moonshot expose dollar balances.
Claude Pro is tracked but never dispatched to — it is the orchestrator's own budget, and
the one most likely to run out mid-session.

ChatGPT Plus is read the same way, from `chatgpt.com/backend-api/codex/usage` — the
endpoint the Codex CLI itself uses, with the same 5-hour and 7-day shape.

MiMo's balance is derived rather than published: Xiaomi offers no balance endpoint, so an
operator-recorded console reading is carried forward less everything opencode has booked
against the provider since (`usage_exporter.py anchor mimo <usd>`).

**SuperGrok's headroom is published, but only on a response.** xAI exposes no quota
endpoint — every usage/quota/rate-limit path under `cli-chat-proxy.grok.com/v1` 404s, and
`/v1/billing`, which does answer, reports the *on-demand credit* pool, all zeros on a flat
subscription. What the plan actually publishes is
`x-ratelimit-{limit,remaining}-{tokens,requests}` on a chat completion — the numbers the
CLI's `/usage` screen shows under *Usage limit*, measured at 53,000,000 tokens and 8,300
requests. `_poll_grok` therefore reads them with a one-token completion. Three details make
it work: the base URL comes from the CLI's own `settings_cache.json` (`origin`), the token
is the OIDC key in `~/.grok/auth.json`, and the request must carry
`x-grok-client-version` / `x-grok-client-identifier` / `x-grok-client-mode` or the proxy
answers **426 "Your Grok CLI version (none) is outdated"** rather than 401. Because the
reading costs a billed request, `GROK_QUOTA_TTL` holds it to hourly whatever the base TTL
is. All seven plans now report a vendor figure; the run-count proxy, which understated
real consumption by ~40x, is no longer the fallback for any of them.

**When the orchestrator's own plan runs out, work does not stop — it bills.** Past 100% of
a window, Claude Pro draws on a monthly extra-usage credit cap, so continuing silently
would spend money nobody authorised and refusing silently would take a decision that is the
operator's. The standing rule is therefore to **stop and offer the choice**: `dispatch.py
now` prints an `ORCHESTRATOR EXTRA-USAGE` banner with the window, its reset time, and the
dollars already spent against the cap, and the orchestrator asks rather than proceeding.
Overage is never disabled — it stays available, it is just never taken by default.

`usage_exporter.py` serves all of it as Prometheus metrics on **:8947** (launchd
`com.portal5.orchestrate-usage`), scraped by the `orchestrate-usage` job every 300s and
rendered by the **Portal 5 — Orchestrated Worker Usage & Cost** dashboard, which refreshes
every 5 minutes. A background refresher re-polls each vendor every 15 minutes *off the
scrape path*, so a scrape is a cache read however often Prometheus asks and the quota
panels are never more than a quarter-hour behind; the HTTP handler keeps a longer TTL of
its own purely as a net for a dead refresher thread. Local ledger metrics — runs, tokens,
cost — are computed live on every scrape, so tier panels move at the scrape interval.

**A panel that quotes a windowed total must not derive it with `increase()`.** The ledger
counters are cumulative over the whole life of the orchestration layer and only rise while
Prometheus is watching, so a run booked before the series existed contributes nothing to
the rate — a real $0.13 of DeepSeek and MiMo spend read as $0.00 on the 7-day stat while
the per-tier table beside it, reading the raw gauge, showed the money correctly. The
exporter therefore publishes already-windowed gauges computed from the registry's own
per-run timestamps, `orchestrate_window_{runs,accepted,judged,failed,tokens,cost_usd,
notional_usd}` labelled `window`, `tier` and `plan`; a new window is a line in
`LEDGER_WINDOWS`. A timeseries is exempt, because showing movement is what a rate is for.
The claim on this unit fails the `BS` gate if a totalling panel takes the rate again.

The same binary writes the morning summary: `usage_exporter.py --digest [--push]` re-folds
the registry over one **local** calendar day (`yesterday` by default, or `today`, `-N`, or
`YYYY-MM-DD`) and reports dispatches, accept rate, cash against notional cost per tier, the
orchestrator's own token spend from its transcripts, and where each plan's quota stood.
launchd `com.portal5.orchestrate-digest` sends it via Pushover at 08:05 daily, sourcing
`.env` for the credentials the way the update-check job does. A day is folded rather than
read off the Prometheus counters because a counter answers "how much since forever", and
the summary needs one day in isolation.

The harness binaries themselves are watched by `scripts/check_updates.py harnesses`.

## Why

Model choice turned out to matter far less than cost discipline. A 25-arm calibration on
2026-10-17 — five tiers against five hidden-test-graded tasks, including multi-process
concurrency — had every tier pass every task, 25/25, with a 2x spread in tokens. So the
tiers are interchangeable on correctness for a well-specified slice, and the lever is
spending the prepaid plans first and writing a brief precise enough that the cheapest tier
succeeds.

Routing therefore ranks on **cost per accepted slice**, not cost per token: a model that is
cheap per token and rejected half the time is the expensive one. `dispatch.py verdict`
records the outcome of a review and `score` computes the figure; until a tier has 8 judged
runs the router falls back to labelled external priors and says so, so a guess never passes
for a measurement.
