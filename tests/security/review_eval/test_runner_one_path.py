"""The harness may reach the product only through the public reviewer service."""

from __future__ import annotations

from pathlib import Path

from portal.modules.security.core.review_eval import guards

RUNNER = Path(__file__).resolve().parents[3] / "scripts" / "review_eval_run.py"
ALLOWED_IMPORTS = (
    "portal.modules.security.core.review.service",
    "portal.modules.security.core.review.contracts",
    "portal.modules.security.core.review.window",
    "portal.modules.security.core.review.embedding",
    "portal.modules.security.core.review.reference",
    "portal.modules.security.core.review_eval",
)


def test_runner_imports_only_public_product_adapters_and_scorer_plane() -> None:
    source = RUNNER.read_text(encoding="utf-8")
    assert guards.disallowed_imports(source, allowed_prefixes=ALLOWED_IMPORTS) == []
    assert "service.run_review" in source


def test_runner_import_guard_catches_seeded_product_escape() -> None:
    violation = "from portal.modules.security.core.bully import artifact_graph\n"
    assert guards.disallowed_imports(violation, allowed_prefixes=ALLOWED_IMPORTS) == [
        "portal.modules.security.core.bully"
    ]
