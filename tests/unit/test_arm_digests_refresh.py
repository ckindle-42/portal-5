"""Writer for ~/.portal5/arm_digests.env. No live engine: httpx is mocked."""

from __future__ import annotations

import json
import os
import warnings
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
import yaml
from typer.testing import CliRunner

from portal.modules.orchestration import service as arm_service
from portal.modules.orchestration.cli import orchestration_app
from portal.modules.orchestration.service import refresh_arm_digests, resolve_seat_digest

ROOT = Path(__file__).resolve().parents[2]


def _plan(fast: str = "fastmodel", deep: str = "deepmodel") -> dict:
    return {
        "load_plan_models": {
            "fast": {"engine": "ollama", "model": fast},
            "deep": {"engine": "omlx", "model": deep},
        }
    }


def _tags_client(digest: str = "sha256:fast", name: str = "fastmodel") -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/tags"
        return httpx.Response(200, json={"models": [{"name": name, "digest": digest}]})

    return httpx.Client(transport=httpx.MockTransport(handler))


def _checkpoint(root: Path, model: str) -> None:
    directory = root / model
    directory.mkdir(parents=True)
    (directory / "config.json").write_text('{"quant": 4}', encoding="utf-8")
    (directory / "model.safetensors").write_text("w" * 10, encoding="utf-8")


def test_refresh_writes_ollama_tags_and_the_wfe_omlx_id(tmp_path: Path, monkeypatch) -> None:
    from tests.wfe import campaign as camp

    monkeypatch.setenv("OMLX_MODEL_DIR", str(tmp_path / "models"))
    settings = tmp_path / "model_settings.json"
    settings.write_text(json.dumps({"models": {"deepmodel": {"temperature": 0.6}}}))
    monkeypatch.setattr(camp, "OMLX_SETTINGS", settings)
    _checkpoint(tmp_path / "models", "deepmodel")
    expected, why = camp.omlx_content_id("deepmodel")
    assert expected and not why

    env_file = tmp_path / "host" / "arm_digests.env"
    source = tmp_path / "orchestration_arm.yaml"
    source.write_text("load_plan_models: {}\n", encoding="utf-8")

    # A tags digest for the oMLX model must not win: the deep seat is absent from Ollama.
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/tags"
        return httpx.Response(
            200,
            json={
                "models": [
                    {"name": "fastmodel", "digest": "sha256:fast"},
                    {"name": "deepmodel", "digest": "sha256:not-the-omlx-id"},
                ]
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    digests = refresh_arm_digests(
        _plan(),
        env_file=env_file,
        config_path=source,
        client=client,
        clock=lambda: datetime(2026, 10, 29, 12, 0, tzinfo=UTC),
    )

    assert digests == {"fast": "sha256:fast", "deep": expected}
    text = env_file.read_text(encoding="utf-8")
    assert text.startswith(f"# refreshed 2026-10-29T12:00:00Z from {source}\n")
    assert "PORTAL_ARM_FAST_DIGEST=sha256:fast\n" in text
    assert f"PORTAL_ARM_DEEP_DIGEST={expected}\n" in text
    assert list(env_file.parent.glob(".arm_digests.env.*.tmp")) == []


def test_dry_run_and_a_missing_digest_do_not_write(tmp_path: Path) -> None:
    env_file = tmp_path / "arm_digests.env"
    digests = refresh_arm_digests(
        _plan(),
        env_file=env_file,
        client=_tags_client(),
        omlx_identity=lambda _model: ("omlxdigest", ""),
        dry_run=True,
    )

    assert digests["deep"] == "omlxdigest"
    assert not env_file.exists()

    with pytest.raises(ValueError, match="unreachable"):
        refresh_arm_digests(
            _plan(),
            env_file=env_file,
            client=httpx.Client(
                transport=httpx.MockTransport(lambda _request: httpx.Response(500))
            ),
            omlx_identity=lambda _model: ("omlxdigest", ""),
        )
    assert not env_file.exists()


def test_resolve_warns_when_the_digest_file_is_older_than_the_seat_config(tmp_path: Path) -> None:
    config = tmp_path / "orchestration_arm.yaml"
    env_file = tmp_path / "arm_digests.env"
    config.write_text("seats: {}\n", encoding="utf-8")
    env_file.write_text("PORTAL_ARM_DEEP_DIGEST=from-file\n", encoding="utf-8")
    os.utime(env_file, (1_000, 1_000))
    os.utime(config, (2_000, 2_000))

    with pytest.warns(UserWarning, match="portal arm digests refresh"):
        found = resolve_seat_digest(
            "deep",
            {"engine": "omlx", "model": "deepmodel"},
            environ={},
            env_file=env_file,
            config_path=config,
            fetch_tags=lambda: {},
        )
    assert found == "from-file"

    os.utime(config, (1_000, 1_000))
    os.utime(env_file, (2_000, 2_000))
    with warnings.catch_warnings():
        warnings.simplefilter("error", UserWarning)
        assert (
            resolve_seat_digest(
                "deep",
                {"engine": "omlx", "model": "deepmodel"},
                environ={"PORTAL_ARM_DEEP_DIGEST": "from-env"},
                env_file=env_file,
                config_path=config,
                fetch_tags=lambda: {},
            )
            == "from-env"
        )
        assert (
            resolve_seat_digest(
                "deep",
                {},
                environ={},
                env_file=env_file,
                config_path=config,
                fetch_tags=lambda: {},
            )
            == "from-file"
        )


def test_cli_dry_run_prints_both_digests_and_does_not_touch_the_host_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(arm_service, "ARM_DIGESTS_ENV", tmp_path / "arm_digests.env")
    config = yaml.safe_load((ROOT / "config" / "orchestration_arm.yaml").read_text())
    fast = config["load_plan_models"]["fast"]
    deep = config["load_plan_models"]["deep"]
    assert fast["engine"] == "ollama"
    assert deep["engine"] == "omlx"
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.path)
        return httpx.Response(
            200, json={"models": [{"name": fast["model"], "digest": "sha256:cli"}]}
        )

    real_client = httpx.Client
    monkeypatch.setattr(
        arm_service.httpx,
        "Client",
        lambda *_args, **_kwargs: real_client(transport=httpx.MockTransport(handler)),
    )
    monkeypatch.setattr(arm_service, "_wfe_omlx_content", lambda model: (f"id:{model}", ""))

    result = CliRunner().invoke(orchestration_app, ["digests", "refresh", "--dry-run"])

    assert result.exit_code == 0, result.output
    assert "PORTAL_ARM_FAST_DIGEST=sha256:cli" in result.output
    assert f"PORTAL_ARM_DEEP_DIGEST=id:{deep['model']}" in result.output
    assert "not written" in result.output
    assert seen == ["/api/tags"]
    assert not (tmp_path / "arm_digests.env").exists()
