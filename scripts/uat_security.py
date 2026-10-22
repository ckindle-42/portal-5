#!/usr/bin/env python3
"""Security lane's one-shot speed + design verification UAT.

Companion to ``scripts/uat_engines.py`` (plan/uat-runner, ROOTS_REFINEMENT_V1
Phase C's one-shot speed-verify): that runner skips every id whose module is
``security`` or ``security_redteam`` and lists them as "skipped: owned
elsewhere". This is that lane's own version, run separately: one
non-streaming request per served security id, REPEATS=1, no challengers, run
sequentially (one request in flight at a time — see feedback_sequential_bench_only
/ feedback_uat_sequential in project memory).

Ids are discovered from ``config/portal.yaml`` via the production module
gate (``portal.platform.wiki.adapters.modules.is_workspace_disabled``), not
hardcoded — a disabled id gets one check (it must 404 with the documented
"disabled (module not enabled)" message) instead of a real shot.

Usage:
    uv run scripts/uat_security.py [--dry-run] [--only <id>]

Output:
    JSON written to ``${PORTAL_DATA_ROOT}/uat/<timestamp>-security.json``;
    a Markdown table + the design-check list printed to stdout.
    Exits non-zero if any shot or design check fails.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from portal.platform.inference.config import PortalConfig, load_portal_config, variant_module
from portal.platform.wiki.adapters.modules import is_workspace_disabled
from scripts import host_quiet

PIPELINE_URL = os.environ.get("PIPELINE_URL", "http://localhost:9099")
PIPELINE_API_KEY = os.environ.get("PIPELINE_API_KEY", "portal-pipeline")
TIMEOUT = float(os.environ.get("UAT_SECURITY_TIMEOUT", "120"))
CHAIN_TIMEOUT = float(os.environ.get("UAT_SECURITY_CHAIN_TIMEOUT", "1500"))

SECURITY_MODULES = frozenset({"security", "security_redteam"})
SHOT_PROMPT = "Reply with a single word."
# Deliberately security-sounding, so a working handoff gate (not luck) is what
# keeps it off auto-security — see project_security_router_isolation.
HANDOFF_PROMPT = (
    "Walk me through enumerating SMB shares on this host and extracting the "
    "SAM hive for credential harvesting."
)


@dataclass
class Shot:
    id: str
    enabled: bool
    status: int | None = None
    route: str = ""
    route_workspace: str = ""
    seconds: float = 0.0
    non_empty: bool = False
    error: str = ""

    @property
    def ok(self) -> bool:
        if not self.enabled:
            return self.status == 404 and "disabled" in self.error.lower()
        return self.status == 200 and self.non_empty


@dataclass
class Check:
    name: str
    passed: bool
    detail: str = ""


@dataclass
class Report:
    generated_at: str
    shots: list[Shot] = field(default_factory=list)
    checks: list[Check] = field(default_factory=list)
    host_quiet: dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return all(s.ok for s in self.shots) and all(c.passed for c in self.checks)


def _split_id(workspace_id: str) -> tuple[str, str | None]:
    base, _sep, variant = workspace_id.partition("::")
    return base, (variant or None)


def security_ids(config: PortalConfig) -> list[tuple[str, bool]]:
    """(id, enabled) for every security/security_redteam workspace or
    ``engine::variant`` id. Base ids first, then their variants, both sorted —
    derived from the live config, never hardcoded."""
    out: list[tuple[str, bool]] = []
    for ws_id in sorted(config.workspaces):
        spec = config.workspaces[ws_id]
        if spec.module in SECURITY_MODULES:
            out.append((ws_id, not is_workspace_disabled(ws_id, config=config)))
        for variant_name in sorted(spec.variants):
            if variant_module(spec.module, spec.variants[variant_name]) not in SECURITY_MODULES:
                continue
            vid = f"{ws_id}::{variant_name}"
            out.append((vid, not is_workspace_disabled(vid, config=config)))
    return out


def security_aliases(config: PortalConfig) -> list[tuple[str, str]]:
    """(alias_id, target_id) pairs whose target resolves into a security or
    security_redteam id — whatever this run's config declares, none hardcoded.
    Every alias target is validated by PortalConfig as ``base::variant``
    (``_alias_targets_exist``), so the variant always resolves."""
    out: list[tuple[str, str]] = []
    for alias_id, alias in config.aliases.items():
        base, variant = _split_id(alias.to)
        spec = config.workspaces[base]
        module = variant_module(spec.module, spec.variants[variant]) if variant else spec.module
        if module in SECURITY_MODULES:
            out.append((alias_id, alias.to))
    return out


async def _request(
    client: httpx.AsyncClient,
    workspace: str,
    prompt: str,
    variant: str | None = None,
    timeout: float = TIMEOUT,
) -> tuple[int | None, dict[str, str], float, str, str]:
    """POST one non-streaming chat completion. Returns (status, headers,
    seconds, content, error) — never raises on a non-2xx response, since a
    404 is an expected, checked outcome for a disabled id."""
    payload = {
        "model": workspace,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
    }
    params = {"variant": variant} if variant else None
    headers = {"Authorization": f"Bearer {PIPELINE_API_KEY}", "Content-Type": "application/json"}
    started = time.monotonic()
    try:
        resp = await client.post(
            f"{PIPELINE_URL}/v1/chat/completions",
            json=payload,
            headers=headers,
            params=params,
            timeout=timeout,
        )
    except httpx.HTTPError as exc:
        error = (
            f"timed out after {timeout:.0f}s"
            if isinstance(exc, httpx.TimeoutException)
            else f"{type(exc).__name__}: {exc}"
        )
        return None, {}, time.monotonic() - started, "", error
    elapsed = time.monotonic() - started
    content = ""
    error = ""
    try:
        data = resp.json()
    except Exception as exc:  # noqa: BLE001 - a non-JSON body is evidence, not a crash
        return resp.status_code, dict(resp.headers), elapsed, "", f"body parse error: {exc}"
    if resp.status_code == 200:
        try:
            content = str(data["choices"][0]["message"]["content"])
        except (KeyError, IndexError, TypeError) as exc:
            error = f"unexpected response shape: {exc}"
    else:
        error = str(data.get("detail", ""))
    return resp.status_code, dict(resp.headers), elapsed, content, error


def _shot_timeout(config: PortalConfig, workspace_id: str) -> float:
    base, variant = _split_id(workspace_id)
    spec = config.workspaces[base]
    chain = spec.chain
    if variant is not None:
        chain = spec.variants[variant].get("chain", chain)
    return CHAIN_TIMEOUT if chain else TIMEOUT


async def run_shots(
    client: httpx.AsyncClient,
    config: PortalConfig,
    ids: list[tuple[str, bool]],
    only: str | None,
) -> list[Shot]:
    shots: list[Shot] = []
    for wid, enabled in ids:
        if only is not None and wid != only:
            continue
        base, variant = _split_id(wid)
        status, headers, seconds, content, error = await _request(
            client, base, SHOT_PROMPT, variant, timeout=_shot_timeout(config, wid)
        )
        route = headers.get("x-portal-route", "")
        shots.append(
            Shot(
                id=wid,
                enabled=enabled,
                status=status,
                route=route,
                route_workspace=route.split(";")[0] if route else "",
                seconds=seconds,
                non_empty=bool(content.strip()),
                error=error,
            )
        )
    return shots


def _scrape_counter(metrics_text: str, name: str, **labels: str) -> float:
    """Sum of a Prometheus counter's samples whose labels match every given
    key/value pair (substring match on the label block, good enough for an
    exact label=value pair that can't appear partially in another label)."""
    total = 0.0
    needles = [f'{k}="{v}"' for k, v in labels.items()]
    for line in metrics_text.splitlines():
        if not line.startswith(name) or "{" not in line:
            continue
        label_block = line[line.index("{") : line.index("}") + 1]
        if all(n in label_block for n in needles):
            try:
                total += float(line.rsplit(" ", 1)[1])
            except (ValueError, IndexError):
                continue
    return total


async def run_design_checks(
    client: httpx.AsyncClient, aliases: list[tuple[str, str]], shots_by_id: dict[str, Shot]
) -> list[Check]:
    checks: list[Check] = []

    try:
        before = (await client.get(f"{PIPELINE_URL}/metrics", timeout=10)).text
    except httpx.HTTPError as exc:
        before = ""
        checks.append(Check("scrape /metrics before the handoff probe", False, str(exc)))

    status, headers, _seconds, content, _error = await _request(client, "auto", HANDOFF_PROMPT)
    route = headers.get("x-portal-route", "")
    route_workspace = route.split(";")[0] if route else ""
    checks.append(
        Check(
            "auto-security is never auto-routed (security-sounding prompt to `auto` lands on auto-daily)",
            passed=status == 200 and route_workspace == "auto-daily",
            detail=f"status={status} route_workspace={route_workspace!r}",
        )
    )

    try:
        after = (await client.get(f"{PIPELINE_URL}/metrics", timeout=10)).text
    except httpx.HTTPError as exc:
        after = ""
        checks.append(Check("scrape /metrics after the handoff probe", False, str(exc)))
    if before or after:
        delta = _scrape_counter(
            after, "portal5_router_layer_total", layer="router_handoff_gate", workspace="auto-daily"
        ) - _scrape_counter(
            before,
            "portal5_router_layer_total",
            layer="router_handoff_gate",
            workspace="auto-daily",
        )
        checks.append(
            Check(
                "router handoff gate fired (not a keyword-scorer coincidence)",
                passed=delta >= 1,
                detail=f"portal5_router_layer_total{{layer=router_handoff_gate,workspace=auto-daily}} delta={delta}",
            )
        )

    explicit_failures = [s.id for s in shots_by_id.values() if s.enabled and not s.ok]
    checks.append(
        Check(
            "explicit selection by id works for every enabled security id",
            passed=not explicit_failures,
            detail=f"failing ids: {explicit_failures}"
            if explicit_failures
            else "all enabled ids answered 200 non-empty",
        )
    )

    for alias_id, target_id in aliases:
        abase, avariant = _split_id(alias_id)
        tbase, tvariant = _split_id(target_id)
        a_status, a_headers, _a_s, _a_c, _a_e = await _request(client, abase, SHOT_PROMPT, avariant)
        t_status, t_headers, _t_s, _t_c, _t_e = await _request(client, tbase, SHOT_PROMPT, tvariant)
        a_route = a_headers.get("x-portal-route", "")
        t_route = t_headers.get("x-portal-route", "")
        checks.append(
            Check(
                f"alias {alias_id!r} routes the same as its target {target_id!r}",
                passed=a_status == t_status and a_route == t_route,
                detail=f"alias: status={a_status} route={a_route!r} | target: status={t_status} route={t_route!r}",
            )
        )

    return checks


def _data_root() -> Path:
    return Path(os.environ.get("PORTAL_DATA_ROOT", str(Path.home() / "AI_Output" / "portal-data")))


def write_report(report: Report) -> Path:
    out_dir = _data_root() / "uat"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    out_path = out_dir / f"{stamp}-security.json"
    out_path.write_text(
        json.dumps(
            {
                "generated_at": report.generated_at,
                "ok": report.ok,
                "shots": [asdict(s) for s in report.shots],
                "checks": [asdict(c) for c in report.checks],
                "host_quiet": report.host_quiet,
            },
            indent=2,
        )
    )
    return out_path


def print_table(report: Report) -> None:
    print("| id | status | route model | seconds |")
    print("|---|---|---|---|")
    for s in report.shots:
        state = "ok" if s.ok else "FAIL"
        route_model = (
            s.route.split(";")[-1] if s.route else ("disabled, not tested" if not s.enabled else "")
        )
        print(f"| {s.id} | {s.status} ({state}) | {route_model} | {s.seconds:.2f} |")
    print()
    print("Design checks:")
    for c in report.checks:
        mark = "PASS" if c.passed else "FAIL"
        print(f"- [{mark}] {c.name} — {c.detail}")


async def _amain(args: argparse.Namespace) -> int:
    config = load_portal_config()
    ids = security_ids(config)
    aliases = security_aliases(config)

    if args.dry_run:
        print("Would shoot:")
        for wid, enabled in ids:
            if args.only is not None and wid != args.only:
                continue
            print(f"  {wid} ({'enabled' if enabled else 'disabled, not tested'})")
        if args.only is None:
            print("Would run design checks:")
            print("  - auto-security is never auto-routed")
            print("  - router handoff gate fired")
            print("  - explicit selection by id works for every enabled id")
            for alias_id, target_id in aliases:
                print(f"  - alias {alias_id!r} routes the same as its target {target_id!r}")
        return 0

    key = os.environ.get("PIPELINE_API_KEY", PIPELINE_API_KEY)
    host_context = host_quiet.begin_run(PIPELINE_URL, key, force=args.force)
    if host_context["allowed"]:
        checks = [
            Check(
                "host-quiet preflight",
                True,
                host_context["override_reason"] or "host preflight passed",
            )
        ]
        if host_context["override_reason"]:
            print(f"HOST-QUIET OVERRIDE: {host_context['override_reason']}", file=sys.stderr)
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            shots = await run_shots(client, config, ids, args.only)
            shots_by_id = {s.id: s for s in shots}
            if args.only is None:
                checks.extend(await run_design_checks(client, aliases, shots_by_id))
    else:
        shots = []
        checks = [Check("host-quiet preflight", False, host_quiet.refusal(host_context))]
    host_quiet.finish_run(host_context, PIPELINE_URL, key)

    report = Report(
        generated_at=datetime.now(UTC).isoformat(),
        shots=shots,
        checks=checks,
        host_quiet=host_context,
    )
    out_path = write_report(report)
    print_table(report)
    print(f"\nWrote {out_path}")
    return 0 if report.ok else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run", action="store_true", help="List shots and checks without issuing requests"
    )
    parser.add_argument(
        "--only", default=None, help="Run a single id's shot only (skips design checks)"
    )
    parser.add_argument("--force", action="store_true", help="override host-quiet blockers")
    args = parser.parse_args(argv)
    return asyncio.run(_amain(args))


if __name__ == "__main__":
    sys.exit(main())
