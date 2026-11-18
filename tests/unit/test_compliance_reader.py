"""The reader's conditions, and the conversation corpus (BILATERAL_CORPUS_V1 P6).

No model is called here. What is tested is everything AROUND the reading: that
the material handed over is complete and labelled, that citations are resolved
and reported with what they are, that a fabricated citation is caught and named,
that an answer is retained and contestable, that it is superseded when its
revision moves, and that an operator note outranks it.

There is deliberately no test asserting what a reading should CONTAIN. A test
that fixed the shape of an answer would be the schema this phase exists to not
build.
"""

from __future__ import annotations

import pytest

from portal.modules.compliance.core import reader


@pytest.fixture(autouse=True)
def _pin_native_transport(monkeypatch):
    """These tests pin the NATIVE wire contract. The P5-FANOUT-001 default
    (``COMPLIANCE_TRANSPORT=pipeline``) would resolve them at the pipeline
    dialect, which owns its transport and bypasses the ``_post`` fakes below;
    ``ollama-native`` restores the resolution these tests were written under."""
    monkeypatch.setenv("COMPLIANCE_TRANSPORT", "ollama-native")


class TestTheMaterialHandedOver:
    def test_the_prompt_imposes_no_output_shape(self) -> None:
        prompt, version, sha = reader.load_prompt()
        lowered = " ".join(prompt.lower().split())
        for forbidden in ("json", "schema", "field", "enum", "step 1", "first,", "format:"):
            assert forbidden not in lowered, forbidden
        assert "prose" in lowered
        # It is a versioned artifact, not a literal: both identifiers exist and
        # the sha is of the body, so an edit cannot pass as the same prompt.
        assert version != "undeclared" and len(sha) == 12

    def test_the_prompt_asks_for_the_work_the_reader_actually_does(self) -> None:
        """PROVE_CIP_007_V1 P1.2. The v1 prompt opened "in front of you" and
        asked for prose. It never said the model had tools, never said the
        opening material was a starting point, and never asked for the
        comparison a posture question needs — so a control contract had to FAIL
        a reading for behaviour the prompt had not requested."""
        prompt, _, _ = reader.load_prompt()
        # wrapping is incidental to prose; the claims are about the sentences
        lowered = " ".join(prompt.lower().split())
        # the tools, named
        for tool in (
            "compliance_requirement",
            "compliance_read",
            "compliance_links",
            "compliance_search",
            "compliance_timeline",
            "compliance_notes",
        ):
            assert tool in prompt, tool
        # references are not text
        assert "references" in lowered and "unread until you read it" in lowered
        # both sides
        assert "at least one operator section" in lowered
        # over-strictness as fact, not as a gap or a question
        assert "exceeding a requirement is permitted" in lowered
        assert "never a gap" in lowered
        # latitude the standard grants and the procedure narrowed
        assert "less latitude than nerc grants" in lowered
        # the GTB, citable but never duty text
        assert "never binding duty text" in lowered
        # declared omissions
        assert "a declared omission is acceptable" in lowered


class TestTheDeletedComparator:
    def test_the_quantity_comparator_is_gone(self) -> None:
        from portal.modules.compliance.core import reading

        assert not hasattr(reading, "_quantity_direction")
        assert "deleted with its cause" in reading._QUANTITY_DIRECTION_DELETED


class TestQuantityAttribution:
    """Found by hand in the P6.8 probe, then reproduced here: three of four
    seats wrote "the operator's procedure evaluates every thirty calendar days"
    and cited the section that says thirty-five. The number was real — it came
    from an operator note elsewhere in the packet — so checking against the
    union of everything cited passed all three."""

    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("thirty-five (35) calendar days", ("35", "day")),
            ("thirty calendar days", ("30", "day")),
            ("35 calendar days", ("35", "day")),
            ("three calendar years", ("3", "year")),
            ("ninety days", ("90", "day")),
        ],
    )
    def test_a_compound_number_is_not_read_as_its_own_tail(
        self, text: str, expected: tuple[str, str]
    ) -> None:
        match = reader._QUANTITY_RE.search(text)
        assert match is not None
        assert reader._normalise_quantity(match) == expected

    def test_thirty_five_is_never_read_as_five(self) -> None:
        match = reader._QUANTITY_RE.search("thirty-five calendar days")
        assert reader._normalise_quantity(match)[0] == "35"

    def test_a_parenthesised_spelling_still_counts_as_stated(self) -> None:
        assert reader._quantity_in("35", "day", "At least every 35 calendar days (thirty-five)")


class TestAnAbsenceClaimIsNotANegativeAnswer:
    """Rung 2, then §P8.4. The analyst asked "does anything narrow that
    choice?"; the model answered "**No.** The operator's procedure preserves
    all three actions" — and the contract read `no` … `procedure` within
    eighty characters as an assertion that evidence was ABSENT. Three live
    Part 2.3 readings, every semantic check passing, all failed for answering
    the question they were asked. The cue regex was first narrowed, then
    REMOVED entirely (WINDOW_AND_SEAT_V1 §P8.4): whether prose asserts an
    absence is a judgment about prose, and a pattern match that makes it is
    the acceptance rubric living inside the product. The closure now fails on
    exactly two facts — no tool call, nothing in scope cited — and never on
    the shape of a sentence."""

    def test_the_closure_has_no_absence_input_left(self) -> None:
        import inspect

        parameters = inspect.signature(reader._closure_failure).parameters
        assert "absence_claim" not in parameters
        assert not hasattr(reader, "_ABSENCE_CLAIM")

    def test_an_absence_flavored_answer_with_in_scope_citations_passes(self) -> None:
        cited = "csection-" + "a" * 20
        # The answer TEXT is not an input to the closure at all — that is the
        # contract. The same facts that once fired the regex now pass: one
        # tool call, one in-scope citation.
        assert reader._closure_failure(model_calls=1, eligible={cited}, cited={cited}) == ""
        assert reader._closure_failure(model_calls=3, eligible={cited}, cited={cited}) == ""

    def test_the_two_facts_still_fail(self) -> None:
        cited = "csection-" + "a" * 20
        no_tool_call = reader._closure_failure(model_calls=0, eligible={cited}, cited={cited})
        assert "without reading" in no_tool_call
        out_of_scope = reader._closure_failure(model_calls=2, eligible={cited}, cited=set())
        assert "cites no section in scope" in out_of_scope


class TestTheLoopRefusesACallThatCannotFit:
    """Rung 0. `DEFAULT_NUM_CTX` was derived at 4.22 chars/token, measured on
    RAW CORPUS TEXT; a real assembled thread runs 2.95–3.06. The loop appends a
    tool result per turn, bounded at 12,000 characters, up to twelve times — so
    the worst thread is ~82,000 tokens, not the ~43,000 the derivation assumed.
    The live `CIP-007-6 R2` cell reached it and died with an Ollama HTTP 500,
    twice, at 1,522 s and 760 s."""

    def test_a_thread_that_would_not_fit_is_refused_with_both_numbers(self) -> None:
        detail = reader._window_exhausted(
            thread_chars=300_000,
            ratio=3.0,
            window=98_304,
            answer_tokens=3072,
            reasoning=4096,
            step=7,
        )
        assert detail
        assert "100000" in detail and "98304" in detail
        assert "after 7 turn(s)" in detail

    def test_a_thread_that_fits_is_not_refused(self) -> None:
        assert (
            reader._window_exhausted(
                thread_chars=30_000,
                ratio=3.0,
                window=98_304,
                answer_tokens=3072,
                reasoning=4096,
                step=1,
            )
            == ""
        )

    def test_the_ratio_is_recalibrated_from_the_runner_not_the_constant(self) -> None:
        """The estimate is seeded from CHARS_PER_TOKEN and replaced by the
        runner's own count, because the constant was measured on other text."""
        assert reader._recalibrate(2.1, 60_000, {"prompt_eval_count": 20_000}) == 3.0
        # no count yet: keep the (conservative) seed rather than invent one
        assert reader._recalibrate(2.1, 60_000, {"prompt_eval_count": 0}) == 2.1
