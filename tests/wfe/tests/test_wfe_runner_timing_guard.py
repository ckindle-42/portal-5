"""A malformed timing field costs the row its timing, never the row (wfe_math_20261018c)."""

from tests.wfe import runner


def test_redacted_or_non_numeric_timings_become_none():
    econ = runner._econ_from_timings(
        {
            "reasoning_tokens": "<redacted>",
            "answer_tokens": 30,
            "answer_tps": 76.6,
            "ttft_s": True,
            "timing_source": "engine",
        }
    )
    assert econ.reasoning_tokens is None and econ.ttft_s is None
    assert econ.answer_tokens == 30 and econ.answer_tps == 76.6
    assert econ.timing_source == "engine"
