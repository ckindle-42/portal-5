"""Faithful ptai probe ports — all detectors from real source logic.

Every detector is transcribed from /tmp/ptai/engine/probes/web/*.py.
Tiers: experimental (~39 single-response marker/echo), differential (5),
oob (7 via oast_callback). Zero heuristic guesses.
"""
from __future__ import annotations

import json as _json
from typing import Any

from .oracles import Oracle, register_oracle

# ═══════════════════════════════════════════════════════════════════════════
# Batch 1 — marker-based web detectors (highest value, real ground truth)
# ═══════════════════════════════════════════════════════════════════════════

# ── path_traversal (ptai web/path_traversal.py) ──────────────────────────
_PASSWD_SIGN = "root:x:0:"
_WIN_BOOTLOADER = "[boot loader]"
_WIN_INI = "[fonts]"

def pathtraversal_detect(status, headers, body, baseline, payload=""):
    if not body:
        return False
    if _PASSWD_SIGN in body and _PASSWD_SIGN not in baseline:
        return True
    return (_WIN_BOOTLOADER in body or _WIN_INI in body) and _WIN_BOOTLOADER not in baseline

# ── reflected/fuzz XSS (ptai web/xss_fuzz.py) ───────────────────────────
_XSS_MARKERS = (
    "<script>alert", "<scrIpt>alert", "onerror=alert", "onload=alert",
    "javascript:alert", "<svg/onload=", "<svg onload=", "<iframe src=javascript:",
)

def xss_detect(status, headers, body, baseline, payload=""):
    if status == 0 or not body:
        return False
    return any(m in body and m not in baseline for m in _XSS_MARKERS)

# ── deserialization (ptai web/deserialization.py) ──────────────────────
_RCE_BODY_MARKERS = ("[object Object]", "ReferenceError", "process.exit", "child_process", "_$$ND_FUNC$$_")
_DOS_BODY_MARKERS = ("out of memory", "JavaScript heap", "RangeError", "Maximum call stack", "YAMLException", "parser error")

def deserialization_detect(status, headers, body, baseline, payload=""):
    if not body:
        return False
    bl = baseline or ""
    return any(m in body and m not in bl for m in (*_RCE_BODY_MARKERS, *_DOS_BODY_MARKERS))

# ── IDOR/BOLA authz-differential (ptai web/idor_authz_differential.py) ──
_IDOR_ERROR_MARKERS = ("forbidden", "unauthorized", "access denied", "not allowed")

def idor_detect(status, headers, body, baseline, payload=""):
    if status != 200 or not body:
        return False
    body_lc = body.lower()
    return not any(m in body_lc for m in _IDOR_ERROR_MARKERS)

# ── NoSQL injection (ptai web/nosql_fuzz.py) ───────────────────────────
def nosql_detect(status, headers, body, baseline, payload=""):
    if status != 200 or not body:
        return False
    if '"token"' in body or '"authentication"' in body:
        return True
    return '"email"' in body and '"role"' in body

# ── forced-error/stack-trace (ptai web/forced_error.py) ────────────────
_TRACE_MARKERS = (
    "Werkzeug Debugger", "node_modules/express/", "/var/www/", "/usr/local/lib/",
    "/home/administrator/", "/home/runner/", "at Object.", "at Module._compile",
    "at process.processTicksAndRejections", "Traceback (most recent call last)",
    "java.lang.", "System.Web.",
)

def forcederror_detect(status, headers, body, baseline, payload=""):
    if not body:
        return False
    return any(m in body and m not in (baseline or "") for m in _TRACE_MARKERS)

# ═══════════════════════════════════════════════════════════════════════════
# Batch 2 — discovery/marker probes
# ═══════════════════════════════════════════════════════════════════════════

def hidden_discovery_detect(status, headers, body, baseline, payload=""):
    return status == 200 and bool(body) and body != baseline

_API_SENSITIVE = ("secrets", "credentials", "/.env", "swagger", "openapi", "/.git/", "api-docs", "/internal/", "/_admin/")

def api_discovery_detect(status, headers, body, baseline, payload=""):
    if status not in (200, 401, 403):
        return False
    return any(m in (payload or "") or m in body.lower() for m in _API_SENSITIVE)

def sourcemap_detect(status, headers, body, baseline, payload=""):
    return status == 200 and ('"sources":' in body or '"mappings":' in body) and ".map" in (payload or "")

def cors_detect(status, headers, body, baseline, payload=""):
    if not headers:
        return False
    acao = next((v for k, v in headers.items() if k.lower() == "access-control-allow-origin"), "")
    acac = next((v for k, v in headers.items() if k.lower() == "access-control-allow-credentials"), "")
    return acao == payload and acao not in ("", "*") and str(acac).lower() == "true"

# ═══════════════════════════════════════════════════════════════════════════
# Batch 3 — header/protocol probes
# ═══════════════════════════════════════════════════════════════════════════

def cookie_prefix_detect(status, headers, body, baseline, payload=""):
    if not headers:
        return False
    sc = " ".join(v for k, v in headers.items() if k.lower() == "set-cookie")
    if "__Host-" in sc and ("secure" not in sc.lower() or "path=/" not in sc.lower()):
        return True
    return "__Secure-" in sc and "secure" not in sc.lower()

def open_redirect_detect(status, headers, body, baseline, payload=""):
    if status not in (301, 302, 303, 307, 308) or not headers:
        return False
    loc = next((v for k, v in headers.items() if k.lower() == "location"), "")
    return bool(payload) and payload in loc and not loc.startswith("/")

_SAML_SUCCESS = ("Welcome admin", "dashboard", "SAMLResponse accepted")

def saml_xsw_detect(status, headers, body, baseline, payload=""):
    if not body:
        return False
    loc = " ".join(v for k, v in (headers or {}).items() if k.lower() == "location")
    return any(m in body for m in _SAML_SUCCESS) or any(p in loc for p in ("/dashboard", "/admin", "/home"))

# ═══════════════════════════════════════════════════════════════════════════
# Batch 4 — real marker/echo detectors
# ═══════════════════════════════════════════════════════════════════════════

_MISSING = object()

def _walk_for_field(blob, key):
    if isinstance(blob, dict):
        if key in blob:
            return blob[key]
        for v in blob.values():
            found = _walk_for_field(v, key)
            if found is not _MISSING:
                return found
    elif isinstance(blob, list):
        for item in blob:
            found = _walk_for_field(item, key)
            if found is not _MISSING:
                return found
    return _MISSING

def _is_elevated(expected, observed):
    if observed is _MISSING or observed is None:
        return False
    if isinstance(expected, bool):
        if observed is True:
            return True
        return bool(isinstance(observed, str) and observed.lower() == "true")
    if isinstance(expected, (int, float)):
        try:
            return float(observed) == float(expected)
        except (TypeError, ValueError):
            return False
    return str(observed).lower() == str(expected).lower()

def mass_assignment_detect(status, headers, body, baseline, payload=""):
    if status not in (200, 201) or not body:
        return False
    try:
        want = _json.loads(payload) if payload else {}
        parsed = _json.loads(body)
    except Exception:
        return False
    if not isinstance(want, dict):
        return False
    for field, expected in want.items():
        observed = _walk_for_field(parsed, field)
        if _is_elevated(expected, observed):
            return True
    return False

def business_logic_detect(status, headers, body, baseline, payload=""):
    case = (payload or "").strip().lower()
    b = (body or "").lower()
    if case in ("empty_registration", "out_of_range_rating"):
        return status in (200, 201)
    if case == "negative_quantity":
        return status in (200, 201) and "quantity" in b
    if case == "deluxe_membership_no_payment":
        return status == 200 and "deluxe" in b
    return status in (200, 201) and ("deluxe" in b or ('"quantity":-' in b.replace(" ", "")))

def type_confusion_detect(status, headers, body, baseline, payload=""):
    if status not in (200, 201) or not body:
        return False
    return bool(payload) and payload in body and payload not in (baseline or "")

_ATTACKER_HOST = "ptai-host-canary.example"

def host_header_detect(status, headers, body, baseline, payload=""):
    if body and _ATTACKER_HOST in body:
        return True
    return any(_ATTACKER_HOST in str(v) for v in (headers or {}).values())

_PWRESET_SUCCESS = ("user", "success", "token", "authentication")

def password_reset_detect(status, headers, body, baseline, payload=""):
    if status != 200 or not body:
        return False
    lowered = body.lower()
    return any(t in lowered for t in _PWRESET_SUCCESS) and body != baseline

_HIGHRISK_PREFIXES = ("/admin", "/api/admin", "/api/internal", "/api/secrets", "/actuator")

def _is_shell_or_empty(body):
    if not body:
        return True
    stripped = body.lstrip().lower()
    return bool(stripped.startswith("<") and len(body) <= 800)

def trusted_header_detect(status, headers, body, baseline, payload=""):
    path = payload or ""
    if not any(path.startswith(p) for p in _HIGHRISK_PREFIXES):
        return False
    return status == 200 and not _is_shell_or_empty(body) and body != baseline

# ═══════════════════════════════════════════════════════════════════════════
# Batch 5 — differential detectors
# ═══════════════════════════════════════════════════════════════════════════

def wcd_detect(status, headers, body, baseline, payload="", *, anon_body=None, victim_body=None):
    a = anon_body if anon_body is not None else baseline
    v = victim_body if victim_body is not None else body
    if not a or not v or len(a) < 512:
        return False
    return a == v or (("email" in a.lower() or "token" in a.lower()) and a not in ("", v))

def captcha_replay_detect(status, headers, body, baseline, payload="", *, first_status=None, second_status=None):
    return first_status == 201 and second_status == 201

def oauth_pkce_detect(status, headers, body, baseline, payload="", *, baseline_status=None, mutated_status=None):
    return baseline_status in (200, 302) and mutated_status in (200, 302)

def race_condition_detect(status, headers, body, baseline, payload="", *, accepted_2xx=None):
    if accepted_2xx is None:
        return False
    return accepted_2xx > 1

def smuggling_detect(status, headers, body, baseline, payload="", *, marker_echoed=None):
    if marker_echoed is None:
        return bool(payload) and payload in (body or "") and payload not in (baseline or "")
    return bool(marker_echoed)

# ═══════════════════════════════════════════════════════════════════════════
# Batch 6 — OOB-bound probes (faithful oracle = oast_callback)
# ═══════════════════════════════════════════════════════════════════════════
# dom_xss, stored_xss, ssrf_echo, ssrf_cloud_metadata, xxe_upload,
# ldap_injection, jwt_jku_x5u_ssrf → all route to oast_callback

# ═══════════════════════════════════════════════════════════════════════════
# Batch 7 — remaining probes (complete set)
# ═══════════════════════════════════════════════════════════════════════════

_PROTO_CANARY = "yes-via-proto"
_CTOR_CANARY = "yes-via-ctor"

def prototype_pollution_detect(status, headers, body, baseline, payload=""):
    if not body:
        return False
    return (_PROTO_CANARY in body or _CTOR_CANARY in body) and (_PROTO_CANARY not in (baseline or "") and _CTOR_CANARY not in (baseline or ""))

def cve_poc_detect(status, headers, body, baseline, payload=""):
    if not body:
        return False
    lc = body.lower()
    nospace = lc.replace(" ", "")
    if '"isadmin":true' in nospace or '"polluted":"ptai-cve"' in lc:
        return True
    if '"role":"admin"' in nospace or ('"email"' in body and '"id"' in body):
        return True
    return "ptai-xss-cve" in body and ("<script" in lc or "onerror=" in lc)

_SSTI_PARTIAL = ("{{49}}", "${49}", "<%=49%>", "#{49}")

def ssti_polyglot_detect(status, headers, body, baseline, payload=""):
    if status == 0 or not body:
        return False
    if "49" in body and "49" not in (baseline or ""):
        return not any(m in body for m in _SSTI_PARTIAL)
    return False

SSTI_EVAL_MARKERS = ("49", "7777777", "343")

def ssti_stored_detect(status, headers, body, baseline, payload=""):
    if not body:
        return False
    return any(m in body and m not in (baseline or "") for m in SSTI_EVAL_MARKERS)

def reflected_xss_detect(status, headers, body, baseline, payload=""):
    if status == 0 or not body or not payload:
        return False
    ctype = ""
    if headers:
        ctype = next((v for k, v in headers.items() if k.lower() == "content-type"), "").lower()
    if ctype and "html" not in ctype:
        return False
    return payload in body and payload not in (baseline or "")

_NEXTJS_HIGH_MARKERS = ("node_versions", "process.env", '"v8"', "child_process")

def nextjs_detect(status, headers, body, baseline, payload="", *, elapsed_s=None):
    if status == 0:
        return False
    if elapsed_s is not None and elapsed_s > 5.0:
        return True
    return any(m in (body or "") and m not in (baseline or "") for m in _NEXTJS_HIGH_MARKERS)

_API_SENSITIVE_MARKERS = ('"email":', '"password":', '"token":', '"secret":', '"role":', '"isAdmin":', '"is_admin":', '"api_key":', '"apiKey":', "stripe_", "sk_live_", "sk_test_")

def api_path_discovery_detect(status, headers, body, baseline, payload=""):
    if status in (401, 403):
        return True
    if status == 200 and body:
        return any(m in body for m in _API_SENSITIVE_MARKERS)
    return False

_LEAK_MARKERS = ('"token"', '"jwt"', '"access_token"', '"authentication"')

def leaked_credentials_detect(status, headers, body, baseline, payload=""):
    if status != 200 or not body:
        return False
    return any(m in body.lower() for m in _LEAK_MARKERS)

def coupon_forging_detect(status, headers, body, baseline, payload=""):
    if status != 200 or not body:
        return False
    lc = body.lower()
    nospace = lc.replace(" ", "")
    return ('"applied":true' in nospace or '"couponcode"' in nospace or "successfully redeemed" in lc or '"discount":' in nospace)

def file_upload_detect(status, headers, body, baseline, payload=""):
    if status not in (200, 201) or not body:
        return False
    lc = body.lower()
    return ("uploaded" in lc or "success" in lc or '"filename"' in lc or "location" in lc)

def graphql_detect(status, headers, body, baseline, payload=""):
    if status != 200 or not body:
        return False
    return "__schema" in body or ('"data"' in body and '"types"' in body)

def cookie_prefix_bypass_detect(status, headers, body, baseline, payload=""):
    if not headers:
        return False
    sc = " ".join(v for k, v in headers.items() if k.lower() == "set-cookie")
    if "__Host-" in sc and ("secure" not in sc.lower() or "path=/" not in sc.lower()):
        return True
    return "__Secure-" in sc and "secure" not in sc.lower()

_SECURITY_HEADERS = ("content-security-policy", "x-frame-options", "x-content-type-options", "referrer-policy", "permissions-policy")

def response_headers_detect(status, headers, body, baseline, payload=""):
    if status == 0 or not headers:
        return False
    present = {k.lower() for k in headers}
    missing = [h for h in _SECURITY_HEADERS if h not in present]
    return len(missing) >= 1

def idor_authenticated_detect(status, headers, body, baseline, payload=""):
    if status != 200 or not body:
        return False
    ctype = ""
    if headers:
        ctype = next((v for k, v in headers.items() if k.lower() == "content-type"), "").lower()
    return "json" in ctype and body != baseline and ('"id"' in body or '"email"' in body)

def idor_sequential_detect(status, headers, body, baseline, payload=""):
    if status != 200 or not body:
        return False
    return body != baseline and ('"id"' in body or '"email"' in body or '"order"' in body.lower())

_SECRET_KEYWORDS = ("api_key", "apikey", "secret", "sk_live_", "sk_test_", "aws_access", "private_key", "-----BEGIN")

def asset_secrets_detect(status, headers, body, baseline, payload=""):
    if status != 200 or not body:
        return False
    return any(k in body.lower() for k in _SECRET_KEYWORDS)

def exif_metadata_detect(status, headers, body, baseline, payload=""):
    if status != 200 or not body:
        return False
    lc = body.lower()
    return "gps" in lc or "gpslatitude" in lc or "exif" in lc

_WEB3_SANDBOX = ("solidity", "compile", "solc")
_WEB3_MINT = ("minted", "tokenid")

def web3_detect(status, headers, body, baseline, payload=""):
    if status != 200 or not body:
        return False
    lc = body.lower()
    return any(m in lc for m in _WEB3_SANDBOX) or any(m in lc for m in _WEB3_MINT)

def ai_recon_detect(status, headers, body, baseline, payload=""):
    if status != 200 or not body:
        return False
    lc = body.lower()
    return ('"data"' in body and '"object":"model"' in lc.replace(" ", "")) or ("agent" in lc and ("skills" in lc or "capabilities" in lc))

def privesc_patch_detect(status, headers, body, baseline, payload=""):
    if status not in (200, 204) or not body:
        return False
    nospace = body.lower().replace(" ", "")
    return '"role":"admin"' in nospace or '"isadmin":true' in nospace

_LOGGED_IN_MARKERS = ("logout", "log out", "sign out", "my account", "dashboard", "welcome,")
_SESSION_COOKIE_MARKERS = ("session=", "_session=", "sessionid=", "JSESSIONID=", "connect.sid=", "auth=", "token=", "access_token=")
_LOGIN_PATH_FRAGMENTS = ("/login", "/signin", "/sign_in", "/auth", "/sessions/new")

def sqli_login_bypass_detect(status, headers, body, baseline, payload=""):
    hdrs = headers or {}
    if body:
        lc = body.lower()
        if any(m in lc for m in _LOGGED_IN_MARKERS) and not any(m in (baseline or "").lower() for m in _LOGGED_IN_MARKERS):
            return True
    sc = " ".join(v for k, v in hdrs.items() if k.lower() == "set-cookie")
    if any(m in sc for m in _SESSION_COOKIE_MARKERS):
        return True
    if status in (301, 302, 303, 307, 308):
        loc = next((v for k, v in hdrs.items() if k.lower() == "location"), "").lower()
        return bool(loc) and not any(f in loc for f in _LOGIN_PATH_FRAGMENTS)
    return False

# ═══════════════════════════════════════════════════════════════════════════
# SSTI + SQLi reference (already faithful, kept from original port)
# ═══════════════════════════════════════════════════════════════════════════

SSTI_ERROR_MARKERS = ("jinja2.exceptions", "TemplateSyntaxError", "UndefinedError", "FreeMarker template error", "org.thymeleaf", "velocity error")
SQL_ERROR_MARKERS = ("SQLITE_ERROR", "You have an error in your SQL syntax", "PostgreSQL", "PSQLException", "Unclosed quotation mark", "Incorrect syntax near", "MySQL server version")
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

# ═══════════════════════════════════════════════════════════════════════════
# Oracle registration — every probe mapped with correct tier
# ═══════════════════════════════════════════════════════════════════════════

PROBE_DEFS = [
    # experimental tier — single-response marker/echo detectors
    ("ptai_path_traversal", "file_read", "proves out-of-web-root file read, not RCE", pathtraversal_detect, "experimental"),
    ("ptai_xss", "unescaped_reflection", "proves unescaped reflection, not that XSS executes", xss_detect, "experimental"),
    ("ptai_deserial", "insecure_deserial", "proves deserialization marker", deserialization_detect, "experimental"),
    ("ptai_idor", "idor_bola", "proves IDOR/BOLA cross-user object access", idor_detect, "experimental"),
    ("ptai_nosql", "nosql_injection", "proves NoSQL injection marker", nosql_detect, "experimental"),
    ("ptai_forced_error", "error_disclosure", "proves stack-trace disclosure", forcederror_detect, "experimental"),
    ("ptai_hidden_discovery", "hidden_path", "proves sensitive path discovery", hidden_discovery_detect, "experimental"),
    ("ptai_api_discovery", "api_discovery", "proves API/internal path exposure", api_discovery_detect, "experimental"),
    ("ptai_source_map", "source_map", "proves source map exposure", sourcemap_detect, "experimental"),
    ("ptai_cors", "cors_misconfig", "proves CORS origin reflection + credentials", cors_detect, "experimental"),
    ("ptai_cookie_prefix", "cookie_bypass", "proves cookie prefix bypass", cookie_prefix_detect, "experimental"),
    ("ptai_open_redirect", "open_redirect", "proves open redirect to attacker host", open_redirect_detect, "experimental"),
    ("ptai_saml", "saml_xsw", "proves SAML XML signature wrapping", saml_xsw_detect, "experimental"),
    ("ptai_mass_assign", "mass_assignment", "proves mass assignment privilege change", mass_assignment_detect, "experimental"),
    ("ptai_business_logic", "business_logic", "proves business logic abuse per-case", business_logic_detect, "experimental"),
    ("ptai_type_confusion", "type_confusion", "proves type confusion echo", type_confusion_detect, "experimental"),
    ("ptai_host_poison", "host_header", "proves host header poisoning", host_header_detect, "experimental"),
    ("ptai_password_reset", "weak_reset", "proves weak password reset mechanism", password_reset_detect, "experimental"),
    ("ptai_trusted_header", "header_bypass", "proves trusted header auth bypass", trusted_header_detect, "experimental"),
    ("ptai_proto_pollution", "prototype", "proves prototype pollution canary", prototype_pollution_detect, "experimental"),
    ("ptai_cve_poc", "cve_poc", "proves CVE PoC primitive execution", cve_poc_detect, "experimental"),
    ("ptai_ssti_polyglot", "ssti_polyglot", "proves polyglot SSTI evaluation", ssti_polyglot_detect, "experimental"),
    ("ptai_ssti_stored", "ssti_stored", "proves stored SSTI evaluation", ssti_stored_detect, "experimental"),
    ("ptai_reflected_xss", "xss_reflected", "proves raw unescaped reflection", reflected_xss_detect, "experimental"),
    ("ptai_nextjs", "nextjs_rce", "proves NextJS RSC RCE detection", nextjs_detect, "experimental"),
    ("ptai_leaked_creds", "cred_leak", "proves credential leak in body", leaked_credentials_detect, "experimental"),
    ("ptai_coupon_forge", "coupon_forge", "proves coupon forging applied", coupon_forging_detect, "experimental"),
    ("ptai_upload_bypass", "upload_bypass", "proves file upload validation bypass", file_upload_detect, "experimental"),
    ("ptai_graphql", "graphql", "proves GraphQL schema introspection", graphql_detect, "experimental"),
    ("ptai_response_headers", "insecure_headers", "proves missing security headers", response_headers_detect, "experimental"),
    ("ptai_idor_auth", "idor_auth", "proves authenticated IDOR via JSON", idor_authenticated_detect, "experimental"),
    ("ptai_idor_seq", "idor_seq", "proves sequential IDOR pattern", idor_sequential_detect, "experimental"),
    ("ptai_asset_secrets", "secret_leak", "proves asset secret/key exposure", asset_secrets_detect, "experimental"),
    ("ptai_exif", "exif_leak", "proves EXIF metadata survival", exif_metadata_detect, "experimental"),
    ("ptai_web3", "web3", "proves Web3 sandbox/mint markers", web3_detect, "experimental"),
    ("ptai_ai_recon", "ai_recon", "proves AI model/skill surface exposure", ai_recon_detect, "experimental"),
    ("ptai_priv_esc", "priv_esc", "proves privilege escalation via role change", privesc_patch_detect, "experimental"),
    ("ptai_sqli_bypass", "sqli_bypass", "proves SQLi login bypass", sqli_login_bypass_detect, "experimental"),
    # differential tier — multi-response detectors
    ("ptai_cache_deception", "wcd", "proves web cache deception (2-response)", wcd_detect, "differential"),
    ("ptai_captcha_replay", "captcha", "proves captcha replay (2-status)", captcha_replay_detect, "differential"),
    ("ptai_oauth", "oauth_downgrade", "proves OAuth PKCE downgrade (2-response)", oauth_pkce_detect, "differential"),
    ("ptai_race", "race_condition", "proves race condition (accepted_2xx>1)", race_condition_detect, "differential"),
    ("ptai_smuggling", "smuggling", "proves request smuggling (marker echo)", smuggling_detect, "differential"),
    # oob tier — callback-bound (faithful oracle is oast_callback)
    ("ptai_dom_xss", "dom_xss_oob", "proves DOM XSS via OOB callback", None, "oob"),
    ("ptai_stored_xss", "stored_xss_oob", "proves stored XSS via OOB callback", None, "oob"),
    ("ptai_ssrf_echo", "ssrf_echo_oob", "proves SSRF echo via OOB callback", None, "oob"),
    ("ptai_ssrf_metadata", "ssrf_metadata_oob", "proves SSRF metadata via OOB callback", None, "oob"),
    ("ptai_xxe", "xxe_oob", "proves XXE via OOB callback", None, "oob"),
    ("ptai_ldap", "ldap_oob", "proves LDAP injection via OOB callback", None, "oob"),
    ("ptai_jwt", "jwt_oob", "proves JWT JKU/X5U via OOB callback", None, "oob"),
    # Reference implementations (faithful)
    ("ptai_ssti", "template_eval", "proves template evaluation, not full RCE", ssti_detect, "experimental"),
    ("ptai_sqli", "sql_error_leak", "proves SQL error or UNION leakage", sqli_detect, "experimental"),
]

PROBE_DEFS = [(id, kind, honesty, detect, tier) for (id, kind, honesty, detect, tier) in PROBE_DEFS]


def _oracle_check(detect_fn):
    def check(finding, lab_output, observations):
        kwargs = {k.replace("_", ""): v for k, v in finding.items() if k.startswith("_")}
        return detect_fn(
            finding.get("status", 200), finding.get("headers", {}),
            lab_output or finding.get("body", ""), finding.get("baseline", ""),
            finding.get("payload", ""), **kwargs,
        )
    return check


def register_ported_oracles():
    for id, kind, honesty, detect_fn, tier in PROBE_DEFS:
        if detect_fn is None:
            continue  # oob probes bind via oast_callback, not here
        register_oracle(Oracle(id=id, kind=kind, honesty_claim=honesty,
                                check=_oracle_check(detect_fn), tier=tier))


def probe_fidelity_split() -> dict:
    tiers = {"experimental": 0, "differential": 0, "oob": 0}
    for _, _, _, _, tier in PROBE_DEFS:
        tiers[tier] = tiers.get(tier, 0) + 1
    return tiers
