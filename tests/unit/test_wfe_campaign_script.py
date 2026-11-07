"""Offline checks for the campaign driver's job-facing flags.

`uv` and `curl` are replaced by shims on PATH that record their argv and environment, so
these run with no network, no Ollama and no campaign.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest
import yaml

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
    if [ "$arg" = "--pilot-floor-check" ]; then
        if [ "${WFE_PILOT_NO_SIGNAL:-0}" = "1" ]; then
            echo "NO_SIGNAL all pilot arms below 25%: plain=1/8, qat=0/8"
            exit 0
        fi
        echo "PILOT_FLOOR CLEAR_OR_UNAVAILABLE"
        exit 7
    fi
done
for arg in "$@"; do
    [ "$arg" = "-c" ] && { echo "True"; exit 0; }
done
for arg in "$@"; do
    if [ "$arg" = "tests.wfe.realuse_paths" ] && [ -n "${WFE_FIXTURE_PREFLIGHT_RC:-}" ]; then
        echo "fixture preflight: FAIL unreadable: /workspace/uploads/realuse_v1/missing.txt" >&2
        exit "$WFE_FIXTURE_PREFLIGHT_RC"
    fi
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


def _run_real_interleaved_script(
    tmp_path: Path,
    campaign_id: str,
    monkeypatch: pytest.MonkeyPatch,
    *,
    pilot: bool = False,
    expired: bool = False,
    rehearse: bool = False,
    slow_setup: bool = False,
) -> tuple[subprocess.CompletedProcess[str], Path]:
    plan = yaml.safe_load(
        (ROOT / "tests/wfe/plans/gemma26b_qat_vision_fallbacks_20261106.yaml").read_text(
            encoding="utf-8"
        )
    )
    plan["repeats"] = 1
    plan["interleave_block"] = 4
    if rehearse:
        plan["rehearsal_max_phase_s"] = 0.1 if slow_setup else 120
        plan["rehearsal_max_overhead"] = 0.6
    workload = next(iter(plan["workloads"].values()))
    suite_path = ROOT / "tests/wfe/suites" / f"{workload['home']}.jsonl"
    task_ids = [
        json.loads(line)["id"]
        for line in suite_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ][:2]
    assert len(task_ids) == 2
    workload["home_tasks"] = task_ids
    plan_path = tmp_path / "two-task-interleaved-plan.yaml"
    plan_path.write_text(yaml.safe_dump(plan), encoding="utf-8")
    matrix = campaign.expand_matrix(plan_path, 1, tier="realuse")
    pilot_tasks = 2 if rehearse else 8 if pilot else None
    if pilot_tasks:
        matrix = campaign.pilot_matrix(matrix, pilot_tasks)
    arms = list(dict.fromkeys(row["arm"] for row in matrix))
    assert len(arms) == 2
    campaign_root = tmp_path / "data" / "tests" / "wfe" / "results" / "campaigns"
    for name, value in (
        ("CAMPAIGNS", campaign_root),
        (
            "instrument_fingerprint",
            lambda: {"fingerprint": "test-instrument", "engine": "pipeline"},
        ),
        (
            "env_fingerprint",
            lambda _base: {"fingerprint": "test-environment", "engine": "pipeline"},
        ),
        ("config_dirty", lambda: []),
        ("gate_controls", lambda *_args: {}),
        ("_engine_swap_profiles", lambda: {}),
        ("_row_wall_history", lambda _matrix: {}),
    ):
        monkeypatch.setattr(campaign, name, value)
    effective_id = campaign._effective_campaign_id(campaign_id, pilot_tasks, rehearsal=rehearse)
    execution = campaign.execution_options(plan_path, matrix, pilot_tasks, rehearsal=rehearse)
    campaign.open_campaign(effective_id, plan_path, matrix, append=False, execution=execution)
    arms_path = tmp_path / "arms.txt"
    arms_path.write_text("\n".join(arms) + "\n", encoding="utf-8")

    bindir = tmp_path / "bin"
    bindir.mkdir()
    real_python = Path(sys.executable)
    python = bindir / "python"
    python.write_text(
        "#!/usr/bin/env bash\n"
        'if [ "$1" = "-m" ] && [ "$2" = "tests.wfe.campaign" ]; then\n'
        "  shift 2\n"
        '  case " $* " in\n'
        '    *" --pilot-floor-check "*) exec "$WFE_TEST_REAL_PYTHON" -c \'import sys; import tests.wfe.campaign as c; sys.argv=["tests.wfe.campaign",*sys.argv[1:]]; raise SystemExit(c._cli())\' "$@" ;;\n'
        '    *" --dry-run "*) echo "matrix rows: 4 arms: 2 repeats: 1"; exit 0 ;;\n'
        '    *" --status "*) exit 0 ;;\n'
        '    *" --finish "*) if [ -n "$WFE_TEST_PHASES" ]; then exec "$WFE_TEST_REAL_PYTHON" -c \'import sys; import tests.wfe.campaign as c; sys.argv=["tests.wfe.campaign",*sys.argv[1:]]; raise SystemExit(c._cli())\' "$@"; fi; exec "$WFE_TEST_REAL_PYTHON" -c \'import json,os,sys; p=os.path.join(os.environ["PORTAL_DATA_ROOT"],"tests/wfe/results/campaigns",os.environ["WFE_TEST_CAMPAIGN_ID"],"manifest.json"); m=json.load(open(p)); print("CAMPAIGN",os.environ["WFE_TEST_CAMPAIGN_ID"],"stopped" if m.get("campaign_stop") else "complete"); raise SystemExit(5 if m.get("campaign_stop") else 0)\' ;;\n'
        "  esac\n"
        '  exec "$WFE_TEST_REAL_PYTHON" -c \'import os,sys; import tests.wfe.campaign as c; '
        "from wfe_campaign_test_support import patch_campaign; patch_campaign(c); "
        'sys.executable=os.environ["WFE_TEST_PYTHON"]; '
        'sys.argv=["tests.wfe.campaign",*sys.argv[1:]]; raise SystemExit(c.main())\' "$@"\n'
        "fi\n"
        'if [ "$1" = "-m" ] && [ "$2" = "tests.wfe.realuse_paths" ]; then\n'
        '  echo "fixture preflight: PASS (test transport)"; exit 0\n'
        "fi\n"
        'if [ "$1" = "-c" ] && [[ "$2" == *archive_drifted_campaign* ]]; then exit 0; fi\n'
        'if [ "$1" = "-c" ] && [[ "$2" == *"load_manifest"* ]]; then\n'
        "  shift 2\n"
        '  exec "$WFE_TEST_REAL_PYTHON" -c \'import json,os,sys; p=os.path.join(os.environ["PORTAL_DATA_ROOT"],"tests/wfe/results/campaigns",sys.argv[1],"manifest.json"); print(json.load(open(p))["execution"]["arm_order"])\' "$@"\n'
        "fi\n"
        'exec "$WFE_TEST_REAL_PYTHON" "$@"\n',
        encoding="utf-8",
    )
    python.chmod(0o755)
    uv = bindir / "uv"
    uv.write_text('#!/usr/bin/env bash\n[ "$1" = run ] && shift\nexec "$@"\n', encoding="utf-8")
    uv.chmod(0o755)
    support = tmp_path / "wfe_campaign_test_support.py"
    support.write_text(
        "import json, os\n"
        "from pathlib import Path\n"
        "\n"
        "def patch_campaign(campaign):\n"
        "    campaign._engine_swap_profiles = lambda: {}\n"
        "    campaign._row_wall_history = lambda _matrix: {}\n"
        '    campaign._load_guard_plan = lambda _models: {"guard_enabled": False, "fits": False, "busy": False}\n'
        '    campaign.instrument_fingerprint = lambda: {"fingerprint": "test-instrument", "engine": "pipeline"}\n'
        '    campaign.env_fingerprint = lambda _base: {"fingerprint": "test-environment", "engine": "pipeline"}\n'
        "    campaign.config_dirty = lambda: []\n"
        "    campaign.gate_controls = lambda *_args: {}\n"
        "    campaign.instrument_drift = lambda _manifest: None\n"
        "    campaign._ready = lambda _directory: True\n"
        "    campaign.ollama_reachable = lambda: True\n"
        "    campaign.gate_execution = lambda _directory: None\n"
        "    campaign._warn_prompt_surface = lambda _matrix: None\n"
        "    campaign._realuse_tool_preflight = lambda _plan: None\n"
        '    campaign._arm_preflight = lambda *_args: {"verdict": "OK", "findings": [], "identities": {}}\n'
        "    campaign._evaluate_interleaved = lambda *_args: (0, False)\n"
        '    if os.environ.get("WFE_TEST_PHASES"):\n'
        "        import time\n"
        "        campaign.drain_model = lambda _model: True\n"
        "        campaign.workspace_context = lambda *_args, **_kwargs: {}\n"
        "        campaign._prepare_arm_resources = lambda _directory, _arm, todo, _resident=None: (campaign.row_model(todo[0]), False)\n"
        "        def run_row(*_args, **_kwargs):\n"
        "            time.sleep(0.5)\n"
        '            return {"outcome": "PASS", "turns": 1, "tool_calls": 1, "tool_errors": 0, "economics": {"wall_s": 0.5}}\n'
        "        campaign.run_row = run_row\n"
        "        campaign.arm_stop_reason = lambda *_args, **_kwargs: None\n"
        "        campaign._halt_arm = lambda *_args, **_kwargs: None\n"
        "        campaign._curtail_after_task = lambda *_args, **_kwargs: None\n"
        '        if os.environ.get("WFE_TEST_SETUP_DELAY"):\n'
        "            arm_todo = campaign._arm_todo\n"
        "            def delayed_arm_todo(*args, **kwargs):\n"
        '                time.sleep(float(os.environ["WFE_TEST_SETUP_DELAY"]))\n'
        "                return arm_todo(*args, **kwargs)\n"
        "            campaign._arm_todo = delayed_arm_todo\n"
        "        return\n"
        "    def execute_arm(directory, arm, *args, only_run_ids=None, **kwargs):\n"
        "        manifest = campaign.load_manifest(directory)\n"
        "        selected = set(only_run_ids or ())\n"
        "        done = []\n"
        '        for row in manifest["rows"]:\n'
        '            if row.get("arm") != arm or (selected and row["run_id"] not in selected):\n'
        "                continue\n"
        '            row["state"] = "PASS"\n'
        '            result = {key: row.get(key) for key in ("run_id", "workspace", "suite", "task_id", "repeat")}\n'
        '            result.update(outcome="PASS", economics={"wall_s": 0.01})\n'
        '            campaign._row_path(directory, row["run_id"]).write_text(json.dumps(result))\n'
        "            done.append(row)\n"
        "        campaign.save_manifest(directory, manifest)\n"
        '        with open(os.environ["WFE_TEST_RUNS"], "a", encoding="utf-8") as log:\n'
        '            log.write(arm + "\\n")\n'
        '        return {"arm": arm, "ran": len(done), "tally": {"PASS": len(done)}}\n'
        "    campaign.execute_arm = execute_arm\n",
        encoding="utf-8",
    )
    run_log = tmp_path / "arms-ran.txt"
    env = {
        **os.environ,
        "PATH": f"{bindir}{os.pathsep}{os.environ['PATH']}",
        "PYTHONPATH": f"{tmp_path}{os.pathsep}{os.environ.get('PYTHONPATH', '')}",
        "WFE_TEST_REAL_PYTHON": str(real_python),
        "WFE_TEST_PYTHON": str(python),
        "WFE_TEST_RUNS": str(run_log),
        "WFE_TEST_CAMPAIGN_ID": str(effective_id),
        "ARMS_FILE": str(arms_path),
        "PORTAL_DATA_ROOT": str(tmp_path / "data"),
        "LOG_DIR": str(tmp_path / "logs"),
        "DEBUG_DIR": str(tmp_path / "debug"),
        "WFE_ENGINE": "pipeline",
        "WFE_SKIP_CONFORMANCE": "1",
        "WFE_ALLOW_DIRTY_INSTRUMENT": "1",
        "WFE_OMLX_URL": "file:///no-omlx-in-test",
        "WFE_DRAIN_TIMEOUT_S": "1",
        "WFE_DRAIN_POLL_S": "0.01",
        "PIPELINE_API_KEY": "test-key",
        "OLLAMA": "file:///no-ollama-in-test",
        "OLLAMA_URL": "file:///no-ollama-in-test",
    }
    env.update(
        {
            **({"WFE_TEST_PHASES": "1"} if rehearse else {}),
            **({"WFE_TEST_SETUP_DELAY": "0.2"} if slow_setup else {}),
        }
    )
    argv = [
        "bash",
        str(SCRIPT),
        campaign_id,
        "--plan",
        str(plan_path),
        "--tier",
        "realuse",
        "--engine",
        "pipeline",
    ]
    if pilot:
        argv.extend(("--pilot", "8"))
    if rehearse:
        argv.append("--rehearse")
    if expired:
        env["WFE_CAMPAIGN_START_EPOCH"] = "1"
    result = subprocess.run(
        argv,
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=5 if rehearse else 120,
    )
    return result, run_log


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


def test_confirm_tier_omits_repeats_when_repeats_is_unset(tmp_path: Path) -> None:
    plan = "tests/wfe/plans/gemma26b_qat_bench_20261106.yaml"

    result, calls = _run(tmp_path, "--plan", plan, "--tier", "confirm", drop_env=("REPEATS",))

    assert result.returncode == 0, result.stdout + result.stderr
    campaign_calls = _campaign_calls(calls)
    assert campaign_calls
    for call in campaign_calls:
        assert "--repeats" not in call["argv"]
        assert call["argv"][-2:] == ["--tier", "confirm"]


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


def test_fixture_preflight_runs_before_rows(tmp_path: Path) -> None:
    plan = "tests/wfe/plans/realuse_v1_s8.yaml"

    result, calls = _run(tmp_path, "--plan", plan, "--tier", "realuse")

    assert result.returncode == 0, result.stdout + result.stderr
    indexes = [i for i, call in enumerate(calls) if "tests.wfe.realuse_paths" in call["argv"]]
    assert indexes, calls
    preflight = calls[indexes[0]]["argv"]
    assert preflight[preflight.index("--plan") + 1] == plan
    assert "--preflight" in preflight
    arm_at = next(i for i, call in enumerate(calls) if "--arm" in call["argv"])
    assert indexes[0] < arm_at


def test_fixture_preflight_refusal_stops_the_campaign(tmp_path: Path) -> None:
    result, calls = _run(
        tmp_path,
        "--plan",
        "tests/wfe/plans/realuse_v1_s8.yaml",
        "--tier",
        "realuse",
        env_extra={"WFE_FIXTURE_PREFLIGHT_RC": "1"},
    )

    assert result.returncode == 4
    text = result.stdout + result.stderr
    assert "ABORT: realuse fixture preflight refused" in text
    assert "unreadable:" in text
    assert not any("--arm" in call["argv"] for call in calls)


def test_a_drifted_campaign_is_archived_aside_before_the_append(tmp_path: Path) -> None:
    result, calls = _run(tmp_path)

    assert result.returncode == 0, result.stdout + result.stderr
    archive_at = next(
        (i for i, call in enumerate(calls) if "archive_drifted_campaign" in " ".join(call["argv"])),
        None,
    )
    append_at = next(
        i for i, call in enumerate(calls) if call["argv"][-2:] == ["--append", "--status"]
    )
    assert archive_at is not None, calls
    assert archive_at < append_at
    assert "wfe_test" in " ".join(calls[archive_at]["argv"])


def test_pilot_uses_a_separate_campaign_id_and_reaches_campaign_commands(tmp_path: Path) -> None:
    result, calls = _run(tmp_path, "--pilot=2")

    assert result.returncode == 0, result.stdout + result.stderr
    campaign_calls = [call["argv"] for call in calls if "--campaign-id" in call["argv"]]
    assert campaign_calls
    assert all(argv[argv.index("--campaign-id") + 1] == "wfe_test_pilot" for argv in campaign_calls)
    assert all(argv[argv.index("--pilot") + 1] == "2" for argv in campaign_calls)


def test_rehearse_refuses_canary(tmp_path: Path) -> None:
    result, _calls = _run(tmp_path, "--rehearse", "--canary")

    assert result.returncode == 2
    assert "cannot be combined with --canary" in result.stderr


def test_rehearse_passes_two_task_and_rehearse_flags_to_campaign_calls(tmp_path: Path) -> None:
    result, calls = _run(tmp_path, "--rehearse")

    assert result.returncode == 0, result.stdout + result.stderr
    calls = [call["argv"] for call in calls if "tests.wfe.campaign" in call["argv"]]
    assert calls
    assert all(argv[argv.index("--campaign-id") + 1] == "wfe_test_rehearsal" for argv in calls)
    assert all(argv[argv.index("--pilot") + 1] == "2" for argv in calls)
    assert all("--rehearse" in argv for argv in calls if "--append" in argv or "--finish" in argv)


def test_sprint_refuses_a_no_signal_pilot_without_override(tmp_path: Path) -> None:
    result, calls = _run(tmp_path, env_extra={"WFE_PILOT_NO_SIGNAL": "1"})

    assert result.returncode == 4
    assert "refusing sprint after below-floor pilot" in result.stderr
    assert any("--pilot-floor-check" in call["argv"] for call in calls)
    assert not any("--append" in call["argv"] for call in calls)


def test_sprint_can_override_a_no_signal_pilot(tmp_path: Path) -> None:
    result, calls = _run(tmp_path, "--allow-below-floor", env_extra={"WFE_PILOT_NO_SIGNAL": "1"})

    assert result.returncode == 0, result.stdout + result.stderr
    assert not any("--pilot-floor-check" in call["argv"] for call in calls)


@pytest.mark.parametrize(
    ("pilot", "expired"),
    [(False, False), (True, False), (True, True)],
    ids=("full-interleaved", "pilot-interleaved", "pilot-time-cap"),
)
def test_real_campaign_script_runs_interleaved_workers_without_a_live_stack(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, pilot: bool, expired: bool
) -> None:
    campaign_id = f"wfe_r3_{int(pilot)}_{int(expired)}"
    result, run_log = _run_real_interleaved_script(
        tmp_path, campaign_id, monkeypatch, pilot=pilot, expired=expired
    )
    effective_id = campaign_id + ("_pilot" if pilot else "")
    manifest_path = (
        tmp_path
        / "data"
        / "tests"
        / "wfe"
        / "results"
        / "campaigns"
        / effective_id
        / "manifest.json"
    )
    assert manifest_path.is_file(), result.stdout + result.stderr
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    output = result.stdout + result.stderr

    if expired:
        assert result.returncode == campaign.EXIT_STOPPED, output
        assert manifest["campaign_stop"]["reason"] == "time cap"
        assert len(manifest["rows"]) == 4
        assert not run_log.exists()
        return

    assert result.returncode == 0, output
    rows = manifest["rows"]
    arms = {row["arm"] for row in rows}
    assert len(arms) == 2
    assert len(rows) == 4
    assert len({row["task_id"] for row in rows}) == 2
    roles = {row["arm"]: row["arm_role"] for row in rows}
    assert manifest["execution"]["arm_order"] == "interleaved"
    assert run_log.read_text(encoding="utf-8").splitlines() == sorted(
        arms, key=lambda arm: (roles[arm] != "incumbent", arm)
    )
    assert all(row["state"] == "PASS" for row in rows)
    if pilot:
        assert effective_id.endswith("_pilot") and not effective_id.endswith("_pilot_pilot")
        assert {arm: sum(row["arm"] == arm for row in rows) for arm in arms} == dict.fromkeys(
            arms, 2
        )
    assert "--pilot requires at least two arms" not in output


@pytest.mark.parametrize("slow_setup", [False, True], ids=("pass", "slow-setup-fails"))
def test_rehearsal_runs_two_blocks_and_gates_phase_timing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, slow_setup: bool
) -> None:
    started = time.monotonic()
    campaign_id = f"wfe_rehearsal_{int(slow_setup)}"
    result, _run_log = _run_real_interleaved_script(
        tmp_path, campaign_id, monkeypatch, rehearse=True, slow_setup=slow_setup
    )
    elapsed = time.monotonic() - started
    effective_id = f"{campaign_id}_rehearsal"
    campaign_dir = tmp_path / "data" / "tests" / "wfe" / "results" / "campaigns" / effective_id
    manifest = json.loads((campaign_dir / "manifest.json").read_text(encoding="utf-8"))
    output = result.stdout + result.stderr

    assert elapsed < 5
    assert "OVERHEAD harness_s=" in output
    assert "PHASE TABLE block arm block_setup_s model_prepare_s rows_s release_s" in output
    timing = manifest["execution"]["timing"]
    assert len(timing["blocks"]) == 4
    assert {row["arm"] for row in timing["blocks"]} == {row["arm"] for row in manifest["rows"]}
    assert all("harness_s" in row and "model_s" in row for row in timing["blocks"])
    interleaved_log = (tmp_path / "logs" / "interleaved.log").read_text()
    assert all(f"PHASE {phase} arm=" in interleaved_log for phase in campaign._TIMING_PHASES)
    if slow_setup:
        assert result.returncode == campaign.EXIT_REHEARSAL_FAILED
        assert "block_setup arm=" in output and "> 0.100" in output
    else:
        assert result.returncode == 0, output


@pytest.mark.parametrize("parent_gap", [0.0, 0.2], ids=("no-gap", "unattributed-gap-fails"))
def test_rehearsal_wall_gate_counts_parent_gap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys, parent_gap: float
) -> None:
    started = time.monotonic()
    campaign_dir = tmp_path / "parent-gap-campaign"
    campaign_dir.mkdir()
    rows = [
        {"run_id": f"{arm}:t{index}", "arm": arm, "arm_role": "incumbent", "state": "PENDING"}
        for arm in ("plain", "qat")
        for index in range(2)
    ]
    execution = {
        "rehearsal": True,
        "rehearsal_max_overhead": 0.25,
        "rehearsal_max_phase_s": 0.1,
        "timing": {"blocks": []},
    }
    campaign.save_manifest(campaign_dir, {"execution": execution, "rows": rows})
    blocks = [
        [{"run_ids": {"plain": ["plain:t0"], "qat": ["qat:t0"]}}],
        [{"run_ids": {"plain": ["plain:t1"], "qat": ["qat:t1"]}}],
    ]
    block_calls = 0

    def next_block(*_args, **_kwargs):
        nonlocal block_calls
        block_calls += 1
        if block_calls == 2 and parent_gap:
            time.sleep(parent_gap)
        return [blocks[block_calls - 1]] if block_calls <= len(blocks) else []

    def run_block(directory, block, arms, _args, _budget):
        block_id = campaign._interleaved_block_id(block)
        for arm in arms:
            row_started = time.monotonic()
            time.sleep(0.1)
            campaign._record_block_timing(
                directory,
                arm,
                block_id,
                {"block_setup": 0.0, "model_prepare": 0.0, "rows": 0.1, "release": 0.0},
                0.1,
                row_started,
            )
        manifest = campaign.load_manifest(directory)
        run_ids = {run_id for unit in block for ids in unit["run_ids"].values() for run_id in ids}
        for row in manifest["rows"]:
            if row["run_id"] in run_ids:
                row["state"] = "PASS"
        campaign.save_manifest(directory, manifest)
        return [{"arm": arm, "ran": 1} for arm in arms]

    monkeypatch.setattr(campaign, "_interleave_blocks", next_block)
    monkeypatch.setattr(campaign, "_run_interleaved_block", run_block)
    args = type("Args", (), {"no_curtail": False, "rerun_failed": False, "budget_s": 10})()
    campaign._run_interleaved_campaign(
        campaign_dir,
        ["plain", "qat"],
        args,
        {"interleave_block": 1, "pilot_tasks": 2},
        time.time() + 60,
    )
    manifest = campaign.load_manifest(campaign_dir)
    result = campaign.campaign_finish(campaign_dir, "parent-gap")
    elapsed = time.monotonic() - started
    timing = manifest["execution"]["timing"]
    output = capsys.readouterr().out
    gaps = {row["block_id"]: row["gap_before_s"] for row in timing["blocks"]}

    assert elapsed < 5
    assert len(gaps) == 2
    assert "unattributed_s=" in output
    assert timing["harness_s"] + timing["model_s"] == pytest.approx(timing["wall_s"], abs=0.002)
    if parent_gap:
        assert result == campaign.EXIT_REHEARSAL_FAILED, f"{timing=} {output=}"
        assert max(gaps.values()) > parent_gap
        assert "unattributed_s=" in output and "> 0.100" in output
    else:
        assert result == 0
        assert max(gaps.values()) < 0.1


def _pilot_manifest(plain_passes: int, qat_passes: int) -> dict:
    rows = [
        {"arm": arm, "state": "PASS" if index < passes else "FAIL"}
        for arm, passes in (("plain", plain_passes), ("qat", qat_passes))
        for index in range(8)
    ]
    return {
        "execution": {"pilot_tasks": 8},
        "rows": rows,
    }


def test_pilot_floor_stops_when_all_arms_are_below_the_floor(tmp_path: Path, capsys) -> None:
    manifest = _pilot_manifest(1, 0)
    (tmp_path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    result = campaign.campaign_finish(tmp_path, "pilot")

    output = capsys.readouterr().out
    assert result == 0
    assert "CAMPAIGN pilot: NO_SIGNAL (all arms below floor 25%: plain=1/8, qat=0/8)" in output


def test_pilot_floor_keeps_normal_verdict_when_one_arm_is_above_floor(
    tmp_path: Path, capsys
) -> None:
    manifest = _pilot_manifest(6, 5)
    (tmp_path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    result = campaign.campaign_finish(tmp_path, "vision")

    output = capsys.readouterr().out
    assert result == 0
    assert "CAMPAIGN vision: complete" in output
    assert "NO_SIGNAL" not in output


def test_plan_validates_pilot_floor_rate_and_rehearsal_limits(tmp_path: Path) -> None:
    plan = tmp_path / "plan.yaml"
    plan.write_text(
        "pilot_floor_rate: 0.2\nrehearsal_max_overhead: 0.3\nrehearsal_max_phase_s: 1.5\n"
    )
    options = campaign.execution_options(plan, [{"arm": "inc"}, {"arm": "cand"}])
    assert options["pilot_floor_rate"] == 0.2
    assert options["rehearsal_max_overhead"] == 0.3
    assert options["rehearsal_max_phase_s"] == 1.5

    for value in (0, 1, True, "0.2"):
        plan.write_text(f"pilot_floor_rate: {value!r}\n")
        with pytest.raises(ValueError, match="pilot_floor_rate"):
            campaign.execution_options(plan, [{"arm": "inc"}, {"arm": "cand"}])


def test_execution_options_default_to_interleaved_for_ab_and_keep_sequential_opt_in(
    tmp_path: Path,
) -> None:
    plan = tmp_path / "plan.yaml"
    matrix = [{"arm": "inc"}, {"arm": "cand"}]
    plan.write_text("max_minutes: 25\n")

    options = campaign.execution_options(plan, matrix)

    assert options["arm_order"] == "interleaved"
    assert options["interleave_block"] == 4
    assert options["max_minutes"] == 25
    plan.write_text("arm_order: sequential\n")
    sequential = campaign.execution_options(plan, matrix)
    assert sequential["arm_order"] == "sequential" and sequential["max_minutes"] == 120
    manifest = {
        "rows": [
            {"arm": "cand", "arm_role": "challenger"},
            {"arm": "inc", "arm_role": "incumbent"},
        ]
    }
    assert campaign._select_arms(manifest, None) == ["inc", "cand"]


def test_interleave_block_uses_swap_median_and_workspace_row_history(monkeypatch) -> None:
    matrix = [
        {"workspace": workspace, "arm": arm}
        for workspace in ("slow", "fast")
        for arm in ("inc", "cand")
    ]
    monkeypatch.setattr(
        campaign,
        "_models_by_workspace",
        lambda _matrix: {
            workspace: [{"engine": "omlx", "model": arm} for arm in ("inc", "cand")]
            for workspace in ("slow", "fast")
        },
    )
    profile = {"swap_median_s": 20.0, "swap_p95_s": 27.0}

    blocks, reasons, _models = campaign._choose_interleave_blocks(
        matrix,
        None,
        {"slow": {"median_s": 80.0, "n": 12}, "fast": {"median_s": 10.0, "n": 8}},
        {"omlx": profile},
    )

    assert blocks == {"fast": 20, "slow": 3}
    assert "p95=27.0s" in reasons["slow"]
    assert "row median=80.0s n=12" in reasons["slow"]


def test_row_wall_history_matches_planned_workspace_suite_and_tasks(
    tmp_path: Path, monkeypatch
) -> None:
    campaign_dir = tmp_path / "old" / "rows"
    campaign_dir.mkdir(parents=True)
    for name, row in (
        ("a", {"workspace": "ws", "suite": "s", "task_id": "t1", "economics": {"wall_s": 2}}),
        ("b", {"workspace": "ws", "suite": "s", "task_id": "t1", "economics": {"wall_s": 6}}),
        ("c", {"workspace": "ws", "suite": "s", "task_id": "other", "economics": {"wall_s": 100}}),
    ):
        (campaign_dir / f"{name}.json").write_text(json.dumps(row), encoding="utf-8")
    monkeypatch.setattr(campaign, "CAMPAIGNS", tmp_path)

    history = campaign._row_wall_history(
        [{"workspace": "ws", "suite": "s", "task_id": "t1", "arm": "inc"}]
    )

    assert history == {"ws": {"n": 2, "median_s": 4.0}}


def test_interleave_block_uses_fallback_or_explicit_plan_override(monkeypatch) -> None:
    matrix = [{"workspace": "ws", "arm": arm} for arm in ("inc", "cand")]
    monkeypatch.setattr(
        campaign,
        "_models_by_workspace",
        lambda _matrix: {"ws": [{"engine": "ollama", "model": arm} for arm in ("i", "c")]},
    )

    fallback, fallback_reasons, _ = campaign._choose_interleave_blocks(
        matrix, None, {}, {"ollama": {"swap_median_s": 11.0, "swap_p95_s": 16.0}}
    )
    override, override_reasons, _ = campaign._choose_interleave_blocks(
        matrix,
        7,
        {"ws": {"median_s": 80.0, "n": 4}},
        {"ollama": {"swap_median_s": 11.0, "swap_p95_s": 16.0}},
    )

    assert fallback == {"ws": 4}
    assert "history or engine swap timing unavailable" in fallback_reasons["ws"]
    assert override == {"ws": 7}
    assert override_reasons["ws"] == "plan override interleave_block=7"


def test_omlx_swap_profile_pairs_load_and_unload_spans(tmp_path: Path) -> None:
    log = tmp_path / "omlx.log"
    log.write_text(
        "2026-11-06 12:00:00,000 - omlx.engine_pool - INFO - Loading model: m\n"
        "2026-11-06 12:00:10.000 - omlx.engine_pool - INFO - Loaded model: m (actual: 1GB)\n"
        "2026-11-06 12:00:11.000 - omlx.engine_pool - INFO - Unloading model: m (immediate abort)\n"
        "2026-11-06 12:00:12.000 - omlx.engine_pool - INFO - Unloaded model: m, freed=1GB\n"
        "2026-11-06 12:01:00.000 - omlx.engine_pool - INFO - Loading model: m\n"
        "2026-11-06 12:01:20.000 - omlx.engine_pool - INFO - Loaded model: m (actual: 1GB)\n"
        "2026-11-06 12:01:21.000 - omlx.engine_pool - INFO - Unloading model: m (immediate abort)\n"
        "2026-11-06 12:01:23.000 - omlx.engine_pool - INFO - Unloaded model: m, freed=1GB\n",
        encoding="utf-8",
    )

    profile = campaign._omlx_swap_profile(log)

    assert profile["load"] == {"n": 2, "median_s": 15.0, "p95_s": 20.0}
    assert profile["unload"] == {"n": 2, "median_s": 1.5, "p95_s": 2.0}
    assert profile["swap_median_s"] == 16.5
    assert profile["swap_p95_s"] == 22.0


def test_ollama_swap_profile_uses_one_startup_span_per_load(tmp_path: Path) -> None:
    log = tmp_path / "ollama.log"
    log.write_text(
        'time=2026-11-06T12:00:00.000-06:00 msg="loading model via llama-server" model=m\n'
        'time=2026-11-06T12:00:12.000-06:00 msg="llama-server started in 12 seconds"\n'
        'time=2026-11-06T12:00:12.001-06:00 msg="llama-server started in 12.01 seconds"\n'
        'time=2026-11-06T12:01:00.000-06:00 msg="loading model via llama-server" model=m\n'
        'time=2026-11-06T12:01:20.000-06:00 msg="llama-server started in 20 seconds"\n',
        encoding="utf-8",
    )

    profile = campaign._ollama_swap_profile(log)

    assert profile["load"] == {"n": 2, "median_s": 16.0, "p95_s": 20.0}
    assert profile["swap_median_s"] == 16.0
    assert profile["unload"] is None


def test_load_guard_fit_sets_block_one_and_records_the_verdict(tmp_path: Path, monkeypatch) -> None:
    rows = [
        {"workspace": "ws", "arm": arm, "model": arm, "state": "PENDING"} for arm in ("inc", "cand")
    ]
    manifest = {"rows": rows}
    execution = {
        "interleave_block": 4,
        "interleave_block_by_workspace": {"ws": 4},
        "interleave_block_reason_by_workspace": {"ws": "measured timing"},
        "interleave_block_override": False,
        "resident_fit_workspaces": [],
    }
    (tmp_path / "manifest.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(campaign, "ENGINE", "pipeline")
    monkeypatch.setattr(
        campaign,
        "_models_by_workspace",
        lambda _rows: {"ws": [{"engine": "omlx", "model": arm} for arm in ("inc", "cand")]},
    )
    monkeypatch.setattr(
        campaign,
        "_load_guard_plan",
        lambda models: {
            "guard_enabled": True,
            "fits": True,
            "busy": False,
            "models": models,
        },
    )

    result = campaign._apply_load_guard_choices(tmp_path, manifest, execution, ["inc", "cand"])

    assert result["interleave_block_by_workspace"]["ws"] == 1
    assert result["interleave_block_reason_by_workspace"]["ws"] == (
        "load guard confirms both arms fit resident together; block 1"
    )
    assert result["resident_fit_workspaces"] == ["ws"]
    assert json.loads((tmp_path / "manifest.json").read_text())["execution"][
        "interleave_load_guard"
    ]["ws"]["fits"]


def test_disabled_load_guard_does_not_select_block_one(tmp_path: Path, monkeypatch) -> None:
    manifest = {
        "rows": [
            {"workspace": "ws", "arm": arm, "model": arm, "state": "PENDING"}
            for arm in ("inc", "cand")
        ]
    }
    execution = {
        "interleave_block": 4,
        "interleave_block_by_workspace": {"ws": 4},
        "interleave_block_reason_by_workspace": {"ws": "measured timing"},
        "interleave_block_override": False,
    }
    (tmp_path / "manifest.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(campaign, "ENGINE", "pipeline")
    monkeypatch.setattr(
        campaign,
        "_models_by_workspace",
        lambda _rows: {"ws": [{"engine": "omlx", "model": arm} for arm in ("inc", "cand")]},
    )
    monkeypatch.setattr(
        campaign,
        "_load_guard_plan",
        lambda _models: {"guard_enabled": False, "fits": True, "busy": False},
    )

    result = campaign._apply_load_guard_choices(tmp_path, manifest, execution, ["inc", "cand"])

    assert result["interleave_block_by_workspace"]["ws"] == 4
    assert result["resident_fit_workspaces"] == []


def test_pilot_defaults_to_six_tasks() -> None:
    _parser, args = campaign._parse_args(["--pilot"])

    assert args.pilot == 6


def test_interleave_blocks_keep_task_repeat_pairs_adjacent_and_honor_block_size() -> None:
    rows = [
        {
            "workspace": "ws",
            "arm": arm,
            "suite": "s",
            "task_id": task,
            "repeat": repeat,
            "run_id": f"{arm}:{task}:r{repeat}",
            "state": "PENDING",
        }
        for arm in ("inc", "cand")
        for task in ("t1", "t2")
        for repeat in (0, 1)
    ]

    single = campaign._interleave_blocks(rows, ["inc", "cand"], {"ws": 1})
    block = campaign._interleave_blocks(rows, ["inc", "cand"], {"ws": 2})

    assert len(single) == 4
    assert single[0][0]["key"] == ("ws", "s", "t1", 0)
    assert single[0][0]["run_ids"] == {
        "inc": ["inc:t1:r0"],
        "cand": ["cand:t1:r0"],
    }
    assert len(block) == 2 and [unit["key"] for unit in block[0]] == [
        ("ws", "s", "t1", 0),
        ("ws", "s", "t2", 0),
    ]


def test_pilot_matrix_selects_the_same_tasks_once_for_each_arm() -> None:
    matrix = [
        {
            "workspace": workspace,
            "arm": arm,
            "suite": "s",
            "task_id": f"t{i}",
            "repeat": repeat,
        }
        for arm in ("inc", "cand")
        for workspace in ("ws", "ws2")
        for i in range(4)
        for repeat in range(3)
    ]

    rows = campaign.pilot_matrix(matrix, 2)

    assert len(rows) == 4
    assert {r["arm"] for r in rows} == {"inc", "cand"}
    assert {r["task_id"] for r in rows if r["arm"] == "inc"} == {"t0", "t1"}
    assert {r["task_id"] for r in rows if r["arm"] == "cand"} == {"t0", "t1"}
    assert {r["repeat"] for r in rows} == {0}
    assert {r["workspace"] for r in rows} == {"ws"}


def test_pilot_matrix_spreads_selection_round_robin_across_families() -> None:
    matrix = [
        {
            "workspace": "ws",
            "arm": arm,
            "suite": "s",
            "task_id": f"{family}-{i:02d}",
            "repeat": repeat,
        }
        for arm in ("inc", "cand")
        for family in ("alpha", "beta", "gamma")
        for i in range(4)
        for repeat in range(2)
    ]

    rows = campaign.pilot_matrix(matrix, 6)

    assert len(rows) == 12
    assert {r["repeat"] for r in rows} == {0}
    inc = {r["task_id"] for r in rows if r["arm"] == "inc"}
    assert inc == {"alpha-00", "alpha-01", "beta-00", "beta-01", "gamma-00", "gamma-01"}
    assert {r["task_id"] for r in rows if r["arm"] == "cand"} == inc


def test_pilot_matrix_with_fewer_tasks_than_families_takes_first_families_in_order() -> None:
    matrix = [
        {
            "workspace": "ws",
            "arm": "inc",
            "suite": "s",
            "task_id": f"{family}-{i:02d}",
            "repeat": 0,
        }
        for family in ("alpha", "beta", "gamma")
        for i in range(4)
    ]

    assert [r["task_id"] for r in campaign.pilot_matrix(matrix, 2)] == ["alpha-00", "beta-00"]


def test_pilot_matrix_groups_by_declared_category_when_the_suite_has_one(tmp_path: Path) -> None:
    suite = tmp_path / "realuse.jsonl"
    suite.write_text(
        "\n".join(
            json.dumps({"id": f"ru-{i:03d}", "category": "writing" if i <= 2 else "coding"})
            for i in range(1, 7)
        )
        + "\n"
    )
    matrix = [
        {
            "workspace": "ws",
            "arm": "inc",
            "suite": "realuse",
            "suite_path": str(suite),
            "task_id": f"ru-{i:03d}",
            "repeat": 0,
        }
        for i in range(1, 7)
    ]

    # Ids alone are one family (ru); the declared category splits writing/coding,
    # so the pilot takes the first task of each instead of the first two ids.
    assert [r["task_id"] for r in campaign.pilot_matrix(matrix, 2)] == ["ru-001", "ru-003"]


def test_arms_file_filters_interleaved_arm_selection_by_id_or_model(tmp_path: Path) -> None:
    arms_file = tmp_path / "arms.txt"
    arms_file.write_text("cand-model\n")
    manifest = {
        "rows": [
            {"arm": "inc", "arm_role": "incumbent", "model": "inc-model"},
            {"arm": "cand@card", "arm_role": "challenger", "model": "cand-model"},
        ]
    }

    assert campaign._select_arms(manifest, None, arms_file) == ["cand@card"]


def test_interleaved_blocks_launch_a_fresh_arm_worker(tmp_path: Path, monkeypatch) -> None:
    campaign_dir = tmp_path / "campaigns" / "c"
    campaign_dir.mkdir(parents=True)
    calls = []

    def fake_run(command, **kwargs):
        path = Path(command[command.index("--run-ids-file") + 1])
        calls.append((command, path.read_text(), kwargs))
        return type("Result", (), {"returncode": 0})()

    monkeypatch.setattr(campaign, "ollama_reachable", lambda: True)
    monkeypatch.setattr(campaign.subprocess, "run", fake_run)
    args = type(
        "Args",
        (),
        {
            "plan": "plan.yaml",
            "tier": "confirm",
            "max_turns": 8,
            "all_suites": False,
            "notify": False,
            "no_halt": False,
            "no_curtail": False,
            "rerun_failed": False,
            "fresh_incumbent": False,
            "repeats": None,
            "pilot": 2,
            "rehearse": True,
            "debug_dir": None,
            "force": False,
        },
    )()
    block = [
        {
            "run_ids": {"inc": ["inc:t0:r0"], "cand": ["cand:t0:r0"]},
        }
    ]

    outs = campaign._run_interleaved_block(campaign_dir, block, ["inc", "cand"], args, 30)

    assert [out["arm"] for out in outs] == ["inc", "cand"]
    assert [call[1] for call in calls] == ["inc:t0:r0", "cand:t0:r0"]
    assert all("--block-worker" in call[0] for call in calls)
    assert all(call[0][call[0].index("--pilot") + 1] == "2" for call in calls)
    assert all("--rehearse" in call[0] for call in calls)
    assert len({call[0][call[0].index("--block-id") + 1] for call in calls}) == 1
    assert all(call[2]["stdin"] is subprocess.DEVNULL for call in calls)
