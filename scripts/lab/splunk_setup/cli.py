"""Stage CLI for the lab Splunk setup. Every mutating command is dry-runnable and idempotent."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections.abc import Callable
from dataclasses import asdict
from pathlib import Path
from urllib.parse import quote

from . import conf, host, plan, reindex, rest

DEFAULT_APP_ROOT = Path("coding_task/scratch/splunk_setup")
_COMPLETE = frozenset({"1", "true", "True"})


def _spec(value: str) -> plan.IndexSpec:
    if value == plan.CONTROL_INDEX:
        raise SystemExit(f"{plan.CONTROL_INDEX} is the untuned control: {plan.CONTROL_REASON}")
    for spec in plan.TUNED:
        if value in (spec.key, spec.source_index, spec.target_index):
            return spec
    raise SystemExit(f"unknown index {value!r}; expected one of {[s.key for s in plan.TUNED]}")


def _print(payload) -> None:
    print(json.dumps(payload, indent=1, default=str))


def cmd_inventory(args: argparse.Namespace) -> int:
    out = {"generated_from": "ingest receipts (sent counts)", "indexes": {}}
    for spec in plan.TUNED:
        receipt = reindex.load_receipt(spec)
        counts: dict[str, int] = {}
        for record in receipt["files"]:
            st = str(record["sourcetype"])
            counts[st] = counts.get(st, 0) + int(record.get("sent", 0))
        out["indexes"][spec.source_index] = {
            "target_index": spec.target_index,
            "receipt": str(spec.receipt),
            "files": len(receipt["files"]),
            "events": int(receipt.get("sent_total", 0)),
            "sourcetypes": dict(sorted(counts.items(), key=lambda kv: -kv[1])),
        }
    Path(args.out).write_text(json.dumps(out, indent=1) + "\n")
    print(f"wrote {args.out} ({sum(len(v['sourcetypes']) for v in out['indexes'].values())} names)")
    return 0


def cmd_app(args: argparse.Namespace) -> int:
    if args.check:
        drift = conf.diff_app(Path(args.out), with_change=args.with_change)
        _print({"in_sync": not drift, "drift": drift})
        return 0 if not drift else 1
    app_dir = conf.write_app(Path(args.out), with_change=args.with_change)
    print(f"rendered {app_dir}")
    return 0


def cmd_preflight(args: argparse.Namespace) -> int:
    svc = rest.SplunkREST(transport=_transport(args))
    info = svc.request("GET", "/services/server/info").get("entry", [{}])[0].get("content", {})
    report: dict[str, object] = {
        "url": os.environ.get("LAB_SPLUNK_URL", rest.DEFAULT_URL),
        "version": info.get("version"),
        "apps": {name: svc.app_state(name) for name in plan.APPS_ENABLE},
        "indexes": {
            spec.target_index: svc.index_settings(spec.target_index) is not None
            for spec in plan.TUNED
        },
        "control": {
            "index": plan.CONTROL_INDEX,
            "reason": plan.CONTROL_REASON,
        },
        "acceleration": _acceleration_state(svc),
    }
    _print(report)
    return 0


def _acceleration_state(svc: rest.SplunkREST) -> dict:
    probe = svc.search(
        "| rest /servicesNS/-/-/data/models | fields title acceleration.enabled "
        "acceleration.earliest_time | search title=Authentication OR title=Endpoint OR "
        "title=Intrusion_Detection OR title=Network_Resolution OR title=Network_Traffic "
        "OR title=Web OR title=Change",
        earliest="-1m",
    )
    return {row.get("title", ""): row for row in probe.rows}


def cmd_apply(args: argparse.Namespace) -> int:
    root = Path(args.app_root)
    app_dir = root / plan.APP_NAME
    accelerate = args.accelerate or args.with_change
    svc = rest.SplunkREST(transport=_transport(args))
    if accelerate:
        _require_indexed_families(svc)
    conf.write_app(root, with_change=args.with_change)
    actions: list[dict] = []
    if not args.dry_run:
        actions.append({"changed": True, "detail": host.install_app(app_dir, lxc_id=args.lxc_id)})
        lookup = host.ensure_lookup_file(
            plan.CIM_APP,
            plan.CIM_DNS_LOOKUP_FILE,
            lxc_id=args.lxc_id,
            container=args.container,
        )
        actions.append(
            {
                "changed": lookup == "copied",
                "detail": f"{plan.CIM_APP} {plan.CIM_DNS_LOOKUP_FILE}: {lookup}",
            }
        )
    for app in plan.APPS_ENABLE:
        actions.append(asdict(svc.ensure_app(app, enabled=True, dry_run=args.dry_run)))
    for macro in plan.cim_macros(args.with_change):
        actions.append(
            asdict(
                svc.ensure_macro(
                    plan.CIM_APP,
                    macro,
                    plan.cim_macro_definition(),
                    dry_run=args.dry_run,
                )
            )
        )
    token = os.environ.get("LAB_SPLUNK_HEC_TOKEN", "")
    for spec in plan.TUNED:
        actions.append(
            asdict(svc.ensure_index(spec.target_index, plan.INDEX_SETTINGS, dry_run=args.dry_run))
        )
        if token:
            actions.append(
                asdict(svc.ensure_hec_index(token, spec.target_index, dry_run=args.dry_run))
            )
    if not args.dry_run and not args.no_restart:
        actions.append({"changed": True, "detail": host.restart(lxc_id=args.lxc_id)})
        _wait_for_rest(svc)
    if accelerate:
        actions.extend(_accelerate(svc, with_change=args.with_change, dry_run=args.dry_run))
    _print({"app": str(app_dir), "dry_run": args.dry_run, "actions": actions})
    return 0


def _accelerate(
    svc: rest.SplunkREST, *, with_change: bool, dry_run: bool
) -> list[dict[str, object]]:
    """Stage 3 after the restart: the model object lives in Splunk_SA_CIM, so the row goes there."""
    return [
        asdict(
            svc.ensure_datamodel_acceleration(
                plan.CIM_APP, model, plan.accel_settings(), dry_run=dry_run
            )
        )
        for model in plan.accelerated_models(with_change)
    ]


def _require_indexed_families(svc: rest.SplunkREST) -> None:
    """Acceleration runs after stage 2: refuse to switch it on over an empty index."""
    empty = []
    for spec in plan.TUNED:
        probe = svc.search(f"| eventcount summarize=false index={spec.target_index}", earliest="0")
        if sum(int(row.get("count") or 0) for row in probe.rows) == 0:
            empty.append(spec.target_index)
    if empty:
        raise SystemExit(f"stage 3 needs stage 2 first: {empty} hold no events")


def _wait_for_rest(svc: rest.SplunkREST, attempts: int = 60) -> None:
    for _ in range(attempts):
        try:
            svc.request("GET", "/services/server/info")
            return
        except Exception:  # noqa: BLE001 -- a restart is expected to refuse connections
            time.sleep(5)
    raise SystemExit("Splunk REST did not come back after restart")


def cmd_plan(args: argparse.Namespace) -> int:
    spec = _spec(args.index)
    built = reindex.make_plan(spec, keep_metrics=args.keep_metrics)
    resolvable, missing = 0, []
    for row in built.rows:
        if row.sourcetype_out is None:
            continue
        try:
            reindex.resolve_path(built.root, row.host, row.source)
            resolvable += 1
        except FileNotFoundError:
            missing.append(f"{row.host}{row.source}")
    payload = {
        "index": spec.target_index,
        "control": plan.CONTROL_INDEX,
        "root": str(built.root),
        "source_events": built.source_total,
        "kept_events": built.kept_total,
        "dropped_events": built.noise_total,
        "files_resolvable": resolvable,
        "files_missing": missing,
        "by_target": built.by_target,
        "files": [
            {
                "host": row.host,
                "source": row.source,
                "from": row.sourcetype_in,
                "to": row.sourcetype_out,
                "index": row.index,
                "events": row.events,
            }
            for row in built.rows
        ],
    }
    _print(payload)
    return 0


def cmd_reindex(args: argparse.Namespace) -> int:
    spec = _spec(args.index)
    built = reindex.make_plan(spec, keep_metrics=args.keep_metrics)
    if args.ship and not (args.force or args.resume):
        svc = rest.SplunkREST(transport=_transport(args))
        probe = svc.search(f"| eventcount summarize=false index={spec.target_index}", earliest="0")
        existing = sum(int(row.get("count") or 0) for row in probe.rows)
        if existing:
            raise SystemExit(
                f"{spec.target_index} already holds {existing} events; re-running would duplicate "
                "them. Use --resume to continue a stopped run, or drop the index first."
            )
    receipt = reindex.ship(
        built,
        state_dir=Path(args.state),
        resume=args.resume,
        dry_run=not args.ship,
        on_file=lambda item: print(f"{item.host}{item.source} -> {item.sourcetype} {item.sent}"),
    )
    _print(
        {
            "index": spec.target_index,
            "shipped": receipt.sent_total,
            "expected": built.kept_total,
            "dry_run": not args.ship,
        }
    )
    return 0


def cmd_summary(args: argparse.Namespace) -> int:
    svc = rest.SplunkREST(transport=_transport(args))
    actions = []
    for spec in plan.TUNED:
        name = spec.summary_search
        path = f"/servicesNS/nobody/{plan.APP_NAME}/saved/searches/{quote(name, safe='')}"
        entry = svc.entry(path)
        if entry is None:
            actions.append({"changed": False, "detail": f"{name} not installed yet"})
            continue
        if entry.get("content", {}).get("disabled"):
            if not args.dry_run:
                svc.request("POST", f"{path}/enable")
            actions.append({"changed": True, "detail": f"{name} enabled"})
        else:
            actions.append({"changed": False, "detail": f"{name} already enabled"})
        if args.run_now and not args.dry_run:
            svc.request("POST", f"{path}/dispatch")
            actions.append({"changed": True, "detail": f"{name} dispatched"})
    _print({"dry_run": args.dry_run, "actions": actions})
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    svc = rest.SplunkREST(transport=_transport(args))
    report = _macro_rows(svc)
    report.append(_row("acceleration_window", _acceleration_check, svc))
    report.append(_row("summaries_complete", _summaries_check, svc))
    report.extend(
        _row(f"summary_index:{spec.source_index}", _summary_index_check, svc, spec)
        for spec in plan.TUNED
    )
    if args.accelerate:
        report.extend(_model_rows(svc))
    if args.index:
        report.extend(_probe_row(svc, probe) for probe in plan.verify_probes(_spec(args.index)))
    report.extend(_probe_row(svc, probe) for probe in plan.CONTROL_PROBES)
    _print(report)
    return 0 if all(row["ok"] for row in report) else 1


def _row(name: str, check: Callable[..., tuple[bool, str]], *args: object) -> dict[str, object]:
    """Run one check alone: a raised error is that check's FAIL row, never the run's abort."""
    print(f"verify: {name}", file=sys.stderr)
    try:
        ok, detail = check(*args)
    except (rest.SplunkError, RuntimeError) as exc:
        ok, detail = False, f"{type(exc).__name__}: {exc}"
    return {"name": name, "ok": ok, "detail": detail}


def _probe_row(svc: rest.SplunkREST, probe: plan.Probe) -> dict[str, object]:
    """`ok` covers both a failed job and a probe that returned too few rows."""

    def check() -> tuple[bool, str]:
        earliest, latest = "0" if probe.name == "events" else "-10y", "now"
        if probe.name == "control_model_scope":
            earliest, latest = "2017-08-01T00:00:00", "2018-10-30T00:00:00"
        result = svc.search(probe.spl, earliest=earliest, latest=latest)
        short = len(result.rows) < probe.min_rows
        detail = f"rows={len(result.rows)} scan={result.scan_count} want {probe.expect}"
        if short:
            detail += f"; got fewer than {probe.min_rows} rows"
        if result.failed:
            detail += "; job failed: " + "; ".join(result.messages)
        return not (result.failed or short), detail

    return _row(probe.name, check)


def _macro_rows(svc: rest.SplunkREST) -> list[dict[str, object]]:
    return [_row(f"cim_macro:{macro}", _macro_check, svc, macro) for macro in plan.cim_macros()]


def _macro_check(svc: rest.SplunkREST, macro: str) -> tuple[bool, str]:
    """The property is the parser's expansion, not the conf row: `()` means the scope lost."""
    expansion = svc.macro_expansion(macro)
    missing = [spec.target_index for spec in plan.TUNED if spec.target_index not in expansion]
    if missing:
        return False, f"expansion does not name {missing}: {expansion}"
    return True, expansion


def _acceleration_check(svc: rest.SplunkREST) -> tuple[bool, str]:
    state = _acceleration_state(svc)
    windows = {
        model: str(state.get(model, {}).get("acceleration.earliest_time", "absent"))
        for model in plan.ACCELERATED
    }
    off = {model: window for model, window in windows.items() if window != plan.ACCEL_WINDOW}
    if off:
        return False, f"expected {plan.ACCEL_WINDOW} on every model; got {off}"
    return True, f"{plan.ACCEL_WINDOW} on {len(windows)} models"


def _summaries_check(svc: rest.SplunkREST) -> tuple[bool, str]:
    """Accelerator ids are ``DM_<app>_<Model>``; ``datamodel_name`` is not a field on the endpoint."""
    result = svc.search(
        "| rest /services/admin/summarization by_tstats=t "
        "| table summary.id summary.size summary.complete",
        earliest="-1m",
    )
    keyed = {str(row.get("summary.id", "")): row for row in result.rows}
    rows = {model: keyed.get(f"DM_{plan.CIM_APP}_{model}", {}) for model in plan.ACCELERATED}
    states = {model: str(row.get("summary.complete", "absent")) for model, row in rows.items()}
    unfinished = {model: value for model, value in states.items() if value not in _COMPLETE}
    sizes = {model: row.get("summary.size", "absent") for model, row in rows.items()}
    detail = f"complete {len(states) - len(unfinished)}/{len(states)}; size {sizes}"
    if unfinished:
        return False, f"{detail}; not complete {unfinished}"
    return True, detail


def _summary_index_check(svc: rest.SplunkREST, spec: plan.IndexSpec) -> tuple[bool, str]:
    result = svc.search(
        f"index=summary hunt_entities_index={spec.source_index} | stats count", earliest="0"
    )
    count = int((result.rows[0] if result.rows else {}).get("count") or 0)
    return count > 0, f"{count} rows for hunt_entities_index={spec.source_index}"


def _model_rows(svc: rest.SplunkREST) -> list[dict[str, object]]:
    return [
        _row(f"acceleration:{model}", _model_check, svc, model)
        for model in plan.accelerated_models()
    ]


def _model_check(svc: rest.SplunkREST, model: str) -> tuple[bool, str]:
    """The property is what the model reports, not the conf row: a row in another app loses."""
    reported = svc.datamodel_acceleration(plan.CIM_APP, model)
    enabled = bool(reported.get("enabled"))
    earliest = str(reported.get("earliest_time", "?"))
    window = str(plan.ACCEL_WINDOW)
    covered = enabled and earliest == window
    return covered, f"reports enabled={enabled} {earliest}; want enabled {window}"


def cmd_rollback(args: argparse.Namespace) -> int:
    spec = _spec(args.index) if args.index else plan.TUNED[0]
    svc = rest.SplunkREST(transport=_transport(args))
    restores = [
        asdict(
            svc.ensure_macro(
                plan.CIM_APP,
                macro,
                plan.CIM_DEFAULT_DEFINITION,
                dry_run=args.dry_run,
            )
        )
        for macro in plan.cim_macros(with_change=True)
    ]
    acceleration = [
        asdict(svc.revert_datamodel_acceleration(plan.CIM_APP, model, dry_run=args.dry_run))
        for model in plan.accelerated_models(with_change=True)
    ]
    commands = {
        "app": [
            f"ssh -i $LAB_SSH_KEY root@$LAB_PROXMOX_HOST 'pct exec {args.lxc_id} -- "
            f"docker exec -i {args.container} rm -rf /opt/splunk/etc/apps/{plan.APP_NAME}'",
            f"ssh -i $LAB_SSH_KEY root@$LAB_PROXMOX_HOST 'pct exec {args.lxc_id} -- "
            f"docker restart {args.container}'",
        ],
        "index": [
            f"curl -sk -u $LAB_SPLUNK_USER:$LAB_SPLUNK_PASSWORD -X DELETE "
            f"$LAB_SPLUNK_URL/services/data/indexes/{spec.target_index}"
            "   # deletes only the _v2 copy; the source index is untouched",
        ],
        "summary": [
            "curl -sk -u $LAB_SPLUNK_USER:$LAB_SPLUNK_PASSWORD -X POST "
            f"$LAB_SPLUNK_URL/servicesNS/nobody/{plan.APP_NAME}/saved/searches/"
            f"{spec.summary_search}/disable",
        ],
        "original_index": (
            f"index={spec.source_index} is never written by any stage; no rollback is needed for it"
        ),
    }
    _print(
        {
            "dry_run": args.dry_run,
            "cim_macros": restores,
            "acceleration": acceleration,
            "commands": commands,
        }
    )
    return 0


def _transport(args: argparse.Namespace):
    if getattr(args, "offline", False):

        def offline(method: str, path: str, data):
            raise rest.SplunkError(f"offline: {method} {path}")

        return offline
    return None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="splunk_setup", description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)

    inv = sub.add_parser("inventory", help="regenerate inventory.json from the ingest receipts")
    inv.add_argument("--out", default=str(Path(__file__).parent / "inventory.json"))
    inv.set_defaults(func=cmd_inventory)

    app = sub.add_parser("app", help="render the Splunk app (conf files) locally")
    app.add_argument("--out", default=str(Path(__file__).parent / "app"))
    app.add_argument("--check", action="store_true", help="compare against the committed tree")
    app.add_argument("--with-change", action="store_true", help="include the Change model")
    app.set_defaults(func=cmd_app)

    pre = sub.add_parser("preflight", help="read-only inventory of the live instance")
    pre.add_argument("--offline", action="store_true")
    pre.set_defaults(func=cmd_preflight)

    apply_ = sub.add_parser("apply", help="stage 1: app + TAs + indexes + HEC allowlist + restart")
    apply_.add_argument("--app-root", default=str(DEFAULT_APP_ROOT))
    apply_.add_argument("--with-change", action="store_true")
    apply_.add_argument("--accelerate", action="store_true", help="stage 3: switch acceleration on")
    apply_.add_argument("--dry-run", action="store_true")
    apply_.add_argument("--no-restart", action="store_true")
    apply_.add_argument("--lxc-id", default=host.DEFAULT_LXC)
    apply_.add_argument("--container", default=host.DEFAULT_CONTAINER)
    apply_.add_argument("--offline", action="store_true")
    apply_.set_defaults(func=cmd_apply)
    _stage_parsers(sub)
    return parser


def _stage_parsers(sub) -> None:
    plan_cmd = sub.add_parser("plan", help="stage 2 dry-run: the per-input routing plan")
    plan_cmd.add_argument("--index", required=True)
    plan_cmd.add_argument("--keep-metrics", action="store_true")
    plan_cmd.set_defaults(func=cmd_plan)

    re_idx = sub.add_parser("reindex", help="stage 2: ship the corpus into <index>_v2")
    re_idx.add_argument("--index", required=True)
    re_idx.add_argument("--keep-metrics", action="store_true")
    re_idx.add_argument("--ship", action="store_true", help="actually send (default: dry run)")
    re_idx.add_argument("--resume", action="store_true")
    re_idx.add_argument("--force", action="store_true", help="skip the empty-target check")
    re_idx.add_argument("--state", default=str(DEFAULT_APP_ROOT / "reindex"))
    re_idx.add_argument("--offline", action="store_true")
    re_idx.set_defaults(func=cmd_reindex)

    summ = sub.add_parser("summary", help="stage 4: enable the per-index collect searches")
    summ.add_argument("--dry-run", action="store_true")
    summ.add_argument("--run-now", action="store_true")
    summ.add_argument("--offline", action="store_true")
    summ.set_defaults(func=cmd_summary)

    verify = sub.add_parser("verify", help="stage 5 probes (add --index for a tuned index)")
    verify.add_argument("--index")
    verify.add_argument("--accelerate", action="store_true", help="also assert the model endpoints")
    verify.add_argument("--offline", action="store_true")
    verify.set_defaults(func=cmd_verify)

    rollback = sub.add_parser("rollback", help="restore the CIM macro defaults; print the rest")
    rollback.add_argument("--index")
    rollback.add_argument("--lxc-id", default=host.DEFAULT_LXC)
    rollback.add_argument("--container", default=host.DEFAULT_CONTAINER)
    rollback.add_argument("--dry-run", action="store_true")
    rollback.set_defaults(func=cmd_rollback)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return int(args.func(args))
    except (rest.SplunkError, RuntimeError) as exc:
        print(f"splunk_setup: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
