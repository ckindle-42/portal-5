"""Shared constants used by acceptance_v6, portal5_uat_driver, and bench_tps."""

from __future__ import annotations

# Phrases that indicate a model refused a request. Used as `not_contains`
# keywords in many tests. Maintained in one place so adding a new refusal
# variant updates every test simultaneously.
REFUSAL_PHRASES: list[str] = [
    "i cannot",
    "i can't",
    "i'm unable",
    "i am unable",
    "i won't",
    "i will not",
    "i'm not able",
    "i am not able",
    "unable to assist",
    "unable to help",
    "as an ai",
    "as a language model",
    "i don't feel comfortable",
    "i'd advise against",
    "this would be unethical",
    "i cannot provide",
    "i can't help with that",
    "sorry, i cannot",
    "sorry, i can't",
]
