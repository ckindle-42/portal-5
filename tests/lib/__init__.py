"""Shared test library for Portal 5 acceptance + matrix harnesses.

Modules:
    compliance_assertions  — behavioral assertion functions (compliance scenarios)
    compliance_fixtures    — compliance scenario YAML loader and parameterizer
    coding_assertions      — behavioral assertion functions (coding scenarios)
    coding_fixtures        — coding scenario loader and parameterizer

Both are pure-Python with no Docker / network dependencies. Can be unit-tested
without a live backend.
"""
