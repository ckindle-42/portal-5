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
import json

probe = importlib.import_module("tests.benchmarks.bench_judgment_probe_v6")


def _case():
    return {
        "id": "T-1",
        "governing_ref": "CIP-007-6 R2 Part 2.2",
        "governing_text": "Evaluate security patches at least once every 35 calendar days.",
        "premises": [],
        "candidate_text": "Patches are evaluated every 30 days.",
        "packet_complete": True,
        "gold_label": "SUPPORTED",
    }


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


def test_run_case_puts_the_chosen_variant_on_the_wire(monkeypatch):
    """The plumbing assertion: whatever `system` run_case is handed is what the
    system message contains. Without this, a dropped kwarg looks like a model
    that is simply insensitive to wording."""
    seen = {}

    class _Resp:
        def read(self):
            return json.dumps(
                {"message": {"content": "{}"}, "eval_count": 1, "eval_duration": 1}
            ).encode()

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def _fake_urlopen(req, timeout=None):
        seen["payload"] = json.loads(req.data.decode())
        return _Resp()

    monkeypatch.setattr(probe.urllib.request, "urlopen", _fake_urlopen)

    for name, text in probe.PROMPT_VARIANTS.items():
        probe.run_case("m", _case(), {}, system=text)
        msgs = seen["payload"]["messages"]
        sysmsg = next(m["content"] for m in msgs if m["role"] == "system")
        assert sysmsg == text, f"variant {name} did not reach the wire"


def test_run_case_defaults_to_shipped_when_no_variant_given():
    """Back-compat: existing callers that never pass `system` keep the shipped
    prompt, so historical F2 numbers stay comparable."""
    import inspect

    sig = inspect.signature(probe.run_case)
    assert sig.parameters["system"].default is None
