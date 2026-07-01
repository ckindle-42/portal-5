"""Stage 1 self-legibility index — read-only weakness view.

Aggregates the system's already-emitted signals (validator checks, oracle
fidelity, coverage, discipline breadth, field journal) into one structured
self-view and ranks where Portal 5 is weakest via a transparent, inspectable
score. READ-ONLY — no writes except its own report output. Enforced by test.
"""

from __future__ import annotations

import json
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_SELF_DIR = Path(__file__).resolve().parent
_RESULTS_DIR = _SELF_DIR / "results"
_JOURNAL_DIR = _SELF_DIR / "field_journal"


# ── Phase 1: signal readers ───────────────────────────────────────────────────


def _run_validator_json() -> dict | None:
    """Run validate_system.py --json and return parsed output, or None on failure."""
    validator_path = _PROJECT_ROOT / "scripts" / "validate_system.py"
    if not validator_path.exists():
        return None
    try:
        result = subprocess.run(
            ["python3", str(validator_path), "--json", "--skip-pytest"],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(_PROJECT_ROOT),
        )
        if result.returncode != 0 or not result.stdout.strip():
            return None
        return json.loads(result.stdout.strip().split("\n")[-1])
    except (subprocess.TimeoutExpired, subprocess.SubprocessError, json.JSONDecodeError):
        return None


def _read_validator_health() -> dict:
    """26 check pass/fail from validate_system.py."""
    data = _run_validator_json()
    if not data:
        return {"status": "absent", "passes": 0, "fails": 0, "warns": 0, "skips": 0, "checks": {}}
    checks = {}
    for r in data.get("results", []):
        name = r.get("name", "")
        checks[name] = {
            "status": r.get("status", "?"),
            "detail": r.get("detail", ""),
            "elapsed_ms": r.get("elapsed_ms", 0),
        }
    return {
        "status": "present",
        "passes": data.get("passes", 0),
        "fails": data.get("fails", 0),
        "warns": data.get("warns", 0),
        "skips": data.get("skips", 0),
        "elapsed_ms": data.get("elapsed_ms", 0),
        "checks": checks,
    }


def _read_oracle_fidelity() -> dict:
    """Per-oracle tier, verified-rate from registry + results."""
    oracles: dict[str, dict] = {}
    try:
        from .oracles import ORACLES  # noqa: N811

        for oid, oracle in sorted(ORACLES.items()):
            oracles[oid] = {
                "kind": oracle.kind,
                "tier": oracle.tier,
                "honesty_claim": oracle.honesty_claim[:120],
                "verified_count": 0,
                "total_checks": 0,
            }
    except ImportError:
        pass

    tier_counts: dict[str, int] = {}
    for o in oracles.values():
        tier = o["tier"]
        tier_counts[tier] = tier_counts.get(tier, 0) + 1

    # Try to enrich with verified counts from the freshest result JSON
    result_files = sorted(
        [p for p in _RESULTS_DIR.glob("sec_bench_*.json") if not p.name.endswith(".partial.json")],
        key=os.path.getmtime,
        reverse=True,
    )
    for rf in result_files:
        try:
            data = json.loads(rf.read_text())
            mr = data.get("matrix_results", {})
            if mr and mr.get("total_units", 0) > 0:
                for o in oracles.values():
                    o["verified_count"] = mr.get("verified", 0)
                    o["total_checks"] = mr.get("total_units", 0)
            break
        except (json.JSONDecodeError, OSError):
            continue

    stable_count = tier_counts.get("stable", 0)
    heuristic_count = sum(v for k, v in tier_counts.items() if k not in ("stable",))

    return {
        "status": "present" if oracles else "absent",
        "total_oracles": len(oracles),
        "stable_count": stable_count,
        "heuristic_count": heuristic_count,
        "tiers": tier_counts,
        "oracles": oracles,
    }


def _read_coverage() -> dict:
    """Coverage: per-discipline/class resolved/ran/verified from results or theory."""
    result_files = sorted(
        [p for p in _RESULTS_DIR.glob("sec_bench_*.json") if not p.name.endswith(".partial.json")],
        key=os.path.getmtime,
        reverse=True,
    )

    # Try loading the latest result that has matrix data
    for rf in result_files:
        try:
            data = json.loads(rf.read_text())
            mr = data.get("matrix_results", {})
            if mr and mr.get("total_units", 0) > 0:
                return {
                    "status": "present",
                    "source": rf.name,
                    "total_units": mr.get("total_units", 0),
                    "verified": mr.get("verified", 0),
                    "rejected": mr.get("rejected", 0),
                    "indeterminate": mr.get("indeterminate", 0),
                    "pass_rate": mr.get("pass_rate", 0.0),
                    "matrix_results": mr,
                }
        except (json.JSONDecodeError, OSError):
            continue

    # Build theoretical coverage from challenge_classes.yaml and matrix
    theoretical = _build_theoretical_coverage()
    if theoretical:
        return {"status": "stale", "source": "theoretical (no recent bench run)", **theoretical}

    return {"status": "absent", "total_units": 0, "verified": 0, "rejected": 0, "indeterminate": 0}


def _build_theoretical_coverage() -> dict | None:
    """Build theoretical coverage from challenge_classes.yaml + PROMPTS."""
    try:
        import yaml

        from ._data import PROMPTS
        from .matrix import _classify_domain
    except ImportError:
        return None

    cc_path = _PROJECT_ROOT / "config" / "challenge_classes.yaml"
    challenge_classes = []
    if cc_path.exists():
        cc_data = yaml.safe_load(cc_path.read_text())
        challenge_classes = cc_data.get("classes", [])

    by_class: dict[str, dict] = {}
    for cls in challenge_classes:
        cid = cls.get("id", "")
        vulhub = cls.get("vulhub", [])
        purpose_built = cls.get("purpose_built")
        resolved = len(vulhub) + (1 if purpose_built else 0)
        if resolved == 0:
            continue
        domain = _classify_domain("", cid)
        by_class[cid] = {
            "resolved": resolved,
            "ran": 0,
            "verified": 0,
            "rejected": 0,
            "indeterminate": 0,
            "domain": domain,
        }

    by_domain: dict[str, dict] = {}
    for _cid, stats in by_class.items():
        d = stats.get("domain", "mixed")
        entry = by_domain.setdefault(d, {"resolved": 0, "ran": 0, "verified": 0})
        entry["resolved"] += stats["resolved"]

    # Per-scenario coverage (from PROMPTS)
    scenarios = {}
    for prompt_key, pd in PROMPTS.items():
        domain = _classify_domain(prompt_key)
        oracle = pd.get("oracle")
        scenarios[prompt_key] = {
            "resolved": 1,
            "ran": 0,
            "verified": 0,
            "rejected": 0,
            "oracle": oracle,
            "domain": domain,
        }
        entry = by_domain.setdefault(domain, {"resolved": 0, "ran": 0, "verified": 0})
        entry["resolved"] += 1

    return {
        "by_class": by_class,
        "by_scenario": scenarios,
        "by_domain": by_domain,
        "total_resolved": sum(s["resolved"] for s in by_class.values()),
        "total_scenarios": len(scenarios),
        "total_classes": len(by_class),
    }


def _read_discipline_breadth() -> dict:
    """Per-discipline (web/AD/RE/cloud/…) depth + red/blue/purple coverage."""
    try:
        from ._data import PROMPTS
        from .matrix import _DOMAIN_KEYWORDS, _classify_domain
    except ImportError:
        return {"status": "absent", "disciplines": {}}

    disciplines: dict[str, dict] = {}
    for label, _keywords in _DOMAIN_KEYWORDS.items():
        disciplines[label] = {"scenario_count": 0, "red": False, "blue": False, "purple": False}

    # Red: scenario exists
    for prompt_key, _prompt_data in PROMPTS.items():
        domain = _classify_domain(prompt_key)
        if domain not in disciplines:
            disciplines[domain] = {
                "scenario_count": 0,
                "red": False,
                "blue": False,
                "purple": False,
            }
        disciplines[domain]["scenario_count"] += 1
        disciplines[domain]["red"] = True

    # Blue: check if any blue-specific scenarios exist or blue models can be run
    try:
        __import__("tests.benchmarks.bench_security.blue", fromlist=["_fetch_blue_telemetry"])

        blue_available = True
    except ImportError:
        blue_available = False

    # Purple: both red + blue
    for d in disciplines.values():
        if blue_available and d["red"]:
            d["blue"] = True
        if d["red"] and d["blue"]:
            d["purple"] = True

    # Mark gaps
    for _domain, stats in disciplines.items():
        if not stats["red"] and not stats["blue"]:
            stats["status"] = "absent"
        elif stats["red"] and not stats["blue"]:
            stats["status"] = "red_only"
        elif stats["red"] and stats["blue"]:
            stats["status"] = "full_spectrum"

    return {"status": "present", "blue_available": blue_available, "disciplines": disciplines}


def _read_journal_summary() -> dict:
    """Prior-run outcomes, recurring failures from field_journal."""
    index_path = _JOURNAL_DIR / "_index.json"
    if index_path.exists():
        try:
            data = json.loads(index_path.read_text())
            return {
                "status": "present",
                "total_entries": data.get("total_entries", 0),
                "by_category": data.get("by_category", {}),
                "outcomes": data.get("outcomes", {}),
                "top_pitfalls": data.get("top_pitfalls", []),
                "generated_at": data.get("generated_at", ""),
            }
        except (json.JSONDecodeError, OSError):
            pass

    # Try building from raw entries
    entries = sorted(
        [p for p in _JOURNAL_DIR.glob("*.json") if p.name != "_index.json"],
    )
    if entries:
        by_category: dict[str, int] = {}
        outcomes = {"goal_met": 0, "partial": 0, "failed": 0}
        all_pitfalls: list[dict] = []
        for p in entries:
            try:
                e = json.loads(p.read_text())
            except (json.JSONDecodeError, OSError):
                continue
            cat = e.get("scenario_category", "other")
            by_category[cat] = by_category.get(cat, 0) + 1
            oc = e.get("outcome", "partial")
            outcomes[oc] = outcomes.get(oc, 0) + 1
            for pit in e.get("pitfalls", []):
                all_pitfalls.append({"file": p.name, **pit})
        top_pitfalls = sorted(all_pitfalls, key=lambda x: len(x.get("problem", "")), reverse=True)[
            :20
        ]
        return {
            "status": "stale",
            "total_entries": len(entries),
            "by_category": by_category,
            "outcomes": outcomes,
            "top_pitfalls": top_pitfalls,
            "generated_at": "",
        }

    return {
        "status": "absent",
        "total_entries": 0,
        "by_category": {},
        "outcomes": {},
        "top_pitfalls": [],
    }


# ── Phase 1: build self-index ─────────────────────────────────────────────────


def build_self_index() -> dict:
    """Aggregate the system's own state from existing signals. READ-ONLY.
    Returns a structured weakness view — never modifies anything."""
    return {
        "validator": _read_validator_health(),
        "oracles": _read_oracle_fidelity(),
        "coverage": _read_coverage(),
        "disciplines": _read_discipline_breadth(),
        "journal": _read_journal_summary(),
        "generated_at": datetime.now(tz=UTC).isoformat(),
    }


# ── Phase 2: weakness ranking ─────────────────────────────────────────────────

# Transparent, inspectable score formula (documented)
_SCORE_RULES = {
    "validator_fail": 30,  # broken subsystem
    "oracle_experimental": 10,  # fidelity gap (single-response marker)
    "oracle_differential": 15,  # fidelity gap (multi-response)
    "oracle_oob": 20,  # fidelity gap (no local check)
    "class_zero_verified": 25,  # runs but 0/N verified
    "class_low_pass_rate": 15,  # pass rate < 0.5
    "discipline_red_only": 20,  # red-only, no blue/purple path
    "discipline_absent": 25,  # no scenarios at all in domain
    "machine_red_coverage": 25,  # provisioned but unexercised (RED in coverage)
    "scenario_heuristic_only": 15,  # scenario with no stable oracle
    "journal_recurring_failure": 10,  # repeated stumble in journal
}


def _oracle_tier_score(tier: str) -> int:
    """Map oracle tier to weakness score."""
    tier_map = {
        "experimental": _SCORE_RULES["oracle_experimental"],
        "differential": _SCORE_RULES["oracle_differential"],
        "oob": _SCORE_RULES["oracle_oob"],
    }
    return tier_map.get(tier, 0)


def rank_weaknesses(index: dict) -> list[dict]:
    """Rank the system's weak spots by a transparent, inspectable score. READ-ONLY.
    Each entry: {area, kind, evidence, score, why}. No proposals — just the ranked view."""
    weaknesses: list[dict] = []

    # 1. Failing validator checks
    validator = index.get("validator", {})
    for check_name, check_data in validator.get("checks", {}).items():
        if check_data.get("status") == "FAIL":
            weaknesses.append(
                {
                    "area": f"validator:{check_name}",
                    "kind": "failing_check",
                    "evidence": check_data.get("detail", ""),
                    "score": _SCORE_RULES["validator_fail"],
                    "why": "broken subsystem — validator check failing",
                }
            )

    # 2. Heuristic-tier oracles
    oracles = index.get("oracles", {})
    for oid, odata in oracles.get("oracles", {}).items():
        tier = odata.get("tier", "stable")
        score = _oracle_tier_score(tier)
        if score > 0:
            weaknesses.append(
                {
                    "area": f"oracle:{oid}",
                    "kind": f"oracle_tier_{tier}",
                    "evidence": f"tier={tier}, kind={odata.get('kind', '?')}",
                    "score": score,
                    "why": f"fidelity gap — {tier}-tier oracle cannot produce VERIFIED verdicts",
                }
            )

    # 3. Coverage: classes with 0 verified / N ran
    coverage = index.get("coverage", {})
    by_class = coverage.get("by_class", {})
    if isinstance(by_class, dict):
        for cid, stats in by_class.items():
            resolved = stats.get("resolved", 0)
            verified = stats.get("verified", 0)
            ran = stats.get("ran", 0)
            if resolved > 0 and ran > 0 and verified == 0:
                weaknesses.append(
                    {
                        "area": f"class:{cid}",
                        "kind": "class_zero_verified",
                        "evidence": f"resolved={resolved}, ran={ran}, verified={verified}",
                        "score": _SCORE_RULES["class_zero_verified"],
                        "why": "coverage that runs but never proves — 0 verified",
                    }
                )
            elif ran > 0 and verified / max(ran, 1) < 0.5:
                weaknesses.append(
                    {
                        "area": f"class:{cid}",
                        "kind": "class_low_pass_rate",
                        "evidence": f"resolved={resolved}, ran={ran}, verified={verified}",
                        "score": _SCORE_RULES["class_low_pass_rate"],
                        "why": f"low pass rate ({verified}/{ran} verified)",
                    }
                )

    # 4. RED machines: resolved > 0 but ran == 0 (provisioned, unexercised)
    for cid, stats in (by_class or {}).items():
        resolved = stats.get("resolved", 0)
        ran = stats.get("ran", 0)
        if resolved > 0 and ran == 0:
            weaknesses.append(
                {
                    "area": f"class:{cid}",
                    "kind": "machine_red_coverage",
                    "evidence": f"resolved={resolved}, ran=0 (provisioned but unexercised)",
                    "score": _SCORE_RULES["machine_red_coverage"],
                    "why": "provisioned but unexercised — RED in coverage",
                }
            )

    # 5. Discipline gaps (red-only, absent)
    disciplines = index.get("disciplines", {})
    for domain, ddata in (disciplines.get("disciplines", {}) or {}).items():
        status = ddata.get("status", "absent")
        if status == "absent":
            weaknesses.append(
                {
                    "area": f"discipline:{domain}",
                    "kind": "discipline_absent",
                    "evidence": "no scenarios in this domain",
                    "score": _SCORE_RULES["discipline_absent"],
                    "why": f"no scenarios at all in {domain} domain",
                }
            )
        elif status == "red_only":
            weaknesses.append(
                {
                    "area": f"discipline:{domain}",
                    "kind": "discipline_red_only",
                    "evidence": f"{ddata.get('scenario_count', 0)} scenarios, red-only",
                    "score": _SCORE_RULES["discipline_red_only"],
                    "why": f"red-only — no blue/purple path in {domain}",
                }
            )

    # 6. Scenarios with no stable oracle (heuristic-only coverage)
    by_scenario = coverage.get("by_scenario", {})
    if isinstance(by_scenario, dict):
        for skey, sdata in by_scenario.items():
            oracle = sdata.get("oracle")
            if oracle is None:
                weaknesses.append(
                    {
                        "area": f"scenario:{skey}",
                        "kind": "scenario_heuristic_only",
                        "evidence": "no oracle — heuristic-only scoring",
                        "score": _SCORE_RULES["scenario_heuristic_only"],
                        "why": "scenario scored heuristically (no oracle), results un-oracled",
                    }
                )

    # 7. Recurring journal failures
    journal = index.get("journal", {})
    top_pitfalls = journal.get("top_pitfalls", [])
    recurring = {}
    for pit in top_pitfalls:
        problem = pit.get("problem", "")
        if problem:
            recurring[problem] = recurring.get(problem, 0) + 1
    for problem, count in recurring.items():
        if count >= 2:
            weaknesses.append(
                {
                    "area": "journal:recurring_pitfall",
                    "kind": "journal_recurring_failure",
                    "evidence": f"'{problem[:80]}' (seen {count}x)",
                    "score": _SCORE_RULES["journal_recurring_failure"],
                    "why": "recurring pitfall — repeated stumble",
                }
            )

    # Sort by score descending, then area for determinism
    weaknesses.sort(key=lambda w: (-w["score"], w["area"]))
    return weaknesses


# ── Phase 3: CLI + report ─────────────────────────────────────────────────────


def print_self_index(index: dict, weaknesses: list[dict]) -> None:
    """Print the human-readable self-view + weakness ranking."""
    print("Portal 5 — Self-Legibility Index")
    print("=" * 60)

    # Validator summary
    v = index.get("validator", {})
    print(f"\nValidator health: {v.get('status', '?')}")
    if v.get("status") == "present":
        print(
            f"  {v.get('passes', 0)} pass · {v.get('fails', 0)} fail · "
            f"{v.get('warns', 0)} warn · {v.get('skips', 0)} skip"
        )
        for check_name, check_data in sorted(v.get("checks", {}).items()):
            if check_data.get("status") != "PASS":
                print(
                    f"  {'!' if check_data['status'] == 'FAIL' else '?'} {check_name}: {check_data.get('detail', '')}"
                )

    # Oracle fidelity
    o = index.get("oracles", {})
    print(f"\nOracle fidelity: {o.get('status', '?')}")
    if o.get("status") == "present":
        print(
            f"  {o.get('total_oracles', 0)} oracles: "
            f"{o.get('stable_count', 0)} stable, "
            f"{o.get('heuristic_count', 0)} heuristic"
        )
        print(f"  Tiers: {o.get('tiers', {})}")

    # Coverage
    c = index.get("coverage", {})
    print(f"\nCoverage: {c.get('status', '?')}")
    if c.get("status") in ("present", "stale"):
        print(f"  Source: {c.get('source', '?')}")
        if c.get("total_units", 0) > 0:
            print(f"  Units: {c.get('total_units', 0)} resolved, {c.get('verified', 0)} verified")
        by_class = c.get("by_class", {})
        if isinstance(by_class, dict) and by_class:
            print(f"\n  {'Class':<35} {'Resolved':>9} {'Ran':>5} {'Verified':>9} {'Domain':>10}")
            print("  " + "-" * 70)
            for cid, stats in sorted(by_class.items()):
                print(
                    f"  {cid:<35} {stats.get('resolved', 0):>9} {stats.get('ran', 0):>5}"
                    f" {stats.get('verified', 0):>9} {stats.get('domain', '?'):>10}"
                )

    # Discipline breadth
    d = index.get("disciplines", {})
    print(f"\nDiscipline breadth: {d.get('status', '?')}")
    for domain, ddata in sorted((d.get("disciplines", {}) or {}).items()):
        print(
            f"  {domain:<12} scenarios={ddata.get('scenario_count', 0):>2}"
            f"  red={'✓' if ddata.get('red') else '✗'}"
            f"  blue={'✓' if ddata.get('blue') else '✗'}"
            f"  purple={'✓' if ddata.get('purple') else '✗'}"
            f"  [{ddata.get('status', '?')}]"
        )

    # Journal
    j = index.get("journal", {})
    print(f"\nField journal: {j.get('status', '?')}")
    if j.get("total_entries", 0) > 0:
        print(f"  {j.get('total_entries', 0)} entries")
        print(f"  Outcomes: {j.get('outcomes', {})}")
        print(f"  By category: {j.get('by_category', {})}")

    # Weakness ranking
    print(f"\n{'─' * 60}")
    print("Weakness ranking (transparent, inspectable score)")
    print("Score formula:", json.dumps(_SCORE_RULES, indent=2))
    print(f"\n  {'Rank':>4}  {'Score':>5}  {'Kind':<28}  {'Area'}")
    print(f"  {'─' * 4}  {'─' * 5}  {'─' * 28}  {'─' * 35}")
    for i, w in enumerate(weaknesses, 1):
        print(f"  {i:>4}  {w['score']:>5}  {w['kind']:<28}  {w['area']}")
        print(f"        {'':>5}  {'':<28}  {'↳ ' + w['why']}")


def self_index_main(*, as_json: bool = False) -> int:
    """Entry point: build index, rank weaknesses, print report."""
    index = build_self_index()
    weaknesses = rank_weaknesses(index)

    if as_json:
        import json as _json_mod

        output = {
            "index": index,
            "weaknesses": weaknesses,
        }
        print(_json_mod.dumps(output, indent=2))
    else:
        print_self_index(index, weaknesses)

    return 0
