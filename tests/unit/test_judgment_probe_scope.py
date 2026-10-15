"""N-9: the judgment probe states that it is a single-seat probe, not the council path."""

from __future__ import annotations

from pathlib import Path

PROBE = Path(__file__).resolve().parents[2] / "tests" / "benchmarks" / "bench_judgment_probe_v6.py"


def test_the_probe_header_says_it_is_not_the_council_path() -> None:
    head = PROBE.read_text(encoding="utf-8").split('"""', 2)[1]
    assert "NOT THE COUNCIL PATH" in head
