"""Portal 5 Web Search MCP Server.

Tools:
- web_search: query SearXNG, return top N results with title/url/snippet
- web_fetch: fetch a URL's text content (size-bounded, blocks private/local)
- news_search: like web_search, biased toward recent news

Port: 8918 (RESEARCH_MCP_PORT env override).
"""

import logging
import os
import re
from urllib.parse import urlparse

import httpx
from starlette.responses import JSONResponse

from portal_mcp.mcp_server.fastmcp import FastMCP

logger = logging.getLogger(__name__)
mcp = FastMCP("research", host="0.0.0.0")

SEARXNG_URL = os.environ.get("SEARXNG_URL", "http://localhost:8088")
BRAVE_API_KEY = os.environ.get("BRAVE_API_KEY", "")
WEB_FETCH_MAX_BYTES = int(os.environ.get("WEB_FETCH_MAX_BYTES", str(2 * 1024 * 1024)))
WEB_FETCH_TIMEOUT_S = float(os.environ.get("WEB_FETCH_TIMEOUT_S", "15"))

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


async def _searxng_search(query, num_results=5, time_range="any", category="general"):
    params = {"q": query, "format": "json", "categories": category}
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
                }
                for x in r.json().get("results", [])[:num_results]
            ]
        except Exception as e:
            logger.error("SearXNG failed: %s", e)
            return []


@mcp.custom_route("/tools/web_search", methods=["POST"])
async def web_search_endpoint(request):
    body = await request.json()
    args = body.get("arguments", {})
    if not args.get("query"):
        return JSONResponse({"error": "query is required"}, status_code=400)
    num = min(max(args.get("num_results", 5), 1), 20)
    results = await _searxng_search(args["query"], num, args.get("time_range", "any"), "general")
    return JSONResponse({"query": args["query"], "num_results": len(results), "results": results})


@mcp.custom_route("/tools/news_search", methods=["POST"])
async def news_search_endpoint(request):
    body = await request.json()
    args = body.get("arguments", {})
    if not args.get("query"):
        return JSONResponse({"error": "query is required"}, status_code=400)
    num = min(max(args.get("num_results", 5), 1), 20)
    results = await _searxng_search(args["query"], num, "week", "news")
    return JSONResponse({"query": args["query"], "num_results": len(results), "results": results})


_HTML_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")
_SCRIPT = re.compile(r"<(script|style)[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL)


def _html_to_text(html):
    return _WS.sub(" ", _HTML_TAG.sub(" ", _SCRIPT.sub("", html))).strip()


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
    try:
        async with httpx.AsyncClient(timeout=WEB_FETCH_TIMEOUT_S, follow_redirects=True) as c:
            r = await c.get(url, headers={"User-Agent": "Portal5-Research/1.0"})
            if r.status_code >= 400:
                return JSONResponse({"error": f"HTTP {r.status_code}", "url": url})
            text = _html_to_text(r.content[:WEB_FETCH_MAX_BYTES].decode("utf-8", errors="replace"))
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
        return JSONResponse({"error": str(e)[:200], "url": url}, status_code=502)


def main():
    port = int(os.environ.get("RESEARCH_MCP_PORT", "8918"))
    mcp.settings.port = port
    mcp.run(transport="streamable-http")


if __name__ == "__main__":
    main()
