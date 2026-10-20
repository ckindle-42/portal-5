#!/usr/bin/env python3
"""Research-task head-to-head probe (TASK-BENCH-FOLLOWUP-001 Part 1B).

Replaces the V1 C4/SWE-diagnosis proxy for Aquila's research-lane decision with
a bench on the actual task: an agentic web_search/web_fetch/synthesis loop
against a fixed, checkable question set, scored on synthesis quality, factual
correctness, and citation grounding. Isolated: writes only to
tests/benchmarks/results/, never touches production workspaces or config.

Usage:
    python3 tests/benchmarks/bench_research_probe.py \
        --candidate portal5/xyz-aquila-mini:q4_k_m-ctx16k \
        --incumbent huihui_ai/tongyi-deepresearch-abliterated:latest-ctx64k \
        --qset tests/benchmarks/fixtures/research_eval_qset.jsonl
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import time
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_ROOT = Path(os.environ.get("PORTAL_DATA_ROOT", str(Path.home() / "AI_Output" / "portal-data")))
RESULTS_DIR = DATA_ROOT / "tests" / "benchmarks" / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

OLLAMA_URL = "http://localhost:11434"
RESEARCH_MCP_URL = "http://localhost:8922"
JUDGE_MODEL = "gemma4:12b-it-qat"

MAX_HOPS = 5
GEN_TIMEOUT_S = 300.0
TOOL_TIMEOUT_S = 30.0

RESEARCH_SYSTEM_PROMPT = (
    "You are a research assistant. Synthesize information from multiple sources. "
    "Distinguish primary from secondary sources. Always acknowledge the limits of "
    "your knowledge."
)

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Search the web for information on a topic.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "The search query"},
                    "num_results": {"type": "integer", "description": "Max results"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_fetch",
            "description": "Fetch and extract readable content from a URL.",
            "parameters": {
                "type": "object",
                "properties": {"url": {"type": "string", "description": "The URL to fetch"}},
                "required": ["url"],
            },
        },
    },
]


@dataclass
class QuestionResult:
    qid: str
    question: str
    checkable: str
    final_answer: str
    hops_used: int
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    searched_or_fetched: list[str] = field(default_factory=list)
    citation_grounding: float = 0.0
    factuality: str = "UNSCORED"
    synthesis_1_5: int = 0
    error: str | None = None
    latency_s: float = 0.0
    answer_source: str = "content"  # N-1: "reasoning" when the answer came from the reasoning field


def _final_answer(msg: dict[str, Any]) -> tuple[str, str]:
    """The answer text and where it came from. Some models (e.g. tongyi-deepresearch) put the
    answer in the reasoning field and leave content empty on the final turn; that fallback is
    kept (so the answer is not scored as blank) and labelled (N-1)."""
    content = msg.get("content") or ""
    if "<tool_call>" in content:
        return "", "text_tool_call"  # N-1: a call written as text is not an answer
    if content:
        return content, "content"
    reasoning = msg.get("reasoning") or ""
    return reasoning, "reasoning" if reasoning else "content"


def _text_call_error(answer_source: str) -> str | None:
    if answer_source == "text_tool_call":
        return "TEXT_TOOL_CALL: the model wrote its tool call as text, not a structured call"
    return None


def _as_str(value: Any) -> str:
    """Tool-call arguments are sometimes malformed (e.g. a list instead of a
    string) — coerce defensively instead of crashing the whole probe run."""
    return value if isinstance(value, str) else json.dumps(value)


def _dispatch_tool(name: str, args: dict[str, Any], client: httpx.Client) -> str:
    try:
        if name == "web_search":
            r = client.post(
                f"{RESEARCH_MCP_URL}/tools/web_search",
                json={"arguments": {"query": _as_str(args.get("query", "")), "num_results": 5}},
                timeout=TOOL_TIMEOUT_S,
            )
        elif name == "web_fetch":
            r = client.post(
                f"{RESEARCH_MCP_URL}/tools/web_fetch",
                json={"arguments": {"url": _as_str(args.get("url", "")), "max_chars": 4000}},
                timeout=TOOL_TIMEOUT_S,
            )
        else:
            return json.dumps({"error": f"unknown tool {name}"})
        r.raise_for_status()
        return r.text
    except Exception as e:
        return json.dumps({"error": f"{type(e).__name__}: {e}"})


def run_agent(
    model: str, question: str, client: httpx.Client, max_hops: int = MAX_HOPS
) -> QuestionResult:
    t0 = time.time()
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": RESEARCH_SYSTEM_PROMPT},
        {"role": "user", "content": question},
    ]
    tool_calls_log: list[dict[str, Any]] = []
    sources: list[str] = []
    hops = 0
    final_answer = ""
    error = None
    answer_source = "content"
    try:
        for hop in range(max_hops + 1):
            hops = hop
            body = {
                "model": model,
                "messages": messages,
                "tools": TOOLS,
                "stream": False,
                "temperature": 0.4,
            }
            r = client.post(f"{OLLAMA_URL}/v1/chat/completions", json=body, timeout=GEN_TIMEOUT_S)
            r.raise_for_status()
            data = r.json()
            msg = data["choices"][0]["message"]
            calls = msg.get("tool_calls") or []
            content = msg.get("content") or ""
            if not calls:
                # Some models (e.g. tongyi-deepresearch) put the answer in a
                # separate reasoning field and leave content empty on the
                # final turn instead of promoting it — fall back so the
                # answer isn't scored as a blank response, and say so.
                final_answer, answer_source = _final_answer(msg)
                break
            messages.append(
                {
                    "role": "assistant",
                    "content": content,
                    "tool_calls": calls,
                }
            )
            if hop == max_hops:
                # Budget exhausted mid tool-call: force a final synthesis turn.
                messages.append(
                    {
                        "role": "user",
                        "content": "Stop researching now and give your final synthesized answer with citations based on what you've found so far.",
                    }
                )
                body["messages"] = messages
                body["tools"] = []
                r2 = client.post(
                    f"{OLLAMA_URL}/v1/chat/completions", json=body, timeout=GEN_TIMEOUT_S
                )
                r2.raise_for_status()
                final_msg = r2.json()["choices"][0]["message"]
                final_answer, answer_source = _final_answer(final_msg)
                break
            for tc in calls:
                fn = tc.get("function", {})
                name = fn.get("name", "")
                raw_args = fn.get("arguments", {})
                args = raw_args if isinstance(raw_args, dict) else json.loads(raw_args or "{}")
                result_text = _dispatch_tool(name, args, client)
                tool_calls_log.append({"name": name, "args": args})
                if name == "web_search":
                    sources.append(_as_str(args.get("query", "")))
                elif name == "web_fetch":
                    sources.append(_as_str(args.get("url", "")))
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.get("id", f"call_{len(tool_calls_log)}"),
                        "content": result_text[:6000],
                    }
                )
    except Exception as e:
        error = f"{type(e).__name__}: {e}"

    grounded = 0
    fetched_urls = [s for s in sources if s.startswith("http")]
    for u in fetched_urls:
        domain = u.split("/")[2] if "/" in u.split("://", 1)[-1] else u
        if domain in final_answer or u in final_answer:
            grounded += 1
    grounding_score = grounded / len(fetched_urls) if fetched_urls else 0.0

    return QuestionResult(
        qid="",
        question=question,
        checkable="",
        final_answer=final_answer,
        hops_used=hops,
        tool_calls=tool_calls_log,
        searched_or_fetched=sources,
        citation_grounding=round(grounding_score, 2),
        error=error or _text_call_error(answer_source),
        latency_s=round(time.time() - t0, 1),
        answer_source=answer_source,
    )


def judge_factuality_and_synthesis(
    question: str, checkable: str, answer: str, client: httpx.Client
) -> tuple[str, int]:
    prompt = f"""You are grading a research assistant's answer for factual correctness and synthesis quality.

QUESTION: {question}

REFERENCE (ground truth facts that must be reflected, paraphrase is fine): {checkable}

CANDIDATE ANSWER: {answer if answer else "(empty / no answer produced)"}

Score two things:
1. FACTUALITY: does the candidate answer's substantive claims match the reference? Answer exactly one of PASS, PARTIAL, FAIL.
2. SYNTHESIS: rate 1-5 how well the answer synthesizes/organizes information (not just factuality) - 1=incoherent or empty, 5=clear, well-structured, appropriately hedged.

Respond with EXACTLY this format, nothing else:
FACTUALITY: <PASS|PARTIAL|FAIL>
SYNTHESIS: <1-5>"""
    try:
        r = client.post(
            f"{OLLAMA_URL}/v1/chat/completions",
            json={
                "model": JUDGE_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.0,
                "stream": False,
            },
            timeout=120.0,
        )
        r.raise_for_status()
        text = r.json()["choices"][0]["message"].get("content", "")
        factuality = "UNSCORED"
        synthesis = 0
        for line in text.splitlines():
            line = line.strip()
            if line.upper().startswith("FACTUALITY:"):
                val = line.split(":", 1)[1].strip().upper()
                if val in ("PASS", "PARTIAL", "FAIL"):
                    factuality = val
            elif line.upper().startswith("SYNTHESIS:"):
                digits = "".join(c for c in line.split(":", 1)[1] if c.isdigit())
                if digits:
                    synthesis = min(5, max(1, int(digits[0])))
        return factuality, synthesis
    except Exception as e:
        return f"JUDGE_ERROR:{type(e).__name__}", 0


def unload_model(model: str, client: httpx.Client) -> None:
    with contextlib.suppress(Exception):
        client.post(
            f"{OLLAMA_URL}/api/generate",
            json={"model": model, "keep_alive": 0},
            timeout=30.0,
        )


def run_arm(model: str, qset: list[dict[str, Any]], client: httpx.Client) -> list[QuestionResult]:
    results = []
    for q in qset:
        res = run_agent(model, q["question"], client)
        res.qid = q["id"]
        res.checkable = q["checkable"]
        factuality, synthesis = judge_factuality_and_synthesis(
            q["question"], q["checkable"], res.final_answer, client
        )
        if res.error or factuality.startswith("JUDGE_ERROR"):
            factuality = "ERROR"  # N-1: a failed run or judge is not a FAIL; it is unscored
        res.factuality = factuality
        res.synthesis_1_5 = synthesis
        results.append(res)
        print(
            f"    [{q['id']}] hops={res.hops_used} factuality={factuality} "
            f"synth={synthesis} grounding={res.citation_grounding} "
            f"latency={res.latency_s}s"
        )
    unload_model(model, client)
    return results


# N-1: a WIN/INCUMBENT verdict needs this many scored items per arm; below it the
# verdict is INSUFFICIENT_N. The qset has 10 items, so a 2/2 or 10/10 result is not a verdict.
MIN_SCORED_FOR_VERDICT = 30


def summarize(results: list[QuestionResult]) -> dict[str, Any]:
    """Rates are over SCORED items (PASS/PARTIAL/FAIL). ERROR and unscored items are excluded
    from the denominator and counted separately (N-1)."""
    scored = [r for r in results if r.factuality in ("PASS", "PARTIAL", "FAIL")]
    n_scored = len(scored) or 1
    n = len(results) or 1
    pass_n = sum(1 for r in scored if r.factuality == "PASS")
    partial_n = sum(1 for r in scored if r.factuality == "PARTIAL")
    fail_n = sum(1 for r in scored if r.factuality == "FAIL")
    return {
        "n": len(results),
        "scored": len(scored),
        "factuality_pass": pass_n,
        "factuality_partial": partial_n,
        "factuality_fail": fail_n,
        "factuality_pass_rate": round(pass_n / n_scored, 2),
        "avg_synthesis_1_5": round(sum(r.synthesis_1_5 for r in scored) / n_scored, 2),
        "avg_citation_grounding": round(sum(r.citation_grounding for r in results) / n, 2),
        "avg_latency_s": round(sum(r.latency_s for r in results) / n, 1),
        "errors": sum(1 for r in results if r.factuality == "ERROR"),
        "reasoning_fallback": sum(1 for r in results if r.answer_source == "reasoning"),
    }


def verdict(candidate: dict[str, Any], incumbent: dict[str, Any]) -> str:
    """CANDIDATE_WINS / TIE / INCUMBENT_WINS, or INSUFFICIENT_N below MIN_SCORED_FOR_VERDICT."""
    if min(candidate["scored"], incumbent["scored"]) < MIN_SCORED_FOR_VERDICT:
        return "INSUFFICIENT_N"
    cp, ip = candidate["factuality_pass_rate"], incumbent["factuality_pass_rate"]
    cs, is_ = candidate["avg_synthesis_1_5"], incumbent["avg_synthesis_1_5"]
    if cp > ip or (cp == ip and cs > is_):
        return "CANDIDATE_WINS"
    if cp == ip and cs == is_:
        return "TIE"
    return "INCUMBENT_WINS"


def main() -> int:
    ap = argparse.ArgumentParser(description="Research-task head-to-head probe")
    ap.add_argument("--candidate", required=True, help="Candidate model tag")
    ap.add_argument("--incumbent", required=True, help="Incumbent model tag")
    ap.add_argument("--qset", required=True, help="Path to research_eval_qset.jsonl")
    ap.add_argument("--output", default=None, help="Output JSON path")
    args = ap.parse_args()

    qset = [json.loads(line) for line in Path(args.qset).read_text().splitlines() if line.strip()]

    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    out_path = Path(args.output) if args.output else RESULTS_DIR / f"research_probe_{ts}.json"

    with httpx.Client() as client:
        print(f"== Candidate: {args.candidate} ==")
        candidate_results = run_arm(args.candidate, qset, client)
        print(f"== Incumbent: {args.incumbent} ==")
        incumbent_results = run_arm(args.incumbent, qset, client)

    candidate_summary = summarize(candidate_results)
    incumbent_summary = summarize(incumbent_results)

    result_verdict = verdict(candidate_summary, incumbent_summary)

    payload = {
        "generated_at": ts,
        "candidate": args.candidate,
        "incumbent": args.incumbent,
        "qset_path": args.qset,
        "candidate_summary": candidate_summary,
        "incumbent_summary": incumbent_summary,
        "verdict": result_verdict,
        "candidate_results": [asdict(r) for r in candidate_results],
        "incumbent_results": [asdict(r) for r in incumbent_results],
    }
    out_path.write_text(json.dumps(payload, indent=2))

    print()
    print("=" * 80)
    print(f"Candidate  ({args.candidate}): {candidate_summary}")
    print(f"Incumbent  ({args.incumbent}): {incumbent_summary}")
    print(f"VERDICT: {result_verdict}")
    print(f"Results: {out_path}")
    print("=" * 80)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
