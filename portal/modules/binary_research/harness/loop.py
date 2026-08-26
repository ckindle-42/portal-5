"""The binary research agent loop. Keeps calling the model until the harness says done."""

from __future__ import annotations

import logging
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import llm as llm_mod
from .llm import LLMConfig
from .policy import Policy
from .re_client import REClient
from .tools import get_schemas, run_tool
from .verifiers import run_all as run_verifiers
from .workspace import TraceLog, snapshot

logger = logging.getLogger(__name__)


@dataclass
class Budget:
    max_turns: int = 80
    max_tool_calls: int = 200
    max_repeat_same_call: int = 3
    _turns: int = field(default=0, init=False)
    _tool_calls: int = field(default=0, init=False)
    _call_tracker: Counter = field(default_factory=Counter, init=False)

    def ok(self) -> bool:
        return self._turns < self.max_turns and self._tool_calls < self.max_tool_calls

    def tick_turn(self) -> None:
        self._turns += 1

    def tick_tool(self, argv: str, output_hash: int) -> None:
        self._tool_calls += 1
        self._call_tracker[(argv, output_hash)] += 1

    def is_stuck(self, argv: str, output_hash: int) -> bool:
        return self._call_tracker.get((argv, output_hash), 0) >= self.max_repeat_same_call

    @property
    def summary(self) -> str:
        return (
            f"turns={self._turns}/{self.max_turns}, tools={self._tool_calls}/{self.max_tool_calls}"
        )


@dataclass
class LoopResult:
    outcome: str
    turns: int
    tool_calls: int
    report_path: Path | None = None
    error: str | None = None


def _build_system_prompt(skill_text: str, ws_snap: str, base_prompt: str | None = None) -> str:
    parts: list[str] = []
    if base_prompt:
        parts.append(base_prompt)
    else:
        parts.append(
            "You are a research agent inside a harness. The model weights behind you may\n"
            "change; follow the harness rules anyway.\n\n"
            "Tools: read, write, edit, bash.\n"
            "- bash target='container' (default) runs inside the RE toolchain: radare2,\n"
            "  rizin, binwalk, unblob, readelf, objdump, nm, strings, yara, ssdeep, and\n"
            "  python3 with lief/capstone/pefile. Use this for ELF/PE/firmware/generic.\n"
            "- bash target='host' runs on the macOS host for Mach-O tools (otool, codesign,\n"
            "  lipo). Only available if the operator enabled it.\n\n"
            "Rules:\n"
            "- Inventory before hypothesizing.\n"
            "- Keep 00_inventory.md, 01_hypotheses.md, 03_model.md current.\n"
            "- Put raw excerpts in 02_evidence/. Do not dump entire binaries into markdown.\n"
            "- Prefer the cheapest experiment that can kill the leading hypothesis.\n"
            "- A single passing verifier is not done. PARTIAL PASS means continue.\n"
            "- Do not execute files under artifacts/ unless policy is relaxed.\n"
            "- Deliverable is 05_report.md: architecture, evidence pointers, residual uncertainty.\n"
            "- Describe mechanisms. Do not produce circumvention or exploit code."
        )
    if skill_text:
        parts.append(f"\n--- SKILL ---\n{skill_text}")
    if ws_snap:
        parts.append(f"\n--- WORKSPACE STATE ---\n{ws_snap}")
    return "\n\n".join(parts)


def run(
    *,
    llm_config: LLMConfig,
    job_dir: Path,
    goal: str,
    policy: Policy,
    budget: Budget,
    re_client: REClient,
    project: str,
    skill_text: str = "",
    base_prompt: str | None = None,
    progress_callback: Any | None = None,
) -> LoopResult:
    trace = TraceLog(job_dir)
    tool_schemas = get_schemas()
    transcript: list[dict] = [
        {
            "role": "system",
            "content": _build_system_prompt(skill_text, snapshot(job_dir), base_prompt),
        },
        {"role": "user", "content": goal},
    ]
    trace.log("loop_start", {"goal": goal, "model": llm_config.model})

    while budget.ok():
        budget.tick_turn()
        transcript[0] = {
            "role": "system",
            "content": _build_system_prompt(skill_text, snapshot(job_dir), base_prompt),
        }

        try:
            response = llm_mod.complete(llm_config, transcript, tools=tool_schemas)
        except Exception as exc:  # noqa: BLE001
            logger.error("LLM call failed: %s", exc)
            trace.log("llm_error", {"error": str(exc)})
            return LoopResult("error", budget._turns, budget._tool_calls, error=str(exc))

        trace.log(
            "model_turn",
            {
                "turn": budget._turns,
                "content": response.content,
                "tool_calls": [
                    {"name": tc.name, "args": tc.arguments} for tc in response.tool_calls
                ],
                "usage": response.usage,
            },
        )

        assistant_msg: dict[str, Any] = {"role": "assistant"}
        if response.content:
            assistant_msg["content"] = response.content
        if response.has_tool_calls:
            assistant_msg["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.name, "arguments": str(tc.arguments)},
                }
                for tc in response.tool_calls
            ]
        transcript.append(assistant_msg)

        if response.has_tool_calls:
            for tc in response.tool_calls:
                result = run_tool(
                    policy, tc.name, tc.arguments, re_client=re_client, project=project
                )
                budget.tick_tool(f"{tc.name}:{tc.arguments}", hash(result))
                trace.log(
                    "tool_call", {"tool": tc.name, "args": tc.arguments, "result_len": len(result)}
                )
                transcript.append({"role": "tool", "tool_call_id": tc.id, "content": result})

                argv_key = f"{tc.name}:{tc.arguments}"
                if budget.is_stuck(argv_key, hash(result)):
                    transcript.append(
                        {
                            "role": "system",
                            "content": (
                                "SYSTEM: You have run the same command with the same output "
                                f"{budget.max_repeat_same_call} times. Change your approach."
                            ),
                        }
                    )
                    trace.log("stuck_detected", {"tool": tc.name, "args": tc.arguments})

            if progress_callback:
                progress_callback(
                    budget._turns, budget.summary, f"tools: {len(response.tool_calls)}"
                )
            continue

        verdict = run_verifiers(job_dir)
        trace.log("verdict", {"label": verdict.label, "details": str(verdict)})

        if verdict.all_pass:
            trace.log(
                "loop_end",
                {"outcome": "completed", "turns": budget._turns, "tool_calls": budget._tool_calls},
            )
            report = job_dir / "05_report.md"
            if progress_callback:
                progress_callback(budget._turns, budget.summary, "ALL PASS — complete")
            return LoopResult(
                "completed",
                budget._turns,
                budget._tool_calls,
                report_path=report if report.exists() else None,
            )

        transcript.append({"role": "system", "content": str(verdict)})
        if progress_callback:
            progress_callback(budget._turns, budget.summary, f"verdict: {verdict.label}")

    trace.log(
        "loop_end",
        {"outcome": "budget_exhausted", "turns": budget._turns, "tool_calls": budget._tool_calls},
    )
    report = job_dir / "05_report.md"
    return LoopResult(
        "budget_exhausted",
        budget._turns,
        budget._tool_calls,
        report_path=report if report.exists() else None,
    )
