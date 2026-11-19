"""Section 5 — engines, load-guard seat fit, and the P40 box."""

from __future__ import annotations

import contextlib
from dataclasses import dataclass, field

import httpx

from .context import TraceContext, run_cmd
from .model import Hop, Status, short

GIB = float(1024**3)
P40_HOST = "thebrain"


@dataclass(frozen=True)
class EngineModels:
    """Model ids each engine reports as present (not necessarily loaded)."""

    omlx: set[str] = field(default_factory=set)
    ollama: set[str] = field(default_factory=set)


def _names(values: list[object]) -> list[str]:
    out: list[str] = []
    for value in values:
        if isinstance(value, dict):
            name = str(value.get("id") or value.get("name") or "")
            if name:
                out.append(name)
    return out


def model_ids(payload: object) -> set[str]:
    """Every model id an OpenAI-shaped or oMLX-status payload lists."""
    if not isinstance(payload, dict):
        return set()
    ids = {str(entry) for entry in _names(payload.get("data") or [])}
    ids |= {str(entry) for entry in _names(payload.get("models") or [])}
    return {entry for entry in ids if entry}


def parse_omlx_status(payload: object) -> tuple[float | None, list[str], float | None]:
    """(ceiling GiB, loaded ids, resident GiB) from ``/v1/models/status``."""
    if not isinstance(payload, dict):
        return None, [], None
    ceiling = payload.get("final_ceiling")
    used = payload.get("current_model_memory")
    loaded = [
        str(entry.get("id") or entry.get("name") or "")
        for entry in payload.get("models") or []
        if isinstance(entry, dict) and entry.get("loaded")
    ]
    return (
        float(ceiling) / GIB if ceiling is not None else None,
        [entry for entry in loaded if entry],
        float(used) / GIB if used is not None else None,
    )


def parse_ollama_ps(payload: object) -> list[tuple[str, float]]:
    """(name, GiB) for every resident Ollama model."""
    if not isinstance(payload, dict):
        return []
    rows = []
    for entry in payload.get("models") or []:
        if not isinstance(entry, dict):
            continue
        name = str(entry.get("name") or entry.get("model") or "")
        size = entry.get("size")
        if name:
            rows.append((name, float(size) / GIB if size is not None else 0.0))
    return rows


def parse_seat_fit(payload: object) -> dict[str, list[str]]:
    """The fit verdict lists ``/admin/seat-fit`` publishes."""
    data = payload if isinstance(payload, dict) else {}
    return {
        key: [str(seat) for seat in data.get(key) or []]
        for key in (
            "never_fit",
            "undeclared_never_fit",
            "over_budget",
            "undeclared_over_budget",
            "unserved",
        )
    }


def seat_fit_basis(payload: object) -> str:
    """The memory budget the never_fit verdicts were measured against."""
    data = payload if isinstance(payload, dict) else {}
    available = data.get("available_gib")
    source = str(data.get("budget_source") or "")
    parts = []
    if isinstance(available, int | float):
        parts.append(f"available={float(available):.1f}GiB")
    if source:
        parts.append(source)
    return " ".join(parts)


def parse_nvidia_smi(text: str) -> dict[str, str]:
    """First GPU row of ``--query-gpu=pstate,clocks.current.graphics,power.limit,power.draw``."""
    for line in text.splitlines():
        parts = [part.strip() for part in line.split(",")]
        if len(parts) >= 4 and parts[0]:
            return {
                "pstate": parts[0],
                "clocks": parts[1],
                "power_limit": parts[2],
                "power_draw": parts[3],
            }
    return {}


def parse_nice_table(text: str) -> list[tuple[str, str, str]]:
    """Rows of ``ps -eo pid=,ni=,comm=`` as (pid, nice, command)."""
    rows = []
    for line in text.splitlines():
        parts = line.split(None, 2)
        if len(parts) == 3 and parts[0].isdigit():
            rows.append((parts[0], parts[1], parts[2].strip()))
    return rows


def _get_json(url: str, timeout: float, headers: dict[str, str] | None = None) -> object:
    response = httpx.get(url, timeout=timeout, headers=headers)
    response.raise_for_status()
    return response.json()


def fetch_engine_models(ctx: TraceContext, timeout: float = 15.0) -> EngineModels:
    """One cheap metadata read per engine; no generation happens here."""
    from portal.platform.inference.omlx_auth import omlx_headers

    omlx: set[str] = set()
    ollama: set[str] = set()
    with contextlib.suppress(httpx.HTTPError, ValueError):
        omlx = model_ids(_get_json(f"{ctx.omlx_url}/v1/models", timeout, omlx_headers()))
    with contextlib.suppress(httpx.HTTPError, ValueError):
        ollama = model_ids(_get_json(f"{ctx.ollama_url}/api/tags", timeout))
    return EngineModels(omlx=omlx, ollama=ollama)


def residency_hop(ctx: TraceContext, backend_id: str, model: str) -> Hop:
    """The engine the route header named must itself report the served model resident."""
    from portal.platform.inference.model_names import model_key
    from portal.platform.inference.omlx_auth import omlx_headers

    from .pins import BACKENDS_YAML, load_backends

    kinds = {b.backend_id: b.kind for b in load_backends(ctx.repo_root / BACKENDS_YAML)}
    kind, name = kinds.get(backend_id, ""), f"resident {backend_id}"
    try:
        if kind == "ollama":
            held = [n for n, _ in parse_ollama_ps(_get_json(f"{ctx.ollama_url}/api/ps", 10.0))]
        elif kind == "omlx":
            status = _get_json(f"{ctx.omlx_url}/v1/models/status", 10.0, omlx_headers())
            held = parse_omlx_status(status)[1]
        else:
            raise ValueError(f"{backend_id} is not declared in config/backends.yaml")
    except (httpx.HTTPError, ValueError) as exc:
        error = short(f"{type(exc).__name__}: {exc}", 70)
        return Hop(name, Status.WARN, f"{model} unconfirmed", "engine resident list", error)
    trimmed = {model_key(entry).removesuffix(":latest") for entry in held}
    present = model_key(model).removesuffix(":latest") in trimmed
    state = "resident" if present else f"not resident, {kind} lists {','.join(held[:4]) or 'none'}"
    return Hop(name, Status.PASS if present else Status.WARN, f"{model} {state}", kind)


def omlx_hop(ctx: TraceContext) -> Hop:
    from portal.platform.inference.omlx_auth import omlx_headers

    try:
        payload = _get_json(f"{ctx.omlx_url}/v1/models/status", 10.0, omlx_headers())
    except (httpx.HTTPError, ValueError) as exc:
        return Hop("omlx status", Status.FAIL, short(f"{type(exc).__name__}: {exc}", 70), "200")
    ceiling, loaded, used = parse_omlx_status(payload)
    if ceiling is None:
        return Hop("omlx status", Status.FAIL, "final_ceiling absent", "final_ceiling GiB")
    observed = f"ceiling={ceiling:.1f}GiB resident={used or 0:.1f}GiB loaded={len(loaded)}"
    return Hop("omlx status", Status.PASS, observed, "ceiling readable", ",".join(loaded[:4]))


def ollama_hop(ctx: TraceContext) -> Hop:
    try:
        rows = parse_ollama_ps(_get_json(f"{ctx.ollama_url}/api/ps", 10.0))
    except (httpx.HTTPError, ValueError) as exc:
        return Hop("ollama ps", Status.FAIL, short(f"{type(exc).__name__}: {exc}", 70), "200")
    total = sum(size for _, size in rows)
    detail = ", ".join(f"{name} {size:.1f}GiB" for name, size in rows[:3])
    return Hop(
        "ollama ps", Status.PASS, f"resident={len(rows)} {total:.1f}GiB", "reachable", detail
    )


def seat_fit_verdict(payload: object) -> Hop:
    """Never-fit (stable, fixed budget only) is a FAIL; over-budget (live snapshot) a WARN."""
    verdicts = parse_seat_fit(payload)
    undeclared = verdicts["undeclared_never_fit"]
    over = verdicts["undeclared_over_budget"]
    observed = (
        f"never_fit={len(verdicts['never_fit'])} over_budget={len(verdicts['over_budget'])}"
        f" unserved={len(verdicts['unserved'])}"
    )
    basis = seat_fit_basis(payload)
    if basis:
        observed += f" ({basis})"
    if undeclared:
        return Hop(
            "seat fit", Status.FAIL, observed, "every never_fit declared", ",".join(undeclared)
        )
    if over:
        return Hop(
            "seat fit", Status.WARN, observed, "every seat fits the live budget", ",".join(over)
        )
    status = Status.WARN if verdicts["never_fit"] or verdicts["unserved"] else Status.PASS
    detail = ",".join(verdicts["never_fit"] or verdicts["unserved"])
    return Hop("seat fit", status, observed, "every seat fits", detail)


def seat_fit_hop(ctx: TraceContext) -> Hop:
    try:
        response = httpx.post(
            f"{ctx.pipeline_url}/admin/seat-fit",
            headers={"Authorization": f"Bearer {ctx.api_key}"},
            timeout=ctx.timeout_s,
        )
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        return Hop("seat fit", Status.FAIL, short(f"{type(exc).__name__}: {exc}", 70), "200")
    return seat_fit_verdict(payload)


def p40_gpu_hop() -> Hop:
    command = (
        "nvidia-smi --query-gpu=pstate,clocks.current.graphics,power.limit,power.draw "
        "--format=csv,noheader,nounits"
    )
    result = run_cmd(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=8", P40_HOST, command])
    if not result.ok:
        return Hop(f"p40 {P40_HOST}", Status.FAIL, short(result.error, 70), "ssh + nvidia-smi")
    gpu = parse_nvidia_smi(result.stdout)
    if not gpu:
        return Hop(f"p40 {P40_HOST}", Status.FAIL, "no gpu row", "nvidia-smi output")
    observed = (
        f"pstate={gpu['pstate']} clocks={gpu['clocks']}MHz"
        f" limit={gpu['power_limit']}W draw={gpu['power_draw']}W"
    )
    return Hop(
        f"p40 {P40_HOST}",
        Status.WARN if gpu["pstate"] != "P0" else Status.PASS,
        observed,
        "P0 under load",
    )


def p40_ollama_hop() -> Hop:
    """The P40's Ollama runs un-niced, with the environment keys it was started with."""
    script = (
        "ps -eo pid=,ni=,comm= | grep -i ollama; "
        "for p in $(pgrep -x ollama); do tr '\\0' '\\n' < /proc/$p/environ; done | cut -d= -f1 | sort -u"
    )
    result = run_cmd(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=8", P40_HOST, script])
    if not result.ok:
        return Hop("p40 ollama", Status.FAIL, short(result.error, 70), "ssh reachable")
    rows = parse_nice_table(result.stdout)
    if not rows:
        return Hop("p40 ollama", Status.FAIL, "ollama not running", "process present")
    nicest = max(int(nice) for _, nice, _ in rows)
    keys = [line.strip() for line in result.stdout.splitlines() if line.startswith("OLLAMA")]
    return Hop(
        "p40 ollama",
        Status.WARN if nicest > 0 else Status.PASS,
        f"procs={len(rows)} nice={nicest} env={len(keys)}",
        "nice=0",
        ",".join(keys[:6]),
    )


def run(ctx: TraceContext) -> list[Hop]:
    """oMLX ceiling, Ollama residents, seat fit and the P40 — each independently reported."""
    return [
        omlx_hop(ctx),
        ollama_hop(ctx),
        seat_fit_hop(ctx),
        p40_gpu_hop(),
        p40_ollama_hop(),
    ]
