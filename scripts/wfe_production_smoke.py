#!/usr/bin/env python3
"""Production smoke: one real Open WebUI turn per tool a workspace offers.

Drives OWUI :8080 -> pipeline exactly as a user does (the preset's system prompt, native model
id, no evaluation scope), then reads the pipeline's /v1/trace for what was called and how it
ended. Per tool it records: called, tool outcome, answer check, garbage in the answer
(zero-width spaces, raw <tool_call> text, a download link on a read, a refusal), and the turn's
prompt tokens. One empty turn per workspace gives P-4 (prompt tokens against the window).

    uv run python scripts/wfe_production_smoke.py --workspaces auto-documents,auto-coding
    uv run python scripts/wfe_production_smoke.py --md docs/WFE_PRODUCTION_SMOKE_20261017.md

Fixtures are uploaded through OWUI (so they land where a user's would) and removed afterwards;
files the create tools publish are removed too; the memory note is forgotten again.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
OWUI = "http://localhost:8080"
PIPE = "http://localhost:9099"
MEMORY_MCP = f"http://localhost:{os.environ.get('MEMORY_MCP_PORT', '8920')}"
OUTPUT = Path(os.environ.get("AI_OUTPUT_DIR", str(Path.home() / "AI_Output")))
_MEMORY_ID_RE = re.compile(
    r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.I
)
# The remember case's code word. Cleanup also sweeps the memory store by this word: the model
# may store the whole prompt sentence and answer without the tool's id (finding I).
SMOKE_CODE_WORD = "bluefinch"
MEMORY_SWEEP_QUERY = f"smoke test code word {SMOKE_CODE_WORD}"


def env(name: str) -> str:
    if os.environ.get(name):
        return os.environ[name]
    for line in (REPO / ".env").read_text().splitlines():
        k, _, v = line.strip().partition("=")
        if k == name:
            return v.strip().strip("'\"")
    return ""


@dataclass
class Case:
    tool: str
    prompt: str
    expect: str = ""  # regex the answer must match (empty: the tool outcome is the check)
    skip: str = ""  # reason this tool is not called in a smoke
    create: bool = False
    # Production has one KB with zero chunks ('smoketest'): there is nothing to search, so a
    # model that calls kb_list and answers from that empty list is correct (finding F).
    expect_empty_kb: bool = False


CASES: list[Case] = [
    Case("read_word_document", "In smoke_memo.docx, what is the notice period in days?", r"\b37\b"),
    Case("read_excel", "In smoke_budget.xlsx, what is the total of the Cost column?", r"2,?235"),
    Case(
        "read_powerpoint",
        "In smoke_deck.pptx, who is the owner named on the Rollout slide?",
        "Ilse Mott",
    ),
    Case("read_pdf", "In smoke_notes.pdf, what is the vault code?", "5521"),
    Case(
        "create_word_document",
        'Create a Word document titled "Smoke Notes" with a heading "Safety" and a bulleted list with the items "Gloves" and "Helmets".',
        r"https?://|Download",
        create=True,
    ),
    Case(
        "create_excel",
        'Create an Excel workbook titled "Smoke Sheet" with the header row Name | Qty and the rows bolt | 4; nut | 9.',
        r"https?://|Download",
        create=True,
    ),
    Case(
        "create_powerpoint",
        'Create a PowerPoint deck titled "Smoke Deck" with two content slides: slide 1 titled "Intro" with the text "Hello", slide 2 titled "Close" with the text "Bye".',
        r"https?://|Download",
        create=True,
    ),
    Case(
        "web_search",
        "Search the web for the Ollama project and tell me in one sentence what it is.",
    ),
    Case("web_fetch", "Fetch https://example.com and tell me its page heading.", "Example Domain"),
    Case("news_search", "What is the latest news about NVIDIA?"),
    Case("kb_list", "List my knowledge bases."),
    Case(
        "kb_search",
        "Search my knowledge base for compliance and summarize the top result.",
        expect_empty_kb=True,
    ),
    Case(
        "kb_search_all",
        "Search all my knowledge bases for backup and summarize the top result.",
        expect_empty_kb=True,
    ),
    Case(
        "remember",
        f'Remember that the smoke test code word is "{SMOKE_CODE_WORD}". Include the exact id returned by the remember tool in your answer.',
    ),
    Case("recall", "What is the smoke test code word I asked you to remember?", SMOKE_CODE_WORD),
    Case("graph_recall", f'Using your memory graph, what do you know about "{SMOKE_CODE_WORD}"?'),
    Case("neighbors", f'Which entities are related to "{SMOKE_CODE_WORD}" in my memory graph?'),
    Case("entity_timeline", f'Show the timeline of events for the entity "{SMOKE_CODE_WORD}".'),
    Case("execute_python", "Run Python to compute 17*23 and tell me the result.", "391"),
    Case("execute_nodejs", "Use Node.js to compute 6*7 and tell me the result.", r"\b42\b"),
    Case(
        "execute_bash", "Run this in bash and show me the output: echo hello-smoke", "hello-smoke"
    ),
    Case("sandbox_status", "Is the code sandbox available right now?"),
    Case("minimax_status", "What is the status of the music generator?"),
    Case(
        "minimax_generate", "", skip="heavy GPU generation: covered by the music UAT, not a smoke"
    ),
    Case("transcribe_audio", "Transcribe smoke_audio.wav", "portal"),
]

GARBAGE = [
    ("zero-width space", lambda a, c: "​" in a),
    ("raw <tool_call> text", lambda a, c: "<tool_call>" in a),
    (
        "download link on a non-create",
        lambda a, c: (not c.create) and bool(re.search(r"Download:\s", a)),
    ),
    (
        "refusal",
        lambda a, c: bool(
            re.search(r"I (?:can(?:no|')t|am unable|'m unable|don't have the capability)", a)
        ),
    ),
]


def http(url: str, body: dict | None = None, headers: dict | None = None, timeout: int = 900):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json", **(headers or {})}
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310
        return json.load(r)


def owui(path: str, body: dict | None = None, timeout: int = 900):
    return http(f"{OWUI}{path}", body, {"Authorization": f"Bearer {env('OWUI_API_KEY')}"}, timeout)


def pipe(path: str):
    return http(f"{PIPE}{path}", None, {"Authorization": f"Bearer {env('PIPELINE_API_KEY')}"}, 30)


def upload(path: Path) -> str:
    """Upload a fixture through OWUI the way a user does; the file id."""
    boundary = "----smoke" + str(time.time_ns())
    body = (
        (
            f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{path.name}"\r\n'
            "Content-Type: application/octet-stream\r\n\r\n"
        ).encode()
        + path.read_bytes()
        + f"\r\n--{boundary}--\r\n".encode()
    )
    req = urllib.request.Request(
        f"{OWUI}/api/v1/files/",
        data=body,
        headers={
            "Authorization": f"Bearer {env('OWUI_API_KEY')}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
    )
    with urllib.request.urlopen(req, timeout=120) as r:  # noqa: S310
        return json.load(r)["id"]


def delete_file(fid: str) -> None:
    req = urllib.request.Request(
        f"{OWUI}/api/v1/files/{fid}",
        method="DELETE",
        headers={"Authorization": f"Bearer {env('OWUI_API_KEY')}"},
    )
    try:
        urllib.request.urlopen(req, timeout=30)  # noqa: S310
    except Exception:  # noqa: BLE001, S110
        pass


def fixtures(tmp: Path) -> list[Path]:
    from tests.wfe.suites import build_documents_production as gen

    files = {
        "smoke_memo.docx": gen.make_docx(
            [
                ("h1", "Harbor Lease Memo"),
                ("p", "The escrow agent is Pell Varga."),
                ("table", [["Clause", "Days"], ["Notice", 37]]),
            ]
        ),
        "smoke_budget.xlsx": gen.make_xlsx(
            {
                "Budget": [
                    ["Line", "Cost"],
                    ["Rent", 1200],
                    ["Power", 340],
                    ["Water", 85],
                    ["Tools", 610],
                ]
            }
        ),
        "smoke_deck.pptx": gen.make_pptx(
            [("Kickoff", "Agenda and goals"), ("Rollout", "Owner: Ilse Mott")]
        ),
        "smoke_notes.pdf": gen.make_pdf([["Incident Record", "The vault code is 5521."]]),
    }
    if subprocess.run(["which", "say"], capture_output=True).returncode == 0:
        aiff = tmp / "a.aiff"
        subprocess.run(["say", "-o", str(aiff), "hello portal smoke test"], check=False)
        wav = tmp / "smoke_audio.wav"
        subprocess.run(
            ["afconvert", "-f", "WAVE", "-d", "LEI16@16000", str(aiff), str(wav)], check=False
        )
        if wav.exists():
            files["smoke_audio.wav"] = wav.read_bytes()
    out = []
    for name, data in files.items():
        p = tmp / name
        p.write_bytes(data)
        out.append(p)
    return out


@dataclass
class Result:
    workspace: str
    tool: str
    called: bool = False
    outcome: str = ""
    answer_ok: str = ""
    garbage: list[str] = field(default_factory=list)
    tokens: int = 0
    seconds: float = 0.0
    note: str = ""
    answer: str = ""
    memory_id: str = ""
    # Correct despite not calling the case tool: an expects-empty-KB case answered from
    # another kb_* tool that completed ok (finding F).
    accepted: bool = False


def newest_trace(ws: str, since: float) -> dict | None:
    for t in pipe("/v1/trace?limit=6")["data"]:
        if t["workspace"] == ws and t["started_at"] >= since - 1:
            return pipe(f"/v1/trace/{t['correlation_id']}")
    return None


def _memory_id_from_tool_result_text(text: str) -> str:
    """Read the UUID that the remember tool returned and the answer repeats."""
    match = _MEMORY_ID_RE.search(text)
    return match.group(0) if match else ""


def run_case(ws: str, case: Case) -> Result:
    r = Result(ws, case.tool)
    if case.skip:
        r.note = f"skipped: {case.skip}"
        return r
    t0 = time.time()
    try:
        out = owui(
            "/api/chat/completions",
            {"model": ws, "messages": [{"role": "user", "content": case.prompt}], "stream": False},
        )
    except Exception as e:  # noqa: BLE001
        r.note = f"request failed: {e}"
        return r
    r.seconds = round(time.time() - t0, 1)
    msg = (out.get("choices") or [{}])[0].get("message", {}).get("content") or ""
    r.answer = msg
    if case.tool == "remember":
        r.memory_id = _memory_id_from_tool_result_text(msg)
    r.tokens = (out.get("usage") or {}).get("prompt_tokens", 0)
    trace = newest_trace(ws, t0)
    spans = (trace or {}).get("spans", [])
    called = [s["tool"] for s in spans if s["name"] == "tool.requested"]
    done = {s["tool"]: s.get("outcome") for s in spans if s["name"] == "tool.completed"}
    r.called = case.tool in called
    r.outcome = done.get(case.tool, "-" if not r.called else "no completion")
    if not r.called and called:
        r.note = f"called {sorted(set(called))} instead"
    if case.expect_empty_kb and not r.called:
        kb_tool = next(
            (t for t in ("kb_list", "kb_search", "kb_search_all") if done.get(t) == "ok"), ""
        )
        if kb_tool:
            r.accepted = True
            r.note = f"correct: no KB has content; answered from {kb_tool}"
    r.answer_ok = (
        "n/a" if not case.expect else ("yes" if re.search(case.expect, msg, re.I) else "NO")
    )
    r.garbage = [name for name, fn in GARBAGE if fn(msg, case)]
    return r


def needs_look(r: Result) -> bool:
    """A row is a finding unless it was skipped or correct by design (empty-KB cases)."""
    if r.note.startswith("skipped"):
        return False
    if r.garbage or r.answer_ok == "NO":
        return True
    return not r.accepted and (not r.called or r.outcome not in ("ok", "complete"))


def empty_turn(ws: str) -> tuple[int, int]:
    import yaml

    ctx = (
        yaml.safe_load((REPO / "config/portal.yaml").read_text())["workspaces"][ws].get(
            "context_limit"
        )
        or 0
    )
    out = owui(
        "/api/chat/completions",
        {
            "model": ws,
            "messages": [{"role": "user", "content": "Reply with the single word: ready"}],
            "stream": False,
        },
    )
    return (out.get("usage") or {}).get("prompt_tokens", 0), ctx


def _forget_memory(memory_id: str) -> bool:
    """Forget one memory id; True when the forget call succeeded."""
    try:
        result = http(
            f"{MEMORY_MCP}/tools/forget",
            {"arguments": {"id": memory_id}},
            timeout=30,
        )
        if result.get("error"):
            raise RuntimeError(result["error"])
        return True
    except Exception as e:  # noqa: BLE001 — cleanup should not hide the smoke result
        print(f"WARNING: could not forget smoke memory {memory_id}: {e}", flush=True)
        return False


def _sweep_memories() -> None:
    """Forget leftover smoke notes by content, not by an id the model may never echo.

    The remember case asks the model to repeat the tool's id, but it can store the prompt
    sentence and answer without one (finding I, re-check 85d26a10). Recall is semantic, so
    only hits whose text carries the smoke code word are forgotten; nothing else is touched.
    """
    try:
        result = http(
            f"{MEMORY_MCP}/tools/recall",
            {"arguments": {"query": MEMORY_SWEEP_QUERY}},
            timeout=30,
        )
        if result.get("error"):
            raise RuntimeError(result["error"])
        ids = {
            m.get("id")
            for m in result.get("memories") or []
            if SMOKE_CODE_WORD in (m.get("text") or "")
        }
        forgotten = sum(1 for memory_id in ids if memory_id and _forget_memory(memory_id))
        print(f"cleanup: forgot {forgotten} smoke memory note(s) via recall sweep", flush=True)
    except Exception as e:  # noqa: BLE001 — cleanup should not hide the smoke result
        print(f"WARNING: could not sweep the memory store for smoke notes: {e}", flush=True)


def cleanup(
    ids: list[str], memory_ids: list[str] | None = None, *, remember_id_missing: bool = False
) -> None:
    for i in ids:
        delete_file(i)
    for memory_id in memory_ids or []:
        _forget_memory(memory_id)
    if remember_id_missing:
        print(
            "WARNING: the remember tool completed but its memory id was not returned; "
            "the smoke note may remain stored",
            flush=True,
        )
    # Always sweep: the turn-based id above is best-effort and the model may not echo one.
    _sweep_memories()
    for f in list(OUTPUT.glob("Smoke_*")) + list(OUTPUT.glob("uploads/*smoke_*")):
        f.unlink(missing_ok=True)


def main() -> int:
    import yaml

    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--workspaces",
        default="auto-documents,auto-research,general-fast,general-deep,auto-daily,auto-coding",
    )
    ap.add_argument("--tools", help="comma list; default: every tool the workspace offers")
    ap.add_argument("--md", type=Path)
    a = ap.parse_args()
    portal = yaml.safe_load((REPO / "config/portal.yaml").read_text())["workspaces"]
    by_tool = {c.tool: c for c in CASES}
    results: list[Result] = []
    memory_ids: list[str] = []
    remember_id_missing = False
    p4: dict[str, tuple[int, int]] = {}
    with tempfile.TemporaryDirectory() as td:
        ids = [upload(p) for p in fixtures(Path(td))]
        try:
            for ws in a.workspaces.split(","):
                p4[ws] = empty_turn(ws)
                for tool in portal[ws].get("tools") or []:
                    if a.tools and tool not in a.tools.split(","):
                        continue
                    case = by_tool.get(tool)
                    if case is None:
                        results.append(Result(ws, tool, note="no smoke prompt for this tool"))
                        continue
                    res = run_case(ws, case)
                    results.append(res)
                    if case.tool == "remember" and res.outcome == "ok":
                        if res.memory_id:
                            memory_ids.append(res.memory_id)
                        else:
                            remember_id_missing = True
                    print(
                        f"{ws:16s} {tool:22s} called={res.called!s:5s} outcome={res.outcome:10s} answer={res.answer_ok:4s} garbage={res.garbage} {res.note}",
                        flush=True,
                    )
        finally:
            cleanup(ids, memory_ids, remember_id_missing=remember_id_missing)
    lines = [
        "| workspace | tool | called | outcome | answer | garbage | prompt tokens | s | note |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for r in results:
        lines.append(
            f"| {r.workspace} | {r.tool} | {'yes' if r.called else 'NO'} | {r.outcome} | {r.answer_ok} | {', '.join(r.garbage) or '-'} | {r.tokens} | {r.seconds} | {r.note} |"
        )
    p4_lines = [
        "| workspace | empty-turn prompt tokens | context_limit | share |",
        "|---|---|---|---|",
    ]
    for ws, (tok, ctx) in p4.items():
        p4_lines.append(f"| {ws} | {tok} | {ctx} | {round(100 * tok / ctx) if ctx else '?'}% |")
    text = (
        "## P-4: prompt tokens of an empty turn\n\n"
        + "\n".join(p4_lines)
        + "\n\n## Per tool\n\n"
        + "\n".join(lines)
        + "\n"
    )
    if a.md:
        a.md.write_text(text)
    print("\n" + text)
    bad = [r for r in results if needs_look(r)]
    print(f"{len(bad)} of {len(results)} rows need a look")
    return 0


if __name__ == "__main__":
    sys.exit(main())
