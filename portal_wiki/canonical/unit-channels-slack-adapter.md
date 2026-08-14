---
id: unit-channels-slack-adapter
kind: mixed
title: "Slack channel adapter \u2014 socket-mode pipeline bridge"
sources:
- type: code
  path: portal_channels/slack/bot.py
  commit: c23c27d9
claims: []
confidence: high
tags:
- authored-v1
- channels
- slack
created_at: 1785795183.754003
updated_at: 1785795183.754003
---

The Slack channel adapter lets a workspace persona be reached from Slack —
either by @mentioning the bot in a channel or by direct message — while keeping
all intelligence in the pipeline. It listens via Socket Mode, so it needs no
public webhook endpoint, and it is a thin transport: the routing decision is
made by mapping the channel name to a workspace and then delegating to the
shared `call_pipeline_sync` dispatcher.

## Why

The channel-to-workspace mapping is the interesting design choice: a channel
named `coding` routes to `auto-coding`, `redteam` and `blueteam` route to
`auto-security` with a variant (`redteam` / `blueteam`) rather than their own
workspace, and `images` maps to `auto-vision` because `auto-images` is not a
valid id. Hard-coding that map in the bot keeps the intelligence out of the
adapter while still letting a channel's name steer which model answers. Tokens
are read inside `build_app` rather than at import so that importing the module
in tests never crashes on a missing `.env`.

## Interfaces

`build_app()` wires the `app_mention` and `message` handlers and returns the
Slack app plus its Socket Mode handler. `_workspace_for_channel` resolves a
channel name against `CHANNEL_WORKSPACE_MAP` with a case-insensitive substring
match, falling back to `DEFAULT_WORKSPACE`. The DM handler skips bot messages
and edits so the bot does not reply to itself or to message mutations.

## Gotchas

The map uses substring matching, so a channel named `data-science` would hit
`data` before anything more specific — ordering matters. Replies are posted to
the same thread (`thread_ts`) when the mention came from a thread, keeping the
conversation contiguous.
