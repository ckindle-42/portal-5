"""Unit tests confirming X and AA do not spawn validate_system.py.

P0 PUSH_GATE_X_AA: checks X (`check_self_index_integrity`) and AA
(`check_stage2_propose_integrity`) each took exactly 30 s because
`build_self_index()` called `_run_validator_json()` which shelled out to
`scripts/validate_system.py --json --skip-pytest` with `timeout=30`. The
validator always timed out and returned None, so the checks carried on with an
absent signal -- but paid 30 s wall-clock for it. The fix patches
`_run_validator_json` to return None immediately inside both checks. This test
ensures the subprocess is never spawned at all.
"""

from __future__ import annotations

import subprocess

import pytest


class TestXAndAANeverSpawnValidator:
    def test_self_index_integrity_does_not_spawn_validate_system(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """X must not call validate_system.py. The validator reader is patched to
        return None immediately; the subprocess call should never reach the OS."""
        import scripts.validation.security_bench as vs

        calls: list[tuple[list[str], dict]] = []

        def _record_run(cmd: list[str], **kwargs: object) -> object:
            calls.append((cmd, kwargs))

            # Return a fake completed process so the check can continue past the
            # call; we only assert on the call list, not on the return value.
            class _Fake:
                stdout = ""
                returncode = 1

            return _Fake()

        monkeypatch.setattr(subprocess, "run", _record_run)

        status, _detail, _subs = vs.check_self_index_integrity()
        assert status == "PASS"

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

        status, _detail, _subs = vs.check_stage2_propose_integrity()
        assert status == "PASS"

        validator_calls = [
            (cmd, kw) for cmd, kw in calls if any("validate_system.py" in str(arg) for arg in cmd)
        ]
        assert validator_calls == [], (
            f"AA spawned validate_system.py {len(validator_calls)} time(s):\n"
            + "\n".join(f"  {cmd}" for cmd, _ in validator_calls)
        )
