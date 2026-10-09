"""Invariants that make whole classes of past defects structurally loud.

Each test names the class it retires. They are also run against SEEDED violations, because a
guard that has never been seen to fail is the same kind of instrument this program exists to
stop trusting."""

from __future__ import annotations

from pathlib import Path

from portal.modules.security.core.review import constants
from portal.modules.security.core.review_eval import guards

REVIEW_DIR = Path(__file__).parents[3] / "portal" / "modules" / "security" / "core" / "review"
MODULES = sorted(p for p in REVIEW_DIR.glob("*.py") if p.stem not in {"__init__", "constants"})
ALLOWED_IMPORTS = (
    "portal.modules.security.core.review",
    "portal.modules.security.core.bully",
    "portal.platform",
)
#: The only literal tables the product may carry, each with the reason it is not a definition
#: matcher. A new entry needs a reason a reviewer would accept; "it was easier" is the failure.
ALLOWED_TABLES = {
    ("wall", "LABEL_IDENTIFIERS"): "deny-list for the truth wall: names what must NOT be said",
}


def test_every_number_in_the_product_is_registered_with_a_kind() -> None:
    """Retires: constants that decide answers (caps, gates, weights, identity thresholds)."""
    found: set[str] = set()
    for path in MODULES:
        found.update(guards.numeric_constants(path.read_text(encoding="utf-8"), module=path.stem))
    assert sorted(found - set(constants.REGISTRY)) == [], (
        "unregistered numbers: classify as budget/bound/protocol"
    )
    installed = {path.stem for path in MODULES}
    stale = {k for k in constants.REGISTRY if k.split(".")[0] in installed} - found
    assert sorted(stale) == [], "registry entries for numbers that no longer exist"
    for name, (kind, why) in constants.REGISTRY.items():
        assert kind in constants.ALLOWED_KINDS, f"{name}: {kind!r} is not an allowed kind"
        assert len(why.strip()) > 10, f"{name}: state what the number is for"


def test_the_product_carries_no_curated_tables() -> None:
    """Retires: definition-matcher creep (field-name tables, verb tables, sourcetype tables)."""
    found: dict[tuple[str, str], int] = {}
    for path in MODULES:
        for name, count in guards.literal_tables(path.read_text(encoding="utf-8")):
            if name != "__all__":
                found[(path.stem, name)] = count
    assert sorted(set(found) - set(ALLOWED_TABLES)) == [], "a literal table crept into the product"
    assert sorted(set(ALLOWED_TABLES) - set(found)) == [], (
        "allow-list entry for a table that is gone"
    )


def test_the_product_imports_only_the_engine_the_platform_and_itself() -> None:
    """Retires: the scorer plane, generators and the hunt loop leaking into the product."""
    for path in MODULES:
        bad = guards.disallowed_imports(
            path.read_text(encoding="utf-8"), allowed_prefixes=ALLOWED_IMPORTS
        )
        assert bad == [], f"{path.name} imports {bad}"


# ── the guards must be able to fail ──────────────────────────────────────────


def test_guards_catch_seeded_violations() -> None:
    constants_src = "THRESHOLD = 0.6\ndef f(x, cutoff=0.55, n=1):\n    return x\nclass C:\n    weight: float = 0.4\n"
    assert guards.numeric_constants(constants_src, module="m") == [
        "m.C.weight",
        "m.THRESHOLD",
        "m.f.cutoff",
    ]
    assert guards.numeric_constants("A = 0\nB = True\ndef g(x=1):\n    pass\n", module="m") == []

    table_src = (
        "TABLE = ('a', 'b', 'c', 'd', 'e', 'f', 'g', 'h', 'i', 'j')\nSMALL = (1, 2)\nM = {'k': 1}\n"
    )
    assert guards.literal_tables(table_src) == [("TABLE", 10)]
    assert guards.literal_tables(
        "X = frozenset({" + ",".join(str(i) for i in range(12)) + "})"
    ) == [("X", 12)]

    leak = "from portal.modules.security.core.review_eval import report\nimport json\n"
    assert guards.disallowed_imports(leak, allowed_prefixes=ALLOWED_IMPORTS) == [
        "portal.modules.security.core.review_eval"
    ]
    lazy = "def f():\n    from portal.modules.security.core.bully import orchestrator\n"
    assert guards.disallowed_imports(lazy, allowed_prefixes=("portal.platform",)) == [
        "portal.modules.security.core.bully"
    ]
