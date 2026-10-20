"""X and AA must never spawn validate_system.py (its 30 s timeout always yielded None)."""

from __future__ import annotations

import subprocess

import pytest


class TestXAndAANeverSpawnValidator:
    def test_self_index_integrity_does_not_spawn_validate_system(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """X must not call validate_system.py."""
        import scripts.validation.security_bench as vs

        calls: list[tuple[list[str], dict]] = []

        def _record_run(cmd: list[str], **kwargs: object) -> object:
            calls.append((cmd, kwargs))

            class _Fake:
                stdout = ""
                returncode = 1

            return _Fake()

        monkeypatch.setattr(subprocess, "run", _record_run)

        vs.check_self_index_integrity()  # its verdict depends on live data; only spawning is asserted

        validator_calls = [
            (cmd, kw) for cmd, kw in calls if any("validate_system.py" in str(arg) for arg in cmd)
        ]
        assert validator_calls == [], (
            f"X spawned validate_system.py {len(validator_calls)} time(s):\n"
            + "\n".join(f"  {cmd}" for cmd, _ in validator_calls)
        )

    def test_stage2_propose_integrity_does_not_spawn_validate_system(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """AA must not call validate_system.py. Same invariant as the X test."""
        import scripts.validation.security_bench as vs

        calls: list[tuple[list[str], dict]] = []

        def _record_run(cmd: list[str], **kwargs: object) -> object:
            calls.append((cmd, kwargs))

            class _Fake:
                stdout = ""
                returncode = 1

            return _Fake()

        monkeypatch.setattr(subprocess, "run", _record_run)

        vs.check_stage2_propose_integrity()  # its verdict depends on live data; only spawning is asserted

        validator_calls = [
            (cmd, kw) for cmd, kw in calls if any("validate_system.py" in str(arg) for arg in cmd)
        ]
        assert validator_calls == [], (
            f"AA spawned validate_system.py {len(validator_calls)} time(s):\n"
            + "\n".join(f"  {cmd}" for cmd, _ in validator_calls)
        )
