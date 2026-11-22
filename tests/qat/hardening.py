"""Stage 1: production hardening + graceful degradation + Obscura browser-mcp.

Checks the pipeline's hardening surface (/health/all, /metrics power+energy
gauges, auth rejection, bench-* concurrency=1), feeds it bad input (empty and
oversized prompts, invalid slug, malformed JSON — never a 500), and probes the
Obscura browser-mcp (:8923) live health, tool manifest, SSRF blocklist and
sensitive-field redaction.
"""

from __future__ import annotations

import json

import httpx

from .config import Settings
from .models import QATResult, Status, classify_defect

BROWSER_MCP_PORT = 8923
BROWSER_MANIFEST = "config/inference/tools_manifest_browser_mcp.json"
OK_STATUSES = frozenset({200, 400, 404, 413, 422})
SSRF_PROBES: tuple[str, ...] = (
    "http://localhost:8080/health",
    "http://127.0.0.1:9099/health",
    "http://169.254.169.254/latest/meta-data/",
    "https://aliyuncs.com/",
)
# Low-entropy on purpose: a redaction probe, not a credential (gitleaks-clean).
REDACTION_CANARY = "qat redaction canary 0123 0123 0123"


def hardening_run(
    settings: Settings, transport: httpx.BaseTransport | None = None
) -> list[QATResult]:
    with httpx.Client(transport=transport, timeout=30.0) as client:
        results = [
            _health_all(settings, client),
            _metrics_gauges(settings, client),
            _auth_rejection(settings, client),
            _bench_concurrency(),
            *_negative_probes(settings, client),
        ]
        results.extend(_browser_mcp(settings, client))
    return results


def _health_all(settings: Settings, client: httpx.Client) -> QATResult:
    try:
        r = client.get(f"{settings.pipeline_url}/health/all")
        body = r.json() if r.status_code == 200 else {}
    except Exception as exc:
        return QATResult("s1-health-all", Status.FAIL, f"unreachable: {exc}")
    ok = sum(1 for v in body.values() if isinstance(v, dict) and v.get("status") == "ok")
    detail = f"{ok}/{len(body)} services ok" if body else f"HTTP {r.status_code}"
    status = Status.PASS if r.status_code == 200 and ok >= len(body) else Status.WARN
    return QATResult("s1-health-all", status, detail, evidence={"services": sorted(body)})


def _metrics_gauges(settings: Settings, client: httpx.Client) -> QATResult:
    required = ("portal5_power_current_watts", "portal5_energy_consumed_watt_seconds_total")
    try:
        r = client.get(f"{settings.pipeline_url}/metrics")
        text = r.text if r.status_code == 200 else ""
    except Exception as exc:
        return QATResult("s1-metrics", Status.FAIL, f"/metrics unreachable: {exc}")
    missing = [
        name for name in required if f"# TYPE {name}" not in text and f"\n{name}" not in text
    ]
    if missing:
        return QATResult("s1-metrics", Status.FAIL, f"missing gauges: {', '.join(missing)}")
    return QATResult("s1-metrics", Status.PASS, f"power+energy gauges present ({len(required)})")


def _auth_rejection(settings: Settings, client: httpx.Client) -> QATResult:
    try:
        r = client.post(
            f"{settings.pipeline_url}/v1/chat/completions",
            json={"model": "auto", "messages": [{"role": "user", "content": "hi"}]},
        )
    except Exception as exc:
        return QATResult("s1-auth", Status.FAIL, f"probe failed: {exc}")
    if r.status_code in (200, 201):
        return QATResult("s1-auth", Status.FAIL, "unauthenticated chat completion accepted")
    if r.status_code in (401, 403):
        return QATResult("s1-auth", Status.PASS, f"rejected with HTTP {r.status_code}")
    return QATResult("s1-auth", Status.WARN, f"unexpected HTTP {r.status_code}")


def _bench_concurrency() -> QATResult:
    """Every bench workspace declares max_concurrent: 1 (the seat discipline)."""
    import yaml

    from .config import BENCH_YAML

    try:
        data = yaml.safe_load(BENCH_YAML.read_text(encoding="utf-8")) or {}
    except OSError:
        return QATResult("s1-bench-concurrency", Status.SKIP, f"{BENCH_YAML} unreadable")
    bench = data.get("workspaces") or {}
    if not bench:
        return QATResult("s1-bench-concurrency", Status.SKIP, "no bench workspaces configured")
    bad = sorted(
        wid for wid, cfg in bench.items() if int((cfg or {}).get("max_concurrent", 0) or 0) != 1
    )
    if bad:
        return QATResult(
            "s1-bench-concurrency",
            Status.FAIL,
            f"bench workspaces without cap 1: {', '.join(bad[:6])}",
        )
    return QATResult(
        "s1-bench-concurrency", Status.PASS, f"{len(bench)} bench workspaces capped at 1"
    )


def _negative_probes(settings: Settings, client: httpx.Client) -> list[QATResult]:
    headers = settings.auth_headers()
    probes: tuple[tuple[str, dict[str, object] | str], ...] = (
        ("empty-prompt", {"model": "auto", "messages": [{"role": "user", "content": ""}]}),
        (
            "oversized-prompt",
            {"model": "auto", "messages": [{"role": "user", "content": "x " * 300_000}]},
        ),
        (
            "invalid-slug",
            {"model": "auto-does-not-exist", "messages": [{"role": "user", "content": "hi"}]},
        ),
        ("malformed-json", '{"model": "auto", "messages": ['),
    )
    results: list[QATResult] = []
    for name, body in probes:
        try:
            if isinstance(body, str):
                r = client.post(
                    f"{settings.pipeline_url}/v1/chat/completions",
                    content=body,
                    headers={**headers, "Content-Type": "application/json"},
                )
            else:
                r = client.post(
                    f"{settings.pipeline_url}/v1/chat/completions", json=body, headers=headers
                )
        except Exception as exc:
            results.append(QATResult(f"s1-neg-{name}", Status.FAIL, f"probe raised: {exc}"))
            continue
        if r.status_code in OK_STATUSES:
            results.append(
                QATResult(f"s1-neg-{name}", Status.PASS, f"graceful HTTP {r.status_code}")
            )
        else:
            results.append(
                QATResult(
                    f"s1-neg-{name}",
                    Status.FAIL,
                    f"HTTP {r.status_code} — not graceful",
                    defect_class=classify_defect(infra_hop_failed=True)
                    if r.status_code >= 500
                    else classify_defect(),
                )
            )
    return results


def _browser_mcp(settings: Settings, client: httpx.Client) -> list[QATResult]:
    base = f"http://localhost:{BROWSER_MCP_PORT}"
    health = _browser_health(base, client)
    manifest = _browser_manifest(settings, base, client)
    ssrf = _browser_ssrf(base, client)
    redaction = _browser_redaction(base, client)
    return [health, manifest, ssrf, redaction]


def _browser_health(base: str, client: httpx.Client) -> QATResult:
    try:
        r = client.get(f"{base}/health")
        body = r.json() if r.status_code == 200 else {}
    except Exception as exc:
        return QATResult("s1-browser-health", Status.FAIL, f"Obscura browser-mcp down: {exc}")
    service = str(body.get("service", ""))
    status = Status.PASS if r.status_code == 200 and body.get("status") == "ok" else Status.FAIL
    return QATResult(
        "s1-browser-health", status, f"{service or 'browser-mcp'} HTTP {r.status_code}"
    )


def _browser_manifest(settings: Settings, base: str, client: httpx.Client) -> QATResult:
    manifest_path = settings.repo_root / BROWSER_MANIFEST
    try:
        designed = {str(t["name"]) for t in json.loads(manifest_path.read_text(encoding="utf-8"))}
    except (OSError, ValueError, KeyError):
        return QATResult(
            "s1-browser-tools", Status.SKIP, f"manifest unreadable: {BROWSER_MANIFEST}"
        )
    try:
        r = client.get(f"{base}/tools")
        observed = {str(t.get("name")) for t in r.json()} if r.status_code == 200 else set()
    except Exception as exc:
        return QATResult("s1-browser-tools", Status.FAIL, f"GET /tools failed: {exc}")
    missing = sorted(designed - observed)
    if missing:
        return QATResult(
            "s1-browser-tools", Status.FAIL, f"live tools missing vs manifest: {', '.join(missing)}"
        )
    return QATResult(
        "s1-browser-tools", Status.PASS, f"{len(observed)} tools live, manifest matches"
    )


def _browser_ssrf(base: str, client: httpx.Client) -> QATResult:
    denied: list[str] = []
    leaks: list[str] = []
    for url in SSRF_PROBES:
        try:
            r = client.post(f"{base}/tools/browser_get_markdown", json={"arguments": {"url": url}})
        except Exception as exc:
            return QATResult("s1-browser-ssrf", Status.FAIL, f"probe failed on {url}: {exc}")
        body_text = r.text
        if r.status_code in (403, 422) or "denied" in body_text.lower():
            denied.append(url)
        else:
            leaks.append(f"{url} -> HTTP {r.status_code}")
    if leaks:
        return QATResult("s1-browser-ssrf", Status.FAIL, f"SSRF blocklist gaps: {'; '.join(leaks)}")
    return QATResult(
        "s1-browser-ssrf", Status.PASS, f"{len(denied)}/{len(SSRF_PROBES)} probes blocked"
    )


def _browser_redaction(base: str, client: httpx.Client) -> QATResult:
    """A sensitive browser_fill attempt must never echo the secret back."""
    try:
        r = client.post(
            f"{base}/tools/browser_fill",
            json={
                "arguments": {
                    "element_ref": "#password",
                    "text": REDACTION_CANARY,
                    "profile": "_qat_missing_profile",
                }
            },
        )
    except Exception as exc:
        return QATResult("s1-browser-redaction", Status.FAIL, f"probe failed: {exc}")
    if REDACTION_CANARY in r.text:
        return QATResult(
            "s1-browser-redaction", Status.FAIL, "sensitive text echoed in tool response"
        )
    return QATResult(
        "s1-browser-redaction",
        Status.PASS,
        f"canary absent from response (HTTP {r.status_code})",
    )
