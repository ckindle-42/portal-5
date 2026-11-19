"""Offline staleness → refresh tests for the host arm_digests.env file."""

from __future__ import annotations

import os
import warnings
from pathlib import Path
from typing import Any

import yaml

from portal.modules.orchestration import cli, service

CONFIG = {
    "planner": {"max_bites": 3},
    "review": {"rubric": "pass"},
    "approval": {"mode": "manual"},
    "calibration": {"minimum_pass_probability": 0.5},
    "disciplines": {},
    "load_plan_models": {
        "fast": {"engine": "omlx", "model": "portal5/fast-test"},
        "deep": {"engine": "omlx", "model": "portal5/deep-test"},
    },
}


def _write_config(tmp_path: Path) -> Path:
    path = tmp_path / "orchestration_arm.yaml"
    path.write_text(yaml.safe_dump(CONFIG), encoding="utf-8")
    return path


def _write_env(path: Path, digest: str = "sha256:stale") -> None:
    path.write_text(
        f"PORTAL_ARM_FAST_DIGEST={digest}\nPORTAL_ARM_DEEP_DIGEST={digest}\n", encoding="utf-8"
    )


def _age(path: Path, seconds: int) -> None:
    stamp = path.stat().st_mtime - seconds
    os.utime(path, (stamp, stamp))


def _identity(digests: dict[str, str], seen: list[str]) -> Any:
    def look(model: str) -> tuple[str, str]:
        seen.append(model)
        digest = digests.get(model, "")
        return digest, ("" if digest else "oMLX content is unobservable")

    return look


def test_stale_env_file_refreshes_itself(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    env_file = tmp_path / "arm_digests.env"
    _write_env(env_file)
    _age(env_file, 10)
    seen: list[str] = []

    cause = service.ensure_arm_digests_fresh(
        CONFIG,
        config_path=config_path,
        env_file=env_file,
        omlx_identity=_identity(
            {"portal5/fast-test": "sha256:fast1", "portal5/deep-test": "sha256:deep1"}, seen
        ),
    )

    assert cause == ""
    assert seen == ["portal5/fast-test", "portal5/deep-test"]
    body = env_file.read_text(encoding="utf-8")
    assert "PORTAL_ARM_FAST_DIGEST=sha256:fast1" in body
    assert "PORTAL_ARM_DEEP_DIGEST=sha256:deep1" in body
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        digest = service.resolve_seat_digest(
            "fast",
            {"model": "portal5/fast-test"},
            environ={},
            env_file=env_file,
            fetch_tags=lambda: {"models": []},
            config_path=config_path,
        )
    assert digest == "sha256:fast1"


def test_missing_env_file_is_created(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    env_file = tmp_path / "arm_digests.env"

    cause = service.ensure_arm_digests_fresh(
        CONFIG,
        config_path=config_path,
        env_file=env_file,
        omlx_identity=_identity(
            {"portal5/fast-test": "sha256:f", "portal5/deep-test": "sha256:d"}, []
        ),
    )

    assert cause == ""
    assert "PORTAL_ARM_FAST_DIGEST=sha256:f" in env_file.read_text(encoding="utf-8")


def test_fresh_env_file_is_left_alone(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    env_file = tmp_path / "arm_digests.env"
    _write_env(env_file, "sha256:keep")
    _age(config_path, 10)
    seen: list[str] = []

    cause = service.ensure_arm_digests_fresh(
        CONFIG, config_path=config_path, env_file=env_file, omlx_identity=_identity({}, seen)
    )

    assert cause == ""
    assert seen == []
    assert "sha256:keep" in env_file.read_text(encoding="utf-8")


def test_refresh_failure_warns_once_with_cause(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    env_file = tmp_path / "arm_digests.env"
    _write_env(env_file, "sha256:stale")
    _age(env_file, 10)
    seen: list[str] = []

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        cause = service.ensure_arm_digests_fresh(
            CONFIG, config_path=config_path, env_file=env_file, omlx_identity=_identity({}, seen)
        )

    assert cause
    assert "load_plan_models.fast" in cause
    assert [w for w in caught if issubclass(w.category, UserWarning)] != []
    assert "sha256:stale" in env_file.read_text(encoding="utf-8")


def test_missing_config_is_a_no_op(tmp_path: Path) -> None:
    env_file = tmp_path / "arm_digests.env"
    _write_env(env_file)

    cause = service.ensure_arm_digests_fresh(
        CONFIG,
        config_path=tmp_path / "absent.yaml",
        env_file=env_file,
        omlx_identity=_identity({}, []),
    )

    assert cause == ""
    assert "sha256:stale" in env_file.read_text(encoding="utf-8")


def test_service_build_refreshes_digests_before_resolving(monkeypatch, tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    monkeypatch.setenv("PIPELINE_API_KEY", "test-key")
    monkeypatch.setenv("PORTAL_ARM_TELEGRAM_DB", str(tmp_path / "telegram.db"))
    monkeypatch.setattr(cli, "_arm_config_path", lambda: config_path)
    monkeypatch.setattr(service, "_default_config_path", lambda: config_path)
    order: list[str] = []

    def fake_ensure(config: Any, **kwargs: Any) -> str:
        order.append(("ensure", kwargs.get("config_path")))
        return ""

    def fake_resolve(seat: str, identity: Any, **kwargs: Any) -> str:
        order.append(f"resolve.{seat}")
        return "sha256:stub"

    monkeypatch.setattr(service, "ensure_arm_digests_fresh", fake_ensure)
    monkeypatch.setattr(service, "resolve_seat_digest", fake_resolve)

    built, error = cli._build_service(tmp_path)

    assert error is None
    assert built is not None
    assert built.engines["fast"].model_digest == "sha256:stub"
    ensure_calls = [entry for entry in order if isinstance(entry, tuple)]
    assert ensure_calls == [("ensure", config_path)]
    assert order.index(ensure_calls[0]) < order.index("resolve.fast")
