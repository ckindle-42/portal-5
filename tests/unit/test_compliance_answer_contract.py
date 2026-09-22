"""Answer-contract unit tests — per-claim grounding (LOAD_AND_CONVERSE_V1 §P5).

The measured case that killed the token-level check: CIP-007-6 unused_latitude
cited ``csection-c36c38b8842c8bc217ac`` (resolves) and, one bullet later, the
same id with two characters dropped (``c36c38b8842c217ac``). Every claim was
supported; the whole answer was failed because the check asked "does every
token resolve" instead of "is every claim supported by a resolving citation".
"""

from __future__ import annotations

import pytest

from portal.modules.compliance.core.answer_contract import build_contract

GOOD = "csection-c36c38b8842c8bc217ac"
TYPO = "csection-c36c38b8842c217ac"  # the same section, "8b" dropped
OP = "isection-12bd999ecfa8bf61d440"


def _contract() -> object:
    return build_contract(
        "CIP-007-6 R2",
        "CIP-007-6 R2",
        [
            {"section_id": GOOD, "side": "regulatory"},
            {"section_id": OP, "side": "operator"},
        ],
    )


class TestCitedClaims:
    def test_mistyped_restatement_does_not_void_a_grounded_answer(self):
        answer = (
            "The standard grants a choice of three actions "
            f"[{GOOD}].\n"
            "* **The Standard's Latitude:** apply, mitigate, or revise "
            f"[{TYPO}].\n"
            "* **Your Procedure's Narrowing:** administrative handling only "
            f"[{OP}].\n"
        )
        result = _contract().cited_claims(answer)
        assert result["grounded"] is True
        # the typo is reported as typed, never mapped onto its neighbour
        assert TYPO in result["unresolved"]
        assert GOOD not in result["unresolved"]

    def test_a_claim_standing_only_on_an_unknown_id_is_ungrounded(self):
        answer = (
            f"A real claim with real support [{GOOD}].\n"
            "A fabricated claim standing on nothing "
            "[csection-00000000000000000000].\n"
        )
        result = _contract().cited_claims(answer)
        assert result["grounded"] is False
        assert result["n_ungrounded"] == 1
        assert "csection-00000000000000000000" in result["unresolved"]

    def test_an_unresolved_token_far_from_every_resolving_id_is_not_absolved(self):
        # no small-edit path from any resolving id — a different section claimed,
        # not a typo of the one that resolved
        answer = f"Claim one [{GOOD}].\nClaim two [csection-11111111111111111111].\n"
        result = _contract().cited_claims(answer)
        assert result["grounded"] is False
        assert result["n_ungrounded"] == 1

    def test_prose_without_citations_is_not_a_citation_bearing_claim(self):
        result = _contract().cited_claims(
            f"Supported here [{GOOD}].\n\nA paragraph that only elaborates, citing nothing.\n"
        )
        assert result["grounded"] is True
        assert result["n_claims"] == 1

    def test_an_answer_that_cites_nothing_is_not_grounded(self):
        result = _contract().cited_claims("An answer with no citations at all.")
        assert result["grounded"] is False
        assert result["n_claims"] == 0

    def test_handles_count_as_resolving_citations(self):
        answer = "The operator's procedure narrows the choices [O1].\n"
        result = _contract().cited_claims(answer)
        assert result["grounded"] is True

    @pytest.mark.parametrize(
        "typo",
        [
            "csection-c36c38b8842c217ac",  # two dropped
            "csection-c36c38b8842c8bc217ac1",  # one appended
            "CSECTION-C36C38B8842C8BC217AC",  # case mangled by a renderer
        ],
    )
    def test_variant_shapes_of_one_dropped_or_mangled_character_pair(self, typo):
        answer = f"Support [{GOOD}].\nRestatement [{typo}].\n"
        result = _contract().cited_claims(answer)
        assert result["grounded"] is True, result["unsupported_lines"]
