"""Offline checks for the campaign driver's job-facing flags.

`uv` and `curl` are replaced by shims on PATH that record their argv and environment, so
these run with no network, no Ollama and no campaign.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from tests.wfe import campaign

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "wfe_campaign.sh"

FAKE_UV = """\
#!/usr/bin/env bash
python3 - "$WFE_LOG" "$WFE_ENGINE" "$PLAN" "$@" <<'PY'
import json, sys
log, engine, plan, *argv = sys.argv[1:]
with open(log, "a") as handle:
    handle.write(json.dumps({"argv": argv, "engine": engine, "plan": plan}) + "\\n")
PY
for arg in "$@"; do
    [ "$arg" = "-c" ] && { echo "True"; exit 0; }
done
if [ -n "${WFE_NOTHING_MEASURED:-}" ]; then
    for arg in "$@"; do
        if [ "$arg" = "--finish" ]; then
            printf '%s\\n' "NOTHING MEASURED: ${WFE_NOTHING_MEASURED}"
            printf '%s\\n' "CAMPAIGN wfe_test: stopped (nothing measured: ${WFE_NOTHING_MEASURED}) rows 0/5"
            exit 10
        fi
    done
fi
if [ -n "${WFE_FINISH_RC:-}" ]; then
    for arg in "$@"; do
        if [ "$arg" = "--finish" ]; then
            printf '%s\\n' "${WFE_FINISH_LINE:-CAMPAIGN wfe_test: complete (all rows measured) rows 5/5}"
            exit "${WFE_FINISH_RC}"
        fi
    done
fi
exit 0
"""

FAKE_CURL = "#!/usr/bin/env bash\nexit 0\n"


def _run(
    tmp_path: Path,
    *args: str,
    env_extra: dict[str, str] | None = None,
    drop_env: tuple[str, ...] = (),
) -> tuple[subprocess.CompletedProcess[str], list[dict]]:
    bindir = tmp_path / "bin"
    bindir.mkdir(exist_ok=True)
    for name, body in (("uv", FAKE_UV), ("curl", FAKE_CURL)):
        path = bindir / name
        path.write_text(body)
        path.chmod(0o755)
    log = tmp_path / "calls.jsonl"
    arms = tmp_path / "arms.txt"
    arms.write_text("arm-a\n", encoding="utf-8")
    env = {
        **os.environ,
        "PATH": f"{bindir}{os.pathsep}{os.environ['PATH']}",
        "WFE_LOG": str(log),
        "LOG_DIR": str(tmp_path / "logs"),
        "PORTAL_DATA_ROOT": str(tmp_path / "data"),
        "ARMS_FILE": str(arms),
        "WFE_SKIP_CONFORMANCE": "1",
        "PIPELINE_API_KEY": "test-key",
        "REPEATS": "3",
    }
    if env_extra:
        env.update(env_extra)
    for key in drop_env:
        env.pop(key, None)
    env.pop("WFE_ENGINE", None)
    result = subprocess.run(
        ["bash", str(SCRIPT), "wfe_test", *args],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    calls = (
        [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines() if line.strip()]
        if log.is_file()
        else []
    )
    return result, calls


def test_wfe_campaign_has_valid_shell_syntax() -> None:
    result = subprocess.run(
        ["bash", "-n", str(SCRIPT)], cwd=ROOT, capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr


def test_plan_and_engine_flags_reach_every_campaign_call(tmp_path: Path) -> None:
    plan = "tests/wfe/plans/seat_card_sampling_ab_20261029.yaml"

    result, calls = _run(tmp_path, "--plan", plan, "--engine", "pipeline", "--tier", "screen")

    assert result.returncode == 0, result.stdout + result.stderr
    campaign_calls = [
        call
        for call in calls
        if "tests.wfe.campaign" in call["argv"] and "--append" in call["argv"]
    ]
    assert campaign_calls, calls
    for call in campaign_calls:
        argv = call["argv"]
        assert argv[argv.index("--plan") + 1] == plan
        assert call["engine"] == "pipeline"
        assert call["plan"] == plan
        assert "--engine" not in argv
        assert argv[-2:] == ["--tier", "screen"]
    arm_calls = [call for call in calls if "--arm" in call["argv"]]
    assert arm_calls and all(call["engine"] == "pipeline" for call in arm_calls)


def test_repeatable_flags_accept_the_equals_form(tmp_path: Path) -> None:
    plan = "tests/wfe/plans/gemma_qat_vs_plain_ab_20261029.yaml"

    result, calls = _run(tmp_path, f"--plan={plan}", "--engine=pipeline")

    assert result.returncode == 0, result.stdout + result.stderr
    campaign_calls = [
        call
        for call in calls
        if "tests.wfe.campaign" in call["argv"] and "--append" in call["argv"]
    ]
    assert campaign_calls
    assert all(call["engine"] == "pipeline" for call in campaign_calls)
    assert all(plan in call["argv"] for call in campaign_calls)


def test_a_flag_without_a_value_is_refused(tmp_path: Path) -> None:
    result, _calls = _run(tmp_path, "--plan")

    assert result.returncode == 2
    assert "--plan needs a path" in result.stderr


def test_without_the_flags_the_environment_is_unchanged(tmp_path: Path) -> None:
    result, calls = _run(tmp_path)

    assert result.returncode == 0, result.stdout + result.stderr
    assert calls
    assert all(not call["engine"] for call in calls)
    assert all(not call["plan"] for call in calls)
    assert all("--plan" not in call["argv"] for call in calls)


def _manifest(tmp_path: Path, rows: list[dict]) -> None:
    campaign_dir = tmp_path / "campaigns" / "s8"
    campaign_dir.mkdir(parents=True)
    (campaign_dir / "manifest.json").write_text(json.dumps({"rows": rows}), encoding="utf-8")


def test_all_blocked_exits_nonzero_and_names_the_dominant_reason(tmp_path, monkeypatch, capsys):
    stale = "deployed pipeline build 'abc' is not HEAD's portal/: rebuild first"
    _manifest(
        tmp_path,
        [
            {"state": "BLOCKED", "note": f"preflight REVIEW: {stale}"},
            {"state": "BLOCKED", "note": f"preflight REVIEW: {stale}"},
            {"state": "BLOCKED", "note": "preflight REVIEW: something else"},
            {"state": "PENDING"},
            {"state": "MISSING"},
        ],
    )
    monkeypatch.setattr(campaign, "CAMPAIGNS", tmp_path / "campaigns")
    monkeypatch.setattr(sys, "argv", ["campaign", "--campaign-id", "s8", "--require-measured"])

    assert campaign._cli() == campaign.EXIT_NOTHING_MEASURED == 10
    assert capsys.readouterr().out == f"NOTHING MEASURED: {stale}\n"


def test_a_measured_row_keeps_exit_zero(tmp_path, monkeypatch, capsys):
    _manifest(
        tmp_path,
        [
            {"state": "BLOCKED", "note": "preflight REVIEW: stale build"},
            {"state": "PASS"},
        ],
    )
    monkeypatch.setattr(campaign, "CAMPAIGNS", tmp_path / "campaigns")
    monkeypatch.setattr(sys, "argv", ["campaign", "--campaign-id", "s8", "--require-measured"])

    assert campaign._cli() == 0
    assert capsys.readouterr().out == ""


def test_dry_run_exits_zero_without_asking_whether_anything_was_measured(tmp_path: Path) -> None:
    result, calls = _run(tmp_path, "--dry-run", env_extra={"WFE_NOTHING_MEASURED": "stale build"})

    assert result.returncode == 0, result.stdout + result.stderr
    assert "NOTHING MEASURED:" not in result.stdout + result.stderr
    assert all("--require-measured" not in call["argv"] for call in calls)


def _campaign_calls(calls: list[dict]) -> list[dict]:
    return [
        call
        for call in calls
        if "tests.wfe.campaign" in call["argv"] and "--append" in call["argv"]
    ]


def test_realuse_tier_omits_repeats_when_repeats_is_unset(tmp_path: Path) -> None:
    plan = "tests/wfe/plans/realuse_v1_s8.yaml"

    result, calls = _run(
        tmp_path,
        "--plan",
        plan,
        "--tier",
        "realuse",
        "--engine",
        "pipeline",
        drop_env=("REPEATS",),
    )

    assert result.returncode == 0, result.stdout + result.stderr
    campaign_calls = _campaign_calls(calls)
    assert campaign_calls
    for call in campaign_calls:
        assert "--repeats" not in call["argv"]
        assert call["argv"][-2:] == ["--tier", "realuse"]


def test_an_explicit_repeats_still_reaches_a_realuse_tier(tmp_path: Path) -> None:
    result, calls = _run(
        tmp_path,
        "--plan",
        "tests/wfe/plans/realuse_v1_s8.yaml",
        "--tier",
        "realuse",
    )

    assert result.returncode == 0, result.stdout + result.stderr
    for call in _campaign_calls(calls):
        argv = call["argv"]
        assert argv[argv.index("--repeats") + 1] == "3"


def test_the_script_exits_with_the_nothing_measured_line(tmp_path: Path) -> None:
    reason = "deployed pipeline build 'stale' is not HEAD's portal/: rebuild first"

    result, calls = _run(tmp_path, env_extra={"WFE_NOTHING_MEASURED": reason})

    assert result.returncode == 10
    assert result.stdout.count(f"NOTHING MEASURED: {reason}") == 1
    assert (
        result.stdout.count(f"CAMPAIGN wfe_test: stopped (nothing measured: {reason}) rows 0/5")
        == 1
    )
    assert any("--finish" in call["argv"] for call in calls)


def test_the_scripts_last_line_is_the_campaign_verdict_and_its_exit_is_the_scripts(
    tmp_path: Path,
) -> None:
    line = "CAMPAIGN wfe_test: stopped (instrument drift in ['harness']) rows 3/68"

    result, calls = _run(tmp_path, env_extra={"WFE_FINISH_RC": "5", "WFE_FINISH_LINE": line})

    assert result.returncode == 5
    assert result.stdout.strip().splitlines()[-1] == line
    assert any("--finish" in call["argv"] for call in calls)
    assert not any("--require-measured" in call["argv"] for call in calls)
