"""Offline checks for production smoke's memory-note cleanup."""

from __future__ import annotations

import importlib

smoke = importlib.import_module("scripts.wfe_production_smoke")

ECHOED_ID = "16c30fcb-7b52-4677-9141-9a0a5277b23d"
SWEEP_ID = "8a8a5c7c-9fbf-4bb4-a532-cce9260ecd95"
UNRELATED_ID = "0b9d3e44-1f18-4c2a-9f08-6f4e2e2c7a11"


class FakeMemoryHTTP:
    """Fake memory-MCP HTTP layer: recall returns a fixed list, forget records the call."""

    def __init__(
        self,
        memories: list[dict] | None = None,
        *,
        recall_error: str = "",
        forget_errors: tuple[str, ...] = (),
    ) -> None:
        self.memories = list(memories or [])
        self.recall_error = recall_error
        self.forget_errors = set(forget_errors)
        self.requests: list[tuple[str, dict, int]] = []

    def __call__(self, url: str, body: dict, timeout: int) -> dict:
        self.requests.append((url, body, timeout))
        if url.endswith("/tools/recall"):
            if self.recall_error:
                raise OSError(self.recall_error)
            return {"memories": self.memories}
        if url.endswith("/tools/forget"):
            memory_id = body["arguments"]["id"]
            if memory_id in self.forget_errors:
                raise OSError("forget failed")
            return {"id": memory_id, "deleted": True}
        raise AssertionError(f"unexpected url {url}")

    def calls(self, tool: str) -> list[tuple[str, dict, int]]:
        return [r for r in self.requests if r[0].endswith(f"/tools/{tool}")]


def _cleanup(
    tmp_path,
    monkeypatch,
    fake: FakeMemoryHTTP,
    *,
    memory_ids: list[str] | None = None,
    remember_id_missing: bool = False,
) -> None:
    monkeypatch.setattr(smoke, "OUTPUT", tmp_path)
    monkeypatch.setattr(smoke, "delete_file", lambda file_id: None)
    monkeypatch.setattr(smoke, "MEMORY_MCP", "http://memory.test")
    monkeypatch.setattr(smoke, "http", fake)
    smoke.cleanup([], memory_ids, remember_id_missing=remember_id_missing)


def _smoke_note(memory_id: str) -> dict:
    return {
        "id": memory_id,
        "text": f'Remember that the smoke test code word is "{smoke.SMOKE_CODE_WORD}".',
    }


def test_remember_result_id_is_captured_from_answer_text() -> None:
    memory_id = "16c30fcb-7b52-4677-9141-9a0a5277b23d"
    assert smoke._memory_id_from_tool_result_text(f"Stored memory id: {memory_id}") == memory_id
    assert smoke._memory_id_from_tool_result_text("Stored, but no id was included") == ""


def test_cleanup_forgets_echoed_id_and_still_sweeps(tmp_path, monkeypatch) -> None:
    fake = FakeMemoryHTTP()

    _cleanup(tmp_path, monkeypatch, fake, memory_ids=[ECHOED_ID])

    assert fake.calls("forget") == [
        ("http://memory.test/tools/forget", {"arguments": {"id": ECHOED_ID}}, 30)
    ]
    assert fake.calls("recall") == [
        (
            "http://memory.test/tools/recall",
            {"arguments": {"query": smoke.MEMORY_SWEEP_QUERY}},
            30,
        )
    ]


def test_cleanup_sweep_forgets_note_when_id_was_not_echoed(tmp_path, monkeypatch, capsys) -> None:
    fake = FakeMemoryHTTP([_smoke_note(SWEEP_ID)])

    _cleanup(tmp_path, monkeypatch, fake, memory_ids=[], remember_id_missing=True)

    assert fake.calls("forget") == [
        ("http://memory.test/tools/forget", {"arguments": {"id": SWEEP_ID}}, 30)
    ]
    out = capsys.readouterr().out
    assert "the smoke note may remain stored" in out
    assert "cleanup: forgot 1 smoke memory note(s) via recall sweep" in out


def test_cleanup_sweep_warns_when_recall_fails(tmp_path, monkeypatch, capsys) -> None:
    fake = FakeMemoryHTTP(recall_error="connection refused")

    _cleanup(tmp_path, monkeypatch, fake)

    assert fake.calls("forget") == []
    assert "WARNING: could not sweep the memory store for smoke notes: connection refused" in (
        capsys.readouterr().out
    )


def test_cleanup_sweep_never_forgets_an_unrelated_memory(tmp_path, monkeypatch, capsys) -> None:
    fake = FakeMemoryHTTP([{"id": UNRELATED_ID, "text": "ZETA-4471 uat_test_key"}])

    _cleanup(tmp_path, monkeypatch, fake)

    assert fake.calls("forget") == []
    assert "cleanup: forgot 0 smoke memory note(s) via recall sweep" in capsys.readouterr().out


def test_cleanup_prints_warning_if_forget_fails(tmp_path, monkeypatch, capsys) -> None:
    fake = FakeMemoryHTTP(forget_errors=(ECHOED_ID,))

    _cleanup(tmp_path, monkeypatch, fake, memory_ids=[ECHOED_ID])

    assert "WARNING: could not forget smoke memory" in capsys.readouterr().out


def test_cleanup_warns_when_successful_remember_has_no_returned_id(
    tmp_path, monkeypatch, capsys
) -> None:
    _cleanup(tmp_path, monkeypatch, FakeMemoryHTTP(), remember_id_missing=True)

    assert "the smoke note may remain stored" in capsys.readouterr().out
