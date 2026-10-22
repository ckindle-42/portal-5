"""Orchestration-arm principle checks (Phase 3).

The arm's design principles are prose unless a gate reads them. These checks
read the arm's own config, suites and request builders: the read/action split a
bite plan must obey, thinking on for every arm model request, the suites and
written pass criteria every configured discipline needs, the Gate C threshold
and its unattended refusal, per-bite tool mounting, and path-only inputs with
the procedure in context.
"""

from __future__ import annotations

import ast
import json
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

import yaml

from ._shared import REPO_ROOT
from .registry import register

_SUPPRESSION_KEYS = {"enable_thinking", "reasoning_effort", "think", "thinking"}
_SUPPRESSED_WORDS = {"disabled", "false", "none", "off"}


def _arm_config(root: Path) -> dict[str, Any]:
    path = root / "config" / "orchestration_arm.yaml"
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise ValueError("config/orchestration_arm.yaml must be a mapping")
    return raw


def _disciplines(config: dict[str, Any]) -> dict[str, Any]:
    value = config.get("disciplines")
    return value if isinstance(value, dict) else {}


def _strings(value: Any) -> list[str]:
    return [item for item in value if isinstance(item, str)] if isinstance(value, list) else []


def _seeded_plan(
    discipline: str,
    tools: list[str],
    *,
    reads_untrusted: bool = False,
    inputs: tuple[str, ...] = (),
    procedure: str = "Follow the bite procedure.",
) -> dict[str, Any]:
    """A minimal valid plan whose work bite carries the seeded tool set."""

    def bite(
        bite_id: str, stage: str, bite_tools: list[str], depends: list[str], *, review: bool = False
    ) -> dict[str, Any]:
        raw: dict[str, Any] = {
            "bite_id": bite_id,
            "goal": f"Complete {bite_id}.",
            "discipline": discipline,
            "inputs": list(inputs) if bite_id == "work" else [],
            "depends_on": depends,
            "tools": bite_tools,
            "output": {"path": f"bites/{bite_id}.json", "schema": {"type": "object"}},
            "accept": [{"type": "exists"}],
            "risk": "low",
            "stage": stage,
            "budget": {"turns": 2, "minutes": 2, "output_tokens": 128, "context_tokens": 512},
            "model": "fast",
            "procedure": procedure if bite_id == "work" else "Assemble and review.",
            "reads_untrusted": reads_untrusted if bite_id == "work" else False,
        }
        if review:
            raw["accept"] = []
            raw["review"] = "deep"
            raw["review_reason"] = "Seeded check needs model judgment."
        return raw

    return {
        "task_id": "validate-seed",
        "goal": "Exercise the arm validator.",
        "bites": [
            bite("work", "work", tools, []),
            bite("assembly", "assembly", [], ["work"]),
            bite("final", "final_review", [], ["assembly"], review=True),
        ],
    }


def _validator_case(
    validate: Callable[..., Any],
    config: dict[str, Any],
    discipline: str,
    tools: list[str],
    name: str,
    *,
    reads_untrusted: bool = False,
    expect_accepted: bool = False,
) -> dict[str, Any]:
    try:
        validate(
            _seeded_plan(discipline, tools, reads_untrusted=reads_untrusted), config, discipline
        )
        error = None
    except ValueError as exc:
        error = str(exc)
    ok = error is None if expect_accepted else bool(error and "reading and acting" in error)
    return {"name": name, "status": "PASS" if ok else "FAIL", "detail": error or "accepted"}


@register("arm_reading_no_write", "HR. arm reading bites hold no write tools", order=207)
def check_arm_reading_bites_hold_no_write_tools() -> tuple[str, str, list[dict]]:
    """HR. A reading-side tool and an action-side tool never share one bite.

    Also requires every allowlisted tool to be classified as one side or the
    other: an unclassified tool is invisible to the validator's split, so a
    write-capable or messaging tool could ride a reading bite unnoticed.
    """
    from portal.modules.orchestration.planner import validate_planned_plan

    config = _arm_config(REPO_ROOT)
    disciplines = _disciplines(config)
    if not disciplines:
        return ("FAIL", "no disciplines configured in config/orchestration_arm.yaml", [])

    subs: list[dict] = []
    bad: list[str] = []
    for name, raw in sorted(disciplines.items()):
        if not isinstance(raw, dict):
            bad.append(f"{name}: discipline must be a mapping")
            continue
        tools = _strings(raw.get("tool_allowlist"))
        reads = _strings(raw.get("read_tools"))
        actions = _strings(raw.get("action_tools"))
        problems: list[str] = []
        if sorted(set(reads) & set(actions)):
            problems.append(f"read/action overlap {sorted(set(reads) & set(actions))}")
        if sorted(set(tools) - set(reads) - set(actions)):
            problems.append(f"unclassified tools {sorted(set(tools) - set(reads) - set(actions))}")
        if sorted((set(reads) | set(actions)) - set(tools)):
            problems.append(
                f"classified but not allowlisted {sorted((set(reads) | set(actions)) - set(tools))}"
            )
        subs.append(
            {
                "name": f"{name}: read/action classes are disjoint and complete",
                "status": "PASS" if not problems else "FAIL",
                "detail": "; ".join(problems) or f"{len(reads)} read, {len(actions)} action",
            }
        )
        if problems:
            bad.append(f"{name}: {'; '.join(problems)}")
            continue
        if reads and actions:
            subs.append(
                _validator_case(
                    validate_planned_plan,
                    config,
                    name,
                    [reads[0], actions[0]],
                    f"{name}: mixed read+write bite rejected",
                )
            )
            subs.append(
                _validator_case(
                    validate_planned_plan,
                    config,
                    name,
                    [actions[0]],
                    f"{name}: untrusted reading bite with an action tool rejected",
                    reads_untrusted=True,
                )
            )
            subs.append(
                _validator_case(
                    validate_planned_plan,
                    config,
                    name,
                    [reads[0]],
                    f"{name}: reading-only bite accepted",
                    expect_accepted=True,
                )
            )
        else:
            subs.append(
                {
                    "name": f"{name}: reading bites are impossible",
                    "status": "PASS",
                    "detail": "no read and action pair to split",
                }
            )
    if bad:
        return ("FAIL", "; ".join(bad), subs)
    return ("PASS", f"{len(disciplines)} discipline(s) keep reading and acting apart", subs)


def _literal(node: ast.expr) -> Any:
    try:
        return ast.literal_eval(node)
    except (SyntaxError, ValueError):
        return None


def _suppressed(key: str, value: Any) -> bool:
    if key == "reasoning_effort":
        return isinstance(value, str) and value.strip().lower() in _SUPPRESSED_WORDS
    if isinstance(value, str):
        return value.strip().lower() in _SUPPRESSED_WORDS
    return value is False or value == 0


def _request_body_findings(module_dir: Path) -> tuple[list[str], int]:
    findings: list[str] = []
    bodies = 0
    for path in sorted(module_dir.rglob("*.py")):
        relative = path.relative_to(module_dir)
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError as exc:
            findings.append(f"{relative}: cannot parse ({exc.msg})")
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Dict):
                continue
            fields = {
                key.value: value
                for key, value in zip(node.keys, node.values, strict=False)
                if isinstance(key, ast.Constant) and isinstance(key.value, str)
            }
            for key, value in fields.items():
                if key in _SUPPRESSION_KEYS and _suppressed(key, _literal(value)):
                    findings.append(f"{relative}: {key}={ast.unparse(value)}")
            if {"model", "messages"} <= set(fields):
                bodies += 1
                thinking = _literal(fields.get("chat_template_kwargs"))
                if not isinstance(thinking, dict) or thinking.get("enable_thinking") is not True:
                    findings.append(f"{relative}: model request omits enable_thinking=True")
    return findings, bodies


def _yaml_documents(root: Path) -> list[tuple[str, Any]]:
    documents: list[tuple[str, Any]] = []
    arm = root / "config" / "orchestration_arm.yaml"
    documents.append(("config/orchestration_arm.yaml", _arm_config(root)))
    portal = root / "config" / "portal.yaml"
    if portal.is_file():
        raw = yaml.safe_load(portal.read_text(encoding="utf-8")) or {}
        if isinstance(raw, dict):
            documents.append(("config/portal.yaml#orchestration_arm", raw.get("orchestration_arm")))
    discipline_root = root / "portal" / "modules" / "orchestration" / "disciplines"
    if discipline_root.is_dir():
        for path in sorted(discipline_root.rglob("*.yaml")):
            raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            documents.append((str(path.relative_to(root)), raw))
    return documents


def _config_suppression_findings(root: Path) -> list[str]:
    findings: list[str] = []

    def walk(value: Any, where: str) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                if key in _SUPPRESSION_KEYS and _suppressed(key, item):
                    findings.append(f"{where}.{key}={item!r}")
                walk(item, f"{where}.{key}")
        elif isinstance(value, list):
            for index, item in enumerate(value):
                walk(item, f"{where}[{index}]")

    for name, document in _yaml_documents(root):
        walk(document, name)
    return findings


def _pipeline_bite_override_findings() -> list[str]:
    from portal.platform.inference.router import validation

    saved = validation.WORKSPACES
    body = {"portal_bite_tools": ["file_read"], "chat_template_kwargs": {"enable_thinking": True}}
    try:
        validation.WORKSPACES = {"arm_probe": {"think": False}}
        ollama = validation._inject_ollama_options(dict(body), "arm_probe")
        omlx = validation._inject_omlx_options(dict(body), "arm_probe")
    finally:
        validation.WORKSPACES = saved
    findings: list[str] = []
    if ollama.get("think") is not True:
        findings.append("Pipeline ollama transport does not force think for a bite request")
    if ollama.get("reasoning_effort") == "none":
        findings.append("Pipeline ollama transport still suppresses a bite request's reasoning")
    if (omlx.get("chat_template_kwargs") or {}).get("enable_thinking") is not True:
        findings.append("Pipeline omlx transport does not keep a bite request's thinking flag")
    return findings


@register("arm_thinking_on", "HS. arm model requests keep thinking on", order=208)
def check_arm_thinking_stays_on() -> tuple[str, str, list[dict]]:
    """HS. Every arm request enables thinking and no arm config suppresses it.

    The Pipeline's bite-request override is checked too: a seat's workspace card
    may say think:false, but a request carrying portal_bite_tools must still
    reason. Production seats without bite tools are deliberately out of scope.
    """
    subs: list[dict] = []
    bad: list[str] = []

    config_findings = _config_suppression_findings(REPO_ROOT)
    subs.append(
        {
            "name": "arm configs contain no reasoning suppression",
            "status": "PASS" if not config_findings else "FAIL",
            "detail": "; ".join(config_findings) or "no suppression keys set",
        }
    )
    bad += config_findings

    module_dir = REPO_ROOT / "portal" / "modules" / "orchestration"
    source_findings, bodies = _request_body_findings(module_dir)
    if bodies == 0:
        source_findings.append("no arm model request body found")
    subs.append(
        {
            "name": "every arm model request enables thinking",
            "status": "PASS" if not source_findings else "FAIL",
            "detail": "; ".join(source_findings) or f"{bodies} request body(s) verified",
        }
    )
    bad += source_findings

    override_findings = _pipeline_bite_override_findings()
    subs.append(
        {
            "name": "Pipeline keeps a bite request thinking over a think:false seat card",
            "status": "PASS" if not override_findings else "FAIL",
            "detail": "; ".join(override_findings) or "bite override wins on ollama and omlx",
        }
    )
    bad += override_findings

    if bad:
        return ("FAIL", f"{len(bad)} reasoning-suppression finding(s): {'; '.join(bad)}", subs)
    return ("PASS", f"{bodies} arm request body(s) keep thinking on", subs)


def _case_count(path: Path) -> int:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return 0
    if path.suffix == ".jsonl":
        return sum(
            1 for line in text.splitlines() if line.strip() and not line.lstrip().startswith("#")
        )
    try:
        document = yaml.safe_load(text) or {}
    except yaml.YAMLError:
        return 0
    cases = document.get("cases") if isinstance(document, dict) else document
    return len(cases) if isinstance(cases, list) else 0


@register(
    "arm_discipline_suites", "HT. arm disciplines declare suites and pass criteria", order=209
)
def check_arm_discipline_suites() -> tuple[str, str, list[dict]]:
    """HT. A configured discipline needs all three suites and written criteria.

    Scope is the arm's own discipline map: a suite directory the arm cannot
    select is a candidate artifact, not a runnable discipline.
    """
    disciplines = _disciplines(_arm_config(REPO_ROOT))
    if not disciplines:
        return ("FAIL", "no disciplines configured in config/orchestration_arm.yaml", [])

    subs: list[dict] = []
    bad: list[str] = []
    for name, raw in sorted(disciplines.items()):
        if not isinstance(raw, dict):
            bad.append(f"{name}: discipline must be a mapping")
            continue
        problems: list[str] = []
        for key in ("bite_suite", "planner_suite", "checker_suite"):
            declared = raw.get(key)
            if not isinstance(declared, str) or not declared.strip():
                problems.append(f"{key} missing")
                continue
            relative = Path(declared)
            if relative.is_absolute() or ".." in relative.parts:
                problems.append(f"{key} must stay inside the repo: {declared}")
            elif not (REPO_ROOT / relative).is_file():
                problems.append(f"{key} not found: {declared}")
            elif _case_count(REPO_ROOT / relative) < 1:
                problems.append(f"{key} declares no cases: {declared}")
        criteria = raw.get("pass_criteria")
        if not isinstance(criteria, dict) or not criteria:
            problems.append("pass_criteria missing or empty")
        subs.append(
            {
                "name": f"{name}: three suites and written pass criteria",
                "status": "PASS" if not problems else "FAIL",
                "detail": "; ".join(problems) or "bite, planner and checker suites + criteria",
            }
        )
        if problems:
            bad.append(f"{name}: {'; '.join(problems)}")
    if bad:
        return ("FAIL", "; ".join(bad), subs)
    return (
        "PASS",
        f"{len(disciplines)} configured discipline(s) carry all suites and criteria",
        subs,
    )


@register("arm_gate_c_threshold", "HU. arm Gate C threshold gates unattended runs", order=210)
def check_arm_gate_c_threshold() -> tuple[str, str, list[dict]]:
    """HU. The calibration threshold is null or a probability; null blocks unattended runs."""
    from portal.modules.orchestration.service import _require_calibration

    config = _arm_config(REPO_ROOT)
    calibration = config.get("calibration")
    subs: list[dict] = []
    bad: list[str] = []
    if not isinstance(calibration, dict) or "minimum_pass_probability" not in calibration:
        return ("FAIL", "calibration.minimum_pass_probability is not configured", [])
    value = calibration["minimum_pass_probability"]
    valid = value is None or (
        isinstance(value, (int, float)) and not isinstance(value, bool) and 0 <= value <= 1
    )
    subs.append(
        {
            "name": "threshold is null or a probability in [0, 1]",
            "status": "PASS" if valid else "FAIL",
            "detail": repr(value),
        }
    )
    if not valid:
        bad.append(f"minimum_pass_probability={value!r}")

    if value is None:
        refused = False
        try:
            _require_calibration(config, True)
        except ValueError as exc:
            refused = "unattended runs are disabled" in str(exc)
        subs.append(
            {
                "name": "null threshold refuses an unattended run",
                "status": "PASS" if refused else "FAIL",
                "detail": "refused before dispatch"
                if refused
                else "unattended run was not refused",
            }
        )
        if not refused:
            bad.append("null threshold did not refuse unattended")
        interactive = True
        try:
            _require_calibration(config, False)
        except ValueError:
            interactive = False
        subs.append(
            {
                "name": "null threshold keeps interactive runs available",
                "status": "PASS" if interactive else "FAIL",
                "detail": "interactive run allowed" if interactive else "interactive run refused",
            }
        )
        if not interactive:
            bad.append("null threshold refused an interactive run")
    else:
        raised = None
        try:
            _require_calibration(config, True)
        except ValueError as exc:
            raised = str(exc)
        subs.append(
            {
                "name": "a configured threshold lets an unattended run through this gate",
                "status": "PASS" if raised is None else "FAIL",
                "detail": raised or "not refused",
            }
        )
        if raised is not None:
            bad.append(raised)

    if bad:
        return ("FAIL", "; ".join(bad), subs)
    return ("PASS", "Gate C threshold is configured and gates unattended runs", subs)


@register("arm_least_agency", "HV. arm requests mount only the bite's tools", order=211)
def check_arm_least_agency() -> tuple[str, str, list[dict]]:
    """HV. The request mounts the bite's tools; the validator rejects anything else."""
    from portal.modules.orchestration.contracts import parse_plan
    from portal.modules.orchestration.planner import validate_planned_plan
    from portal.modules.orchestration.worker import Engine, _request_body

    config = _arm_config(REPO_ROOT)
    disciplines = _disciplines(config)
    selected = next(
        (
            (name, raw)
            for name, raw in sorted(disciplines.items())
            if isinstance(raw, dict) and _strings(raw.get("tool_allowlist"))
        ),
        None,
    )
    if selected is None:
        return ("FAIL", "no configured discipline declares a tool allowlist", [])
    name, raw = selected
    allowed = _strings(raw["tool_allowlist"])
    engine = Engine(model_tag="probe", model_digest="probe", base_url="http://127.0.0.1:1")
    mount_failures: list[str] = []
    hop_failures: list[str] = []
    for tool in allowed:
        bite = parse_plan(_seeded_plan(name, [tool])).bites[0]
        body = _request_body(bite, engine, [])
        mounted = body.get("portal_bite_tools")
        if not (isinstance(mounted, list) and mounted == [*bite.tools, "finish"]):
            mount_failures.append(f"{tool}: mounted={mounted!r}")
        schemas = body.get("tools")
        schema_names = (
            [
                item.get("function", {}).get("name")
                for item in schemas
                if isinstance(item, dict) and isinstance(item.get("function"), dict)
            ]
            if isinstance(schemas, list)
            else []
        )
        if schema_names != [*bite.tools, "finish"]:
            mount_failures.append(f"{tool}: schemas={schema_names!r}")
        if body.get("portal_bite_max_hops") != bite.budget.turns:
            hop_failures.append(f"{tool}: max_hops={body.get('portal_bite_max_hops')!r}")
    mounted_ok = not mount_failures
    hops_ok = not hop_failures

    rejected = False
    try:
        validate_planned_plan(_seeded_plan(name, ["outside_allowlist_tool"]), config, name)
    except ValueError as exc:
        rejected = "tool outside discipline allowlist" in str(exc)

    subs = [
        {
            "name": "worker mounts exactly the bite's tools plus finish",
            "status": "PASS" if mounted_ok else "FAIL",
            "detail": "; ".join(mount_failures) or f"{len(allowed)} tool(s) mounted",
        },
        {
            "name": "worker applies the bite's turn budget",
            "status": "PASS" if hops_ok else "FAIL",
            "detail": "; ".join(hop_failures) or f"{len(allowed)} tool(s) budgeted",
        },
        {
            "name": "planner rejects a tool outside the discipline allowlist",
            "status": "PASS" if rejected else "FAIL",
            "detail": "rejected" if rejected else "accepted",
        },
    ]
    if not (mounted_ok and hops_ok and rejected):
        return ("FAIL", "per-bite tool mounting is not enforced", subs)
    return ("PASS", "requests carry only the bite's tools and turn budget", subs)


@register("arm_pull_notes", "HW. arm inputs are paths and procedures ride in context", order=212)
def check_arm_pull_not_prepack() -> tuple[str, str, list[dict]]:
    """HW. The worker receives input paths, never pre-packed contents, and the procedure."""
    from portal.modules.orchestration.contracts import parse_plan
    from portal.modules.orchestration.worker import _messages

    disciplines = _disciplines(_arm_config(REPO_ROOT))
    discipline = sorted(disciplines)[0] if disciplines else ""
    if not discipline:
        return ("FAIL", "no disciplines configured in config/orchestration_arm.yaml", [])
    marker = "ARM-PULL-MARKER-7f3c"
    procedure = "ARM-PROCEDURE-MARKER-91ad"
    with tempfile.TemporaryDirectory() as tmp:
        source = Path(tmp) / "source.txt"
        source.write_text(marker, encoding="utf-8")
        bite = parse_plan(
            _seeded_plan(discipline, [], inputs=("source.txt",), procedure=procedure)
        ).bites[0]
        messages = _messages(bite, {"source": source})
    serialized = json.dumps(messages)
    system = str(messages[0].get("content", "")) if messages else ""
    path_ok = str(source) in serialized
    no_contents = marker not in serialized
    procedure_ok = procedure in system
    subs = [
        {
            "name": "input contents are not pre-packed",
            "status": "PASS" if no_contents else "FAIL",
            "detail": "path-only message" if no_contents else "input text leaked into the prompt",
        },
        {
            "name": "the input path reaches the worker",
            "status": "PASS" if path_ok else "FAIL",
            "detail": str(source) if path_ok else "path missing",
        },
        {
            "name": "the bite procedure rides in the system prompt",
            "status": "PASS" if procedure_ok else "FAIL",
            "detail": "procedure found" if procedure_ok else "procedure missing",
        },
    ]
    if not (no_contents and path_ok and procedure_ok):
        return ("FAIL", "pull-don't-pre-pack or procedure-in-context is not enforced", subs)
    return ("PASS", "inputs are paths and the procedure is in the bite context", subs)
