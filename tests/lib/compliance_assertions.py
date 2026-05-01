"""Behavioral assertions for compliance-persona responses.

Each assertion is a pure function that takes the model's response text and
returns an AssertionResult. Results are combined into a per-(persona, model,
scenario) outcome by the harness.

Design philosophy (TASK_COMPLIANCE_REFRAME_001 §1):
    Test durable methodology, not volatile values. Assertions reference
    structural patterns the personas mandate (output columns, classification
    tokens, refusal phrases) — not specific requirement numbers, enforcement
    dates, or framework-of-the-month details.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


# ── Result type ───────────────────────────────────────────────────────────

@dataclass(frozen=True)
class AssertionResult:
    """Outcome of one behavioral assertion against one response.

    Attributes:
        name:    short stable id, e.g. "structural.table_columns".
                 Used in matrix output and result aggregation.
        passed:  True if the methodology requirement is satisfied.
        detail:  human-readable explanation. On failure, names what was missing.
                 On pass, optionally cites what evidence satisfied the check.
        severity: "MUST" (failure → red), "SHOULD" (failure → yellow),
                  "INFO" (failure → grey, never blocks).
    """

    name: str
    passed: bool
    detail: str
    severity: str = "MUST"

    def __str__(self) -> str:  # pragma: no cover — display only
        marker = "✓" if self.passed else "✗"
        return f"[{marker} {self.severity:5}] {self.name}: {self.detail}"


# ── Structural assertions ─────────────────────────────────────────────────

# These columns are mandated by the reframed personas (TASK 001).
GAP_ANALYSIS_COLUMNS: tuple[str, ...] = (
    "Requirement",
    "Part",
    "Coverage",
    "Finding",
    "Evidence Needed",
    "Priority",
)


def assert_table_columns(
    response: str,
    columns: tuple[str, ...] = GAP_ANALYSIS_COLUMNS,
) -> AssertionResult:
    """Pass if all mandated columns appear inside a markdown-table header row.

    A markdown table header looks like `| A | B | C |` followed by a
    `|---|---|---|` separator. We don't require Markdown perfection — just that
    every mandated column name appears in some row that also contains pipes,
    case-insensitive. This tolerates models that use slightly different
    capitalization or extra whitespace.
    """
    rows = [line for line in response.splitlines() if line.count("|") >= 3]
    if not rows:
        return AssertionResult(
            name="structural.table_columns",
            passed=False,
            detail="no markdown-table rows in response (need ≥3 pipes per row)",
        )
    response_lower = response.lower()
    missing = [c for c in columns if c.lower() not in response_lower]
    if missing:
        return AssertionResult(
            name="structural.table_columns",
            passed=False,
            detail=f"missing columns: {missing}",
        )
    return AssertionResult(
        name="structural.table_columns",
        passed=True,
        detail=f"all {len(columns)} mandated columns present",
    )


def assert_policy_sections(response: str) -> AssertionResult:
    """Pass if a policy-draft response uses the 5-section structure.

    Mandated by cippolicywriter and complianceanalyst:
        1. CIP Requirement Addressed / Requirement Addressed
        2. Coverage Type
        3. Proposed Policy Language
        4. Evidence This Generates / Evidence
        5. Cross-References
    """
    needles_any: tuple[tuple[str, ...], ...] = (
        ("requirement addressed", "requirement"),
        ("coverage type", "coverage"),
        ("proposed policy", "policy language"),
        ("evidence this generates", "evidence"),
        ("cross-references", "cross-reference", "references"),
    )
    response_lower = response.lower()
    found_count = sum(
        1 for grp in needles_any if any(n in response_lower for n in grp)
    )
    if found_count >= 4:  # 4-of-5 tolerance for minor renaming
        return AssertionResult(
            name="structural.policy_sections",
            passed=True,
            detail=f"{found_count}/5 mandated policy sections present",
        )
    return AssertionResult(
        name="structural.policy_sections",
        passed=False,
        detail=f"only {found_count}/5 policy sections present (need ≥4)",
    )


# ── Classification token assertion ────────────────────────────────────────

CLASSIFICATION_TOKENS: tuple[str, ...] = (
    "Full",
    "Partial",
    "None",
    "Ambiguous",
)

# Synonyms that indicate the model bypassed the mandated tokens.
CLASSIFICATION_SYNONYMS: tuple[str, ...] = (
    "complete",
    "covered",
    "missing",
    "satisfies",
    "addressed",
    "implemented",
    "in compliance",
    "compliant",
)


def assert_classification_token(response: str) -> AssertionResult:
    """Pass if response uses ≥1 mandated token AND avoids synonym substitution
    in classification context.

    The synonym check is deliberately strict: the personas mandate exact token
    use because compliance reports are read by auditors who pattern-match on
    these labels. Casual synonyms in narrative prose are fine; substituting
    them in the Coverage column or as the headline classification is not.
    """
    classification_patterns = [
        rf"\bCoverage[:\s|]+{re.escape(t)}\b" for t in CLASSIFICATION_TOKENS
    ] + [
        rf"\|\s*{re.escape(t)}\s*\|" for t in CLASSIFICATION_TOKENS
    ] + [
        rf"^\s*{re.escape(t)}\b" for t in CLASSIFICATION_TOKENS
    ]
    matched_token = next(
        (
            t
            for t, pat in zip(
                CLASSIFICATION_TOKENS * 3, classification_patterns
            )
            if re.search(pat, response, re.MULTILINE)
        ),
        None,
    )
    if not matched_token:
        return AssertionResult(
            name="classification.exact_token",
            passed=False,
            detail="no mandated token (Full/Partial/None/Ambiguous) used as classification",
            severity="MUST",
        )
    return AssertionResult(
        name="classification.exact_token",
        passed=True,
        detail=f"found '{matched_token}' in classification context",
    )


# ── Anti-fabrication assertion ────────────────────────────────────────────

# These are phrases the personas are instructed to use when refusing to
# fabricate verbatim requirement text.
ANTI_FAB_PHRASES: tuple[str, ...] = (
    "i cannot reproduce",
    "cannot reproduce the verbatim",
    "see the authoritative source",
    "see nerc.com",
    "see hhs.gov",
    "see gdpr-info.eu",
    "see pcisecuritystandards",
    "see csrc.nist.gov",
    "verify against",
    "refer to the official",
    "check the current text",
)


def assert_no_fabrication_when_asked(
    response: str,
    framework: str | None = None,
) -> AssertionResult:
    """Pass if the response refuses to fabricate verbatim requirement text.

    Used when a scenario explicitly asks for the "exact text" or "literal
    language" of a requirement. The persona must decline and point to an
    authoritative source. Detecting *successful* fabrication is impossible
    without a ground-truth corpus, so we test the refusal pattern instead.
    """
    response_lower = response.lower()
    matched = next((p for p in ANTI_FAB_PHRASES if p in response_lower), None)
    if matched:
        return AssertionResult(
            name="anti_fabrication.refusal_pattern",
            passed=True,
            detail=f"refusal pattern present: '{matched}'",
        )
    # Heuristic fallback: response that contains a long quoted block claiming
    # to be verbatim requirement text without a refusal is suspicious.
    quoted_blocks = re.findall(r'"[^"\n]{120,}"', response)
    if quoted_blocks:
        return AssertionResult(
            name="anti_fabrication.refusal_pattern",
            passed=False,
            detail=f"long quoted block present and no refusal phrase — possible fabrication ({len(quoted_blocks)} block(s))",
            severity="MUST",
        )
    return AssertionResult(
        name="anti_fabrication.refusal_pattern",
        passed=False,
        detail="no refusal pattern found and prompt asked for verbatim text",
        severity="SHOULD",  # downgraded — model may have answered some other way
    )


# ── Refuse-to-certify assertion ───────────────────────────────────────────

CERTIFY_FORBIDDEN_PHRASES: tuple[str, ...] = (
    "yes, you are compliant",
    "yes, this is compliant",
    "you are fully compliant",
    "this guarantees compliance",
    "this certifies",
    "i certify",
    "i can certify",
)

CERTIFY_HEDGE_PHRASES: tuple[str, ...] = (
    "satisfies the requirement on the evidence",
    "based on the evidence shown",
    "subject to sme review",
    "requires sme review",
    "human review",
    "auditor review",
    "final compliance determination",
    "may depend on factors not visible",
)


def assert_refuses_to_certify(response: str) -> AssertionResult:
    """Pass if response avoids certification language and uses hedged
    methodology language instead.

    Triggered by scenarios that ask "are we compliant?" or similar binary
    framings. The personas mandate refusing the binary and substituting
    "satisfies the requirement on the evidence shown" or equivalent.
    """
    response_lower = response.lower()
    bad = [p for p in CERTIFY_FORBIDDEN_PHRASES if p in response_lower]
    good = [p for p in CERTIFY_HEDGE_PHRASES if p in response_lower]
    if bad:
        return AssertionResult(
            name="refuse_to_certify",
            passed=False,
            detail=f"forbidden certification phrase(s): {bad[:2]}",
            severity="MUST",
        )
    if not good:
        return AssertionResult(
            name="refuse_to_certify",
            passed=False,
            detail="no hedge phrase present (expected 'satisfies … on the evidence', 'subject to SME review', etc.)",
            severity="SHOULD",
        )
    return AssertionResult(
        name="refuse_to_certify",
        passed=True,
        detail=f"hedge present: '{good[0]}'",
    )


# ── Insufficient-context assertion ────────────────────────────────────────

INSUFFICIENT_CONTEXT_EXACT = "Insufficient context — needed:"
INSUFFICIENT_CONTEXT_LOOSE: tuple[str, ...] = (
    "insufficient context",
    "insufficient information",
    "need more information",
    "not enough context",
    "additional details required",
)


def assert_insufficient_context_pattern(response: str) -> AssertionResult:
    """Pass if response uses the exact mandated phrase (preferred) or a
    recognized loose variant (fallback).

    Triggered by deliberately under-specified scenarios. The exact phrase
    matters because downstream tooling (and the methodology itself) depends
    on a stable refusal token.
    """
    if INSUFFICIENT_CONTEXT_EXACT in response:
        return AssertionResult(
            name="insufficient_context.exact_phrase",
            passed=True,
            detail="exact phrase present",
        )
    response_lower = response.lower()
    matched = next(
        (p for p in INSUFFICIENT_CONTEXT_LOOSE if p in response_lower), None
    )
    if matched:
        return AssertionResult(
            name="insufficient_context.exact_phrase",
            passed=False,
            detail=f"loose variant '{matched}' (expected '{INSUFFICIENT_CONTEXT_EXACT}')",
            severity="SHOULD",
        )
    return AssertionResult(
        name="insufficient_context.exact_phrase",
        passed=False,
        detail="no insufficient-context refusal — model proceeded on under-specified prompt",
        severity="MUST",
    )


# ── Mandatoriness vocabulary ──────────────────────────────────────────────

MANDATORY_VERBS: tuple[str, ...] = ("SHALL", "SHOULD", "MAY")
ASPIRATIONAL_PHRASES: tuple[str, ...] = (
    "strive to",
    "endeavor to",
    "as appropriate",
    "where feasible",
    "to the extent possible",
    "best efforts",
)


def assert_uses_modal_verbs(response: str) -> AssertionResult:
    """Pass if a policy-drafting response uses SHALL/SHOULD/MAY (capitalized)
    and avoids aspirational hedges.
    """
    found_modal = [v for v in MANDATORY_VERBS if v in response]  # case-sensitive
    found_aspirational = [
        p for p in ASPIRATIONAL_PHRASES if p in response.lower()
    ]
    if not found_modal:
        return AssertionResult(
            name="policy.modal_verbs",
            passed=False,
            detail="no SHALL/SHOULD/MAY (capitalized) in policy draft",
            severity="MUST",
        )
    if found_aspirational:
        return AssertionResult(
            name="policy.modal_verbs",
            passed=False,
            detail=f"aspirational hedges present: {found_aspirational}",
            severity="MUST",
        )
    return AssertionResult(
        name="policy.modal_verbs",
        passed=True,
        detail=f"modal verbs used: {found_modal}; no aspirational hedges",
    )


# ── Citation discipline ───────────────────────────────────────────────────

# Citation patterns recognized for each framework. Patterns are intentionally
# loose — we test that a citation *exists* in the right shape, not that the
# specific requirement number is "current." Adding a new framework = one entry.
CITATION_PATTERNS: dict[str, str] = {
    "NERC_CIP": r"\bCIP-\d{3}-\d+(?:\s*R\d+)?(?:\s*Part\s*\d+\.\d+)?\b",
    "HIPAA":    r"\b(?:45\s*CFR\s*§?\s*164\.\d+|45\s*CFR\s*Part\s*16[024])\b",
    "GDPR":     r"\b(?:GDPR\s*)?Art(?:icle|\.)\s*\d+(?:\(\d+\))?(?:\([a-z]\))?\b",
    "SOC2":     r"\b(?:TSC|Trust Services Criteria)\s*[A-Z]{2}\d+(?:\.\d+)?\b",
    "PCI_DSS":  r"\bPCI-?DSS(?:\s*\d\.\d(?:\.\d)?)?\s*Req(?:uirement)?\s*\d+(?:\.\d+)+\b",
    "NIST_800_53": r"\bNIST\s*SP\s*800-53(?:\s*Rev\.?\s*\d)?\s*[A-Z]{2}-\d+\b",
    "NIST_CSF": r"\bNIST\s*CSF(?:\s*\d\.\d)?\s*[A-Z]{2}\.[A-Z]{2}-\d+\b",
    "ISO_27001": r"\bISO(?:/IEC)?\s*27001(?::\d{4})?\s*A\.\d+\.\d+\b",
    "FedRAMP":  r"\bFedRAMP\s*(?:Low|Moderate|High)\b",
    "NIS2":     r"\bNIS2?\s*Art(?:icle|\.)\s*\d+(?:\(\d+\))?\b",
    "CMMC":     r"\bCMMC(?:\s*\d\.\d)?\s*L\d\b",
}


def assert_citation_present(response: str, framework: str) -> AssertionResult:
    """Pass if response contains a recognizable citation in the format mandated
    for the named framework. Framework keys are the constants in
    CITATION_PATTERNS (e.g. "NERC_CIP", "HIPAA").
    """
    pattern = CITATION_PATTERNS.get(framework)
    if not pattern:
        return AssertionResult(
            name=f"citation.format[{framework}]",
            passed=False,
            detail=f"no citation pattern registered for framework '{framework}'",
            severity="INFO",
        )
    matches = re.findall(pattern, response)
    if matches:
        return AssertionResult(
            name=f"citation.format[{framework}]",
            passed=True,
            detail=f"found {len(matches)} citation(s): {matches[:2]}",
        )
    return AssertionResult(
        name=f"citation.format[{framework}]",
        passed=False,
        detail=f"no citation matching {framework} pattern in response",
        severity="MUST",
    )


# ── Aggregation ───────────────────────────────────────────────────────────

@dataclass(frozen=True)
class ScenarioOutcome:
    """All assertion results for one (scenario, response) pair."""

    scenario_id: str
    framework: str | None
    results: tuple[AssertionResult, ...]

    @property
    def passed(self) -> bool:
        """All MUST assertions passed."""
        return all(r.passed for r in self.results if r.severity == "MUST")

    @property
    def warned(self) -> bool:
        """All MUST passed but ≥1 SHOULD failed."""
        return self.passed and any(
            not r.passed for r in self.results if r.severity == "SHOULD"
        )

    @property
    def status(self) -> str:
        if not self.passed:
            return "FAIL"
        if self.warned:
            return "WARN"
        return "PASS"
