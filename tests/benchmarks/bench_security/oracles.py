"""Named-oracle verification registry (Gap 3).

An oracle is a named, deterministic verifier that re-checks a claimed finding
against real evidence (lab output and/or observations) and returns a verdict.

Key rules (enforced in code):
- A finding with no named oracle, or an unknown oracle id, is rejected — never verified.
- VERIFIED requires N/N reproduction (all required re-checks must pass).
- The verdict copies the oracle's honesty_claim verbatim — no caller-written claims.

The registry is extensible: downstream tasks add oracles via register_oracle().
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class OracleVerdict:
    oracle: str  # named oracle id — REQUIRED, non-empty
    oracle_kind: str  # the specific property proved (e.g. "unescaped_reflection")
    verified: bool
    evidence: str  # the exact bytes/observation that proved it (truncated)
    honesty_claim: str  # what this oracle proves and NO more
    reproductions: int  # N successful re-checks
    required: int  # N required (default 2)


class Oracle:
    """A named, deterministic verifier of a specific finding class."""

    id: str
    kind: str  # oracle_kind
    honesty_claim: str  # fixed — "proves X, not that Y"
    tier: str  # "stable" counts; "experimental" excluded until bench-gated

    def __init__(
        self,
        id: str,
        kind: str,
        honesty_claim: str,
        tier: str = "stable",
    ):
        self.id = id
        self.kind = kind
        self.honesty_claim = honesty_claim
        self.tier = tier

    def check(self, finding: dict, lab_output: str, observations: dict) -> bool:
        """Return True if the oracle confirms this finding against the evidence."""
        raise NotImplementedError("subclasses must implement check()")


# ── Built-in oracle implementations ──────────────────────────────────────────


class _ReflectionOracle(Oracle):
    def __init__(self):
        super().__init__(
            id="reflection",
            kind="unescaped_reflection",
            honesty_claim="proves unescaped reflection, not that XSS executes",
        )

    def check(self, finding, lab_output, observations):
        payload = finding.get("payload", "")
        return bool(payload) and payload in lab_output


class _SQLiBooleanOracle(Oracle):
    def __init__(self):
        super().__init__(
            id="sqli_boolean",
            kind="boolean_differential",
            honesty_claim="proves boolean SQL differential, not data exfiltration",
        )

    def check(self, finding, lab_output, observations):
        diffs = finding.get("differentials", [])
        return len(diffs) >= 2 and any(d in lab_output for d in diffs)


class _SQLiErrorOracle(Oracle):
    def __init__(self):
        super().__init__(
            id="sqli_error",
            kind="sql_error_signature",
            honesty_claim="proves SQL error signature, not data exfiltration",
        )

    def check(self, finding, lab_output, observations):
        sigs = finding.get("error_signatures", ["sql syntax", "mysql_fetch", "unclosed quotation"])
        return any(s.lower() in lab_output.lower() for s in sigs)


class _OpenRedirectOracle(Oracle):
    def __init__(self):
        super().__init__(
            id="open_redirect",
            kind="unvalidated_redirect",
            honesty_claim="proves an open redirect, not arbitrary code execution",
        )

    def check(self, finding, lab_output, observations):
        redirect_host = finding.get("redirect_host", "")
        return bool(redirect_host) and redirect_host in lab_output


class _RCEShellOracle(Oracle):
    def __init__(self):
        super().__init__(
            id="rce_shell",
            kind="command_execution",
            honesty_claim="proves command execution (shell marker), not full compromise",
        )

    def check(self, finding, lab_output, observations):
        markers = finding.get("success_indicators", ["uid=", "shell obtained"])
        return any(m.lower() in lab_output.lower() for m in markers)


class _CVEConfirmedOracle(Oracle):
    def __init__(self):
        super().__init__(
            id="cve_confirmed",
            kind="cve_signature_match",
            honesty_claim="proves CVE version+PoC signature matches, not exploitability",
        )

    def check(self, finding, lab_output, observations):
        cve_id = finding.get("cve_id", "")
        return bool(cve_id) and cve_id in lab_output


class _LFIConfirmOracle(Oracle):
    def __init__(self):
        super().__init__(
            id="lfi_confirm",
            kind="file_inclusion",
            honesty_claim="proves file inclusion (planted-file contents), not code execution",
        )

    def check(self, finding, lab_output, observations):
        markers = finding.get(
            "success_indicators",
            ["root:x:0:0", "phpinfo", "passwd"],
        )
        return any(m.lower() in lab_output.lower() for m in markers)


class _OASTCallbackOracle(Oracle):
    def __init__(self):
        super().__init__(
            id="oast_callback",
            kind="out_of_band_interaction",
            honesty_claim="proves an out-of-band callback was observed, not data exfiltration",
            tier="experimental",  # stub — Gap 4 fills the collaborator
        )

    def check(self, finding, lab_output, observations):
        callback = finding.get("callback_id", "")
        return bool(callback) and callback in lab_output


# ── Registry ─────────────────────────────────────────────────────────────────

ORACLES: dict[str, Oracle] = {
    "reflection": _ReflectionOracle(),
    "sqli_boolean": _SQLiBooleanOracle(),
    "sqli_error": _SQLiErrorOracle(),
    "open_redirect": _OpenRedirectOracle(),
    "idor_bola": Oracle(
        id="idor_bola",
        kind="authorization_bypass",
        honesty_claim="proves IDOR/BOLA object access, not privilege escalation",
    ),
    "rce_shell": _RCEShellOracle(),
    "cve_confirmed": _CVEConfirmedOracle(),
    "lfi_confirm": _LFIConfirmOracle(),
    "oast_callback": _OASTCallbackOracle(),
}


def register_oracle(oracle: Oracle) -> None:
    """Register a new oracle into ORACLES. Downstream capability tasks call this."""
    ORACLES[oracle.id] = oracle


def verify_finding(
    finding: dict,
    lab_output: str,
    observations: dict,
    required: int = 2,
) -> OracleVerdict:
    """Run the named oracle for finding['oracle'] required times; VERIFIED only if N/N.

    Returns OracleVerdict with verified=False when:
    - 'oracle' key is missing from finding (rejection: "no oracle named")
    - oracle id is unknown in ORACLES (rejection: "unknown oracle")
    - fewer than required checks pass (N/N gating failed)
    """
    oracle_name = finding.get("oracle", "")
    if not oracle_name:
        return OracleVerdict(
            oracle="",
            oracle_kind="",
            verified=False,
            evidence="REJECTION: no oracle named in finding",
            honesty_claim="",
            reproductions=0,
            required=required,
        )

    oracle = ORACLES.get(oracle_name)
    if oracle is None:
        return OracleVerdict(
            oracle=oracle_name,
            oracle_kind="",
            verified=False,
            evidence=f"REJECTION: unknown oracle '{oracle_name}'",
            honesty_claim="",
            reproductions=0,
            required=required,
        )

    successes = 0
    for _ in range(required):
        if oracle.check(finding, lab_output, observations):
            successes += 1

    verified = successes >= required and oracle.tier == "stable"

    return OracleVerdict(
        oracle=oracle_name,
        oracle_kind=oracle.kind,
        verified=verified,
        evidence=lab_output[:500] if verified else f"reproductions: {successes}/{required}",
        honesty_claim=oracle.honesty_claim,
        reproductions=successes,
        required=required,
    )
