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
    "docs_generated_current",
    "AK. docs/generated POC projections current (live unit count)",
    order=36,
)
def check_docs_generated_current() -> tuple[str, str, list[dict]]:
    """AK. The docs/generated/ POC renders must project the live unit count.

    `render_admin_guide` / `render_architecture_map` are refreshed by
    `python3 -m portal_wiki render --all`, **not** by `sync-config`, so they can
    silently freeze against a stale canonical set while every other gate stays
    green. Parse the `*Deterministic projection of N canonical units.*` line in
    every `docs/generated/*.md` and HARD-FAIL when N differs from the live
    `portal_wiki/canonical/*.md` count — staleness then fails the push-time
    `validate-system` hook instead of shipping a misleading projection.
    """
    import re

    live = len(list((REPO_ROOT / "portal_wiki" / "canonical").glob("*.md")))
    violations: list[str] = []
    for p in sorted((REPO_ROOT / "docs" / "generated").glob("*.md")):
        m = re.search(
            r"Deterministic projection of (\d+) canonical units", p.read_text(encoding="utf-8")
        )
        if m and int(m.group(1)) != live:
            violations.append(f"{p.name}: projects {m.group(1)} units, live is {live}")
    if violations:
        return (
            "FAIL",
            "; ".join(violations) + " — run `python3 -m portal_wiki render --all`",
            [
                {
                    "name": "docs/generated projections match live unit count",
                    "status": "FAIL",
                    "detail": "; ".join(violations),
                }
            ],
        )
    return (
        "PASS",
        f"docs/generated projections match the live canonical count ({live})",
        [
            {
                "name": "docs/generated projections match live unit count",
                "status": "PASS",
                "detail": f"all project {live} units",
            }
        ],
    )


@register(
    "wiki_facts_current",
    "AW. wiki facts current (fact-units only, P0 A4)",
    order=47,
)
def check_wiki_facts_current() -> tuple[str, str, list[dict]]:
    """AW. Wiki fact-units are current vs live config, and every KEEP-FACT
    generated doc block matches its unit's current body.

    DESIGN_WIKI_GENERATION_LOOP_V1.md F3 — the precise replacement for a
    coarse "a bound directory changed" doc-currency signal on the docs
    that now carry generated fact-blocks: read-only diff of each
    fact-unit's would-be body against what's stored, plus every
    `<!-- WIKI:GENERATED unit=... -->` block bound to a KEEP-FACT unit in
    the Tier-1 docs against its unit's current body. A mismatch here is
    precise ("unit says 138, doc block says 130"), not "a directory
    changed, re-stamp" — it means `sync-config` was not re-run after a
    source change before commit.

    P0 A4 scoped this check to the KEEP-FACT set (`claims.fact_unit_ids`) —
    released prose carries no AW currency requirement, editing it is not a
    `sync-config` event.

    Additionally enforces A1: a doc that has graduated to "migrated" status
    must have zero substantive remainder (no hand-edited facts outside
    WIKI:GENERATED or WIKI:HUMAN-OWNED fences). Edit the unit, not the shell.
    """
    from portal.platform.wiki.adapters.seed_facts import check_facts_current
    from portal.platform.wiki.claims import fact_unit_ids
    from portal.platform.wiki.migration import substantive_remainder
    from portal.platform.wiki.render import check_generated_blocks_current, render_report
    from portal.platform.wiki.store import load_all

    subs: list[dict] = []

    stale_units = check_facts_current()
    subs.append(
        {
            "name": "fact-units vs live config",
            "status": "PASS" if not stale_units else "FAIL",
            "detail": ", ".join(stale_units) if stale_units else "all current",
        }
    )

    fact_ids = fact_unit_ids(load_all())
    drift = check_generated_blocks_current(REPO_ROOT, unit_ids=fact_ids)
    subs.append(
        {
            "name": "generated doc blocks vs units (fact-units only, A4)",
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
    `last_generated_commit` pins axis, which proved nothing about whether a
    body was still true and only forced a two-commit re-pin dance. No pin
    axis to restore.
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


@register(
    "fleet_capability_coverage",
    "GR. fleet capability coverage (every MCP server has a capability unit)",
    order=72,
)
def check_fleet_capability_coverage() -> tuple[str, str, list[dict]]:
    """GR. Every mcp_fleet server has a gate-passing capability unit.

    Absolute, not a ratchet: a fleet entry with no `unit-capability-<id>`, or
    whose unit fails the authored-quality gate or lacks the capability shape
    (`## What` / `## Value`), fails outright. A new MCP server can no longer
    land undocumented.
    """
    import yaml

    from portal.platform.wiki.quality import assess
    from portal.platform.wiki.store import load_all

    fleet = [
        str(e["id"])
        for e in (
            yaml.safe_load((REPO_ROOT / "config" / "portal.yaml").read_text(encoding="utf-8")) or {}
        ).get("mcp_fleet")
        or []
    ]
    units = {u.id: u for u in load_all()}
    missing: list[str] = []
    bad_shape: list[str] = []
    for fid in fleet:
        uid = f"unit-capability-{fid.replace('_', '-')}"
        u = units.get(uid)
        if u is None:
            missing.append(fid)
            continue
        for sec in ("## What", "## Value"):
            if sec not in u.body:
                bad_shape.append(f"{uid} (missing {sec})")
    caps = [u for u in units.values() if u.id.startswith("unit-capability-")]
    report = assess(caps, REPO_ROOT)
    failing = sorted({i.unit_id for i in report.issues})

    problems = (
        [f"no capability unit: {m}" for m in missing]
        + [f"missing section: {b}" for b in bad_shape]
        + [f"fails quality gate: {f}" for f in failing]
    )
    if problems:
        return (
            "FAIL",
            "; ".join(problems),
            [
                {
                    "name": "every mcp_fleet id has a gate-passing capability unit",
                    "status": "FAIL",
                    "detail": "; ".join(problems),
                }
            ],
        )
    return (
        "PASS",
        f"all {len(fleet)} MCP servers have gate-passing capability units",
        [
            {
                "name": "every mcp_fleet id has a gate-passing capability unit",
                "status": "PASS",
                "detail": f"{len(caps)} capability units, all gate-passing",
            }
        ],
    )


@register(
    "module_state_claim_coverage",
    "GS. module-state claim coverage (every unit-module-* binds modules.enabled/disabled)",
    order=73,
)
def check_module_state_claim_coverage() -> tuple[str, str, list[dict]]:
    """GS. Every module unit binds its shipped state to a live probe.

    A `unit-module-*` that asserts an `enabled:` fence without a claim on
    `modules.enabled`/`modules.disabled` can drift silently; the fence is only
    honest when it is bound. Each unit must declare at least one claim whose
    probe is one of the two module-state probes.
    """
    from portal.platform.wiki.store import load_all

    module_units = [u for u in load_all() if u.id.startswith("unit-module-")]
    unbind = []
    for u in module_units:
        probes = {c.get("probe") for c in (u.claims or []) if isinstance(c, dict)}
        if not probes & {"modules.enabled", "modules.disabled"}:
            unbind.append(u.id)
    if unbind:
        return (
            "FAIL",
            f"{len(unbind)} module unit(s) without a module-state claim: {', '.join(unbind)}",
            [
                {
                    "name": "every unit-module-* binds modules.enabled/disabled",
                    "status": "FAIL",
                    "detail": ", ".join(unbind),
                }
            ],
        )
    return (
        "PASS",
        f"all {len(module_units)} module units bind their state to a live probe",
        [
            {
                "name": "every unit-module-* binds modules.enabled/disabled",
                "status": "PASS",
                "detail": f"{len(module_units)} bound",
            }
        ],
    )


@register(
    "launch_usage_complete",
    "GT. launch usage completeness (every case-arm subcommand in usage)",
    order=74,
)
def check_launch_usage_complete() -> tuple[str, str, list[dict]]:
    """GT. Every launch.sh subcommand is named in the usage string.

    The usage string is the operator's command index; a case-arm that is not in
    it is an undocumented command. Passes today and locks it in — adding a
    subcommand without updating the usage help fails the gate.
    """
    import re

    src = (REPO_ROOT / "launch.sh").read_text(encoding="utf-8")
    cmds = set(re.findall(r"^\s+([a-z][a-z0-9-]+)\)", src, re.M))
    m = re.search(r"Usage:.*?\]\"", src, re.S)
    usage = m.group(0) if m else ""
    missing = sorted(c for c in cmds if c not in usage)
    if missing:
        return (
            "FAIL",
            f"{len(missing)} launch.sh subcommand(s) missing from usage: {', '.join(missing)}",
            [
                {
                    "name": "every case-arm subcommand appears in usage",
                    "status": "FAIL",
                    "detail": ", ".join(missing),
                }
            ],
        )
    return (
        "PASS",
        f"all {len(cmds)} launch.sh subcommands are in the usage string",
        [
            {
                "name": "every case-arm subcommand appears in usage",
                "status": "PASS",
                "detail": f"{len(cmds)} documented",
            }
        ],
    )


@register(
    "env_comment_complete",
    "GU. env-var comment completeness (every var in .env.example is commented)",
    order=75,
)
def check_env_comment_complete() -> tuple[str, str, list[dict]]:
    """GU. Every .env.example var carries an inline or section comment.

    An uncommented var is a bare knob — an operator cannot tell what toggling it
    costs. The instrument mirrors the census: a var counts as commented when its
    own line carries a trailing `#` or the immediately preceding line is a
    comment. Secrets and knobs alike must be annotated.
    """
    import re

    env = (REPO_ROOT / ".env.example").read_text(encoding="utf-8").splitlines()
    undoc: list[str] = []
    for i, line in enumerate(env):
        m = re.match(r"^#?\s*([A-Z][A-Z0-9_]{2,})=", line)
        if not m:
            continue
        same = "#" in line.split("=", 1)[1] if "=" in line else False
        prev = env[i - 1].strip() if i else ""
        if not (same or (prev.startswith("#") and len(prev) > 3)):
            undoc.append(m.group(1))
    if undoc:
        return (
            "FAIL",
            f"{len(undoc)} uncommented env var(s): {', '.join(undoc)}",
            [
                {
                    "name": "every env var is annotated",
                    "status": "FAIL",
                    "detail": ", ".join(undoc),
                }
            ],
        )
    return (
        "PASS",
        f"all {_env_var_count(env)} env vars annotated",
        [
            {
                "name": "every env var is annotated",
                "status": "PASS",
                "detail": "all commented",
            }
        ],
    )


def _env_var_count(env: list[str]) -> int:
    """Count env-var lines in a .env.example-style file (allowing commented-out)."""
    import re

    return sum(1 for line in env if re.match(r"^#?\s*[A-Z][A-Z0-9_]{2,}=", line))


@register(
    "config_index_complete",
    "GV. config-index completeness (every config/*.yaml named in unit-fact-config-index)",
    order=76,
)
def check_config_index_complete() -> tuple[str, str, list[dict]]:
    """GV. Every config/*.yaml is named in unit-fact-config-index.

    A new config file that is not indexed is a config surface an operator
    cannot discover from the wiki. Absolute: the index unit must name every
    live file in the config directory.
    """
    from portal.platform.wiki.store import load_unit

    unit = load_unit("unit-fact-config-index")
    body = unit.body if unit else ""
    missing = [f.name for f in sorted((REPO_ROOT / "config").glob("*.yaml")) if f.name not in body]
    if missing:
        return (
            "FAIL",
            f"{len(missing)} config file(s) not in unit-fact-config-index: {', '.join(missing)}",
            [
                {
                    "name": "every config/*.yaml is indexed",
                    "status": "FAIL",
                    "detail": ", ".join(missing),
                }
            ],
        )
    return (
        "PASS",
        f"all {len(list((REPO_ROOT / 'config').glob('*.yaml')))} config files are indexed",
        [
            {
                "name": "every config/*.yaml is indexed",
                "status": "PASS",
                "detail": "index complete",
            }
        ],
    )


@register(
    "dockerfile_index_complete",
    "GW. dockerfile-index completeness (every Dockerfile* named in unit-fact-dockerfile-index)",
    order=77,
)
def check_dockerfile_index_complete() -> tuple[str, str, list[dict]]:
    """GW. Every Dockerfile* is named in unit-fact-dockerfile-index.

    A new image with no index entry is an undocumented build surface. Absolute:
    the index unit must name every live Dockerfile in the repo root.
    """
    from portal.platform.wiki.store import load_unit

    unit = load_unit("unit-fact-dockerfile-index")
    body = unit.body if unit else ""
    missing = [f.name for f in sorted(REPO_ROOT.glob("Dockerfile*")) if f.name not in body]
    if missing:
        return (
            "FAIL",
            f"{len(missing)} Dockerfile(s) not in unit-fact-dockerfile-index: {', '.join(missing)}",
            [
                {
                    "name": "every Dockerfile* is indexed",
                    "status": "FAIL",
                    "detail": ", ".join(missing),
                }
            ],
        )
    return (
        "PASS",
        f"all {len(list(REPO_ROOT.glob('Dockerfile*')))} Dockerfiles are indexed",
        [
            {
                "name": "every Dockerfile* is indexed",
                "status": "PASS",
                "detail": "index complete",
            }
        ],
    )


@register(
    "no_generic_mcp_surfaces",
    "GX. no generic-bucket capability files (no *_mcp surface maps to unit-fact-tool-registry)",
    order=78,
)
def check_no_generic_mcp_surfaces() -> tuple[str, str, list[dict]]:
    """GX. Capability-bearing MCP files are not covered by the flat tool index.

    `unit-fact-tool-registry` is the flat tool roster; it documents *that* a
    tool exists, not *what the server does*. A `*_mcp.py` surface mapped to it
    is the generic-bucket loophole this check closes — capability code must be
    covered by a real capability unit.
    """
    import yaml

    data = (
        yaml.safe_load((REPO_ROOT / "config" / "spine_surfaces.yaml").read_text(encoding="utf-8"))
        or {}
    )
    surfaces = data.get("surfaces") or []
    bad = [
        str(s.get("name"))
        for s in surfaces
        if "_mcp" in str(s.get("name")) and s.get("unit") == "unit-fact-tool-registry"
    ]
    if bad:
        return (
            "FAIL",
            f"{len(bad)} *_mcp surface(s) still on the generic bucket: {', '.join(bad)}",
            [
                {
                    "name": "no *_mcp surface maps to unit-fact-tool-registry",
                    "status": "FAIL",
                    "detail": ", ".join(bad),
                }
            ],
        )
    return (
        "PASS",
        "no *_mcp surface maps to unit-fact-tool-registry",
        [
            {
                "name": "no *_mcp surface maps to unit-fact-tool-registry",
                "status": "PASS",
                "detail": "all MCP surfaces covered by capability units",
            }
        ],
    )
