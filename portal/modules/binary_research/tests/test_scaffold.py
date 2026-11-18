"""Session-based intake — start, answer, scaffold write (no live model, stubbed)."""

from portal.modules.binary_research.harness import scaffold as s


def test_parse_json_plain() -> None:
    assert s._parse_json('{"done": true}', {}) == {"done": True}


def test_parse_json_fenced() -> None:
    assert s._parse_json('```json\n{"goal":"x"}\n```', {}) == {"goal": "x"}


def test_parse_json_embedded() -> None:
    assert s._parse_json('here: {"goal":"y"} done', {}).get("goal") == "y"


def test_parse_json_garbage_returns_default() -> None:
    assert s._parse_json("not json", {"goal": "d"}) == {"goal": "d"}
