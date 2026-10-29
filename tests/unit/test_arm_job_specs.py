"""Offline checks for the committed arm job specs (config/arm_jobs/).

The specs are the offline half of the Jarvis Local runs: they must parse under the runner's own
schema and name plan files that exist, or the first live run fails on a typo.
"""

from __future__ import annotations

from pathlib import Path

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
    "wfe-fast-baseline",
}


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
def test_report_steps_run_without_a_quiet_host_and_campaign_steps_keep_it(path: Path) -> None:
    for step in _spec(path).steps:
        is_report = step.argv[:4] == ("uv", "run", "python", "-m") and step.argv[4] == (
            "tests.wfe.report"
        )
        if is_report:
            assert step.quiet_host is False, f"{path.stem}:{step.step_id}"
        else:
            assert step.quiet_host is True, f"{path.stem}:{step.step_id}"


@pytest.mark.parametrize("path", SPECS, ids=lambda path: path.stem)
def test_every_plan_a_step_opens_exists(path: Path) -> None:
    for step in _spec(path).steps:
        for index, token in enumerate(step.argv):
            if token == "--plan":
                assert (ROOT / step.argv[index + 1]).is_file(), step.argv[index + 1]


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


def test_the_recapture_backs_up_the_store_it_rewrites() -> None:
    spec = _spec(SPEC_DIR / "compliance-recapture.yaml")

    assert any(path.endswith("compliance_store.db") for path in spec.checkpoints)
    assert "--require-corpus" in spec.steps[0].argv
