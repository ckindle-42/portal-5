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
