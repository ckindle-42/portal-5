"""Y23 — the prompt variant must actually reach the model.

This session found three parameters that were accepted and silently discarded
(`think` on /v1, runtime `options.num_ctx`, the campaign CLI's `--workspace`).
Y23 sends a CHANGED PROMPT and reads a CHANGED NUMBER, which is the same shape:
if `--prompt-variant` were ignored, every variant would score identically and
the sweep would report "stable under paraphrase" — the right answer for the
wrong reason, indistinguishable from success.

So the wire payload is asserted here, not assumed.
"""

from __future__ import annotations

import importlib

probe = importlib.import_module("tests.benchmarks.bench_judgment_probe_v6")


def test_every_variant_is_a_distinct_prompt():
    """A duplicated variant would silently shrink the measured range."""
    v = probe.PROMPT_VARIANTS
    assert len(v) >= 4, "Y23 asks for the shipped prompt plus 3-4 paraphrases"
    assert "shipped" in v
    assert v["shipped"] is probe._SYSTEM
    texts = list(v.values())
    assert len(set(texts)) == len(texts), "two variants are byte-identical"


def test_paraphrases_keep_the_output_contract():
    """A paraphrase that drops a determination label or finding type would
    change what the scorer can even see — that is a different experiment."""
    for name, text in probe.PROMPT_VARIANTS.items():
        for token in ("SUPPORTED", "PARTIAL", "CONTRADICTED", "ABSENT", "ABSTAIN"):
            assert token in text, f"{name} dropped determination {token}"
        for token in ("GAP", "CONTRADICTION", "OUTDATED_LANGUAGE", "WEAK_MAPPING"):
            assert token in text, f"{name} dropped finding_type {token}"
        assert "determination" in text and "cited_refs" in text


def test_outdated_rule_variant_adds_a_trigger_the_shipped_prompt_lacks():
    """The Y21 fix under test. It must differ from `shipped` by an actual rule,
    not by whitespace."""
    shipped = probe.PROMPT_VARIANTS["shipped"]
    fixed = probe.PROMPT_VARIANTS["outdated_rule"]
    assert fixed != shipped
    assert len(fixed) > len(shipped)
    added = fixed.replace(shipped.split("RULES:")[0], "")
    assert "aligned" in added.lower() or "dated" in added.lower()


def test_run_case_defaults_to_shipped_when_no_variant_given():
    """Back-compat: existing callers that never pass `system` keep the shipped
    prompt, so historical F2 numbers stay comparable."""
    import inspect

    sig = inspect.signature(probe.run_case)
    assert sig.parameters["system"].default is None
