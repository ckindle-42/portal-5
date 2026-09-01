"""Portal 5 — Vulnerability & Threat Intelligence MCP.

Read-only, outbound-HTTPS-only. Fronts NVD, FIRST EPSS, CISA KEV, OSV.dev,
CISA ICS advisories, and a clearnet threat-intel subset. Composite risk score
with a CISA-KEV hard override + SSVC-style decision. Append-only audit log.

Port: 8934 (VULNINTEL_MCP_PORT or MCP_PORT env override).
All API keys optional; tools degrade gracefully when a key is absent.
"""

from __future__ import annotations

import ipaddress
import json
import logging
import os
import re
import time
from pathlib import Path

from mcp.server import MCPServer
from starlette.responses import JSONResponse

from portal.platform.data_loader import load_data

logger = logging.getLogger(__name__)

_port = int(os.environ.get("VULNINTEL_MCP_PORT") or os.environ.get("MCP_PORT", "8934"))
mcp = MCPServer(
    "vulnintel",
    instructions="Read-only live vulnerability & threat intelligence — NVD, FIRST EPSS, "
    "CISA KEV, OSV.dev, CISA ICS advisories, and a clearnet IOC subset. Composite risk "
    "score with a CISA-KEV hard override.",
)

# ── Config ───────────────────────────────────────────────────────────────────
_NVD = "https://services.nvd.nist.gov/rest/json/cves/2.0"
_EPSS = "https://api.first.org/data/v1/epss"
_KEV = "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json"
_ICSA = "https://www.cisa.gov/cybersecurity-advisories/all.json"
_OSV = "https://api.osv.dev/v1/query"
_THREATFOX = "https://threatfox-api.abuse.ch/api/v1/"
_GREYNOISE = "https://api.greynoise.io/v3/community/"
_AUDIT = Path(
    os.environ.get("VULNINTEL_AUDIT_LOG", str(Path.home() / ".portal-vulnintel" / "audit.jsonl"))
)
_TIMEOUT = float(os.environ.get("VULNINTEL_HTTP_TIMEOUT", "20"))
_CVE_RE = re.compile(r"^CVE-\d{4}-\d{4,}$", re.I)

# lazy singletons
_client = None
_kev_cache: dict = {"ts": 0.0, "ids": None}


def _http():
    global _client
    if _client is None:
        import httpx

        _client = httpx.Client(timeout=_TIMEOUT, headers={"User-Agent": "portal5-vulnintel/1.0"})
    return _client


def _audit(tool: str, params: dict, dt: float, status: str, cache_hit: bool = False) -> None:
    try:
        _AUDIT.parent.mkdir(parents=True, exist_ok=True)
        redacted = {
            k: v for k, v in params.items() if "key" not in k.lower() and "token" not in k.lower()
        }
        with _AUDIT.open("a") as fh:
            fh.write(
                json.dumps(
                    {
                        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                        "tool": tool,
                        "params": redacted,
                        "duration_ms": round(dt * 1000, 1),
                        "cache_hit": cache_hit,
                        "status": status,
                    }
                )
                + "\n"
            )
    except Exception:  # audit must never break a tool
        logger.exception("audit write failed")


def _norm_cve(cve_id: str) -> str:
    c = (cve_id or "").strip().upper()
    if not _CVE_RE.match(c):
        raise ValueError(f"not a CVE id: {cve_id!r}")
    return c


def _reject_private_ip(ip: str) -> None:
    addr = ipaddress.ip_address(ip)
    if addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_reserved:
        raise ValueError(f"private/reserved IP rejected before any lookup: {ip}")


def _kev_ids() -> set[str]:
    if _kev_cache["ids"] is not None and (time.time() - _kev_cache["ts"]) < 3600:
        return _kev_cache["ids"]
    data = _http().get(_KEV).json()
    ids = {v["cveID"].upper() for v in data.get("vulnerabilities", [])}
    _kev_cache.update(ts=time.time(), ids=ids)
    return ids


# ── Tools ────────────────────────────────────────────────────────────────────
@mcp.tool()
def lookup_cve(cve_id: str) -> dict:
    """Fetch a CVE record from NVD: CVSS vector/score, CWEs, references, timeline.

    Args:
        cve_id: e.g. "CVE-2024-3400".
    """
    t0 = time.time()
    try:
        cid = _norm_cve(cve_id)
        headers = {}
        if os.environ.get("NVD_API_KEY"):
            headers["apiKey"] = os.environ["NVD_API_KEY"]
        r = _http().get(_NVD, params={"cveId": cid}, headers=headers)
        r.raise_for_status()
        vulns = r.json().get("vulnerabilities", [])
        if not vulns:
            _audit("lookup_cve", {"cve_id": cid}, time.time() - t0, "not_found")
            return {"cve_id": cid, "found": False}
        cve = vulns[0]["cve"]
        metrics = cve.get("metrics", {})
        cvss = None
        for key in ("cvssMetricV31", "cvssMetricV30", "cvssMetricV2"):
            if metrics.get(key):
                cvss = metrics[key][0]["cvssData"]
                break
        out = {
            "cve_id": cid,
            "found": True,
            "description": next(
                (d["value"] for d in cve.get("descriptions", []) if d["lang"] == "en"), ""
            ),
            "cvss": cvss,
            "cwes": [
                w["value"]
                for p in cve.get("weaknesses", [])
                for w in p.get("description", [])
                if w["value"].startswith("CWE")
            ],
            "published": cve.get("published"),
            "last_modified": cve.get("lastModified"),
            "references": [r_["url"] for r_ in cve.get("references", [])][:20],
        }
        _audit("lookup_cve", {"cve_id": cid}, time.time() - t0, "ok")
        return out
    except Exception as e:  # noqa: BLE001
        _audit("lookup_cve", {"cve_id": cve_id}, time.time() - t0, f"error:{type(e).__name__}")
        return {"cve_id": cve_id, "error": str(e)}


@mcp.tool()
def get_epss(cve_id: str) -> dict:
    """FIRST EPSS exploitation probability (0-1) and percentile for a CVE."""
    t0 = time.time()
    try:
        cid = _norm_cve(cve_id)
        r = _http().get(_EPSS, params={"cve": cid})
        r.raise_for_status()
        rows = r.json().get("data", [])
        out = (
            {
                "cve_id": cid,
                "epss": float(rows[0]["epss"]),
                "percentile": float(rows[0]["percentile"]),
            }
            if rows
            else {"cve_id": cid, "epss": None, "note": "no EPSS score yet (may be <24h old)"}
        )
        _audit("get_epss", {"cve_id": cid}, time.time() - t0, "ok")
        return out
    except Exception as e:  # noqa: BLE001
        _audit("get_epss", {"cve_id": cve_id}, time.time() - t0, f"error:{type(e).__name__}")
        return {"cve_id": cve_id, "error": str(e)}


@mcp.tool()
def check_kev(cve_id: str) -> dict:
    """Is this CVE in CISA's Known Exploited Vulnerabilities catalog?"""
    t0 = time.time()
    try:
        cid = _norm_cve(cve_id)
        in_kev = cid in _kev_ids()
        _audit("check_kev", {"cve_id": cid}, time.time() - t0, "ok")
        return {"cve_id": cid, "in_kev": in_kev}
    except Exception as e:  # noqa: BLE001
        _audit("check_kev", {"cve_id": cve_id}, time.time() - t0, f"error:{type(e).__name__}")
        return {"cve_id": cve_id, "error": str(e)}


@mcp.tool()
def scan_dependencies(ecosystem: str, packages: dict) -> dict:
    """OSV.dev scan of {name: version} for known vulns. ecosystem e.g. 'PyPI','npm','Go'."""
    t0 = time.time()
    findings = {}
    try:
        for name, version in packages.items():
            body = {"package": {"ecosystem": ecosystem, "name": name}, "version": str(version)}
            r = _http().post(_OSV, json=body)
            r.raise_for_status()
            vulns = r.json().get("vulns", [])
            if vulns:
                findings[name] = [
                    {
                        "id": v["id"],
                        "summary": v.get("summary", "")[:200],
                        "aliases": v.get("aliases", []),
                    }
                    for v in vulns
                ]
        _audit(
            "scan_dependencies",
            {"ecosystem": ecosystem, "n": len(packages)},
            time.time() - t0,
            "ok",
        )
        return {"ecosystem": ecosystem, "vulnerable_count": len(findings), "findings": findings}
    except Exception as e:  # noqa: BLE001
        _audit(
            "scan_dependencies",
            {"ecosystem": ecosystem},
            time.time() - t0,
            f"error:{type(e).__name__}",
        )
        return {"error": str(e), "partial": findings}


@mcp.tool()
def ics_advisories(vendor: str = "", days: int = 30) -> dict:
    """Recent CISA ICS advisories (ICSA/ICSMA), optionally filtered by vendor keyword.

    The OT-specific source the generic IT-CVE tooling misses. Read-only feed pull.
    """
    t0 = time.time()
    try:
        r = _http().get(_ICSA)
        r.raise_for_status()
        items = r.json()
        rows = items if isinstance(items, list) else items.get("advisories", items.get("data", []))
        out = []
        for a in rows:
            if not isinstance(a, dict):
                continue
            atype = str(a.get("type") or a.get("advisoryType") or "")
            title = a.get("title") or a.get("name") or ""
            is_ics = "ics" in atype.lower() or str(a.get("id", "")).upper().startswith("ICS")
            # when the feed is the combined advisories list, keep only the ICS family
            if atype and not is_ics:
                continue
            if vendor and vendor.lower() not in title.lower():
                continue
            out.append(
                {
                    "id": a.get("id") or a.get("advisoryId"),
                    "title": title[:160],
                    "released": a.get("released") or a.get("date") or a.get("published"),
                    "url": a.get("url") or a.get("link"),
                }
            )
        _audit("ics_advisories", {"vendor": vendor, "days": days}, time.time() - t0, "ok")
        return {"vendor": vendor or "all", "count": len(out), "advisories": out[:50]}
    except Exception as e:  # noqa: BLE001
        _audit("ics_advisories", {"vendor": vendor}, time.time() - t0, f"error:{type(e).__name__}")
        return {"error": str(e)}


@mcp.tool()
def lookup_ioc(indicator: str) -> dict:
    """Clearnet IOC enrichment for an IP/domain/hash via abuse.ch ThreatFox (+ GreyNoise for IPs).

    Private/reserved IPs are rejected before any lookup.
    """
    t0 = time.time()
    result = {"indicator": indicator, "sources": {}}
    try:
        is_ip = False
        try:
            ipaddress.ip_address(indicator)
            is_ip = True
            _reject_private_ip(indicator)
        except ValueError as ve:
            if "rejected" in str(ve):
                raise
        tf = _http().post(_THREATFOX, json={"query": "search_ioc", "search_term": indicator})
        if tf.status_code == 200:
            result["sources"]["threatfox"] = tf.json().get("data", [])[:10]
        if is_ip:
            gn = _http().get(_GREYNOISE + indicator)
            if gn.status_code == 200:
                result["sources"]["greynoise"] = gn.json()
        _audit("lookup_ioc", {"indicator": indicator}, time.time() - t0, "ok")
        return result
    except Exception as e:  # noqa: BLE001
        _audit(
            "lookup_ioc", {"indicator": indicator}, time.time() - t0, f"error:{type(e).__name__}"
        )
        return {"indicator": indicator, "error": str(e)}


def _cvss_base(cvss: dict | None) -> float:
    if not cvss:
        return 0.0
    return float(cvss.get("baseScore", 0.0))


@mcp.tool()
def triage_cve(cve_id: str, depth: str = "standard") -> dict:
    """One-call triage: NVD + EPSS + KEV -> composite risk (KEV hard override) + SSVC-style decision.

    Sized for NERC CIP-007-6 R2 patch-evaluation evidence — every fan-out call is audited.

    Args:
        cve_id: the CVE to triage.
        depth: 'quick' (score only) | 'standard' (default) | 'deep' (adds SSVC decision).
    """
    t0 = time.time()
    try:
        cid = _norm_cve(cve_id)
        cve = lookup_cve(cid)
        epss = get_epss(cid)
        kev = check_kev(cid)
        cvss_base = _cvss_base(cve.get("cvss"))
        epss_p = epss.get("epss") or 0.0
        in_kev = bool(kev.get("in_kev"))
        # v1 weighted sum (CVSS .25, EPSS .45, KEV .30)
        score = (cvss_base / 10.0) * 25 + epss_p * 45 + (30 if in_kev else 0)
        if in_kev:
            score = max(score, 76)  # KEV hard override
        score = round(min(score, 100), 1)
        label = (
            "CRITICAL"
            if score >= 76
            else "HIGH"
            if score >= 51
            else "MEDIUM"
            if score >= 26
            else "LOW"
        )
        out = {
            "cve_id": cid,
            "risk_score": score,
            "label": label,
            "scoring_version": "1.0",
            "signals": {"cvss_base": cvss_base, "epss": epss_p, "in_kev": in_kev},
            "cvss": cve.get("cvss"),
            "description": cve.get("description", "")[:300],
        }
        if depth == "deep":
            # SSVC-style qualitative decision (CISA Deployer-ish, explainable)
            if in_kev:
                dec = "Act"
            elif epss_p > 0.3 or cvss_base >= 9.0:
                dec = "Attend"
            else:
                dec = "Track"
            out["ssvc_decision"] = dec
            out["cip_007_r2_note"] = (
                "KEV/active-exploitation drives an expedited patch/mitigation "
                "window; document applicability and the apply-or-mitigate decision."
            )
        _audit("triage_cve", {"cve_id": cid, "depth": depth}, time.time() - t0, "ok")
        return out
    except Exception as e:  # noqa: BLE001
        _audit("triage_cve", {"cve_id": cve_id}, time.time() - t0, f"error:{type(e).__name__}")
        return {"cve_id": cve_id, "error": str(e)}


# ── REST surface (portal-pipeline tool_registry) ─────────────────────────────
TOOLS_MANIFEST = load_data("config/inference", "tools_manifest_vulnintel_mcp")

_DISPATCH = {
    "lookup_cve": lookup_cve,
    "get_epss": get_epss,
    "check_kev": check_kev,
    "scan_dependencies": scan_dependencies,
    "ics_advisories": ics_advisories,
    "lookup_ioc": lookup_ioc,
    "triage_cve": triage_cve,
}


@mcp.custom_route("/health", methods=["GET"])
async def health_check(request):
    return JSONResponse({"status": "ok", "service": "vulnintel-mcp", "port": _port})


@mcp.custom_route("/ready", methods=["GET"])
async def ready(request):
    return JSONResponse({"port": _port, "audit_log": str(_AUDIT)})


@mcp.custom_route("/tools", methods=["GET"])
async def list_tools(request):
    return JSONResponse({"tools": TOOLS_MANIFEST})


@mcp.custom_route("/tools/{tool_name}", methods=["POST"])
async def invoke_tool(request):
    name = request.path_params.get("tool_name", "")
    fn = _DISPATCH.get(name)
    if fn is None:
        return JSONResponse({"error": f"unknown tool {name}"}, status_code=404)
    try:
        body = await request.json()
    except Exception:
        body = {}
    args = body.get("arguments", body) if isinstance(body, dict) else {}
    try:
        return JSONResponse(fn(**args))
    except TypeError as e:
        return JSONResponse({"error": f"bad params: {e}"}, status_code=400)


if __name__ == "__main__":
    mcp.run(transport="streamable-http", host="0.0.0.0", port=_port)
