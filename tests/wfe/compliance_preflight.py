#!/usr/bin/env python3
"""The settings the transport REQUESTS, proven to be the settings Ollama APPLIES.

TASK_COMPLIANCE_PROVE_CIP_007_V1 §P0. ``settings_audit`` is config and
metadata; it makes the request path no promises. This is the request path: for
each candidate seat, one real call carrying the largest case's material, with
every number read back from the runner rather than from the request.

What it settles, and why each one can invalidate a run silently:

* **the ceiling** — a baked ``num_ctx`` is a DEFAULT, not a limit. ``/api/chat``
  honours a larger request-time value; ``/v1`` does not. Which of those a path
  gets decides whether a 32k tag can hold a 40k thread.
* **truncation** — measured, not assumed. On Ollama 0.34.0 an oversized prompt
  is HTTP 400 ``exceed_context_size_error``, not a front-truncated prompt. The
  guard is therefore "did the runner refuse", not "did it quietly cut".
* **tools and think** — the two settings the reading path depends on and the two
  the shared audit's probes did not cover until this task added them.
* **the template** — a sha, pinned before the first case. A run whose template
  moved underneath it is not comparable to the runs before it, and the sha is
  the only way to know it happened.
* **chars per token** — OBSERVED, from ``prompt_eval_count``, because the
  constant the assembly sizes windows with is an estimate and an estimate is
  only safe in one direction.

Usage:
  uv run python -m tests.wfe.compliance_preflight --json
  uv run python -m tests.wfe.compliance_preflight --seat <tag> [--seat <tag>]
"""

from __future__ import annotations

import argparse
import json
import subprocess
import time
import urllib.request
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
OLLAMA = "http://localhost:11434"

#: The loop's own bounds, which are what the window has to hold. Kept beside
#: the check that uses them so the two cannot drift: `reader.read` runs at most
#: `max_steps` turns and `reading_tools.dispatch` bounds every tool result at
#: `max_chars`, so the tool results alone can be `MAX_STEPS * MAX_CHARS`
#: characters -- the dominant term, and the one the first version of this check
#: left out entirely.
MAX_STEPS = 12
TOOL_RESULT_MAX_CHARS = 12000

#: The CIP-007-6 requirement whose population is largest, which is what the
#: ceiling has to hold. Derived, never hardcoded in prose: --ref overrides it and
#: `--survey` prints the whole standard's populations so the choice is checkable.
LARGEST_REF = "CIP-007-6 R5"


def _get(path: str, timeout: int = 10) -> dict[str, Any]:
    with urllib.request.urlopen(f"{OLLAMA}{path}", timeout=timeout) as response:  # noqa: S310
        return dict(json.load(response))


def free_memory_mb() -> int:
    """Free plus inactive pages, which is what a model load can actually take."""
    try:
        out = subprocess.check_output(["vm_stat"], text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return 0
    page = 4096
    counts: dict[str, int] = {}
    for line in out.splitlines():
        if "page size of" in line:
            page = int(line.split("page size of")[1].split("bytes")[0].strip())
        if ":" in line:
            key, _, value = line.partition(":")
            digits = value.strip().rstrip(".")
            if digits.isdigit():
                counts[key.strip()] = int(digits)
    pages = counts.get("Pages free", 0) + counts.get("Pages inactive", 0)
    return pages * page // (1024 * 1024)


def populations(standard: str = "CIP-007-6") -> list[dict[str, Any]]:
    """Every requirement identity in the standard with the size of its population.

    The ``chars`` column is what §P0.6 sizes the ceiling against, and the
    operator count is what decides whether an identity can carry a posture case
    at all. Note the key: ``population()`` returns ``sections``/``section_ids``
    and has never returned an ``eligible`` list — reading one produces an empty
    survey that looks like an empty corpus.
    """
    from portal.modules.compliance.core import requirement_scope
    from portal.modules.compliance.core.repository import Repository
    from portal.modules.compliance.core.section_index import resolve_sections

    repo = Repository()
    try:
        parts = [
            str(row[0])
            for row in repo._conn.execute(
                "SELECT node_id FROM requirement_nodes "
                "WHERE standard_revision_id = ? AND part <> '' ORDER BY node_id",
                (standard,),
            ).fetchall()
        ]
        requirements = sorted({p.split(" Part ")[0] for p in parts})
        rows: list[dict[str, Any]] = []
        for ref in [*requirements, *parts]:
            pop = requirement_scope.population(repo, ref)
            sections = pop["sections"]
            resolved = resolve_sections(repo, list(sections))
            rows.append(
                {
                    "ref": ref,
                    "regulatory": sum(1 for e in sections.values() if e["side"] == "regulatory"),
                    "operator": sum(1 for e in sections.values() if e["side"] == "operator"),
                    "operator_notes": sum(
                        1 for e in sections.values() if e["side"] == "operator_note"
                    ),
                    "link_statuses": sorted(
                        {
                            str(e.get("link_status", ""))
                            for e in sections.values()
                            if e["side"] == "operator"
                        }
                    ),
                    "chars": sum(len(str(v.get("text") or "")) for v in resolved.values()),
                    "population_method": pop["population_method"],
                }
            )
        return rows
    finally:
        repo.close()


def first_turn_thread(ref: str, *, budget_tokens: int = 12000) -> tuple[list[dict[str, Any]], str]:
    """Exactly what the reader ships on its FIRST call, and nothing else.

    Rebuilt from the reader's own pieces rather than approximated, because the
    thing being measured is whether the window holds what is actually sent: the
    system prompt, the assembly seed, both recorded acquisition payloads, the
    unread-population disclosure and the question.
    """
    from portal.modules.compliance.core import reader, requirement_scope
    from portal.modules.compliance.core.notes import notes_for
    from portal.modules.compliance.core.reading_assembly import assemble
    from portal.modules.compliance.core.repository import Repository

    repo = Repository()
    try:
        context = assemble(repo, ref, budget_tokens=budget_tokens, include=["requirement"])
        context["operator_notes"] = [
            note
            for identity in requirement_scope.resolve(repo, ref).refs
            for note in notes_for(repo, identity)
        ]
        seed = reader._render_material(context)
        trace: list[dict[str, Any]] = []
        bootstrap, acquired = reader._acquire(
            repo, context["ref"], max_chars=budget_tokens, trace=trace
        )
        examined = {
            str(section.get("section_id", ""))
            for component in context.get("components", [])
            for section in component.get("sections", [])
            if section.get("section_id")
        }
        examined |= acquired["examined"]
        population = requirement_scope.population(repo, context["ref"])
        outstanding = reader._outstanding(population, examined)
        system_prompt, _, _ = reader.load_prompt()
        thread = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": seed},
            *bootstrap,
            *([{"role": "user", "content": outstanding}] if outstanding else []),
            {
                "role": "user",
                "content": (
                    "The analyst asks:\n\nWhat does this requirement oblige us to do, "
                    "and what do our own procedures say about it?"
                ),
            },
        ]
        return thread, context["ref"]
    finally:
        repo.close()


def _thread_chars(thread: list[dict[str, Any]]) -> int:
    return sum(len(str(m.get("content", "") or "")) for m in thread)


def applied_versus_requested(seat: str, ref: str, num_ctx: int) -> dict[str, Any]:
    """One real call with the largest case's material. Every row is read back."""
    from portal.modules.compliance.core.reading_tools import TOOL_SCHEMAS
    from portal.modules.compliance.core.reading_transport import (
        DEFAULT_ANSWER_BUDGET,
        DEFAULT_REASONING_ALLOWANCE,
        ContextCeilingError,
        chat,
        seat_ceiling,
    )

    thread, resolved_ref = first_turn_thread(ref)
    chars = _thread_chars(thread)
    row: dict[str, Any] = {
        "seat": seat,
        "ref": resolved_ref,
        "material_chars": chars,
        "num_ctx_requested": num_ctx,
        "seat_ceiling": seat_ceiling(seat),
        "answer_budget": DEFAULT_ANSWER_BUDGET,
        "reasoning_allowance": DEFAULT_REASONING_ALLOWANCE,
    }
    started = time.time()
    try:
        result = chat(
            seat,
            messages=thread,
            tools=TOOL_SCHEMAS,
            answer_budget=DEFAULT_ANSWER_BUDGET,
            fmt=None,
            think=False,
            num_ctx=num_ctx,
            timeout=3600,
        )
    except ContextCeilingError as exc:
        row.update(error=str(exc), blocks=True)
        return row

    prompt_tokens = int(result.get("prompt_eval_count") or 0)
    generated = int(result.get("eval_count") or 0)
    row.update(
        elapsed_s=round(time.time() - started, 1),
        num_ctx_applied=result.get("num_ctx_applied"),
        temperature_applied=result.get("temperature"),
        prompt_eval_count=prompt_tokens,
        eval_count=generated,
        headroom_tokens=num_ctx - prompt_tokens - generated,
        chars_per_token_observed=round(chars / prompt_tokens, 2) if prompt_tokens else None,
        tool_calls=[
            str((c.get("function") or {}).get("name", "")) for c in (result.tool_calls or [])
        ],
        thinking_chars=len(result.thinking),
        answer_chars=len(result.content),
        transport_stop_reason=result.get("stop_reason"),
    )
    reasons: list[str] = []
    if row["num_ctx_applied"] and row["num_ctx_applied"] != num_ctx:
        reasons.append(
            f"applied num_ctx {row['num_ctx_applied']} != requested {num_ctx}: the runner "
            "did not serve the window that was asked for"
        )
    if row["headroom_tokens"] <= 0:
        reasons.append(f"headroom {row['headroom_tokens']} <= 0: no room to answer")
    if prompt_tokens and prompt_tokens >= num_ctx:
        reasons.append(
            f"prompt_eval_count {prompt_tokens} is at or above the window {num_ctx}: the "
            "prompt did not fit"
        )
    # The ceiling must hold the WORST THREAD THE LOOP CAN BUILD, not the first
    # turn. This check counted `first-turn prompt + answer + reasoning` and
    # reported 41,778 tokens of margin on a seat whose loop then died with an
    # Ollama HTTP 500 after twelve tool calls: it measured one turn and
    # certified a twelve-turn loop. The tool results the loop appends are the
    # dominant term and were simply absent from the sum.
    #
    # The ratio is the OBSERVED one from this very call, never a constant: a
    # character budget divided by too large a ratio under-counts the tokens it
    # becomes, which is how 4.22 (measured on raw corpus text) produced a window
    # that did not fit threads whose real ratio is ~3.0.
    ratio = row.get("chars_per_token_observed") or 3.0
    tool_result_tokens = int(MAX_STEPS * TOOL_RESULT_MAX_CHARS / float(ratio))
    required = (
        prompt_tokens + tool_result_tokens + DEFAULT_ANSWER_BUDGET + DEFAULT_REASONING_ALLOWANCE
    )
    row["worst_case_tool_result_tokens"] = tool_result_tokens
    row["required_tokens"] = required
    row["margin_tokens"] = num_ctx - required
    if row["margin_tokens"] <= 0:
        reasons.append(
            f"the window {num_ctx} does not hold the worst thread this loop can build: the "
            f"first turn is {prompt_tokens} tokens, {MAX_STEPS} tool results bounded at "
            f"{TOOL_RESULT_MAX_CHARS} characters add ~{tool_result_tokens} at the observed "
            f"{ratio} chars/token, and the answer budget ({DEFAULT_ANSWER_BUDGET}) plus the "
            f"reasoning allowance ({DEFAULT_REASONING_ALLOWANCE}) needs {required} in all"
        )
    row["blocks"] = bool(reasons)
    row["block_reasons"] = reasons
    return row


def pin_seat(seat: str, ref: str, num_ctx: int) -> dict[str, Any]:
    """Everything §P0.5 records before the first case runs."""
    from tests.wfe.settings_audit import probe_tag

    probe = probe_tag(seat)
    applied = (
        applied_versus_requested(seat, ref, num_ctx)
        if not probe.get("fail_count")
        else {"seat": seat, "skipped": "probe FAILed; no request-path call attempted"}
    )
    ps = _get("/api/ps")
    go = (
        not probe.get("fail_count")
        and bool(probe.get("tools_probe", {}).get("tools_rendered"))
        and probe.get("think_probe", {}).get("verdict") in {"honored", "refused", "ignored"}
        and not applied.get("blocks")
    )
    no_go: list[str] = []
    if probe.get("fail_count"):
        no_go += [v["detail"] for v in probe.get("violations", []) if v["severity"] == "FAIL"]
    if not probe.get("tools_probe", {}).get("tools_rendered"):
        no_go.append("the tools probe did not return a tool call")
    if probe.get("think_probe", {}).get("verdict") == "unmeasured":
        no_go.append("the think verdict was not measured")
    no_go += list(applied.get("block_reasons") or [])
    if applied.get("error"):
        no_go.append(str(applied["error"]))
    return {
        "seat": seat,
        "template_sha": probe.get("template_sha"),
        "baked_params": probe.get("baked_params"),
        "baked_ctx_from_tag": probe.get("baked_ctx_from_tag"),
        "tools_probe": probe.get("tools_probe"),
        "think_probe": probe.get("think_probe"),
        "audit_violations": probe.get("violations"),
        "applied_versus_requested": applied,
        "ollama_ps": ps.get("models"),
        "free_memory_mb": free_memory_mb(),
        "go": bool(go),
        "no_go_reasons": no_go,
    }


def run(seats: list[str], ref: str = LARGEST_REF, num_ctx: int = 0) -> dict[str, Any]:
    from portal.modules.compliance.core.reading_transport import DEFAULT_NUM_CTX

    window = num_ctx or DEFAULT_NUM_CTX
    survey = populations()
    largest = max(survey, key=lambda r: r["chars"])
    return {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "git_rev": subprocess.check_output(
            ["git", "-C", str(REPO), "rev-parse", "HEAD"], text=True
        ).strip(),
        "ollama_version": _get("/api/version").get("version"),
        "num_ctx_requested": window,
        "reference_ref": ref,
        "largest_population": largest,
        "populations": survey,
        "seats": [pin_seat(seat, ref, window) for seat in seats],
    }


def main() -> int:
    from portal.modules.compliance.core.runtime_config import reading_seat

    parser = argparse.ArgumentParser()
    parser.add_argument("--seat", action="append", default=[])
    parser.add_argument("--ref", default=LARGEST_REF)
    parser.add_argument("--num-ctx", type=int, default=0)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--survey", action="store_true", help="populations only, no model calls")
    args = parser.parse_args()

    if args.survey:
        print(json.dumps(populations(), indent=1))
        return 0

    seats = args.seat or [reading_seat()]
    report = run(seats, ref=args.ref, num_ctx=args.num_ctx)
    if args.json:
        print(json.dumps(report, indent=1))
    else:
        for seat in report["seats"]:
            print(f"{'GO ' if seat['go'] else 'NO-GO'}  {seat['seat']}")
            for reason in seat["no_go_reasons"]:
                print(f"    - {reason}")
    return 0 if all(s["go"] for s in report["seats"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
