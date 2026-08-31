"""Portal 5 Web Search MCP Server.

Tools:
- web_search: Brave API (or SearXNG) — top N results with title/url/snippet
- web_fetch: fetch a URL's text content (size-bounded, blocks private/local)
- news_search: like web_search, biased toward recent news

Port: 8922 (RESEARCH_MCP_PORT env override).
"""

import logging
import os
import re
import time
from urllib.parse import quote_plus, urlparse

import httpx
from mcp.server import MCPServer
from starlette.responses import JSONResponse

logger = logging.getLogger(__name__)
mcp = MCPServer("research")

SEARXNG_URL = os.environ.get("SEARXNG_URL", "http://localhost:8088")
BRAVE_API_KEY = os.environ.get("BRAVE_API_KEY", "")
WEB_FETCH_MAX_BYTES = int(os.environ.get("WEB_FETCH_MAX_BYTES", str(2 * 1024 * 1024)))
WEB_FETCH_TIMEOUT_S = float(os.environ.get("WEB_FETCH_TIMEOUT_S", "15"))

# Obscura-backed browser MCP (TASK_BROWSER_OBSCURA_MIGRATION_V1). Used as a
# fallback tier for web_fetch (A2) and web_search (A3): the browser passes bot
# challenges that a plain httpx GET / SERP-scrape cannot. Reachable in-compose.
BROWSER_MCP_URL = os.environ.get("BROWSER_MCP_URL", "http://portal-browser:8923")
WEB_FETCH_BROWSER_FALLBACK = os.environ.get("WEB_FETCH_BROWSER_FALLBACK", "true").lower() != "false"
WEB_SEARCH_BROWSER_TIER = os.environ.get("WEB_SEARCH_BROWSER_TIER", "true").lower() != "false"


async def _browser_tool(tool: str, arguments: dict, timeout_s: float = 45.0) -> dict | None:
    """Call one tool on the Obscura browser MCP. Returns its payload or None."""
    try:
        async with httpx.AsyncClient(timeout=timeout_s) as c:
            r = await c.post(f"{BROWSER_MCP_URL}/tools/{tool}", json={"arguments": arguments})
        if r.status_code != 200:
            logger.info("browser MCP %s -> HTTP %s", tool, r.status_code)
            return None
        data = r.json()
        if isinstance(data, dict) and (data.get("error") or data.get("isError")):
            return None
        return data
    except Exception as e:  # network / MCP down — degrade silently to the caller
        logger.info("browser MCP %s failed: %s", tool, e)
        return None


async def _browser_fetch_markdown(url: str) -> str | None:
    """A2: fetch a challenged URL as clean Markdown via Obscura (stateless)."""
    data = await _browser_tool("browser_get_markdown", {"url": url})
    if data:
        md = data.get("markdown") or ""
        return md.strip() or None
    return None


BLOCKED_DOMAINS = {
    "localhost",
    "127.0.0.1",
    "0.0.0.0",
    "169.254.169.254",
    "metadata.google.internal",
}
PRIVATE_PREFIXES = (
    "192.168.",
    "10.",
    "172.16.",
    "172.17.",
    "172.18.",
    "172.19.",
    "172.20.",
    "172.21.",
    "172.22.",
    "172.23.",
    "172.24.",
    "172.25.",
    "172.26.",
    "172.27.",
    "172.28.",
    "172.29.",
    "172.30.",
    "172.31.",
)


@mcp.custom_route("/health", methods=["GET"])
async def health(request):
    return JSONResponse(
        {
            "status": "ok",
            "service": "research-mcp",
            "backend": "brave" if BRAVE_API_KEY else "searxng",
        }
    )


TOOLS_MANIFEST = [
    {
        "name": "web_search",
        "description": "Search the web. Returns title, URL, snippet for top N results. Use for current events or factual lookups beyond training data.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "num_results": {"type": "integer", "default": 5, "minimum": 1, "maximum": 20},
                "time_range": {
                    "type": "string",
                    "enum": ["any", "day", "week", "month", "year"],
                    "default": "any",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "web_fetch",
        "description": "Fetch the text content of a URL (HTML stripped, max 2MB). Refuses localhost and private addresses.",
        "parameters": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "Full URL with http/https scheme"},
                "max_chars": {"type": "integer", "default": 50000},
            },
            "required": ["url"],
        },
    },
    {
        "name": "news_search",
        "description": "Search recent news articles. Biased toward news sources and recent results.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "num_results": {"type": "integer", "default": 5, "minimum": 1, "maximum": 20},
            },
            "required": ["query"],
        },
    },
]


@mcp.custom_route("/tools", methods=["GET"])
async def list_tools(request):
    return JSONResponse(TOOLS_MANIFEST)


# SearXNG's `general` category aggregate returns nothing when its default
# engines (brave / startpage / google-cse / ddg) are all captcha'd / rate-
# limited from this instance's IP — which was the steady state 2026-08-31.
# Pin the engines explicitly so a working one (Bing) is always queried; the
# others are tried too and contribute when they recover. Override via env.
_SEARXNG_ENGINES = os.environ.get("SEARXNG_ENGINES") or "bing,duckduckgo,google"


async def _searxng_search(query, num_results=5, time_range="any", category="general"):
    params = {
        "q": query,
        "format": "json",
        "categories": category,
        "engines": _SEARXNG_ENGINES,
    }
    if time_range != "any":
        params["time_range"] = time_range
    async with httpx.AsyncClient(timeout=10) as c:
        try:
            r = await c.get(f"{SEARXNG_URL}/search", params=params)
            if r.status_code != 200:
                return []
            return [
                {
                    "title": x.get("title", ""),
                    "url": x.get("url", ""),
                    "snippet": x.get("content", "")[:500],
                    "engine": x.get("engine", ""),
                    "published": x.get("publishedDate", "") or "",
                }
                for x in r.json().get("results", [])[:num_results]
            ]
        except Exception as e:
            logger.error("SearXNG failed: %s", e)
            return []


async def _brave_search(query, num_results=5, time_range="any", category="general"):
    """Brave Search API. Primary or fallback per WEB_SEARCH_PRIMARY; no-op
    without BRAVE_API_KEY.

    Maps time_range -> Brave 'freshness' (pd/pw/pm/py). category 'news' uses the
    /news endpoint; everything else uses /web. Returns the same result shape as
    _searxng_search (title/url/snippet/engine/published).
    """
    if not BRAVE_API_KEY:
        return []
    freshness = {"day": "pd", "week": "pw", "month": "pm", "year": "py"}.get(time_range)
    endpoint = "news" if category == "news" else "web"
    url = f"https://api.search.brave.com/res/v1/{endpoint}/search"
    params = {"q": query, "count": min(max(num_results, 1), 20)}
    if freshness:
        params["freshness"] = freshness
    headers = {"X-Subscription-Token": BRAVE_API_KEY, "Accept": "application/json"}
    async with httpx.AsyncClient(timeout=10) as c:
        try:
            r = await c.get(url, params=params, headers=headers)
            if r.status_code != 200:
                logger.warning("Brave HTTP %s", r.status_code)
                return []
            data = r.json()
            items = (data.get("results") or data.get("web", {}).get("results") or [])[:num_results]
            return [
                {
                    "title": x.get("title", ""),
                    "url": x.get("url", ""),
                    "snippet": (x.get("description", "") or "")[:500],
                    "engine": "brave",
                    "published": x.get("age", "") or x.get("page_age", "") or "",
                }
                for x in items
            ]
        except Exception as e:
            logger.error("Brave failed: %s", e)
            return []


# Which backend leads. SearXNG is free/private but scrape-based: its engines
# get bot-throttled and then return only site-root / Wikipedia / nav links
# rather than answer-bearing results (a browser hitting google.com/search
# hits the SAME degradation — worse, it CAPTCHAs faster — so "use a real
# browser" does not fix search quality; only a real index API does). Brave's
# API returns answer-bearing snippets and 2000 free queries/mo is ample for a
# single user. Default: brave when a key is configured, else searxng.
# Override with WEB_SEARCH_PRIMARY=searxng|brave. The other backend is the
# fallback either way.
WEB_SEARCH_PRIMARY = (
    os.environ.get("WEB_SEARCH_PRIMARY") or ("brave" if BRAVE_API_KEY else "searxng")
).lower()


def _results_are_weak(results: list) -> bool:
    """True when a non-empty result set is unlikely to help — every URL points
    at a site root / nav page, most carry no real snippet, or it is dominated
    by generic reference pages (Wikipedia). SearXNG's scraped results degrade
    to this shape when an engine throttles."""
    if not results:
        return True
    n = len(results)
    rooty = sum(1 for r in results if urlparse(r.get("url", "")).path.strip("/") == "")
    with_snippet = sum(1 for r in results if len((r.get("snippet") or "").strip()) >= 40)
    wiki = sum(1 for r in results if "wikipedia.org" in (r.get("url") or ""))
    return (
        rooty == n
        or with_snippet == 0
        or (n >= 3 and with_snippet < 2)
        or (n >= 3 and rooty + wiki >= n - 1)
    )


# In-process result cache — a single-user deployment re-runs the same lookups
# constantly (UAT reruns, common regs, a model refining a query with the same
# terms). TTL default 6h; every engine has some rate ceiling, so not re-hitting
# them for a repeat query is the cheapest win. Bounded LRU-ish (oldest evicted).
_SEARCH_CACHE_TTL_S = int(os.environ.get("WEB_SEARCH_CACHE_TTL_S", str(6 * 3600)))
_SEARCH_CACHE_MAX = int(os.environ.get("WEB_SEARCH_CACHE_MAX", "512"))
_search_cache: dict[tuple, tuple[float, list]] = {}


def _cache_get(key: tuple) -> list | None:
    hit = _search_cache.get(key)
    if hit is None:
        return None
    ts, results = hit
    if _SEARCH_CACHE_TTL_S <= 0 or time.time() - ts >= _SEARCH_CACHE_TTL_S:
        _search_cache.pop(key, None)
        return None
    return results


def _cache_put(key: tuple, results: list) -> None:
    if not results:
        return  # never cache an empty/failed lookup
    if len(_search_cache) >= _SEARCH_CACHE_MAX:
        oldest = min(_search_cache, key=lambda k: _search_cache[k][0])
        _search_cache.pop(oldest, None)
    _search_cache[key] = (time.time(), results)


async def _search_with_fallback(query, num_results=5, time_range="any", category="general"):
    """Primary backend (WEB_SEARCH_PRIMARY) then the other one, on an empty OR
    low-quality result set. Brave requires BRAVE_API_KEY. Cached per
    (query, num_results, time_range, category)."""
    key = (query.strip().lower(), num_results, time_range, category)
    cached = _cache_get(key)
    if cached is not None:
        logger.debug("web_search cache hit for %r", query)
        return cached

    brave_first = WEB_SEARCH_PRIMARY == "brave" and BRAVE_API_KEY
    order = ["brave", "searxng"] if brave_first else ["searxng", "brave"]
    results: list = []
    for backend in order:
        if backend == "brave" and not BRAVE_API_KEY:
            continue
        fn = _brave_search if backend == "brave" else _searxng_search
        candidate = await fn(query, num_results, time_range, category)
        if not _results_are_weak(candidate):
            _cache_put(key, candidate)
            return candidate
        if candidate and not results:
            results = candidate  # keep the best weak set as a last resort
        logger.info(
            "web_search: %s gave %d weak/empty results for %r", backend, len(candidate), query
        )

    # A3: final tier — both API backends returned weak/empty. Render a real SERP
    # through the Obscura browser (stealth) and scrape it. Only for general search.
    if WEB_SEARCH_BROWSER_TIER and category == "general" and _results_are_weak(results):
        browser_results = await _browser_search(query, num_results)
        if browser_results and not _results_are_weak(browser_results):
            _cache_put(key, browser_results)
            return browser_results

    _cache_put(key, results)
    return results


async def _browser_search(query: str, num_results: int) -> list:
    """A3: scrape a rendered SERP via the Obscura browser MCP. Returns the
    standard result shape, or [] on failure."""
    serp = f"https://duckduckgo.com/html/?q={quote_plus(query)}"
    nav = await _browser_tool("browser_navigate", {"url": serp}, timeout_s=45.0)
    if nav is None:
        return []
    # Extract result rows from the rendered DOM via browser_evaluate.
    limit = max(num_results, 1)
    expr = (
        f"Array.from(document.querySelectorAll('.result')).slice(0, {limit}).map(r => {{"
        "const a = r.querySelector('.result__a');"
        "const s = r.querySelector('.result__snippet');"
        "return {title: a ? a.textContent.trim() : '',"
        " url: a ? a.href : '',"
        " snippet: s ? s.textContent.trim() : ''};"
        "}).filter(x => x.url)"
    )
    ev = await _browser_tool("browser_evaluate", {"expression": expr}, timeout_s=20.0)
    rows = ev.get("result") if isinstance(ev, dict) else None
    if not isinstance(rows, list):
        return []
    out = []
    for row in rows[:num_results]:
        if isinstance(row, dict) and row.get("url"):
            out.append(
                {
                    "title": row.get("title", ""),
                    "url": row.get("url", ""),
                    "snippet": row.get("snippet", ""),
                    "engine": "browser",
                    "published": "",
                }
            )
    return out


@mcp.custom_route("/tools/web_search", methods=["POST"])
async def web_search_endpoint(request):
    body = await request.json()
    args = body.get("arguments", {})
    if not args.get("query"):
        return JSONResponse({"error": "query is required"}, status_code=400)
    num = min(max(args.get("num_results", 5), 1), 20)
    results = await _search_with_fallback(
        args["query"], num, args.get("time_range", "any"), "general"
    )
    return JSONResponse({"query": args["query"], "num_results": len(results), "results": results})


@mcp.custom_route("/tools/news_search", methods=["POST"])
async def news_search_endpoint(request):
    body = await request.json()
    args = body.get("arguments", {})
    if not args.get("query"):
        return JSONResponse({"error": "query is required"}, status_code=400)
    num = min(max(args.get("num_results", 5), 1), 20)
    results = await _search_with_fallback(args["query"], num, "week", "news")
    return JSONResponse({"query": args["query"], "num_results": len(results), "results": results})


_HTML_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")
_SCRIPT = re.compile(r"<(script|style)[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL)


_CHROME = re.compile(r"<(nav|header|footer|aside|form)\b[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL)


def _html_to_text(html):
    # Drop scripts/styles, then obvious page chrome, then remaining tags.
    stripped = _CHROME.sub(" ", _SCRIPT.sub("", html))
    return _WS.sub(" ", _HTML_TAG.sub(" ", stripped)).strip()


@mcp.custom_route("/tools/web_fetch", methods=["POST"])
async def web_fetch_endpoint(request):
    body = await request.json()
    args = body.get("arguments", {})
    url = args.get("url", "")
    if not url:
        return JSONResponse({"error": "url is required"}, status_code=400)
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return JSONResponse({"error": "only http/https supported"}, status_code=400)
    host = parsed.hostname or ""
    if host in BLOCKED_DOMAINS or host.startswith(PRIVATE_PREFIXES):
        return JSONResponse({"error": "private/local URLs blocked"}, status_code=403)
    max_chars = args.get("max_chars", 50000)

    async def _browser_fallback(reason: str):
        """A2: retry via the Obscura browser MCP (passes bot challenges)."""
        if not WEB_FETCH_BROWSER_FALLBACK:
            return None
        md = await _browser_fetch_markdown(url)
        if not md:
            return None
        truncated = len(md) > max_chars
        logger.info("web_fetch browser fallback used for %s (%s)", url, reason)
        return JSONResponse(
            {
                "url": url,
                "status_code": 200,
                "content_type": "text/markdown",
                "char_count": len(md),
                "truncated": truncated,
                "via": "browser",
                "text": md[:max_chars] + ("\n\n[...truncated]" if truncated else ""),
            }
        )

    try:
        async with httpx.AsyncClient(timeout=WEB_FETCH_TIMEOUT_S, follow_redirects=True) as c:
            r = await c.get(url, headers={"User-Agent": "Portal5-Research/1.0"})
            if r.status_code >= 400:
                fb = await _browser_fallback(f"HTTP {r.status_code}")
                return fb or JSONResponse({"error": f"HTTP {r.status_code}", "url": url})
            text = _html_to_text(r.content[:WEB_FETCH_MAX_BYTES].decode("utf-8", errors="replace"))
            if not text.strip():
                fb = await _browser_fallback("empty body")
                if fb:
                    return fb
            truncated = len(text) > max_chars
            return JSONResponse(
                {
                    "url": str(r.url),
                    "status_code": r.status_code,
                    "content_type": r.headers.get("content-type", ""),
                    "char_count": len(text),
                    "truncated": truncated,
                    "text": text[:max_chars] + ("\n\n[...truncated]" if truncated else ""),
                }
            )
    except Exception as e:
        fb = await _browser_fallback(f"exception: {type(e).__name__}")
        return fb or JSONResponse({"error": str(e)[:200], "url": url}, status_code=502)


def main():
    port = int(os.environ.get("RESEARCH_MCP_PORT", "8922"))
    mcp.run(transport="streamable-http", host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
