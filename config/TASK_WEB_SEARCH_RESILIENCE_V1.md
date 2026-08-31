# Task: Web search resilience — SearXNG scraping is rate-limited/blocked

## Problem (found 2026-08-31 during the compliance model probe)

Every `web_search` / `news_search` call was returning **empty results** across
`auto-compliance`, `auto-research`, and `auto-data`. SearXNG's `/search` with
the default `general` category aggregate returned 0 results; the standalone
`!bing` bang returned 10.

Root cause: SearXNG scrapes search engines' HTML result pages (it does not use
APIs). Google, DuckDuckGo, Brave, and Startpage all bot-detect and
CAPTCHA/throttle the instance's egress IP (`99.19.77.167` — the normal
residential egress, no VPN in the path). Days of UAT + research-lane traffic
tripped the thresholds; the bans persist for hours-to-days. Even Wikidata
returns HTTP 403. This is the inherent tradeoff of SearXNG's scraping approach,
not a compromise.

## Shipped (commits a17a58c3, + this)

- `_searxng_search` pins `engines=bing,duckduckgo,google` (env `SEARXNG_ENGINES`).
- **`BRAVE_API_KEY` set in `.env`** (operator-provided). `_search_with_fallback`
  reworked: `WEB_SEARCH_PRIMARY` env (`brave` when a key is set, else `searxng`);
  the other backend is the fallback, tried on an **empty OR low-quality** result
  set (`_results_are_weak` — all site-root URLs, no snippets, or Wikipedia+root
  dominated). SearXNG-Bing returns org homepages for "how many ISO 27001
  controls"; Brave returns "Explore the 93 controls…". Tests in
  `tests/unit/test_web_search_fallback.py`.

## Why not "just use a browser" for search

A headless browser navigating `google.com/search` hits the **same**
bot-detection as SearXNG's scraper — worse, Google serves a CAPTCHA to
automation faster than to a plain server request, and the results it does
return are the same degraded set. Scraping a search engine's *result page* is
the fragile part regardless of the client. Only a real search *index* (an API)
returns answer-bearing results reliably. Brave's is the privacy-respecting one
and 2,000 free queries/mo is ample for a single user. SearXNG stays as the
zero-key fallback.

## Where a browser DOES belong — `web_fetch`

`web_fetch` is `httpx.get` + a fake UA + regex HTML-strip. It 403s on any
Cloudflare / JS-gated / bot-checked page, and returns garbage on JS-rendered
content. **Reading a specific known page** is exactly what a real browser is
for (unlike search). Options, lightest first:

- **Evaluate a light agent-browser**: `obscura` (Rust, embedded V8, ~30MB vs
  Chromium's ~200MB, ~85ms vs ~500ms page load, agent-oriented per its README)
  — a genuine fit here and worth a spike. Also: Playwright with **Firefox** or a
  headless-shell build (lighter than full Chromium), or `htmlq` + a JS engine.
- The existing `portal-browser` MCP (`@playwright/mcp` + Chromium) is in the
  stack but its REST route is broken — `POST :8923/tools/{tool_name}` returns
  MCP JSON-RPC "Method not found" (the path-param `custom_route` loses to
  FastMCP's own `/tools` handling). Fix that route OR give the research MCP its
  own browser.
- Trigger the browser path from `web_fetch` on a 4xx/challenge response, not
  for every fetch (most pages are fine with httpx).

## The architectural fix — browser-backed fallback (preferred, stays local)

SearXNG scrapes engine HTML with a headless-scraper fingerprint, which is what
gets bot-detected. Portal 5 **already ships a real headless browser**:
`portal5-playwright` (portal-browser MCP, :8923, `browser_navigate` /
`browser_snapshot` / `browser_evaluate`, persistent profiles). The research MCP
(`web_search_mcp.py`) does not use it. obscura (the Rust Puppeteer alternative)
is not needed — it is not a search backend, and it duplicates Playwright.

Build a tiered `web_search_mcp.py`:

1. **`web_fetch` → browser fallback** (do first, ~1 hr, highest ROI). Current
   `web_fetch` is a plain `httpx.get` with a `Portal5-Research/1.0` UA + regex
   HTML strip — it 403s on any Cloudflare / JS-gated / bot-checked page. On a
   4xx/challenge response, retry via `browser_navigate` + `browser_snapshot`
   (accessibility tree → text). Agents can then read anything search surfaces.

2. **`web_search` → browser-driven search** (~2-3 hr). Add a fallback tier that
   navigates a real search engine page (bing / google) using a **persistent
   browser profile** — real Chrome with JS, cookies, and human-ish timing
   survives CAPTCHA far better than SearXNG's scraper. Read results from the
   accessibility snapshot; normalize to `_searxng_search`'s result shape.

3. **Fallback chain**: SearXNG (bing-pinned) → Brave API (if key) →
   browser-driven search → browser-fetch of authoritative domains.

4. **Compliance-specific**: the `auto-compliance` workspace should navigate
   directly to primary sources (nerc.com, hhs.gov, gdpr-info.eu, eur-lex,
   pcisecuritystandards.org) rather than fuzzy search — a curated
   authoritative-source tool, or a system-prompt directive to `browser_navigate`
   the standard-body site. Workspace-level, separate from the MCP change.

## Optional hardening (engineering)

- **Result caching** — cache `(query, category) -> results` for ~24h in the
  research MCP so repeat lookups (UAT reruns, common regs) don't re-hit engines.
- **Add non-blocking engines** to `config/searxng/settings.yml`: `mojeek`,
  `marginalia`, `wikipedia` (direct), `wikidata` with a custom User-Agent.
- **Slow SearXNG down** — `search.max_request_timeout` + a small inter-request
  delay so bursts look less scraper-like.
- Make `_search_with_fallback` also fall through on a *low-quality* result set
  (all results from one weak engine, or all homepage/nav links), not only on a
  truly empty one.

## Impact on the compliance decision

`auto-compliance` was promoted to Qwen3.8-27B partly on how it behaves when
search fails (it hedges / refuses to fabricate). With Brave API restored, the
retrieval path works and the model matters less — re-check the cascade-2
challenger bench with search actually working.
