from __future__ import annotations

from pathlib import Path

from scripts.validation.ollama_direct import check_allowlist, direct_ollama_posts


def _fixture_tree(root: Path, allowlist: str) -> Path:
    (root / "portal").mkdir()
    (root / "config").mkdir()
    source = root / "portal" / "caller.py"
    source.write_text(
        "import httpx\n"
        "def call(url):\n"
        '    return httpx.post(f"{url}/api/chat", json={"model": "x"})\n',
        encoding="utf-8",
    )
    (root / "config" / "ollama_direct_allowlist.yaml").write_text(allowlist, encoding="utf-8")
    return source


def test_unlisted_runtime_ollama_post_fails(tmp_path):
    source = _fixture_tree(tmp_path, "allowlist: {}\n")

    status, message, details = check_allowlist(tmp_path)

    assert status == "FAIL"
    assert "direct Ollama POST" in message
    assert details[0]["file"] == source.relative_to(tmp_path).as_posix()


def test_reasoned_allowlist_entry_passes(tmp_path):
    source = _fixture_tree(
        tmp_path,
        "allowlist:\n  portal/caller.py: operator-only model diagnostic\n",
    )

    status, message, details = check_allowlist(tmp_path)

    assert status == "PASS"
    assert "1 direct POST" in message
    assert details[0]["reason"] == "operator-only model diagnostic"
    assert direct_ollama_posts(tmp_path) == [
        {"file": source.relative_to(tmp_path).as_posix(), "line": 3}
    ]


def test_pipeline_passthrough_base_is_not_a_bypass(tmp_path):
    (tmp_path / "portal").mkdir()
    caller = tmp_path / "portal" / "caller.py"
    caller.write_text(
        "import httpx\n"
        'OLLAMA_NATIVE_BASE = "http://portal-pipeline:9099/ollama"\n'
        "def call():\n"
        '    return httpx.post(f"{OLLAMA_NATIVE_BASE}/api/chat", json={})\n',
        encoding="utf-8",
    )

    assert direct_ollama_posts(tmp_path) == []
