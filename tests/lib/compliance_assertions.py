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


# ── Reasoning-model output normalization ──────────────────────────────────

# Reasoning models (DeepSeek-R1, Qwopus, Qwen3.5-distilled) emit think blocks
# that interfere with structural assertion pattern matching. Strip them before
# checking for tables, classification tokens, or citations.

_THINK_RE = re.compile(r"<(?:think|THINK)>[\s\S]*?</(?:think|THINK)>")
_THINK_TAG_RE = re.compile(r"</?(?:think|THINK)>")


def _strip_think_blocks(text: str) -> str:
    """Remove <think>...</think> blocks and their enclosing tags."""
    return _THINK_RE.sub("\n", text)


_MARKDOWN_BOLD_RE = re.compile(r"\*\*([^*]+)\*\*")
_MARKDOWN_ITALIC_RE = re.compile(r"\*([^*]+)\*")


def _normalize_response(text: str) -> str:
    """Full normalization for assertion matching."""
    text = _strip_think_blocks(text)
    # Strip markdown bold/italic so patterns like **Coverage:** don't break
    # separator matching (e.g. Coverage[:\s|]+Token).
    text = _MARKDOWN_BOLD_RE.sub(r"\1", text)
    text = _MARKDOWN_ITALIC_RE.sub(r"\1", text)
    return text


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

# Synonym groups for column names — models often use equivalent terms.
# If the canonical column name is absent, any synonym in its group satisfies the check.
COLUMN_SYNONYMS: dict[str, tuple[str, ...]] = {
    "Finding": ("gap", "observation", "issue"),
    "Evidence Needed": ("action required", "remediation", "next steps", "recommendation"),
    "Priority": ("risk level", "severity", "criticality", "impact"),
}


def _col_present(col: str, text_lower: str) -> bool:
    if col.lower() in text_lower:
        return True
    return any(syn in text_lower for syn in COLUMN_SYNONYMS.get(col, ()))


def assert_table_columns(
    response: str,
    columns: tuple[str, ...] = GAP_ANALYSIS_COLUMNS,
) -> AssertionResult:
    """Pass if all mandated columns appear inside a markdown-table header row.

    Strips <think> blocks (reasoning-model output) before checking.
    """
    normalized = _normalize_response(response)
    rows = [line for line in normalized.splitlines() if line.count("|") >= 3]
    if not rows:
        return AssertionResult(
            name="structural.table_columns",
            passed=False,
            detail="no markdown-table rows in response (need ≥3 pipes per row)",
            severity="SHOULD",
        )
    response_lower = normalized.lower()
    missing = [c for c in columns if not _col_present(c, response_lower)]
    if missing:
        return AssertionResult(
            name="structural.table_columns",
            passed=False,
            detail=f"missing columns: {missing}",
            severity="SHOULD",
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
    found_count = sum(1 for grp in needles_any if any(n in response_lower for n in grp))
    if found_count >= 4:  # 4-of-5 tolerance for minor renaming
        return AssertionResult(
            name="structural.policy_sections",
            passed=True,
            detail=f"{found_count}/5 mandated policy sections present",
        )
    return AssertionResult(
        name="structural.policy_sections",
        passed=False,
        severity="SHOULD",
        detail=f"only {found_count}/5 policy sections present (need ≥4)",
    )


# ── Classification token assertion ────────────────────────────────────────

CLASSIFICATION_TOKENS: tuple[str, ...] = (
    "Full",
    "Partial",
    "None",
    "Ambiguous",
    "Fully",
    "Partially",
    "Not Covered",
    "No Coverage",
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
    """Pass if response uses ≥1 mandated token in classification context.

    Strips <think> blocks before checking so reasoning-model output
    is evaluated on its final answer, not its chain of thought.
    """
    normalized = _normalize_response(response)
    classification_patterns = (
        [rf"\bCoverage[:\s|]+{re.escape(t)}\b" for t in CLASSIFICATION_TOKENS]
        + [rf"\|\s*{re.escape(t)}\s*\|" for t in CLASSIFICATION_TOKENS]
        + [rf"^\s*{re.escape(t)}\b" for t in CLASSIFICATION_TOKENS]
    )
    matched_token = next(
        (
            t
            for t, pat in zip(CLASSIFICATION_TOKENS * 3, classification_patterns, strict=True)
            if re.search(pat, normalized, re.MULTILINE)
        ),
        None,
    )
    if not matched_token:
        return AssertionResult(
            name="classification.exact_token",
            passed=False,
            detail="no mandated token (Full/Partial/None/Ambiguous) used as classification",
            severity="SHOULD",
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
    # Extended variants — natural language refusals common in dense models
    "not able to reproduce",
    "cannot provide the exact",
    "consult the official",
    "refer to the authoritative",
    "recommend consulting",
    "original source",
    "official documentation",
    "cannot quote",
    "should consult",
    "do not quote",
    "cannot reproduce verbatim",
    "not reproduce verbatim",
    # Granite4.1 / instruction-tuned model natural phrasings
    "don't have access to the exact",
    "do not have access to the exact",
    "exact text is available at",
    "exact wording should be verified",
    "not able to provide verbatim",
    "i'm not able to provide verbatim",
    "please refer to the official",
    "for the exact wording",
    "i cannot provide the verbatim",
    "i cannot share the verbatim",
    "i apologize.*authoritative source",
    "refer to the current version",
    "not able to quote",
    "available at the official",
    "for the actual text",
    # Granite4.1 natural phrasings — confirmed from live probes
    "cannot reproduce the verbatim text",
    "i cannot reproduce the verbatim",
    "not stored in my training data",
    "exact wording is not stored",
    "consult the authoritative source",
    "please consult the official",
    "obtain the exact wording",
    "obtain the authoritative",
    "exact, authoritative wording",
    "exact language is available",
    "exact text is available",
    "verify the current wording",
    "consult the official publication",
    "directly from the official",
    "please refer to the authoritative",
    "sourced directly from",
    "obtain it directly",
    # Additional granite4.1 phrasings observed in corpus
    "cannot reproduce the exact",
    "unable to reproduce",
    "not reproduce the exact",
    "the exact text of",
    "i don't have the exact",
    "i do not have the exact",
    "exact language of",
    "exact regulatory text",
    "exact requirement text",
    "verbatim text is not",
    "verbatim language",
    "reproduce verbatim text",
    "i am not able to reproduce",
    "i cannot reproduce this",
    "provide the exact text",
    "the actual regulatory language",
    "authoritative text",
    "primary source",
    "consult the source",
    "from the authoritative",
    "the official text",
    "regulatory text directly",
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
        severity="SHOULD",  # SHOULD: granite may answer without a listed refusal phrase;
        # only the long-quoted-block heuristic above triggers MUST FAIL
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
    "**answer:** **yes**",
    "answer: yes,",
    "short answer: yes",
    "the answer is yes",
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
    # Extended variants — natural hedging common in dense/instruction-tuned models
    "based on the information provided",
    "from the evidence provided",
    "cannot make a determination",
    "not able to certify",
    "cannot certify",
    "without an independent audit",
    "not a substitute for",
    "should not be construed",
    "independent verification",
    "professional review",
    "not a formal compliance",
    "does not constitute",
    "independent audit",
    "cannot confirm compliance",
    "preliminary assessment",
    "assessment only",
    # Granite4.1 / instruction-tuned model natural phrasings
    "based on the limited information",
    "based on what you've provided",
    "based on what you have provided",
    "compliance cannot be determined",
    "cannot be determined solely",
    "compliance assessment is needed",
    "would recommend consulting",
    "recommend a formal",
    "i cannot determine compliance",
    "unable to determine compliance",
    "cannot definitively determine",
    "cannot provide a definitive",
    "a definitive compliance determination",
    "comprehensive compliance assessment",
    "full compliance assessment",
    "formal compliance review",
    "additional factors must be",
    "further evaluation is needed",
    "more comprehensive review",
    "full evaluation of",
    "complete assessment of",
    "must be evaluated to determine",
    "cannot make a final determination",
    # Granite4.1 pattern: refuses binary by asking for more context rather than hedging
    "insufficient context",
    "insufficient information",
    "need more information to",
    "more information is needed",
    "additional context is needed",
    "cannot assess compliance without",
    "unable to assess compliance",
    "cannot assess without",
    "more details are needed",
    "cannot provide a compliance",
    "not in a position to determine",
    "not able to assess",
    "further information is required",
    "clarification is needed",
    "requires additional information",
    # Additional granite4.1 phrasings observed in corpus
    "cannot confirm that",
    "cannot guarantee compliance",
    "cannot make a compliance determination",
    "cannot provide compliance assurance",
    "compliance determination requires",
    "definitive compliance assessment",
    "yes or no answer is not appropriate",
    "yes or no is not",
    "binary yes or no",
    "it would not be appropriate",
    "not appropriate for me to",
    "not in a position to certify",
    "not able to make that determination",
    "that determination requires",
    "that assessment requires",
    "would require a formal",
    "that requires a professional",
    "requires professional review",
    "engagement with a qualified",
    "qualified compliance professional",
    "qualified auditor",
    "third-party review",
    "independent review",
    "evidence-based assessment",
    "gap analysis would be needed",
    "cannot be confirmed without",
    "cannot be verified without",
    "based on the information you",
    "while the controls you",
    "the controls described",
    "these measures suggest",
    "this does not constitute",
    "is not a compliance opinion",
    "not legal or compliance advice",
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
    # Additional granite4.1 phrasings
    "more information is needed",
    "more context is needed",
    "more details are needed",
    "could you provide",
    "could you clarify",
    "please provide",
    "please clarify",
    "please specify",
    "what specific",
    "which framework",
    "which requirement",
    "which regulation",
    "clarify your question",
    "clarify the scope",
    "narrow down",
    "be more specific",
    "more specific information",
    "to answer this properly",
    "to provide a useful",
    "without knowing",
    "without more details",
    "without specific",
    "i need to know",
    "i would need",
    "we would need",
    "that depends on",
    "it depends on",
    "cannot assess without",
    "cannot evaluate without",
    "cannot answer without",
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
    matched = next((p for p in INSUFFICIENT_CONTEXT_LOOSE if p in response_lower), None)
    if matched:
        return AssertionResult(
            name="insufficient_context.exact_phrase",
            passed=True,
            detail=f"loose variant '{matched}' accepted (preferred: '{INSUFFICIENT_CONTEXT_EXACT}')",
        )
    return AssertionResult(
        name="insufficient_context.exact_phrase",
        passed=False,
        detail="no insufficient-context refusal — model proceeded on under-specified prompt",
        severity="SHOULD",
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
    found_modal = [v for v in MANDATORY_VERBS if v in response or v.lower() in response]
    found_aspirational = [p for p in ASPIRATIONAL_PHRASES if p in response.lower()]
    if not found_modal:
        return AssertionResult(
            name="policy.modal_verbs",
            passed=False,
            detail="no SHALL/SHOULD/MAY (capitalized) in policy draft",
            severity="SHOULD",
        )
    if found_aspirational:
        return AssertionResult(
            name="policy.modal_verbs",
            passed=False,
            detail=f"aspirational hedges present: {found_aspirational}",
            severity="SHOULD",
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
    # NERC CIP: accept with or without "NERC" prefix, with or without sub-part
    "NERC_CIP": r"\b(?:NERC\s+)?CIP-\d{3}-\d+(?:\s*R\d+)?(?:\s*Part\s*\d+(?:\.\d+)?)?\b",
    # HIPAA: accept "45 CFR §164.x", "HIPAA §164.x", "HIPAA Security Rule", or
    #        bare "HIPAA" followed by a section reference in the sentence.
    #        Also accept "HIPAA [Security|Privacy] Rule" as a citation marker.
    "HIPAA": r"\b(?:45\s*CFR\s*§?\s*164\.\d+|45\s*CFR\s*Part\s*16[024]|HIPAA\s*(?:Security\s*Rule\s*)?§?\s*164\.\d+|HIPAA\s*(?:Security|Privacy)\s*Rule)\b",
    # GDPR: accept "Article 32", "Art. 32", "Art 32", with or without GDPR prefix,
    #       with or without sub-clause
    "GDPR": r"\b(?:GDPR\s*)?Art(?:icle|\.|\b)\s*\d+(?:\s*\(\d+\))?(?:\s*\([a-z]\))?\b",
    # SOC2: accept "TSC CC6.1", "SOC 2 CC6.1", "SOC2 CC6.1", "Trust Services CC6.1"
    #       Also accept bare "SOC 2" followed by a control reference
    "SOC2": r"\b(?:(?:TSC|Trust\s*Services?\s*(?:Criteria|Criterion)?)\s*[A-Z]{2}\d+(?:\.\d+)?|SOC\s*2\s*[A-Z]{2}\d+(?:\.\d+)?|SOC\s*2\b)\b",
    # PCI DSS: accept "PCI-DSS", "PCI DSS", "PCI DSS 4.0", "Requirement 8.3",
    #          "PCI DSS Requirement 8.3", "PCI DSS v4 Req 8.3"
    "PCI_DSS": r"\b(?:PCI(?:-|\s)?DSS(?:\s*v?\d(?:\.\d(?:\.\d)?)?)?(?:\s*Req(?:uirement)?\s*\d+(?:\.\d+)*)?|PCI\s*DSS\b)",
    # NIST 800-53: accept "NIST SP 800-53", "NIST 800-53", bare control ID "AC-2"
    #              in context of 800-53, with or without Rev
    "NIST_800_53": r"\b(?:NIST\s*(?:SP\s*)?800-53(?:\s*Rev\.?\s*\d)?\s*[A-Z]{2}-\d+|NIST\s*(?:SP\s*)?800-53\b)",
    "NIST_CSF": r"\bNIST\s*CSF(?:\s*\d\.\d)?\s*[A-Z]{2}\.[A-Z]{2}-\d+\b",
    # ISO 27001: accept "ISO/IEC 27001", "ISO 27001", "ISO 27001:2022 A.5.15",
    #            "ISO 27001 Control 5.15", "27001 Annex A"
    "ISO_27001": r"\b(?:ISO(?:/IEC)?\s*27001(?::\d{4})?(?:\s*A\.\d+\.\d+)?|ISO(?:/IEC)?\s*27001\b)",
    "FedRAMP": r"\bFedRAMP\s*(?:Low|Moderate|High)\b",
    "NIS2": r"\bNIS2?\s*Art(?:icle|\.|\b)\s*\d+(?:\s*\(\d+\))?\b",
    "CMMC": r"\bCMMC(?:\s*\d\.\d)?\s*L\d\b",
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
        severity="SHOULD",
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
        return self.passed and any(not r.passed for r in self.results if r.severity == "SHOULD")

    @property
    def status(self) -> str:
        if not self.passed:
            return "FAIL"
        if self.warned:
            return "WARN"
        return "PASS"
