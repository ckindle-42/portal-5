"""Behavioral assertions for coding-persona responses.

Mirrors the shape of tests/lib/compliance_assertions.py — same
AssertionResult / ScenarioOutcome types, same MUST/SHOULD/INFO severities.
The matrix driver dispatches by spec name.

Design philosophy:
    Test that the response delivers a runnable, complete code artifact
    matching the persona's mandated output shape. Avoid coupling to
    specific algorithmic choices ("uses requestAnimationFrame") that
    constrain the model unnecessarily — instead test for absence of
    placeholders, presence of required structural elements (e.g. fenced
    code block, no premature truncation), and discipline around
    constraints the user stated.
"""

from __future__ import annotations

import re

from tests.lib.compliance_assertions import AssertionResult, ScenarioOutcome  # noqa: F401

# ── Code block presence ───────────────────────────────────────────────────

_FENCED_RE = re.compile(r"```[a-zA-Z+]*\n[\s\S]+?\n```", re.MULTILINE)
_TILDE_RE = re.compile(r"~~~[a-zA-Z+]*\n[\s\S]+?\n~~~", re.MULTILINE)
_INDENT_BLOCK_RE = re.compile(r"(?:^ {4}.+\n){3,}", re.MULTILINE)


def assert_code_block_present(response: str) -> AssertionResult:
    """Pass if response contains at least one code block (fenced or indented)."""
    fenced = _FENCED_RE.findall(response)
    tilded = _TILDE_RE.findall(response)
    indented = _INDENT_BLOCK_RE.findall(response)
    n = len(fenced) + len(tilded) + len(indented)
    if n == 0:
        return AssertionResult(
            name="structural.code_block_present",
            passed=False,
            detail="no code block (fenced, tilded, or indented) in response",
        )
    return AssertionResult(
        name="structural.code_block_present",
        passed=True,
        detail=f"{n} code block(s) found",
    )


# ── No truncation / placeholders ──────────────────────────────────────────

_TRUNCATION_PATTERNS: tuple[str, ...] = (
    r"\bTODO\s*[:\(]",
    r"\bFIXME\b",
    r"\bXXX\b",
    r"#\s*your code here",
    r"//\s*your code here",
    r"#\s*implementation goes here",
    r"//\s*implementation goes here",
    r"#\s*\.\.\.\s*\(implement\b",
    r"# Note: this is a simplified",
    r"# For brevity",
    r"// For brevity",
    r"\(rest of the code omitted\)",
    r"\bnot implemented\b",
    r"\braise NotImplementedError",
    r"throw new Error\([\"']not implemented",
    r"^\s*pass\s*$\s*#",
)


def assert_no_truncation_or_placeholders(response: str) -> AssertionResult:
    """Pass if response has no obvious 'I gave up here' markers."""
    found = []
    for pat in _TRUNCATION_PATTERNS:
        m = re.search(pat, response, re.IGNORECASE | re.MULTILINE)
        if m:
            found.append(m.group(0)[:60])
    if found:
        return AssertionResult(
            name="structural.no_truncation_or_placeholders",
            passed=False,
            detail=f"{len(found)} placeholder marker(s): {found[:3]}",
        )
    return AssertionResult(
        name="structural.no_truncation_or_placeholders",
        passed=True,
        detail="no placeholder/truncation markers",
    )


# ── Language constraint adherence ─────────────────────────────────────────

_LANGUAGE_SIGNATURES: dict[str, tuple[str, ...]] = {
    "python": (
        r"^\s*def\s+\w+\s*\(",
        r"^\s*class\s+\w+",
        r"^\s*import\s+\w+",
        r"^\s*from\s+\w+\s+import",
    ),
    "javascript": (
        r"\bfunction\s+\w+\s*\(",
        r"\bconst\s+\w+\s*=",
        r"\blet\s+\w+\s*=",
        r"=>\s*[{(]",
        r"\bdocument\.",
        r"\bwindow\.",
        # Playwright / JS-test idioms — short .spec.js files were failing
        # the >=2-signature threshold because they use these patterns
        # rather than the more general patterns above. See
        # TASK_V2_SCENARIO_FIXES_V1.md section A2.
        r"\bimport\s*\{\s*test\b",
        r"\bawait\s+page\.",
        r"\bexpect\s*\([^)]+\)\.to",
        r"\.spec\.js\b|\.test\.js\b",
    ),
    "html": (
        r"<!DOCTYPE\s+html",
        r"<html\b",
        r"<body\b",
        r"<script\b",
    ),
    "rust": (
        r"\bfn\s+\w+\s*\(",
        r"\bimpl\b",
        r"\blet\s+(?:mut\s+)?\w+",
        r"::<.*>",
        r"\buse\s+std::",
    ),
    "go": (
        r"\bpackage\s+\w+",
        r"\bfunc\s+\w+\s*\(",
        r"\binterface\s*{",
        r"\bgo\s+\w+\(",
    ),
    "sql": (
        r"\bSELECT\b",
        r"\bFROM\b",
        r"\bWHERE\b",
        r"\bJOIN\b",
        r"\bCREATE\s+TABLE\b",
    ),
    "bash": (
        r"^#!/(?:usr/)?bin/(?:bash|sh)",
        r"\b(?:if|for|while)\s+\[\[",
        r"\$\{\w+",
    ),
}


def assert_uses_language(response: str, language: str) -> AssertionResult:
    """Pass if response shows characteristic features of the named language."""
    sigs = _LANGUAGE_SIGNATURES.get(language.lower())
    if not sigs:
        return AssertionResult(
            name=f"language.{language}",
            passed=False,
            detail=f"no signatures registered for language '{language}'",
            severity="INFO",
        )
    hits = [pat for pat in sigs if re.search(pat, response, re.MULTILINE)]
    if len(hits) >= 2:
        return AssertionResult(
            name=f"language.{language}",
            passed=True,
            detail=f"{len(hits)} {language} signatures matched",
        )
    return AssertionResult(
        name=f"language.{language}",
        passed=False,
        detail=f"only {len(hits)} {language} signatures (need ≥2)",
    )


# ── Constraint discipline ─────────────────────────────────────────────────

_STDLIB_VIOLATION_HINTS: dict[str, tuple[str, ...]] = {
    "python_no_external": (
        r"^\s*import\s+(?!os|sys|re|json|math|random|time|datetime|"
        r"collections|itertools|functools|typing|pathlib|tempfile|"
        r"shutil|subprocess|argparse|logging|hashlib|base64|csv|"
        r"copy|warnings|enum|dataclasses|abc|ast|inspect|operator|"
        r"contextlib|io|struct|array|bisect|heapq|threading|asyncio|"
        r"unittest|tkinter|sqlite3|http|urllib|socket|ssl|email|"
        r"html|xml|uuid|secrets|string|textwrap|unicodedata)\w+",
    ),
    "js_no_framework": (
        r"\bimport\s+.*?\bfrom\s+['\"](?:react|vue|angular|svelte|"
        r"jquery|lodash|axios)['\"]",
        r"\brequire\s*\(\s*['\"](?:react|vue|angular|svelte|jquery|"
        r"lodash|axios)['\"]",
    ),
    "html_single_file": (
        r"<link[^>]+href\s*=\s*['\"][^'\"]+\.css",
        r"<script[^>]+src\s*=\s*['\"][^'\"]+\.js['\"]",
    ),
}


def assert_respects_constraint(response: str, constraint: str) -> AssertionResult:
    """Pass if response does not violate the named constraint."""
    patterns = _STDLIB_VIOLATION_HINTS.get(constraint)
    if not patterns:
        return AssertionResult(
            name=f"constraint.{constraint}",
            passed=False,
            detail=f"no patterns registered for constraint '{constraint}'",
            severity="INFO",
        )
    violations = []
    for pat in patterns:
        m = re.search(pat, response, re.MULTILINE)
        if m:
            violations.append(m.group(0)[:60])
    if violations:
        return AssertionResult(
            name=f"constraint.{constraint}",
            passed=False,
            detail=f"{len(violations)} violation(s): {violations[:2]}",
        )
    return AssertionResult(
        name=f"constraint.{constraint}",
        passed=True,
        detail=f"no violations of {constraint}",
    )


# ── Refuses to ask clarifying questions when prompt is self-evident ──────

_CLARIFICATION_STALL_PATTERNS: tuple[str, ...] = (
    r"\b(?:could you|can you|would you)\s+(?:clarify|specify|provide more)",
    r"\bbefore I (?:write|build|implement|create)",
    r"\b(?:I'd|I would) need (?:to know|more information)",
    r"\bcouple of questions\b",
    r"\bcould you tell me\b",
    r"\bwhat (?:framework|toolchain|language|library) (?:do|would) you (?:want|prefer)",
)


def assert_no_clarification_stall(response: str) -> AssertionResult:
    """Pass if response does not stall with clarifying questions before
    delivering code. Triggered by scenarios with self-evident prompts.
    """
    found = []
    for pat in _CLARIFICATION_STALL_PATTERNS:
        m = re.search(pat, response, re.IGNORECASE)
        if m:
            found.append(m.group(0)[:60])
    if found:
        return AssertionResult(
            name="behavioral.no_clarification_stall",
            passed=False,
            detail=f"clarifying-question stall: {found[:1]}",
            severity="SHOULD",
        )
    return AssertionResult(
        name="behavioral.no_clarification_stall",
        passed=True,
        detail="response did not stall with clarifying questions",
    )


# ── Stateful session handling (SQL REPL, Linux terminal) ──────────────────

_STATEFUL_RESULT_MARKERS: dict[str, tuple[str, ...]] = {
    "sql": (
        r"\b\d+\s+row(?:s)?\b",
        r"\(\s*\d+\s+row(?:s)?\s*(?:returned|affected)?\s*\)",
        r"\|\s*\w+\s*\|",  # ASCII table row
        r"-{3,}\+\-{3,}",  # ASCII table separator
        r"INSERT\s+0\s+\d+",  # postgres-style insert ack
    ),
    "bash": (
        r"^\$\s+",  # shell prompt echoed
        r"\b\d+\s+bytes\b",
        r"^/[\w/.-]+$",  # absolute path output
    ),
    "python": (
        r">>>\s+",  # REPL prompt
        r"\bTraceback\b",
        r"\bError\b.*:.*",
    ),
}


def assert_handles_stateful_session(response: str, language: str) -> AssertionResult:
    """Pass if response shows evidence of in-order, stateful multi-statement
    execution — not a single one-shot answer.

    For SQL: query results, row counts, INSERT acknowledgements.
    For bash: shell prompts, file listings, path output.
    For python REPL: prompts, tracebacks, error messages.

    A persona that answers a stateful question with prose only (no
    statement-level output markers) fails this assertion even if the prose
    is correct — the test verifies the model maintained the REPL/terminal
    contract.
    """
    markers = _STATEFUL_RESULT_MARKERS.get(language.lower())
    if not markers:
        return AssertionResult(
            name=f"behavioral.stateful_session.{language}",
            passed=False,
            detail=f"no markers registered for language '{language}'",
            severity="INFO",
        )
    hits = [pat for pat in markers if re.search(pat, response, re.MULTILINE)]
    if len(hits) >= 2:
        return AssertionResult(
            name=f"behavioral.stateful_session.{language}",
            passed=True,
            detail=f"{len(hits)} stateful-session markers matched",
        )
    return AssertionResult(
        name=f"behavioral.stateful_session.{language}",
        passed=False,
        detail=f"only {len(hits)} stateful-session markers (need ≥2)",
    )


# ── Required-elements check (named primitives by API/library/language) ────


def assert_contains_required_elements(response: str, elements: list[str]) -> AssertionResult:
    """Pass if every element in `elements` appears in the response.

    Elements are matched case-insensitively as plain substrings. Use for
    APIs/identifiers that have specific spellings (httpx.AsyncClient,
    pragma solidity, nonReentrant, exp claim, etc.). Not regex — keep
    scenarios YAML-readable.

    Severity is MUST: a missing required element is a hard fail.
    """
    if not elements:
        return AssertionResult(
            name="structural.required_elements",
            passed=False,
            detail="no elements provided",
            severity="INFO",
        )
    lower = response.lower()
    missing = [e for e in elements if e.lower() not in lower]
    if missing:
        return AssertionResult(
            name="structural.required_elements",
            passed=False,
            detail=f"missing: {missing}",
        )
    return AssertionResult(
        name="structural.required_elements",
        passed=True,
        detail=f"all {len(elements)} required elements present",
    )
