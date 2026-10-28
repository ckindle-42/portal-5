"""Grounded deterministic checkers for detection-engineering bite outputs."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

Artifact = Mapping[str, Any]
CheckSpec = Mapping[str, Any]
ToolCall = Mapping[str, Any]


@dataclass(frozen=True)
class CheckResult:
    """One deterministic checker verdict with reviewable evidence."""

    passed: bool
    detail: str
    evidence: dict[str, Any]


Checker = Callable[[CheckSpec, Artifact, Sequence[ToolCall]], CheckResult]


def _fail(detail: str, **evidence: Any) -> CheckResult:
    return CheckResult(False, detail, evidence)


def _pass(detail: str, **evidence: Any) -> CheckResult:
    return CheckResult(True, detail, evidence)


def _mapping(value: Any) -> dict[str, Any] | None:
    if isinstance(value, dict):
        return value
    if not isinstance(value, str):
        return None
    try:
        decoded = json.loads(value)
    except json.JSONDecodeError:
        return None
    return decoded if isinstance(decoded, dict) else None


def _artifact_text(spec: CheckSpec, artifact: Artifact) -> tuple[str | None, CheckResult | None]:
    field = str(spec.get("artifact_field", ""))
    value = artifact.get(field)
    if not field or not isinstance(value, str) or not value.strip():
        return None, _fail(f"artifact field {field!r} must be a non-empty string")
    return value, None


def _matching_tool_result(
    calls: Sequence[ToolCall],
    name: str,
    expected_args: Mapping[str, Any],
    defaults: Mapping[str, Any] | None = None,
) -> tuple[dict[str, Any] | None, CheckResult | None]:
    seen: list[str] = []
    for call in calls:
        if call.get("name") != name:
            continue
        raw_args = call.get("args", call.get("arguments"))
        args = _mapping(raw_args)
        seen.append(
            json.dumps(args, sort_keys=True, default=str) if args is not None else "invalid"
        )
        # An argument the call left out takes the tool's declared default (convert_sigma's
        # target defaults to splunk); omitting it is not a different call.
        effective = {**(defaults or {}), **(args or {})}
        if args is None or any(effective.get(key) != value for key, value in expected_args.items()):
            continue
        if call.get("error"):
            return None, _fail(f"{name} returned a tool error", error=str(call["error"]))
        output = _mapping(call.get("output"))
        if output is None:
            return None, _fail(f"{name} returned no structured result")
        if output.get("error"):
            return None, _fail(f"{name} rejected the artifact", error=str(output["error"]))
        return output, None
    return None, _fail(
        f"no {name} call used the exact artifact under review",
        expected_args=dict(expected_args),
        seen_args=seen,
    )


def check_spl_syntax(spec: CheckSpec, artifact: Artifact, calls: Sequence[ToolCall]) -> CheckResult:
    """Require the exact SPL artifact to pass the detections MCP syntax validator."""
    spl, failure = _artifact_text(spec, artifact)
    if failure is not None or spl is None:
        return failure or _fail("SPL artifact missing")
    output, failure = _matching_tool_result(calls, "spl_validate_syntax", {"spl": spl})
    if failure is not None or output is None:
        return failure or _fail("SPL validator result missing")
    errors = output.get("errors")
    if output.get("ok") is not True or errors not in (None, []):
        return _fail("SPL syntax validation failed", validator=output)
    return _pass("exact SPL artifact passed syntax validation", validator=output)


def check_sigma_validate_convert(
    spec: CheckSpec, artifact: Artifact, calls: Sequence[ToolCall]
) -> CheckResult:
    """Require pySigma validation and Splunk conversion of the exact Sigma artifact."""
    sigma_yaml, failure = _artifact_text(spec, artifact)
    if failure is not None or sigma_yaml is None:
        return failure or _fail("Sigma artifact missing")
    expected_count = int(spec.get("rule_count", 1))
    converted, conversion_failure = _matching_tool_result(
        calls,
        "convert_sigma",
        {"sigma_yaml": sigma_yaml, "target": "splunk"},
        defaults={"target": "splunk"},
    )
    validated, failure = _matching_tool_result(calls, "validate_sigma", {"sigma_yaml": sigma_yaml})
    if validated is None and converted is not None:
        # convert_sigma parses the rule with the same SigmaCollection.from_yaml as
        # validate_sigma before converting (detection_mcp.py), so a successful conversion of
        # the exact artifact is its structural validation too (2026-10-28: the deep seat was
        # failed for skipping a redundant validate call the tool contract says convert covers).
        validated, failure = converted, None
    if failure is not None or validated is None:
        return failure or _fail("Sigma validation result missing")
    if validated.get("valid") is not True or validated.get("rule_count") != expected_count:
        return _fail("Sigma structural validation failed", validation=validated)
    if conversion_failure is not None or converted is None:
        return conversion_failure or _fail("Sigma conversion result missing")
    queries = converted.get("queries")
    if (
        converted.get("valid") is not True
        or converted.get("target") != "splunk"
        or converted.get("rule_count") != expected_count
        or not isinstance(queries, list)
        or not all(isinstance(query, str) and query.strip() for query in queries)
        or len(queries) != expected_count
    ):
        return _fail("Sigma-to-SPL conversion failed", conversion=converted)
    query_blob = "\n".join(queries).casefold()
    missing = [
        str(value)
        for value in spec.get("query_contains", [])
        if str(value).casefold() not in query_blob
    ]
    if missing:
        return _fail("converted SPL lacks required detection literals", missing=missing)
    return _pass(
        "exact Sigma artifact validated and converted to SPL",
        rule_count=expected_count,
        queries=queries,
    )


def check_yara_compile(
    spec: CheckSpec, artifact: Artifact, calls: Sequence[ToolCall]
) -> CheckResult:
    """Require the exact YARA artifact to compile through the detection MCP."""
    rule_text, failure = _artifact_text(spec, artifact)
    if failure is not None or rule_text is None:
        return failure or _fail("YARA artifact missing")
    output, failure = _matching_tool_result(calls, "compile_yara", {"rule_text": rule_text})
    if failure is not None or output is None:
        return failure or _fail("YARA compiler result missing")
    if output.get("valid") is not True:
        return _fail("YARA compilation failed", compiler=output)
    return _pass("exact YARA artifact compiled", compiler=output)


def _row_matches(expected: Mapping[str, Any], row: Mapping[str, Any]) -> bool:
    # SplunkBackend rows carry the search's columns under "fields"; flat rows are accepted too.
    nested = row.get("fields")
    values = {**row, **nested} if isinstance(nested, Mapping) else row
    return all(
        str(values.get(key, "")).casefold() == str(value).casefold()
        for key, value in expected.items()
    )


def check_lab_spl_results(
    spec: CheckSpec, artifact: Artifact, calls: Sequence[ToolCall]
) -> CheckResult:
    """Require a live-lab SPL call whose rows contain every predeclared known answer."""
    spl, failure = _artifact_text(spec, artifact)
    if failure is not None or spl is None:
        return failure or _fail("lab SPL artifact missing")
    if spec.get("requires_live_lab") is not True:
        return _fail("lab result checker must be declared requires_live_lab")
    expected_args: dict[str, Any] = {"spl": spl}
    for key in ("earliest", "latest", "max_results"):
        if key in artifact:
            expected_args[key] = artifact[key]
    output, failure = _matching_tool_result(calls, "query_splunk", expected_args)
    if failure is not None or output is None:
        return failure or _fail("live lab SPL result missing")
    rows = output.get("rows")
    if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
        return _fail("live lab SPL result has no structured rows", result=output)
    if output.get("requested_spl") != spl or output.get("row_count") != len(rows):
        return _fail(
            "live lab SPL result does not self-consistently identify the query", result=output
        )
    minimum = int(spec.get("min_rows", 1))
    if len(rows) < minimum:
        return _fail("live lab SPL returned too few rows", row_count=len(rows), min_rows=minimum)
    expected_rows = spec.get("expected_rows")
    if not isinstance(expected_rows, list) or not expected_rows:
        return _fail("lab result checker has no predeclared known-answer rows")
    missing = [
        expected
        for expected in expected_rows
        if isinstance(expected, dict) and not any(_row_matches(expected, row) for row in rows)
    ]
    if missing or not all(isinstance(expected, dict) for expected in expected_rows):
        return _fail("live lab SPL missed known-answer rows", missing=missing, rows=rows)
    return _pass("live lab SPL returned every known-answer row", row_count=len(rows))


CHECKERS: dict[str, Checker] = {
    "spl_syntax": check_spl_syntax,
    "sigma_validate_convert": check_sigma_validate_convert,
    "yara_compile": check_yara_compile,
    "lab_spl_results": check_lab_spl_results,
}


def run_checker(spec: CheckSpec, artifact: Artifact, calls: Sequence[ToolCall]) -> CheckResult:
    """Run one named checker without treating an unknown checker as a pass."""
    checker_name = str(spec.get("type", ""))
    checker = CHECKERS.get(checker_name)
    if checker is None:
        return _fail(f"unknown detection-engineering checker {checker_name!r}")
    return checker(spec, artifact, calls)
