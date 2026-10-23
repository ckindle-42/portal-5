#!/usr/bin/env python3
"""Gate C calibration calculator.

Reads orchestration-arm task receipts (`receipt.json` beside its `plan.json`)
and reports three things:

  * per-discipline/seat pass counts, observed rates and Wilson lower bounds;
  * the pre-written `pass_criteria` from `config/orchestration_arm.yaml`,
    evaluated against those observed rates;
  * the value to set for `calibration.minimum_pass_probability`.

`minimum_pass_probability` is a **task-level** floor, because
`calibration.calibration_status` compares it with the product of per-bite rates
over the remaining bites. It is derived from the fixed pass criteria, never
from the observed pass counts: for every task shape found in the receipts,
multiply the configured criterion for each bite's seat, then take the minimum
across tasks. A bad run therefore cannot lower its own bar. The same
independence assumption as `calibration.project_remaining` applies.

The Wilson lower bound for a binomial proportion:

  p_hat = k/n
  lower = (p_hat + z^2/(2n) - z*sqrt(p_hat(1-p_hat)/n + z^2/(4n^2)))
          / (1 + z^2/n)

Only final bite states (`passed`, `blocked`, `failed`) are counted; rows that
are still `pending`, `ready`, `running`, `checking`, `waiting` or
`paused_for_replan` are ignored so a partial receipt cannot poison the rates.
The tool is read-only: it never writes config.

Usage:
  uv run python scripts/gate_c_calculator.py receipts/*.json
  uv run python scripts/gate_c_calculator.py --json ~/AI_Output/generated/tasks/test-fixing
  uv run python scripts/gate_c_calculator.py --help
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "config" / "orchestration_arm.yaml"

_Z_SCORES = {
    0.90: 1.645,
    0.95: 1.960,
    0.99: 2.576,
}
DEFAULT_Z = 1.96
DEFAULT_MINIMUM_SAMPLES = 5
_STANDARD_SEATS = {"fast", "deep"}
_FINAL_STATES = {"passed", "blocked", "failed"}
_FINAL_STATUSES = {"PASS", "BLOCKED", "FAILED"}


def wilson_lower_bound(passes: int, total: int, z: float = DEFAULT_Z) -> float:
    """Wilson score interval lower bound for a binomial proportion."""
    if total <= 0:
        return 0.0
    phat = passes / total
    z2 = z * z
    denominator = 1 + z2 / total
    centre = phat + z2 / (2 * total)
    spread = z * math.sqrt(phat * (1 - phat) / total + z2 / (4 * total * total))
    return max(0.0, (centre - spread) / denominator)


def _final_state(result: dict[str, Any]) -> str | None:
    state = str(result.get("state", "")).strip().lower()
    if state:
        return state if state in _FINAL_STATES else None
    status = str(result.get("status", "")).strip().upper()
    return status.lower() if status in _FINAL_STATUSES else None


def _plan_index(receipt: dict[str, Any]) -> dict[str, dict[str, Any]]:
    plan = receipt.get("plan")
    if not isinstance(plan, dict):
        return {}
    bites = plan.get("bites")
    if not isinstance(bites, list):
        return {}
    return {
        str(bite["bite_id"]): bite
        for bite in bites
        if isinstance(bite, dict) and isinstance(bite.get("bite_id"), str)
    }


def _row_identity(
    result: dict[str, Any], plan: dict[str, dict[str, Any]]
) -> tuple[str | None, str | None]:
    bite = plan.get(str(result.get("bite_id", "")), {})
    discipline = result.get("discipline") or bite.get("discipline")
    seat = result.get("model") or result.get("seat") or bite.get("model")
    return (
        str(discipline) if isinstance(discipline, str) and discipline else None,
        str(seat) if isinstance(seat, str) and seat else None,
    )


def _row_elapsed(result: dict[str, Any]) -> float | None:
    value = result.get("elapsed_seconds")
    if isinstance(value, (int, float)) and not isinstance(value, bool) and value >= 0:
        return float(value)
    return None


def _seat_roles(config_path: Path) -> dict[str, str]:
    """Map seated workspace tags (auto-daily::gemma-fast) back to the role keys the arm reads."""
    roles = {f"auto-daily::{seat}": seat for seat in _STANDARD_SEATS}
    try:
        raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return roles
    disciplines = raw.get("disciplines") if isinstance(raw, dict) else None
    for entry in (disciplines or {}).values():
        seated = entry.get("seated_models") if isinstance(entry, dict) else None
        for seat, tag in (seated or {}).items():
            if seat in _STANDARD_SEATS and isinstance(tag, str):
                roles[tag] = seat
    return roles


def _collect_rows(
    receipts: list[dict[str, Any]], seat_roles: dict[str, str] | None = None
) -> list[dict[str, Any]]:
    roles = seat_roles or {}
    rows: list[dict[str, Any]] = []
    for index, receipt in enumerate(receipts):
        if not isinstance(receipt, dict):
            raise ValueError("each receipt must be a JSON object")
        if receipt.get("suite") not in (None, "bite"):
            continue
        results = receipt.get("results", [])
        if not isinstance(results, list):
            raise ValueError("receipt.results must be a list")
        plan = _plan_index(receipt)
        for result in results:
            if not isinstance(result, dict):
                raise ValueError("each receipt result must be an object")
            if result.get("suite") not in (None, "bite"):
                continue
            state = _final_state(result)
            if state is None:
                continue
            discipline, seat = _row_identity(result, plan)
            if discipline is None:
                continue
            if not isinstance(seat, str) or not seat.strip() or any(ord(c) < 32 for c in seat):
                raise ValueError(
                    f"receipt {index} bite {result.get('bite_id')!r} has invalid seat {seat!r}"
                )
            rows.append(
                {
                    "receipt": index,
                    "bite_id": result.get("bite_id"),
                    "discipline": discipline,
                    "seat": roles.get(seat, seat),
                    "passed": state == "passed",
                    "elapsed_seconds": _row_elapsed(result),
                }
            )
    return rows


def _count_rows(rows: list[dict[str, Any]]) -> dict[str, dict[str, dict[str, Any]]]:
    counts: dict[str, dict[str, dict[str, Any]]] = {}
    for row in rows:
        seat = counts.setdefault(row["discipline"], {}).setdefault(
            row["seat"], {"passes": 0, "total": 0, "seconds": 0.0, "timed": 0}
        )
        seat["passes"] += int(row["passed"])
        seat["total"] += 1
        if row["elapsed_seconds"] is not None:
            seat["seconds"] += row["elapsed_seconds"]
            seat["timed"] += 1
    return counts


def extract_discipline_rates(
    receipts: list[dict[str, Any]],
) -> dict[str, dict[str, tuple[int, int]]]:
    """Extract per-discipline, per-seat (passes, total) from final receipt rows."""
    counts = _count_rows(_collect_rows(receipts))
    return {
        discipline: {seat: (data["passes"], data["total"]) for seat, data in seats.items()}
        for discipline, seats in counts.items()
    }


def _check_minimum_samples(counts: dict[str, dict[str, dict[str, Any]]], minimum: int) -> None:
    floor = max(1, minimum)
    short = [
        f"{discipline}/{seat} n={data['total']}"
        for discipline, seats in counts.items()
        for seat, data in seats.items()
        if data["total"] < floor
    ]
    if short:
        raise ValueError(
            f"insufficient evidence: each discipline/seat needs n>={floor}; got {', '.join(short)}"
        )


def _load_criteria(config_path: Path) -> dict[str, Any]:
    try:
        raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as exc:
        raise ValueError(f"cannot read pass_criteria from {config_path}: {exc}") from exc
    disciplines = raw.get("disciplines") if isinstance(raw, dict) else None
    if not isinstance(disciplines, dict):
        raise ValueError(f"{config_path} does not define disciplines")
    criteria = {
        str(name): entry["pass_criteria"]
        for name, entry in disciplines.items()
        if isinstance(entry, dict) and isinstance(entry.get("pass_criteria"), dict)
    }
    if not criteria:
        raise ValueError(f"{config_path} defines no disciplines.*.pass_criteria")
    return criteria


def _seat_criterion(discipline: str, entry: dict[str, Any], seat: str) -> float:
    if seat in _STANDARD_SEATS:
        value = entry.get(f"minimum_{seat}_pass_rate", entry.get("minimum_bite_pass_rate"))
        if _valid_probability(value):
            return float(value)
    values = [entry.get("minimum_bite_pass_rate")]
    values.extend(entry.get(f"minimum_{name}_pass_rate") for name in sorted(_STANDARD_SEATS))
    configured = [float(value) for value in values if _valid_probability(value)]
    per_seat = entry.get("per_seat_bite_suite")
    if isinstance(per_seat, dict):
        for policy in per_seat.values():
            if not isinstance(policy, dict):
                continue
            passed, total = policy.get("minimum_passed"), policy.get("total")
            if (
                isinstance(passed, int)
                and not isinstance(passed, bool)
                and isinstance(total, int)
                and not isinstance(total, bool)
                and total > 0
                and 0 < passed <= total
            ):
                configured.append(passed / total)
    if configured:
        return max(configured)
    raise ValueError(
        f"pass_criteria for {discipline} has no fixed rate for seat {seat!r} "
        "or a general bite-suite rate"
    )


def _valid_probability(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and 0 < value <= 1


def _task_shapes(
    receipts: list[dict[str, Any]],
    rows: list[dict[str, Any]],
    seat_roles: dict[str, str] | None = None,
) -> dict[int, list[tuple[str, str]]]:
    roles = seat_roles or {}
    shapes: dict[int, list[tuple[str, str]]] = {}
    for index, receipt in enumerate(receipts):
        final_ids = {
            str(row.get("bite_id"))
            for row in rows
            if row["receipt"] == index and row.get("bite_id")
        }
        plan = receipt.get("plan")
        shape: list[tuple[str, str]] = []
        bites = plan.get("bites") if isinstance(plan, dict) else None
        if isinstance(bites, list):
            for bite in bites:
                if not isinstance(bite, dict):
                    continue
                discipline, seat = bite.get("discipline"), bite.get("model")
                if (
                    bite.get("suite") in (None, "bite")
                    and str(bite.get("bite_id")) in final_ids
                    and isinstance(discipline, str)
                    and isinstance(seat, str)
                    and seat.strip()
                ):
                    shape.append((discipline, roles.get(seat, seat)))
        if not shape:
            shape = [(row["discipline"], row["seat"]) for row in rows if row["receipt"] == index]
        if shape:
            shapes[index] = shape
    return shapes


def _task_floors(
    shapes: dict[int, list[tuple[str, str]]], criteria: dict[str, Any]
) -> list[dict[str, Any]]:
    floors = []
    for index, shape in sorted(shapes.items()):
        value = 1.0
        for discipline, seat in shape:
            entry = criteria.get(discipline)
            if not isinstance(entry, dict):
                raise ValueError(
                    f"discipline {discipline!r} has no pre-written pass_criteria; "
                    "Gate C cannot derive an independent task floor"
                )
            value *= _seat_criterion(discipline, entry, seat)
        floors.append({"receipt": index, "bites": len(shape), "floor": value})
    return floors


def _observed_task_lower_bounds(
    shapes: dict[int, list[tuple[str, str]]], bounds: dict[str, float]
) -> list[dict[str, Any]]:
    out = []
    for index, shape in sorted(shapes.items()):
        value = 1.0
        for discipline, seat in shape:
            value *= bounds[f"{discipline}/{seat}"]
        out.append({"receipt": index, "bites": len(shape), "wilson_lower": value})
    return out


def _evaluate_criteria(
    counts: dict[str, dict[str, dict[str, Any]]], criteria: dict[str, Any]
) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for discipline, seats in counts.items():
        entry = criteria.get(discipline)
        if not isinstance(entry, dict):
            out[discipline] = {"configured": False}
            continue
        observed = {
            "bite_pass_rate": _rate(seats, None),
            "fast_pass_rate": _rate(seats, "fast"),
            "deep_pass_rate": _rate(seats, "deep"),
            "candidate_seat_pass_rates": {
                seat: _rate(seats, seat) for seat in seats if seat not in _STANDARD_SEATS
            },
        }
        checks: dict[str, dict[str, Any]] = {}
        standard_seats = [seat for seat in seats if seat in _STANDARD_SEATS]
        custom_seats = [seat for seat in seats if seat not in _STANDARD_SEATS]
        for key, observed_key in (
            ("minimum_bite_pass_rate", "bite_pass_rate"),
            ("minimum_fast_pass_rate", "fast_pass_rate"),
            ("minimum_deep_pass_rate", "deep_pass_rate"),
        ):
            if key not in entry:
                continue
            if (
                custom_seats
                and not standard_seats
                and key
                in {
                    "minimum_fast_pass_rate",
                    "minimum_deep_pass_rate",
                }
            ):
                continue
            actual = observed[observed_key]
            checks[key] = {
                "required": float(entry[key]),
                "observed": actual,
                "met": actual is not None and actual >= float(entry[key]),
            }
        if custom_seats:
            for seat in custom_seats:
                required = _seat_criterion(discipline, entry, seat)
                actual = _rate(seats, seat)
                checks[f"minimum_{seat}_pass_rate"] = {
                    "required": required,
                    "observed": actual,
                    "met": actual is not None and actual >= required,
                }
        out[discipline] = {
            "configured": True,
            "criteria": {key: value["required"] for key, value in checks.items()},
            "observed": observed,
            "checks": checks,
            "met": all(value["met"] for value in checks.values()) if checks else False,
        }
    return out


def _rate(seats: dict[str, dict[str, Any]], seat: str | None) -> float | None:
    if seat is None:
        passes = sum(data["passes"] for data in seats.values())
        total = sum(data["total"] for data in seats.values())
        return passes / total if total else None
    data = seats.get(seat)
    return data["passes"] / data["total"] if data and data["total"] else None


def _rates_block(counts: dict[str, dict[str, dict[str, Any]]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for discipline, seats in counts.items():
        out[discipline] = {}
        for seat, data in seats.items():
            mean_seconds = data["seconds"] / data["timed"] if data["timed"] else 0.0
            out[discipline][seat] = {
                "pass_probability": data["passes"] / data["total"],
                "mean_seconds": mean_seconds,
                "samples": data["total"],
                "mean_seconds_source": "checks.json" if data["timed"] else "not recorded (0.0)",
            }
    return out


def compute_gate_c_threshold(
    receipts: list[dict[str, Any]],
    z: float = DEFAULT_Z,
    *,
    confidence: float = 0.95,
    minimum_samples: int = DEFAULT_MINIMUM_SAMPLES,
    config_path: Path | None = None,
) -> tuple[float, dict[str, Any]]:
    """Return the task-level Gate C floor and the evidence behind it."""
    resolved_config = config_path or DEFAULT_CONFIG
    seat_roles = _seat_roles(resolved_config)
    rows = _collect_rows(receipts, seat_roles)
    if not rows:
        raise ValueError(
            "No final per-bite results with a discipline and seat found in receipts; "
            "join plan.json or pass an ArmService receipt"
        )
    counts = _count_rows(rows)
    _check_minimum_samples(counts, minimum_samples)

    bounds = {
        f"{discipline}/{seat}": wilson_lower_bound(data["passes"], data["total"], z)
        for discipline, seats in counts.items()
        for seat, data in seats.items()
    }
    per_discipline_seat = {
        f"{discipline}/{seat}": {
            "passes": data["passes"],
            "total": data["total"],
            "observed_rate": data["passes"] / data["total"],
            "wilson_lower": bounds[f"{discipline}/{seat}"],
        }
        for discipline, seats in counts.items()
        for seat, data in seats.items()
    }

    criteria = _load_criteria(resolved_config)
    shapes = _task_shapes(receipts, rows, seat_roles)
    if not shapes:
        raise ValueError("No task shapes found in receipts")
    floors = _task_floors(shapes, criteria)
    threshold = min(item["floor"] for item in floors)
    if threshold <= 0:
        raise ValueError(
            "computed Gate C threshold is zero or negative; "
            "unattended runs must not be unlocked with calibration disabled"
        )

    criteria_status = _evaluate_criteria(counts, criteria)
    configured = {name: value for name, value in criteria_status.items() if value.get("configured")}
    return threshold, {
        "threshold": threshold,
        "threshold_domain": "task-level projected pass probability",
        "derivation": (
            "min over task shapes of fixed per-seat pass criteria; unknown seat ids use the strictest configured rate; "
            "independent of observed pass counts"
        ),
        "per_discipline_seat": per_discipline_seat,
        "rates_by_discipline": _rates_block(counts),
        "observed_task_lower_bounds": _observed_task_lower_bounds(shapes, bounds),
        "task_floors": floors,
        "pass_criteria": criteria_status,
        "pass_criteria_met": all(item["met"] for item in configured.values())
        if configured
        else None,
        "formula": (
            "Wilson score interval lower bound per discipline/seat for evidence; "
            "threshold from fixed pass_criteria"
        ),
        "confidence": confidence,
        "z_score": z,
        "minimum_samples": max(1, minimum_samples),
        "receipt_count": len(receipts),
    }


def _read_receipt(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"WARNING: {path} is not a readable receipt: {exc}", file=sys.stderr)
        return None
    if not isinstance(data, dict):
        print(f"WARNING: {path} is not a JSON object", file=sys.stderr)
        return None
    return data


def _attach_task_files(receipt: dict[str, Any], task_dir: Path) -> None:
    plan_path = task_dir / "plan.json"
    if plan_path.is_file():
        try:
            receipt["plan"] = json.loads(plan_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"WARNING: {plan_path} is not a readable plan: {exc}", file=sys.stderr)
    results = receipt.get("results")
    if not isinstance(results, list):
        return
    for result in results:
        if not isinstance(result, dict) or result.get("elapsed_seconds") is not None:
            continue
        bite_id = result.get("bite_id")
        if not isinstance(bite_id, str):
            continue
        attempts = (task_dir / "bites" / bite_id / "attempts").resolve()
        if not attempts.is_relative_to(task_dir.resolve()) or not attempts.is_dir():
            continue
        elapsed = [_checks_elapsed(path) for path in attempts.glob("*/checks.json")]
        recorded = [value for value in elapsed if value is not None]
        if recorded:
            result["elapsed_seconds"] = max(recorded)


def _checks_elapsed(path: Path) -> float | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    value = data.get("elapsed_seconds") if isinstance(data, dict) else None
    return float(value) if isinstance(value, (int, float)) and value >= 0 else None


def load_receipts(paths: list[Path]) -> list[dict[str, Any]]:
    """Load receipt JSON files, attaching sibling plan.json and elapsed evidence."""
    receipts: list[dict[str, Any]] = []
    for path in paths:
        if path.is_dir():
            for receipt_path in sorted(path.rglob("receipt.json")):
                data = _read_receipt(receipt_path)
                if data is not None:
                    _attach_task_files(data, receipt_path.parent)
                    receipts.append(data)
            continue
        if not path.is_file():
            print(f"WARNING: {path} not found, skipping", file=sys.stderr)
            continue
        data = _read_receipt(path)
        if data is None:
            continue
        if path.name == "receipt.json":
            _attach_task_files(data, path.parent)
        receipts.append(data)
    return receipts


def _print_criteria(details: dict[str, Any]) -> None:
    for discipline, status in details["pass_criteria"].items():
        if not status.get("configured"):
            print(
                f"pass_criteria {discipline}: NOT CONFIGURED (no task floor derived)",
                file=sys.stderr,
            )
            continue
        state = "MET" if status["met"] else "NOT MET"
        observed = ", ".join(
            f"{name}=n/a"
            if value is None
            else f"{name}={value:.3f}"
            if isinstance(value, (int, float))
            else f"{name}={json.dumps(value, sort_keys=True)}"
            for name, value in status["observed"].items()
        )
        print(f"pass_criteria {discipline}: {state} ({observed})", file=sys.stderr)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Compute Gate C calibration.minimum_pass_probability from bite-suite receipts",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "receipts",
        nargs="+",
        type=Path,
        help="Receipt JSON files (or directories containing receipt.json)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output full details as JSON instead of just the threshold value",
    )
    parser.add_argument(
        "--confidence",
        type=float,
        default=0.95,
        choices=[0.90, 0.95, 0.99],
        help="Confidence level for Wilson interval (default: 0.95)",
    )
    parser.add_argument(
        "--minimum-samples",
        type=int,
        default=DEFAULT_MINIMUM_SAMPLES,
        help=f"Minimum final bites per discipline/seat (default: {DEFAULT_MINIMUM_SAMPLES})",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG,
        help="Arm config carrying the pre-written pass_criteria",
    )
    args = parser.parse_args()

    receipts = load_receipts(args.receipts)
    if not receipts:
        missing = all(not path.exists() for path in args.receipts)
        message = (
            "No receipt files found"
            if missing
            else "No valid receipts loaded (paths exist but held no readable receipt)"
        )
        print(f"ERROR: {message}", file=sys.stderr)
        return 2 if missing else 3

    try:
        threshold, details = compute_gate_c_threshold(
            receipts,
            _Z_SCORES.get(args.confidence, DEFAULT_Z),
            confidence=args.confidence,
            minimum_samples=args.minimum_samples,
            config_path=args.config,
        )
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 3

    if args.json:
        print(json.dumps(details, indent=2))
    else:
        print(f"{threshold:.6f}")
        _print_criteria(details)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
