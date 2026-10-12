from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path
from typing import Any

import httpx
import jinja2

REPO = Path(__file__).resolve().parent.parent

from portal.platform.inference.ollama_native import to_native_request

RESULTS = REPO / "tests/benchmarks/results/saluki_spike"
RECEIPT = RESULTS / "p4_rule5_reverify.json"
RENDERED = RESULTS / "rule5_reverify_rendered"
WFE_DEBUG = RESULTS / "wfe/debug/portal5_underdog-saluki-27b_iq2-mix-ctx32k.debug.jsonl"
TEMPLATES = {
    "saluki": RESULTS / "Underdog-Saluki-27B-1.0-IQ2-mix.gguf.chat_template.jinja",
    "incumbent": RESULTS
    / "sha256-322e194ff79741c7baa497c240f677f54b201b0efab44ca8e50f122b39123482.chat_template.jinja",
}

OLLAMA = "http://localhost:11434"
SALUKI = "portal5/underdog-saluki-27b:iq2-mix-ctx32k"
INCUMBENT = "hf.co/unsloth/Qwen3.8-27B-GGUF:Q4_K_M-ctx32k"
MAX_TURNS = 6
MAX_TOKENS = 8192
SEEDS = [1000, 1001, 1002, 1003, 1004]
CLAUSE_MARK = "Reply with a single JSON object"
THINK_BLOCK = "<think>\n\n</think>\n\n"

LANE = {"temperature": 0.3, "top_p": 0.95, "top_k": 20, "min_p": 0.0, "repeat_penalty": 1.1}
CARD = {"temperature": 0.6, "top_p": 0.95, "top_k": 20, "min_p": 0.0, "repeat_penalty": 1.0}


def _cell(
    model: str, tmpl: str, sampling: dict[str, Any], think: bool, clause: bool, system: str = ""
) -> dict[str, Any]:
    cell: dict[str, Any] = {
        "model": model,
        "tmpl": tmpl,
        "sampling": sampling,
        "think": think,
        "clause": clause,
    }
    if system:
        cell["system"] = system
    return cell


CELLS: dict[str, dict[str, Any]] = {
    "S1": _cell(SALUKI, "saluki", LANE, False, True),
    "S2": _cell(SALUKI, "saluki", {**LANE, "repeat_penalty": 1.0}, False, True),
    "S3": _cell(SALUKI, "saluki", CARD, False, True),
    "S4": _cell(SALUKI, "saluki", CARD, True, True),
    "S5": _cell(SALUKI, "saluki", LANE, False, False),
    "I1": _cell(INCUMBENT, "incumbent", LANE, False, True),
    "I2": _cell(INCUMBENT, "incumbent", LANE, False, False),
    "S6": _cell(SALUKI, "saluki", LANE, False, True, system="consistent"),
}

PACKET = {
    "governing_refs": {
        "CIP-009-6 R1 Part 1.1": "Recovery plans shall include the conditions for activation."
    },
    "governing_text": "Recovery plans shall include the conditions for activation of the recovery plan.",
    "candidate_text": "Our recovery plan documents the conditions for activation and is reviewed annually.",
    "premises": ["The entity classifies its BES Cyber Systems as high impact."],
}

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "file_read",
            "description": "Read a file from the working directory.",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
        },
    }
]


def load_wfe_texts() -> tuple[str, str]:
    for line in WFE_DEBUG.open():
        row = json.loads(line)
        if row.get("workspace") == "auto-compliance" and CLAUSE_MARK in row.get("instruction", ""):
            return row["system_prompt"], row["instruction"]
    raise SystemExit(f"no auto-compliance row with the JSON clause in {WFE_DEBUG}")


SYSTEM, USER_WITH = load_wfe_texts()
USER_WITHOUT = USER_WITH[: USER_WITH.index(CLAUSE_MARK)].strip()

SYSTEM_TOOL_TAIL = "PRIMARY SOURCES:"
assert SYSTEM.count(SYSTEM_TOOL_TAIL) == 1
SYSTEM_CONSISTENT = SYSTEM[: SYSTEM.index(SYSTEM_TOOL_TAIL)].rstrip() + "\n"


def read_tool(workdir: Path, args: dict[str, Any]) -> str:
    path = str(args.get("path", ""))
    target = workdir / path
    if path == "packet.json" and target.is_file():
        return target.read_text()
    return f"error: {path} not found in working directory"


def parse_json_reply(text: str) -> dict[str, Any] | None:
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        obj = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None
    if not isinstance(obj, dict):
        return None
    return obj if {"determination", "cited_refs", "rationale"} <= obj.keys() else None


def chat_body(cell: dict[str, Any], seed: int, messages: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "model": cell["model"],
        "messages": messages,
        "tools": TOOLS,
        "stream": False,
        "max_tokens": MAX_TOKENS,
        "seed": seed,
        "think": cell["think"],
        **cell["sampling"],
    }


def post_chat(cell: dict[str, Any], body: dict[str, Any]) -> dict[str, Any]:
    native = to_native_request(body, can_think=True, renderer="")
    r = httpx.post(f"{OLLAMA}/api/chat", json=native, timeout=900)
    r.raise_for_status()
    return r.json()


def unload(model: str) -> None:
    httpx.post(f"{OLLAMA}/api/generate", json={"model": model, "keep_alive": 0}, timeout=120)


def to_template_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for m in messages:
        if m["role"] == "assistant" and m.get("tool_calls"):
            calls = [
                {
                    "type": "function",
                    "function": {
                        "name": c["function"]["name"],
                        "arguments": json.loads(c["function"]["arguments"]),
                    },
                }
                for c in m["tool_calls"]
            ]
            out.append({"role": "assistant", "content": m.get("content", ""), "tool_calls": calls})
        else:
            out.append(dict(m))
    return out


def official_render(tmpl: str, messages: list[dict[str, Any]], think: bool) -> str:
    source = TEMPLATES[tmpl].read_text()
    env = jinja2.Environment(
        undefined=jinja2.StrictUndefined, trim_blocks=False, lstrip_blocks=False
    )
    env.globals["raise_exception"] = lambda msg: (_ for _ in ()).throw(ValueError(msg))
    template = env.from_string(source)
    return template.render(
        messages=to_template_messages(messages),
        tools=TOOLS,
        add_generation_prompt=True,
        enable_thinking=think,
    )


def raw_prompt_tokens(model: str, rendered: str) -> int:
    r = httpx.post(
        f"{OLLAMA}/api/generate",
        json={
            "model": model,
            "prompt": rendered,
            "raw": True,
            "stream": False,
            "options": {"num_predict": 0},
        },
        timeout=900,
    )
    r.raise_for_status()
    return int(r.json()["prompt_eval_count"])


def capture_audit(
    cell: dict[str, Any], messages: list[dict[str, Any]], data: dict[str, Any]
) -> dict[str, Any]:
    think = bool(cell["think"])
    rendered = official_render(cell["tmpl"], messages, think)
    audit: dict[str, Any] = {
        "engine_prompt_tokens": data.get("prompt_eval_count"),
        "official_render_tokens": raw_prompt_tokens(cell["model"], rendered),
        "official_render_tokens_rstrip": raw_prompt_tokens(cell["model"], rendered.rstrip()),
        "think_flag_sent": think,
        "think_block_in_render": THINK_BLOCK in rendered[-200:],
    }
    RENDERED.mkdir(parents=True, exist_ok=True)
    flags = f"{'think' if think else 'nothink'}_{'clause' if cell['clause'] else 'noclause'}"
    name = f"{cell['model'].split(':')[-1]}_{flags}.txt"
    (RENDERED / name).write_text(rendered)
    audit["rendered_file"] = str(Path("rule5_reverify_rendered") / name)
    return audit


def run_one(cell: dict[str, Any], seed: int, workdir: Path, capture: bool) -> dict[str, Any]:
    user = USER_WITH if cell["clause"] else USER_WITHOUT
    system = SYSTEM_CONSISTENT if cell.get("system") == "consistent" else SYSTEM
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
    turns: list[dict[str, Any]] = []
    audit: dict[str, Any] | None = None
    outcome = "loop"
    final_text = ""
    for t in range(MAX_TURNS):
        data = post_chat(cell, chat_body(cell, seed, messages))
        msg = data.get("message", {})
        calls = msg.get("tool_calls") or []
        turns.append(
            {
                "turn": t,
                "prompt_eval_count": data.get("prompt_eval_count"),
                "eval_count": data.get("eval_count"),
                "done_reason": data.get("done_reason"),
                "tool_calls": [c["function"]["name"] for c in calls],
                "tool_args": [c["function"].get("arguments") or {} for c in calls],
                "content_head": (msg.get("content") or "")[:200],
                "thinking_chars": len(msg.get("thinking") or ""),
            }
        )
        if capture and t == 1:
            audit = capture_audit(cell, messages, data)
        if not calls:
            final_text = msg.get("content") or ""
            outcome = "answered"
            break
        messages.append(
            {
                "role": "assistant",
                "content": msg.get("content") or "",
                "tool_calls": [
                    {
                        "id": f"c{t}_{i}",
                        "type": "function",
                        "function": {
                            "name": c["function"]["name"],
                            "arguments": json.dumps(c["function"].get("arguments") or {}),
                        },
                    }
                    for i, c in enumerate(calls)
                ],
            }
        )
        for i, c in enumerate(calls):
            result = read_tool(workdir, c["function"].get("arguments") or {})
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": f"c{t}_{i}",
                    "name": c["function"]["name"],
                    "content": result,
                }
            )
    if outcome == "answered" and cell["clause"]:
        outcome = "answered_json" if parse_json_reply(final_text) else "answered_malformed"
    return {
        "seed": seed,
        "outcome": outcome,
        "turns_used": len(turns),
        "final_head": final_text[:300],
        "turns": turns,
        "audit": audit,
    }


def run_cell(
    name: str, cell: dict[str, Any], audit_only: bool
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    runs: list[dict[str, Any]] = []
    audit: dict[str, Any] | None = None
    seeds = SEEDS[:1] if audit_only else SEEDS
    for seed in seeds:
        with tempfile.TemporaryDirectory() as tmp:
            workdir = Path(tmp)
            (workdir / "packet.json").write_text(json.dumps(PACKET, indent=1))
            run = run_one(cell, seed, workdir, capture=(seed == SEEDS[0]))
        if run["audit"] is not None:
            audit = run.pop("audit")
        runs.append(run)
        print(f"{name} seed={seed} -> {run['outcome']} turns={run['turns_used']}", flush=True)
    unload(cell["model"])
    counts: dict[str, int] = {}
    for r in runs:
        counts[r["outcome"]] = counts.get(r["outcome"], 0) + 1
    loops = counts.get("loop", 0)
    summary = {"n": len(runs), "loop": loops, "counts": counts, "runs": runs}
    return summary, audit


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cells", help="comma list, e.g. S1,I1 (default: all)")
    ap.add_argument("--audit-only", action="store_true", help="seed 1000 per cell only (Step 0)")
    ap.add_argument(
        "--seeds",
        type=int,
        default=len(SEEDS),
        help="seeds per cell, taken from the front of SEEDS",
    )
    args = ap.parse_args()
    SEEDS[:] = SEEDS[: args.seeds]
    names = args.cells.split(",") if args.cells else list(CELLS)

    receipt = json.loads(RECEIPT.read_text())
    cells_out = receipt.get("cells", {})
    audit_out = receipt.get("step0_delivery_audit", {})
    for name in names:
        summary, audit = run_cell(name, CELLS[name], args.audit_only)
        summary["config"] = {k: v for k, v in CELLS[name].items() if k != "tmpl"} | {
            "template": CELLS[name]["tmpl"]
        }
        cells_out[name] = summary
        if audit is not None:
            audit_out[name] = audit
        receipt["cells"] = cells_out
        receipt["step0_delivery_audit"] = audit_out
        RECEIPT.write_text(json.dumps(receipt, indent=2) + "\n")
        print(
            f"{name}: loop {summary['loop']}/{summary['n']} counts={summary['counts']}", flush=True
        )


if __name__ == "__main__":
    main()
