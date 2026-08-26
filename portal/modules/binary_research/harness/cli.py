"""CLI for the binary research harness.

The operator's entry point is the OpenCode/Pi skill + command (see integrations/),
which drive these subcommands. Direct CLI use also works.

Commands:
  intake [--project] [--answer ...] [--status] [--json]
                 the harness-conducted Q/A session (skill relays it)
  new <name>     resolve a project under the root and start intake
  init [--project]   create the static structure (no interview)
  run [--project] [--goal ...]   run the loop (requires a ready project + artifacts)
  verify [--project]             run verifiers standalone
  status [--project] [--json]    project phase for the skill
  preflight                      check the RE toolchain via the MCP

Analysis-loop model: --model > config pin > TTY prompt > Qwen3.8-27B.
Intake questions come from a fast MoE (config scaffold.model; default gemma4-heretic).
"""

from __future__ import annotations

import argparse
import json
import logging
import shutil
import sys
from pathlib import Path

import yaml

from . import scaffold as scaffold_mod
from .llm import LLMConfig
from .loop import Budget, run
from .policy import Policy
from .re_client import REClient, REClientError
from .verifiers import run_all
from .workspace import (
    has_artifacts,
    init_project,
    is_initialized,
    resolve_project,
    verifier_count,
)

DEFAULT_MODEL = "hf.co/unsloth/Qwen3.8-27B-GGUF:Q4_K_M"
SCAFFOLD_MODEL = "portal5/gemma4-26b-heretic:q4_K_M-ctx256k"  # fastest MoE
MODEL_MENU = [
    (DEFAULT_MODEL, "Qwen3.8-27B dense — thinking, slow, strong (default)"),
    ("portal5/hauhaucs-qwen36-35b:q4_K_M-ctx256k", "HauhauCS 35B-A3B MoE — rapid-fire"),
    ("portal5/gemma4-26b-heretic:q4_K_M-ctx256k", "Gemma-4-26B-A4B MoE — rapid-fire (fastest)"),
    ("portal5/ornith15-35b:q4_K_M-ctx256k", "Ornith-1.5 35B-A3B MoE — rapid-fire"),
]
DEFAULT_NUM_CTX = 262144


def _load_config(path: Path | None) -> dict:
    if path and path.exists():
        return yaml.safe_load(path.read_text()) or {}
    for candidate in [Path("config.yaml"), Path("brh_config.yaml")]:
        if candidate.exists():
            return yaml.safe_load(candidate.read_text()) or {}
    return {}


def _resolve_model(cli_model: str | None, cfg: dict) -> str:
    if cli_model:
        return cli_model
    pinned = cfg.get("llm", {}).get("model")
    if pinned:
        return pinned
    if sys.stdin.isatty() and sys.stdout.isatty():
        print("Select a model for the analysis loop:")
        for i, (_tag, desc) in enumerate(MODEL_MENU, 1):
            print(f"  {i}) {desc}")
        try:
            choice = input(f"Choice [1-{len(MODEL_MENU)}, default 1]: ").strip()
        except (EOFError, KeyboardInterrupt):
            choice = ""
        if choice.isdigit() and 1 <= int(choice) <= len(MODEL_MENU):
            return MODEL_MENU[int(choice) - 1][0]
        return DEFAULT_MODEL
    logging.getLogger(__name__).info("Non-interactive: defaulting to %s", DEFAULT_MODEL)
    return DEFAULT_MODEL


def _llm_config(cfg: dict, model: str) -> LLMConfig:
    llm = cfg.get("llm", {})
    extra = dict(llm.get("extra_body", {}))
    extra.setdefault("num_ctx", DEFAULT_NUM_CTX)
    return LLMConfig(
        base_url=llm.get("base_url", "http://127.0.0.1:11434/v1"),
        api_key=llm.get("api_key", "local"),
        model=model,
        temperature=llm.get("temperature", 0.2),
        max_tokens=llm.get("max_tokens", 4096),
        extra_body=extra,
        timeout=llm.get("timeout", 600.0),
    )


def _scaffold_llm_config(cfg: dict) -> LLMConfig:
    sc = cfg.get("scaffold", {})
    return _llm_config(cfg, sc.get("model", SCAFFOLD_MODEL))


def _policy(cfg: dict, project_dir: Path) -> Policy:
    pol = cfg.get("policy", {})
    deny = pol.get("deny_command_substrings")
    return Policy(
        job_root=project_dir,
        allow_network=pol.get("allow_network", False),
        allow_execution_of_artifacts=pol.get("allow_execution_of_artifacts", False),
        allow_host_exec=pol.get("allow_host_exec", False),
        deny_command_substrings=deny
        if deny is not None
        else Policy.__dataclass_fields__["deny_command_substrings"].default_factory(),
        extra_allowed_roots=[Path(p) for p in pol.get("extra_allowed_roots", [])],
        tool_output_chars=pol.get("tool_output_chars", 24_000),
        tool_timeout_sec=pol.get("tool_timeout_sec", 120),
    )


def _budget(cfg: dict) -> Budget:
    b = cfg.get("budget", {})
    return Budget(
        max_turns=b.get("max_turns", 80),
        max_tool_calls=b.get("max_tool_calls", 200),
        max_repeat_same_call=b.get("max_repeat_same_call", 3),
    )


def _skill(cfg: dict, module_dir: Path) -> str:
    sp = cfg.get("skill_path")
    if sp and Path(sp).exists():
        return Path(sp).read_text()
    default = module_dir / "skills" / "static_research.md"
    return default.read_text() if default.exists() else ""


def _emit(obj: dict, as_json: bool) -> None:
    if as_json:
        print(json.dumps(obj))
        return
    state = obj.get("state")
    if state == "asking":
        print(obj.get("question", ""))
    elif state == "ready":
        print("READY — scaffold written.")
        print(f"  Goal: {obj.get('goal', '')}")
        print(f"  Verifier stubs: {obj.get('verifiers', 0)}")
        print(f"  {obj.get('hint', '')}")
    else:
        print(json.dumps(obj, indent=2))


def cmd_intake(args: argparse.Namespace) -> int:
    cfg = _load_config(Path(args.config) if args.config else None)
    project_dir = resolve_project(args.project)
    if args.status:
        _emit(scaffold_mod.status(project_dir), args.json)
        return 0
    if args.answer is None:
        _emit(scaffold_mod.start(project_dir), args.json)
        return 0
    out = scaffold_mod.answer(_scaffold_llm_config(cfg), project_dir, args.answer)
    _emit(out, args.json)
    return 0


def cmd_new(args: argparse.Namespace) -> int:
    project_dir = resolve_project(args.name)
    out = scaffold_mod.start(project_dir)
    print(f"Project: {project_dir}")
    _emit(out, args.json)
    return 0


def cmd_init(args: argparse.Namespace) -> int:
    project_dir = resolve_project(args.project)
    init_project(project_dir)
    print(f"Initialized project: {project_dir}")
    print("  artifacts/    — place binaries/dumps here")
    print("  verifiers/    — add *.sh or *.py oracle scripts (need at least 2)")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    project_dir = resolve_project(args.project)
    st = {
        "project": str(project_dir),
        "initialized": is_initialized(project_dir),
        "intake_state": scaffold_mod.status(project_dir).get("state"),
        "has_artifacts": has_artifacts(project_dir),
        "verifier_count": verifier_count(project_dir),
    }
    st["ready_to_run"] = st["initialized"] and st["has_artifacts"] and st["verifier_count"] >= 2
    if args.json:
        print(json.dumps(st))
    else:
        for k, v in st.items():
            print(f"  {k}: {v}")
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    cfg = _load_config(Path(args.config) if args.config else None)
    project_dir = resolve_project(args.project)

    if not is_initialized(project_dir):
        print(
            f"ERROR: {project_dir} is not initialized. Start intake first "
            "(the binary-research skill, or: brh intake --project <name>).",
            file=sys.stderr,
        )
        return 1
    if not has_artifacts(project_dir):
        print(f"ERROR: no artifacts in {project_dir / 'artifacts'}. Add the binaries to research.")
        return 1
    if verifier_count(project_dir) < 2:
        print(
            f"WARNING: {project_dir / 'verifiers'} has < 2 verifiers. "
            "A single oracle is how models stop early."
        )

    model = _resolve_model(args.model, cfg)
    llm_config = _llm_config(cfg, model)
    policy = _policy(cfg, project_dir)
    budget = _budget(cfg)
    skill = _skill(cfg, Path(__file__).parent.parent)
    re_url = cfg.get("re_mcp", {}).get("base_url", "http://127.0.0.1:8930")
    re_client = REClient(base_url=re_url)
    project_name = project_dir.name

    goal = args.goal
    gf = project_dir / "GOAL.txt"
    if not goal and gf.exists():
        goal = gf.read_text().strip()
    if not goal:
        print("ERROR: --goal is required (or write GOAL.txt in the project).", file=sys.stderr)
        return 1

    print("Binary Research Harness")
    print(f"  Project: {project_dir}")
    print(f"  Model:   {model}")
    print(f"  RE MCP:  {re_url}")
    print(f"  Goal:    {goal[:80]}{'...' if len(goal) > 80 else ''}")
    print()

    def progress(turn: int, summary: str, event: str) -> None:
        print(f"  [{summary}] {event}")

    result = run(
        llm_config=llm_config,
        job_dir=project_dir,
        goal=goal,
        policy=policy,
        budget=budget,
        re_client=re_client,
        project=project_name,
        skill_text=skill,
        progress_callback=progress,
    )
    print()
    print(f"Outcome: {result.outcome}  (turns={result.turns}, tools={result.tool_calls})")
    if result.report_path:
        print(f"  Report: {result.report_path}")
    if result.error:
        print(f"  Error: {result.error}")
    return 0 if result.outcome == "completed" else 1


def cmd_verify(args: argparse.Namespace) -> int:
    verdict = run_all(resolve_project(args.project))
    print(str(verdict))
    return 0 if verdict.all_pass else 1


def cmd_install_trigger(args: argparse.Namespace) -> int:
    """Copy the shipped skill + command shim into agent-discovered directories.

    The AGENT discovers the correct skills/commands dirs for its runtime
    (OpenCode or Claude Code / Pi) — see integrations/INSTALL.md — and passes
    them here. The harness performs the copy. No paths are hardcoded.
    """
    integ = Path(__file__).parent.parent / "integrations"
    skill_src = integ / "SKILL.md"
    cmd_src = integ / "binresearch.command.md"
    if not skill_src.exists() or not cmd_src.exists():
        print(f"ERROR: integration files missing under {integ}", file=sys.stderr)
        return 1

    plan = []
    if args.skills_dir:
        dest = Path(args.skills_dir).expanduser() / "binary-research" / "SKILL.md"
        plan.append((skill_src, dest))
    if args.commands_dir:
        dest = Path(args.commands_dir).expanduser() / "binresearch.md"
        plan.append((cmd_src, dest))
    if not plan:
        print(
            "ERROR: pass --skills-dir and/or --commands-dir (discover them for your "
            "runtime; see integrations/INSTALL.md).",
            file=sys.stderr,
        )
        return 1

    for src, dest in plan:
        if args.dry_run:
            print(f"would copy {src.name} -> {dest}")
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dest)
        print(f"installed: {dest}")
    if not args.dry_run:
        print(
            "Trigger installed. Confirm the toolchain: "
            "python -m portal.modules.binary_research.harness preflight"
        )
    return 0


def cmd_preflight(args: argparse.Namespace) -> int:
    cfg = _load_config(Path(args.config) if args.config else None)
    re_url = cfg.get("re_mcp", {}).get("base_url", "http://127.0.0.1:8930")
    client = REClient(base_url=re_url)
    try:
        print("RE MCP health:", client.health())
        rep = client.tools()
        print(f"Image: {rep.get('image')}")
        print(f"Present ({len(rep.get('present', []))}): {', '.join(rep.get('present', []))}")
        missing = rep.get("missing", [])
        print(f"Missing ({len(missing)}): {', '.join(missing) or 'none'}")
        return 0 if not missing else 1
    except REClientError as exc:
        print(f"RE MCP unreachable: {exc}")
        print("Start the stack, then: ./launch.sh build-binresearch && ./launch.sh restart-mcp")
        return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="brh", description="Binary Research Harness — model-swappable static analysis loop"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_intake = sub.add_parser("intake", help="Harness-conducted Q/A intake session")
    p_intake.add_argument("--project", help="Project name/path (default: auto-detect from CWD)")
    p_intake.add_argument("--answer", help="Operator's answer to the pending question")
    p_intake.add_argument("--status", action="store_true", help="Print session state")
    p_intake.add_argument(
        "--json", action="store_true", help="Machine-readable output (for the skill)"
    )
    p_intake.add_argument("--config")
    p_intake.set_defaults(func=cmd_intake)

    p_new = sub.add_parser("new", help="Resolve a project under the root and start intake")
    p_new.add_argument("name")
    p_new.add_argument("--json", action="store_true")
    p_new.set_defaults(func=cmd_new)

    p_init = sub.add_parser("init", help="Create the static structure (no interview)")
    p_init.add_argument("--project")
    p_init.set_defaults(func=cmd_init)

    p_run = sub.add_parser("run", help="Run the research loop (requires a ready project)")
    p_run.add_argument("--project")
    p_run.add_argument("--goal")
    p_run.add_argument("--config")
    p_run.add_argument("--model", help="Override the analysis model; skips the prompt")
    p_run.set_defaults(func=cmd_run)

    p_verify = sub.add_parser("verify", help="Run verifiers standalone")
    p_verify.add_argument("--project")
    p_verify.set_defaults(func=cmd_verify)

    p_status = sub.add_parser("status", help="Project phase (for the skill)")
    p_status.add_argument("--project")
    p_status.add_argument("--json", action="store_true")
    p_status.set_defaults(func=cmd_status)

    p_inst = sub.add_parser(
        "install-trigger", help="Copy the skill + command into agent-discovered dirs"
    )
    p_inst.add_argument("--skills-dir", help="Discovered skills dir for your runtime")
    p_inst.add_argument("--commands-dir", help="Discovered commands dir for your runtime")
    p_inst.add_argument("--dry-run", action="store_true", help="Show what would be written")
    p_inst.set_defaults(func=cmd_install_trigger)

    p_pre = sub.add_parser("preflight", help="Check the RE toolchain via the MCP")
    p_pre.add_argument("--config")
    p_pre.set_defaults(func=cmd_preflight)

    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    return args.func(args)
