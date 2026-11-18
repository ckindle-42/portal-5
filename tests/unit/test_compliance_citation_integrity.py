"""P5 — the one citation-integrity diagnostic, and harness parity.

Every case runs against a fixture store built in ``tmp_path`` (one regulatory
document, one operator document, synthetic text) so nothing skips: the
resolving, fabricated and side-evidencing paths are all exercised.
"""

from __future__ import annotations

from scripts.compliance.truth.citation_integrity import MIN_QUOTE_WORDS


def test_min_quote_words_is_the_b0_calibrated_value():
    assert MIN_QUOTE_WORDS == 2


def test_obligation_attribution_inside_a_quote_is_not_an_attribution():
    import importlib

    conv = importlib.import_module("scripts.compliance.ask_conversational")
    pattern = conv._STANDARD_ATTRIBUTION
    quoted = '- "Updated CIP-004 and CIP-011 requirements for standards effective 1/1/2024"'
    assert not pattern.search(conv.QUOTED_SPAN.sub(" ", quoted))
    assert not pattern.search("CIP-011 requirements were updated")
    assert pattern.search("CIP-011 requires an information protection program")
