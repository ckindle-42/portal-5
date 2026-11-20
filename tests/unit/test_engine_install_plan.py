"""Engine installers upgrade sweep fixes only. The core stack stays put.

The 2026-11-19 install-music failure: `uv pip install --upgrade` moved
torch 2.10.0→2.15, transformers 4.57.6→5.23.0, huggingface-hub 0.36→2.4,
diffusers 0.37.1→0.43, and numpy 2.3.5→2.5.5. The advisory fixes that were
kept were pillow 13.0.0, certifi 2026.10.23, anyio 4.16.0, and brotli 1.2.1.
"""

from __future__ import annotations

from scripts.engine_install_plan import build_plan, is_core_stack

_INSTALLED = {
    "torch": "2.10.0",
    "transformers": "4.57.6",
    "huggingface-hub": "0.36.0",
    "diffusers": "0.37.1",
    "numpy": "2.3.5",
    "mlx": "0.29.0",
    "pillow": "12.2.0",
    "certifi": "2025.1.31",
    "anyio": "4.8.0",
    "brotli": "1.1.0",
}

_SWEEP = """
| Ecosystem | Package | Version | Advisory | Severity | Fixed in | Source |
|---|---|---|---|---|---|---|
| PyPI | pillow | 12.2.0 | GHSA-5x8w-8jj5-q52h | CRITICAL | 13.0.0 | music/.venv |
| PyPI | certifi | 2025.1.31 | GHSA-certifi | HIGH | 2026.10.23 | music/.venv |
| PyPI | anyio | 4.8.0 | GHSA-anyio | HIGH | 4.16.0 | music/.venv |
| PyPI | brotli | 1.1.0 | GHSA-brotli | HIGH | 1.2.1 | music/.venv |
| PyPI | torch | 2.10.0 | GHSA-torch | HIGH | 2.15.0 | music/.venv |
| PyPI | transformers | 4.57.6 | GHSA-transformers | HIGH | 5.23.0 | music/.venv |
| PyPI | huggingface-hub | 0.36.0 | GHSA-hf | HIGH | 2.4.0 | music/.venv |
| PyPI | diffusers | 0.37.1 | GHSA-diffusers | HIGH | 0.43.0 | music/.venv |
| PyPI | numpy | 2.3.5 | GHSA-numpy | HIGH | 2.5.5 | music/.venv |
| PyPI | mlx | 0.29.0 | GHSA-mlx | HIGH | 0.40.0 | music/.venv |
"""


def test_core_stack_names_cover_the_engine_runtime():
    for name in ("torch", "transformers", "diffusers", "huggingface-hub", "numpy", "mlx", "mlx-lm"):
        assert is_core_stack(name)
    assert not is_core_stack("pillow")
    assert not is_core_stack("certifi")


def test_music_plan_upgrades_only_the_kept_advisories():
    plan = build_plan("music", _INSTALLED, _SWEEP)
    assert plan.upgrades == (
        "anyio>=4.16.0",
        "brotli>=1.2.1",
        "certifi>=2026.10.23",
        "pillow>=13.0.0",
    )
    joined = " ".join(plan.requirements())
    for core in (
        "torch==",
        "torch>=",
        "transformers==",
        "transformers>=",
        "diffusers==",
        "diffusers>=",
        "huggingface-hub==",
        "huggingface-hub>=",
        "numpy==",
        "numpy>=",
        "mlx==",
    ):
        assert core not in joined
    assert "mlx-audio==0.6.6" in plan.service_deps
    held = set(plan.holds)
    assert "torch==2.10.0" in held
    assert "transformers==4.57.6" in held
    assert "huggingface-hub==0.36.0" in held
    assert "diffusers==0.37.1" in held
    assert "numpy==2.3.5" in held
    assert "mlx==0.29.0" in held
    assert any("torch==2.15.0" in line and "engine bump required" in line for line in plan.refused)
    command = plan.argv("/tmp/python", "/tmp/hold.txt")
    assert "--upgrade" in command
    assert command[command.index("--resolution") + 1] == "highest"
    assert command[command.index("--prerelease") + 1] == "disallow"
    assert "--upgrade-package" not in command
    assert "torch==2.15.0" not in command
    assert "transformers==5.23.0" not in command


def test_video_plan_does_not_request_transformers():
    plan = build_plan("video", _INSTALLED, _SWEEP)
    assert "transformers>=5.10.0" not in plan.service_deps
    assert "transformers==5.23.0" not in plan.upgrades
    assert "starlette>=1.3.1" in plan.service_deps


def test_dry_run_text_lists_the_package_changes():
    from scripts.engine_install_plan import render_plan

    text = render_plan(build_plan("music", _INSTALLED, _SWEEP), "/tmp/python")
    assert "pillow>=13.0.0" in text
    assert "certifi>=2026.10.23" in text
    assert "torch==2.10.0" in text
    assert "engine bump required" in text
    assert "--upgrade-package" not in text
    assert "--upgrade " in text


# Real shapes from the 2026-11-19 round-3 run: the hold file, the target set and
# uv's stderr were captured from scratch copies of the three engine venvs.

_MUSIC_INSTALLED = {
    "mlx": "0.30.6",
    "mlx-lm": "0.29.1",
    "mlx-metal": "0.30.6",
    "torch": "2.10.0",
    "torchaudio": "2.10.0",
    "torchvision": "0.25.0",
    "transformers": "4.57.6",
    "numpy": "2.3.5",
    "huggingface-hub": "0.36.0",
    "diffusers": "0.37.1",
    "gradio": "6.2.0",
    "multidict": "6.7.1",
    "filelock": "3.20.3",
    "aiohttp": "3.13.3",
    "certifi": "2026.1.4",
    "pillow": "12.1.0",
    "setuptools": "71.1.0",
}

_MUSIC_SWEEP = """
| Ecosystem | Package | Version | Advisory | Severity | Fixed in | Source |
|---|---|---|---|---|---|---|
| PyPI | gradio | 6.2.0 | GHSA-j36p-7w88-g82j | HIGH | 6.16.0 | ~/.portal5/music/ACE-Step-1.5/.venv |
| PyPI | gradio | 6.2.0 | PYSEC-2026-2179 | UNKNOWN | 6.16.0 | ~/.portal5/music/ACE-Step-1.5/.venv |
| PyPI | gradio | 6.2.0 | PYSEC-2026-211 | UNKNOWN |  | ~/.portal5/music/ACE-Step-1.5/.venv |
| PyPI | multidict | 6.7.1 | GHSA-54p9-h82j-f925 | MODERATE | 6.9.1 | ~/mcp/comet-kvm/.venv |
| PyPI | filelock | 3.25.2 | GHSA-v4x8-3wr5-3wq8 | HIGH | 4.2.1 | ~/.portal5/music/.venv |
| PyPI | fastmcp | 3.2.0 | GHSA-7xgj-8392-5q4r | MODERATE | 3.4.10 | ~/.portal5/music/.venv |
| PyPI | certifi | 2026.5.20 | GHSA-6q48-6c7w-9gw2 | CRITICAL | 2026.10.18 | ~/mcp/comet-kvm/.venv |
| PyPI | aiohttp | 3.14.1 | GHSA-24c4-3p7v-29cm | HIGH | 3.14.4 | ~/mcp/comet-kvm/.venv |
| PyPI | pillow | 12.2.0 | GHSA-5x8w-8jj5-q52h | CRITICAL | 13.0.0 | ~/.local/share/uv/tools/hermes-agent |
| PyPI | setuptools | 84.0.0 | GHSA-xmj3-9gf7-h52w | LOW | 84.1.0 | /Volumes/data01/mflux-venv |
| PyPI | torch | 2.11.0 | GHSA-rrmf-rvhw-rf47 | LOW | 2.13.0 | ~/.portal5/music/.venv |
| PyPI | transformers | 5.5.0 | GHSA-xrqw-3rrv-vx5w | HIGH | 5.10.0 | ~/.portal5/music/.venv |
| PyPI | transformers | 5.5.0 | PYSEC-2026-3929 | UNKNOWN | 5.10.0 | ~/.portal5/music/.venv |
"""

_MLX_CONFLICT_STDERR = """  × No solution found when resolving dependencies:
  ╰─▶ Because mlx-audio==0.6.6 depends on mlx>=0.32.4 and mlx==0.30.6, we can
      conclude that mlx-audio==0.6.6 cannot be used.
      And because you require mlx-audio==0.6.6, we can
      conclude that your requirements are unsatisfiable.
"""

_FASTMCP_CONFLICT_STDERR = """  × No solution found when resolving dependencies:
  ╰─▶ Because fastmcp-slim[client]==3.4.10 depends on mcp>=1.24.0,<2.0 and
      fastmcp==3.4.10 depends on fastmcp-slim[client]==3.4.10, we can conclude
      that fastmcp==3.4.10 depends on mcp>=1.24.0,<2.0.
      And because you require mcp>=2.0.0,<3.0.0 and fastmcp==3.4.10, we can
      conclude that your requirements are unsatisfiable.
"""


def test_music_plan_applies_sweep_fixes_to_installed_versions_below_the_floor():
    plan = build_plan("music", _MUSIC_INSTALLED, _MUSIC_SWEEP)
    assert plan.upgrades == (
        "aiohttp>=3.14.4",
        "certifi>=2026.10.18",
        "filelock>=4.2.1",
        "gradio>=6.16.0",
        "multidict>=6.9.1",
        "pillow>=13.0.0",
        "setuptools>=84.1.0",
    )
    # A report row cannot target a package that is absent from the engine venv.
    for name in ("fastmcp",):
        assert not any(spec.startswith(f"{name}==") for spec in plan.upgrades)
    assert "mlx==0.30.6" in plan.holds
    assert "torch==2.10.0" in plan.holds
    refused = "\n".join(plan.refused)
    assert "torch==2.13.0" in refused and "engine bump required" in refused
    assert "transformers==5.10.0" in refused
    assert "GHSA-rrmf-rvhw-rf47" in refused
    assert "PYSEC-2026-3929" in refused
    assert plan.satisfied == ()


def test_music_plan_applies_reported_fixes_across_versions_and_service_deps():
    installed = {"fastapi": "0.128.0", "pillow": "12.1.0"}
    sweep = """
| Ecosystem | Package | Version | Advisory | Severity | Fixed in | Source |
|---|---|---|---|---|---|---|
| PyPI | fastapi | 0.128.0 | GHSA-fastapi | HIGH | 0.165.0 | another/.venv |
| PyPI | pillow | 12.2.0 | GHSA-pillow | CRITICAL | 13.0.0 | another/.venv |
"""
    plan = build_plan("music", installed, sweep)
    assert plan.upgrades == ("fastapi>=0.165.0", "pillow>=13.0.0")


def test_apply_refreshes_sweep_before_building_the_engine_plan(tmp_path):
    import os
    import subprocess
    from pathlib import Path

    portal_root = tmp_path / "portal"
    python = portal_root / ".venv" / "bin" / "python"
    python.parent.mkdir(parents=True)
    call_log = tmp_path / "calls.txt"
    python.write_text(
        "#!/bin/sh\n"
        "{ printf '__CALL__\\n'; printf '%s\\n' \"$@\"; } >> \"$CALL_LOG\"\n"
        'if [ "${1##*/}" = security_sweep.py ]; then\n'
        '  while [ "$#" -gt 0 ]; do\n'
        '    if [ "$1" = --output-dir ]; then shift; out="$1"; break; fi\n'
        "    shift\n"
        "  done\n"
        '  mkdir -p "$out"\n'
        '  touch "$out/security_sweep_20990101.md"\n'
        "fi\n",
        encoding="utf-8",
    )
    python.chmod(0o755)
    home = tmp_path / "home"
    stale_report = home / ".portal5" / "security" / "security_sweep_20260101.md"
    stale_report.parent.mkdir(parents=True)
    stale_report.touch()
    services = Path(__file__).resolve().parents[2] / "scripts" / "lib" / "services.sh"
    env = os.environ | {
        "CALL_LOG": str(call_log),
        "HOME": str(home),
        "PORTAL_ROOT": str(portal_root),
        "SERVICES_SH": str(services),
        "TARGET_PY": str(tmp_path / "music" / ".venv" / "bin" / "python"),
    }
    result = subprocess.run(
        ["bash", "-c", 'source "$SERVICES_SH"; _engine_dep_plan music "$TARGET_PY" apply'],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    calls = [
        part.splitlines()
        for part in call_log.read_text(encoding="utf-8").split("__CALL__\n")
        if part.strip()
    ]
    assert len(calls) == 2
    assert calls[0][0].endswith("security_sweep.py")
    assert {"--skip-images", "--no-alert", "--no-delta"}.issubset(calls[0])
    assert calls[1][0].endswith("engine_install_plan.py")
    report = calls[1][calls[1].index("--sweep-report") + 1]
    assert "portal5-engine-sweep." in report
    assert report != str(stale_report)
    assert not Path(report).exists()


def test_engine_plan_exports_upstream_lock_before_resolving(tmp_path):
    import os
    import subprocess
    from pathlib import Path

    portal_root = tmp_path / "portal"
    python = portal_root / ".venv" / "bin" / "python"
    python.parent.mkdir(parents=True)
    plan_args = tmp_path / "plan-args.txt"
    python.write_text(
        "#!/bin/sh\n"
        'if [ "${1##*/}" = security_sweep.py ]; then\n'
        '  while [ "$#" -gt 0 ]; do\n'
        '    if [ "$1" = --output-dir ]; then shift; out="$1"; break; fi\n'
        "    shift\n"
        "  done\n"
        '  mkdir -p "$out"; touch "$out/security_sweep_20990101.md"\n'
        'elif [ "${1##*/}" = engine_install_plan.py ]; then\n'
        '  printf "%s\\n" "$@" > "$PLAN_ARGS"\n'
        "fi\n",
        encoding="utf-8",
    )
    python.chmod(0o755)
    project = tmp_path / "music-engine"
    project.mkdir()
    (project / "uv.lock").touch()
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    uv_log = tmp_path / "uv-args.txt"
    fake_uv = fake_bin / "uv"
    fake_uv.write_text(
        "#!/bin/sh\n"
        'printf "%s\\n" "$@" > "$UV_LOG"\n'
        'while [ "$#" -gt 0 ]; do\n'
        '  if [ "$1" = --output-file ]; then shift; out="$1"; break; fi\n'
        "  shift\n"
        "done\n"
        'printf "aiohttp==3.13.3\\n" > "$out"\n',
        encoding="utf-8",
    )
    fake_uv.chmod(0o755)
    services = Path(__file__).resolve().parents[2] / "scripts" / "lib" / "services.sh"
    env = os.environ | {
        "HOME": str(tmp_path / "home"),
        "PATH": f"{fake_bin}:{os.environ['PATH']}",
        "PLAN_ARGS": str(plan_args),
        "PORTAL_ROOT": str(portal_root),
        "SERVICES_SH": str(services),
        "TARGET_PY": str(tmp_path / "music" / ".venv" / "bin" / "python"),
        "UV_LOG": str(uv_log),
    }
    result = subprocess.run(
        [
            "bash",
            "-c",
            'source "$SERVICES_SH"; _engine_dep_plan music "$TARGET_PY" apply "$PROJECT"',
        ],
        capture_output=True,
        text=True,
        env=env | {"PROJECT": str(project)},
        check=False,
    )
    assert result.returncode == 0, result.stderr
    exported = uv_log.read_text(encoding="utf-8").splitlines()
    assert exported[0] == "export"
    assert "--locked" in exported
    assert "--python" in exported
    assert "--all-extras" not in exported
    args = plan_args.read_text(encoding="utf-8").splitlines()
    assert "--upstream-requirements" in args
    assert "upstream-requirements.txt" in args[args.index("--upstream-requirements") + 1]

    wan_requirement = "mlx-video @ git+https://example.invalid/mlx-video.git@abc123"
    result = subprocess.run(
        [
            "bash",
            "-c",
            'source "$SERVICES_SH"; _engine_dep_plan video "$TARGET_PY" apply "$PROJECT" "$WAN_REQ"',
        ],
        capture_output=True,
        text=True,
        env=env | {"PROJECT": str(project), "WAN_REQ": wan_requirement},
        check=False,
    )
    assert result.returncode == 0, result.stderr
    exported = uv_log.read_text(encoding="utf-8").splitlines()
    assert "--all-extras" in exported
    args = plan_args.read_text(encoding="utf-8").splitlines()
    assert args[args.index("--extra-requirement") + 1] == wan_requirement


def test_music_and_video_seed_only_missing_engine_venvs():
    from pathlib import Path

    services = Path(__file__).resolve().parents[2] / "scripts" / "lib" / "services.sh"
    text = services.read_text(encoding="utf-8")
    assert 'if [ -d "$ACE_DIR/.venv" ]; then' in text
    assert 'if [ -d "$VX_VENV" ]; then' in text
    assert "Existing ACE-Step venv has no usable Python" in text
    assert "Existing video venv has no usable Python" in text
    assert "uv sync --python 3.12 --frozen" in text
    assert "uv sync --all-extras" in text
    assert 'uv pip install "mlx-video @ git+' not in text


def test_sweep_parser_ignores_rows_without_a_fixed_version_column():
    from scripts.engine_install_plan import parse_sweep_fixes

    sweep = "| PyPI | aiohttp | 3.13.3 | PYSEC-2026-2094 | UNKNOWN | ~/.portal5/music/.venv |\n"
    assert parse_sweep_fixes(sweep) == {}


def test_upstream_lock_versions_are_requirements_floors_not_pins():
    from scripts.engine_install_plan import build_plan, parse_upstream_floors

    lock = """
# Generated requirements
-e ./packages/engine-core
aiohttp==3.13.3
torch==2.10.0 ; sys_platform == 'darwin'
torch==2.10.0+cu130 ; sys_platform == 'win32'
"""
    floors = parse_upstream_floors(lock)
    assert floors == (
        "aiohttp>=3.13.3",
        "torch>=2.10.0 ; sys_platform == 'darwin'",
        "torch>=2.10.0 ; sys_platform == 'win32'",
    )
    plan = build_plan("video", {}, "", lock)
    assert "aiohttp>=3.13.3" in plan.requirements()
    assert "torch>=2.10.0 ; sys_platform == 'darwin'" in plan.requirements()


def test_upgrade_plan_updates_all_installed_packages_without_lowering_floors():
    plan = build_plan("video", {"idna": "3.20.0", "torch": "2.10.0"}, "")
    command = plan.argv("/tmp/python", "/tmp/constraints")
    assert "--upgrade" in command
    assert "idna" in command
    assert "idna>=3.20.0" in plan.floors
    assert "torch==2.10.0" in plan.holds


def test_extra_dependency_uses_the_same_install_plan():
    dependency = "mlx-video @ git+https://example.invalid/mlx-video.git@abc123"
    plan = build_plan("video", {"idna": "3.20.0"}, "", extra_requirements=(dependency,))
    assert dependency in plan.requirements()
    assert "idna>=3.20.0" in plan.floors


def test_apply_shows_old_to_new_changes_before_installing(monkeypatch, capsys):
    import subprocess

    from scripts.engine_install_plan import _apply

    plan = build_plan("video", {"idna": "3.20.0"}, "")
    calls = []

    def run(command, **kwargs):
        calls.append(command)
        stdout = "Would install 1 package\n - idna==3.20.0\n + idna==3.21.0\n"
        return subprocess.CompletedProcess(command, 0, stdout=stdout, stderr="")

    monkeypatch.setattr("scripts.engine_install_plan.subprocess.run", run)
    assert _apply(plan, "/tmp/python", dry_run=False) == 0
    assert len(calls) == 2
    assert "--dry-run" in calls[0]
    assert "--dry-run" not in calls[1]
    assert "idna: 3.20.0 -> 3.21.0" in capsys.readouterr().out


def test_apply_aborts_before_install_when_dry_run_downgrades(monkeypatch, capsys):
    import subprocess

    from scripts.engine_install_plan import _apply

    plan = build_plan("video", {"idna": "3.20.0"}, "")
    calls = []

    def run(command, **kwargs):
        calls.append(command)
        stdout = "Would install 1 package\n - idna==3.20.0\n + idna==3.11.0\n"
        return subprocess.CompletedProcess(command, 0, stdout=stdout, stderr="")

    monkeypatch.setattr("scripts.engine_install_plan.subprocess.run", run)
    assert _apply(plan, "/tmp/python", dry_run=False) != 0
    assert len(calls) == 1
    assert "--dry-run" in calls[0]
    output = capsys.readouterr().out
    assert "idna: 3.20.0 -> 3.11.0" in output
    assert "refusing downgrade" in output.lower()


def test_music_plan_holds_core_at_the_installed_versions_only():
    plan = build_plan("music", _MUSIC_INSTALLED, _MUSIC_SWEEP)
    for hold in plan.holds:
        name, _, version = hold.partition("==")
        assert _MUSIC_INSTALLED[name] == version


def test_core_refusal_requires_the_package_installed_and_below_the_fix():
    plan = build_plan("video", {"transformers": "5.3.0", "filelock": "3.25.2"}, _MUSIC_SWEEP)
    assert plan.upgrades == ("filelock>=4.2.1",)
    assert any(
        "transformers==5.10.0" in line and "installed 5.3.0" in line for line in plan.refused
    )
    # torch is not installed in the video venv: no refusal for it.
    assert not any(line.startswith("torch") for line in plan.refused)
    # An installed core version at or above the fix is already satisfied.
    plan = build_plan("mflux", {"torch": "2.13.0", "mlx": "0.32.2"}, _MUSIC_SWEEP)
    assert plan.refused == ()
    assert plan.satisfied == ("torch==2.13.0 (fix 2.13.0)",)


def test_requirement_tokens_parse_the_real_conflict_output():
    from scripts.engine_install_plan import requirement_tokens

    tokens = requirement_tokens(_MLX_CONFLICT_STDERR)
    assert tokens == ["mlx-audio==0.6.6", "mlx>=0.32.4", "mlx==0.30.6"]


def test_refine_drops_the_service_dep_that_contradicts_a_held_pin():
    from scripts.engine_install_plan import refine_plan

    plan = build_plan("music", _MUSIC_INSTALLED, _MUSIC_SWEEP)
    refined, note = refine_plan(plan, _MLX_CONFLICT_STDERR)
    assert "mlx-audio==0.6.6" in note and "mlx==0.30.6" in note
    assert "engine bump required" in note
    assert not any("mlx-audio" in spec for spec in refined.service_deps)
    assert any(
        "mlx-audio==0.6.6" in line and "held mlx==0.30.6" in line for line in refined.refused
    )
    assert refined.holds == plan.holds
    assert refined.upgrades == plan.upgrades
    # A second refine on a plan without mlx-audio finds nothing to drop.
    assert refine_plan(refined, _MLX_CONFLICT_STDERR) is None


def test_refine_drops_the_sweep_fix_that_contradicts_a_service_dep():
    from scripts.engine_install_plan import refine_plan

    installed = {"fastmcp": "3.2.0", "mcp": "2.3.0"}
    sweep = "| PyPI | fastmcp | 3.2.0 | GHSA-7xgj-8392-5q4r | MODERATE | 3.4.10 | x |\n"
    plan = build_plan("mflux", installed, sweep)
    assert "fastmcp>=3.4.10" in plan.upgrades
    refined, note = refine_plan(plan, _FASTMCP_CONFLICT_STDERR)
    assert "fastmcp==3.4.10" in note and "mcp>=2.0.0" in note
    assert refined.upgrades == ()
    assert refined.upgrade_packages == ()
    assert "fastmcp>=3.2.0" in refined.floors
    assert refined.service_deps == plan.service_deps


def test_dry_run_text_names_the_conflict_sources():
    from scripts.engine_install_plan import render_plan

    text = render_plan(build_plan("music", _MUSIC_INSTALLED, _MUSIC_SWEEP), "/tmp/python")
    assert "gradio>=6.16.0" in text
    assert "multidict>=6.9.1" in text
    assert "mlx==0.30.6" in text
    assert "engine bump required" in text
