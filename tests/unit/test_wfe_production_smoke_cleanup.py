"""Offline checks for production smoke's memory-note cleanup."""

from __future__ import annotations

import importlib

smoke = importlib.import_module("scripts.wfe_production_smoke")


def test_remember_result_id_is_captured_from_answer_text() -> None:
    memory_id = "16c30fcb-7b52-4677-9141-9a0a5277b23d"
    assert smoke._memory_id_from_tool_result_text(f"Stored memory id: {memory_id}") == memory_id
    assert smoke._memory_id_from_tool_result_text("Stored, but no id was included") == ""


def test_cleanup_posts_memory_id_to_forget_tool(tmp_path, monkeypatch) -> None:
    memory_id = "16c30fcb-7b52-4677-9141-9a0a5277b23d"
    requests = []
    monkeypatch.setattr(smoke, "OUTPUT", tmp_path)
    monkeypatch.setattr(smoke, "delete_file", lambda file_id: None)
    monkeypatch.setattr(smoke, "MEMORY_MCP", "http://memory.test")
    monkeypatch.setattr(
        smoke,
        "http",
        lambda url, body, timeout: requests.append((url, body, timeout)) or {"forgotten": True},
    )

    smoke.cleanup(["uploaded-file"], [memory_id])

    assert requests == [
        (
            "http://memory.test/tools/forget",
            {"arguments": {"id": memory_id}},
            30,
        )
    ]


def test_cleanup_prints_warning_if_forget_fails(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.setattr(smoke, "OUTPUT", tmp_path)
    monkeypatch.setattr(
        smoke, "http", lambda *args, **kwargs: (_ for _ in ()).throw(OSError("offline"))
    )

    smoke.cleanup([], ["16c30fcb-7b52-4677-9141-9a0a5277b23d"])

    assert "WARNING: could not forget smoke memory" in capsys.readouterr().out


def test_cleanup_warns_when_successful_remember_has_no_returned_id(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(smoke, "OUTPUT", tmp_path)

    smoke.cleanup([], remember_id_missing=True)

    assert "the smoke note may remain stored" in capsys.readouterr().out
