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
        "anyio==4.16.0",
        "brotli==1.2.1",
        "certifi==2026.10.23",
        "pillow==13.0.0",
    )
    joined = " ".join(plan.requirements())
    for core in ("torch", "transformers", "diffusers", "huggingface-hub", "numpy", "mlx=="):
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
    assert "--upgrade" not in command
    assert command.count("--upgrade-package") == 4
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
    assert "pillow==13.0.0" in text
    assert "certifi==2026.10.23" in text
    assert "torch==2.10.0" in text
    assert "engine bump required" in text
    assert "--upgrade-package" in text
    assert "--upgrade " not in text


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


def test_music_plan_moves_only_the_flagged_versions_installed_here():
    plan = build_plan("music", _MUSIC_INSTALLED, _MUSIC_SWEEP)
    assert plan.upgrades == ("gradio==6.16.0", "multidict==6.9.1")
    # Fixtures flagged in other environments must not move this venv.
    for name in ("fastmcp", "filelock", "certifi", "aiohttp", "pillow", "setuptools"):
        assert not any(spec.startswith(f"{name}==") for spec in plan.upgrades)
    assert "mlx==0.30.6" in plan.holds
    assert "torch==2.10.0" in plan.holds
    refused = "\n".join(plan.refused)
    assert "torch==2.13.0" in refused and "engine bump required" in refused
    assert "transformers==5.10.0" in refused
    assert "GHSA-rrmf-rvhw-rf47" in refused
    assert "PYSEC-2026-3929" in refused
    assert plan.satisfied == ()


def test_music_plan_holds_core_at_the_installed_versions_only():
    plan = build_plan("music", _MUSIC_INSTALLED, _MUSIC_SWEEP)
    for hold in plan.holds:
        name, _, version = hold.partition("==")
        assert _MUSIC_INSTALLED[name] == version


def test_core_refusal_requires_the_package_installed_and_below_the_fix():
    plan = build_plan("video", {"transformers": "5.3.0", "filelock": "3.25.2"}, _MUSIC_SWEEP)
    assert plan.upgrades == ("filelock==4.2.1",)
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
    assert "fastmcp==3.4.10" in plan.upgrades
    refined, note = refine_plan(plan, _FASTMCP_CONFLICT_STDERR)
    assert "fastmcp==3.4.10" in note and "mcp>=2.0.0" in note
    assert refined.upgrades == ()
    assert refined.upgrade_packages == ()
    assert refined.service_deps == plan.service_deps


def test_dry_run_text_names_the_conflict_sources():
    from scripts.engine_install_plan import render_plan

    text = render_plan(build_plan("music", _MUSIC_INSTALLED, _MUSIC_SWEEP), "/tmp/python")
    assert "gradio==6.16.0" in text
    assert "multidict==6.9.1" in text
    assert "mlx==0.30.6" in text
    assert "engine bump required" in text
