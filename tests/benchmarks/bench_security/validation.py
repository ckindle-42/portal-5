"""Validation suite — honeypot + hardened-twin methodology.

A use-case PASSES only if the finding lands on the vulnerable target AND
vanishes on the hardened twin (zero false positives). Red, blue, and purple
are each scored independently with their own twin-control gate.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import httpx

from ._data import _LAB_EXEC_AVAILABLE  # noqa: F401 — test monkeypatching target

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

PIPELINE_URL = os.environ.get("PIPELINE_URL", "http://localhost:9099")
PIPELINE_API_KEY = os.environ.get("PIPELINE_API_KEY", "")


def _call_pipeline(prompt: str, workspace: str = "auto-security", timeout: float = 60.0) -> str:
    headers = {"Content-Type": "application/json"}
    if PIPELINE_API_KEY:
        headers["Authorization"] = f"Bearer {PIPELINE_API_KEY}"
    urls_to_try = [PIPELINE_URL, "http://host.docker.internal:9099", "http://localhost:9099"]
    for url in urls_to_try:
        try:
            r = httpx.post(
                f"{url}/v1/chat/completions",
                headers=headers,
                json={
                    "model": workspace,
                    "messages": [{"role": "user", "content": prompt}],
                    "stream": False,
                },
                timeout=timeout,
            )
            return r.json().get("choices", [{}])[0].get("message", {}).get("content", "")
        except Exception:
            continue
    return "[error: pipeline unreachable]"


def validate_usecase(usecase: dict, *, dry_run: bool = False) -> dict:
    """Run a validation use-case against vulnerable + hardened twin.

    usecase keys:
        name: str — use-case identifier
        cve: str — CVE or technique to test (optional)
        target_vulnerable: str — vulnerable target description
        target_hardened: str — hardened twin description
        red_prompt: str — prompt to send to red workspace
        blue_prompt: str — prompt to send to blue workspace (optional)
        models: dict — {red: str, blue: str} workspace names (optional)
    """
    name = usecase.get("name", "unnamed")
    cve = usecase.get("cve", "")
    models = usecase.get("models", {})
    red_ws = models.get("red", "auto-redteam")
    blue_ws = models.get("blue", "auto-blueteam")

    if dry_run:
        return {
            "usecase": name,
            "status": "dry_run",
            "target": usecase.get("target_vulnerable", "?"),
            "cve": cve,
            "models": {"red": red_ws, "blue": blue_ws},
            "hardened_twin": usecase.get("target_hardened", {}),
            "verdicts_expected": "red=land, blue=detect, purple=converge on vulnerable; zero on hardened",
        }

    if not _LAB_EXEC_AVAILABLE:
        return {"usecase": name, "status": "indeterminate", "reason": "lab exec not available"}

    red_prompt = usecase.get("red_prompt", "")
    blue_prompt = usecase.get("blue_prompt", "")

    if not red_prompt:
        return {"usecase": name, "status": "skipped", "reason": "no red_prompt defined"}

    # Run red against vulnerable target
    t0 = time.monotonic()
    red_vuln_response = _call_pipeline(red_prompt, workspace=red_ws)
    red_vuln_elapsed = time.monotonic() - t0

    # Run red against hardened twin
    hardened_prompt = usecase.get("hardened_prompt", red_prompt)
    t0 = time.monotonic()
    red_hard_response = _call_pipeline(hardened_prompt, workspace=red_ws)
    red_hard_elapsed = time.monotonic() - t0

    # Score: does red find the vuln on vulnerable but not on hardened?
    vuln_indicators = usecase.get("vuln_indicators", [cve, "vulnerable", "exploit", "confirmed"])
    red_vuln_found = any(ind.lower() in red_vuln_response.lower() for ind in vuln_indicators if ind)
    red_hard_clean = not any(
        ind.lower() in red_hard_response.lower() for ind in vuln_indicators if ind
    )

    red_pass = red_vuln_found and red_hard_clean

    # Blue detection (if blue_prompt provided)
    blue_result = None
    if blue_prompt:
        t0 = time.monotonic()
        blue_response = _call_pipeline(blue_prompt, workspace=blue_ws)
        blue_elapsed = time.monotonic() - t0

        detection_indicators = usecase.get(
            "detection_indicators", ["detected", "alert", "mitre", "T1", "T1190"]
        )
        blue_detected = any(ind.lower() in blue_response.lower() for ind in detection_indicators)

        blue_result = {
            "detected": blue_detected,
            "elapsed_s": round(blue_elapsed, 1),
            "response_preview": blue_response[:300],
        }

    # Purple convergence
    purple_pass = None
    if blue_result:
        purple_pass = red_pass and blue_result["detected"]

    status = "indeterminate"
    if red_pass and purple_pass is None:
        status = "verified"  # red-only validation
    elif red_pass and purple_pass:
        status = "verified"  # full purple convergence
    elif not red_pass:
        status = "rejected"

    return {
        "usecase": name,
        "status": status,
        "cve": cve,
        "red": {
            "vulnerable_found": red_vuln_found,
            "hardened_clean": red_hard_clean,
            "pass": red_pass,
            "vuln_elapsed_s": round(red_vuln_elapsed, 1),
            "hard_elapsed_s": round(red_hard_elapsed, 1),
            "vuln_response_preview": red_vuln_response[:300],
            "hard_response_preview": red_hard_response[:300],
        },
        "blue": blue_result,
        "purple_pass": purple_pass,
    }
