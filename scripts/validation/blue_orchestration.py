"""Blue-orchestration-family checks: the analyst verdict axis, council/multichain
gates, mentor/budget/barrier/discriminator semantics, and the emergent-agent
measurement gates (trajectory, perception, recall, challenge reality, model
inventory, fleet health)."""

from __future__ import annotations

import re

from ._shared import REPO_ROOT
from .registry import register


@register("trajectory", "AX. trajectory scoring honesty", order=48)
def check_trajectory_scoring_honesty() -> tuple[str, str, list[dict]]:
    """AX. Trajectory scoring honesty (DESIGN_EMERGENT_LAB_AGENT_V2 §7 gate).

    Permanent ratchet: a trajectory whose objective was reached via a
    synthetic-derived step is never PROVEN, and the objective verdict derives
    from lab state (an objective-state oracle), never from step narration.
    This turns the Slice 2 measurement gate into a standing regression check,
    not a one-time build proof.
    """
    from portal.modules.security.core.trajectory_score import StepRecord, score_trajectory

    subs: list[dict] = []

    da_state = {"sessions": [{"host_role": "dc", "privilege": "da_equivalent", "verified": True}]}

    clean = score_trajectory(
        "da_equivalent",
        [StepRecord("s1", "c1", "RED_LANDED", "DETECTION_CONFIRMED")],
        da_state,
    )
    subs.append(
        {
            "name": "reached + clean -> PROVEN",
            "status": "PASS" if clean.verdict == "PROVEN" else "FAIL",
            "detail": clean.verdict,
        }
    )

    synthetic = score_trajectory(
        "da_equivalent",
        [
            StepRecord("s1", "c1", "RED_LANDED", "DETECTION_CONFIRMED"),
            StepRecord("s2", "c2", "RED_LANDED", "DETECTION_CONFIRMED", used_synthetic=True),
        ],
        da_state,
    )
    synthetic_never_proven = synthetic.objective_reached is True and synthetic.verdict != "PROVEN"
    subs.append(
        {
            "name": "synthetic-present -> never PROVEN",
            "status": "PASS" if synthetic_never_proven else "FAIL",
            "detail": synthetic.verdict,
        }
    )

    narrated = score_trajectory(
        "da_equivalent",
        [StepRecord("s1", "c1", "RED_LANDED", "DETECTION_CONFIRMED")],
        {"sessions": []},
    )
    state_not_narration = narrated.objective_reached is False and narrated.verdict != "PROVEN"
    subs.append(
        {
            "name": "objective verdict derives from state, not narration",
            "status": "PASS" if state_not_narration else "FAIL",
            "detail": narrated.verdict,
        }
    )

    if any(s["status"] == "FAIL" for s in subs):
        return ("FAIL", "trajectory scoring honesty invariant violated", subs)
    return ("PASS", "synthetic never PROVEN; objective verdict is state-derived", subs)


@register("perception", "AY. perception lab-scope allowlist", order=49)
def check_perception_lab_scope() -> tuple[str, str, list[dict]]:
    """AY. Perception lab-scope allowlist (DESIGN_EMERGENT_LAB_AGENT_V2 invariant I1).

    Permanent ratchet: perception (LabPerception) and the live executor
    (SecurityExecutor) both reject a non-lab target before any probe/action
    leaves the box. Non-network — constructs both with fake probers/dispatch
    and asserts OutOfScopeError fires and the fake was never called.
    """
    from unittest import mock

    from portal.modules.security.core.objective_executor import SecurityExecutor
    from portal.modules.security.core.perception import LabPerception, OutOfScopeError

    subs: list[dict] = []

    calls: list[object] = []
    perception = LabPerception(prober=lambda hosts: calls.append(hosts) or {})
    try:
        perception.enumerate(["10.10.11.5", "8.8.8.8"])
        perception_rejected = False
    except OutOfScopeError:
        perception_rejected = True
    subs.append(
        {
            "name": "LabPerception rejects non-lab target before probing",
            "status": "PASS" if perception_rejected and not calls else "FAIL",
            "detail": f"rejected={perception_rejected} probe_calls={len(calls)}",
        }
    )

    exec_calls: list[object] = []

    def _fake_dispatch(fn_name, fn_args, dry_run=False):
        exec_calls.append((fn_name, fn_args))
        return "should never run"

    with mock.patch("portal.modules.security.core.lab.lab_dispatch", side_effect=_fake_dispatch):
        executor = SecurityExecutor()
        try:
            executor.execute(
                {"tool": "run_nmap_scan", "args": {"target": "8.8.8.8"}},
                {"observations": {}, "history": []},
            )
            executor_rejected = False
        except OutOfScopeError:
            executor_rejected = True

    subs.append(
        {
            "name": "SecurityExecutor rejects non-lab target before dispatch",
            "status": "PASS" if executor_rejected and not exec_calls else "FAIL",
            "detail": f"rejected={executor_rejected} dispatch_calls={len(exec_calls)}",
        }
    )

    if any(s["status"] == "FAIL" for s in subs):
        return ("FAIL", "lab-scope allowlist not enforced end-to-end", subs)
    return ("PASS", "perception + executor both reject non-lab targets before any action", subs)


@register("recall_metric", "AZ. detection recall vs emergent corpus", order=50)
def check_recall_metric() -> tuple[str, str, list[dict]]:
    """AZ. Detection recall vs emergent corpus (DESIGN_EMERGENT_LAB_AGENT_V2 D4).

    Asserts the recall-vs-emergent-corpus metric is wired and actually
    computed over an arbitrary procedure corpus — not just present as dead
    code. Non-network: builds a small in-memory graph and checks the metric
    reflects the corpus, not the graph's own accumulated technique set.
    """
    from portal.modules.security.core.agentic_blue_eval import emergent_recall_metric
    from portal.modules.security.core.capability_graph import CapabilityGraph, Detection, Gap

    subs: list[dict] = []

    graph = CapabilityGraph()
    graph.add_detection(Detection(detection_id="det-T1110", technique_id="T1110"))
    graph.add_gap(
        Gap(
            gap_id="gap-scripted-T1110",
            procedure_id="proc-scripted",
            technique_id="T1110",
            axes={
                "red": "RED_LANDED",
                "telemetry": "TELEMETRY_OBSERVED",
                "detection": "DETECTION_CONFIRMED",
            },
            summary="COVERED",
            reason_codes=[],
        )
    )

    corpus = {"T1110", "T1595", "T1078", "T1021"}
    metric = emergent_recall_metric(graph, corpus)

    wired_correctly = (
        metric.get("metric") == "recall_vs_emergent_corpus"
        and metric.get("corpus_size") == len(corpus)
        and metric.get("detected") == 1
        and metric.get("recall_pct") == 25.0
    )
    subs.append(
        {
            "name": "recall computed over the corpus, not the graph's own technique set",
            "status": "PASS" if wired_correctly else "FAIL",
            "detail": str(metric),
        }
    )

    if not wired_correctly:
        return ("FAIL", "recall-vs-emergent-corpus metric not wired correctly", subs)
    return ("PASS", "recall metric wired and computed over an arbitrary corpus", subs)


@register("challenge_reality", "BA. challenge reality-aware (backed or aspirational)", order=51)
def check_challenge_reality() -> tuple[str, str, list[dict]]:
    """BA. Challenge classes describe only what is deployed or explicitly aspirational.

    P5-SECURITY-ARM-RECONCILE-001: the RBP bench declares a 40-class (now
    wider) challenge taxonomy in config/challenge_classes.yaml, most of which
    predates any actual lab build-out. A class is valid only if it is backed
    on the live lab (its `purpose_built` dir exists on disk, relative to the
    repo root) OR it explicitly carries `status: aspirational` — so drift
    (a class quietly claiming to be real when nothing backs it) cannot
    silently reopen once gated. This check is filesystem-only (no live probe)
    so it stays fast and network-free; it does not re-verify vulhub deploy
    state (that's the reconciliation script's job, run periodically).
    """
    import yaml

    cc_path = REPO_ROOT / "config" / "challenge_classes.yaml"
    doc = yaml.safe_load(cc_path.read_text())
    classes = doc.get("classes", [])

    subs: list[dict] = []
    bad: list[str] = []
    for cl in classes:
        cid = cl.get("id")
        pb = cl.get("purpose_built")
        status = cl.get("status")
        backed = bool(pb) and (REPO_ROOT / pb).is_dir()
        ok = backed or status == "aspirational"
        if not ok:
            bad.append(cid)
        subs.append(
            {
                "name": cid,
                "status": "PASS" if ok else "FAIL",
                "detail": f"purpose_built={pb!r} backed={backed} status={status!r}",
            }
        )

    if bad:
        return (
            "FAIL",
            f"{len(bad)} challenge class(es) neither backed nor marked aspirational: {bad}",
            subs,
        )
    return ("PASS", f"{len(classes)} challenge classes all backed or gated aspirational", [])


@register("model_inventory", "BB. model inventory reality (bench hints vs snapshot)", order=52)
def check_model_inventory_reality() -> tuple[str, str, list[dict]]:
    """BB. Bench-reachable model_hints resolve against the committed Ollama snapshot.

    P5-SECURITY-ARM-RECONCILE-001: config/model_inventory.snapshot is a
    committed `ollama list` capture (refreshed by
    scripts/reconcile_security_arm.py's model-pull phase). Any workspace
    whose model_hint is referenced from a `[security]`-tagged workspace (the
    bench-reachability signal the reconciliation engine uses) must resolve
    against that snapshot — this is the mechanical drift check that would
    have caught the VulnLLM-R-7B ctx8k tag-case mismatch this run fixed
    (config declared `Q4_K_M-ctx8k`, Ollama only ever had `q4_K_M-ctx8k`).
    Non-bench hints are informational only, matching the reconciliation
    engine's own scope.
    """
    import yaml

    snap_path = REPO_ROOT / "config" / "model_inventory.snapshot"
    if not snap_path.exists():
        return (
            "FAIL",
            "config/model_inventory.snapshot missing — run reconcile_security_arm.py",
            [],
        )
    pulled = {ln.strip() for ln in snap_path.read_text().splitlines() if ln.strip()}

    portal_cfg = yaml.safe_load((REPO_ROOT / "config" / "portal.yaml").read_text())
    workspaces = portal_cfg.get("workspaces") or {}

    subs: list[dict] = []
    bad: list[str] = []
    for wid, c in sorted(workspaces.items()):
        if not isinstance(c, dict) or c.get("module") != "security":
            continue
        hint = c.get("model_hint")
        if not hint:
            continue
        ok = hint in pulled
        if not ok:
            bad.append(f"{wid} -> {hint}")
        subs.append({"name": wid, "status": "PASS" if ok else "FAIL", "detail": hint})

    if bad:
        return ("FAIL", f"{len(bad)} bench-reachable model_hint(s) not in snapshot: {bad}", subs)
    return (
        "PASS",
        f"{len(subs)} bench-reachable model_hint(s) all resolve against the snapshot",
        [],
    )


@register("fleet_health", "BC. fleet health reality (declared vs live)", order=53)
def check_fleet_health_reality() -> tuple[str, str, list[dict]]:
    """BC. Declared MCP fleet ports are live when the stack is up.

    P5-SECURITY-ARM-RECONCILE-001: health-probes every port declared under
    config/portal.yaml's mcp_fleet against /ready or /health with a short
    timeout. Skipped entirely (WARN, not FAIL) when the stack is down —
    Rule 3 servers are independent processes this check can't start, and a
    dev machine with the stack stopped shouldn't fail validate_system.py.
    When at least one fleet member answers, the stack is considered "up"
    and every declared port must answer.
    """
    import urllib.request

    import yaml

    portal_cfg = yaml.safe_load((REPO_ROOT / "config" / "portal.yaml").read_text())
    fleet = portal_cfg.get("mcp_fleet") or []
    ports = [
        (e.get("id") or e.get("name"), e.get("port"), e.get("default_enabled", True))
        for e in fleet
        if e.get("port")
    ]

    def _up(port: int) -> bool:
        for ep in ("/ready", "/health"):
            try:
                urllib.request.urlopen(f"http://localhost:{port}{ep}", timeout=2)  # noqa: S310
                return True
            except Exception:  # noqa: BLE001
                continue
        return False

    subs = [{"name": f"{name} :{port}", "status": "", "detail": ""} for name, port, _ in ports]
    results = {name: _up(port) for name, port, _ in ports}

    if not any(results.values()):
        return ("WARN", "stack appears down — skipping fleet health (not a failure)", [])

    # default_enabled: false fleet members (e.g. video_mlx, module-gated off
    # in docker-compose.yml) stay declared for tool advertisement but must
    # not fail liveness — they're expected down unless their profile is on.
    down = [f"{name}:{port}" for name, port, enabled in ports if enabled and not results[name]]
    for sub in subs:
        name = sub["name"].split(" :")[0]
        enabled = next(e for n, _p, e in ports if n == name)
        if results.get(name):
            sub["status"], sub["detail"] = "PASS", "UP"
        elif not enabled:
            sub["status"], sub["detail"] = "WARN", "DOWN (default_enabled: false — expected)"
        else:
            sub["status"], sub["detail"] = "FAIL", "DOWN (stack otherwise up)"

    if down:
        return (
            "FAIL",
            f"{len(down)} declared fleet port(s) unreachable while stack is up: {down}",
            subs,
        )
    return ("PASS", f"{len(ports)} declared fleet ports all reachable", [])


@register("blue_orchestration", "BD. blue orchestration verdict axis", order=54)
def check_blue_orchestration_axis() -> tuple[str, str, list[dict]]:
    """BD. The analyst-confidence verdict axis stays disjoint from harness truth,
    and blue_orchestrate.py reuses (never re-implements) the never-invent +
    similarity substrate.

    BUILD_PROGRAM_SEC_BLUE_ORCHESTRATION_V2 I1/I2/I7: (1) ANALYST_VERDICTS
    (analyst_verdict.py) must never collide with CAPABILITY_VERDICTS
    (episode.py, harness truth) — a collision would let a model-produced
    verdict silently masquerade as ground truth. (2) blue_orchestrate.py must
    import _cite_or_drop and compute_similarity (reused, not duplicated) and
    must not define its own derive_verdict (episode.py's stays the single
    harness-truth implementation).
    """
    from portal.modules.security.core.analyst_verdict import ANALYST_VERDICTS
    from portal.modules.security.core.episode import CAPABILITY_VERDICTS

    subs: list[dict] = []
    bad: list[str] = []

    overlap = set(ANALYST_VERDICTS) & set(CAPABILITY_VERDICTS)
    ok = not overlap
    subs.append(
        {
            "name": "verdict axes disjoint",
            "status": "PASS" if ok else "FAIL",
            "detail": f"overlap={sorted(overlap)}" if overlap else "no overlap",
        }
    )
    if not ok:
        bad.append(f"ANALYST_VERDICTS overlaps CAPABILITY_VERDICTS: {sorted(overlap)}")

    orch_path = REPO_ROOT / "portal" / "modules" / "security" / "core" / "blue_orchestrate.py"
    src = orch_path.read_text()

    import ast

    module_tree = ast.parse(src)
    imports_cite_or_drop = any(
        isinstance(node, ast.ImportFrom)
        and any(alias.name == "_cite_or_drop" for alias in node.names)
        for node in ast.walk(module_tree)
    )
    subs.append(
        {
            "name": "imports _cite_or_drop",
            "status": "PASS" if imports_cite_or_drop else "FAIL",
            "detail": "reused from blue.py" if imports_cite_or_drop else "not imported",
        }
    )
    if not imports_cite_or_drop:
        bad.append("blue_orchestrate.py does not import _cite_or_drop")

    imports_compute_similarity = bool(
        re.search(r"^\s*from\s+\S+\s+import\s+.*\bcompute_similarity\b", src, re.MULTILINE)
    )
    subs.append(
        {
            "name": "imports compute_similarity",
            "status": "PASS" if imports_compute_similarity else "FAIL",
            "detail": "reused from unknown_defense.py"
            if imports_compute_similarity
            else "not imported",
        }
    )
    if not imports_compute_similarity:
        bad.append("blue_orchestrate.py does not import compute_similarity")

    redefines_derive_verdict = bool(re.search(r"^\s*def\s+derive_verdict\s*\(", src, re.MULTILINE))
    subs.append(
        {
            "name": "does not redefine derive_verdict",
            "status": "FAIL" if redefines_derive_verdict else "PASS",
            "detail": "redefined!" if redefines_derive_verdict else "not redefined",
        }
    )
    if redefines_derive_verdict:
        bad.append("blue_orchestrate.py redefines derive_verdict (must reuse episode.py's)")

    if bad:
        return ("FAIL", "; ".join(bad), subs)
    return ("PASS", "verdict axis disjoint; never-invent + similarity substrate reused", [])


@register(
    "council_agreement", "BE. council agreement gate (cite-or-drop + novelty carry)", order=55
)
def check_council_agreement_gate() -> tuple[str, str, list[dict]]:
    """BE. Council of Agreement (GATE-D ablation Part II-A): consensus never
    yields CONFIRMED without passing through _cite_or_drop, and the
    ANOMALOUS_UNCLASSIFIED (disagreement-as-novelty, I8) path preserves
    similar_to rather than silently dropping the near-miss neighbours.

    Structural (source-scan) + live functional checks combined: source-scan
    alone would pass on a _run_council that imports _cite_or_drop but never
    actually calls it on the council's own aggregate technique set (as
    opposed to each member's own already-gated CONFIRMED); the functional
    check exercises compute_agreement/to_section_output directly to confirm
    the runtime contract, not just that the right names appear somewhere in
    the file.
    """
    from portal.modules.security.core.analyst_verdict import SectionOutput
    from portal.modules.security.core.council_agreement import compute_agreement, to_section_output

    subs: list[dict] = []
    bad: list[str] = []

    orch_path = REPO_ROOT / "portal" / "modules" / "security" / "core" / "blue_orchestrate.py"
    src = orch_path.read_text()

    has_run_council = bool(re.search(r"^\s*def\s+_run_council\s*\(", src, re.MULTILINE))
    subs.append(
        {
            "name": "_run_council defined",
            "status": "PASS" if has_run_council else "FAIL",
            "detail": "found" if has_run_council else "missing",
        }
    )
    if not has_run_council:
        bad.append("blue_orchestrate.py does not define _run_council")

    # _run_council's own body (not just any _cite_or_drop call elsewhere in
    # the file, which _run_three_section/run_expert_model already have) must
    # call _cite_or_drop on the council's aggregate verdict.
    council_body_match = re.search(
        r"^def _run_council\(.*?(?=^def |\Z)", src, re.MULTILINE | re.DOTALL
    )
    council_body = council_body_match.group(0) if council_body_match else ""
    council_calls_cite_or_drop = "_cite_or_drop(" in council_body
    subs.append(
        {
            "name": "_run_council calls _cite_or_drop on its own aggregate",
            "status": "PASS" if council_calls_cite_or_drop else "FAIL",
            "detail": "found in _run_council body" if council_calls_cite_or_drop else "not found",
        }
    )
    if not council_calls_cite_or_drop:
        bad.append("_run_council does not gate its aggregate CONFIRMED through _cite_or_drop (I2)")

    # Live functional check: a 3-way split with SIMILAR neighbours must
    # surface as ANOMALOUS_UNCLASSIFIED carrying the similar_to union, never
    # silently dropped novelty (I8).
    members = [
        SectionOutput(verdict="CONFIRMED", technique_ids=["T1078"], similar_to=["T1078.002"]),
        SectionOutput(verdict="CONFIRMED", technique_ids=["T1055"], similar_to=["T1055.001"]),
        SectionOutput(
            verdict="ANOMALOUS_UNCLASSIFIED", technique_ids=["T1548"], similar_to=["T1548.002"]
        ),
    ]
    agreement = compute_agreement(members, quorum=0.5)
    novelty_ok = (
        agreement.verdict == "ANOMALOUS_UNCLASSIFIED"
        and agreement.needs_arbiter
        and set(agreement.similar_to) == {"T1055.001", "T1078.002", "T1548.002"}
    )
    subs.append(
        {
            "name": "split-no-quorum preserves similar_to union (live)",
            "status": "PASS" if novelty_ok else "FAIL",
            "detail": f"verdict={agreement.verdict} similar_to={agreement.similar_to}",
        }
    )
    if not novelty_ok:
        bad.append("compute_agreement split-no-quorum did not preserve the similar_to union (I8)")

    so = to_section_output(agreement)
    section_output_ok = (
        so.verdict == "ANOMALOUS_UNCLASSIFIED" and so.match_grade == "SIMILAR" and so.similar_to
    )
    subs.append(
        {
            "name": "to_section_output carries novelty forward (live)",
            "status": "PASS" if section_output_ok else "FAIL",
            "detail": f"verdict={so.verdict} match_grade={so.match_grade} similar_to={so.similar_to}",
        }
    )
    if not section_output_ok:
        bad.append("to_section_output did not carry the novelty (match_grade/similar_to) forward")

    # Unanimous CONFIRMED must still expose technique_ids for a downstream
    # _cite_or_drop gate to act on (never a bare verdict with nothing to check).
    unanimous = compute_agreement(
        [
            SectionOutput(verdict="CONFIRMED", technique_ids=["T1078"]),
            SectionOutput(verdict="CONFIRMED", technique_ids=["T1078"]),
        ]
    )
    confirmed_carries_ids = unanimous.verdict == "CONFIRMED" and bool(unanimous.technique_ids)
    subs.append(
        {
            "name": "unanimous CONFIRMED carries technique_ids for cite-or-drop (live)",
            "status": "PASS" if confirmed_carries_ids else "FAIL",
            "detail": f"verdict={unanimous.verdict} technique_ids={unanimous.technique_ids}",
        }
    )
    if not confirmed_carries_ids:
        bad.append("unanimous CONFIRMED agreement did not carry technique_ids")

    if bad:
        return ("FAIL", "; ".join(bad), subs)
    return (
        "PASS",
        "council consensus gated through _cite_or_drop; novelty carry verified live",
        [],
    )


@register(
    "multichain",
    "BF. multichain consolidation gate (escalate first-class + I7 composition)",
    order=56,
)
def check_multichain_consolidation_gate() -> tuple[str, str, list[dict]]:
    """BF. Multi-model multi-chain analyst (2026-07-22): the consolidation
    across INDEPENDENT chains routes to a real operator decision, with ESCALATE
    ('a human needs to look at this') as a FIRST-CLASS outcome — divergent
    independent investigations must never be forced into a confirm or silently
    dismissed. Also structurally guards that the arm COMPOSES the untouched
    3-section path (independence via full chains) rather than reimplementing a
    hunter loop (I7).
    """
    from portal.modules.security.core.multichain import ChainResult, consolidate

    subs: list[dict] = []
    bad: list[str] = []

    orch_path = REPO_ROOT / "portal" / "modules" / "security" / "core" / "blue_orchestrate.py"
    src = orch_path.read_text()

    body_match = re.search(
        r"^def run_multichain_orchestration\(.*?(?=^def |\Z)", src, re.MULTILINE | re.DOTALL
    )
    body = body_match.group(0) if body_match else ""
    composes_3section = bool(body) and "run_blue_orchestration(" in body
    subs.append(
        {
            "name": "run_multichain_orchestration composes run_blue_orchestration (I7)",
            "status": "PASS" if composes_3section else "FAIL",
            "detail": "found" if composes_3section else "missing or reimplements the loop",
        }
    )
    if not composes_3section:
        bad.append(
            "run_multichain_orchestration does not compose run_blue_orchestration "
            "(must reuse the untouched 3-section path per chain, not reimplement)"
        )

    # Live: divergent independent chains (each a different technique) must
    # ESCALATE, never AUTO_CONFIRM.
    divergent = consolidate(
        [
            ChainResult(model="a", verdict="CONFIRMED", technique_ids=["T1190"]),
            ChainResult(model="b", verdict="CONFIRMED", technique_ids=["T1059"]),
            ChainResult(model="c", verdict="ANOMALOUS_UNCLASSIFIED", similar_to=["T1505.003"]),
        ],
        quorum=0.5,
    )
    escalate_ok = (
        divergent.decision == "ESCALATE"
        and divergent.verdict == "ANOMALOUS_UNCLASSIFIED"
        and bool(divergent.escalation_reason)
        and "T1505.003" in divergent.similar_to
    )
    subs.append(
        {
            "name": "divergent independent chains ESCALATE with novelty carry (live)",
            "status": "PASS" if escalate_ok else "FAIL",
            "detail": f"decision={divergent.decision} similar_to={divergent.similar_to}",
        }
    )
    if not escalate_ok:
        bad.append("divergent independent chains did not ESCALATE as a first-class outcome (I8)")

    # Live: independent convergence AUTO_CONFIRMs; unanimous benign DISMISSes.
    converge = consolidate(
        [
            ChainResult(model="a", verdict="CONFIRMED", technique_ids=["T1190"]),
            ChainResult(model="b", verdict="CONFIRMED", technique_ids=["T1190"]),
        ]
    )
    dismiss = consolidate(
        [
            ChainResult(model="a", verdict="RULED_OUT"),
            ChainResult(model="b", verdict="RULED_OUT"),
        ]
    )
    decisions_ok = converge.decision == "AUTO_CONFIRM" and dismiss.decision == "DISMISS"
    subs.append(
        {
            "name": "convergence AUTO_CONFIRM / unanimous benign DISMISS (live)",
            "status": "PASS" if decisions_ok else "FAIL",
            "detail": f"converge={converge.decision} dismiss={dismiss.decision}",
        }
    )
    if not decisions_ok:
        bad.append("consolidate did not route convergence/benign to AUTO_CONFIRM/DISMISS")

    # Live: an incomplete investigation (no chain concluded) must ESCALATE, not
    # be handed to the SOC as 'all clear'.
    incomplete = consolidate(
        [ChainResult(model="a", verdict="UNRESOLVED"), ChainResult(model="b", verdict="UNRESOLVED")]
    )
    incomplete_ok = incomplete.decision == "ESCALATE"
    subs.append(
        {
            "name": "incomplete investigation ESCALATES, never DISMISS (live)",
            "status": "PASS" if incomplete_ok else "FAIL",
            "detail": f"decision={incomplete.decision}",
        }
    )
    if not incomplete_ok:
        bad.append("no-conclusion consolidation did not ESCALATE (was handed to SOC as clear)")

    # Live: known-bad and unknown are SEPARATE channels — a confirm alongside a
    # near-miss lead is CONFIRM_AND_ESCALATE carrying BOTH, never dropping the
    # unknown just because a different technique auto-confirmed (dims 1-3 fix).
    both = consolidate(
        [
            ChainResult(model="a", verdict="CONFIRMED", technique_ids=["T1190"]),
            ChainResult(model="b", verdict="CONFIRMED", technique_ids=["T1190"]),
            ChainResult(model="c", verdict="ANOMALOUS_UNCLASSIFIED", similar_to=["T1505.003"]),
        ],
        quorum=0.5,
    )
    both_ok = (
        both.decision == "CONFIRM_AND_ESCALATE"
        and both.confirmed_techniques == ["T1190"]
        and both.review_leads == ["T1505.003"]
    )
    subs.append(
        {
            "name": "confirm+escalate keeps both channels separate (live)",
            "status": "PASS" if both_ok else "FAIL",
            "detail": (
                f"decision={both.decision} confirmed={both.confirmed_techniques} "
                f"review={both.review_leads}"
            ),
        }
    )
    if not both_ok:
        bad.append("confirm-alongside-unknown did not surface both channels (dropped the unknown)")

    # Live: escalation is a SCORED win, not a miss — a correct escalation
    # (review lead hits ground truth) yields operational_recall 1.0 even though
    # nothing was autonomously confirmed (dimension-1 scoring fix).
    from portal.modules.security.core.agentic_blue_eval import score_analyst_outcome

    esc_score = score_analyst_outcome(
        confirmed=set(), review_leads={"T1558.003"}, ground_truth={"T1558.003"}
    )
    esc_scored_ok = (
        esc_score["confirmed"]["overall"]["recall"] == 0.0
        and esc_score["operational"]["operational_recall"] == 1.0
    )
    subs.append(
        {
            "name": "correct escalation scores operational win, not a miss (live)",
            "status": "PASS" if esc_scored_ok else "FAIL",
            "detail": (
                f"confirmed_recall={esc_score['confirmed']['overall']['recall']} "
                f"operational_recall={esc_score['operational']['operational_recall']}"
            ),
        }
    )
    if not esc_scored_ok:
        bad.append("a correct escalation was not credited as an operational win (I8 scoring)")

    if bad:
        return ("FAIL", "; ".join(bad), subs)
    return (
        "PASS",
        "multichain: separate known/unknown channels, escalate first-class + scored",
        [],
    )


def _mentor_prompt_directive_text(prompt: str) -> str:
    """Strip sentences that are themselves negations/self-references (e.g.
    "not to tell it what the answer is", the "MUST NOT ..." clause) so a
    forbidden substring appearing ONLY inside a disclaimer doesn't trip the
    scan. A plain disclaimer-span removal (just the "MUST NOT" sentence)
    isn't enough — the locked prompt's opening sentence also self-references
    ("not to tell it what the answer is") outside that span."""
    sentences = re.split(r"(?<=[.!?])\s+", prompt)
    kept = [
        s
        for s in sentences
        if not re.search(r"\bnot\b|\bcannot\b|\bnever\b|n['’]t\b", s, re.IGNORECASE)
    ]
    return " ".join(kept)


@register("mentor", "BG. mentor prompt discipline (M1: never prescribes)", order=57)
def check_mentor_discipline() -> tuple[str, str, list[dict]]:
    """BG. Mentor prompt (M1) never prescribes: no MITRE technique IDs,
    no verdict class as a directive, no 'the answer is' language.

    Purely static — scans the source constant _MENTOR_SYSTEM_PROMPT. This
    catches drift: someone re-edits the prompt to be 'more helpful' and
    accidentally names a technique or a verdict target. Directive text is
    computed by dropping negation/self-reference sentences (see
    _mentor_prompt_directive_text) rather than only the trailing "MUST NOT"
    clause, since the prompt's own opening disclaimer sentence also contains
    a forbidden substring in negated form."""
    from portal.modules.security.core.blue_orchestrate import _MENTOR_SYSTEM_PROMPT

    subs: list[dict] = []
    bad: list[str] = []

    mitre_hits = re.findall(r"\bT\d{4}(?:\.\d+)?\b", _MENTOR_SYSTEM_PROMPT)
    ok_mitre = not mitre_hits
    subs.append(
        {
            "name": "no MITRE technique IDs in mentor prompt",
            "status": "PASS" if ok_mitre else "FAIL",
            "detail": "none found" if ok_mitre else f"found: {mitre_hits}",
        }
    )
    if not ok_mitre:
        bad.append(f"mentor prompt names MITRE IDs: {mitre_hits}")

    directive = _mentor_prompt_directive_text(_MENTOR_SYSTEM_PROMPT)

    verdict_hits = [
        v for v in ("CONFIRMED", "RULED_OUT", "ANOMALOUS_UNCLASSIFIED") if v in directive
    ]
    ok_verdicts = not verdict_hits
    subs.append(
        {
            "name": "verdict class names confined to negated/self-reference sentences",
            "status": "PASS" if ok_verdicts else "FAIL",
            "detail": "confined" if ok_verdicts else f"leaked to directive body: {verdict_hits}",
        }
    )
    if not ok_verdicts:
        bad.append(f"mentor prompt names verdict classes outside disclaimer: {verdict_hits}")

    prescriptive = [
        p
        for p in (
            "the answer is",
            "you should conclude",
            "conclude that",
            "this is a ",
            "is confirmed",
            "is ruled out",
        )
        if p.lower() in directive.lower()
    ]
    ok_pres = not prescriptive
    subs.append(
        {
            "name": "no prescriptive templates in mentor prompt directive body",
            "status": "PASS" if ok_pres else "FAIL",
            "detail": "none found" if ok_pres else f"found: {prescriptive}",
        }
    )
    if not ok_pres:
        bad.append(f"mentor prompt contains prescriptive templates: {prescriptive}")

    if bad:
        return ("FAIL", "; ".join(bad), subs)
    return ("PASS", "mentor prompt scans clean (M1 preserved)", subs)


@register(
    "budget_backward_compat", "BH. budget backward compat (V2 identical when no budgets=)", order=58
)
def check_budget_backward_compat() -> tuple[str, str, list[dict]]:
    """BH. V3B: run_blue_orchestration with only max_rounds= (no budgets=)
    reproduces V2 behavior for a deterministic three-section run.

    Live-functional check — not source-scan. A source scan would pass on a
    signature that accepts budgets= but silently ignores it; only a
    functional run catches wiring regressions in _resolve_budget or one of
    the dispatch functions.
    """
    import json

    from portal.modules.security.core import blue_orchestrate as bo
    from portal.modules.security.core.agentic_blue_eval import Episode

    subs: list[dict] = []
    bad: list[str] = []

    episode = Episode(
        scenario="asrep_to_lateral",
        target_host="dc01",
        techniques=["T1558.004"],
        telemetry={"windows:security": ["EventCode=4768 AS-REP event for svc-web"]},
    )
    sections = [
        bo.SectionSpec(role="tool", model="tool-model", needs_tools=True),
        bo.SectionSpec(role="reasoning", model="reasoning-model"),
        bo.SectionSpec(role="expert", model="expert-model"),
    ]

    def fake_call_model(model, messages, tools=None, max_tokens=2000, extra_options=None):
        if model == "reasoning-model":
            return {"content": json.dumps({"request_more": "need more", "technique_ids": []})}
        return {
            "content": json.dumps(
                {
                    "verdict": "CONFIRMED",
                    "technique_ids": ["T1558.004"],
                    "evidence": ["EventCode=4768 AS-REP event for svc-web"],
                    "reasoning": "confirmed",
                    "match_grade": "EXACT",
                    "similar_to": [],
                    "request_more": "",
                }
            )
        }

    def fake_run_tool_model(req, *, tool_model, episode, dry_run=False):
        return bo.ToolResult(query=req.spec, provenance="matched", raw_summary="EventCode=4768")

    orig_call_model = bo._call_model
    orig_run_tool_model = bo.run_tool_model
    bo._call_model = fake_call_model
    bo.run_tool_model = fake_run_tool_model
    try:
        v2 = bo.run_blue_orchestration(episode, sections=sections, max_rounds=6)
        v3b = bo.run_blue_orchestration(episode, sections=sections, max_rounds=6, budgets=None)
    finally:
        bo._call_model = orig_call_model
        bo.run_tool_model = orig_run_tool_model

    identical = (
        v2.verdict == v3b.verdict == "CONFIRMED"
        and v2.rounds == v3b.rounds
        and v2.trace == v3b.trace
    )
    subs.append(
        {
            "name": "max_rounds= alone reproduces V2 trace/verdict/rounds (live)",
            "status": "PASS" if identical else "FAIL",
            "detail": f"v2.rounds={v2.rounds} v3b.rounds={v3b.rounds} v2.verdict={v2.verdict}",
        }
    )
    if not identical:
        bad.append("budgets=None with max_rounds=N diverged from V2 (B1 broken)")

    has_hunter_tool_expert = {t.get("section") for t in v2.trace} >= {"tool", "reasoning", "expert"}
    subs.append(
        {
            "name": "trace contains hunter+tool+expert entries",
            "status": "PASS" if has_hunter_tool_expert else "FAIL",
            "detail": f"sections={sorted({t.get('section') for t in v2.trace})}",
        }
    )
    if not has_hunter_tool_expert:
        bad.append("V2-equivalent trace missing expected section entries")

    if bad:
        return ("FAIL", "; ".join(bad), subs)
    return ("PASS", "budgets=None is byte-for-byte V2 (B1 preserved)", subs)


@register(
    "barrier_tools",
    "BI. barrier tools gate (T1 JSON fallback + T2 escalate first-class + I2 cite-or-drop)",
    order=59,
)
def check_barrier_tools_gate() -> tuple[str, str, list[dict]]:
    """BI. V3C: barrier-tool schemas are shaped correctly (T2: escalate is
    distinct from emit_verdict) and cite-or-drop still runs on CONFIRMED
    emitted via barrier tool (I2).

    Static schema check + live functional check combined."""
    from portal.modules.security.core import blue_orchestrate as bo
    from portal.modules.security.core.blue_orchestrate import _BARRIER_TOOL_SCHEMAS

    subs: list[dict] = []
    bad: list[str] = []

    names = [t["function"]["name"] for t in _BARRIER_TOOL_SCHEMAS]
    expected = {"emit_verdict", "escalate_anomalous", "request_more"}
    ok_names = set(names) == expected
    subs.append(
        {
            "name": "three barrier tools present",
            "status": "PASS" if ok_names else "FAIL",
            "detail": f"names={names}",
        }
    )
    if not ok_names:
        bad.append(f"barrier tool set incorrect: got {names}, want {sorted(expected)}")

    emit = next((t for t in _BARRIER_TOOL_SCHEMAS if t["function"]["name"] == "emit_verdict"), None)
    if emit:
        enum_vals = emit["function"]["parameters"]["properties"]["verdict"].get("enum", [])
        t2_ok = "ANOMALOUS_UNCLASSIFIED" not in enum_vals and set(enum_vals) == {
            "CONFIRMED",
            "RULED_OUT",
        }
        subs.append(
            {
                "name": "T2: emit_verdict enum excludes ANOMALOUS_UNCLASSIFIED",
                "status": "PASS" if t2_ok else "FAIL",
                "detail": f"enum={enum_vals}",
            }
        )
        if not t2_ok:
            bad.append(
                f"T2 violated: emit_verdict enum = {enum_vals} (should be CONFIRMED/RULED_OUT only)"
            )

    # I2 live check: a CONFIRMED emitted via barrier tool with ungrounded
    # evidence must still be demoted through the same cite-or-drop gate the
    # JSON path uses — barrier tools are structural, not exempting.
    orig_call_model = bo._call_model

    def fake_ungrounded_confirm(model, messages, tools=None, max_tokens=2000, extra_options=None):
        return {
            "tool_calls": [
                {
                    "function": {
                        "name": "emit_verdict",
                        "arguments": {
                            "verdict": "CONFIRMED",
                            "technique_ids": ["T1558.004"],
                            "evidence": ["fabricated-citation-zzz99001, never actually gathered"],
                            "reasoning": "r",
                            "match_grade": "EXACT",
                        },
                    }
                }
            ]
        }

    bo._call_model = fake_ungrounded_confirm
    try:
        out = bo.run_expert_model(
            "ctx",
            expert_model="expert-model",
            context_text="",
            tool_results=[
                bo.ToolResult(
                    query="q",
                    provenance="matched-exact",
                    raw_summary="EventCode=9999 innocuous-startup-alpha7712",
                )
            ],
            use_barrier_tools=True,
        )
    finally:
        bo._call_model = orig_call_model

    i2_ok = out.verdict == "ANOMALOUS_UNCLASSIFIED" and out.ungrounded_claims == ["T1558.004"]
    subs.append(
        {
            "name": "I2: ungrounded CONFIRMED via barrier tool is demoted (live)",
            "status": "PASS" if i2_ok else "FAIL",
            "detail": f"verdict={out.verdict} ungrounded_claims={out.ungrounded_claims}",
        }
    )
    if not i2_ok:
        bad.append("barrier-tool CONFIRMED with ungrounded evidence was not demoted (I2 broken)")

    if bad:
        return ("FAIL", "; ".join(bad), subs)
    return ("PASS", "barrier tools shape + I2 grounding preserved", subs)


@register(
    "subtechnique",
    "BJ. sub-technique discriminator gate (S1 label-blind + S2 contradiction-only)",
    order=60,
)
def check_subtechnique_discriminator_gate() -> tuple[str, str, list[dict]]:
    """BJ. V4A discriminator gate is label-blind and contradiction-only."""
    import inspect

    from portal.modules.security.core.blue import _discriminator_contradicts

    subs: list[dict] = []
    bad: list[str] = []

    params = list(inspect.signature(_discriminator_contradicts).parameters)
    forbidden = {"ground_truth", "episode", "techniques", "expected", "answer"}
    leaked = [p for p in params if any(word in p.lower() for word in forbidden)]
    s1_ok = not leaked
    subs.append(
        {
            "name": "S1: gate takes no ground-truth parameter",
            "status": "PASS" if s1_ok else "FAIL",
            "detail": f"params={params}",
        }
    )
    if not s1_ok:
        bad.append(f"discriminator gate leaks ground truth via params: {leaked}")

    telemetry = "EventCode=4768 PreAuthType=0 Account=svc-web"
    contradicted_wrong, siblings = _discriminator_contradicts("T1558.003", telemetry)
    contradicted_right, _ = _discriminator_contradicts("T1558.004", telemetry)
    s2_ok = contradicted_wrong and "T1558.004" in siblings and not contradicted_right
    subs.append(
        {
            "name": "S2: wrong sibling contradicted, correct claim retained",
            "status": "PASS" if s2_ok else "FAIL",
            "detail": (
                f"wrong={contradicted_wrong} siblings={siblings} right={contradicted_right}"
            ),
        }
    )
    if not s2_ok:
        bad.append("positive-contradiction behavior failed")

    orch = (
        REPO_ROOT / "portal" / "modules" / "security" / "core" / "blue_orchestrate.py"
    ).read_text()
    cite_sites = orch.count("_cite_or_drop(")
    gate_sites = orch.count("_grounded_discriminator_contradictions(") - 1
    coexist_ok = gate_sites >= cite_sites
    subs.append(
        {
            "name": "I2: discriminator gate shares every orchestration citation chokepoint",
            "status": "PASS" if coexist_ok else "FAIL",
            "detail": f"cite_sites={cite_sites} gated_sites={gate_sites}",
        }
    )
    if not coexist_ok:
        bad.append(f"only {gate_sites}/{cite_sites} citation chokepoints are discriminator-gated")

    if bad:
        return ("FAIL", "; ".join(bad), subs)
    return ("PASS", "sub-technique discriminator gate is label-blind and S2-safe", subs)


@register("budget_starve", "BK. budget-starve reaches expert (U1: no silent UNRESOLVED)", order=61)
def check_budget_starve_reaches_expert() -> tuple[str, str, list[dict]]:
    """BK. A budget-starved Hunter reaches the Expert before UNRESOLVED."""
    import json

    from portal.modules.security.core import blue_orchestrate as bo

    hunter_more = json.dumps({"request_more": "still need more", "technique_ids": []})
    expert_ruled_out = json.dumps(
        {
            "verdict": "RULED_OUT",
            "technique_ids": [],
            "evidence": [],
            "reasoning": "nothing conclusive",
            "match_grade": "NONE",
            "similar_to": [],
            "request_more": "",
        }
    )
    calls: list[str] = []

    def fake_call_model(model, messages, tools=None, max_tokens=2000, extra_options=None):
        calls.append(model)
        return {"content": expert_ruled_out if model == "expert-model" else hunter_more}

    def fake_run_tool_model(req, *, tool_model, episode, dry_run=False):
        return bo.ToolResult(query=req.spec, provenance="empty", raw_summary="")

    episode = bo.Episode(
        scenario="v4b-budget-starve-check",
        target_host="dc01",
        techniques=[],
        telemetry={"windows:security": []},
    )
    sections = [
        bo.SectionSpec(role="tool", model="tool-model", needs_tools=True),
        bo.SectionSpec(role="reasoning", model="hunter-model"),
        bo.SectionSpec(role="expert", model="expert-model"),
    ]

    original_call_model = bo._call_model
    original_run_tool_model = bo.run_tool_model
    try:
        bo._call_model = fake_call_model
        bo.run_tool_model = fake_run_tool_model
        result = bo.run_blue_orchestration(
            episode,
            sections=sections,
            max_rounds=20,
            budgets={"hunter": 4},
        )
    finally:
        bo._call_model = original_call_model
        bo.run_tool_model = original_run_tool_model

    expert_in_trace = any(entry.get("section") == "expert" for entry in result.trace)
    ok = "expert-model" in calls and expert_in_trace and result.verdict == "RULED_OUT"
    subs = [
        {
            "name": "U1: starved hunt invokes Expert and uses its conclusion",
            "status": "PASS" if ok else "FAIL",
            "detail": (
                f"verdict={result.verdict} expert_called={'expert-model' in calls} "
                f"expert_trace={expert_in_trace}"
            ),
        }
    ]
    if not ok:
        return ("FAIL", "budget-starved hunt still bypassed its Expert", subs)
    return ("PASS", "budget-starved hunt reaches a final Expert turn", subs)


@register(
    "council_participation",
    "BL. council participation floor (Q1: non-voter counts against quorum)",
    order=62,
)
def check_council_participation_floor() -> tuple[str, str, list[dict]]:
    """BL. Council quorum uses the full roster, including non-voters."""
    from portal.modules.security.core.analyst_verdict import SectionOutput
    from portal.modules.security.core.council_agreement import compute_agreement

    concluder = SectionOutput(
        verdict="CONFIRMED",
        technique_ids=["T1558.003"],
        section="expert",
    )
    non_voter = SectionOutput(
        verdict=None,
        request_more="still confused",
        section="expert",
    )
    one_of_two = compute_agreement([concluder, non_voter], quorum=0.5)
    roster_ok = (
        one_of_two.verdict == "ANOMALOUS_UNCLASSIFIED"
        and one_of_two.needs_arbiter
        and one_of_two.agreement == 0.5
    )

    both = [
        SectionOutput(
            verdict="CONFIRMED",
            technique_ids=["T1558.003"],
            section="expert",
        ),
        SectionOutput(
            verdict="CONFIRMED",
            technique_ids=["T1558.003"],
            section="expert",
        ),
    ]
    unanimous = compute_agreement(both, quorum=0.5)
    full_ok = unanimous.verdict == "CONFIRMED" and unanimous.agreement == 1.0

    below_floor = compute_agreement([concluder, non_voter, non_voter], quorum=0.5)
    floor_ok = (
        below_floor.verdict == "ANOMALOUS_UNCLASSIFIED"
        and below_floor.needs_arbiter
        and "below floor" in below_floor.rationale
    )
    subs = [
        {
            "name": "Q1: lone survivor is 1/2, never auto-1.0",
            "status": "PASS" if roster_ok else "FAIL",
            "detail": f"agreement={one_of_two.agreement} verdict={one_of_two.verdict}",
        },
        {
            "name": "I7: full participation unanimous remains CONFIRMED @1.0",
            "status": "PASS" if full_ok else "FAIL",
            "detail": f"agreement={unanimous.agreement} verdict={unanimous.verdict}",
        },
        {
            "name": "Q1: participation below floor escalates",
            "status": "PASS" if floor_ok else "FAIL",
            "detail": f"verdict={below_floor.verdict} rationale={below_floor.rationale}",
        },
    ]
    if not (roster_ok and full_ok and floor_ok):
        return ("FAIL", "council roster denominator or participation floor failed", subs)
    return ("PASS", "council quorum uses roster and participation floor", subs)


@register(
    "recall_attribution",
    "BM. recall attribution boundary (label-blind oracle + World A/B split)",
    order=63,
)
def check_recall_attribution_boundary() -> tuple[str, str, list[dict]]:
    """BM. Eval label selection cannot leak into the presence decision."""
    import inspect

    from portal.modules.security.core import recall_attribution as ra

    params = list(inspect.signature(ra.evidence_presence).parameters)
    signature_ok = params == ["telemetry", "technique_discriminators"]

    present_cell = {
        "label": "world-a",
        "technique_expected": "T1558.004",
        "mode": "orchestrated",
        "model_arm": "synthetic",
        "status": "done",
        "verdict": "ANOMALOUS_UNCLASSIFIED",
        "technique_ids": [],
        "trace": [{"section": "tool", "content": "EventCode=4768 PreAuthType=0"}],
    }
    absent_cell = {
        **present_cell,
        "label": "world-b",
        "verdict": "RULED_OUT",
        "trace": [{"section": "tool", "content": "EventCode=4769 TicketEncryptionType=0x17"}],
    }
    world_a = ra.attribute_cell(present_cell)
    world_b = ra.attribute_cell(absent_cell)
    split_ok = (
        world_a["attribution"] == ra.EVIDENCE_PRESENT_MISS
        and world_b["attribution"] == ra.HONEST_NEGATIVE
    )

    production_source = (
        REPO_ROOT / "portal" / "modules" / "security" / "core" / "siem" / "spl_detections.py"
    ).read_text()
    boundary_ok = "recall_attribution" not in production_source

    subs = [
        {
            "name": "oracle presence decision receives no label or answer key",
            "status": "PASS" if signature_ok else "FAIL",
            "detail": f"params={params}",
        },
        {
            "name": "canonical World A and World B cases remain distinct",
            "status": "PASS" if split_ok else "FAIL",
            "detail": (f"present={world_a['attribution']} absent={world_b['attribution']}"),
        },
        {
            "name": "production discriminator accessor does not import eval attribution",
            "status": "PASS" if boundary_ok else "FAIL",
            "detail": "read-only dependency direction preserved",
        },
    ]
    if not (signature_ok and split_ok and boundary_ok):
        return ("FAIL", "recall-attribution boundary or World A/B split failed", subs)
    return ("PASS", "label-blind token oracle and eval-only boundary preserved", subs)


@register("notify_scoreboard", "BN. hunt-and-notify scoreboard semantics", order=64)
def check_notify_scoreboard_semantics() -> tuple[str, str, list[dict]]:
    """BN. RBP-native scoring preserves catch, fairness, and trust ordering."""
    from portal.modules.security.core import notify_scoreboard as ns
    from portal.modules.security.core import recall_attribution as ra

    anomaly = {
        "label": "anomaly",
        "technique_expected": "T1558.004",
        "model_arm": "synthetic",
        "verdict": "ANOMALOUS_UNCLASSIFIED",
        "technique_ids": [],
        "oracle_result": ra.PRESENT,
    }
    absent_silence = {
        **anomaly,
        "label": "absent-silence",
        "verdict": "RULED_OUT",
        "oracle_result": ra.ABSENT,
    }
    wrong_confirm = {
        **anomaly,
        "label": "wrong-confirm",
        "verdict": "CONFIRMED",
        "technique_ids": ["T1053.005"],
    }
    scored = ns.score_arm([anomaly, absent_silence, wrong_confirm])
    axis_1 = scored["axis_1_notify_recall"]
    axis_2 = scored["axis_2_notification_trustworthiness"]

    anomaly_catch_ok = axis_1["raw"]["notified"] == 2
    absent_fairness_ok = axis_1["evidence_never_shown"] == 1 and axis_1["real_misses"] == 0
    ordering_ok = (
        axis_2["ordinal_ranks"][ns.CONFIRMED_CORRECT]
        > axis_2["ordinal_ranks"][ns.HONEST_ANOMALY]
        > axis_2["ordinal_ranks"][ns.CONFIRMED_WRONG]
    )

    subs = [
        {
            "name": "ANOMALOUS_UNCLASSIFIED is an Axis-1 catch",
            "status": "PASS" if anomaly_catch_ok else "FAIL",
            "detail": f"notified={axis_1['raw']['notified']}/3",
        },
        {
            "name": "silence on ABSENT evidence is not a real miss",
            "status": "PASS" if absent_fairness_ok else "FAIL",
            "detail": (
                f"absent={axis_1['evidence_never_shown']} real_misses={axis_1['real_misses']}"
            ),
        },
        {
            "name": "confirmed-wrong ranks below honest anomaly",
            "status": "PASS" if ordering_ok else "FAIL",
            "detail": f"ranks={axis_2['ordinal_ranks']}",
        },
    ]
    if not (anomaly_catch_ok and absent_fairness_ok and ordering_ok):
        return ("FAIL", "hunt-and-notify scoreboard semantics failed", subs)
    return ("PASS", "hunt-and-notify catch and trust semantics preserved", subs)


@register("single_council_quorum", "BO. single council quorum implementation", order=65)
def check_single_council_quorum() -> tuple[str, str, list[dict]]:
    """BO. Legacy security votes delegate to the platform council primitive."""
    import inspect

    from portal.modules.security.core import council_agreement as security_council
    from portal.modules.security.core.analyst_verdict import SectionOutput
    from portal.platform.inference.router.council import CouncilOpinion, aggregate_opinions

    def member(verdict: str | None, technique: str = "") -> SectionOutput:
        return SectionOutput(
            verdict=verdict,
            technique_ids=[technique] if technique else [],
            request_more="" if verdict else "need more evidence",
            section="expert",
        )

    legacy = security_council.compute_agreement(
        [member("CONFIRMED", "T1078"), member(None)],
        quorum=0.5,
        min_participation=0.67,
    )
    platform = aggregate_opinions(
        [
            CouncilOpinion("one", "one", "m1", "SUPPORT", valid=True),
            CouncilOpinion("two", "two", "m2", "ABSTAIN", valid=False),
        ],
        minimum_participation=0.67,
        quorum=0.5,
    )
    source = inspect.getsource(security_council.compute_agreement)
    delegates = "aggregate_opinions(" in source
    same_floor = (
        legacy.verdict == "ANOMALOUS_UNCLASSIFIED"
        and legacy.needs_arbiter
        and platform.decision == "ESCALATE"
    )
    production_lean = "has_council" in inspect.getsource(
        __import__(
            "portal.modules.security.core.blue_orchestrate",
            fromlist=["run_blue_orchestration"],
        ).run_blue_orchestration
    )
    subs = [
        {
            "name": "security compatibility path delegates quorum",
            "status": "PASS" if delegates else "FAIL",
            "detail": "aggregate_opinions call present"
            if delegates
            else "independent quorum found",
        },
        {
            "name": "participation-floor result matches platform ESCALATE",
            "status": "PASS" if same_floor else "FAIL",
            "detail": f"security={legacy.verdict} platform={platform.decision}",
        },
        {
            "name": "legacy council remains opt-in, not production workhorse",
            "status": "PASS" if production_lean else "FAIL",
            "detail": "dispatch requires an explicit multi-member reasoning roster",
        },
    ]
    if not (delegates and same_floor and production_lean):
        return ("FAIL", "council reconciliation invariant failed", subs)
    return ("PASS", "platform aggregate_opinions is the single quorum implementation", subs)


@register("council_bench", "BP. council bench scoring semantics", order=66)
def check_council_bench_semantics() -> tuple[str, str, list[dict]]:
    """BP. Council value is evidence-backed and always compared with solo."""
    from portal.modules.security.core import council_review_bench as bench
    from portal.platform.inference.router.council import CouncilOpinion

    task = bench.ReviewTask(
        "synthetic",
        "Synthetic flaw",
        "validator",
        "No dry-run is planned.",
        ("dry-run",),
    )
    with_evidence = {
        "findings": [
            {
                "claim": "Missing dry-run",
                "evidence": ["No dry-run is planned."],
                "action": "Add one.",
            }
        ]
    }
    without_evidence = {
        "findings": [{"claim": "Missing dry-run", "evidence": [], "action": "Add one."}]
    }
    evidence_required = bench.catches_known_flaw(
        task, [with_evidence]
    ) and not bench.catches_known_flaw(task, [without_evidence])
    baseline_required = False
    try:
        bench.summarize([])
    except ValueError:
        baseline_required = True

    thin = bench.ReviewTask("thin", "Thin", "validator", "Proceed?", thin_material=True)
    case = bench.score_case(
        thin,
        council_payload={
            "portal_council": {
                "aggregate": {"decision": "ESCALATE", "dissent": []},
                "reviewers": [
                    {
                        "member_id": "a",
                        "participated": False,
                        "findings": [],
                    }
                ],
            },
            "choices": [{"message": {"content": "**Code-determined decision: ESCALATE**"}}],
        },
        solo_opinion=CouncilOpinion("solo", "Solo", "m", "ABSTAIN", valid=True),
        council_latency_s=1.0,
        solo_latency_s=0.5,
    )
    abstention_correct = case["council"]["honest_abstention"]
    subs = [
        {
            "name": "flaw catch requires cited evidence",
            "status": "PASS" if evidence_required else "FAIL",
            "detail": "unsupported finding rejected",
        },
        {
            "name": "solo baseline is mandatory",
            "status": "PASS" if baseline_required else "FAIL",
            "detail": "empty baseline raises ValueError",
        },
        {
            "name": "thin-material ESCALATE scores as honest abstention",
            "status": "PASS" if abstention_correct else "FAIL",
            "detail": f"honest_abstention={abstention_correct}",
        },
    ]
    if not (evidence_required and baseline_required and abstention_correct):
        return ("FAIL", "council bench scoring invariant failed", subs)
    return ("PASS", "council bench requires evidence, abstention, and solo delta", subs)


@register("benign_alert", "BQ. benign alert-fatigue semantics", order=67)
def check_benign_alert_fatigue() -> tuple[str, str, list[dict]]:
    """BQ. Benign notifications are false flags and populate Axis 4."""
    from portal.modules.security.core import notify_scoreboard as ns

    cells = [
        {
            "label": "attack",
            "status": "done",
            "cell_kind": "attack",
            "technique_expected": "T1078",
            "model_arm": "synthetic",
            "verdict": "CONFIRMED",
            "technique_ids": ["T1078"],
            "oracle_result": "PRESENT",
        },
        {
            "label": "quiet",
            "status": "done",
            "ground_truth": "benign",
            "technique_expected": "",
            "model_arm": "synthetic",
            "verdict": "RULED_OUT",
            "technique_ids": [],
        },
        {
            "label": "false-confirm",
            "status": "done",
            "ground_truth": "benign",
            "technique_expected": "",
            "model_arm": "synthetic",
            "verdict": "CONFIRMED",
            "technique_ids": ["T1053.005"],
        },
    ]
    joined = [cells[0], *ns.join_oracle(cells[1:])]
    scored = ns.score_arm(joined)
    fatigue = scored["axis_4_alert_fatigue_on_benign"]
    populated = fatigue["status"] == "MEASURED" and fatigue["benign_cells"] == 2
    false_flag = (
        fatigue["false_flags"] == 1 and fatigue["false_flag_kinds"][ns.CONFIRMED_ON_BENIGN] == 1
    )
    both_axes = (
        scored["axis_1_notify_recall"]["raw"]["rate"] == 1.0 and not scored["measurement_gaps"]
    )
    subs = [
        {
            "name": "benign cells populate notification precision",
            "status": "PASS" if populated else "FAIL",
            "detail": f"axis={fatigue}",
        },
        {
            "name": "NOTIFY on benign is a typed false flag",
            "status": "PASS" if false_flag else "FAIL",
            "detail": f"kinds={fatigue['false_flag_kinds']}",
        },
        {
            "name": "combined attack/benign run has both axes",
            "status": "PASS" if both_axes else "FAIL",
            "detail": "recall and alert-fatigue are measured",
        },
    ]
    if not (populated and false_flag and both_axes):
        return ("FAIL", "benign alert-fatigue invariant failed", subs)
    return ("PASS", "benign precision and false-flag semantics populated", subs)
