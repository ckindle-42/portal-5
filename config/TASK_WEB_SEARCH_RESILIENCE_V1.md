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

## Shipped stopgap (commit a17a58c3)

`portal/modules/research/tools/web_search_mcp.py` `_searxng_search` now pins
`engines=bing,duckduckgo,google` (env override `SEARXNG_ENGINES`). Bing
scraping is currently the most tolerant; ddg/google contribute when they
recover. Bing will eventually throttle too — this is not the durable fix.

## Durable fix — operator action

**`BRAVE_API_KEY` is present in `.env` but empty.** The MCP already has a
`_brave_search` fallback wired (`if not BRAVE_API_KEY: return []`) that fires
when SearXNG returns nothing. Brave's Search API (free tier: 2,000 queries/
month, real API, no bot-blocking) is the right backstop for the queries that
matter.

1. Get a free key: https://brave.com/search/api/ (Data for AI → free plan).
2. `BRAVE_API_KEY=<key>` in `.env`.
3. `cd deploy/portal-5 && docker compose up -d --no-deps mcp-research`.
4. Verify: a compliance/research query cites retrieved sources again.

## Optional hardening (engineering)

- **Result caching** — cache `(query, category) -> results` for ~24h in the
  research MCP so repeat lookups (UAT reruns, common regs) don't re-hit engines.
- **Add non-blocking engines** to `config/searxng/settings.yml`: `mojeek`,
  `marginalia`, `wikipedia` (direct), `wikidata` with a custom User-Agent.
- **Slow SearXNG down** — `search.max_request_timeout` + a small inter-request
  delay so bursts look less scraper-like.
- Make `_searxng_search` → `_brave_search` fallback also trigger on a
  *low-quality* result set (all results from a single weak engine), not only on
  a truly empty one.

## Impact on the compliance decision

`auto-compliance` was promoted to Qwen3.8-27B partly on how it behaves when
search fails (it hedges / refuses to fabricate). With Brave API restored, the
retrieval path works and the model matters less — re-check the cascade-2
challenger bench with search actually working.
