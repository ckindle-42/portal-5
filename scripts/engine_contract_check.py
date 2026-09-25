#!/usr/bin/env python3
"""Live proof that the values Portal sends reach the model, per inference engine.

Why this exists: on 2026-09-25 it was found that Ollama's /v1 had silently
dropped every Ollama workspace's sampling for its whole life (the `options`
object is ignored; missing temperature/top_p are forced to 1.0), and that the
WFE harness sent oMLX a `repeat_penalty` it ignores. Nothing failed loudly —
the requests all returned 200. Only a behavioural probe catches this class, and
it has to be re-run whenever an engine changes, because Ollama ships often and
oMLX has major versions ahead.

Every probe builds its request with PRODUCTION's own code
(`router.validation._inject_ollama_options` / `_inject_omlx_options` from a
synthetic workspace) and sends it the way production does (Ollama through
`ollama_native.OllamaNativeTransport`). A key counts as delivered only when it
visibly changes the output, against a control that shows the probe could have
seen the difference:
  top_k=1 / min_p=1 / top_p=0.001 / temperature=0 -> 3 seeds collapse to 1 output
  repeat_penalty / presence_penalty at 2.0        -> a temperature-0 output changes
  seed                                            -> same seed, same output at 1.5
  max_tokens                                      -> completion_tokens <= cap
  think false / true                              -> reasoning absent / present
Ollama additionally proves the adapter answers exactly as /v1 would (content,
tool calls, finish_reason, prompt_tokens — equal prompt tokens mean the
messages rendered identically) for text, tools, a tool-result turn, a
non-thinking model and image parts.

Usage:
  uv run python scripts/engine_contract_check.py                 # both engines
  uv run python scripts/engine_contract_check.py ollama
  uv run python scripts/engine_contract_check.py --if-changed    # launchd: only
      when an engine version differs from the last verified one, or the last
      pass is older than 7 days
Exit 0 = all delivered; 1 = a contract failure (Pushover when configured);
2 = could not run (engine down, probe model missing).
State: ~/.portal5/engine_contract.json. Probe models: config/engine_contract.yaml.
"""

from __future__ import annotations

import asyncio
import base64
import datetime as dt
import json
import os
import struct
import subprocess
import sys
import zlib
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
import yaml

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from portal.platform.inference.ollama_native import OllamaNativeTransport  # noqa: E402
from portal.platform.inference.router import validation  # noqa: E402

# Host-side URLs. Deliberately NOT OLLAMA_URL/OMLX_URL: .env sets those to the
# container-facing host.docker.internal, which a host process cannot resolve.
OLLAMA = os.environ.get("ENGINE_CONTRACT_OLLAMA_URL", "http://localhost:11434").rstrip("/")
OMLX = os.environ.get("ENGINE_CONTRACT_OMLX_URL", "http://localhost:8085").rstrip("/")
STATE = Path.home() / ".portal5" / "engine_contract.json"
PROBES = REPO / "config" / "engine_contract.yaml"
MAX_AGE_DAYS = 7
_CHAT = "/v1/chat/completions"
_WS = "__engine_contract_probe__"
_SENTENCE = "Write one unusual sentence about a lighthouse."
_LIST = "List ten fruits, one per line, then list them again."


@dataclass
class Result:
    name: str
    ok: bool
    detail: str


class CannotRunError(RuntimeError):
    """The check could not be performed (engine down, probe model missing)."""


# ── shared probe mechanics ──────────────────────────────────────────────────


Send = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]


def _text(r: dict[str, Any]) -> str:
    return (r["choices"][0]["message"].get("content") or "").strip()


def _reasoning(r: dict[str, Any]) -> str:
    m = r["choices"][0]["message"]
    return str(m.get("reasoning") or m.get("reasoning_content") or "")


async def _distinct(send: Send, base: dict[str, Any], seeds: int = 3) -> int:
    return len({_text(await send(base | {"seed": s})) for s in range(seeds)})


async def _delivery(
    send: Send,
    build: Callable[[dict[str, Any]], dict[str, Any]],
    unimplemented: frozenset[str] = frozenset(),
) -> list[Result]:
    """The behavioural delivery probes. `build(ws_cfg)` returns the request body
    production would send for a workspace configured with `ws_cfg`."""
    out: list[Result] = []
    hot = {"messages": [{"role": "user", "content": _SENTENCE}], "max_tokens": 30}
    control = await _distinct(send, build({"temperature": 1.5, "think": False}) | hot)
    if control < 2:
        raise CannotRunError(f"control produced {control} distinct output(s) at temperature 1.5")
    for key, val in (("top_k", 1), ("min_p", 1.0), ("top_p", 0.001)):
        n = await _distinct(send, build({"temperature": 1.5, key: val, "think": False}) | hot)
        out.append(
            Result(f"{key} delivered", n == 1, f"{n} distinct over 3 seeds (control {control})")
        )
    n = await _distinct(send, build({"temperature": 0.0, "think": False}) | hot)
    out.append(Result("temperature delivered", n == 1, f"{n} distinct at 0 (control {control})"))
    a = _text(await send(build({"temperature": 1.5, "think": False}) | hot | {"seed": 11}))
    b = _text(await send(build({"temperature": 1.5, "think": False}) | hot | {"seed": 11}))
    out.append(Result("seed delivered", a == b, "same seed reproduced" if a == b else "differed"))

    lst = {"messages": [{"role": "user", "content": _LIST}], "max_tokens": 80}
    base_txt = _text(await send(build({"temperature": 0.0, "think": False}) | lst))
    for key in ("repeat_penalty", "presence_penalty"):
        pen = _text(await send(build({"temperature": 0.0, key: 2.0, "think": False}) | lst))
        changed = pen != base_txt
        if key in unimplemented:
            # Reaches the engine but its sampler does nothing with it — a known
            # engine limitation (KNOWN_LIMITATIONS.md), not a delivery failure.
            # If it starts working, that is news worth surfacing.
            detail = (
                "NOW HAS EFFECT — update the limitation" if changed else "known: engine ignores it"
            )
            out.append(Result(f"info: {key}", True, detail))
            continue
        out.append(
            Result(f"{key} delivered", changed, "output changed" if changed else "no effect")
        )
    r = await send(build({"think": False}) | hot | {"max_tokens": 5})
    ct = (r.get("usage") or {}).get("completion_tokens")
    out.append(
        Result("max_tokens delivered", ct is not None and ct <= 5, f"completion_tokens={ct}")
    )

    think_q = {"messages": [{"role": "user", "content": "What is 17*23?"}], "max_tokens": 600}
    off = _reasoning(await send(build({"temperature": 0.0, "think": False}) | think_q))
    on = _reasoning(await send(build({"temperature": 0.0, "think": True}) | think_q))
    out.append(Result("think:false delivered", not off, f"{len(off)} reasoning chars"))
    out.append(Result("think:true delivered", bool(on), f"{len(on)} reasoning chars"))
    return out


def _probe_workspace(cfg: dict[str, Any]) -> None:
    validation.WORKSPACES[_WS] = cfg


# ── Ollama ──────────────────────────────────────────────────────────────────


def _ollama_version() -> str:
    try:
        return str(httpx.get(f"{OLLAMA}/api/version", timeout=5).json()["version"])
    except Exception as e:
        raise CannotRunError(f"Ollama unreachable at {OLLAMA}: {e}") from e


def _png(rgb: tuple[int, int, int], side: int = 32) -> str:
    raw = b"".join(b"\x00" + bytes(rgb) * side for _ in range(side))

    def chunk(tag: bytes, data: bytes) -> bytes:
        body = tag + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))

    png = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", side, side, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )
    return "data:image/png;base64," + base64.b64encode(png).decode()


def _view(r: httpx.Response) -> dict[str, Any]:
    j = r.json()
    ch = j["choices"][0]
    m = ch["message"]
    return {
        "status": r.status_code,
        "content": m.get("content"),
        "tools": [
            (t["function"]["name"], t["function"]["arguments"]) for t in m.get("tool_calls") or []
        ],
        "finish": ch["finish_reason"],
        "prompt_tokens": j["usage"]["prompt_tokens"],
    }


async def _parity(
    raw: httpx.AsyncClient, nat: httpx.AsyncClient, models: dict[str, str]
) -> list[Result]:
    """Adapter vs Ollama's own /v1 on identical requests (temperature 0)."""
    tools = [
        {
            "type": "function",
            "function": {
                "name": "get_weather",
                "description": "weather",
                "parameters": {
                    "type": "object",
                    "properties": {"city": {"type": "string"}},
                    "required": ["city"],
                },
            },
        }
    ]
    tm = models["thinking_tools"]
    ask = [{"role": "user", "content": "What's the weather in Paris? Use the tool."}]
    first = await raw.post(
        OLLAMA + _CHAT,
        json={"model": tm, "messages": ask, "tools": tools, "temperature": 0, "seed": 1},
    )
    calls = first.json()["choices"][0]["message"].get("tool_calls") or []
    cases: list[tuple[str, dict[str, Any]]] = [
        (
            "text",
            {
                "model": tm,
                "messages": [{"role": "user", "content": "Name three primary colors."}],
                "reasoning_effort": "none",
            },
        ),
        ("tool call", {"model": tm, "messages": ask, "tools": tools}),
        (
            "non-thinking model",
            {
                "model": models["non_thinking"],
                "messages": [{"role": "user", "content": "Say hello."}],
                "reasoning_effort": "none",
            },
        ),
        (
            "image parts",
            {
                "model": models["vision"],
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "What color is this image?"},
                            {"type": "image_url", "image_url": {"url": _png((220, 20, 20))}},
                        ],
                    }
                ],
            },
        ),
    ]
    if calls:
        turn = ask + [
            {"role": "assistant", "content": "", "tool_calls": calls},
            {"role": "tool", "tool_call_id": calls[0]["id"], "content": "18C, light rain"},
        ]
        cases.append(
            (
                "tool-result turn",
                {"model": tm, "messages": turn, "tools": tools, "reasoning_effort": "none"},
            )
        )
    out = [Result("tool call emitted for parity", bool(calls), f"{len(calls)} call(s)")]
    for name, body in cases:
        body = body | {"temperature": 0, "seed": 1, "max_tokens": 300}
        a = _view(await raw.post(OLLAMA + _CHAT, json=body))
        b = _view(await nat.post(OLLAMA + _CHAT, json=body))
        diff = {k: (a[k], b[k]) for k in a if a[k] != b[k]}
        out.append(
            Result(
                f"parity: {name}", not diff, "identical" if not diff else f"v1 vs adapter {diff}"
            )
        )
    return out


async def check_ollama(models: dict[str, str]) -> list[Result]:
    async with (
        httpx.AsyncClient(timeout=600) as raw,
        httpx.AsyncClient(
            timeout=600,
            transport=OllamaNativeTransport(httpx.AsyncHTTPTransport(), lambda b: b == OLLAMA),
        ) as nat,
    ):
        tags = {m["name"] for m in (await raw.get(f"{OLLAMA}/api/tags")).json()["models"]}
        missing = sorted(set(models.values()) - tags)
        if missing:
            raise CannotRunError(f"Ollama probe model(s) not installed: {missing}")

        async def send(body: dict[str, Any]) -> dict[str, Any]:
            r = await nat.post(OLLAMA + _CHAT, json=body)
            r.raise_for_status()
            return dict(r.json())

        def build(cfg: dict[str, Any]) -> dict[str, Any]:
            _probe_workspace(cfg)
            return validation._inject_ollama_options({"model": models["thinking_tools"]}, _WS)

        # Ollama's sampler accepts presence_penalty and applies nothing — measured
        # on /api/chat itself (2026-09-25, 0.34.2), so no transport can fix it.
        results = await _delivery(send, build, frozenset({"presence_penalty"}))
        results += await _parity(raw, nat, models)
        # Informational: if Ollama's /v1 ever starts honouring top_k natively the
        # adapter's reason to exist has shrunk — worth knowing, not a failure.
        hot = {
            "model": models["thinking_tools"],
            "messages": [{"role": "user", "content": _SENTENCE}],
            "max_tokens": 30,
            "temperature": 1.5,
            "top_k": 1,
            "reasoning_effort": "none",
        }
        seen = {
            _text((await raw.post(OLLAMA + _CHAT, json=hot | {"seed": s})).json()) for s in range(3)
        }
        results.append(
            Result(
                "info: raw /v1 honours top_k",
                True,
                "YES — review adapter" if len(seen) == 1 else "no (adapter still required)",
            )
        )
        return results


# ── oMLX ────────────────────────────────────────────────────────────────────


def _omlx_version() -> str:
    try:
        httpx.get(f"{OMLX}/health", timeout=5).raise_for_status()
    except Exception as e:
        raise CannotRunError(f"oMLX unreachable at {OMLX}: {e}") from e
    try:
        out = subprocess.run(
            ["brew", "list", "--versions", "jundot/omlx/omlx"],
            capture_output=True,
            text=True,
            timeout=30,
        ).stdout.split()
        return out[-1] if out else "unknown"
    except Exception:
        return "unknown"


async def check_omlx(models: dict[str, str]) -> list[Result]:
    async with httpx.AsyncClient(timeout=600) as client:
        served = {m["id"] for m in (await client.get(f"{OMLX}/v1/models")).json()["data"]}
        missing = sorted(set(models.values()) - served)
        if missing:
            raise CannotRunError(f"oMLX probe model(s) not served: {missing}")

        async def send(body: dict[str, Any]) -> dict[str, Any]:
            r = await client.post(OMLX + _CHAT, json=body)
            r.raise_for_status()
            return dict(r.json())

        def build(cfg: dict[str, Any]) -> dict[str, Any]:
            _probe_workspace(cfg)
            return validation._inject_omlx_options({"model": models["thinking_tools"]}, _WS)

        return await _delivery(send, build)


# ── runner ──────────────────────────────────────────────────────────────────

ENGINES: dict[
    str, tuple[Callable[[], str], Callable[[dict[str, str]], Awaitable[list[Result]]]]
] = {
    "ollama": (_ollama_version, check_ollama),
    "omlx": (_omlx_version, check_omlx),
}


def _load_state() -> dict[str, Any]:
    try:
        return dict(json.loads(STATE.read_text()))
    except Exception:
        return {}


def _due(state: dict[str, Any], engine: str, version: str) -> bool:
    last = state.get(engine) or {}
    if last.get("version") != version or not last.get("ok"):
        return True
    try:
        age = dt.datetime.now(dt.UTC) - dt.datetime.fromisoformat(last["verified_utc"])
    except Exception:
        return True
    return age > dt.timedelta(days=MAX_AGE_DAYS)


def _notify(title: str, message: str) -> None:
    try:
        from scripts.check_updates import _pushover  # noqa: PLC0415

        _pushover(title, message, high=True)
    except Exception as e:  # never let alerting mask the verdict
        print(f"notify failed: {e}", file=sys.stderr)


def main(argv: list[str]) -> int:
    if_changed = "--if-changed" in argv
    wanted = [a for a in argv if not a.startswith("-")] or list(ENGINES)
    probes = yaml.safe_load(PROBES.read_text()) or {}
    state = _load_state()
    worst = 0
    for engine in wanted:
        version_fn, check = ENGINES[engine]
        try:
            version = version_fn()
            if if_changed and not _due(state, engine, version):
                print(f"[SKIP] {engine} {version}: verified {state[engine]['verified_utc']}")
                continue
            results = asyncio.run(check(dict(probes.get(engine) or {})))
        except CannotRunError as e:
            print(f"[CANNOT RUN] {engine}: {e}")
            worst = max(worst, 2)
            # A probe model that vanished after an engine change is most often the
            # macOS data01 permission popup waiting for 'Allow'.
            _notify(
                f"Engine contract cannot verify {engine}",
                f"{e}\nIf the engine was just updated, check the Mac for a data01 "
                "access popup and click Allow.",
            )
            continue
        failed = [r for r in results if not r.ok]
        print(f"[{'FAIL' if failed else 'OK'}] {engine} {version}")
        for r in results:
            print(f"    {'ok  ' if r.ok else 'FAIL'} {r.name}: {r.detail}")
        state[engine] = {
            "version": version,
            "ok": not failed,
            "verified_utc": dt.datetime.now(dt.UTC).isoformat(),
            "failed": [f"{r.name}: {r.detail}" for r in failed],
        }
        if failed:
            worst = max(worst, 1)
            _notify(
                f"Engine contract FAILED: {engine} {version}",
                "Values Portal sends are not reaching the model:\n"
                + "\n".join(f"- {r.name}: {r.detail}" for r in failed),
            )
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(state, indent=1))
    return worst


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
