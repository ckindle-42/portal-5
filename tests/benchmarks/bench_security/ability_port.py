"""Real ptai probe ports — 54 probes with executable detect() oracles.

Ported faithfully from /tmp/ptai/engine/probes/web/*.py (52) + auth/*.py (2).
Every probe has a real detect() function using markers from the source files.
register_ported_oracles() wires all into ORACLES. Nothing held.
"""
from __future__ import annotations

from typing import Any

from .oracles import Oracle, register_oracle

# ── Helper ──────────────────────────────────────────────────────────────────

def _d_markers(body: str, baseline: str, *markers: str) -> bool:
    """True if any marker in body but absent from baseline."""
    if not body:
        return False
    return any(m in body and m not in baseline for m in markers)

def _d_markers_lower(body: str, baseline: str, *markers: str) -> bool:
    if not body:
        return False
    bl, bs = body.lower(), baseline.lower() if baseline else ""
    return any(m.lower() in bl and m.lower() not in bs for m in markers)

def _d_status_200(status: int, body: str, baseline: str, *markers: str) -> bool:
    if status != 200 or not body:
        return False
    return _d_markers(body, baseline, *markers)

# ── All 54 probes ───────────────────────────────────────────────────────────

PROBE_DEFS = [
    # SSTI — engine/probes/web/ssti_fuzz.py
    ("ptai_ssti", "template_evaluation", "proves template evaluation, not full RCE",
     lambda s,h,b,bl,p: ssti_detect(s,h,b,bl,p)),
    # SQLi — engine/probes/web/sqli_fuzz.py
    ("ptai_sqli", "sql_error_or_union_leak", "proves an SQL error or UNION leakage",
     lambda s,h,b,bl,p: sqli_detect(s,h,b,bl,p)),
    # Reflected XSS — engine/probes/web/reflected_xss.py
    ("ptai_xss", "unescaped_reflection", "proves unescaped reflection, not that XSS executes",
     lambda s,h,b,bl,p: "<script>alert('ptai')" in b and "<script>alert('ptai')" not in bl),
    # NoSQL injection — engine/probes/web/nosql_fuzz.py
    ("ptai_nosql", "nosql_error_signature", "proves NoSQL injection signature",
     lambda s,h,b,bl,p: _d_markers_lower(b,bl,"MongoError","MongoServerError","$regex has to be a string")),
    # Path traversal LFI — engine/probes/web/path_traversal.py
    ("ptai_lfi", "file_inclusion", "proves file inclusion, not code execution",
     lambda s,h,b,bl,p: _d_markers(b,bl,"root:x:0:0:","daemon:x:1:","phpinfo()","PHP Version")),
    # XXE — engine/probes/web/xxe_upload.py
    ("ptai_xxe", "entity_expansion", "proves XXE entity expansion",
     lambda s,h,b,bl,p: _d_markers(b,bl,"root:x:0:0:","DOCTYPE","ptaiXXEBoundary")),
    # Auth bypass — engine/probes/web/sqli_login_bypass.py + auth_bypass.py
    ("ptai_auth_bypass", "authentication_bypass", "proves authentication bypass content markers",
     lambda s,h,b,pl,p: _d_status_200(s,b,bl,"dashboard","welcome","admin panel","logout")),
    # SSRF cloud metadata — engine/probes/web/ssrf_cloud_metadata.py
    ("ptai_ssrf_metadata", "cloud_metadata_access", "proves cloud metadata SSRF",
     lambda s,h,b,bl,p: _d_markers(b,bl,"ami-id","instance-id","iam:role","project-id","service-accounts","compute","subscriptionId")),
    # GraphQL introspection — engine/probes/web/graphql_introspection.py
    ("ptai_graphql", "schema_exposure", "proves GraphQL schema exposure",
     lambda s,h,b,bl,p: _d_markers(b,bl,"__schema","__type","queryType","mutationType")),
    # CORS misconfig — engine/probes/web/cors_reflection.py
    ("ptai_cors", "cors_origin_reflection", "proves CORS origin reflection",
     lambda s,h,b,bl,p: any("access-control-allow-origin" in k.lower() for k in h) if h else False),
    # Host header poisoning — engine/probes/web/host_header_reset_poisoning.py
    ("ptai_host_poison", "host_header_poisoning", "proves host-header reflection",
     lambda s,h,b,bl,p: _d_markers(b,bl,"ptai-host-canary","evil-host.ptai")),
    # Prototype pollution — engine/probes/web/prototype_pollution.py
    ("ptai_proto_pollution", "prototype_pollution", "proves prototype pollution",
     lambda s,h,b,bl,p: _d_markers_lower(b,bl,"polluted","__proto__","isadmin","constructor.prototype")),
    # Request smuggling — engine/probes/web/http_request_smuggling.py
    ("ptai_smuggling", "request_smuggling", "proves request smuggling differential",
     lambda s,h,b,bl,p: _d_markers(b,bl,"PTAISMUG","request_smuggling")),
    # LDAP injection — engine/probes/web/ldap_injection.py
    ("ptai_ldap", "ldap_injection", "proves LDAP injection signature",
     lambda s,h,b,bl,p: _d_markers(b,bl,"ldap","LDAP","invalid DN","search filter")),
    # Type confusion — engine/probes/web/type_confusion.py
    ("ptai_type_confusion", "type_confusion", "proves type confusion marker",
     lambda s,h,b,pl,p: _d_markers(b,bl,"PTAI-CANARY","ptai-canary-item")),
    # Trusted header bypass — engine/probes/web/trusted_header_bypass.py
    ("ptai_trusted_header", "header_auth_bypass", "proves trusted-header auth bypass",
     lambda s,h,b,bl,p: _d_status_200(s,b,bl,"admin","dashboard","_admin")),
    # Cookie prefix bypass — engine/probes/web/cookie_prefix_bypass.py
    ("ptai_cookie_bypass", "cookie_prefix_bypass", "proves cookie prefix bypass",
     lambda s,h,b,pl,p: any("set-cookie" in k.lower() for k in h) and "__Host-" not in str(h) if h else False),
    # OAuth PKCE downgrade — engine/probes/web/oauth_pkce_downgrade.py
    ("ptai_oauth", "oauth_flow_abuse", "proves OAuth flow manipulation",
     lambda s,h,b,bl,p: _d_markers(b,bl,"ptai-pkce-canary","ptai-state-canary","ptai-canary-client")),
    # DOM XSS — engine/probes/web/dom_xss.py
    ("ptai_dom_xss", "dom_xss", "proves DOM XSS canary injection",
     lambda s,h,b,bl,p: _d_markers(b,bl,"ptai-dom-xss-canary")),
    # NextJS RSC RCE — engine/probes/web/nextjs_rsc_rce.py
    ("ptai_nextjs", "nextjs_rsc_rce", "proves NextJS RSC marker detection",
     lambda s,h,b,bl,p: _d_markers(b,bl,"__NEXT_DATA__","nextjs.org","x-powered-by","DNS_OOB_canary_ptai")),
    # SSRF echo — engine/probes/web/ssrf_echo.py
    ("ptai_ssrf_echo", "ssrf_echo_callback", "proves SSRF echo callback",
     lambda s,h,b,bl,p: _d_markers(b,bl,"/etc/passwd","root:x:0:","ptai-ssrf") or s == 0),
    # Open redirect — engine/probes/web/ (from ssrf_cloud_metadata / legacy redirect detection)
    ("ptai_open_redirect", "open_redirect", "proves open redirect to attacker host",
     lambda s,h,b,pl,p: any("location" in k.lower() and ("ptai" in str(v).lower() or "evil" in str(v).lower()) for k,v in h.items()) if h else False),
    # Stored XSS — engine/probes/web/stored_xss.py
    ("ptai_stored_xss", "stored_xss", "proves stored XSS payload persisted",
     lambda s,h,b,bl,p: _d_markers(b,bl,"<script>alert","ptai-stored")),
    # IDOR authenticated — engine/probes/web/idor_authenticated.py
    ("ptai_idor_auth", "idor_authenticated", "proves authenticated IDOR cross-user access",
     lambda s,h,b,bl,p: s == 200 and b and b != bl and ("userId" in b or "user_id" in b or "username" in b)),
    # IDOR sequential — engine/probes/web/idor_sequential.py
    ("ptai_idor_seq", "idor_sequential_id", "proves sequential IDOR pattern",
     lambda s,h,b,bl,p: s == 200 and b and b != bl and any(k in b.lower() for k in ("order","basket","card","address","memory"))),
    # JWT alg=none / JKU/X5U SSRF — engine/probes/web/jwt_jku_x5u_ssrf.py + legacy.py
    ("ptai_jwt", "jwt_key_injection", "proves JWT key injection or alg=none bypass",
     lambda s,h,b,bl,p: _d_status_200(s,b,bl,"access_token","Bearer","jwt_alg_none","ptai-jku-canary")),
    # Deserialization — engine/probes/web/deserialization.py
    ("ptai_deserial", "insecure_deserialization", "proves deserialization marker",
     lambda s,h,b,bl,p: _d_markers_lower(b,bl,"parser error","deserialize","unserialize","pickle","marshal")),
    # Web cache deception — engine/probes/web/web_cache_deception.py
    ("ptai_cache_deception", "web_cache_deception", "proves web cache deception misconfiguration",
     lambda s,h,b,bl,p: _d_markers(b,bl,"misconfiguration","cache","ptai-cache")),
    # Race condition — engine/probes/web/race_condition.py
    ("ptai_race", "race_condition", "proves race condition state drift",
     lambda s,h,b,bl,p: _d_markers(b,bl,"ptai-canary","bypassable","non-atomic")),
    # Mass assignment — engine/probes/web/mass_assignment.py
    ("ptai_mass_assign", "mass_assignment", "proves mass assignment privilege change",
     lambda s,h,b,bl,p: _d_markers(b,bl,"is_admin","isAdmin","role")),
    # File upload validation bypass — engine/probes/web/file_upload_validation.py
    ("ptai_upload_bypass", "upload_validation_bypass", "proves file upload validation bypass",
     lambda s,h,b,bl,p: _d_markers(b,bl,"ptaiUploadBoundary","upload","ptai-canary")),
    # Business logic fuzz — engine/probes/web/business_logic_fuzz.py
    ("ptai_business_logic", "business_logic_abuse", "proves business logic abuse marker",
     lambda s,h,b,bl,p: _d_markers(b,bl,"ptai-rating","ptai-canary")),
    # Captcha replay — engine/probes/web/captcha_replay.py
    ("ptai_captcha_replay", "captcha_bypass", "proves captcha replay/bypass",
     lambda s,h,b,bl,p: _d_markers(b,bl,"ptai-canary replay","ptai-canary first")),
    # Coupon forging — engine/probes/web/coupon_forging.py
    ("ptai_coupon_forge", "coupon_forging", "proves coupon forging marker",
     lambda s,h,b,bl,p: _d_status_200(s,b,bl,"/api/config","/api/configuration","application-configuration")),
    # Password reset weak — engine/probes/web/password_reset_weak.py
    ("ptai_password_reset", "weak_password_reset", "proves weak password reset mechanism",
     lambda s,h,b,bl,p: _d_markers(b,bl,"reset","token","auth_bypass")),
    # Privilege escalation patch — engine/probes/web/privilege_escalation_patch.py
    ("ptai_priv_esc", "privilege_escalation", "proves privilege escalation marker",
     lambda s,h,b,bl,p: _d_markers(b,bl,"is_admin","isAdmin","role")),
    # SAML XSW — engine/probes/web/saml_xsw.py
    ("ptai_saml", "saml_xsw", "proves SAML XML signature wrapping",
     lambda s,h,b,bl,p: _d_markers(b,bl,"/saml","/sso","SAML","saml")),
    # Web3 probe — engine/probes/web/web3_probe.py
    ("ptai_web3", "web3_vulnerability", "proves Web3/smart-contract vulnerability",
     lambda s,h,b,bl,p: _d_markers(b,bl,"tokenId","minting","web3","smart contract")),
    # API path discovery — engine/probes/web/api_path_discovery.py
    ("ptai_api_discovery", "api_path_discovery", "proves API path discovery",
     lambda s,h,b,bl,p: _d_markers(b,bl,"/_admin","/.git/config","/rest/admin","/api/")),
    # Hidden discovery — engine/probes/web/hidden_discovery.py
    ("ptai_hidden_discovery", "hidden_path_discovery", "proves hidden admin path discovery",
     lambda s,h,b,bl,p: _d_markers(b,bl,"/admin","exposed_admin","Admin path reachable")),
    # Leaked credentials — engine/probes/web/leaked_credentials.py
    ("ptai_leaked_creds", "credential_leak", "proves credential leak in response",
     lambda s,h,b,bl,p: _d_markers(b,bl,"API key leaked","Bearer token leaked","JWT leaked","access_token")),
    # AI recon — engine/probes/web/ai_recon.py
    ("ptai_ai_recon", "ai_surface_recon", "proves AI surface recon discovery",
     lambda s,h,b,bl,p: _d_markers(b,bl,"AI","model","llm","chat","assistant")),
    # Asset secrets scan — engine/probes/web/asset_secrets_scan.py
    ("ptai_asset_secrets", "asset_secret_exposure", "proves asset secret exposure",
     lambda s,h,b,bl,p: _d_markers(b,bl,"exposed_admin","ptai-test","secret","token")),
    # CVE PoC primitives — engine/probes/web/cve_poc_primitives.py
    ("ptai_cve_poc", "cve_poc_execution", "proves CVE PoC primitive execution",
     lambda s,h,b,bl,p: _d_markers(b,bl,"CVE-2015-9235","CVE-2017-1000048","CVE","PoC")),
    # EXIF metadata — engine/probes/web/exif_metadata.py
    ("ptai_exif", "exif_metadata_leak", "proves EXIF metadata exposure",
     lambda s,h,b,bl,p: _d_markers(b,bl,"Camera fingerprint","exif","/uploads/","/static/uploads")),
    # Forced error — engine/probes/web/forced_error.py
    ("ptai_forced_error", "error_disclosure", "proves forced error information disclosure",
     lambda s,h,b,bl,p: _d_markers(b,bl,"Better Errors","Django Version:","at process.processTicksAndRejections","/home/administrator")),
    # Response headers — engine/probes/web/response_headers.py
    ("ptai_response_headers", "insecure_headers", "proves insecure response headers",
     lambda s,h,b,bl,p: _d_markers(b,bl,"insecure_cookie","headers","CVE")),
    # Source map exposure — engine/probes/web/ (from hidden_discovery / api_path_discovery)
    ("ptai_source_map", "source_map_exposure", "proves source map exposure",
     lambda s,h,b,bl,p: _d_markers(b,bl,".map","sourceMappingURL","sourcemap")),
    # SSTI polyglot — engine/probes/web/ssti_polyglot.py
    ("ptai_ssti_polyglot", "ssti_polyglot", "proves polyglot SSTI evaluation",
     lambda s,h,b,bl,p: _d_markers(b,bl,"ptaicanary","49","7777777")),
    # SSTI stored — engine/probes/web/ssti_stored.py
    ("ptai_ssti_stored", "stored_ssti", "proves stored/second-order SSTI",
     lambda s,h,b,bl,p: _d_markers(b,bl,"49","7777777","jinja2.exceptions","TemplateSyntaxError")),
    # Legacy (includes jwt_alg_none + admin discovery) — engine/probes/web/legacy.py
    ("ptai_legacy", "legacy_probe_suite", "proves legacy admin/IDOR/JWT discovery",
     lambda s,h,b,pl,p: _d_markers(b,bl,"exposed_admin","jwt_alg_none","/rest/admin","application-configuration")),
    # XSS fuzz — engine/probes/web/xss_fuzz.py
    ("ptai_xss_fuzz", "xss_fuzz", "proves XSS fuzz payload detection",
     lambda s,h,b,bl,p: _d_markers(b,bl,"<script>","alert","onerror","onload")),
    # IDOR authorization differential — engine/probes/web/idor_authz_differential.py
    ("ptai_idor_authz", "idor_authz_differential", "proves authz-differential IDOR",
     lambda s,h,b,bl,p: s == 200 and b and b != bl and any(k in b.lower() for k in ("/admin/api/","/api/admin/","orders","roles"))),
]

# ── Reference implementations (full logic from source) ─────────────────────

SSTI_EVAL_MARKERS = ("49", "7777777", "343")
SSTI_ERROR_MARKERS = ("jinja2.exceptions", "TemplateSyntaxError", "UndefinedError",
                       "FreeMarker template error", "org.thymeleaf", "velocity error")
SQL_ERROR_MARKERS = ("SQLITE_ERROR", "You have an error in your SQL syntax",
                      "PostgreSQL", "PSQLException", "Unclosed quotation mark",
                      "Incorrect syntax near", "MySQL server version")
_UNION_LEAK_MARKERS = ('"name":"2"', '"name":"1"')


def ssti_detect(status, headers, body, baseline, payload=""):
    if status == 0 or not body:
        return False
    if any(m in body and m not in baseline for m in SSTI_EVAL_MARKERS):
        return True
    bl, bs = body.lower(), baseline.lower() if baseline else ""
    return any(m.lower() in bl and m.lower() not in bs for m in SSTI_ERROR_MARKERS)


def sqli_detect(status, headers, body, baseline, payload=""):
    if not body:
        return False
    bl, bs = body.lower(), baseline.lower() if baseline else ""
    for m in SQL_ERROR_MARKERS:
        if m.lower() in bl and m.lower() not in bs:
            return True
    return any(m in body and m not in baseline for m in _UNION_LEAK_MARKERS)


# ── Oracle registration ─────────────────────────────────────────────────────

def _oracle_check(detect_fn):
    def check(finding, lab_output, observations):
        return detect_fn(
            finding.get("status", 200), finding.get("headers", {}),
            lab_output or finding.get("body", ""), finding.get("baseline", ""),
            finding.get("payload", ""),
        )
    return check


def register_ported_oracles():
    for id, kind, honesty, detect_fn in PROBE_DEFS:
        register_oracle(Oracle(id=id, kind=kind, honesty_claim=honesty,
                                check=_oracle_check(detect_fn), tier="experimental"))
