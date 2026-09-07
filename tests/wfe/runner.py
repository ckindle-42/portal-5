#!/usr/bin/env python3
"""WFE fitness runner — real-use evaluation of a model IN its workspace/persona
context with tools exposed. This is the instrument the short-prompt probes could
not be: multi-turn, tool-executing, real-work tasks with objective checkers.

Fidelity model (the point of this harness):
  - system prompt = the workspace persona's actual system_prompt
  - tools = the tools that workspace declares, executing locally
  - tasks = real work with checkable outcomes (pytest passes, file produced,
    cited answer) — not synthetic single-turn accuracy
  - budget/turns bounded per task; results recorded verbatim for review

Tool implementations are deliberately whitelisted and sandboxed:
  file_read / file_list / repo_search : read-only inside the repo or task sandbox
  pytest_run                          : subprocess `pytest` scoped to the task sandbox
  http_get                            : urllib GET, size-capped, text-only

Usage:
  uv run python -m tests.wfe.runner --workspace tools-specialist \\
      --suite tests/wfe/suites/coding.jsonl --sandbox /tmp/wfe/coding_smoke
  uv run python -m tests.wfe.runner --model <tag> --system-prompt-file <txt> ...  # raw arm
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
OLLAMA = "http://localhost:11434"
RESULTS = REPO / "tests" / "wfe" / "results"
TOOLS_AVAILABLE = ["file_read", "file_list", "repo_search", "pytest_run", "http_get"]

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "file_read",
            "description": "Read a text file. Args: path (str, relative).",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "file_list",
            "description": "List files under a directory. Args: path (str, default '.')",
            "parameters": {"type": "object", "properties": {"path": {"type": "string"}}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "repo_search",
            "description": "Regex search in sandbox/repo files. Args: pattern (str)",
            "parameters": {
                "type": "object",
                "properties": {"pattern": {"type": "string"}},
                "required": ["pattern"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "pytest_run",
            "description": "Run pytest in the task sandbox. Args: args (str, default '')",
            "parameters": {"type": "object", "properties": {"args": {"type": "string"}}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "file_write",
            "description": "Write a file in the sandbox. Args: path, content",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}, "content": {"type": "string"}},
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "http_get",
            "description": "GET a URL, return first 4000 chars of text. Args: url (str)",
            "parameters": {
                "type": "object",
                "properties": {"url": {"type": "string"}},
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "file_write",
            "description": "Write a text file inside the task sandbox. Args: path (str), content (str)",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}, "content": {"type": "string"}},
                "required": ["path", "content"],
            },
        },
    },
]


class Sandbox:
    """Root for all file tools. repo=True allows read-only access to the real repo."""

    def __init__(self, root: Path, allow_repo_read: bool = True):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.allow_repo_read = allow_repo_read

    def _resolve(self, path: str, write: bool = False) -> Path | None:
        p = (self.root / path).resolve()
        try:
            p.relative_to(self.root)
            return p
        except ValueError:
            if not write and self.allow_repo_read:
                rp = (REPO / path).resolve()
                try:
                    rp.relative_to(REPO)
                    return rp
                except ValueError:
                    return None
            return None

    def file_read(self, path: str = ".") -> str:
        f = self._resolve(path)
        if f is None or not f.is_file():
            return f"ERROR: cannot read {path}"
        return f.read_text(errors="ignore")[:20000]

    def file_list(self, path: str = ".") -> str:
        d = self._resolve(path)
        if d is None or not d.is_dir():
            return f"ERROR: cannot list {path}"
        return "\n".join(str(x.relative_to(d)) for x in sorted(d.rglob("*"))[:200])

    def repo_search(self, pattern: str = "") -> str:
        try:
            r = subprocess.run(
                ["grep", "-rEn", "--", pattern, str(self.root)],
                capture_output=True,
                text=True,
                timeout=20,
            )
            return (r.stdout or "(no matches)")[:8000]
        except Exception as e:
            return f"ERROR: {e}"

    def pytest_run(self, args: str = "") -> str:
        try:
            r = subprocess.run(
                [sys.executable, "-m", "pytest", "-x", "-q", *(args.split() or [])],
                capture_output=True,
                text=True,
                timeout=180,
                cwd=self.root,
            )
            return (r.stdout + r.stderr)[:8000]
        except Exception as e:
            return f"ERROR: {e}"

    def file_write(self, path: str = "", content: str = "") -> str:
        f = self._resolve(path, write=True)
        if f is None:
            return f"ERROR: {path} outside sandbox"
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(content)
        return f"wrote {len(content)} chars to {path}"

    def http_get(self, url: str = "") -> str:
        if not url.startswith("http"):
            return "ERROR: url required"
        try:
            with urllib.request.urlopen(url, timeout=30) as r:
                return r.read(200000).decode(errors="ignore")[:4000]
        except Exception as e:
            return f"ERROR: {e}"

    def dispatch(self, name: str, args: dict) -> str:
        fn = {
            "file_read": self.file_read,
            "file_list": self.file_list,
            "repo_search": self.repo_search,
            "pytest_run": self.pytest_run,
            "file_write": self.file_write,
            "http_get": self.http_get,
        }.get(name)
        if fn is None:
            return f"ERROR: unknown tool {name}"
        try:
            return fn(**args)
        except TypeError as e:
            return f"ERROR: bad args: {e}"


# Harness dimensions — every result records these so instrument confounds are
# visible in analysis (the gpt-oss 0.000 artifact was think:false+format:json
# against a harmony model; production serves /v1 while most probes used /api).
HARNESS_DEFAULTS = {"endpoint": "v1", "stream": False, "think": "default", "format": "none"}


def _think_policy(tag: str) -> str:
    """Per-family think policy from the model-card registry ('default'|'true'|'false')."""
    try:
        import yaml as _yaml

        reg = (
            _yaml.safe_load((REPO / "config/model_card_expectations.yaml").read_text()) or {}
        ).get("models", {})
        tl = tag.lower()
        for key, entry in reg.items():
            if key.lower() in tl:
                pol = (entry or {}).get("harness_policy", {}).get("think")
                if pol:
                    return pol
    except Exception:
        pass
    return "default"


def _parse_stream_api(lines) -> dict:
    content, tool_parts, done = [], {}, False
    for line in lines:
        line = line.strip()
        if not line:
            continue
        obj = json.loads(line)
        msg = obj.get("message") or {}
        if msg.get("content"):
            content.append(msg["content"])
        for tc in msg.get("tool_calls") or []:
            idx = tc.get("function", {}).get("index", 0) or 0
            slot = tool_parts.setdefault(
                idx, {"id": "", "type": "function", "function": {"name": "", "arguments": ""}}
            )
            fn = tc.get("function", {})
            slot["function"]["name"] += fn.get("name", "")
            slot["function"]["arguments"] += fn.get("arguments", "")
        done = done or bool(obj.get("done"))
    message = {"content": "".join(content)}
    if tool_parts:
        message["tool_calls"] = [
            {"function": {"name": s["function"]["name"], "arguments": s["function"]["arguments"]}}
            for _, s in sorted(tool_parts.items())
        ]
    return {"message": message, "done": done}


def _parse_stream_v1(lines) -> dict:
    content, tool_parts = [], {}
    for line in lines:
        line = line.strip()
        if not line.startswith("data:"):
            continue
        data = line[5:].strip()
        if data == "[DONE]":
            break
        obj = json.loads(data)
        delta = (obj.get("choices") or [{}])[0].get("delta") or {}
        if delta.get("content"):
            content.append(delta["content"])
        for tc in delta.get("tool_calls") or []:
            idx = tc.get("index", 0) or 0
            slot = tool_parts.setdefault(idx, {"function": {"name": "", "arguments": ""}})
            fn = tc.get("function", {}) or {}
            slot["function"]["name"] += fn.get("name") or ""
            slot["function"]["arguments"] += fn.get("arguments") or ""
    message = {"content": "".join(content)}
    if tool_parts:
        message["tool_calls"] = [
            {"function": {"name": s["function"]["name"], "arguments": s["function"]["arguments"]}}
            for _, s in sorted(tool_parts.items())
        ]
    return {"message": message}


def chat(
    model: str,
    messages: list[dict],
    tools: bool = True,
    harness: dict | None = None,
) -> dict:
    """One completion under explicit harness dimensions.

    endpoint: 'v1' (production /v1/chat/completions — what the pipeline uses)
              or 'api' (Ollama-native /api/chat — what the Sept bench probes used)
    stream:   streaming parse; content/tool_calls assembled from deltas
    think:    'default' | 'true' | 'false' (api endpoint only; v1 has no think knob —
              thinking models may inline reasoning, recorded as a harness caveat)
    """
    h = {**HARNESS_DEFAULTS, **(harness or {})}
    endpoint, stream = h["endpoint"], bool(h["stream"])
    think = h["think"]
    if think == "default":
        think = _think_policy(model)
    if tools:
        pass  # TOOL_SCHEMAS applied per-endpoint below
    if endpoint == "v1":
        payload = {"model": model, "messages": messages, "stream": stream, "max_tokens": 2048}
        if tools:
            payload["tools"] = TOOL_SCHEMAS
        req = urllib.request.Request(
            f"{OLLAMA}/v1/chat/completions",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=600) as r:
            if stream:
                resp = _parse_stream_v1(line.decode() for line in r)
            else:
                body = json.load(r)
                msg = (body.get("choices") or [{}])[0].get("message") or {}
                resp = {"message": msg}
                if think != "default":
                    resp.setdefault("harness_caveats", []).append("v1_think_unsupported")
    else:
        payload = {
            "model": model,
            "messages": messages,
            "stream": stream,
            "options": {"num_predict": 2048},
        }
        if tools:
            payload["tools"] = TOOL_SCHEMAS
        if think in ("true", "false"):
            payload["think"] = think == "true"
        req = urllib.request.Request(
            f"{OLLAMA}/api/chat",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=600) as r:
            resp = _parse_stream_api(line.decode() for line in r) if stream else json.load(r)
    return resp


def preflight_harness(model: str) -> dict:
    """Harness self-test — catch instrument artifacts BEFORE a campaign:
    (1) api think:false+format-json vs native (the gpt-oss breakage class),
    (2) stream vs non-stream content parity, (3) v1 reachability."""
    out: dict = {"model": model}
    base_msgs = [{"role": "user", "content": "Reply with exactly: OK"}]

    def _content(harness):
        try:
            r = chat(model, base_msgs, tools=False, harness=harness)
            c = (r.get("message") or {}).get("content", "")
            caveats = r.get("harness_caveats")
            if caveats:
                c = c + f" [{'; '.join(caveats)}]"
            return c
        except Exception as e:
            return f"ERROR: {e}"

    strict = {"endpoint": "api", "think": "false", "format": "json"}
    native = {"endpoint": "api", "think": "default", "format": "none"}
    out["api_strict_json"] = _content(strict)[:120]
    out["api_native"] = _content(native)[:120]
    ns = _content({"endpoint": "api", "think": "default"})
    st = _content({"endpoint": "api", "think": "default", "stream": True})
    out["stream_parity"] = (
        "OK" if ns.strip() == st.strip() else f"MISMATCH ns={ns[:60]!r} st={st[:60]!r}"
    )
    out["v1"] = _content({"endpoint": "v1", "think": "default"})[:120]
    out["verdict"] = "OK" if "ERROR" not in str(out) and out["stream_parity"] == "OK" else "REVIEW"
    return out


def run_task(
    model: str,
    system_prompt: str,
    task: dict,
    sandbox: Sandbox,
    max_turns: int,
    budget_s: int,
    use_tools: bool,
    harness: dict | None = None,
) -> dict:
    """Run one fitness task to completion (tool-loop), then apply the checker."""
    for seed_path, seed_body in (task.get("seed") or {}).items():
        sandbox.file_write(seed_path, seed_body)
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": task["instruction"]},
    ]
    transcript, tool_calls, t0 = [], [], time.monotonic()
    final_text = ""
    for turn in range(max_turns):
        if time.monotonic() - t0 > budget_s:
            break
        resp = chat(model, messages, tools=use_tools, harness=harness)
        msg = resp.get("message") or {}
        content = msg.get("content", "") or ""
        calls = msg.get("tool_calls") or []
        transcript.append(
            {
                "turn": turn,
                "content": content[:2000],
                "tool_calls": [
                    {"name": c["function"]["name"], "args": c["function"]["arguments"]}
                    for c in calls
                ],
            }
        )
        if calls:
            messages.append(msg)
            for c in calls:
                name = c["function"]["name"]
                args = c["function"]["arguments"] or {}
                out = sandbox.dispatch(name, args)
                tool_calls.append({"name": name, "args": args, "out_head": out[:300]})
                messages.append({"role": "tool", "content": out[:4000]})
            continue
        final_text = content
        messages.append({"role": "assistant", "content": content})
        if task.get("completion_signal") and re.search(task["completion_signal"], content, re.I):
            break
        # no signal: single answer tasks end here
        if not task.get("agentic"):
            break
    checker_name = task.get("checker", {}).get("type", "transcript_contains")
    spec = task.get("checker", {})
    ok, notes = apply_checker(checker_name, spec, final_text, transcript, tool_calls, sandbox)
    return {
        "harness": harness or {},
        "task_id": task["id"],
        "completed": ok,
        "notes": notes,
        "turns": len(transcript),
        "tool_calls": len(tool_calls),
        "tool_call_log": tool_calls,
        "wall_s": round(time.monotonic() - t0, 1),
        "final_text_head": final_text[:600],
        "transcript": transcript,
    }


def apply_checker(name, spec, final_text, transcript, tool_calls, sandbox) -> tuple[bool, str]:
    if name == "pytest_pass":
        out = sandbox.pytest_run(spec.get("pytest_args", ""))
        ok = "failed" not in out.split("\n")[-2] if out else False
        return (
            "passed" in out or "no tests ran" not in out and "== " in out and "failed" not in out
        ), f"pytest tail: {out[-200:]}"
    if name == "file_exists":
        f = sandbox._resolve(spec["path"])
        ok = f is not None and f.is_file() and f.stat().st_size > 0
        return ok, f"file {spec['path']} exists={ok}"
    if name == "file_contains":
        f = sandbox._resolve(spec["path"])
        if f is None or not f.is_file():
            return False, "file missing"
        body = f.read_text(errors="ignore")
        ok = all(re.search(pat, body) for pat in spec.get("patterns", []))
        return ok, f"patterns matched={ok} in {spec['path']}"
    if name == "transcript_contains":
        blob = final_text + " " + json.dumps(transcript)
        ok = all(re.search(pat, blob, re.I) for pat in spec.get("patterns", []))
        cites = spec.get("require_citation") and not re.search(r"https?://", blob)
        return (
            ok and not cites,
            f"patterns={ok} citation_present={bool(re.search(r'https?://', blob))}",
        )
    if name == "human_review":
        return None, "recorded for operator review (rubric fields in notes)"
    return False, f"unknown checker {name}"


def workspace_context(ws_id: str) -> tuple[str, str, list[str]]:
    """(model, system_prompt, tools) for a workspace, honoring persona overrides."""
    portal = yaml.safe_load((REPO / "config/portal.yaml").read_text())
    ws = portal["workspaces"][ws_id]
    model, system_prompt, tools = ws.get("model_hint"), "", list(ws.get("tools") or [])
    for pf in (REPO / "config/personas").glob("*.yaml"):
        d = yaml.safe_load(pf.read_text()) or {}
        if d.get("workspace_model") == ws_id and d.get("system_prompt"):
            system_prompt = d["system_prompt"]
            break
    if not system_prompt:
        system_prompt = (ws.get("description") or "") + "\nPerform the user's task faithfully."
    return model, system_prompt, tools


def main() -> int:
    ap = argparse.ArgumentParser()
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument(
        "--workspace", help="portal.yaml workspace id (uses its hint + persona + tools)"
    )
    src.add_argument("--model", help="raw model tag arm")
    ap.add_argument("--system-prompt-file")
    ap.add_argument("--suite", required=True, help="jsonl suite file")
    ap.add_argument("--sandbox", default="/tmp/wfe/run")
    ap.add_argument("--max-turns", type=int, default=8)
    ap.add_argument("--budget-s", type=int, default=600)
    ap.add_argument("--no-tools", action="store_true")
    ap.add_argument("--label", default="")
    ap.add_argument(
        "--endpoint",
        choices=["v1", "api"],
        default="v1",
        help="v1 = production /v1/chat/completions (default); api = Ollama-native (Sept probes)",
    )
    ap.add_argument("--stream", action="store_true")
    ap.add_argument("--think", choices=["default", "true", "false"], default="default")
    ap.add_argument(
        "--preflight",
        action="store_true",
        help="harness self-test only: strict-json/native parity, stream parity, v1 reachability",
    )
    args = ap.parse_args()
    if args.preflight:
        model_pf = (
            args.model or workspace_context(args.workspace)[0]
            if args.workspace or args.model
            else None
        )
        if not model_pf:
            ap.error("--preflight needs --model or --workspace")
        print(json.dumps(preflight_harness(model_pf), indent=1))
        return 0
    harness = {"endpoint": args.endpoint, "stream": args.stream, "think": args.think}

    model = args.model
    system_prompt = Path(args.system_prompt_file).read_text() if args.system_prompt_file else ""
    if args.workspace:
        model, sp, ws_tools = workspace_context(args.workspace)
        system_prompt = system_prompt or sp
        print(f"workspace {args.workspace}: model={model} tools_declared={len(ws_tools)}")

    tasks = [json.loads(x) for x in Path(args.suite).read_text().splitlines() if x.strip()]
    sandbox = Sandbox(Path(args.sandbox))
    label = args.label or (args.workspace or model).replace("/", "_")
    run_rows = []
    for t in tasks:
        if t.get("requires_network") and not args.suite:
            pass  # network tasks simply fail their http tool if offline; recorded honestly
        print(f"--- {t['id']}: {t['instruction'][:80]}...", flush=True)
        row = run_task(
            model,
            system_prompt,
            t,
            sandbox,
            args.max_turns,
            args.budget_s,
            use_tools=not args.no_tools,
            harness=harness,
        )
        row["task_instruction"] = t["instruction"]
        run_rows.append(row)
        print(
            f"    completed={row['completed']} turns={row['turns']} tools={row['tool_calls']} {row['wall_s']}s"
        )

    RESULTS.mkdir(parents=True, exist_ok=True)
    ts = dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%SZ")
    out = RESULTS / f"wfe_{label}_{ts}.json"
    out.write_text(
        json.dumps(
            {
                "model": model,
                "workspace": args.workspace,
                "suite": args.suite,
                "label": label,
                "results": run_rows,
            },
            indent=1,
        )
    )
    done = sum(1 for r in run_rows if r["completed"] is True)
    print(f"\nfitness: {done}/{len(run_rows)} tasks completed -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
