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
claims: []
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
against the provider since (`usage_exporter.py anchor mimo <usd>`). SuperGrok is the one
plan that exposes nothing readable at all — accounts.x.ai serves HTML and the CLI's
subscription check is not reachable as REST — so it falls back to counting local runs, a
proxy that understated real consumption by ~40x when measured, because one dispatch is
many billed requests. There, the reliable signal of exhaustion is a dispatch failing.

**When the orchestrator's own plan runs out, work does not stop — it bills.** Past 100% of
a window, Claude Pro draws on a monthly extra-usage credit cap, so continuing silently
would spend money nobody authorised and refusing silently would take a decision that is the
operator's. The standing rule is therefore to **stop and offer the choice**: `dispatch.py
now` prints an `ORCHESTRATOR EXTRA-USAGE` banner with the window, its reset time, and the
dollars already spent against the cap, and the orchestrator asks rather than proceeding.
Overage is never disabled — it stays available, it is just never taken by default.

`usage_exporter.py` serves all of it as Prometheus metrics on **:8947** (vendor polls
cached hourly; launchd `com.portal5.orchestrate-usage`), scraped by the `orchestrate-usage`
job and rendered by the **Portal 5 — Orchestrated Worker Usage & Cost** dashboard. The
harness binaries themselves are watched by `scripts/check_updates.py harnesses`.

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
