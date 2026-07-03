"""Triage call — P40 model diagnoses novel bench failures.

When Layer 1's deterministic supervisor hits a failure NOT in its known-pattern
table, this module packages the context (log tail, failing command, target/model
state) and asks a small triage model on the P40 one bounded question: "what's the
likely cause, and which corrective action (from a fixed menu) should the supervisor
take?"

The model returns a structured recommendation; the deterministic supervisor
validates it against an allowlist and executes only approved actions.

Config (env vars):
    TRIAGE_OLLAMA_URL  — P40 Ollama endpoint (default: http://localhost:11434)
    TRIAGE_MODEL       — model ID (default: ducquoc/gpt-oss-sonnet:latest)
"""

from __future__ import annotations

import json
import os
import re
import urllib.request
from typing import Any

from scripts.triage_actions import ALLOWED_ACTIONS, get_action_menu_description

# ── Config ────────────────────────────────────────────────────────────────────

DEFAULT_TRIAGE_OLLAMA_URL = os.environ.get("TRIAGE_OLLAMA_URL", "http://localhost:11434")
DEFAULT_TRIAGE_MODEL = os.environ.get("TRIAGE_MODEL", "ducquoc/gpt-oss-sonnet:latest")

# Max log lines to send to triage (bounded context window)
MAX_LOG_LINES = 100

# Confidence floor: below this → pause, don't act
DEFAULT_CONFIDENCE_FLOOR = 0.5


# ── Prompt construction ───────────────────────────────────────────────────────


def build_triage_prompt(
    log_tail: str,
    failing_line: str,
    scenario: str,
    target_state: str = "",
    model_state: str = "",
) -> str:
    """Build a bounded diagnostic prompt for the triage model.

    The prompt asks ONE question: what's the likely cause and which corrective
    action from the fixed menu should be taken? It does NOT ask the model to
    produce attack content or run arbitrary commands.
    """
    menu = get_action_menu_description()

    return f"""You are a run-health diagnostician for a security benchmark supervisor.
A benchmark run encountered a novel failure that the deterministic supervisor could not pattern-match.

## Failing context
Scenario: {scenario or "(unknown)"}
Failing line: {failing_line[:500]}

## Log tail (last {MAX_LOG_LINES} lines)
{log_tail[-8000:]}

## Target state
{target_state or "(not available)"}

## Model state
{model_state or "(not available)"}

## Your task
Diagnose the likely root cause and recommend ONE corrective action from this fixed menu:
{menu}

## Response format
Reply with ONLY a JSON object (no markdown, no explanation before/after):
{{
  "action": "<action_name from the menu above>",
  "params": {{}},
  "reason": "<one-sentence diagnosis>",
  "confidence": <0.0 to 1.0>
}}

If you cannot determine the cause with confidence >= 0.5, use action "pause_for_human" with confidence 0.0.
Never invent actions not in the menu. Never produce attack content."""


# ── Ollama call ───────────────────────────────────────────────────────────────


def call_triage_model(
    prompt: str,
    ollama_url: str = "",
    model: str = "",
    timeout: int = 120,
) -> dict[str, Any]:
    """Call the triage model on the P40 via Ollama /api/chat.

    Returns {"ok": True, "response": str} on success, {"ok": False, "error": str} on failure.
    """
    url = ollama_url or DEFAULT_TRIAGE_OLLAMA_URL
    mdl = model or DEFAULT_TRIAGE_MODEL

    payload = json.dumps(
        {
            "model": mdl,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "options": {"temperature": 0.1, "num_predict": 512},
        }
    ).encode()

    try:
        req = urllib.request.Request(
            f"{url}/api/chat",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read())
            content = data.get("message", {}).get("content", "")
            return {"ok": True, "response": content}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


# ── Response parsing ──────────────────────────────────────────────────────────


def parse_triage_response(raw: str) -> dict[str, Any]:
    """Parse the triage model's JSON response strictly.

    Returns {"action": str, "params": dict, "reason": str, "confidence": float}
    on success, or {"action": "pause_for_human", "error": str} on parse failure.
    """
    # Strip markdown code fences if present
    cleaned = raw.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    cleaned = cleaned.strip()

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        # Try to extract JSON from the response (handle nested braces)
        json_match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if json_match:
            try:
                data = json.loads(json_match.group())
            except json.JSONDecodeError:
                return {
                    "action": "pause_for_human",
                    "params": {},
                    "reason": "parse_error",
                    "confidence": 0.0,
                    "error": f"Could not parse JSON from response: {raw[:200]}",
                }
        else:
            return {
                "action": "pause_for_human",
                "params": {},
                "reason": "parse_error",
                "confidence": 0.0,
                "error": f"No JSON found in response: {raw[:200]}",
            }

    # Validate required fields
    action = data.get("action", "")
    if not action or not isinstance(action, str):
        return {
            "action": "pause_for_human",
            "params": {},
            "reason": "missing_action",
            "confidence": 0.0,
            "error": "Response missing 'action' field",
        }

    return {
        "action": action,
        "params": data.get("params", {}),
        "reason": data.get("reason", ""),
        "confidence": float(data.get("confidence", 0.0)),
    }


# ── Main diagnose function ────────────────────────────────────────────────────


def diagnose(
    log_tail: str,
    failing_line: str,
    scenario: str,
    target_state: str = "",
    model_state: str = "",
    ollama_url: str = "",
    model: str = "",
    confidence_floor: float = DEFAULT_CONFIDENCE_FLOOR,
) -> dict[str, Any]:
    """Diagnose a novel failure using the P40 triage model.

    Returns a dict with:
        action: str — one of ALLOWED_ACTIONS keys (or "pause_for_human")
        params: dict — parameters for the action
        reason: str — diagnosis explanation
        confidence: float — 0.0 to 1.0
        allowed: bool — whether the action is in the allowlist
        above_floor: bool — whether confidence meets the floor
        raw_response: str — raw model output (for logging)
    """
    prompt = build_triage_prompt(
        log_tail=log_tail,
        failing_line=failing_line,
        scenario=scenario,
        target_state=target_state,
        model_state=model_state,
    )

    result = call_triage_model(prompt, ollama_url=ollama_url, model=model)

    if not result.get("ok"):
        return {
            "action": "pause_for_human",
            "params": {},
            "reason": "model_unavailable",
            "confidence": 0.0,
            "allowed": True,
            "above_floor": False,
            "raw_response": "",
            "error": result.get("error", "unknown"),
        }

    raw_response = result.get("response", "")
    parsed = parse_triage_response(raw_response)
    parsed["raw_response"] = raw_response

    # Validate against allowlist
    action = parsed.get("action", "pause_for_human")
    parsed["allowed"] = action in ALLOWED_ACTIONS

    # If disallowed, force pause_for_human
    if not parsed["allowed"]:
        parsed["action"] = "pause_for_human"
        parsed["params"] = {}
        parsed["reason"] = f"disallowed_action: {action}"
        parsed["confidence"] = 0.0
        parsed["allowed"] = True  # pause_for_human is always allowed

    # Check confidence floor
    confidence = parsed.get("confidence", 0.0)
    parsed["above_floor"] = confidence >= confidence_floor

    # If below floor, force pause
    if not parsed["above_floor"] and parsed["action"] != "pause_for_human":
        parsed["action"] = "pause_for_human"
        parsed["params"] = {}
        parsed["reason"] = f"low_confidence ({confidence:.2f} < {confidence_floor:.2f})"

    return parsed


# ── Convenience: extract log tail from a log file ─────────────────────────────


def extract_log_tail(log_path: str, max_lines: int = MAX_LOG_LINES) -> str:
    """Read the last N lines from a log file."""
    try:
        with open(log_path) as f:
            lines = f.readlines()
        return "".join(lines[-max_lines:])
    except Exception:
        return ""
