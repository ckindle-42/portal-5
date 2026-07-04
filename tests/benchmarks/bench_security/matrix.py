"""Scenario × container matrix — the seam between library and on-demand containers.

build_run_matrix: crosses scenarios + challenge classes with the vulhub catalog.
run_matrix: spins each target ephemerally, runs the chain, scores with the named oracle.
"""

from __future__ import annotations

import logging
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from ._data import _LAB_EXEC_AVAILABLE, PROMPTS
from .oracles import ORACLES, verify_finding

_log = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# module-level sentinel — evidence the oracle must always map to indeterminate, never verified
DISPATCH_NOT_RUN = "__DISPATCH_NOT_RUN__"

LAB_VULHUB_HOST_ROOT = os.environ.get("LAB_VULHUB_HOST_ROOT", "/opt/vulhub")


# ── Telemetry backend protocol (P2.2) ────────────────────────────────────────


class TelemetryBackend(Protocol):
    """Backend-agnostic telemetry query interface.

    Implementations: WazuhBackend (now), SplunkBackend (future).
    The protocol is the contract — blue.py calls .query() without knowing
    which SIEM answers.
    """

    def query(self, technique_id: str, window: dict) -> dict:
        """Query telemetry for a technique. Returns {signals, source, matched}."""
        ...


class WazuhBackend:
    """Wazuh/OpenSearch telemetry backend (first adapter).

    Reads LAB_OPENSEARCH_URL / wazuh-alerts-* as blue.py does today.
    Falls back to synthetic-fallback when no real telemetry is available.
    """

    def __init__(self, opensearch_url: str = ""):
        self.opensearch_url = opensearch_url or os.environ.get("LAB_OPENSEARCH_URL", "")

    def query(self, technique_id: str, window: dict) -> dict:
        """Query Wazuh alerts index for the technique's signals."""
        if not self.opensearch_url:
            return {"signals": [], "source": "synthetic-fallback", "matched": False}
        # Live query would hit opensearch here — placeholder for the adapter seam
        return {"signals": [], "source": "wazuh", "matched": False}


# ── Data classes ──────────────────────────────────────────────────────────────


@dataclass
class RunUnit:
    """A single test unit: one scenario or class against one container."""

    id: str
    kind: str  # "scenario" | "class"
    target_spec: str  # vulhub path or purpose_built dir
    oracle: str | None  # named oracle id, or None for heuristic
    scoring: str  # "oracle" | "heuristic"
    domain: str  # "web" | "ad" | "linux" | "cloud" | "mixed"
    spin: str  # "ephemeral" | "static"
    challenge_class: str = ""  # parent class id (for class-derived units)
    scenario_key: str = ""  # parent scenario key (for scenario-derived units)
    vulhub_path: str = ""  # resolved vulhub directory path
    technique_ids: list[str] = field(default_factory=list)  # MITRE ATT&CK IDs
    has_telemetry: bool = False  # whether a telemetry source exists for this target


@dataclass
class RunResult:
    """Result of executing one RunUnit."""

    unit_id: str
    status: str  # "verified" | "rejected" | "indeterminate" | "error" | "dry_run"
    oracle_verdict: dict | None = None
    lab_output: str = ""
    elapsed_s: float = 0.0
    error: str = ""
    blue_result: dict | None = None
    purple_result: dict | None = None


# ── Domain classification ─────────────────────────────────────────────────────

_DOMAIN_KEYWORDS: dict[str, list[str]] = {
    "web": [
        "sqli",
        "xss",
        "lfi",
        "rce",
        "ssrf",
        "webshell",
        "tomcat",
        "redis",
        "php",
        "nginx",
        "flask",
        "jwt",
        "api",
        "graphql",
    ],
    "ad": [
        "kerberos",
        "kerberoast",
        "dcsync",
        "golden",
        "asrep",
        "rbcd",
        "bloodhound",
        "adcs",
        "trust",
        "pth",
        "eternalblue",
        "smb",
        "relay",
    ],
    "linux": ["linux", "privesc", "cron", "nfs", "suid", "kernel", "container", "docker"],
    "cloud": ["cloud", "k8s", "aws", "ssrf-metadata", "lambda"],
}


def _classify_domain(scenario_key: str, class_id: str = "") -> str:
    """Classify a unit into a domain for filtering."""
    text = f"{scenario_key} {class_id}".lower()
    for domain, keywords in _DOMAIN_KEYWORDS.items():
        if any(kw in text for kw in keywords):
            return domain
    return "mixed"


# ── Vulhub glob expansion (resolved ON the live host, LXC 112 — never local fs) ────────────


def _expand_vulhub_globs(patterns: list[str], vulhub_root: str | Path | None = None) -> list[str]:
    """Expand vulhub glob patterns against the vulhub clone on host 112, via _host_exec.

    E.g. 'fastjson/*' → ['fastjson/CVE-2017-7525', 'fastjson/CVE-2019-...']
    Returns list of relative paths from vulhub_root. A pattern matching no real host env
    resolves to zero paths — those units are built with zero targets and honestly score
    indeterminate (never silently fabricated).
    """
    from scripts.lab_host import _host_exec

    root = str(vulhub_root) if vulhub_root else LAB_VULHUB_HOST_ROOT
    resolved: list[str] = []
    for pat in patterns:
        # `; true` at the end so a mid-loop non-match (e.g. a dir without docker-compose.yml)
        # doesn't flip the whole command's exit code and hide the matches found before it.
        cmd = (
            f"bash -lc 'for d in {root}/{pat}/; do "
            f'[ -f "${{d}}docker-compose.yml" ] && echo "$d"; done; true\''
        )
        r = _host_exec(cmd, timeout=20)
        if not r.get("ok"):
            continue
        for line in r["output"].splitlines():
            line = line.strip().rstrip("/")
            if not line:
                continue
            rel = os.path.relpath(line, root)
            resolved.append(rel)
    return sorted(resolved)


def _resolve_challenge_class(cls: dict, vulhub_root: str | Path | None = None) -> list[str]:
    """Resolve a challenge class to its list of vulhub target paths (on the host)."""
    vulhub_patterns = cls.get("vulhub", [])
    if not vulhub_patterns:
        return []
    return _expand_vulhub_globs(vulhub_patterns, vulhub_root)


# ── Build run matrix ──────────────────────────────────────────────────────────


def build_run_matrix(
    *,
    scenarios: bool = True,
    classes: bool = True,
    domains: list[str] | None = None,
    vulhub_root: str | Path | None = None,
) -> list[RunUnit]:
    """Cross the scenario + challenge-class library with the container catalog.

    For each scenario/class, resolve its target(s):
      - challenge class → its vulhub paths (expand globs) + purpose_built dirs
      - scenario → its declared target, OR a challenge_class tag mapping it to containers

    Returns run units. This is where 56 scenarios × N containers becomes
    hundreds of real test units.
    """
    import yaml

    from ._data import EXEC_SEQUENCES

    units: list[RunUnit] = []
    vulhub_root = str(vulhub_root) if vulhub_root else LAB_VULHUB_HOST_ROOT

    # Load challenge classes
    cc_path = _PROJECT_ROOT / "config" / "challenge_classes.yaml"
    challenge_classes: list[dict] = []
    if cc_path.exists():
        cc_data = yaml.safe_load(cc_path.read_text())
        challenge_classes = cc_data.get("classes", [])

    # Telemetry-capable domains
    telemetry_domains = {"web", "linux"}

    # ── Build from challenge classes ──────────────────────────────────────────
    if classes:
        for cls in challenge_classes:
            cls_id = cls.get("id", "")
            oracle = cls.get("ground_truth", {}).get("oracle", "")
            vulhub_paths = _resolve_challenge_class(cls, vulhub_root)
            purpose_built = cls.get("purpose_built")

            # Filter by domain
            domain = _classify_domain("", cls_id)
            if domains and domain not in domains:
                continue

            # Expand vulhub paths into individual units
            for vp in vulhub_paths:
                unit_id = f"class:{cls_id}:{vp.replace('/', '_')}"
                units.append(
                    RunUnit(
                        id=unit_id,
                        kind="class",
                        target_spec=vp,
                        oracle=oracle if oracle else None,
                        scoring="oracle" if oracle else "heuristic",
                        domain=domain,
                        spin="ephemeral",
                        challenge_class=cls_id,
                        vulhub_path=vp,
                        has_telemetry=domain in telemetry_domains,
                    )
                )

            # Purpose-built targets
            if purpose_built:
                unit_id = f"class:{cls_id}:purpose_built"
                units.append(
                    RunUnit(
                        id=unit_id,
                        kind="class",
                        target_spec=purpose_built,
                        oracle=oracle if oracle else None,
                        scoring="oracle" if oracle else "heuristic",
                        domain=domain,
                        spin="ephemeral",
                        challenge_class=cls_id,
                        vulhub_path=purpose_built,
                        has_telemetry=domain in telemetry_domains,
                    )
                )

    # ── Build from scenarios ──────────────────────────────────────────────────
    if scenarios:
        for prompt_key, prompt_data in PROMPTS.items():
            oracle = prompt_data.get("oracle")
            scoring = prompt_data.get("scoring", "oracle" if oracle else "heuristic")
            domain = _classify_domain(prompt_key)
            if domains and domain not in domains:
                continue

            # Each scenario maps to at least one run unit
            # If it has an exec_sequence, use that to determine target
            exec_seq = prompt_data.get("exec_sequence", EXEC_SEQUENCES.get(prompt_key, []))

            # Determine target from exec_sequence hints or lab context
            target_spec = _infer_target(prompt_key, exec_seq)

            unit_id = f"scenario:{prompt_key}"
            units.append(
                RunUnit(
                    id=unit_id,
                    kind="scenario",
                    target_spec=target_spec,
                    oracle=oracle,
                    scoring=scoring,
                    domain=domain,
                    spin="static",  # scenarios use existing lab targets
                    scenario_key=prompt_key,
                    technique_ids=prompt_data.get("detect_ground_truth", []),
                    has_telemetry=domain in telemetry_domains,
                )
            )

    _log.info(
        "Built matrix: %d units (%d from classes, %d from scenarios)",
        len(units),
        sum(1 for u in units if u.kind == "class"),
        sum(1 for u in units if u.kind == "scenario"),
    )
    return units


def _infer_target(prompt_key: str, exec_seq: list | dict) -> str:
    """Infer the target spec from a scenario's exec sequence hints."""
    if isinstance(exec_seq, dict):
        exec_seq = exec_seq.get("steps", [])

    # Extract target from tool_hint fields
    for step in exec_seq:
        if isinstance(step, dict):
            hint = step.get("tool_hint", "")
            if "$LAB_TARGET_DC" in hint or "10.10.11.21" in hint:
                return "dc01"
            if "$LAB_TARGET_SRV" in hint or "10.10.11.33" in hint:
                return "srv01"
            if "$LAB_TARGET_WEB" in hint or "10.10.11.50" in hint:
                return "lab-vulhub"
            if "$LAB_TARGET_META3" in hint:
                return "meta3"
    # Fallback to lab-vulhub for web-oriented scenarios
    return "lab-vulhub"


# ── Run matrix ────────────────────────────────────────────────────────────────


def run_matrix(
    units: list[RunUnit],
    *,
    dry_run: bool = False,
    lab_exec: bool = False,
    max_concurrent: int = 3,
    purple: bool = False,
) -> dict:
    """Execute the run matrix: spin → run → score → teardown per unit.

    Respects dry_run (plan only) and _LAB_EXEC_AVAILABLE (synthetic → indeterminate).
    Aggregates pass/verified/rejected.
    """
    results: list[RunResult] = []
    t0 = time.monotonic()

    for unit in units:
        if dry_run:
            results.append(
                RunResult(
                    unit_id=unit.id,
                    status="dry_run",
                    oracle_verdict={"oracle": unit.oracle, "plan": "spin→run→score→teardown"},
                )
            )
            continue

        if not _LAB_EXEC_AVAILABLE:
            results.append(
                RunResult(
                    unit_id=unit.id,
                    status="indeterminate",
                    error="lab exec not available — cannot run against real targets",
                )
            )
            continue

        result = _execute_unit(unit, lab_exec=lab_exec, purple=purple)
        results.append(result)

    elapsed = time.monotonic() - t0
    return _aggregate_results(results, elapsed, len(units))


def _execute_unit(unit: RunUnit, *, lab_exec: bool, purple: bool) -> RunResult:
    """Execute a single run unit against a real target."""
    t0 = time.monotonic()

    try:
        # 1. Spin up container (if ephemeral)
        if unit.spin == "ephemeral":
            spin_result = _spin_target(unit.target_spec, lab_exec=lab_exec)
            if not spin_result.get("ok"):
                return RunResult(
                    unit_id=unit.id,
                    status="error",
                    error=f"spin failed: {spin_result.get('error', 'unknown')}",
                    elapsed_s=time.monotonic() - t0,
                )

        # 2. Run the exec chain against the live target
        scenario_start = t0
        lab_output = _run_against_target(unit, lab_exec=lab_exec)

        # 2b. Collect + ship telemetry to Splunk, then wait for it to be indexed
        telemetry_error = ""
        if purple and unit.has_telemetry and unit.technique_ids:
            try:
                from .siem.collect import collect_target
                from .siem.hec_ship import ship_batch
                from .siem.index_wait import wait_indexed

                tele = collect_target(
                    unit.target_spec,
                    unit.kind,
                    since_epoch=scenario_start,
                    dry_run=not lab_exec,
                )
                shipped = 0
                for sourcetype, lines in tele.items():
                    if lines:
                        ship_batch(
                            [{"raw": line} for line in lines],
                            sourcetype=sourcetype,
                            host=unit.target_spec,
                        )
                        shipped += len(lines)
                if shipped:
                    wait_indexed(
                        host=unit.target_spec,
                        since_epoch=scenario_start,
                        expect_min=1,
                        timeout_s=30,
                    )
            except Exception as exc:
                # Telemetry collection never blocks scoring (a real value this
                # keeps) — but a silent `except: pass` here meant a genuine
                # collection/shipping failure looked identical to "nothing to
                # collect," indistinguishable from DETECTION_MISSING at the
                # result level (flagged in coding_task/f1/DESIGN_SEC_UNIFIED_
                # RBP_FRAMEWORK_V3.md as a verified defect). Record it instead.
                telemetry_error = f"TELEMETRY_COLLECTION_FAILED: {exc}"

        # 3. Score with the named oracle
        oracle_verdict = None
        if lab_output == DISPATCH_NOT_RUN or not lab_output.strip():
            # No dispatch path (tier-3) or empty evidence — never let this reach an oracle;
            # the governing rule is no path emits verified without real host output.
            status = "indeterminate"
            oracle_verdict = {
                "oracle": unit.oracle,
                "reason": "no dispatch — DISPATCH_NOT_RUN or empty evidence",
            }
        elif unit.oracle and unit.oracle in ORACLES:
            finding = {"oracle": unit.oracle}
            observations = {}
            verdict = verify_finding(finding, lab_output, observations, required=2)
            oracle_verdict = {
                "oracle": verdict.oracle,
                "verified": verdict.verified,
                "evidence": verdict.evidence[:200],
                "honesty_claim": verdict.honesty_claim,
                "reproductions": verdict.reproductions,
                "required": verdict.required,
            }
            status = "verified" if verdict.verified else "rejected"
        elif unit.oracle is None and unit.scoring == "heuristic":
            # Explicit heuristic — no oracle, score on text-match
            status = "indeterminate"
            oracle_verdict = {
                "oracle": None,
                "scoring": "heuristic",
                "reason": "no oracle — heuristic only",
            }
        else:
            status = "rejected"
            oracle_verdict = {"oracle": unit.oracle, "reason": "oracle not in registry"}

        # 4. Blue/purple (if requested and telemetry available)
        blue_result = None
        purple_result = None
        if purple and unit.has_telemetry and unit.technique_ids:
            blue_result = _run_blue_on_unit(unit, lab_output, lab_exec=lab_exec)
            if blue_result and status == "verified":
                purple_result = _score_purple_on_unit(unit, blue_result)

        # 5. Teardown (if ephemeral)
        if unit.spin == "ephemeral":
            _teardown_target(unit.target_spec, lab_exec=lab_exec)

        return RunResult(
            unit_id=unit.id,
            status=status,
            oracle_verdict=oracle_verdict,
            lab_output=lab_output[:500],
            elapsed_s=time.monotonic() - t0,
            blue_result=blue_result,
            purple_result=purple_result,
            error=telemetry_error,
        )

    except Exception as exc:
        return RunResult(
            unit_id=unit.id,
            status="error",
            error=str(exc),
            elapsed_s=time.monotonic() - t0,
        )


def _spin_target(target_spec: str, *, lab_exec: bool) -> dict:
    """Spin up a target container. Returns {ok, error}."""
    try:
        from scripts.lab_targets import cmd_up

        result = cmd_up(target_spec, dry_run=not lab_exec)
        return {"ok": result.get("status") != "error", "detail": result}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def _teardown_target(target_spec: str, *, lab_exec: bool) -> dict:
    """Tear down a target container."""
    try:
        from scripts.lab_targets import cmd_down

        result = cmd_down(target_spec, dry_run=not lab_exec)
        return {"ok": True, "detail": result}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


# ── Tier-1 proven phase functions (verified against PROMPTS — see task Instruction #1) ───────
# dcsync/meta3_compromise/srv01_local_privesc/mbptl_full_chain are NOT PROMPTS keys, so no
# scenario-derived unit can ever carry those scenario_key values; they're intentionally excluded.
try:
    from bench_lab_exec import (
        _phase_asrep,
        _phase_kerberoast,
        _phase_vulhub_lfi,
        _phase_vulhub_log4shell,
        _phase_vulhub_redis,
        _phase_vulhub_tomcat,
    )

    _PHASE_MAP: dict[str, object] = {
        "kerberoasting": _phase_kerberoast,
        "asrep_roasting": _phase_asrep,
        "log4shell_rce": _phase_vulhub_log4shell,
        "redis_to_rce": _phase_vulhub_redis,
        "tomcat_manager": _phase_vulhub_tomcat,
        "htb_lfi_log_poison": _phase_vulhub_lfi,
    }
except ImportError:
    _PHASE_MAP = {}


def _phase_result_to_evidence(result: dict) -> str:
    """Proven phases return {ok, output, detail,...}; the oracle scores the real output text.
    Return output plus detail so the named-proof markers the phase produced stay visible."""
    return f"{result.get('output', '')}\n[phase-detail] {result.get('detail', '')}".strip()


def _lab_env_vars() -> dict[str, str]:
    """The canonical lab-env values — reused from bench_lab_exec, never a second config.
    Re-read (not cached) each call: bench_lab_exec's DC/SRV/WEB are read from os.environ at
    import time, but tests and callers may patch them per-scenario."""
    try:
        import bench_lab_exec as _lab

        return {
            "LAB_TARGET_DC": _lab.DC,
            "LAB_TARGET_SRV": _lab.SRV,
            "LAB_TARGET_WEB": _lab.WEB,
            "LAB_TARGET_META3_WIN": _lab.LAB_META3,
            "DOMAIN": _lab.DOMAIN,
            "ADMIN_PASS": _lab.ADMIN_PASS,
        }
    except ImportError:
        return {}


def _resolve_env(hint: str, runtime_env: dict | None = None) -> str:
    """Substitute known lab env vars ($LAB_TARGET_DC etc.) into a tool_hint.

    Also substitutes $TARGET_HOST and $TARGET_PORT from runtime_env (the
    readiness gate result) so the dispatched prompt attacks the container's
    REAL published port — the single source of truth.

    Unset/unknown $NAME is left literal so the command visibly fails rather than
    silently mis-targeting (→ indeterminate, never a false verified).
    """
    resolved = hint
    for name, value in _lab_env_vars().items():
        if value:
            resolved = resolved.replace(f"${name}", value)
    # Inject target host/port from readiness gate (Phase 2: port single-source-of-truth)
    if runtime_env:
        if runtime_env.get("TARGET_HOST"):
            resolved = resolved.replace("$TARGET_HOST", str(runtime_env["TARGET_HOST"]))
        if runtime_env.get("TARGET_PORT"):
            resolved = resolved.replace("$TARGET_PORT", str(runtime_env["TARGET_PORT"]))
    return resolved


def _dispatch_exec_sequence(unit: RunUnit, seq: list, *, lab_exec: bool) -> str:
    """Execute each step's real tool_hint via _mcp_call; accumulate REAL output for the oracle.
    No fabricated success markers — dry-run and step-failure both yield honest evidence."""
    from bench_lab_exec import _mcp_call  # sandbox attack-host transport, returns {ok,output}

    transcript: list[str] = []
    for step in seq:
        if not isinstance(step, dict):
            continue
        cmd = _resolve_env(step.get("tool_hint", ""))
        if not lab_exec:
            transcript.append(f"[dry-run] {step.get('step', '?')}: {cmd}")
            continue
        r = _mcp_call(cmd, timeout=step.get("time_budget_s", 120))  # verified key: time_budget_s
        transcript.append(f"[{step.get('step', '?')}] $ {cmd}\n{r.get('output', '')}")
        if not r.get("ok"):  # every step required; halt on failure
            transcript.append(
                f"[dispatch-halt] step '{step.get('step', '?')}' failed; chain incomplete"
            )
            break
    return "\n".join(transcript)  # REAL output only; the oracle's named N/N proof decides verified


def _run_against_target(unit: RunUnit, *, lab_exec: bool) -> str:
    """Run the scenario's exec chain against the live target. Returns output text.

    3-tier router keyed on unit.scenario_key: tier-1 proven phase, tier-2 real exec_sequence,
    tier-3 no path -> DISPATCH_NOT_RUN (oracle must score this indeterminate, never verified).
    """
    fn = _PHASE_MAP.get(unit.scenario_key)
    if fn:
        return _phase_result_to_evidence(fn(dry_run=not lab_exec))

    from ._data import EXEC_SEQUENCES

    seq = EXEC_SEQUENCES.get(unit.scenario_key)
    if seq and isinstance(seq, list) and seq and isinstance(seq[0], dict):
        return _dispatch_exec_sequence(unit, seq, lab_exec=lab_exec)

    return DISPATCH_NOT_RUN


def _run_blue_on_unit(unit: RunUnit, lab_output: str, *, lab_exec: bool) -> dict:
    """Run blue detection on a unit's output."""
    from .blue import _fetch_blue_telemetry

    telemetry = _fetch_blue_telemetry(unit.technique_ids, lab_exec=lab_exec, dry_run=False)
    # Check if any real telemetry was returned
    has_real = any(v.get("source") == "live" for v in telemetry.values())
    return {
        "telemetry": telemetry,
        "has_real_telemetry": has_real,
        "technique_ids": unit.technique_ids,
    }


def _score_purple_on_unit(unit: RunUnit, blue_result: dict) -> dict:
    """Score purple convergence for a unit."""
    has_real = blue_result.get("has_real_telemetry", False)
    if not has_real:
        return {
            "model_competence_score": 0.0,
            "capability_verdict": "INDETERMINATE",
            "source": "synthetic-fallback",
            "status": "indeterminate",
        }
    return {
        "model_competence_score": 0.5,  # placeholder — real scoring in blue.py
        "capability_verdict": "INDETERMINATE",
        "source": "live",
        "status": "converged",
    }


# ── Aggregation ───────────────────────────────────────────────────────────────


def _aggregate_results(results: list[RunResult], elapsed: float, total_units: int) -> dict:
    """Aggregate run results into a summary dict."""
    verified = sum(1 for r in results if r.status == "verified")
    rejected = sum(1 for r in results if r.status == "rejected")
    indeterminate = sum(1 for r in results if r.status == "indeterminate")
    errors = sum(1 for r in results if r.status == "error")
    dry_runs = sum(1 for r in results if r.status == "dry_run")

    return {
        "total_units": total_units,
        "elapsed_s": round(elapsed, 1),
        "verified": verified,
        "rejected": rejected,
        "indeterminate": indeterminate,
        "errors": errors,
        "dry_runs": dry_runs,
        "pass_rate": round(verified / max(verified + rejected, 1), 3),
        "results": results,
    }


# ── Coverage report ───────────────────────────────────────────────────────────


def build_coverage_report(units: list[RunUnit], results: list[RunResult]) -> dict:
    """Build a per-class/scenario coverage report.

    Shows: how many containers resolved, how many ran, how many VERIFIED.
    """
    by_class: dict[str, dict] = {}
    by_scenario: dict[str, dict] = {}

    for unit, result in zip(units, results, strict=False):
        # By challenge class
        if unit.challenge_class:
            entry = by_class.setdefault(
                unit.challenge_class,
                {
                    "resolved": 0,
                    "ran": 0,
                    "verified": 0,
                    "rejected": 0,
                    "indeterminate": 0,
                },
            )
            entry["resolved"] += 1
            if result.status in ("verified", "rejected", "indeterminate"):
                entry["ran"] += 1
            if result.status == "verified":
                entry["verified"] += 1
            elif result.status == "rejected":
                entry["rejected"] += 1
            elif result.status == "indeterminate":
                entry["indeterminate"] += 1

        # By scenario
        if unit.scenario_key:
            entry = by_scenario.setdefault(
                unit.scenario_key,
                {
                    "resolved": 0,
                    "ran": 0,
                    "verified": 0,
                    "rejected": 0,
                    "indeterminate": 0,
                    "oracle": unit.oracle,
                },
            )
            entry["resolved"] += 1
            if result.status in ("verified", "rejected", "indeterminate"):
                entry["ran"] += 1
            if result.status == "verified":
                entry["verified"] += 1
            elif result.status == "rejected":
                entry["rejected"] += 1
            elif result.status == "indeterminate":
                entry["indeterminate"] += 1

    return {
        "by_class": by_class,
        "by_scenario": by_scenario,
        "total_resolved": len(units),
        "total_ran": sum(
            1 for r in results if r.status in ("verified", "rejected", "indeterminate")
        ),
        "total_verified": sum(1 for r in results if r.status == "verified"),
    }
