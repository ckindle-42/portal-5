"""Wiki-family checks: core backbone, fact currency, spine coverage/drift, and
archived-unit reachability."""

from __future__ import annotations

from pathlib import Path

from ._shared import REPO_ROOT
from .registry import register


@register("wiki_core", "AJ. wiki core backbone", order=35)
def check_wiki_core() -> tuple[str, str, list[dict]]:
    """AJ. Wiki core backbone — schema + provenance + integrity + import-clean.

    Verifies:
    - KnowledgeUnit schema works (mandatory provenance)
    - Core has zero Portal-specific imports (extraction guarantee)
    - MCP tools (search, get_unit, explain) functional
    """
    subs: list[dict] = []

    # Check 1: schema + mandatory provenance
    try:
        from portal.platform.wiki.schema import KnowledgeUnit, SourceRef

        # Must reject no-source unit
        rejected = False
        try:
            KnowledgeUnit(id="test", kind="what", title="t", sources=[])
        except ValueError:
            rejected = True
        assert rejected, "No-source unit not rejected"

        # Must accept valid unit
        unit = KnowledgeUnit(
            id="test-unit",
            kind="mixed",
            title="Test",
            sources=[SourceRef(type="code", path="test.py")],
        )
        assert unit.content_hash()
        subs.append({"name": "schema + provenance", "status": "PASS", "detail": ""})
    except Exception as e:
        subs.append({"name": "schema + provenance", "status": "FAIL", "detail": str(e)})
        return "FAIL", f"wiki schema failed: {e}", subs

    # Check 2: canonical body + repository-local provenance integrity.
    try:
        from portal.platform.wiki.audit import audit_units

        integrity_issues = audit_units(REPO_ROOT)
        assert not integrity_issues, "; ".join(
            (
                f"{issue.unit_id}: {issue.code}"
                + (f" ({issue.source_path})" if issue.source_path else "")
            )
            for issue in integrity_issues[:10]
        )
        subs.append(
            {
                "name": "canonical integrity",
                "status": "PASS",
                "detail": "no truncation artifacts or unresolved local provenance",
            }
        )
    except Exception as e:
        subs.append({"name": "canonical integrity", "status": "FAIL", "detail": str(e)})
        return "FAIL", f"canonical integrity failed: {e}", subs

    # Check 3: core import-clean
    try:
        import glob as glob_mod

        bad = []
        for f in glob_mod.glob("portal/platform/wiki/*.py"):
            content = Path(f).read_text(encoding="utf-8")
            for forbidden in ["portal_pipeline", "portal.platform.inference", "bench_security"]:
                if forbidden in content:
                    bad.append(f)
        assert bad == [], f"Core has Portal imports: {bad}"
        subs.append({"name": "core import-clean", "status": "PASS", "detail": ""})
    except Exception as e:
        subs.append({"name": "core import-clean", "status": "FAIL", "detail": str(e)})
        return "FAIL", f"core import-clean failed: {e}", subs

    # Check 4: MCP tools importable
    try:
        from portal_wiki.mcp import wiki_explain, wiki_get_unit, wiki_search  # noqa: F401

        subs.append({"name": "MCP tools importable", "status": "PASS", "detail": ""})
    except Exception as e:
        subs.append({"name": "MCP tools importable", "status": "FAIL", "detail": str(e)})
        return "FAIL", f"MCP tools import failed: {e}", subs

    return (
        "PASS",
        "schema validates; canonical integrity clean; core import-clean; MCP tools functional",
        subs,
    )


@register(
    "wiki_facts_current", "AW. wiki facts current (fact-units + generated doc blocks)", order=47
)
def check_wiki_facts_current() -> tuple[str, str, list[dict]]:
    """AW. Wiki fact-units are current vs live config, generated doc
    blocks match their units, and migrated docs have no un-fenced substance.

    DESIGN_WIKI_GENERATION_LOOP_V1.md F3 — the precise replacement for a
    coarse "a bound directory changed" doc-currency signal on the docs
    that now carry generated fact-blocks: read-only diff of each
    fact-unit's would-be body against what's stored, plus every
    `<!-- WIKI:GENERATED unit=... -->` block in the Tier-1 docs against
    its unit's current body. A mismatch here is precise ("unit says 138,
    doc block says 130"), not "a directory changed, re-stamp" — it means
    `sync-config` was not re-run after a source change before commit.

    Additionally enforces A1: a doc that has graduated to "migrated" status
    must have zero substantive remainder (no hand-edited facts outside
    WIKI:GENERATED or WIKI:HUMAN-OWNED fences). Edit the unit, not the shell.
    """
    from portal.platform.wiki.adapters.seed_facts import check_facts_current
    from portal.platform.wiki.migration import substantive_remainder
    from portal.platform.wiki.render import check_generated_blocks_current, render_report

    subs: list[dict] = []

    stale_units = check_facts_current()
    subs.append(
        {
            "name": "fact-units vs live config",
            "status": "PASS" if not stale_units else "FAIL",
            "detail": ", ".join(stale_units) if stale_units else "all current",
        }
    )

    drift = check_generated_blocks_current(REPO_ROOT)
    subs.append(
        {
            "name": "generated doc blocks vs units",
            "status": "PASS" if not drift else "FAIL",
            "detail": "; ".join(drift) if drift else "all match",
        }
    )

    # A1 enforcement: a migrated doc must have zero substantive remainder.
    # If someone hand-edits a migrated doc's meat (outside fences), catch it.
    report = render_report(REPO_ROOT)
    violations: list[str] = []
    for rel in report["migrated"]:
        p = REPO_ROOT / rel
        if p.exists():
            remainder = substantive_remainder(p.read_text(encoding="utf-8"))
            if remainder:
                violations.append(rel)
    subs.append(
        {
            "name": "migrated docs have no un-fenced substance",
            "status": "PASS" if not violations else "FAIL",
            "detail": (
                "; ".join(f"{v}: hand-edited substance outside fences" for v in violations)
                if violations
                else "all clean"
            ),
        }
    )

    # V2 enforcement: HUMAN-OWNED fences must be reasoned and bounded.
    from portal.platform.wiki.migration import human_owned_reasons
    from portal.platform.wiki.render import TIER1_DOCS

    fence_violations: list[str] = []
    for rel in TIER1_DOCS:
        p = REPO_ROOT / rel
        if not p.exists():
            continue
        text = p.read_text(encoding="utf-8")
        reasons = human_owned_reasons(text)
        if any(r == "[MISSING]" for r in reasons):
            fence_violations.append(f"{rel}: unreasoned HUMAN-OWNED fence")
    for rel in report.get("gamed", []):
        fence_violations.append(f"{rel}: gamed (fence-everything, not real migration)")
    subs.append(
        {
            "name": "HUMAN-OWNED fences are reasoned + bounded",
            "status": "PASS" if not fence_violations else "FAIL",
            "detail": "; ".join(fence_violations)
            if fence_violations
            else "all reasoned and bounded",
        }
    )

    if stale_units or drift or violations or fence_violations:
        detail = (
            f"{len(stale_units)} fact-unit(s) stale, {len(drift)} doc block(s) drifted, "
            f"{len(violations)} migrated doc(s) with un-fenced substance, "
            f"{len(fence_violations)} fence violation(s) — run sync-config / edit units"
        )
        return ("FAIL", detail, subs)
    return (
        "PASS",
        "fact-units current, all generated blocks match, migrated docs clean, fences reasoned",
        subs,
    )


@register(
    "spine_code_coverage",
    "BR. spine code coverage ratchet (new code must carry a covering unit)",
    order=68,
)
def check_spine_code_coverage() -> tuple[str, str, list[dict]]:
    """BR. Manifest-driven spine coverage: surfaces documented, files covered.

    The per-file era ended in TASK_PORTAL_SIMPLIFY_V1 Phase R3. Before it, the
    coverage gate walked the filesystem and required a hand-authored unit per
    eligible `.py` file — which set knowledge granularity by file, not by
    subsystem, and made documentation mass grow in lockstep with code mass
    forever. The regrain collapsed ~570 per-file mirrors into ~30 subsystem
    surfaces, and coverage now means something narrower but stronger:

    Part 1 — every declared surface in `config/spine_surfaces.yaml` has a
    covering unit that exists, passes the quality gate, and cites paths
    matching the surface's globs.
    Part 2 — every eligible `.py` file falls under some declared surface glob.
    New code inside a documented surface costs nothing; new code outside one
    must force a manifest entry — a deliberate act with a named owner. Code can
    still never arrive silently undocumented; it just no longer costs a
    hand-authored unit per file. The wiki engine (`portal/platform/wiki/`)
    stays per-file as the extraction-guarantee boundary (check AJ), so a new
    file there must be deliberately registered.
    """
    from portal.platform.wiki.coverage import (
        generate_surface_manifest,
        load_surface_manifest,
        surface_manifest_uncovered,
    )

    part1, part2 = surface_manifest_uncovered(REPO_ROOT)

    # Manifest freshness: the committed manifest must equal a fresh generation
    # from the live unit set, or it has silently drifted from the landed
    # boundaries (mirror of the sync-config idempotence guard for this file).
    committed = load_surface_manifest(REPO_ROOT)
    fresh = generate_surface_manifest(REPO_ROOT)
    manifest_drifted = _surface_manifests_differ(committed, fresh)

    subs = [
        {
            "name": "every declared surface has a covering unit",
            "status": "PASS" if not part1 else "FAIL",
            "detail": (
                f"{len(committed)} declared surface(s) documented by a "
                "gate-passing unit citing their globs"
                if not part1
                else f"{len(part1)} surface(s) without a valid covering unit"
            ),
        },
        {
            "name": "every eligible file falls under a declared surface",
            "status": "PASS" if not part2 else "FAIL",
            "detail": (
                "every eligible .py file matched by a declared surface glob"
                if not part2
                else f"{len(part2)} eligible file(s) under no declared surface: "
                f"{', '.join(part2[:6])}"
            ),
        },
        {
            "name": "manifest is current with the landed boundaries",
            "status": "PASS" if not manifest_drifted else "FAIL",
            "detail": (
                "config/spine_surfaces.yaml matches a fresh generation"
                if not manifest_drifted
                else "config/spine_surfaces.yaml is stale — re-run "
                "`python3 -m portal.platform.wiki.coverage --write-manifest`"
            ),
        },
    ]
    if part1 or part2 or manifest_drifted:
        parts = []
        if part1:
            parts.append(f"{len(part1)} surface(s) without a valid covering unit")
        if part2:
            parts.append(f"{len(part2)} eligible file(s) under no declared surface")
        if manifest_drifted:
            parts.append("manifest is stale")
        return ("FAIL", "; ".join(parts), subs)
    return ("PASS", "manifest coverage 100% — every surface documented, every file covered", subs)


def _surface_manifests_differ(committed: list[dict], fresh: list[dict]) -> bool:
    """Compare two surface manifests by name -> (globs, unit), order-insensitive."""
    key = lambda s: (s["name"], tuple(s["globs"]), s["unit"])  # noqa: E731
    return sorted(map(key, committed)) != sorted(map(key, fresh))


@register(
    "spine_drift",
    "BS. spine drift census (claims hold + doc refs exist)",
    order=69,
)
def check_spine_drift() -> tuple[str, str, list[dict]]:
    """BS. The spine's content is true, not merely self-consistent.

    AW proves a generated block equals its unit's body; BR proves a new code
    surface is cited by some unit. Neither asks whether the body is *correct*.
    At the commit this gate landed, both were green while README asserted 60
    benchmark workspaces against a live 65 and 22 MCP servers against a live 21.

    Two axes, both HARD FAIL, neither baselinable:
      claims     — declared unit assertions vs live probes. A unit that
                   states a wrong number is a bug.
      doc refs   — repo-relative paths named in Tier-1 docs must exist.

    P0 A1 deleted the third axis this check used to carry — the
    `last_generated_commit` pins axis. 461 of ~720 units were pinned to a SHA
    absent from all history, so a pin resolving proved nothing about whether
    the body was still true; it only forced a two-commit re-pin dance on
    every fact edit. `claims` is the axis that actually catches a wrong
    number; there is no pin axis to restore.
    """
    from portal.platform.wiki.claims import claim_count, evaluate_claims
    from portal.platform.wiki.drift import broken_path_refs
    from portal.platform.wiki.store import load_all

    units = load_all()
    violations = evaluate_claims(units, REPO_ROOT)
    refs = broken_path_refs(REPO_ROOT)

    subs: list[dict] = [
        {
            "name": "declared claims hold against live probes",
            "status": "PASS" if not violations else "FAIL",
            "detail": (
                f"{claim_count(units)} claim(s) declared, all hold"
                if not violations
                else "; ".join(str(v) for v in violations[:8])
            ),
        },
        {
            "name": "no broken doc reference",
            "status": "PASS" if not refs else "FAIL",
            "detail": (
                "every repo path referenced in Tier-1 docs exists"
                if not refs
                else f"{len(refs)} dead refs: {', '.join(refs[:6])}"
            ),
        },
    ]

    hard = bool(violations) or bool(refs)
    if hard:
        return (
            "FAIL",
            f"{len(violations)} claim violation(s), {len(refs)} dead doc ref(s)",
            subs,
        )
    return (
        "PASS",
        f"{claim_count(units)} claim(s) hold; no dead refs",
        subs,
    )


@register(
    "archive_reachability",
    "BT. archived units unreachable (no live link or doc block references)",
    order=70,
)
def check_archive_reachability() -> tuple[str, str, list[dict]]:
    """BT. Archived units stay out of the working set.

    Archiving moves a unit's file to `portal_wiki/archive/`; the archive command
    refuses when a live doc block references the id, a live unit links it, or a
    live code source determines it. This check proves the invariant holds across
    the store as a whole, so an archived id can never be re-reached through a
    stray reference.
    """
    from portal.platform.wiki.archive import archive_reachability

    violations = archive_reachability(REPO_ROOT)
    if violations:
        return (
            "FAIL",
            f"{len(violations)} archived unit(s) reachable from the live store",
            [
                {
                    "name": "archived units unreachable",
                    "status": "FAIL",
                    "detail": "; ".join(violations[:6]),
                }
            ],
        )
    return (
        "PASS",
        "no live unit or doc block references an archived unit",
        [{"name": "archived units unreachable", "status": "PASS", "detail": "all clean"}],
    )
