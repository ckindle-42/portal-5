"""Unit tests for the MFLUX image tool contract (MEDIA_OVERHAUL_RESEARCH §1.3/§1.4).

No network: subprocess building is exercised through _mflux_cmd, the job
lifecycle through the shared MediaJobManager with _generate stubbed, and the
admission/reclaim coupling through admit() call capture.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest

import portal.modules.media.tools.mflux_mcp as mflux_mcp
from portal.modules.media.tools import _admission


class TestRoster:
    def test_default_model_is_the_recommended_primary(self):
        assert mflux_mcp.MFLUX_DEFAULT_MODEL == "flux2-klein"

    def test_roster_matches_the_research_plan(self):
        assert mflux_mcp.MFLUX_MODELS == {
            "flux2-klein": "flux2-klein-4b",
            "flux3-klein": "flux3-image-klein",
            "qwen-2.1": "qwen-image-2.1-turbo",
            "z-image": "z-image-turbo",
        }

    def test_distilled_step_counts_are_correct(self):
        # klein was hardcoded to 28 — FLUX.2 klein 4B is a 4-step distilled model.
        steps = mflux_mcp.MFLUX_DEFAULT_STEPS
        assert steps["flux2-klein"] == 4
        assert steps["flux3-klein"] == 16
        assert steps["qwen-2.1"] == 8
        assert steps["z-image"] == 8

    def test_retired_tags_are_not_rostered(self):
        for tag in ("schnell", "dev", "qwen-image", "qwen-image-edit"):
            assert tag not in mflux_mcp.MFLUX_MODELS, tag
            assert tag not in mflux_mcp.MFLUX_MODEL_BIN, tag

    def test_retired_schnell_still_routes_through_the_base_binary(self):
        built = mflux_mcp._mflux_cmd("hi", "schnell", 4, 1, 512, 512, Path("/tmp/o.png"))
        assert isinstance(built, list)
        assert built[0] == mflux_mcp.MFLUX_BIN
        assert "--compute-precision" not in built  # FLUX.1 base binary has no such flag

    def test_admission_budgets_cover_the_roster(self):
        for key in ("flux2-klein", "flux3-klein", "qwen-2.1", "z-image"):
            assert f"mflux:{key}" in _admission.MEDIA_MODEL_MEMORY_GB, key


class TestCommandBuilding:
    def test_t2i_uses_the_family_binary_and_roster_tag(self):
        built = mflux_mcp._mflux_cmd("hi", "flux2-klein", 4, 1, 1024, 1024, Path("/tmp/o.png"))
        assert isinstance(built, list)
        assert built[0].endswith("mflux-generate-flux2")
        assert built[built.index("--model") + 1] == "flux2-klein-4b"

    def test_edit_uses_the_edit_binary_with_repeatable_image_paths(self):
        srcs = [Path("/tmp/a.png"), Path("/tmp/b.png")]
        built = mflux_mcp._mflux_cmd(
            "hi", "qwen-2.1", 8, 1, 1024, 1024, Path("/tmp/o.png"), image_paths=srcs
        )
        assert isinstance(built, list)
        assert built[0].endswith("mflux-generate-qwen-2.1-edit")
        assert built.count("--image-paths") == 2
        assert built[built.index("--image-paths") + 1] == "/tmp/a.png"
        assert "strength" not in built

    def test_edit_model_without_edit_binary_is_refused(self):
        built = mflux_mcp._mflux_cmd(
            "hi", "z-image", 8, 1, 1024, 1024, Path("/tmp/o.png"), image_paths=[Path("/tmp/a.png")]
        )
        assert built["success"] is False
        assert "no edit binary" in built["error"]

    def test_float16_compute_precision_flag_is_family_only(self, monkeypatch):
        monkeypatch.setattr(mflux_mcp, "MFLUX_COMPUTE_PRECISION", "float16")
        built = mflux_mcp._mflux_cmd("hi", "flux3-klein", 16, 1, 1024, 1024, Path("/tmp/o.png"))
        assert isinstance(built, list)
        assert built[built.index("--compute-precision") + 1] == "float16"
        legacy = mflux_mcp._mflux_cmd("hi", "schnell", 4, 1, 512, 512, Path("/tmp/o.png"))
        assert isinstance(legacy, list)
        assert "--compute-precision" not in legacy

    def test_compute_precision_can_be_disabled(self, monkeypatch):
        monkeypatch.setattr(mflux_mcp, "MFLUX_COMPUTE_PRECISION", "")
        built = mflux_mcp._mflux_cmd("hi", "flux2-klein", 4, 1, 1024, 1024, Path("/tmp/o.png"))
        assert isinstance(built, list)
        assert "--compute-precision" not in built


@pytest.mark.asyncio
async def test_edit_image_refuses_unsupported_model_before_any_subprocess(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    async def explode(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("no subprocess may start for an unsupported edit model")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", explode)
    monkeypatch.setattr(mflux_mcp, "admit", _no_refusal)
    monkeypatch.setattr(mflux_mcp, "_fetch_source_image", _fake_source(tmp_path))
    result = await mflux_mcp.edit_image(image_url="a.png", prompt="make it blue", model="z-image")
    assert result["success"] is False
    assert "no edit binary" in result["error"]


@pytest.mark.asyncio
async def test_edit_image_admits_before_generating(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls: list[str] = []

    async def fake_admit(key: str) -> None:
        calls.append(key)

    async def fake_generate(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        calls.append("generate")
        return {"success": True, "artifact_path": "/tmp/x.png"}

    monkeypatch.setattr(mflux_mcp, "admit", fake_admit)
    monkeypatch.setattr(mflux_mcp, "_generate", fake_generate)
    monkeypatch.setattr(mflux_mcp, "_fetch_source_image", _fake_source(tmp_path))
    result = await mflux_mcp.edit_image(image_url="a.png", prompt="make it blue")
    assert result["success"] is True
    assert calls == ["mflux:qwen-2.1", "generate"]


def _fake_source(tmp_path: Path):
    async def _fetch(_url: str) -> Path:
        src = tmp_path / "src.png"
        src.write_bytes(b"\x89PNG\r\n\x1a\n")
        return src

    return _fetch


@pytest.mark.asyncio
async def test_image_job_lifecycle_publishes_artifact_under_generated_images(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("AI_OUTPUT_DIR", str(tmp_path))
    monkeypatch.setattr(mflux_mcp, "admit", _no_refusal)

    async def fake_generate(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        out = mflux_mcp.get_generated_dir("images") / "mflux_test.png"
        out.write_bytes(b"\x89PNG\r\n\x1a\n")
        return {"success": True, "artifact_path": str(out), "url": "http://owui/f.png"}

    monkeypatch.setattr(mflux_mcp, "_generate", fake_generate)
    started = await mflux_mcp.image_start(prompt="a red circle", width=512, height=512)
    assert started["success"] is True and started["job_id"]
    assert (
        started["next_action"]
        == f"in a later turn, call image_status with job_id='{started['job_id']}'"
    )
    done = await mflux_mcp.image_status(started["job_id"], wait_s=2.0)
    assert done["status"] == "done"
    assert Path(done["artifact_path"]).is_relative_to(tmp_path / "generated" / "images")
    assert done["model"] == "flux2-klein"


@pytest.mark.asyncio
async def test_image_start_admits_with_the_roster_model_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[str] = []

    async def fake_admit(key: str) -> None:
        seen.append(key)

    async def fake_generate(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return {"success": True, "artifact_path": "/tmp/x.png"}

    monkeypatch.setattr(mflux_mcp, "admit", fake_admit)
    monkeypatch.setattr(mflux_mcp, "_generate", fake_generate)
    started = await mflux_mcp.image_start(prompt="x", model="flux3-klein")
    await mflux_mcp.image_status(started["job_id"], wait_s=2.0)
    assert seen == ["mflux:flux3-klein", "mflux:flux3-klein"]  # pre-flight + in-job re-check


async def _no_refusal(_key: str) -> None:
    return None
