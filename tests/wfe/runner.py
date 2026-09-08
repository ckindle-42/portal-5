#!/usr/bin/env python3
"""WFE fitness runner — real-use evaluation of a model IN its workspace/persona
context with tools exposed: multi-turn, tool-executing, objectively checked.

Repairs in this revision (each was a false-result generator):
  - /v1 returns tool-call arguments as a JSON STRING; the previous runner
    splatted it as **kwargs, so EVERY tool call on the default endpoint failed
    with "ERROR: bad args". Arguments are now normalised at the boundary,
    matching portal/platform/inference/router/tools.py.
  - tool result messages carry tool_call_id + name, as production does.
  - sandboxes are per (task, repeat); the previous runner shared one directory
    across every task and every arm, so later runs inherited earlier work.
  - persona resolution is deterministic and recorded (auto-coding has 40
    personas bound to it; first-glob-wins made the measured prompt arbitrary).
  - token/latency economics and finish_reason are captured, not discarded.
  - the harness `format` dimension is actually applied, so --preflight really
    exercises the gpt-oss strict-JSON breakage class it was written for, and
    a degenerate (non-empty non-JSON) reply fails it, not only an empty one.
  - every request is STREAMED on the wire and a stall (no bytes for STALL_S),
    not a total-time cap, aborts the turn — a slow-but-progressing model keeps
    its work; a wedged backend is caught in minutes, not hours.

Usage:
  uv run python -m tests.wfe.runner --workspace tools-specialist \\
      --suite tests/wfe/suites/coding.jsonl --sandbox /tmp/wfe/coding
  uv run python -m tests.wfe.runner --model <tag> --preflight
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import yaml

from tests.wfe.checkers import CheckContext, apply_checkers
from tests.wfe.schema import Economics, Outcome, ResultRow, env_fingerprint, sha12

REPO = Path(__file__).resolve().parents[2]
OLLAMA = "http://localhost:11434"
RESULTS = REPO / "tests" / "wfe" / "results"

HARNESS_DEFAULTS = {"endpoint": "v1", "stream": False, "think": "default", "format": "none"}

#: A timeout is the enemy of a slow-but-progressing model: a large model under
#: memory pressure can legitimately take many minutes per turn, and a blind
#: wall-clock deadline throws that work away. The runner therefore streams every
#: request on the wire and watches for a STALL — no bytes for STALL_S — rather
#: than a total-time cap. Real progress (tokens arriving) resets the clock and is
#: logged so a human tailing a multi-day sweep can see the model is alive.
STALL_S = int(os.environ.get("WFE_STALL_S", "300"))
_PROGRESS_EVERY_S = 30


class StreamStalledError(RuntimeError):
    """The backend accepted the request but produced no output for STALL_S, or
    blew a generous hard ceiling. Attributed to the model (too slow for real
    work in its lane), never to the harness."""


_NETWORK_OK: bool | None = None


def network_ok(probe: str = "https://raw.githubusercontent.com") -> bool:
    """One cached reachability probe for the public internet. A `requires_network`
    task on a machine with no outbound route is a BLOCKED instrument outcome, not
    a model FAIL — without this check http_get errors on every call and a
    fetch-grounded checker scores the model 0 for the harness's problem."""
    global _NETWORK_OK
    if _NETWORK_OK is None:
        try:
            urllib.request.urlopen(probe, timeout=5)
            _NETWORK_OK = True
        except Exception:
            _NETWORK_OK = False
    return _NETWORK_OK


def _fn(name: str, desc: str, props: dict, required: list[str] | None = None) -> dict:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": desc,
            "parameters": {"type": "object", "properties": props, "required": required or []},
        },
    }


#: One entry per tool. The previous list declared file_write TWICE (7 entries,
#: 6 unique names) alongside a stale TOOLS_AVAILABLE constant that omitted it.
TOOL_SCHEMAS = [
    _fn(
        "file_read",
        "Read a text file. Args: path (str, relative).",
        {"path": {"type": "string"}},
        ["path"],
    ),
    _fn(
        "file_list",
        "List files under a directory. Args: path (str, default '.').",
        {"path": {"type": "string"}},
    ),
    _fn(
        "repo_search",
        "Regex search across the sandbox and the repository. Args: pattern (str), path (str, optional).",
        {"pattern": {"type": "string"}, "path": {"type": "string"}},
        ["pattern"],
    ),
    _fn(
        "pytest_run",
        "Run pytest in the task sandbox. Args: args (str, default '').",
        {"args": {"type": "string"}},
    ),
    _fn(
        "file_write",
        "Write a text file inside the task sandbox. Args: path (str), content (str).",
        {"path": {"type": "string"}, "content": {"type": "string"}},
        ["path", "content"],
    ),
    _fn(
        "http_get",
        "GET a URL, return the first 4000 chars of text. Args: url (str).",
        {"url": {"type": "string"}},
        ["url"],
    ),
]
TOOL_NAMES = [t["function"]["name"] for t in TOOL_SCHEMAS]


class Sandbox:
    """Root for all file tools. Writes are confined to the sandbox; reads may
    fall back to the repository (read-only) so in-repo tasks are possible.
    Checkers never use this resolver — they resolve sandbox-only, because a repo
    fallback let a checker be satisfied by a file the model never wrote."""

    def __init__(self, root: Path, allow_repo_read: bool = True):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.allow_repo_read = allow_repo_read

    @staticmethod
    def _under(child: Path, parent: Path) -> bool:
        return child == parent or parent in child.parents

    def _resolve(self, path: str, write: bool = False) -> Path | None:
        """Resolve a tool path. Writes are sandbox-only. Reads prefer a sandbox
        file when one exists, then fall back to the repository — the previous
        version only fell back when the path ESCAPED the sandbox, so
        file_read('README.md') on an in-repo research task never reached the
        repo and repo_search('.', ...) searched an empty directory."""
        sp = (self.root / path).resolve()
        in_sandbox = self._under(sp, self.root)
        if write:
            return sp if in_sandbox else None
        if in_sandbox and sp.exists():
            return sp
        if self.allow_repo_read:
            rp = (REPO / path).resolve()
            if self._under(rp, REPO) and rp.exists():
                return rp
        return sp if in_sandbox else None

    def file_read(self, path: str = ".") -> str:
        f = self._resolve(path)
        if f is None or not f.is_file():
            return f"ERROR: cannot read {path}"
        return f.read_text(errors="ignore")[:20000]

    def file_list(self, path: str = ".") -> str:
        d = self._resolve(path)
        # A bare, empty sandbox root is useless to a research task — show the
        # repository's top level instead so the model can navigate it.
        if d is not None and d == self.root and self.allow_repo_read and not any(d.iterdir()):
            return "\n".join(sorted(p.name for p in REPO.iterdir() if not p.name.startswith(".")))
        if d is None or not d.is_dir():
            return f"ERROR: cannot list {path}"
        if d == REPO:  # never rglob the whole repo — top level only
            return "\n".join(sorted(p.name for p in d.iterdir() if not p.name.startswith(".")))
        return "\n".join(str(x.relative_to(d)) for x in sorted(d.rglob("*"))[:200])

    def _grep_sandbox(self, pattern: str, root: Path) -> str:
        try:
            return subprocess.run(
                ["grep", "-rEnI", "--exclude-dir=__pycache__", "--", pattern, str(root)],
                capture_output=True,
                text=True,
                timeout=15,
            ).stdout.replace(str(root) + "/", "")
        except Exception as e:  # pragma: no cover - defensive
            return f"ERROR: {e}\n"

    def _grep_repo(self, pattern: str) -> str:
        """`git grep` over TRACKED files only — fast, and .venv / worktrees /
        node_modules / build artifacts are excluded for free. A plain `grep -r`
        over the repo root walks .claude/worktrees/*/.venv and times out."""
        try:
            r = subprocess.run(
                ["git", "-C", str(REPO), "grep", "-nEI", "--no-color", "-e", pattern],
                capture_output=True,
                text=True,
                timeout=20,
            )
            return r.stdout
        except Exception as e:  # pragma: no cover - defensive
            return f"ERROR: {e}\n"

    def repo_search(self, pattern: str = "", path: str = "") -> str:
        """Regex search across the sandbox AND the repository (its stated
        contract). The previous version only added the repo when `path` was
        empty or escaped the sandbox, so `path='.'` — which the model naturally
        passes for "here" — resolved to the sandbox root and excluded the repo."""
        if not str(pattern).strip():
            return "ERROR: pattern required"
        chunks: list[str] = []
        if path and path not in (".", "./"):
            t = self._resolve(path)
            chunks.append(self._grep_sandbox(pattern, t if (t and t.is_dir()) else self.root))
        else:
            chunks.append(self._grep_sandbox(pattern, self.root))
            if self.allow_repo_read:
                chunks.append(self._grep_repo(pattern))
        body = "\n".join(c for c in chunks if c.strip())
        return (body or "(no matches)")[:8000]

    def pytest_run(self, args: str = "") -> str:
        try:
            r = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "pytest",
                    "-q",
                    "-p",
                    "no:cacheprovider",
                    "--import-mode=importlib",
                    *(args.split() if args else []),
                ],
                capture_output=True,
                text=True,
                timeout=180,
                cwd=str(self.root),
            )
            return (r.stdout + r.stderr)[:8000]
        except Exception as e:
            return f"ERROR: {e}"

    def file_write(self, path: str = "", content: str = "") -> str:
        if not str(path).strip():
            return "ERROR: path required"
        f = self._resolve(path, write=True)
        if f is None:
            return f"ERROR: {path} outside sandbox"
        if f.is_dir() or f == self.root:
            return f"ERROR: {path} is a directory"
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(content)
        return f"wrote {len(content)} chars to {path}"

    def http_get(self, url: str = "") -> str:
        if not str(url).startswith("http"):
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
            return f"ERROR: bad args for {name}: {e}"
        except Exception as e:
            # A model emitting a hostile or malformed argument must produce a
            # recorded tool ERROR the model can recover from, not abort the run
            # into HARNESS_ERROR. Dimension 13/14 depend on this distinction.
            return f"ERROR: {name} failed: {type(e).__name__}: {e}"


def normalize_tool_args(raw) -> tuple[dict, str | None]:
    """/api/chat returns a dict; /v1 returns a JSON string (OpenAI contract).
    Mirrors portal/platform/inference/router/tools.py:189."""
    if raw is None or raw == "":
        return {}, None
    if isinstance(raw, dict):
        return raw, None
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as e:
            return {}, f"invalid JSON arguments: {e}"
        if not isinstance(parsed, dict):
            return {}, f"arguments decoded to {type(parsed).__name__}, expected object"
        return parsed, None
    return {}, f"unsupported arguments type {type(raw).__name__}"


def _card_registry() -> dict:
    path = REPO / "config" / "model_card_expectations.yaml"
    if not path.exists():
        return {}
    return (yaml.safe_load(path.read_text()) or {}).get("models", {}) or {}


def _norm_key(s: str) -> str:
    return re.sub(r"[-_.\s]", "", s.lower())


def card_entry(tag: str, registry: dict | None = None) -> tuple[str, dict] | None:
    """Longest-match-wins over separator-normalised keys.

    The previous first-substring-wins scan resolved 28 of 81 production hints to
    the generic 'qwen3' entry (shadowing qwen3.5/3.6/3.8) and matched NOTHING for
    granite, because registry keys are hyphenated ('granite-4.1') while installed
    tags are not ('granite4.1'). Dimensions 2 and 3 were inert as a result."""
    registry = _card_registry() if registry is None else registry
    tl = _norm_key(tag)
    best = None
    for key, entry in registry.items():
        nk = _norm_key(key)
        if nk and nk in tl and (best is None or len(nk) > len(_norm_key(best[0]))):
            best = (key, entry or {})
    return best


def think_policy(tag: str, registry: dict | None = None) -> str:
    hit = card_entry(tag, registry)
    if hit:
        pol = (hit[1].get("harness_policy") or {}).get("think")
        if pol:
            return pol
    return "default"


def format_json_policy(tag: str, registry: dict | None = None) -> bool | None:
    """Card ground truth for the strict-JSON arm: harness_policy.format_json_safe.

    Returns True/False when the card records it, None when the model has no card
    entry or the field is absent. The gpt-oss card records this False — a
    harmony/template conflict makes `format:json` return empty or degenerate
    content — and preflight reconciles that claim against live behaviour rather
    than trusting either side."""
    hit = card_entry(tag, registry)
    if hit:
        pol = (hit[1].get("harness_policy") or {}).get("format_json_safe")
        if isinstance(pol, bool):
            return pol
    return None


def _is_json_object(text: str) -> bool:
    """True iff `text` parses to a JSON object. The strict-JSON arm asks for
    exactly `{"ok": true}`; anything that will not `json.loads` to a dict is
    degenerate output, not a passing response — which is the other half of the
    'empty/degenerate' breakage the gpt-oss card records."""
    try:
        return isinstance(json.loads((text or "").strip()), dict)
    except (json.JSONDecodeError, ValueError):
        return False


def _mk_msg(content: list, tool_parts: dict) -> dict:
    msg = {"role": "assistant", "content": "".join(content)}
    if tool_parts:
        msg["tool_calls"] = [
            {
                "id": s.get("id") or f"call_{i}",
                "type": "function",
                "function": {
                    "name": s["function"]["name"],
                    "arguments": s["function"]["arguments"],
                },
            }
            for i, (_, s) in enumerate(sorted(tool_parts.items()))
        ]
    return msg


def _iter_lines_with_stall(resp, stall_s: int, hard_s: int, tag: str):
    """Yield response lines, aborting on a stall rather than on total time.

    The socket carries a stall_s read timeout, so a readline that blocks longer
    than that means the backend has gone quiet — raise StreamStalledError. As long as
    bytes keep arriving the only ceiling is hard_s (minutes of headroom over the
    slowest plausible real turn), and progress is logged every _PROGRESS_EVERY_S.
    """
    t0 = time.monotonic()
    last_log = t0
    seen = 0
    while True:
        try:
            line = resp.readline()
        except TimeoutError as e:
            raise StreamStalledError(
                f"{tag}: no output for {stall_s}s after {seen} bytes / "
                f"{int(time.monotonic() - t0)}s — backend stalled"
            ) from e
        if not line:
            return
        seen += len(line)
        now = time.monotonic()
        if now - t0 > hard_s:
            raise StreamStalledError(
                f"{tag}: exceeded {hard_s}s hard ceiling ({seen} bytes) — abandoning turn"
            )
        if now - last_log >= _PROGRESS_EVERY_S:
            print(
                f"    … {tag}: streaming, {seen} bytes, {int(now - t0)}s elapsed",
                file=sys.stderr,
                flush=True,
            )
            last_log = now
        yield line


def _parse_stream_api(lines) -> dict:
    content, tool_parts, done_reason, raw = [], {}, None, {}
    for line in lines:
        line = line.strip()
        if not line:
            continue
        obj = json.loads(line)
        msg = obj.get("message") or {}
        if msg.get("content"):
            content.append(msg["content"])
        for tc in msg.get("tool_calls") or []:
            fn = tc.get("function", {}) or {}
            idx = fn.get("index", len(tool_parts)) or 0
            slot = tool_parts.setdefault(
                idx, {"id": tc.get("id") or "", "function": {"name": "", "arguments": ""}}
            )
            slot["function"]["name"] += fn.get("name") or ""
            a = fn.get("arguments")
            slot["function"]["arguments"] += a if isinstance(a, str) else json.dumps(a or {})
        if obj.get("done"):
            done_reason = obj.get("done_reason")
            raw = obj
    return {"message": _mk_msg(content, tool_parts), "done_reason": done_reason, "_raw": raw}


def _parse_stream_v1(lines) -> dict:
    content, tool_parts, finish, usage = [], {}, None, {}
    for line in lines:
        line = line.strip()
        if not line.startswith("data:"):
            continue
        data = line[5:].strip()
        if data == "[DONE]":
            break
        obj = json.loads(data)
        if obj.get("usage"):
            usage = obj["usage"]
        choice = (obj.get("choices") or [{}])[0]
        finish = choice.get("finish_reason") or finish
        delta = choice.get("delta") or {}
        if delta.get("content"):
            content.append(delta["content"])
        for tc in delta.get("tool_calls") or []:
            idx = tc.get("index", 0) or 0
            slot = tool_parts.setdefault(
                idx, {"id": tc.get("id") or "", "function": {"name": "", "arguments": ""}}
            )
            if tc.get("id"):
                slot["id"] = tc["id"]
            fn = tc.get("function", {}) or {}
            slot["function"]["name"] += fn.get("name") or ""
            slot["function"]["arguments"] += fn.get("arguments") or ""
    return {"message": _mk_msg(content, tool_parts), "finish_reason": finish, "usage": usage}


def _build_payload(
    model: str,
    messages: list[dict],
    h: dict,
    sampling: dict,
    schemas: list | None,
    think: str,
    wire_stream: bool = True,
) -> tuple[str, dict, list[str]]:
    """Assemble the endpoint-specific request. Split out of chat() so the two
    wire contracts stay legible and independently testable.

    `wire_stream` is how the bytes come off the socket, which the stall watchdog
    needs — it is independent of the harness `stream` dimension (that only marks
    which logical mode a preflight arm is exercising). Default True: streaming is
    the only way to tell a slow model from a wedged one."""
    endpoint, fmt = h["endpoint"], h.get("format", "none")
    caveats: list[str] = []
    max_tokens = int(sampling.pop("max_tokens", 2048))
    if endpoint == "v1":
        payload = {
            "model": model,
            "messages": messages,
            "stream": wire_stream,
            "max_tokens": max_tokens,
        }
        if wire_stream:
            payload["stream_options"] = {"include_usage": True}
        for k in ("temperature", "top_p", "seed"):
            if sampling.get(k) is not None:
                payload[k] = sampling[k]
        if fmt == "json":
            payload["response_format"] = {"type": "json_object"}
        if think != "default":
            caveats.append("v1_think_unsupported")
        url = f"{OLLAMA}/v1/chat/completions"
    else:
        options = {"num_predict": max_tokens}
        for k in ("temperature", "top_p", "seed"):
            if sampling.get(k) is not None:
                options[k] = sampling[k]
        payload = {
            "model": model,
            "messages": messages,
            "stream": wire_stream,
            "options": options,
        }
        if fmt == "json":
            payload["format"] = "json"
        if think in ("true", "false"):
            payload["think"] = think == "true"
        url = f"{OLLAMA}/api/chat"
    if schemas:
        payload["tools"] = schemas
    return url, payload, caveats


def _econ_from_usage(u: dict) -> Economics:
    return Economics(
        prompt_tokens=u.get("prompt_tokens"),
        completion_tokens=u.get("completion_tokens"),
        total_tokens=u.get("total_tokens")
        or ((u.get("prompt_tokens") or 0) + (u.get("completion_tokens") or 0))
        or None,
    )


def _read_stream(endpoint: str, lines) -> tuple[dict, str | None, Economics]:
    """Decode a streamed response into (message, finish_reason, economics).
    Economics come from the usage chunk (/v1, stream_options.include_usage) or
    the final done object (/api/chat) — the pre-repair runner discarded both."""
    if endpoint == "v1":
        out = _parse_stream_v1(line.decode() for line in lines)
        return out["message"], out.get("finish_reason"), _econ_from_usage(out.get("usage") or {})
    out = _parse_stream_api(line.decode() for line in lines)
    raw = out.get("_raw") or {}
    total = (raw.get("prompt_eval_count") or 0) + (raw.get("eval_count") or 0)
    return (
        out["message"],
        out.get("done_reason"),
        Economics(
            prompt_tokens=raw.get("prompt_eval_count"),
            completion_tokens=raw.get("eval_count"),
            total_tokens=total or None,
            load_ms=int((raw.get("load_duration") or 0) / 1e6) or None,
        ),
    )


def _read_response(endpoint: str, r) -> tuple[dict, str | None, Economics]:
    """Decode a NON-streamed response. Only the preflight parity arm asks for
    this; every other path streams so the stall watchdog has a pulse to watch."""
    if endpoint == "v1":
        body = json.load(r)
        choice = (body.get("choices") or [{}])[0]
        return (
            choice.get("message") or {"role": "assistant", "content": ""},
            choice.get("finish_reason"),
            _econ_from_usage(body.get("usage") or {}),
        )
    raw = json.load(r)
    total = (raw.get("prompt_eval_count") or 0) + (raw.get("eval_count") or 0)
    return (
        raw.get("message") or {"role": "assistant", "content": ""},
        raw.get("done_reason"),
        Economics(
            prompt_tokens=raw.get("prompt_eval_count"),
            completion_tokens=raw.get("eval_count"),
            total_tokens=total or None,
            load_ms=int((raw.get("load_duration") or 0) / 1e6) or None,
        ),
    )


def chat(
    model: str,
    messages: list[dict],
    tools: bool = True,
    harness: dict | None = None,
    sampling: dict | None = None,
    timeout: int = 600,
    tool_schemas: list | None = None,
) -> dict:
    """One completion under explicit harness dimensions.
    Returns {message, finish_reason, economics, harness_caveats, resolved_think}.

    The wire is streamed unless the harness sets `wire_stream: False` (the
    preflight parity arm). `timeout` is the STALL threshold — no bytes for that
    long aborts with StreamStalledError — not a total-time cap; a model that keeps
    emitting tokens runs to a generous hard ceiling. This is deliberate: a large
    model under memory pressure is slow, not broken, and a blind deadline would
    discard real work and mislabel the model."""
    h = {**HARNESS_DEFAULTS, **(harness or {})}
    endpoint = h["endpoint"]
    wire_stream = h.get("wire_stream", True)
    think = h["think"]
    if think == "default":
        think = think_policy(model)
    schemas = TOOL_SCHEMAS if tool_schemas is None else tool_schemas
    url, payload, caveats = _build_payload(
        model, messages, h, dict(sampling or {}), schemas if tools else None, think, wire_stream
    )
    # `timeout` is the caller's remaining budget for this one call. The stall
    # threshold is the smaller of STALL_S and that budget; the hard ceiling for
    # a single call IS that budget, so a task never overruns its wall budget
    # even though no individual generation is cut off while tokens still flow.
    hard_s = max(30, int(timeout))
    stall_s = min(STALL_S, hard_s)
    t0 = time.monotonic()
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=stall_s) as r:
            if wire_stream:
                lines = _iter_lines_with_stall(r, stall_s, hard_s, model)
                msg, finish, econ = _read_stream(endpoint, lines)
            else:
                msg, finish, econ = _read_response(endpoint, r)
    except TimeoutError as e:
        raise StreamStalledError(f"{model}: no response headers for {stall_s}s ({e})") from e
    econ.wall_s = round(time.monotonic() - t0, 2)
    return {
        "message": msg,
        "finish_reason": finish,
        "economics": econ,
        "harness_caveats": caveats,
        "resolved_think": think,
    }


def _tool_probe(model: str, endpoint: str) -> dict:
    """Live tool-call probe: does the model emit a call, and do its arguments
    decode to an object under THIS endpoint's contract? This is the check that
    would have caught the v1 string-arguments defect before a campaign."""
    try:
        r = chat(
            model,
            [
                {
                    "role": "user",
                    "content": "List the files in the current directory using the file_list tool.",
                }
            ],
            tools=True,
            harness={"endpoint": endpoint, "think": "default"},
            sampling={"temperature": 0.0, "seed": 7, "max_tokens": 256},
            timeout=180,
        )
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}
    calls = (r.get("message") or {}).get("tool_calls") or []
    if not calls:
        return {"emitted_call": False, "parsed_ok": False, "note": "no tool call emitted"}
    raw = (calls[0].get("function") or {}).get("arguments")
    args, err = normalize_tool_args(raw)
    return {
        "emitted_call": True,
        "parsed_ok": err is None,
        "arg_type": type(raw).__name__,
        "error": err,
    }


def preflight_harness(model: str) -> dict:
    """Harness self-test. Deterministic by construction: temperature 0 and a
    fixed seed, so stream parity is a real signal rather than sampling noise
    (the previous version compared two default-temperature generations for exact
    string equality, flagging REVIEW at random — and per WFE-0.8 rule 2 that
    would have blocked nearly every model's campaign). The strict-JSON arm now
    actually sets format:json, so it exercises the gpt-oss harmony breakage
    class it was written to detect."""
    out: dict = {
        "model": model,
        "resolved_think_policy": think_policy(model),
        "card_format_json_safe": format_json_policy(model),
        "notes": [],
    }
    msgs = [{"role": "user", "content": "Reply with exactly: OK"}]
    det = {"temperature": 0.0, "seed": 7, "max_tokens": 64}

    def _run(harness, messages=None):
        try:
            r = chat(
                model,
                messages or msgs,
                tools=False,
                harness=harness,
                sampling=dict(det),
                timeout=180,
            )
            return {
                "content": ((r.get("message") or {}).get("content") or "").strip(),
                "finish_reason": r.get("finish_reason"),
                "caveats": r.get("harness_caveats") or [],
            }
        except Exception as e:
            return {"error": f"{type(e).__name__}: {e}"}

    json_msgs = [
        {"role": "system", "content": 'Reply with exactly {"ok": true} and nothing else.'},
        {"role": "user", "content": "go"},
    ]
    out["api_native"] = _run({"endpoint": "api", "think": "default"})
    out["api_strict_json"] = _run(
        {"endpoint": "api", "think": "false", "format": "json"}, json_msgs
    )
    ns = _run({"endpoint": "api", "think": "default", "wire_stream": False})
    st = _run({"endpoint": "api", "think": "default", "wire_stream": True})
    out["stream_nonstream"] = {"ns": ns, "stream": st}
    out["v1"] = _run({"endpoint": "v1", "think": "default"})
    out["v1_tools"] = _tool_probe(model, "v1")

    findings = []
    if out["v1"].get("error"):
        findings.append("v1 endpoint unreachable — the production path cannot be measured")
    card_json_safe = out["card_format_json_safe"]
    sj = out["api_strict_json"]
    sj_content = sj.get("content") or ""
    if sj.get("error"):
        findings.append("strict-json arm errored")
    elif not sj_content or not _is_json_object(sj_content):
        kind = "empty" if not sj_content else "degenerate (not a JSON object)"
        reconcile = (
            "confirmed against the model card (format_json_safe: false)"
            if card_json_safe is False
            else "NOT predicted by the model card — card ground truth owed (WFE-0.6)"
        )
        findings.append(
            f"{kind} content under format:json + think:false — harmony/template conflict "
            f"(gpt-oss class); this model must not run strict-JSON tasks; {reconcile}. "
            f"Observed: {sj_content[:60]!r}"
        )
    elif card_json_safe is False:
        out["notes"].append(
            "model card records format_json_safe: false but the strict-JSON arm returned "
            f"a clean JSON object ({sj_content[:40]!r}) — the card may be stale, re-verify"
        )
    if ns.get("error") or st.get("error"):
        findings.append("stream/non-stream arm errored")
    elif ns.get("content") != st.get("content"):
        findings.append(
            f"stream parity mismatch at temperature 0: ns={ns.get('content', '')[:40]!r} "
            f"st={st.get('content', '')[:40]!r}"
        )
    if out["v1_tools"].get("error"):
        findings.append(f"tool probe failed on v1: {out['v1_tools']['error']}")
    elif not out["v1_tools"].get("parsed_ok"):
        findings.append("v1 tool-call arguments did not decode to an object")

    out["stream_parity"] = "MISMATCH" if any("parity" in f for f in findings) else "OK"
    out["findings"] = findings
    out["verdict"] = "OK" if not findings else "REVIEW"
    return out


def resolve_persona(ws_id: str, override: str | None = None) -> tuple[str | None, str]:
    """Deterministic persona selection, recorded in every result row. auto-coding
    has 40 personas bound to it and auto-security 10; the previous
    first-glob-wins scan made the measured system prompt arbitrary and
    machine-dependent."""
    candidates = []
    for pf in sorted((REPO / "config/personas").glob("*.yaml")):
        d = yaml.safe_load(pf.read_text()) or {}
        if d.get("workspace_model") == ws_id and d.get("system_prompt"):
            candidates.append((d.get("slug") or pf.stem, d["system_prompt"]))
    candidates.sort(key=lambda c: c[0])
    if override:
        for slug, sp in candidates:
            if slug == override:
                return slug, sp
        raise SystemExit(f"persona '{override}' not bound to workspace {ws_id}")
    if candidates:
        return candidates[0]
    return None, ""


def workspace_context(ws_id: str, persona: str | None = None) -> dict:
    portal = yaml.safe_load((REPO / "config/portal.yaml").read_text())
    ws = portal["workspaces"][ws_id]
    slug, sp = resolve_persona(ws_id, persona)
    if not sp:
        sp = (ws.get("description") or "") + "\nPerform the user's task faithfully."
    declared = list(ws.get("tools") or [])
    surface = [t for t in TOOL_NAMES if t in declared] or TOOL_NAMES
    # Production sampling fidelity (dimension 8): every workspace in
    # portal.yaml declares its own sampling block. A temperature-0 pass is not
    # evidence about a product served at temperature 0.7, so the campaign runs
    # each workspace at ITS OWN settings rather than at a harness default.
    sampling = {
        k: ws[k]
        for k in ("temperature", "top_p", "top_k", "min_p", "repeat_penalty", "presence_penalty")
        if ws.get(k) is not None
    }
    if ws.get("predict_limit"):
        sampling["max_tokens"] = int(ws["predict_limit"])
    return {
        "model": ws.get("model_hint"),
        "system_prompt": sp,
        "persona_slug": slug,
        "persona_candidates": len(
            [
                1
                for pf in (REPO / "config/personas").glob("*.yaml")
                if (yaml.safe_load(pf.read_text()) or {}).get("workspace_model") == ws_id
            ]
        ),
        "declared_tools": declared,
        "tool_surface": surface,
        "tool_surface_proxy": sorted(surface) != sorted(declared),
        "context_limit": ws.get("context_limit"),
        "module": ws.get("module"),
        "sampling": sampling,
        "pinned_seed": ws.get("seed"),
        "declared_temperature": ws.get("temperature"),
    }


def _execute_calls(calls: list, turn: int, sandbox: Sandbox, tool_log: list, messages: list) -> int:
    """Dispatch one turn's tool calls and append production-shaped results.

    Two contracts matter here and both were previously wrong: arguments arrive
    as a JSON string on /v1, and every tool result must carry its tool_call_id
    (portal/platform/inference/router/tools.py). Returns the error count."""
    errors = 0
    for i, c in enumerate(calls):
        fn = c.get("function") or {}
        name = fn.get("name") or ""
        call_id = c.get("id") or f"call_{turn}_{i}"
        args, err = normalize_tool_args(fn.get("arguments"))
        if err:
            out = f"ERROR: {err}"
            errors += 1
        else:
            out = sandbox.dispatch(name, args)
            if str(out).startswith("ERROR:"):
                errors += 1
        tool_log.append(
            {
                "name": name,
                "args": args,
                "raw_args": str(fn.get("arguments"))[:500],
                "output": str(out)[:4000],
                "error": bool(err),
            }
        )
        messages.append(
            {
                "role": "tool",
                "tool_call_id": call_id,
                "name": name,
                "content": str(out)[:4000],
            }
        )
    return errors


def _classify(
    task: dict,
    ctx: CheckContext,
    transcript: list,
    override,
    tool_log: list,
    tool_errors: int,
) -> tuple[Outcome, str, dict]:
    """Turn checker output plus run telemetry into one terminal outcome. The
    ordering matters: an instrument failure must outrank a model failure."""
    if override is Outcome.HARNESS_ERROR:
        note = (
            transcript[-1].get("harness_error", "harness error") if transcript else "harness error"
        )
        return Outcome.HARNESS_ERROR, note, {}
    cr = apply_checkers(task, ctx)
    outcome, notes, evidence = cr.outcome, cr.notes, cr.evidence
    if override is Outcome.BUDGET_EXHAUSTED and outcome != Outcome.PASS:
        outcome, notes = Outcome.BUDGET_EXHAUSTED, "budget exhausted | " + notes
    if outcome == Outcome.FAIL and tool_log and tool_errors == len(tool_log):
        outcome = Outcome.TOOL_ERROR
        notes = "every tool call errored — instrument suspect | " + notes
    return outcome, notes, evidence


def _empty_result(outcome: Outcome, notes: str) -> dict:
    """A no-run task result (BLOCKED / early HARNESS_ERROR) in run_task's shape."""
    return {
        "outcome": outcome.value,
        "notes": notes,
        "evidence": {},
        "turns": 0,
        "tool_calls": 0,
        "tool_errors": 0,
        "finish_reason": None,
        "economics": Economics().__dict__,
        "final_text": "",
        "final_text_head": "",
        "transcript": [],
        "tool_call_log": [],
    }


def run_task(
    model: str,
    system_prompt: str,
    task: dict,
    sandbox: Sandbox,
    max_turns: int,
    budget_s: int,
    use_tools: bool,
    harness: dict | None = None,
    sampling: dict | None = None,
    tool_surface: list[str] | None = None,
) -> dict:
    """Run one fitness task to completion, then apply its checkers."""
    if task.get("requires_network") and not network_ok():
        # No outbound network here: http_get would fail on every call and a
        # fetch-grounded checker would score the model 0 for the instrument's
        # gap. BLOCKED, excluded from every rate — not the FAIL the previous
        # version recorded.
        return _empty_result(
            Outcome.BLOCKED, "requires_network but the harness has no outbound network"
        )
    for seed_path, seed_body in (task.get("seed") or {}).items():
        sandbox.file_write(seed_path, seed_body)

    schemas = (
        [t for t in TOOL_SCHEMAS if t["function"]["name"] in tool_surface]
        if tool_surface
        else TOOL_SCHEMAS
    )
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": task["instruction"]},
    ]
    transcript: list = []
    tool_log: list = []
    assistant_texts: list = []
    econ = Economics()
    t0 = time.monotonic()
    final_text = ""
    finish_reason = None
    outcome_override = None
    tool_errors = 0

    for turn in range(max_turns):
        remaining = budget_s - (time.monotonic() - t0)
        if remaining <= 5:
            outcome_override = Outcome.BUDGET_EXHAUSTED
            break
        try:
            resp = chat(
                model,
                messages,
                tools=use_tools,
                harness=harness,
                sampling=sampling,
                timeout=int(remaining),
                tool_schemas=schemas if use_tools else None,
            )
        except Exception as e:
            # A stall (backend accepted the request then went quiet) is the
            # model's problem — a real fitness verdict, too slow for its lane —
            # so it is BUDGET_EXHAUSTED, never HARNESS_ERROR.
            stalled = isinstance(e, StreamStalledError | TimeoutError)
            outcome_override = Outcome.BUDGET_EXHAUSTED if stalled else Outcome.HARNESS_ERROR
            key = "stalled" if stalled else "harness_error"
            transcript.append({"turn": turn, key: f"{type(e).__name__}: {e}"})
            break

        econ.merge(resp["economics"])
        finish_reason = resp.get("finish_reason") or finish_reason
        msg = resp.get("message") or {}
        content = msg.get("content") or ""
        calls = msg.get("tool_calls") or []
        transcript.append(
            {
                "turn": turn,
                "content": content[:2000],
                "tool_calls": [
                    {
                        "name": (c.get("function") or {}).get("name"),
                        "args_raw": str((c.get("function") or {}).get("arguments"))[:500],
                    }
                    for c in calls
                ],
            }
        )
        if content:
            assistant_texts.append(content)

        if calls:
            messages.append({"role": "assistant", "content": content, "tool_calls": calls})
            tool_errors += _execute_calls(calls, turn, sandbox, tool_log, messages)
            continue

        final_text = content
        messages.append({"role": "assistant", "content": content})
        if task.get("completion_signal") and re.search(task["completion_signal"], content, re.I):
            break
        if not task.get("agentic"):
            break
    else:
        # The loop ran every turn without breaking — an agentic task that kept
        # calling tools and never delivered an answer. That is a turn-budget
        # exhaustion (the model didn't get to finish), not a wrong answer, so
        # it is BUDGET_EXHAUSTED, not a content FAIL against an empty string.
        if not final_text:
            outcome_override = outcome_override or Outcome.BUDGET_EXHAUSTED
            transcript.append(
                {"turn": max_turns, "exhausted_turns": f"no final answer in {max_turns} turns"}
            )

    econ.wall_s = round(time.monotonic() - t0, 1)
    if not final_text and assistant_texts:
        final_text = assistant_texts[-1]
    return _finalize_run(
        task,
        final_text,
        assistant_texts,
        tool_log,
        sandbox,
        finish_reason,
        transcript,
        outcome_override,
        tool_errors,
        econ,
    )


def _finalize_run(
    task,
    final_text,
    assistant_texts,
    tool_log,
    sandbox,
    finish_reason,
    transcript,
    outcome_override,
    tool_errors,
    econ,
) -> dict:
    """Grade the completed run and assemble its result row."""
    ctx = CheckContext(
        final_text=final_text,
        assistant_texts=assistant_texts,
        tool_calls=tool_log,
        sandbox_root=sandbox.root,
        task=task,
        finish_reason=finish_reason,
    )
    outcome, notes, evidence = _classify(
        task, ctx, transcript, outcome_override, tool_log, tool_errors
    )
    return {
        "outcome": outcome.value,
        "notes": notes,
        "evidence": evidence,
        "turns": len(transcript),
        "tool_calls": len(tool_log),
        "tool_errors": tool_errors,
        "finish_reason": finish_reason,
        "economics": econ.__dict__,
        "final_text": final_text,
        "final_text_head": final_text[:600],
        "transcript": transcript,
        # Full tool output (already capped at 4000 in _execute_calls). The
        # previous re-truncation to 300 meant an offline --rescore of the
        # contamination checker (forbid_in_tool_output) saw less than the live
        # run, so a leaked answer key past char 300 was caught live, not on
        # re-grade.
        "tool_call_log": tool_log,
    }


def load_suite(path: str | Path) -> list[dict]:
    return [json.loads(x) for x in Path(path).read_text().splitlines() if x.strip()]


def make_sandbox(root: Path, task_id: str, repeat: int, fresh: bool = True) -> Sandbox:
    """Per (task, repeat) sandbox. Sharing one directory across tasks let task N
    inherit task N-1's files — pytest_run collected both — and let a later arm
    pass on an earlier arm's implementation."""
    d = Path(root) / f"{task_id}__r{repeat}"
    if fresh and d.exists():
        shutil.rmtree(d, ignore_errors=True)
    return Sandbox(d)


def _row(label, args, ctxinfo, model, task, r, harness, sampling, env, system_prompt) -> dict:
    return ResultRow(
        run_id=f"{label}__{task['id']}__r{args.repeat}",
        workspace=args.workspace,
        arm=model,
        suite=str(args.suite),
        task_id=task["id"],
        repeat=args.repeat,
        outcome=r["outcome"],
        notes=r["notes"],
        evidence=r["evidence"],
        persona_slug=ctxinfo.get("persona_slug"),
        prompt_sha=sha12(system_prompt),
        tool_surface=ctxinfo.get("tool_surface") or TOOL_NAMES,
        tool_surface_proxy=bool(ctxinfo.get("tool_surface_proxy", True)),
        harness=harness,
        sampling=sampling,
        seed=args.seed,
        turns=r["turns"],
        tool_calls=r["tool_calls"],
        tool_errors=r["tool_errors"],
        finish_reason=r["finish_reason"],
        economics=r["economics"],
        env=env,
        final_text_head=r["final_text_head"],
        transcript=r["transcript"],
        tool_call_log=r["tool_call_log"],
    ).to_dict()


def _parse_args(argv=None):
    ap = argparse.ArgumentParser()
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--workspace", help="portal.yaml workspace id")
    src.add_argument("--model", help="raw model tag arm")
    ap.add_argument("--persona", help="explicit persona slug (default: first by sorted slug)")
    ap.add_argument("--system-prompt-file")
    ap.add_argument("--suite")
    ap.add_argument("--sandbox", default="/tmp/wfe/run")
    ap.add_argument("--max-turns", type=int, default=8)
    ap.add_argument("--budget-s", type=int, default=600)
    ap.add_argument("--repeat", type=int, default=0)
    ap.add_argument("--temperature", type=float)
    ap.add_argument("--seed", type=int)
    ap.add_argument("--max-tokens", type=int, default=2048)
    ap.add_argument("--no-tools", action="store_true")
    ap.add_argument("--label", default="")
    ap.add_argument("--endpoint", choices=["v1", "api"], default="v1")
    ap.add_argument("--stream", action="store_true")
    ap.add_argument("--think", choices=["default", "true", "false"], default="default")
    ap.add_argument("--format", choices=["none", "json"], default="none")
    ap.add_argument("--preflight", action="store_true")
    return ap, ap.parse_args(argv)


def main() -> int:
    ap, args = _parse_args()

    ctxinfo = workspace_context(args.workspace, args.persona) if args.workspace else {}
    model = args.model or ctxinfo.get("model")

    if args.preflight:
        if not model:
            ap.error("--preflight needs --model or --workspace")
        print(json.dumps(preflight_harness(model), indent=1))
        return 0
    if not args.suite:
        ap.error("--suite is required unless --preflight")

    system_prompt = (
        Path(args.system_prompt_file).read_text()
        if args.system_prompt_file
        else ctxinfo.get("system_prompt", "")
    )
    harness = {
        "endpoint": args.endpoint,
        "stream": args.stream,
        "think": args.think,
        "format": args.format,
    }
    sampling = {"max_tokens": args.max_tokens}
    if args.temperature is not None:
        sampling["temperature"] = args.temperature
    if args.seed is not None:
        sampling["seed"] = args.seed

    env = env_fingerprint(OLLAMA)
    tasks = load_suite(args.suite)
    label = args.label or (args.workspace or model).replace("/", "_")
    if args.workspace:
        print(
            f"workspace {args.workspace}: model={model} persona={ctxinfo.get('persona_slug')} "
            f"(of {ctxinfo.get('persona_candidates')} bound) tools={ctxinfo.get('tool_surface')}"
        )
    rows = []
    for t in tasks:
        sb = make_sandbox(Path(args.sandbox), t["id"], args.repeat)
        print(f"--- {t['id']}: {t['instruction'][:80]}...", flush=True)
        r = run_task(
            model,
            system_prompt,
            t,
            sb,
            args.max_turns,
            args.budget_s,
            use_tools=not args.no_tools,
            harness=harness,
            sampling=sampling,
            tool_surface=ctxinfo.get("tool_surface"),
        )
        rows.append(_row(label, args, ctxinfo, model, t, r, harness, sampling, env, system_prompt))
        print(
            f"    outcome={r['outcome']} turns={r['turns']} tools={r['tool_calls']} "
            f"tool_errors={r['tool_errors']} {r['economics'].get('wall_s')}s"
        )

    RESULTS.mkdir(parents=True, exist_ok=True)
    ts = dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%SZ")
    out = RESULTS / f"wfe_{label}_{ts}.json"
    out.write_text(json.dumps({"env": env, "results": rows}, indent=1))
    tally: dict = {}
    for r in rows:
        tally[r["outcome"]] = tally.get(r["outcome"], 0) + 1
    print(f"\noutcomes: {tally} -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
