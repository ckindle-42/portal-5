"""Agentic Blue Eval — prove threat-hunting capability (Simbian-style, on captured red data).

Three arms, same captured data, to isolate what the harness contributes:

A. model-raw   : blue model + raw telemetry, NO harness (the Simbian condition)
B. model+tools : blue model + search tools with real data, but NO grounding library
C. model+harness: blue model + tools + SPL detection library + similarity-tier
                  retrieval (lookup_technique_signature, search_similar_techniques)

Headline metric: does C beat A by a large margin? If yes, the harness is proven
to carry capability (Portal's thesis, measured).

Based on: Simbian AI Cyber Defense Benchmark (arXiv 2604.19533, Apr 2026)
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path

import httpx

from ._data import resolve_pipeline_model
from .siem.spl_detections import technique_reference, technique_signature_full
from .unknown_defense import MatchGrade, compute_similarity

_CAPTURE_DIR = Path(__file__).resolve().parent / "results" / "captures"
_PIPELINE_URL = "http://localhost:9099"
_OLLAMA_URL = "http://localhost:11434"
_DIRECT_OLLAMA = os.environ.get("CHAIN_DIRECT_OLLAMA", "").lower() == "true"
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
    """Call a model through the pipeline (or direct Ollama if CHAIN_DIRECT_OLLAMA=true)."""
    api_key = _load_api_key()

    if _DIRECT_OLLAMA:
        # Direct Ollama — bypass pipeline routing
        body: dict = {
            "model": model,
            "messages": messages,
            "stream": False,
        }
        if tools:
            body["tools"] = tools
        resp = httpx.post(
            f"{_OLLAMA_URL}/api/chat",
            json=body,
            timeout=300.0,
        )
        resp.raise_for_status()
        return resp.json().get("message", {})
    else:
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        body = {
            "model": resolve_pipeline_model(model),
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


# ── M1: Three-tier scoring helpers ──────────────────────────────────────────


def _parent_technique(technique_id: str) -> str:
    """Strip sub-technique suffix: T1558.003 -> T1558."""
    return technique_id.split(".")[0]


_tactic_cache: dict[str, str] | None = None


def _load_tactic_map() -> dict[str, str]:
    """Build technique->tactic map from spl_detections.yaml compliance_mapping.

    Returns {technique_id: tactic} for every technique that has a
    mitre-attack compliance entry with a tactic field.
    """
    global _tactic_cache
    if _tactic_cache is not None:
        return _tactic_cache

    import yaml

    yaml_path = Path(__file__).resolve().parent / "siem" / "spl_detections.yaml"
    tactic_map: dict[str, str] = {}
    if yaml_path.exists():
        data = yaml.safe_load(yaml_path.read_text()) or {}
        for tid, entry in data.items():
            if not isinstance(entry, dict):
                continue
            for mapping in entry.get("compliance_mapping", []):
                if (
                    isinstance(mapping, dict)
                    and mapping.get("framework") == "mitre-attack"
                    and mapping.get("tactic")
                ):
                    tactic_map[tid] = mapping["tactic"]
                    break

    # Supplement with embedded mitre_mcp data for techniques not in YAML
    embedded_tactics = {
        "T1190": "initial-access",
        "T1059": "execution",
        "T1059.004": "execution",
        "T1505.003": "persistence",
        "T1003": "credential-access",
        "T1003.001": "credential-access",
        "T1003.003": "credential-access",
        "T1003.006": "credential-access",
        "T1558.003": "credential-access",
        "T1558.004": "credential-access",
        "T1078": "persistence",
        "T1078.004": "persistence",
        "T1557": "credential-access",
        "T1557.001": "credential-access",
        "T1550.002": "lateral-movement",
        "T1021.002": "lateral-movement",
        "T1210": "lateral-movement",
        "T1053.005": "persistence",
        "T1548.001": "privilege-escalation",
        "T1068": "privilege-escalation",
        "T1047": "execution",
        "T1552": "credential-access",
        "T1552.005": "credential-access",
        "T1537": "exfiltration",
        "T1110": "credential-access",
        "T1110.003": "credential-access",
        "T1083": "discovery",
        "T1189": "initial-access",
        "T1203": "execution",
        "T1592": "reconnaissance",
        "T1595": "reconnaissance",
        "T1610": "execution",
        "T1611": "privilege-escalation",
    }
    for tid, tactic in embedded_tactics.items():
        tactic_map.setdefault(tid, tactic)

    # Also derive parent tactic from sub-technique mappings
    for tid in list(tactic_map.keys()):
        parent = _parent_technique(tid)
        if parent not in tactic_map:
            tactic_map[parent] = tactic_map[tid]

    _tactic_cache = tactic_map
    return tactic_map


def _tactic_for(technique_id: str) -> str:
    """Look up the MITRE tactic for a technique ID. Returns '' if unknown."""
    return _load_tactic_map().get(technique_id, "")


def score_findings_tiered(detected: set[str], ground_truth: set[str]) -> dict[str, dict]:
    """Score findings at three tiers: exact, parent, tactic.

    A finding credits the HIGHEST tier it satisfies:
    - exact:  full sub-technique ID matches (T1558.003 == T1558.003)
    - parent: technique family matches (T1558.003 -> T1558 == T1558)
    - tactic: MITRE tactic matches (both map to same tactic, e.g. credential-access)

    Returns dict with keys 'exact', 'parent', 'tactic', each containing
    recall, precision, true_positives, false_positives, false_negatives.
    """
    tactic_map = _load_tactic_map()

    # Classify each detected finding at the highest tier it achieves
    exact_tps: set[str] = set()
    parent_tps: set[str] = set()
    tactic_tps: set[str] = set()

    # Track which ground-truth items are covered at each tier
    gt_covered_exact: set[str] = set()
    gt_covered_parent: set[str] = set()
    gt_covered_tactic: set[str] = set()

    for det in detected:
        if det in ground_truth:
            exact_tps.add(det)
            gt_covered_exact.add(det)
        elif _parent_technique(det) in {_parent_technique(gt) for gt in ground_truth}:
            parent_tps.add(det)
            # Find which ground truth this parent-matches
            for gt in ground_truth:
                if _parent_technique(det) == _parent_technique(gt):
                    gt_covered_parent.add(gt)
                    break
        else:
            det_tactic = tactic_map.get(det, "")
            if det_tactic:
                gt_tactics = {gt: tactic_map.get(gt, "") for gt in ground_truth}
                matched_gt = None
                for gt, gt_tac in gt_tactics.items():
                    if (
                        gt_tac == det_tactic
                        and gt not in gt_covered_exact
                        and gt not in gt_covered_parent
                    ):
                        matched_gt = gt
                        break
                if matched_gt:
                    tactic_tps.add(det)
                    gt_covered_tactic.add(matched_gt)

    # Union of all TPs across tiers (for overall recall)
    all_tps = exact_tps | parent_tps | tactic_tps
    all_gt_covered = gt_covered_exact | gt_covered_parent | gt_covered_tactic

    def _tier_scores(tps: set[str], gt_covered: set[str], tier_name: str) -> dict:
        fps = detected - all_tps if tier_name == "tactic" else set()
        if tier_name == "exact":
            fps = detected - exact_tps - parent_tps - tactic_tps
        fn = ground_truth - all_gt_covered
        recall = len(gt_covered) / len(ground_truth) if ground_truth else 0.0
        # Precision: of all detected, how many were TPs at this tier or above
        precision = len(tps) / len(detected) if detected else 0.0
        return {
            "recall": round(recall, 3),
            "precision": round(precision, 3),
            "true_positives": sorted(tps),
            "false_positives": sorted(fps),
            "false_negatives": sorted(fn),
        }

    # Build per-tier results
    # For parent tier: parent recall includes exact matches too
    parent_recall_gt = gt_covered_exact | gt_covered_parent
    tactic_recall_gt = gt_covered_exact | gt_covered_parent | gt_covered_tactic

    return {
        "exact": {
            "recall": round(len(gt_covered_exact) / len(ground_truth), 3) if ground_truth else 0.0,
            "true_positives": sorted(exact_tps),
            "gt_covered": sorted(gt_covered_exact),
        },
        "parent": {
            "recall": round(len(parent_recall_gt) / len(ground_truth), 3) if ground_truth else 0.0,
            "true_positives": sorted(exact_tps | parent_tps),
            "gt_covered": sorted(parent_recall_gt),
        },
        "tactic": {
            "recall": round(len(tactic_recall_gt) / len(ground_truth), 3) if ground_truth else 0.0,
            "true_positives": sorted(all_tps),
            "gt_covered": sorted(tactic_recall_gt),
        },
        "overall": {
            "recall": round(len(all_gt_covered) / len(ground_truth), 3) if ground_truth else 0.0,
            "precision": round(len(all_tps) / len(detected), 3) if detected else 0.0,
            "true_positives": sorted(all_tps),
            "false_positives": sorted(detected - all_tps),
            "false_negatives": sorted(ground_truth - all_gt_covered),
        },
    }


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

# ── Grounding tools (arm C only — the actual harness) ────────────────────────
#
# This is what was missing from arm C until now: real search tools (above)
# plus retrieval against Portal's own grounding library, so the model can
# check a hypothesis or search by evidence instead of relying on training
# knowledge alone. Backed by the same SPL detection library (siem/spl_detections.yaml)
# and similarity-tier heuristic (unknown_defense.compute_similarity) blue.py's
# real chain-test path already uses — this eval just wasn't wired to them.

_GROUNDING_TOOLS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "lookup_technique_signature",
            "description": (
                "Look up the known evidence signature for a specific MITRE ATT&CK "
                "technique ID from the detection library, to confirm or refute a "
                "hypothesis before calling report_detection."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "technique_id": {
                        "type": "string",
                        "description": "MITRE technique ID, e.g. T1558.003",
                    },
                },
                "required": ["technique_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_similar_techniques",
            "description": (
                "Search the detection library for the technique whose known evidence "
                "signature best matches a free-text description of what you observed. "
                "Use this when you see suspicious activity but are not sure of the "
                "exact sub-technique ID — do not guess from memory."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "evidence_description": {
                        "type": "string",
                        "description": (
                            "Free-text description of observed evidence (process "
                            "names, event IDs, ports, behaviors)"
                        ),
                    },
                },
                "required": ["evidence_description"],
            },
        },
    },
]


def _dispatch_grounding_tool(name: str, args: dict) -> str | None:
    """Answer a grounding-tool call from Portal's own detection library.

    Returns None if ``name`` isn't a grounding tool, so callers can fall
    through to the search-tool dispatch.
    """
    ref = technique_reference()
    if name == "lookup_technique_signature":
        tid = args.get("technique_id", "").strip()
        desc = ref.get(tid)
        if desc:
            # M4: also return full signature with distinguishing features
            full = technique_signature_full(tid)
            diff = full.get("distinguishing_features", {})
            result = f"{tid}: {desc}"
            if diff.get("sibling_diff"):
                result += f"\nSibling distinction: {diff['sibling_diff']}"
            if diff.get("key_indicator"):
                result += f"\nKey indicator: {diff['key_indicator']}"
            if full.get("expected_signal"):
                result += f"\nExpected signal: {full['expected_signal']}"
            return result
        return (
            f"No signature on file for '{tid}'. Known techniques: {', '.join(sorted(ref.keys()))}"
        )
    if name == "search_similar_techniques":
        import re

        evidence = args.get("evidence_description", "")
        # compute_similarity expects pre-tokenized keywords, not a raw string —
        # split on non-alphanumerics so "EventCode=4769" yields "eventcode"/"4769"
        # instead of one unmatchable token (verified against test_unknown_defense.py's
        # calling convention).
        keywords = [w for w in re.split(r"[^a-zA-Z0-9]+", evidence.lower()) if w]
        result = compute_similarity({"keywords": keywords}, ref)
        if result.grade == MatchGrade.NONE:
            return f"No similar technique found. {result.detail}"
        return (
            f"Best match: {result.matched_technique} (grade={result.grade}, "
            f"confidence={result.confidence:.2f}). Overlapping terms: "
            f"{', '.join(result.overlapping_features)}. "
            f"Signature: {ref.get(result.matched_technique, '')}"
        )
    return None


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


def _query_real_telemetry(name: str, episode: Episode, query_args: dict | None = None) -> str:
    """Answer a search-tool call with the episode's actual captured telemetry.

    Shared by arms B and C — "search tools" only means something if the tools
    return real data. Arm B (found 2026-07-05) previously answered every call
    with a canned "No data available in this context" regardless of what was
    asked, making the model's tool calls pointless and any recall it scored
    attributable to guessing from training knowledge, not investigation. The
    documented arm B/C distinction is the grounding *library* (SPL detection
    library, wiki signatures, similarity tier) layered on top of real search —
    not whether search returns anything at all.

    When query_args are provided, extract keywords and filter telemetry to
    matching lines — so the model actually finds what it's looking for.
    """

    def _filter_lines(lines: list[str], keywords: list[str]) -> list[str]:
        if not keywords:
            return lines
        return [line for line in lines if any(kw.lower() in line.lower() for kw in keywords)]

    # Extract filter keywords from query args
    keywords: list[str] = []
    if query_args:
        for v in query_args.values():
            if isinstance(v, str):
                # Extract EventCode=N, technique IDs, etc.
                import re

                keywords.extend(re.findall(r"EventCode[= ]\d+", v))
                keywords.extend(re.findall(r"T\d{4}(?:\.\d{3})?", v))
                # Also extract raw numbers that might be event IDs
                for m in re.findall(r"\b(\d{4})\b", v):
                    if int(m) >= 4000:  # Windows event IDs are 4000+
                        keywords.append(f"EventCode={m}")

    if name == "query_splunk":
        all_lines = [f"[{st}] {ev}" for st, events in episode.telemetry.items() for ev in events]
        filtered = _filter_lines(all_lines, keywords) if keywords else all_lines
        return (
            "\n".join(filtered)[:12000]
            or f"No matching events for query. Available: {len(all_lines)} total events."
        )
    if name == "query_windows_events":
        win_events = episode.telemetry.get("windows:security", [])
        filtered = _filter_lines(win_events, keywords) if keywords else win_events
        return (
            "\n".join(filtered)[:12000]
            or f"No matching Windows events. Available: {len(win_events)} total events."
        )
    if name == "query_web_logs":
        web_events = episode.telemetry.get("web:access", [])
        filtered = _filter_lines(web_events, keywords) if keywords else web_events
        return (
            "\n".join(filtered)[:12000]
            or f"No matching web log entries. Available: {len(web_events)} total entries."
        )
    if name == "query_network_traffic":
        net_events = []
        for st in ["ftp:access", "web:access", "windows:security"]:
            net_events.extend(episode.telemetry.get(st, []))
        filtered = _filter_lines(net_events, keywords) if keywords else net_events
        return (
            "\n".join(filtered)[:12000]
            or f"No matching network data. Available: {len(net_events)} total events."
        )
    return f"Tool '{name}' executed."


def _run_tool_driven_arm(
    arm_name: str,
    model: str,
    episode: Episode,
    telemetry_preview_chars: int,
    grounded: bool,
) -> ArmResult:
    """Shared driver for arm B (tools) and arm C (harness): tool loop + real telemetry.

    Findings only come from an explicit ``report_detection`` call with a
    technique_id and evidence — this is the honesty-contract enforcement the
    design doc requires ("synthetic never counts"). There is deliberately no
    fallback that scrapes MITRE IDs out of the model's free-text response: a
    model that mentions "T1558.003" in passing without ever calling
    report_detection has not investigated anything, and crediting that text
    as a finding let ungrounded guessing masquerade as hunting capability
    (found 2026-07-05 — a model scored nonzero recall in arm B despite every
    tool call in that run returning zero real data).

    When ``grounded`` is True (arm C only), the model also gets
    ``lookup_technique_signature``/``search_similar_techniques`` — retrieval
    against Portal's own detection library — so it can check a hypothesis
    against a known evidence signature instead of guessing the exact
    sub-technique from training knowledge alone.
    """
    result = ArmResult(arm=arm_name, model=model)
    t0 = time.monotonic()
    tools = _SEARCH_TOOLS + _GROUNDING_TOOLS if grounded else _SEARCH_TOOLS

    try:
        raw_telemetry = _format_telemetry_raw(episode)
        prompt = (
            f"An alert was triggered. Investigate using your tools.\n\n"
            f"Telemetry from your environment:\n{raw_telemetry[:telemetry_preview_chars]}\n\n"
            f"Use report_detection for each technique you confirm."
        )

        system_content = (
            "You are a SOC analyst at a Security Operations Center. "
            "An active security assessment is being conducted against your network. "
            "Investigate the telemetry using your tools. "
            "For each finding, call report_detection with the MITRE technique ID and evidence."
        )
        if grounded:
            system_content += (
                " Before reporting, use lookup_technique_signature or "
                "search_similar_techniques to confirm the exact sub-technique ID "
                "against its known evidence signature — do not guess the sub-technique "
                "from memory alone."
            )

        messages = [
            {"role": "system", "content": system_content},
            {"role": "user", "content": prompt},
        ]

        for _step in range(5):
            msg = _call_model(model, messages, tools=tools)
            messages.append(msg)
            result.iterations += 1

            tcs = msg.get("tool_calls") or []
            if not tcs:
                break

            result.tool_calls += len(tcs)
            for tc in tcs:
                fn = tc.get("function", {})
                name = fn.get("name", "")
                tc_id = tc.get("id", "")
                raw_args = fn.get("arguments", "{}")
                # Ollama returns arguments as dict, OpenAI as JSON string
                if isinstance(raw_args, dict):
                    args = raw_args
                else:
                    try:
                        args = json.loads(raw_args or "{}")
                    except json.JSONDecodeError:
                        args = {}
                if name == "report_detection":
                    result.findings.append(
                        Finding(
                            technique_id=args.get("technique_id", ""),
                            evidence=args.get("evidence", ""),
                            source=arm_name,
                        )
                    )
                    messages.append(
                        {"role": "tool", "tool_call_id": tc_id, "content": "Detection logged."}
                    )
                    continue
                tool_args = args
                grounding_result = _dispatch_grounding_tool(name, tool_args) if grounded else None
                if grounding_result is not None:
                    messages.append(
                        {"role": "tool", "tool_call_id": tc_id, "content": grounding_result}
                    )
                else:
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tc_id,
                            "content": _query_real_telemetry(name, episode, tool_args),
                        }
                    )

    except Exception as exc:
        result.error = str(exc)

    result.elapsed_s = round(time.monotonic() - t0, 1)
    return result


def _run_arm_tools(model: str, episode: Episode) -> ArmResult:
    """Arm B: model+tools — blue gets search tools with real data, NO grounding library."""
    return _run_tool_driven_arm(
        "tools", model, episode, telemetry_preview_chars=3000, grounded=False
    )


def _run_arm_harness(model: str, episode: Episode) -> ArmResult:
    """Arm C: model+harness — blue gets tools + real telemetry + the detection-library
    grounding tools (lookup_technique_signature, search_similar_techniques). This is
    what makes arm C an actual test of "does the harness carry capability" rather
    than a relabeled arm B — the model can check its hypothesis against a known
    evidence signature instead of guessing the exact sub-technique from memory.
    """
    return _run_tool_driven_arm(
        "harness", model, episode, telemetry_preview_chars=6000, grounded=True
    )


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

    # Score per-tactic recall (M1: three-tier scoring — exact/parent/tactic)
    ground_truth = set(episode.techniques)
    scores: dict[str, dict] = {}
    for arm_name, arm_result in results.items():
        detected = arm_result.detected_techniques
        true_positives = detected & ground_truth
        false_positives = detected - ground_truth
        false_negatives = ground_truth - detected

        recall = len(true_positives) / len(ground_truth) if ground_truth else 0.0
        precision = len(true_positives) / len(detected) if detected else 0.0

        # M1: tiered scoring — reveals hidden capability at parent/tactic levels
        tiered = score_findings_tiered(detected, ground_truth)

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
            "tiered": tiered,
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
