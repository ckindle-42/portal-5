---
id: unit-browser-mcp-http-wrapper
kind: mixed
title: "Browser MCP \u2014 the guarded web-automation surface"
sources:
- type: code
  path: deploy/playwright-mcp/browser_mcp.py
  commit: 9751c754
last_generated_commit: 9751c754
claims: []
confidence: high
tags:
- authored-v1
- mcp
- browser
created_at: 1785794738.164835
updated_at: 1785794738.164835
---

The browser MCP is Portal 5's web-automation surface: it wraps Microsoft's
stdio-only Playwright MCP (`@playwright/mcp`) into the HTTP MCP fleet so that
personas and the tool registry can drive a real browser. The wrapping is not
mechanical — every call passes through a security gate that URL-filters the
target, rate-limits per domain, redacts secrets from audit logs, and refuses
sensitive form fields unless a persona explicitly carries the credential-fill
privilege. It is the only MCP server that reaches an arbitrary external
destination, which is exactly why it carries the strongest admission controls.

## Why

A browser tool is a SSRF machine wearing a GUI: pointed at
`http://169.254.169.254` it reads the cloud metadata service, and pointed at a
login form it can exfiltrate whatever a user types. The blocking rules therefore
cover the *whole* loopback range (`127.` prefix, not just `127.0.0.1`) and the
full link-local range (`169.254.`), so a permissive rewrite or a typo cannot
smuggle a private address past the check. `_validate_url` runs before any
navigation, `_check_domain_rate` caps how fast one host can be hammered, and
`_check_anomaly` warns when a navigate follows a snapshot on a persistent
profile — a sequence that smells like scraping a page a moment after reading it.
Every decision, including denials, is written to a rotating audit log with
sensitive arguments redacted, so the fence is itself observable.

## Interfaces

`browser_navigate`, `browser_click`, `browser_fill`, `browser_snapshot`,
`browser_screenshot`, `browser_evaluate`, `browser_close`, and
`browser_list_profiles` are the MCP tools a persona sees. `_execute_tool` is the
shared choke point all of them call: it validates, rate-limits, anomalies-check,
forwards to a per-profile `PlaywrightStdioClient`, and maps the stdio JSON-RPC
result to an HTTP status. Named profiles persist under `PROFILES_DIR` via
`--user-data-dir`; `_isolated` is the default ephemeral session. The admin
routes `admin_create_profile`, `admin_login_session`, and
`admin_delete_profile` manage those persistent identities.

## Gotchas

`_idle_reaper` terminates any client idle for five minutes, so a long manual
login flow inside a named profile must finish quickly or the browser process
dies. `browser_fill` refuses fields whose element reference matches
`SENSITIVE_FIELD_PATTERNS` unless the caller passes `force_credential_fill`,
which is the persona policy switch — the refusal lives here, the privilege
lives upstream in the persona's allowed tools.
