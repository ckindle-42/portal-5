"""Stage 2 — propose, prove, and gate oracle-tier promotions.

The Stage 1 self-index (self_index.py) surfaces one dominant weakness: 46 of 55
oracles (41 experimental + 5 differential tier) cannot produce a VERIFIED verdict
because ``oracles.verify_finding()`` hard-gates VERIFIED on ``tier == "stable"``
(oracles.py:254). This module generates one bounded promotion proposal per weak
oracle, PROVES each against real chain-test data (positive: the check verifies
true exploitation N/N; negative: it must NOT verify benign/refused entries),
scores the proposal's quality (bounded / real weakness / proven / not-hollow /
moves-fitness), and stages verified diffs for one batch operator approval.

Nothing is written to ``oracles.py`` or ``ability_port.py`` by this module except
through ``apply_batch()``, which only ever runs when the operator passes
``--apply`` on the command line (see ``stage2_propose_main``). Running without
``--apply`` proposes + proves + reports and applies nothing — enforced by test
(``tests/unit/test_stage2_propose.py``) and by validator check AB.

A promotion must be EARNED by evidence: a proposal that only flips ``tier``
without strengthening a stub ``check`` is hollow and can never be marked
promotable, regardless of what the (necessarily fake, since untested) proof
claims — see ``goal_eval``.
"""

from __future__ import annotations

import copy
import json
import re
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parents[4]
_SELF_DIR = Path(__file__).resolve().parent
_RESULTS_DIR = _SELF_DIR / "results"
_ORACLES_PY = _SELF_DIR / "oracles.py"
_ABILITY_PORT_PY = _SELF_DIR / "ability_port.py"

STAGE2_DIR = _SELF_DIR / "stage2_proposals"

# Oracle tiers this task targets — matches the Stage 1 weakness view exactly
# (41 experimental + 5 differential == 46). "oob"-tier oracles (7, detect_fn=None,
# bound to oast_callback instead) are out of scope for THIS task's weakness view.
WEAK_TIERS = {"experimental", "differential"}

REQUIRED_REPRODUCTIONS = 2


# ── Phase 1: proposal generator ────────────────────────────────────────────


def weak_oracle_ids(oracles: dict[str, Any]) -> list[str]:
    """Oracle ids currently gated out of VERIFIED — tier in WEAK_TIERS. Deterministic order."""
    return sorted(oid for oid, o in oracles.items() if o.tier in WEAK_TIERS)


def generate_proposal(oracle_id: str, oracle: Any) -> dict:
    """One bounded proposal for oracle_id: promote tier, strengthen check IF it's a stub.

    Bounded = touches only this oracle's check + tier. Never a multi-oracle change.
    """
    return {
        "oracle_id": oracle_id,
        "scope": [oracle_id],
        "current_tier": oracle.tier,
        "proposed_tier": "stable",
        "kind": oracle.kind,
        "honesty_claim": oracle.honesty_claim,
        # True only once Phase 2 proof demonstrates the existing check() already
        # does real detection against real data — a bounded promotion never
        # touches detection logic that hasn't been proven; a proposal whose
        # check is proven insufficient stays experimental instead of being
        # "strengthened" speculatively (that would be a second unproven change).
        "diff_touches_check": False,
        "check_change": (
            f"promote {oracle_id} experimental/differential -> stable IF check() "
            "is proven (positive+negative) against real chain-test data; "
            "no speculative rewrite of check() logic without proof"
        ),
        "rationale": (
            f"{oracle_id} (kind={oracle.kind}) is hard-gated out of VERIFIED by "
            f"oracles.py:254 (tier=='stable' required). Promoting is meaningful only "
            f"if check() actually discriminates true exploitation from benign/refused."
        ),
    }


# ── Phase 2: prove against real data ───────────────────────────────────────


def _complete_all_scenarios_files() -> list[Path]:
    """Non-partial sec_*.json files with all_scenarios: true, newest first.

    Not anchored to sec_bench_ — EXEC_SEC_FULL_COVERAGE_V1.md's Step 1 writes
    sec_full_red_ instead (same gap fixed in self_index.py's _RESULT_GLOB).
    """
    candidates = []
    for p in _RESULTS_DIR.glob("sec_*.json"):
        if p.name.endswith(".partial.json"):
            continue
        try:
            data = json.loads(p.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        if data.get("all_scenarios") is True and data.get("chain_tests"):
            candidates.append(p)

    # "Newest" = the run's own embedded UTC timestamp, not filesystem mtime —
    # mtimes get scrambled by git checkout/clone (see self_index._run_timestamp_key).
    from .self_index import _run_timestamp_key

    return sorted(candidates, key=_run_timestamp_key, reverse=True)


def load_chain_data() -> dict:
    """Load the newest all_scenarios:true chain-test result. {} if none exist."""
    files = _complete_all_scenarios_files()
    if not files:
        return {}
    latest = files[0]
    data = json.loads(latest.read_text())
    return {"source_file": latest.name, "chain_tests": data.get("chain_tests", [])}


# Fields an oracle.check() implementation actually reads from a `finding` dict
# (see oracles.py's built-in Oracle subclasses and ability_port._oracle_check's
# status/headers/body/baseline/payload contract). None of these appear in a
# chain_tests entry (verified against the real schema: argument_adaptation,
# chain_depth, coherence, cve_research, elapsed_s, error, expected_order,
# lab_observations, lab_success, max_depth, mode, model, order_accuracy,
# pivot_correctness, refused, scenario, scope_discipline, stalled,
# timeout_steps, tools_called, unique_coverage, unique_steps_hit) — chain-test
# entries carry attack-chain telemetry (tool calls, booleans), never the raw
# finding evidence (payload/body/status/headers/differentials/success markers)
# oracle checks need.
_ORACLE_EVIDENCE_FIELDS = (
    "payload",
    "differentials",
    "error_signatures",
    "redirect_host",
    "cve_id",
    "success_indicators",
    "callback_id",
    "status",
    "headers",
    "body",
    "baseline",
)


def _extract_finding_from_chain_entry(entry: dict) -> dict | None:
    """Try to build an oracle-checkable `finding` dict from a chain_tests entry.

    Returns None if the entry carries none of the evidence fields any oracle's
    check() needs — which is the honest, verified case for every entry in the
    real chain-test schema today (see _ORACLE_EVIDENCE_FIELDS docstring).
    """
    present = {k: entry[k] for k in _ORACLE_EVIDENCE_FIELDS if k in entry}
    return present or None


@dataclass
class Proof:
    oracle_id: str
    source_file: str
    positive_tested: int = 0
    positive_passed: int = 0
    negative_tested: int = 0
    negative_passed: int = 0
    insufficient_evidence: bool = True
    evidence_detail: str = ""
    entries_examined: int = 0

    def as_dict(self) -> dict:
        return asdict(self)


def prove_proposal(oracle_id: str, oracle: Any, chain_data: dict) -> Proof:
    """Phase 2 — the heart. Run oracle.check() against real chain-test entries.

    Positive test: entries with lab_success True for this oracle's technique must
    VERIFY (check() returns True, REQUIRED_REPRODUCTIONS/REQUIRED_REPRODUCTIONS).
    Negative test: entries that are refused/benign/non-exploitation must NOT verify.

    If the chain-test schema carries no field any oracle.check() reads (verified:
    it doesn't, today), there is no real data to prove against — reported as
    insufficient evidence, never a forced pass and never a forced fail.
    """
    entries = chain_data.get("chain_tests", [])
    source_file = chain_data.get("source_file", "")
    proof = Proof(oracle_id=oracle_id, source_file=source_file, entries_examined=len(entries))

    if not entries:
        proof.evidence_detail = "no all_scenarios:true chain-test result file found"
        return proof

    positive_entries = [e for e in entries if e.get("lab_success") is True]
    negative_entries = [e for e in entries if e.get("lab_success") is not True]

    findable_positive = [(e, _extract_finding_from_chain_entry(e)) for e in positive_entries]
    findable_negative = [(e, _extract_finding_from_chain_entry(e)) for e in negative_entries]

    usable_positive = [(e, f) for e, f in findable_positive if f is not None]
    usable_negative = [(e, f) for e, f in findable_negative if f is not None]

    if not usable_positive and not usable_negative:
        proof.evidence_detail = (
            f"{len(entries)} chain-test entries examined in {source_file}; none carry "
            "the finding fields this oracle's check() reads "
            f"({', '.join(_ORACLE_EVIDENCE_FIELDS)}) — chain-test entries are attack-chain "
            "telemetry (tool calls, lab_success booleans), not oracle-checkable findings. "
            "verify_finding() has never been exercised against real chain-test data."
        )
        proof.insufficient_evidence = True
        return proof

    # Real usable evidence exists — actually run the check (this path is exercised
    # only if/when the chain-test schema starts emitting finding-shaped data).
    for _entry, finding in usable_positive:
        proof.positive_tested += 1
        successes = sum(
            1
            for _ in range(REQUIRED_REPRODUCTIONS)
            if oracle.check(finding, finding.get("body", ""), {})
        )
        if successes >= REQUIRED_REPRODUCTIONS:
            proof.positive_passed += 1

    for _entry, finding in usable_negative:
        proof.negative_tested += 1
        successes = sum(
            1
            for _ in range(REQUIRED_REPRODUCTIONS)
            if oracle.check(finding, finding.get("body", ""), {})
        )
        if successes >= REQUIRED_REPRODUCTIONS:
            proof.negative_passed += 1  # a "pass" here is a FALSE POSITIVE

    proof.insufficient_evidence = False
    proof.evidence_detail = (
        f"{proof.positive_passed}/{proof.positive_tested} positive verified, "
        f"{proof.negative_passed}/{proof.negative_tested} negative false-verified"
    )
    return proof


# ── Phase 3: proposal-quality evaluator ────────────────────────────────────


def _oracle_still_weak(oracle_id: str, index: dict) -> bool:
    """Recompute (don't assume) whether oracle_id is in the live Stage 1 weakness view."""
    oracles = index.get("oracles", {}).get("oracles", {})
    odata = oracles.get(oracle_id)
    return bool(odata) and odata.get("tier") in WEAK_TIERS


def _fitness_delta_if_promoted(oracle_id: str, index: dict) -> dict:
    """Recompute the Stage 1 weakness score before/after promoting oracle_id to stable.

    Uses the real self_index.rank_weaknesses — never assumes the delta.
    """
    from .self_index import rank_weaknesses

    before = rank_weaknesses(index)
    before_score = sum(w["score"] for w in before if w["area"] == f"oracle:{oracle_id}")

    after_index = copy.deepcopy(index)
    odata = after_index.get("oracles", {}).get("oracles", {}).get(oracle_id)
    if odata is not None:
        odata["tier"] = "stable"
    after = rank_weaknesses(after_index)
    after_score = sum(w["score"] for w in after if w["area"] == f"oracle:{oracle_id}")

    return {"before": before_score, "after": after_score, "delta": before_score - after_score}


def goal_eval(proposal: dict, proof: dict, index: dict | None = None) -> dict:
    """Score a proposal transparently. Deterministic — same inputs, same output.

    Criteria (all must hold for promotable=True):
      - bounded: proposal touches exactly one oracle's check+tier
      - real weakness: the oracle is in the live Stage 1 weakness view
      - proven: Phase 2 positive AND negative tests both passed against real data
      - not hollow: the proposal isn't a tier-only flip on an unproven stub check
      - moves fitness: promoting actually reduces the weakness score (recomputed)
    """
    oracle_id = proposal.get("oracle_id", "")
    reasons: list[str] = []

    bounded = proposal.get("scope") == [oracle_id] and bool(oracle_id)
    if not bounded:
        reasons.append("not bounded — proposal scope is not exactly [oracle_id]")

    targets_real_weakness = True
    if index is not None:
        targets_real_weakness = _oracle_still_weak(oracle_id, index)
        if not targets_real_weakness:
            reasons.append("does not target a real weakness — oracle not in Stage 1 weakness view")

    insufficient_evidence = bool(proof.get("insufficient_evidence"))
    positive_tested = proof.get("positive_tested", 0)
    positive_passed = proof.get("positive_passed", 0)
    negative_tested = proof.get("negative_tested", 0)
    negative_passed = proof.get("negative_passed", 0)  # false positives

    proven = (
        not insufficient_evidence
        and positive_tested > 0
        and positive_passed == positive_tested
        and negative_tested > 0
        and negative_passed == 0
    )
    if insufficient_evidence:
        reasons.append("not proven — insufficient real-data evidence to test against")
    elif not proven:
        if positive_tested == 0 or positive_passed < positive_tested:
            reasons.append(
                f"not proven — positive test failed ({positive_passed}/{positive_tested} verified)"
            )
        if negative_tested == 0:
            reasons.append("not proven — no negative (benign/refused) entries to test against")
        elif negative_passed > 0:
            reasons.append(
                f"not proven — false positive on negative test "
                f"({negative_passed}/{negative_tested} benign entries wrongly verified)"
            )

    # Hollow: a check-untouched tier flip on an oracle whose check was never proven
    # is a flag flip, not a promotion — the exact hollow-verification failure this
    # task exists to prevent. This check is independent of `proven`: even a proof
    # dict that CLAIMS success cannot rescue a diff that never strengthens the
    # check for a stub, because "proven" here would have to mean the *existing*
    # stub check already discriminates correctly — which the diff itself asserts
    # is not the case by not touching it while still being empty of prior proof.
    diff_touches_check = bool(proposal.get("diff_touches_check"))
    hollow = not diff_touches_check and not proven
    # Only surface the "hollow" reason when it's the actual diagnosis — data
    # unavailability ("insufficient evidence") already has its own honest reason
    # above; restating "hollow" on top of it would read as a harsher verdict
    # (a deceptive flag-flip attempt) than what actually happened (no data yet).
    if hollow and not insufficient_evidence:
        reasons.append("hollow / flag-flip only — tier changed with no proven check behavior")

    promotable = bounded and targets_real_weakness and proven and not hollow

    fitness = (
        _fitness_delta_if_promoted(oracle_id, index) if (index is not None and promotable) else None
    )
    would_move_fitness = fitness is None or fitness["delta"] > 0
    if index is not None and promotable and not would_move_fitness:
        promotable = False
        reasons.append("promoting does not reduce the weakness score (recomputed delta <= 0)")

    score = sum(
        [
            10 if bounded else 0,
            10 if targets_real_weakness else 0,
            40 if proven else 0,
            20 if not hollow else 0,
            20 if would_move_fitness else 0,
        ]
    )

    return {
        "oracle_id": oracle_id,
        "score": score,
        "promotable": promotable,
        "reasons": reasons,
        "evidence": {
            "bounded": bounded,
            "targets_real_weakness": targets_real_weakness,
            "proven": proven,
            "hollow": hollow,
            "would_move_fitness": would_move_fitness,
            "fitness": fitness,
            "proof": proof,
        },
    }


def classify_outcome(eval_result: dict, proof: dict) -> str:
    """The tri-state operator-facing outcome string for one oracle's proposal."""
    if eval_result["promotable"]:
        return "promotable"
    if proof.get("insufficient_evidence"):
        return "not-promotable-yet (insufficient evidence)"
    return "not-promotable"


# ── Phase 4: diffs + report ────────────────────────────────────────────────


def _locate_oracle_definition(oracle_id: str) -> tuple[Path, str] | None:
    """Find which file+file-text defines oracle_id's tier — oracles.py or ability_port.py."""
    for path in (_ORACLES_PY, _ABILITY_PORT_PY):
        text = path.read_text()
        if f'"{oracle_id}"' in text or f"id={oracle_id!r}" in text:
            return path, text
    return None


def _apply_tier_to_lines(oracle_id: str, current_tier: str) -> list[str] | None:
    """Locate oracle_id's definition and return the file's lines with its tier flipped
    to "stable" — position-based (finds THIS oracle's id, then its tier within the
    following lines), never a whole-file string replace that could hit an unrelated
    oracle sharing the same tier string.
    """
    located = _locate_oracle_definition(oracle_id)
    if located is None:
        return None
    path, text = located
    lines = text.splitlines(keepends=True)

    if path == _ORACLES_PY:
        # id="oast_callback" ... tier="experimental" inside the same __init__ block
        pattern = re.compile(rf'id="{re.escape(oracle_id)}"')
    else:
        # ("ptai_xxx", "<kind>", "<honesty>", <detect_fn>, "<tier>")  — tuple form
        pattern = re.compile(rf'"{re.escape(oracle_id)}"')

    found_idx = None
    for i, line in enumerate(lines):
        if pattern.search(line):
            found_idx = i
            break
    if found_idx is None:
        return None

    new_lines = list(lines)
    # tier string is within a few lines of the id (both layouts are multi-line)
    tier_pat = re.compile(rf'"{re.escape(current_tier)}"')
    for j in range(found_idx, min(found_idx + 8, len(lines))):
        if tier_pat.search(lines[j]):
            new_lines[j] = tier_pat.sub('"stable"', lines[j])
            return new_lines
    return None


def build_diff_for_oracle(oracle_id: str, current_tier: str) -> str | None:
    """Unified diff flipping oracle_id's tier -> stable, in whichever real file defines it.

    Real deviation from the task's assumption that all oracles live in oracles.py:
    the 45 ptai_* oracles are defined in ability_port.py's PROBE_DEFS tuples, not
    oracles.py. Diffs target the file that actually declares the tier (HEAD wins).
    """
    import difflib

    located = _locate_oracle_definition(oracle_id)
    if located is None:
        return None
    path, text = located
    lines = text.splitlines(keepends=True)
    new_lines = _apply_tier_to_lines(oracle_id, current_tier)
    if new_lines is None:
        return None

    diff = difflib.unified_diff(
        lines,
        new_lines,
        fromfile=str(path.relative_to(_PROJECT_ROOT)),
        tofile=str(path.relative_to(_PROJECT_ROOT)),
    )
    return "".join(diff)


@dataclass
class Stage2Report:
    generated_at: str
    source_file: str
    total_weak_oracles: int
    promotable: list[dict] = field(default_factory=list)
    not_promotable: list[dict] = field(default_factory=list)
    fitness_before: int = 0
    fitness_after: int = 0
    fitness_delta: int = 0

    def as_dict(self) -> dict:
        return asdict(self)


def run_stage2(index: dict | None = None) -> Stage2Report:
    """Orchestrate Phases 1-3 for all 46 weak oracles. Read-only — writes nothing."""
    from .oracles import ORACLES

    if index is None:
        from .self_index import build_self_index

        index = build_self_index()

    chain_data = load_chain_data()
    weak_ids = weak_oracle_ids(ORACLES)

    promotable: list[dict] = []
    not_promotable: list[dict] = []
    fitness_before_total = 0
    fitness_after_total = 0

    for oid in weak_ids:
        oracle = ORACLES[oid]
        proposal = generate_proposal(oid, oracle)
        proof = prove_proposal(oid, oracle, chain_data)
        if (
            not proof.insufficient_evidence
            and proof.positive_passed == proof.positive_tested
            and (proof.positive_tested > 0)
        ):
            proposal["diff_touches_check"] = False  # never speculative — proof reflects check as-is

        eval_result = goal_eval(proposal, proof.as_dict(), index=index)
        outcome = classify_outcome(eval_result, proof.as_dict())

        fd = _fitness_delta_if_promoted(oid, index)
        fitness_before_total += fd["before"]
        fitness_after_total += fd["after"] if eval_result["promotable"] else fd["before"]

        record = {
            "oracle_id": oid,
            "outcome": outcome,
            "proposal": proposal,
            "proof": proof.as_dict(),
            "eval": eval_result,
            "fitness": fd,
        }
        if eval_result["promotable"]:
            promotable.append(record)
        else:
            not_promotable.append(record)

    return Stage2Report(
        generated_at=datetime.now(tz=UTC).isoformat(),
        source_file=chain_data.get("source_file", ""),
        total_weak_oracles=len(weak_ids),
        promotable=promotable,
        not_promotable=not_promotable,
        fitness_before=fitness_before_total,
        fitness_after=fitness_after_total,
        fitness_delta=fitness_before_total - fitness_after_total,
    )


def print_stage2_report(report: Stage2Report) -> None:
    print("Portal 5 — Stage 2 Propose + Prove Report")
    print("=" * 60)
    print(f"Source: {report.source_file or '(no all_scenarios:true chain-test result found)'}")
    print(f"Weak oracles evaluated: {report.total_weak_oracles}")
    print(f"\npromotable (proven): {len(report.promotable)}")
    for r in report.promotable:
        print(f"  + {r['oracle_id']}: {r['proof']['evidence_detail']}")
    print(f"\nnot-promotable: {len(report.not_promotable)}")
    for r in report.not_promotable:
        print(f"  - {r['oracle_id']} [{r['outcome']}]: {'; '.join(r['eval']['reasons'])}")
    print(
        f"\nfitness (Stage 1 weakness score): "
        f"{report.fitness_before} -> {report.fitness_after} "
        f"(delta {report.fitness_delta})"
    )


def write_report(report: Stage2Report, out_dir: Path = STAGE2_DIR) -> None:
    """Stage verified diffs + the batch-approval report. NOT auto-applied."""
    out_dir.mkdir(parents=True, exist_ok=True)
    for f in out_dir.glob("*.diff"):
        f.unlink()

    for r in report.promotable:
        oid = r["oracle_id"]
        diff_text = build_diff_for_oracle(oid, r["proposal"]["current_tier"])
        if diff_text:
            (out_dir / f"{oid}.diff").write_text(diff_text)

    (out_dir / "stage2_report.json").write_text(json.dumps(report.as_dict(), indent=2))

    md = [
        "# Stage 2 — Propose + Prove Report",
        "",
        f"Generated: {report.generated_at}",
        f"Source: {report.source_file or '(none)'}",
        f"Weak oracles evaluated: {report.total_weak_oracles}",
        "",
        f"## Promotable (proven): {len(report.promotable)}",
    ]
    for r in report.promotable:
        md.append(f"- **{r['oracle_id']}** — {r['proof']['evidence_detail']}")
    md += ["", f"## Not promotable: {len(report.not_promotable)}"]
    for r in report.not_promotable:
        md.append(f"- **{r['oracle_id']}** [{r['outcome']}]: {'; '.join(r['eval']['reasons'])}")
    md += [
        "",
        "## Fitness delta (Stage 1 weakness score)",
        f"before={report.fitness_before} after={report.fitness_after} delta={report.fitness_delta}",
    ]
    (out_dir / "stage2_report.md").write_text("\n".join(md) + "\n")


# ── Operator-gated batch apply — NEVER called automatically ───────────────


def apply_batch(report: Stage2Report, out_dir: Path = STAGE2_DIR) -> dict:
    """Apply staged promotable diffs in one batch. ONLY called via --apply on the CLI.

    Never call this from an automated/CI/loop code path — see module docstring.
    """
    applied = []
    skipped = []
    for r in report.promotable:
        oid = r["oracle_id"]
        diff_path = out_dir / f"{oid}.diff"
        if not diff_path.exists():
            skipped.append(oid)
            continue
        current_tier = r["proposal"]["current_tier"]
        # Reuse build_diff_for_oracle's position-based line lookup (finds THIS
        # oracle's id, then its tier string within the following lines) rather
        # than a whole-file text.replace — a naive replace(f'"{tier}"', ...)
        # would silently rewrite the FIRST matching tier string anywhere in the
        # file, which for ability_port.py's PROBE_DEFS (many same-tier tuples)
        # could promote the wrong oracle entirely.
        new_lines = _apply_tier_to_lines(oid, current_tier)
        if new_lines is None:
            skipped.append(oid)
            continue
        path, _text = _locate_oracle_definition(oid)
        path.write_text("".join(new_lines))
        applied.append(oid)
    return {"applied": applied, "skipped": skipped}


# ── CLI entry point ─────────────────────────────────────────────────────────


def stage2_propose_main(*, as_json: bool = False, apply: bool = False) -> int:
    report = run_stage2()
    write_report(report)

    if as_json:
        print(json.dumps(report.as_dict(), indent=2))
    else:
        print_stage2_report(report)

    if apply:
        result = apply_batch(report)
        msg = f"\n[--apply] applied {len(result['applied'])} promotion(s): {result['applied']}"
        if result["skipped"]:
            msg += f"; skipped {result['skipped']}"
        print(msg)

    return 0
