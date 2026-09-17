#!/usr/bin/env python3
"""WFE checkers — extracted from the runner so they can be unit-tested against
adversarial fixtures (dimension 20) rather than trusted.

Every checker here replaced a version that could return a false PASS:
  pytest_pass      : old form returned True whenever "passed" appeared anywhere,
                     so "1 failed, 3 passed" scored as success
  file_exists /
  file_contains    : old form resolved misses against the real repo, so a
                     checker could be satisfied by a file the model never wrote
  transcript_contains: old form matched the whole transcript INCLUDING tool-call
                     arguments, so repo_search("CONTRADICTED") scored the task
  (all pytest)     : graded tests lived in a model-writable sandbox
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from tests.wfe.schema import Outcome

REPO = Path(__file__).resolve().parents[2]
GRADED_ROOT = REPO / "tests" / "wfe" / "graded"

REFUSAL_PATTERNS = [
    r"\bI (?:can(?:no|')t|won'?t|am unable to|'m unable to)\b",
    r"\bI (?:must|have to) (?:decline|refuse)\b",
    r"\bas an AI\b.{0,60}\b(?:cannot|can't|unable)\b",
    r"\bI'?m sorry,? but\b.{0,80}\b(?:cannot|can't|won'?t|unable)\b",
]


@dataclass
class CheckResult:
    outcome: Outcome
    notes: str
    evidence: dict


@dataclass
class CheckContext:
    """Everything a checker may look at. Note the deliberate separation of
    final_text from tool output: answers must come from the model, not be
    echoed out of a file it read."""

    final_text: str = ""
    assistant_texts: list = None
    tool_calls: list = None  # [{name, args, output, error}]
    sandbox_root: Path | None = None
    task: dict = None
    finish_reason: str | None = None

    def __post_init__(self):
        self.assistant_texts = self.assistant_texts or []
        self.tool_calls = self.tool_calls or []
        self.task = self.task or {}

    def tool_outputs(self) -> str:
        return "\n".join(str(c.get("output", "")) for c in self.tool_calls)

    def tool_args_blob(self) -> str:
        return "\n".join(str(c.get("args", "")) for c in self.tool_calls)


# --------------------------------------------------------------------------
# pytest
# --------------------------------------------------------------------------

_COUNT_RE = re.compile(r"(\d+)\s+(passed|failed|errors?|skipped|xfailed|xpassed)")


def parse_pytest_summary(out: str) -> dict:
    """Parse pytest's terminal summary into explicit counts.

    Returns {passed, failed, errors, skipped, no_tests, internal_error, line}.
    """
    res = {
        "passed": 0,
        "failed": 0,
        "errors": 0,
        "skipped": 0,
        "no_tests": False,
        "internal_error": False,
        "line": "",
    }
    if not out:
        return res
    if "INTERNALERROR" in out:
        res["internal_error"] = True
    lines = [ln.strip() for ln in out.strip().splitlines() if ln.strip()]
    summary = ""
    for ln in reversed(lines):
        if re.search(r"\b(passed|failed|error|errors|no tests ran)\b", ln):
            summary = ln
            break
    res["line"] = summary
    if "no tests ran" in summary:
        res["no_tests"] = True
    for num, kind in _COUNT_RE.findall(summary):
        key = "errors" if kind.startswith("error") else kind
        if key in res:
            res[key] += int(num)
    return res


def _pytest_verdict(out: str, min_passed: int) -> tuple[bool, str]:
    s = parse_pytest_summary(out)
    if s["internal_error"]:
        return False, f"pytest INTERNALERROR: {s['line']}"
    if s["no_tests"]:
        return False, "no tests ran"
    ok = s["failed"] == 0 and s["errors"] == 0 and s["passed"] >= min_passed
    return ok, (
        f"passed={s['passed']} failed={s['failed']} errors={s['errors']} "
        f"min_passed={min_passed} :: {s['line'][:160]}"
    )


def _run_pytest(cwd: Path, args: str = "", timeout: int = 240) -> str:
    try:
        r = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                "-q",
                "-p",
                "no:cacheprovider",
                "--import-mode=importlib",
                *(args.split() if args else []),
            ],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(cwd),
        )
        return (r.stdout or "") + (r.stderr or "")
    except subprocess.TimeoutExpired:
        return "INTERNALERROR: pytest timed out"
    except Exception as e:  # pragma: no cover - defensive
        return f"INTERNALERROR: {e}"


def check_pytest_pass(spec: dict, ctx: CheckContext) -> CheckResult:
    """Run the model's own tests. Weak signal — the model authored them — so
    suites should prefer hidden_pytest. Kept for smoke use only."""
    out = _run_pytest(ctx.sandbox_root, spec.get("pytest_args", ""))
    ok, notes = _pytest_verdict(out, int(spec.get("min_passed", 1)))
    return CheckResult(Outcome.PASS if ok else Outcome.FAIL, notes, {"pytest_tail": out[-800:]})


def check_hidden_pytest(spec: dict, ctx: CheckContext) -> CheckResult:
    """Grade the model's implementation against tests it never saw and cannot
    write to. Closes the reward-hacking hole in the original coding suite,
    where the model authored both the implementation and its own grader."""
    graded_dir = GRADED_ROOT / spec["graded"]
    if not graded_dir.is_dir():
        return CheckResult(Outcome.HARNESS_ERROR, f"graded suite missing: {graded_dir}", {})
    impl = list(spec.get("impl_files") or [])
    tmp = Path(tempfile.mkdtemp(prefix="wfe_graded_"))
    try:
        missing = []
        for rel in impl:
            src = ctx.sandbox_root / rel
            if not src.is_file():
                missing.append(rel)
                continue
            dst = tmp / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
        if missing:
            return CheckResult(
                Outcome.FAIL,
                f"implementation not produced: {missing}",
                {"missing": missing},
            )
        for gf in graded_dir.glob("test_*.py"):
            shutil.copy2(gf, tmp / gf.name)
        out = _run_pytest(tmp, spec.get("pytest_args", ""))
        ok, notes = _pytest_verdict(out, int(spec.get("min_passed", 1)))
        return CheckResult(
            Outcome.PASS if ok else Outcome.FAIL,
            f"hidden-suite {spec['graded']}: {notes}",
            {"pytest_tail": out[-800:]},
        )
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def check_immutable(spec: dict, ctx: CheckContext) -> CheckResult:
    """Seeded files the model must not rewrite. Rewriting the grader is the
    cheapest path to a green result; this makes it a FAIL instead."""
    bad = []
    for rel, want in (spec.get("hashes") or {}).items():
        f = ctx.sandbox_root / rel
        if not f.is_file():
            bad.append(f"{rel}: deleted")
            continue
        got = hashlib.sha256(f.read_bytes()).hexdigest()[:16]
        if got != want:
            bad.append(f"{rel}: mutated ({got} != {want})")
    if bad:
        return CheckResult(Outcome.FAIL, "graded fixture tampered: " + "; ".join(bad), {})
    return CheckResult(Outcome.PASS, "seeded fixtures intact", {})


# --------------------------------------------------------------------------
# files
# --------------------------------------------------------------------------


def _sandbox_only(ctx: CheckContext, rel: str) -> Path | None:
    """Resolve strictly inside the sandbox. The pre-repair checkers used the
    runner's tool resolver, which falls back to the real repo on a miss."""
    root = Path(ctx.sandbox_root).resolve()
    p = (root / rel).resolve()
    try:
        p.relative_to(root)
    except ValueError:
        return None
    return p


def check_file_exists(spec: dict, ctx: CheckContext) -> CheckResult:
    f = _sandbox_only(ctx, spec["path"])
    ok = bool(f and f.is_file() and f.stat().st_size > 0)
    return CheckResult(
        Outcome.PASS if ok else Outcome.FAIL,
        f"sandbox file {spec['path']} exists={ok}",
        {},
    )


def check_file_contains(spec: dict, ctx: CheckContext) -> CheckResult:
    f = _sandbox_only(ctx, spec["path"])
    if not f or not f.is_file():
        return CheckResult(Outcome.FAIL, f"sandbox file {spec['path']} missing", {})
    body = f.read_text(errors="ignore")
    missing = [p for p in (spec.get("patterns") or []) if not re.search(p, body)]
    ok = not missing
    return CheckResult(
        Outcome.PASS if ok else Outcome.FAIL,
        f"patterns matched={ok}" + (f" missing={missing}" if missing else ""),
        {},
    )


# --------------------------------------------------------------------------
# answer content
# --------------------------------------------------------------------------


def check_answer_contains(spec: dict, ctx: CheckContext) -> CheckResult:
    """Patterns must appear in the MODEL'S ANSWER, not anywhere in the
    transcript. The original matched final_text + json.dumps(transcript), and
    transcript rows carry tool-call arguments — so a model that merely searched
    for the expected string scored the task."""
    text = ctx.final_text or ""
    missing = [p for p in (spec.get("patterns") or []) if not re.search(p, text, re.I)]
    ev = {}
    leaked = [
        p
        for p in (spec.get("forbid_in_tool_output") or [])
        if re.search(p, ctx.tool_outputs(), re.I)
    ]
    if leaked:
        ev["leak_detected"] = leaked
        return CheckResult(
            Outcome.HARNESS_ERROR,
            f"answer key leaked into tool output ({leaked}) — task is contaminated, "
            f"not a model result",
            ev,
        )
    if missing:
        return CheckResult(Outcome.FAIL, f"answer missing patterns={missing}", ev)
    forbidden = [p for p in (spec.get("forbid") or []) if re.search(p, text, re.I)]
    if forbidden:
        return CheckResult(Outcome.FAIL, f"answer contains forbidden={forbidden}", ev)
    return CheckResult(Outcome.PASS, "answer patterns matched", ev)


def check_cited_answer(spec: dict, ctx: CheckContext) -> CheckResult:
    """A citation only counts when the model's ANSWER carries a URL whose host
    was actually fetched successfully during the run. The original accepted any
    URL-shaped string anywhere in the transcript, including inside a failed
    http_get argument."""
    base = check_answer_contains(spec, ctx)
    if base.outcome != Outcome.PASS:
        return base
    urls = re.findall(r"https?://[^\s)\"'<>\]]+", ctx.final_text or "")
    if not urls:
        return CheckResult(Outcome.FAIL, "no citation URL in the answer", {})
    fetched_hosts = set()
    for c in ctx.tool_calls:
        if c.get("name") != "http_get":
            continue
        out = str(c.get("output", ""))
        if out.startswith("ERROR:") or c.get("error"):
            continue
        for u in re.findall(r"https?://[^\s)\"'<>\]]+", str(c.get("args", ""))):
            fetched_hosts.add(urlparse(u).netloc.lower())
    cited_hosts = {urlparse(u).netloc.lower() for u in urls}
    grounded = cited_hosts & fetched_hosts
    if not grounded:
        return CheckResult(
            Outcome.FAIL,
            f"citation not grounded: cited {sorted(cited_hosts)} but successfully "
            f"fetched {sorted(fetched_hosts) or 'nothing'}",
            {"cited": sorted(cited_hosts), "fetched": sorted(fetched_hosts)},
        )
    return CheckResult(
        Outcome.PASS,
        f"answer cites fetched host(s) {sorted(grounded)}",
        {"grounded_hosts": sorted(grounded)},
    )


def check_human_review(spec: dict, ctx: CheckContext) -> CheckResult:
    """Creative lane. Returns PENDING_REVIEW so the row is quarantined out of
    every rate rather than silently counted as a failure — the original
    counted None as not-completed, which scored creative arms 0/n by
    construction."""
    if not (ctx.final_text or "").strip():
        return CheckResult(Outcome.FAIL, "empty response", {})
    return CheckResult(
        Outcome.PENDING_REVIEW,
        "queued for blinded operator review",
        {"rubric": spec.get("rubric", []), "word_count": len((ctx.final_text or "").split())},
    )


def _receipt_from_calls(tool_calls: list) -> dict | None:
    """The reading's OWN receipt, out of the `compliance_ask` call that produced
    it — never the model's account of it.

    The checker used to score a JSON object the model wrote about its own run.
    A model that reports `closure_complete: true` and cites nothing scores the
    same as one that read the population, which makes the gate an instrument for
    measuring compliance with a reporting format.
    """
    decoder = json.JSONDecoder()
    for call in reversed(list(tool_calls or [])):
        if "compliance_ask" not in str(call.get("name", "")):
            continue
        output = call.get("output")
        if isinstance(output, dict):
            payload = output
        else:
            payload = None
            for match in re.finditer(r"\{", str(output or "")):
                try:
                    candidate, _end = decoder.raw_decode(str(output)[match.start() :])
                except json.JSONDecodeError:
                    continue
                if isinstance(candidate, dict) and "closure_receipt" in candidate:
                    payload = candidate
                    break
        if isinstance(payload, dict) and "closure_receipt" in payload:
            return payload
    return None


def _resolved_citations(receipt: dict) -> list[dict]:
    citations = ((receipt.get("verification") or {}).get("citations")) or []
    return [c for c in citations if isinstance(c, dict) and c.get("resolved") is True]


def _ground_truth_sections(spec: dict) -> list[str]:
    """The labelled sections this reading is expected to cite.

    ``ground_truth_sections`` states them outright. ``ground_truth_requirement``
    resolves them from the evaluation set — the APPROVED mappings, which is the
    only ground truth the module recognises — so the gate starts scoring recall
    the moment a human settles a proposal, without the suite being re-edited.

    An unavailable or empty label set returns nothing, and the caller reports
    honest-BLOCKED rather than a pass.
    """
    stated = [str(s) for s in (spec.get("ground_truth_sections") or [])]
    if stated:
        return stated
    requirement = str(spec.get("ground_truth_requirement", ""))
    if not requirement:
        return []
    try:
        from portal.modules.compliance.core.evaluation import as_eval_set, labelled_examples
        from portal.modules.compliance.core.repository import Repository
    except Exception:  # noqa: BLE001 - the checker must run without the module installed
        return []
    repo = Repository()
    try:
        eval_set = as_eval_set(labelled_examples(repo))
    except Exception:  # noqa: BLE001 - no labels is not a bad reading, and not a pass
        return []
    finally:
        repo.close()
    for example in eval_set.get("examples", []):
        if str(example.get("requirement_id", "")) == requirement:
            return [str(s) for s in example.get("expected_sections", [])]
    return []


def check_compliance_reading_contract(spec: dict, ctx: CheckContext) -> CheckResult:
    """Score the mechanical reading contract from what was OBSERVED.

    Every sub-check reads either the transcript's own tool calls or the receipt
    `compliance_ask` returned. Three ways this previously reported a false PASS,
    each reproduced before it was fixed:

    * `payload["closure_complete"] is (not unread)` is TRUE when the model
      reports `false` with a non-empty unread list — an explicitly incomplete
      closure passed as a satisfied one. What is required in its place is
      `accounted_for`: every eligible section read, or NAMED as not-read. A
      strict `unread == []` fails a reading that declares the one section it
      skipped and says why, which is the contract being complied with — measured
      on three live Part 2.2 runs, all three did exactly that;
    * citations were only checked for `resolved is not True`, so an empty
      citation list passed every time;
    * `first_tool` was whatever the model said it was; `ctx.tool_calls` was
      never looked at, so a run with no tool calls at all could pass.

    `ground_truth_sections` is required because the suite has always asked the
    model for `ground_truth_section_hits` and nothing ever checked it. With no
    labels for this requirement the reading is NOT scored — that is the
    evaluation set's own `honest-BLOCKED` discipline, and a gate that passed
    instead would qualify a seat against nothing.
    """
    calls = list(ctx.tool_calls or [])
    compliance_calls = [c for c in calls if str(c.get("name", "")).find("compliance_") >= 0]
    if not compliance_calls:
        return CheckResult(
            Outcome.FAIL,
            "no compliance tool was called: nothing was read",
            {"tool_calls": [str(c.get("name", "")) for c in calls]},
        )

    receipt = _receipt_from_calls(calls)
    if receipt is None:
        return CheckResult(
            Outcome.FAIL,
            "no compliance_ask receipt in the transcript — the contract cannot be "
            "scored from the model's own account of it",
            {"tools_called": [str(c.get("name", "")) for c in compliance_calls]},
        )

    closure = receipt.get("closure_receipt") or {}
    resolved = _resolved_citations(receipt)
    unresolved = [
        c
        for c in ((receipt.get("verification") or {}).get("citations") or [])
        if isinstance(c, dict) and c.get("resolved") is not True
    ]
    eligible = set(closure.get("eligible") or [])
    operator_eligible = set(closure.get("operator_eligible") or [])
    cited = {str(c.get("cited_ref", "")) for c in resolved}
    regulatory_cited = [c for c in resolved if str(c.get("jurisdiction", "")) not in ("internal",)]
    operator_cited = [c for c in resolved if str(c.get("jurisdiction", "")) == "internal"]

    expected_first = str(spec.get("expected_first_tool", "compliance_requirement"))
    first_tool = str(compliance_calls[0].get("name", ""))
    ground_truth = _ground_truth_sections(spec)

    checks = {
        "tool_selection": first_tool.endswith(expected_first),
        "reading_did_not_fail": receipt.get("failed") is False,
        # Everything eligible was READ, or NAMED as not-read with a reason. A
        # strict `unread == []` fails a reading that explicitly declares the one
        # section it skipped and why, which is the contract being complied with.
        # `complete` stays in the evidence, unweakened, so a declared omission is
        # visible as one rather than passing as a full read.
        "closure_accounted_for": closure.get("accounted_for") is True,
        "no_undeclared_unread": not (closure.get("undeclared_unread") or []),
        "citation_resolution": bool(resolved) and not unresolved,
        "regulatory_citation": bool(regulatory_cited),
        "nothing_cited_outside_scope": not (closure.get("outside") or []),
    }
    # An operator citation is required wherever the population HAS an operator
    # side: a posture answer that never cites the operator's own documents is
    # about the standard, not about the operator.
    if operator_eligible:
        checks["operator_citation"] = bool(operator_cited)
    if ground_truth:
        checks["ground_truth_citation_recall"] = set(ground_truth) <= cited

    evidence = {
        "reading_contract": checks,
        "first_tool": first_tool,
        "model_tool_calls": closure.get("model_tool_calls"),
        "eligible": len(eligible),
        "closure_complete": closure.get("complete"),
        "unread": closure.get("unread") or [],
        "omitted_with_reason": closure.get("omitted_with_reason") or [],
        "undeclared_unread": closure.get("undeclared_unread") or [],
        "outside": closure.get("outside") or [],
        "resolved_citations": len(resolved),
        "unresolved_citations": unresolved,
        "operator_citations": len(operator_cited),
        "ground_truth_missing": sorted(set(ground_truth) - cited),
        "failure": receipt.get("failure", ""),
    }
    if not ground_truth:
        return CheckResult(
            Outcome.PENDING_REVIEW,
            "honest-BLOCKED: no ground-truth sections are labelled for this "
            "requirement, so citation recall cannot be scored",
            evidence,
        )
    ok = all(checks.values())
    return CheckResult(
        Outcome.PASS if ok else Outcome.FAIL,
        "reading contract passed"
        if ok
        else f"reading contract failed={[k for k, v in checks.items() if not v]}",
        evidence,
    )


CHECKERS = {
    "pytest_pass": check_pytest_pass,
    "hidden_pytest": check_hidden_pytest,
    "immutable": check_immutable,
    "file_exists": check_file_exists,
    "file_contains": check_file_contains,
    "answer_contains": check_answer_contains,
    "cited_answer": check_cited_answer,
    "human_review": check_human_review,
    "compliance_reading_contract": check_compliance_reading_contract,
}


def detect_refusal(text: str) -> bool:
    return any(re.search(p, text or "", re.I) for p in REFUSAL_PATTERNS)


def apply_checkers(task: dict, ctx: CheckContext) -> CheckResult:
    """Apply every checker on the task; ALL must pass. Precedence for non-PASS:
    HARNESS_ERROR > FAIL, so a contaminated task never reads as a model verdict.
    """
    specs = task.get("checkers")
    if specs is None:
        specs = [task.get("checker") or {"type": "answer_contains"}]
    results = []
    for spec in specs:
        name = spec.get("type", "answer_contains")
        fn = CHECKERS.get(name)
        if fn is None:
            results.append(CheckResult(Outcome.HARNESS_ERROR, f"unknown checker {name}", {}))
            continue
        try:
            results.append(fn(spec, ctx))
        except Exception as e:
            results.append(CheckResult(Outcome.HARNESS_ERROR, f"checker {name} raised: {e}", {}))
    evidence = {}
    for r in results:
        evidence.update(r.evidence)
    notes = " | ".join(r.notes for r in results)
    for level in (Outcome.HARNESS_ERROR, Outcome.PENDING_REVIEW, Outcome.FAIL):
        if any(r.outcome == level for r in results):
            if level == Outcome.FAIL and detect_refusal(ctx.final_text):
                return CheckResult(Outcome.REFUSED, "model refused | " + notes, evidence)
            if level == Outcome.FAIL and ctx.finish_reason in ("length", "max_tokens"):
                return CheckResult(
                    Outcome.TRUNCATED, "output truncated at token cap | " + notes, evidence
                )
            return CheckResult(level, notes, evidence)
    return CheckResult(Outcome.PASS, notes, evidence)
