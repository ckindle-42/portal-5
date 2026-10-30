"""Offline checks for the committed arm job specs (config/arm_jobs/).

The specs are the offline half of the Jarvis Local runs: they must parse under the runner's own
schema and name plan files that exist, or the first live run fails on a typo.
"""

from __future__ import annotations

from ipaddress import ip_address
from pathlib import Path
from urllib.parse import urlparse

import pytest
import yaml

from portal.modules.orchestration.jobs import REPORT_FIELDS, parse_job_spec

ROOT = Path(__file__).resolve().parents[2]
SPEC_DIR = ROOT / "config" / "arm_jobs"
SPECS = sorted(SPEC_DIR.glob("*.yaml"))

EXPECTED = {
    "mlx-cache-probe",
    "seat-vs-card-sampling-ab",
    "wfe-s5-s7",
    "wfe-s8-screens",
    "wfe-s10",
    "gemma-qat-vs-plain-ab",
    "spark-shadow-n20",
    "compliance-recapture",
    "bully-r0b-real-dryrun",
    "bully-r0b-ship",
    "wfe-fast-baseline",
    "wfe-realuse-rest",
    "wfe-realuse-autocoding-ab",
    "wfe-realuse-sec",
}

SHIP_ENV = (
    "LAB_SPLUNK_URL",
    "LAB_SPLUNK_USER",
    "LAB_SPLUNK_PASSWORD",
    "LAB_SPLUNK_INDEX",
    "LAB_SPLUNK_HEC_URL",
    "LAB_SPLUNK_HEC_TOKEN",
)


def _spec(path: Path):
    return parse_job_spec(yaml.safe_load(path.read_text(encoding="utf-8")), repo_root=ROOT)


def test_every_briefed_job_has_exactly_one_spec() -> None:
    assert {path.stem for path in SPECS} == EXPECTED
    assert len(SPECS) == len(EXPECTED)


@pytest.mark.parametrize("path", SPECS, ids=lambda path: path.stem)
def test_spec_parses_under_the_runner_schema(path: Path) -> None:
    spec = _spec(path)

    assert spec.job_id == path.stem
    assert spec.purpose.strip()
    assert spec.steps
    assert len({step.step_id for step in spec.steps}) == len(spec.steps)
    assert set(spec.report_fields) <= REPORT_FIELDS
    assert spec.preconditions.stack in {"up", "down"}
    assert spec.stop_conditions.max_job_minutes is not None
    for step in spec.steps:
        assert step.timeout_seconds > 0
        assert step.timeout_seconds <= spec.stop_conditions.max_job_minutes * 60
        assert isinstance(step.quiet_host, bool)


@pytest.mark.parametrize("path", SPECS, ids=lambda path: path.stem)
def test_repo_only_steps_run_without_a_quiet_host_and_campaign_steps_keep_it(path: Path) -> None:
    # Repo-only steps (report, plan regenerator, diagnostic council) need no quiet host;
    # everything that touches the stack keeps the window.
    repo_only = ("tests.wfe.report", "tests.wfe.sweep_plan", "tests.wfe.judge_council")
    # Lab-only steps post to / read from the lab Splunk, never the local stack.
    lab_only = {
        ("scripts/corpus_reingest.py", "--ship"),
        ("scripts/corpus_reingest.py", "--verify"),
    }
    for step in _spec(path).steps:
        is_repo_only = step.argv[:4] == ("uv", "run", "python", "-m") and step.argv[4] in repo_only
        is_repo_only = is_repo_only or tuple(step.argv[3:5]) in lab_only
        if is_repo_only:
            assert step.quiet_host is False, f"{path.stem}:{step.step_id}"
        else:
            assert step.quiet_host is True, f"{path.stem}:{step.step_id}"


@pytest.mark.parametrize("path", SPECS, ids=lambda path: path.stem)
def test_every_plan_a_step_opens_exists(path: Path) -> None:
    for step in _spec(path).steps:
        for index, token in enumerate(step.argv):
            if token == "--plan":
                assert (ROOT / step.argv[index + 1]).is_file(), step.argv[index + 1]


@pytest.mark.parametrize("name", ["wfe-realuse-rest", "wfe-realuse-sec"])
def test_every_realuse_campaign_step_is_gated_by_a_canary_that_stops_the_job(name: str) -> None:
    spec = _spec(SPEC_DIR / f"{name}.yaml")

    assert spec.stop_conditions.on_failure == "stop"
    for step in spec.steps:
        if step.argv[0] != "scripts/wfe_campaign.sh" or step.canary_of:
            continue
        gate = spec.steps[spec.steps.index(step) - 1]
        assert gate.canary_of == step.step_id, step.step_id
        assert gate.argv == (*step.argv, "--canary"), step.step_id


def test_the_cache_probe_runs_the_briefed_series() -> None:
    spec = _spec(SPEC_DIR / "mlx-cache-probe.yaml")
    services = [step.argv[4] for step in spec.steps]

    assert services == ["mlx-transcribe", "mlx-speech"]
    for step in spec.steps:
        assert step.argv[step.argv.index("--requests") + 1] == "20"
        assert step.argv[step.argv.index("--warm") + 1] == "2"


def test_wfe_campaign_specs_pipeline_the_seat_decisions() -> None:
    for name in ("seat-vs-card-sampling-ab", "wfe-s5-s7", "wfe-s8-screens", "wfe-s10"):
        spec = _spec(SPEC_DIR / f"{name}.yaml")
        campaign_steps = [step for step in spec.steps if step.argv[0] == "scripts/wfe_campaign.sh"]
        assert campaign_steps, name
        for step in campaign_steps:
            assert step.argv[step.argv.index("--engine") + 1] == "pipeline"
            assert "--tier" in step.argv


def test_the_spark_job_requires_twenty_comparisons() -> None:
    spec = _spec(SPEC_DIR / "spark-shadow-n20.yaml")
    argv = spec.steps[0].argv

    assert argv[argv.index("--minimum-compared") + 1] == "20"
    assert int(argv[argv.index("--repeat") + 1]) * 2 >= 20


def test_bully_r0b_ship_names_dotenv_keys_and_verifies_the_latest_report() -> None:
    spec = _spec(SPEC_DIR / "bully-r0b-ship.yaml")

    assert [step.step_id for step in spec.steps] == ["dry-run", "ship", "verify"]
    assert "--dry-run" in spec.steps[0].argv
    assert "--ship" in spec.steps[1].argv
    assert spec.steps[2].argv[-1] == "--verify"
    assert "--items" not in spec.steps[2].argv
    for step in spec.steps:
        assert step.env_from_dotenv == SHIP_ENV


def test_env_from_dotenv_rejects_keys_outside_the_allowlist() -> None:
    raw = yaml.safe_load((SPEC_DIR / "bully-r0b-ship.yaml").read_text(encoding="utf-8"))
    raw["steps"][0]["env_from_dotenv"] = ["NOT_A_REAL_SECRET"]

    with pytest.raises(ValueError, match="allowlist"):
        parse_job_spec(raw, repo_root=ROOT)


def test_realuse_rest_runs_the_three_groups_then_reports() -> None:
    spec = _spec(SPEC_DIR / "wfe-realuse-rest.yaml")
    campaigns = [
        step
        for step in spec.steps
        if step.argv[0] == "scripts/wfe_campaign.sh" and step.canary_of is None
    ]
    canaries = [step for step in spec.steps if step.canary_of is not None]
    reports = [step for step in spec.steps if step.argv[3:5] == ("-m", "tests.wfe.report")]

    assert [step.step_id for step in spec.steps] == [
        "reruns-canary",
        "reruns",
        "reruns-report",
        "reruns-judge-council",
        "documents-canary",
        "documents",
        "documents-report",
        "documents-judge-council",
        "decisions-canary",
        "decisions",
        "decisions-report",
        "decisions-judge-council",
    ]
    assert [step.argv[1] for step in campaigns] == [
        "realuse_reruns_20261030b",
        "realuse_documents_20261030b",
        "realuse_s5s7s10_20261030b",
    ]
    plans = (
        "tests/wfe/plans/realuse_v1_reruns.yaml",
        "tests/wfe/plans/realuse_v1_documents.yaml",
        "tests/wfe/plans/realuse_v1_s5s7s10.yaml",
    )
    for step, plan, campaign_id in zip(
        campaigns, plans, [s.argv[1] for s in campaigns], strict=True
    ):
        assert step.argv[step.argv.index("--plan") + 1] == plan
        assert step.argv[step.argv.index("--tier") + 1] == "realuse"
        assert step.argv[step.argv.index("--engine") + 1] == "pipeline"
        assert "--judge" in step.argv
        assert step.quiet_host is True
        assert campaign_id.startswith("realuse_")
    assert [step.canary_of for step in canaries] == [step.step_id for step in campaigns]
    for gate, campaign in zip(canaries, campaigns, strict=True):
        assert gate.argv == (*campaign.argv, "--canary")
        assert spec.steps.index(gate) < spec.steps.index(campaign)
        assert gate.quiet_host is True
    assert [step.argv[step.argv.index("--campaign") + 1] for step in reports] == [
        step.argv[1] for step in campaigns
    ]
    assert all(step.quiet_host is False for step in reports)
    councils = [step for step in spec.steps if step.argv[3:5] == ("-m", "tests.wfe.judge_council")]
    assert [step.argv[step.argv.index("--campaign") + 1] for step in councils] == [
        step.argv[1] for step in campaigns
    ]
    assert all(step.quiet_host is False for step in councils)
    for council, report in zip(councils, reports, strict=True):
        assert spec.steps.index(report) < spec.steps.index(council)
    for name in plans:
        data = yaml.safe_load((ROOT / name).read_text(encoding="utf-8"))
        for workspace, workload in data["workloads"].items():
            assert workload["home"] == "realuse_v1", f"{name}:{workspace}"


def test_realuse_security_runs_the_seat_plan_then_reports() -> None:
    spec = _spec(SPEC_DIR / "wfe-realuse-sec.yaml")
    campaign = next(
        step
        for step in spec.steps
        if step.canary_of is None and step.argv[0] == "scripts/wfe_campaign.sh"
    )
    report = next(step for step in spec.steps if step.argv[3:5] == ("-m", "tests.wfe.report"))

    assert [step.step_id for step in spec.steps] == [
        "security-canary",
        "security",
        "security-report",
        "security-judge-council",
    ]
    gate = spec.steps[0]
    assert gate.canary_of == campaign.step_id
    assert gate.argv == (*campaign.argv, "--canary")
    assert spec.steps.index(gate) < spec.steps.index(campaign)
    assert campaign.argv[1] == "realuse_sec_20261030b"
    assert campaign.argv[campaign.argv.index("--plan") + 1] == (
        "tests/wfe/plans/realuse_sec_v1_seats.yaml"
    )
    assert campaign.argv[campaign.argv.index("--tier") + 1] == "realuse"
    assert campaign.argv[campaign.argv.index("--engine") + 1] == "pipeline"
    assert "--judge" in campaign.argv
    assert campaign.quiet_host is True
    assert report.argv[report.argv.index("--campaign") + 1] == campaign.argv[1]
    assert report.quiet_host is False
    council = spec.steps[-1]
    assert council.argv[3:5] == ("-m", "tests.wfe.judge_council")
    assert council.argv[council.argv.index("--campaign") + 1] == campaign.argv[1]
    assert council.quiet_host is False
    assert spec.steps.index(report) < spec.steps.index(council)

    plan = yaml.safe_load((ROOT / campaign.argv[campaign.argv.index("--plan") + 1]).read_text())
    assert set(plan["workloads"]) == {
        "auto-security",
        "auto-security::blueteam",
        "auto-spl",
        "auto-compliance",
        "auto-compliance::reading",
    }
    for workload in plan["workloads"].values():
        assert workload["home"] == "realuse_sec_v1"

    judge = yaml.safe_load((ROOT / "tests/wfe/judge.yaml").read_text(encoding="utf-8"))
    judge_host = urlparse(judge["url"]).hostname
    assert judge_host is not None
    assert ip_address(judge_host).is_private


def test_the_recapture_backs_up_the_store_it_rewrites() -> None:
    spec = _spec(SPEC_DIR / "compliance-recapture.yaml")

    assert any(path.endswith("compliance_store.db") for path in spec.checkpoints)
    assert "--require-corpus" in spec.steps[0].argv
