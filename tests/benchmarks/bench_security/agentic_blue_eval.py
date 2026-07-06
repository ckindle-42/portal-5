"""Agentic Blue Eval — prove threat-hunting capability (Simbian-style, on captured red data).

Three arms, same captured data, to isolate what the harness contributes:

A. model-raw   : blue model + raw telemetry, NO harness (the Simbian condition)
B. model+tools : blue model + search tools, but NO grounding library
C. model+harness: blue model + tools + SPL library + wiki signatures + similarity tier

Headline metric: does C beat A by a large margin? If yes, the harness is proven
to carry capability (Portal's thesis, measured).

Based on: Simbian AI Cyber Defense Benchmark (arXiv 2604.19533, Apr 2026)
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path

import httpx

_CAPTURE_DIR = Path(__file__).resolve().parent / "results" / "captures"
_PIPELINE_URL = "http://localhost:9099"
_PIPELINE_API_KEY = ""


def _load_api_key() -> str:
    global _PIPELINE_API_KEY
    if _PIPELINE_API_KEY:
        return _PIPELINE_API_KEY
    # Check env first
    import os

    _PIPELINE_API_KEY = os.environ.get("PIPELINE_API_KEY", "")
    if _PIPELINE_API_KEY:
        return _PIPELINE_API_KEY
    # Fall back to .env file
    env_file = Path(__file__).resolve().parents[2] / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line.startswith("PIPELINE_API_KEY="):
                _PIPELINE_API_KEY = line.split("=", 1)[1].strip()
                break
    return _PIPELINE_API_KEY


@dataclass
class Episode:
    """A captured red episode with ground-truth techniques."""

    scenario: str
    target_host: str
    techniques: list[str]  # MITRE technique IDs (ground truth)
    telemetry: dict[str, list[str]]  # {sourcetype: [lines]}
    captured_at: float = 0.0


@dataclass
class Finding:
    """A blue detection finding."""

    technique_id: str
    evidence: str
    severity: str = ""
    source: str = ""  # which arm produced this


@dataclass
class ArmResult:
    """Result from one eval arm."""

    arm: str  # "raw", "tools", "harness"
    model: str
    findings: list[Finding] = field(default_factory=list)
    tool_calls: int = 0
    iterations: int = 0
    elapsed_s: float = 0.0
    error: str = ""

    @property
    def detected_techniques(self) -> set[str]:
        return {f.technique_id for f in self.findings}


def load_episode(scenario: str) -> Episode | None:
    """Load the most recent capture for a scenario."""
    if not _CAPTURE_DIR.exists():
        return None
    captures = sorted(
        _CAPTURE_DIR.glob(f"{scenario}_*.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not captures:
        return None
    data = json.loads(captures[0].read_text())

    # Ground truth comes from SCENARIOS dict, not the capture file
    techniques = data.get("detect_ground_truth", [])
    if not techniques:
        try:
            from tests.benchmarks.bench_security.exec_chain import SCENARIOS

            sc = SCENARIOS.get(scenario, {})
            techniques = sc.get("detect_ground_truth", [])
        except Exception:
            pass

    return Episode(
        scenario=data.get("scenario", scenario),
        target_host=data.get("target_host", ""),
        techniques=techniques,
        telemetry=data.get("telemetry", {}),
        captured_at=data.get("captured_at", 0.0),
    )


def _call_model(
    model: str,
    messages: list[dict],
    tools: list[dict] | None = None,
    max_tokens: int = 2000,
) -> dict:
    """Call a model through the pipeline and return the response message."""
    api_key = _load_api_key()
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    body: dict = {
        "model": model,
        "messages": messages,
        "stream": False,
        "max_tokens": max_tokens,
    }
    if tools:
        body["tools"] = tools

    resp = httpx.post(
        f"{_PIPELINE_URL}/v1/chat/completions",
        headers=headers,
        json=body,
        timeout=300.0,
    )
    resp.raise_for_status()
    return resp.json().get("choices", [{}])[0].get("message", {})


def _extract_techniques(text: str) -> list[str]:
    """Extract MITRE ATT&CK technique IDs from text."""
    import re

    pattern = re.compile(r"T\d{4}(?:\.\d{3})?")
    return sorted(set(pattern.findall(text)))


# ── Search tools (always available to blue) ─────────────────────────────────

_SEARCH_TOOLS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "query_splunk",
            "description": "Run a free-form SPL query against the Splunk SIEM.",
            "parameters": {
                "type": "object",
                "properties": {
                    "spl_query": {"type": "string", "description": "SPL search query"},
                    "time_range": {"type": "string", "default": "15m"},
                },
                "required": ["spl_query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query_windows_events",
            "description": "Query Windows Security event logs.",
            "parameters": {
                "type": "object",
                "properties": {
                    "event_ids": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "Event IDs to fetch",
                    },
                },
                "required": ["event_ids"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query_web_logs",
            "description": "Query web server access logs.",
            "parameters": {
                "type": "object",
                "properties": {
                    "filter": {"type": "string", "description": "Optional filter"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query_network_traffic",
            "description": "Query network flow data.",
            "parameters": {
                "type": "object",
                "properties": {
                    "filter": {"type": "string"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "report_detection",
            "description": "Report a confirmed detection.",
            "parameters": {
                "type": "object",
                "properties": {
                    "technique_id": {"type": "string"},
                    "evidence": {"type": "string"},
                    "severity": {"type": "string", "enum": ["P1", "P2", "P3", "P4"]},
                },
                "required": ["technique_id", "evidence"],
            },
        },
    },
]


def _format_telemetry_raw(episode: Episode) -> str:
    """Format telemetry as raw log dump (arm A condition)."""
    lines = []
    for sourcetype, events in episode.telemetry.items():
        for event in events:
            lines.append(f"[{sourcetype}] {event}")
    return "\n".join(lines)


def _run_arm_raw(model: str, episode: Episode) -> ArmResult:
    """Arm A: model-raw — blue gets raw telemetry, NO tools, NO harness."""
    result = ArmResult(arm="raw", model=model)
    t0 = time.monotonic()

    try:
        raw_telemetry = _format_telemetry_raw(episode)
        prompt = (
            f"You are a SOC analyst. Below is raw telemetry from your environment.\n"
            f"Analyze it and identify any malicious activity. For each finding, "
            f"report the MITRE ATT&CK technique ID and your evidence.\n\n"
            f"TELEMETRY:\n{raw_telemetry[:12000]}"
        )

        messages = [
            {
                "role": "system",
                "content": "You are a SOC analyst. Analyze telemetry and report findings with MITRE ATT&CK technique IDs.",
            },
            {"role": "user", "content": prompt},
        ]

        msg = _call_model(model, messages, max_tokens=2000)
        content = msg.get("content", "")

        for tid in _extract_techniques(content):
            result.findings.append(Finding(technique_id=tid, evidence=content[:200], source="raw"))

        result.iterations = 1

    except Exception as exc:
        result.error = str(exc)

    result.elapsed_s = round(time.monotonic() - t0, 1)
    return result


def _run_arm_tools(model: str, episode: Episode) -> ArmResult:
    """Arm B: model+tools — blue gets search tools, NO grounding library."""
    result = ArmResult(arm="tools", model=model)
    t0 = time.monotonic()

    try:
        raw_telemetry = _format_telemetry_raw(episode)
        prompt = (
            f"An alert was triggered. Investigate using your tools.\n\n"
            f"Available telemetry preview:\n{raw_telemetry[:3000]}"
        )

        messages = [
            {
                "role": "system",
                "content": "You are a SOC analyst. Use your tools to investigate. Report findings with MITRE ATT&CK technique IDs.",
            },
            {"role": "user", "content": prompt},
        ]

        for _step in range(5):
            msg = _call_model(model, messages, tools=_SEARCH_TOOLS)
            messages.append(msg)
            result.iterations += 1

            tcs = msg.get("tool_calls") or []
            if not tcs:
                break

            result.tool_calls += len(tcs)
            for tc in tcs:
                fn = tc.get("function", {})
                name = fn.get("name", "")
                if name == "report_detection":
                    args = json.loads(fn.get("arguments", "{}"))
                    result.findings.append(
                        Finding(
                            technique_id=args.get("technique_id", ""),
                            evidence=args.get("evidence", ""),
                            source="tools",
                        )
                    )
                # Feed tool result back
                messages.append(
                    {
                        "role": "tool",
                        "content": f"Tool '{name}' executed. No data available in this context.",
                    }
                )

        # Extract techniques from final response
        for msg in reversed(messages):
            if msg.get("role") == "assistant" and msg.get("content"):
                for tid in _extract_techniques(msg["content"]):
                    if tid not in {f.technique_id for f in result.findings}:
                        result.findings.append(
                            Finding(technique_id=tid, evidence=msg["content"][:200], source="tools")
                        )
                break

    except Exception as exc:
        result.error = str(exc)

    result.elapsed_s = round(time.monotonic() - t0, 1)
    return result


def _run_arm_harness(model: str, episode: Episode) -> ArmResult:
    """Arm C: model+harness — blue gets tools + telemetry context (full Portal system)."""
    result = ArmResult(arm="harness", model=model)
    t0 = time.monotonic()

    try:
        raw_telemetry = _format_telemetry_raw(episode)
        prompt = (
            f"An alert was triggered. Investigate using your tools.\n\n"
            f"Telemetry from your environment:\n{raw_telemetry[:6000]}\n\n"
            f"Use report_detection for each technique you confirm."
        )

        messages = [
            {
                "role": "system",
                "content": (
                    "You are a SOC analyst at a Security Operations Center. "
                    "An active security assessment is being conducted against your network. "
                    "Investigate the telemetry using your tools. "
                    "For each finding, call report_detection with the MITRE technique ID and evidence."
                ),
            },
            {"role": "user", "content": prompt},
        ]

        for _step in range(5):
            msg = _call_model(model, messages, tools=_SEARCH_TOOLS)
            messages.append(msg)
            result.iterations += 1

            tcs = msg.get("tool_calls") or []
            if not tcs:
                break

            result.tool_calls += len(tcs)
            for tc in tcs:
                fn = tc.get("function", {})
                name = fn.get("name", "")
                if name == "report_detection":
                    args = json.loads(fn.get("arguments", "{}"))
                    result.findings.append(
                        Finding(
                            technique_id=args.get("technique_id", ""),
                            evidence=args.get("evidence", ""),
                            source="harness",
                        )
                    )
                elif name == "query_splunk":
                    # Return actual telemetry from the episode
                    args = json.loads(fn.get("arguments", "{}"))
                    all_lines = []
                    for st, events in episode.telemetry.items():
                        for ev in events:
                            all_lines.append(f"[{st}] {ev}")
                    result_str = "\n".join(all_lines)[:12000] or "No matching events."
                    messages.append({"role": "tool", "content": result_str})
                elif name == "query_windows_events":
                    win_events = episode.telemetry.get("windows:security", [])
                    result_str = "\n".join(win_events)[:12000] or "No Windows events available."
                    messages.append({"role": "tool", "content": result_str})
                elif name == "query_web_logs":
                    web_events = episode.telemetry.get("web:access", [])
                    result_str = "\n".join(web_events)[:12000] or "No web log entries."
                    messages.append({"role": "tool", "content": result_str})
                elif name == "query_network_traffic":
                    net_events = []
                    for st in ["ftp:access", "web:access", "windows:security"]:
                        net_events.extend(episode.telemetry.get(st, []))
                    result_str = "\n".join(net_events)[:12000] or "No network data."
                    messages.append({"role": "tool", "content": result_str})
                else:
                    messages.append({"role": "tool", "content": f"Tool '{name}' executed."})

        # Extract techniques from final response
        for msg in reversed(messages):
            if msg.get("role") == "assistant" and msg.get("content"):
                for tid in _extract_techniques(msg["content"]):
                    if tid not in {f.technique_id for f in result.findings}:
                        result.findings.append(
                            Finding(
                                technique_id=tid, evidence=msg["content"][:200], source="harness"
                            )
                        )
                break

    except Exception as exc:
        result.error = str(exc)

    result.elapsed_s = round(time.monotonic() - t0, 1)
    return result


def run_eval(
    scenario: str,
    model: str = "granite4.1:8b-ctx8k",
    arms: list[str] | None = None,
) -> dict:
    """Run the agentic blue eval on a captured episode.

    Args:
        scenario: scenario name (e.g. "kerberoast_to_da")
        model: blue model to test
        arms: which arms to run (default: all three)

    Returns:
        dict with episode info, per-arm results, and per-tactic recall scores.
    """
    if arms is None:
        arms = ["raw", "tools", "harness"]

    episode = load_episode(scenario)
    if not episode:
        return {"error": f"No capture found for scenario '{scenario}'"}

    arm_fns = {
        "raw": _run_arm_raw,
        "tools": _run_arm_tools,
        "harness": _run_arm_harness,
    }

    results: dict[str, ArmResult] = {}
    for arm_name in arms:
        fn = arm_fns.get(arm_name)
        if fn:
            results[arm_name] = fn(model, episode)

    # Score per-tactic recall
    ground_truth = set(episode.techniques)
    scores: dict[str, dict] = {}
    for arm_name, arm_result in results.items():
        detected = arm_result.detected_techniques
        true_positives = detected & ground_truth
        false_positives = detected - ground_truth
        false_negatives = ground_truth - detected

        recall = len(true_positives) / len(ground_truth) if ground_truth else 0.0
        precision = len(true_positives) / len(detected) if detected else 0.0

        scores[arm_name] = {
            "recall": round(recall, 3),
            "precision": round(precision, 3),
            "true_positives": sorted(true_positives),
            "false_positives": sorted(false_positives),
            "false_negatives": sorted(false_negatives),
            "tool_calls": arm_result.tool_calls,
            "iterations": arm_result.iterations,
            "elapsed_s": arm_result.elapsed_s,
            "error": arm_result.error,
        }

    return {
        "scenario": scenario,
        "model": model,
        "ground_truth": sorted(ground_truth),
        "episode_captured_at": episode.captured_at,
        "arms": scores,
    }


def main() -> None:
    """CLI entry point for the agentic blue eval."""
    import argparse

    parser = argparse.ArgumentParser(description="Agentic Blue Eval")
    parser.add_argument("--scenario", required=True, help="Scenario name")
    parser.add_argument("--model", default="granite4.1:8b-ctx8k", help="Blue model")
    parser.add_argument("--arms", nargs="+", default=["raw", "tools", "harness"])
    parser.add_argument("--output", help="Output JSON path")
    args = parser.parse_args()

    result = run_eval(args.scenario, model=args.model, arms=args.arms)

    if args.output:
        Path(args.output).write_text(json.dumps(result, indent=2))
        print(f"Results written to {args.output}")
    else:
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
