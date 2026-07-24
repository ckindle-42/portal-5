"""Drift-detection gate — rolling-baseline regression + model-behavior canary
(TASK_SEC_DRIFT_GATE_V1).

The one release-gate concept Portal's absolute gates don't cover: a metric
that degrades run-over-run but never crosses a hard floor, so everything
stays green while quality quietly rots. This is additive analysis over
EXISTING bench results — it changes no scoring and promotes nothing.

Two independent mechanisms:
  1. Rolling-baseline drift: per-metric delta vs a trailing window of prior
     purple-test runs for the same (scenario, blue_model) pair.
  2. Model canary: a tiny fixed deterministic probe suite that detects the
     MODEL ITSELF changed (silent quant/Ollama-version/template shift),
     independent of any scenario.

Both are FLAGS, never verdicts: they never mutate capability_verdict and
never auto-fail a run. Absolute gates still own pass/fail.
"""

from __future__ import annotations

import json
import statistics
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .self_index import _complete_result_files, _run_timestamp_key

RESULTS_DIR = Path(__file__).resolve().parent / "results"
CANARY_DIR = RESULTS_DIR / "canary_baselines"
CANARY_DIR.mkdir(parents=True, exist_ok=True)

TRACKED_METRICS = (
    "blue_f1",
    "detection_coverage",
    "model_competence_score",
    "red_order_accuracy",
)
NOISE_FLOOR = 0.03  # on a 0-1 scale; a drop below this is noise, never REGRESSION
MIN_BASELINE_RUNS = 3
DEFAULT_WINDOW = 7

try:
    from scipy import stats as _scipy_stats

    _SCIPY_AVAILABLE = True
except ImportError:
    _scipy_stats = None
    _SCIPY_AVAILABLE = False


# ── Phase 1: rolling-baseline drift gate ───────────────────────────────────────


@dataclass
class MetricDrift:
    metric: str
    status: str  # OK | DRIFT-WARN | DRIFT-REGRESSION | INSUFFICIENT-BASELINE
    candidate_mean: float | None = None
    baseline_mean: float | None = None
    baseline_stdev: float | None = None
    delta: float | None = None
    n_candidate: int = 0
    n_baseline: int = 0
    method: str = ""

    def to_dict(self) -> dict:
        return {
            "metric": self.metric,
            "status": self.status,
            "candidate_mean": self.candidate_mean,
            "baseline_mean": self.baseline_mean,
            "baseline_stdev": self.baseline_stdev,
            "delta": self.delta,
            "n_candidate": self.n_candidate,
            "n_baseline": self.n_baseline,
            "method": self.method,
        }


@dataclass
class PairDrift:
    scenario: str
    blue_model: str
    candidate_ts: str
    metrics: list[MetricDrift] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "scenario": self.scenario,
            "blue_model": self.blue_model,
            "candidate_ts": self.candidate_ts,
            "metrics": [m.to_dict() for m in self.metrics],
        }


def _load_purple_runs() -> list[tuple[str, dict]]:
    """All complete sec_*.json results containing purple_tests, newest first."""
    runs = []
    for p in _complete_result_files():
        try:
            data = json.loads(p.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        if data.get("purple_tests"):
            ts = _run_timestamp_key(p) or data.get("timestamp", p.name)
            runs.append((ts, data))
    return runs


def _known_pairs(runs: list[tuple[str, dict]]) -> set[tuple[str, str]]:
    pairs = set()
    for _ts, data in runs:
        for pt in data.get("purple_tests", []):
            scenario = pt.get("scenario")
            blue = pt.get("blue_model")
            if scenario and blue:
                pairs.add((scenario, blue))
    return pairs


def _values_for_run(data: dict, scenario: str, blue_model: str, metric: str) -> list[float]:
    return [
        pt[metric]
        for pt in data.get("purple_tests", [])
        if pt.get("scenario") == scenario
        and pt.get("blue_model") == blue_model
        and isinstance(pt.get(metric), (int, float))
    ]


def _metric_drift(
    metric: str,
    candidate_values: list[float],
    baseline_run_values: list[list[float]],
) -> MetricDrift:
    baseline_pooled = [v for run_vals in baseline_run_values for v in run_vals]
    if len(baseline_run_values) < MIN_BASELINE_RUNS or not baseline_pooled or not candidate_values:
        return MetricDrift(
            metric=metric,
            status="INSUFFICIENT-BASELINE",
            n_candidate=len(candidate_values),
            n_baseline=len(baseline_run_values),
        )

    candidate_mean = statistics.mean(candidate_values)
    baseline_mean = statistics.mean(baseline_pooled)
    baseline_stdev = statistics.stdev(baseline_pooled) if len(baseline_pooled) > 1 else 0.0
    delta = candidate_mean - baseline_mean
    worse = delta < 0
    drop = -delta if worse else 0.0

    method = "band"
    statistically_significant = worse
    if _SCIPY_AVAILABLE and len(candidate_values) >= 2 and len(baseline_pooled) >= 2:
        method = "welch"
        _tstat, pvalue = _scipy_stats.ttest_ind(candidate_values, baseline_pooled, equal_var=False)
        statistically_significant = worse and pvalue < 0.05
    elif baseline_stdev > 0:
        statistically_significant = worse and drop > 2.0 * baseline_stdev

    if worse and drop >= NOISE_FLOOR and statistically_significant:
        status = "DRIFT-REGRESSION"
    elif worse and drop > 0:
        status = "DRIFT-WARN"
    else:
        status = "OK"

    return MetricDrift(
        metric=metric,
        status=status,
        candidate_mean=round(candidate_mean, 4),
        baseline_mean=round(baseline_mean, 4),
        baseline_stdev=round(baseline_stdev, 4),
        delta=round(delta, 4),
        n_candidate=len(candidate_values),
        n_baseline=len(baseline_pooled),
        method=method,
    )


def drift_check(window: int = DEFAULT_WINDOW) -> dict:
    """Run the drift gate over the latest results for every (scenario,
    blue_model) pair seen. Returns {generated_at, window, pairs: [...]}.
    """
    from datetime import UTC, datetime

    runs = _load_purple_runs()
    pairs = sorted(_known_pairs(runs))
    pair_reports: list[PairDrift] = []

    for scenario, blue_model in pairs:
        matching_runs = [
            (ts, data)
            for ts, data in runs
            if any(_values_for_run(data, scenario, blue_model, m) for m in TRACKED_METRICS)
        ]
        if not matching_runs:
            continue
        candidate_ts, candidate_data = matching_runs[0]
        baseline_runs = matching_runs[1 : 1 + window]

        pd = PairDrift(scenario=scenario, blue_model=blue_model, candidate_ts=candidate_ts)
        for metric in TRACKED_METRICS:
            candidate_values = _values_for_run(candidate_data, scenario, blue_model, metric)
            baseline_run_values = [
                _values_for_run(data, scenario, blue_model, metric) for _ts, data in baseline_runs
            ]
            baseline_run_values = [v for v in baseline_run_values if v]
            pd.metrics.append(_metric_drift(metric, candidate_values, baseline_run_values))
        pair_reports.append(pd)

    return {
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "window": window,
        "pairs": [p.to_dict() for p in pair_reports],
    }


def render_drift_markdown(report: dict) -> str:
    lines = [
        f"# Drift Report — window={report['window']}",
        f"Generated: {report['generated_at']}",
        "",
    ]
    if not report["pairs"]:
        lines.append("(no purple-test series available)")
        return "\n".join(lines)
    lines.append(
        "| scenario | blue_model | metric | status | delta | baseline_mean | candidate_mean | n_baseline |"
    )
    lines.append("|---|---|---|---|---|---|---|---|")
    for pair in report["pairs"]:
        for m in pair["metrics"]:
            lines.append(
                f"| {pair['scenario']} | {pair['blue_model']} | {m['metric']} | {m['status']} | "
                f"{m['delta']} | {m['baseline_mean']} | {m['candidate_mean']} | {m['n_baseline']} |"
            )
    return "\n".join(lines)


# ── Phase 2: model-behavior canary ──────────────────────────────────────────────

CANARY_PROBES: list[dict[str, Any]] = [
    {
        "id": "kerberoast_mitre_id",
        "prompt": "Name the exact MITRE ATT&CK technique ID for Kerberoasting (requesting a service ticket for offline cracking). Respond with only the technique ID.",
        "expect_any": ["T1558.003", "T1558/003"],
    },
    {
        "id": "asreproast_mitre_id",
        "prompt": "Name the exact MITRE ATT&CK technique ID for AS-REP Roasting. Respond with only the technique ID.",
        "expect_any": ["T1558.004", "T1558/004"],
    },
    {
        "id": "golden_ticket_mitre_id",
        "prompt": "Name the exact MITRE ATT&CK technique ID for a Golden Ticket attack. Respond with only the technique ID.",
        "expect_any": ["T1558.001", "T1558/001"],
    },
    {
        "id": "pass_the_hash_mitre_id",
        "prompt": "Name the exact MITRE ATT&CK technique ID for Pass the Hash. Respond with only the technique ID.",
        "expect_any": ["T1550.002", "T1550/002"],
    },
    {
        "id": "log4shell_cve",
        "prompt": "What is the CVE ID for the Log4Shell remote code execution vulnerability in Apache Log4j?",
        "expect_any": ["CVE-2021-44228"],
    },
    {
        "id": "container_escape_mitre_id",
        "prompt": "Name the exact MITRE ATT&CK technique ID for Escape to Host (container escape). Respond with only the technique ID.",
        "expect_any": ["T1611"],
    },
    {
        "id": "llmnr_poisoning_mitre_id",
        "prompt": "Name the exact MITRE ATT&CK technique ID for LLMNR/NBT-NS Poisoning and SMB Relay. Respond with only the technique ID.",
        "expect_any": ["T1557.001", "T1557/001"],
    },
    {
        "id": "sqli_owasp_category",
        "prompt": "SQL injection falls under which OWASP Top 10 2021 category letter/number (e.g. A03)?",
        "expect_any": ["A03"],
    },
    {
        "id": "wmi_exec_mitre_id",
        "prompt": "Name the exact MITRE ATT&CK technique ID for Windows Management Instrumentation (as an execution technique). Respond with only the technique ID.",
        "expect_any": ["T1047"],
    },
    {
        "id": "nonblank_general",
        "prompt": "In one sentence, what does a port scanner do?",
        "expect_any": [],  # non-blank check only
    },
    {
        "id": "eternal_blue_cve",
        "prompt": "What is the CVE ID for the EternalBlue SMBv1 remote code execution vulnerability?",
        "expect_any": ["CVE-2017-0144"],
    },
    {
        "id": "ssrf_owasp_category",
        "prompt": "Server-Side Request Forgery (SSRF) falls under which OWASP Top 10 2021 category letter/number?",
        "expect_any": ["A10"],
    },
]


def _run_single_probe(model: str, probe: dict, ollama_url: str) -> dict:
    import httpx

    try:
        r = httpx.post(
            f"{ollama_url}/api/chat",
            json={
                "model": model,
                "messages": [{"role": "user", "content": probe["prompt"]}],
                "stream": False,
                "options": {"temperature": 0, "num_ctx": 8192},
            },
            timeout=90.0,
        )
        r.raise_for_status()
        content = r.json().get("message", {}).get("content", "") or ""
    except (httpx.HTTPError, ValueError) as e:
        return {"id": probe["id"], "ok": False, "response": f"[error: {e}]", "passed": False}

    non_blank = bool(content.strip())
    if probe["expect_any"]:
        passed = non_blank and any(exp in content for exp in probe["expect_any"])
    else:
        passed = non_blank

    return {"id": probe["id"], "ok": True, "response": content[:300], "passed": passed}


def run_canary_probe(model: str, *, ollama_url: str = "http://localhost:11434") -> dict:
    """Run the fixed canary probe suite against `model`. Cheap + deterministic
    (temperature=0) — this is a canary, not a full bench."""
    from datetime import UTC, datetime

    results = [_run_single_probe(model, probe, ollama_url) for probe in CANARY_PROBES]
    return {
        "model": model,
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "results": results,
        "pass_count": sum(1 for r in results if r["passed"]),
        "total": len(results),
    }


def _canary_baseline_path(model: str) -> Path:
    safe = model.replace("/", "_").replace(":", "_")
    return CANARY_DIR / f"{safe}.json"


def save_canary_baseline(model: str, *, ollama_url: str = "http://localhost:11434") -> dict:
    snapshot = run_canary_probe(model, ollama_url=ollama_url)
    _canary_baseline_path(model).write_text(json.dumps(snapshot, indent=2))
    return snapshot


def check_model_canary(model: str, *, ollama_url: str = "http://localhost:11434") -> dict:
    """Diff a fresh canary run vs the saved baseline for `model`.

    Returns {status: NO-BASELINE|NONE|LOW|MEDIUM|HIGH, flipped: [...], baseline_ts, candidate_ts}.
    This is what would have caught a silent quant/Ollama-version/template
    regression (e.g. the Ollama 0.31.1 GGUF slowdown noted in KNOWN_LIMITATIONS).
    """
    baseline_path = _canary_baseline_path(model)
    if not baseline_path.exists():
        return {"status": "NO-BASELINE", "flipped": [], "model": model}

    baseline = json.loads(baseline_path.read_text())
    candidate = run_canary_probe(model, ollama_url=ollama_url)

    baseline_by_id = {r["id"]: r for r in baseline["results"]}
    flipped = []
    for r in candidate["results"]:
        prior = baseline_by_id.get(r["id"])
        if prior is not None and prior["passed"] != r["passed"]:
            flipped.append(
                {"probe": r["id"], "was_passed": prior["passed"], "now_passed": r["passed"]}
            )

    n_flipped = len(flipped)
    if n_flipped == 0:
        status = "NONE"
    elif n_flipped <= 1:
        status = "LOW"
    elif n_flipped <= 3:
        status = "MEDIUM"
    else:
        status = "HIGH"

    return {
        "status": status,
        "flipped": flipped,
        "model": model,
        "baseline_ts": baseline.get("generated_at"),
        "candidate_ts": candidate.get("generated_at"),
        "pass_count": candidate["pass_count"],
        "total": candidate["total"],
    }
