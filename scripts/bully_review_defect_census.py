#!/usr/bin/env python3
"""Defect census for the Bully/Crogl overhaul -- the before/after instrument.

Every finding is a *probe against the code as it stands*, never a belief carried in a document.
Statuses: ``present`` (the defect reproduces), ``absent`` (it does not), ``module_absent`` (the
code it probes no longer exists -- the usual state after the prune), ``error`` (the probe
itself failed; read the evidence).

Also reports the import census (production-reachable / script-only / tests-only / orphan
modules of the ``bully`` package) so "unreachable" is a counted fact.

    uv run python scripts/bully_review_defect_census.py --out reports/bully_review
    uv run python scripts/bully_review_defect_census.py --expect-absent D-UNITS-CAP,D-DEFENSE-CONSTANT

``--expect-absent`` exits 1 if any listed finding is still ``present`` (an acceptance gate).
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
import tempfile
import time
from collections import Counter
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
CORE = REPO / "portal" / "modules" / "security" / "core"
BULLY = CORE / "bully"
PKG = "portal.modules.security.core.bully"


@dataclass
class Finding:
    id: str
    title: str
    status: str
    evidence: str


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.is_file() else ""


def _finding(fid: str, title: str, present: bool, evidence: str) -> Finding:
    return Finding(fid, title, "present" if present else "absent", evidence)


def _probe(fid: str, title: str, fn: Callable[[], tuple[bool, str]]) -> Finding:
    try:
        present, evidence = fn()
    except ModuleNotFoundError as exc:
        return Finding(fid, title, "module_absent", f"{type(exc).__name__}: {exc}")
    except Exception as exc:  # noqa: BLE001 -- a probe failure is a finding, not a crash
        return Finding(fid, title, "error", f"{type(exc).__name__}: {exc}")
    return _finding(fid, title, present, evidence)


# ── probes ───────────────────────────────────────────────────────────────────


def _records(n: int, schema: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for i in range(n):
        if schema == "a":
            out.append(
                {
                    "_time": f"2026-10-01T{(i // 60) % 24:02d}:{i % 60:02d}:00Z",
                    "host": f"h{i % 7}",
                    "user": f"u{i % 11}",
                    "action": ["logon", "list", "run", "read", "write", "stop"][i % 6],
                }
            )
        else:
            out.append(
                {
                    "ts": f"2026-10-01T{(i // 60) % 24:02d}:{i % 60:02d}:30Z",
                    "clientip": f"10.0.{i % 5}.{i % 13}",
                    "uri": ["/a", "/b", "/login", "/api"][i % 4],
                    "status": [200, 200, 404, 500][i % 4],
                }
            )
    return out


def probe_units_cap() -> tuple[bool, str]:
    from portal.modules.security.core.bully import artifact_graph as ag

    n = ag.MAX_UNITS_PER_LEVEL + 188
    graph = ag.build_graph(_records(n, "a"), source_id="census")
    level_one = sum(1 for u in ag.enumerate_units(graph) if u.level == "L1_ARTIFACT")
    return level_one < len(
        graph.artifacts
    ), f"{len(graph.artifacts)} artifacts -> {level_one} L1 units by default"


def probe_entity_fieldname() -> tuple[bool, str]:
    """Entity tokens embed the field name, so the same host under two column names never links."""
    from portal.modules.security.core.bully import artifact_graph as ag

    a = [
        {
            "_time": f"2026-10-01T00:{i % 60:02d}:00Z",
            "host": f"WKS{i % 5}",
            "action": ["logon", "run"][i % 2],
        }
        for i in range(200)
    ]
    b = [
        {
            "ts": f"2026-10-01T00:{i % 60:02d}:30Z",
            "hostname": f"WKS{i % 5}",
            "op": ["list", "stop"][i % 2],
        }
        for i in range(200)
    ]
    graph = ag.build_graph(
        [{**r, "__source_id": "a"} for r in a] + [{**r, "__source_id": "b"} for r in b]
    )
    source = {k: v.source_id for k, v in graph.artifacts.items()}
    cross = sum(
        1 for e in graph.edges if e.kind == "shared_entity" and source[e.left] != source[e.right]
    )
    return cross == 0, f"cross-source shared_entity edges for the same host values: {cross}"


def _episode(telemetry: dict[str, list[Any]], scenario: str = "kerberoast_chain") -> Any:
    handle = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)  # noqa: SIM115
    json.dump({"scenario": scenario, "telemetry": telemetry}, handle)
    handle.close()
    return SimpleNamespace(
        evidence_refs=[handle.name],
        detection_status="DETECTION_CONFIRMED",
        scenario=scenario,
        episode_id="ep-census",
        target_host="10.0.0.5",
        red_status="RED_LANDED",
        telemetry_status="TELEMETRY_OBSERVED",
        response_status="",
        used_synthetic=False,
        verdict=lambda: "OK",
    )


def _signature(telemetry: dict[str, list[Any]]) -> Any:
    from portal.modules.security.core.bully import evidence, signatures

    episode = _episode(telemetry)
    return signatures.build_signature(
        evidence.adapt_episode(episode), evidence.adapt_episode_telemetry(episode)
    )


def probe_sig_windows_spine() -> tuple[bool, str]:
    sig = _signature(
        {
            "windows:security": [
                "EventCode=4624 LogonType=3 Account_Name=svc_sql",
                "EventCode=4769 Service_Name=svc_sql Ticket_Encryption_Type=0x17",
                "EventCode=4688 New_Process_Name=C:\\Windows\\System32\\whoami.exe",
                "EventCode=4672 Privileges=SeDebugPrivilege",
            ]
        }
    )
    return (
        not sig.behavior_spine,
        f"behavior_spine={sig.behavior_spine!r} actions={sig.action_sequence[:3]}",
    )


def probe_sig_dict_records() -> tuple[bool, str]:
    sig = _signature(
        {
            "WinEventLog:Security": [
                {"_raw": "EventCode=4688 New_Process_Name=whoami.exe", "host": "dc01"},
                {"_raw": "EventCode=4624 LogonType=3", "host": "dc01"},
            ]
        }
    )
    return all(a.endswith(":record") for a in sig.action_sequence), f"actions={sig.action_sequence}"


def probe_sig_web_http_verbs() -> tuple[bool, str]:
    sig = _signature(
        {"web:access": ["GET /a 200", "POST /upload.php 200", "GET /s.php?x=whoami 200"]}
    )
    return bool(sig.behavior_spine), f"behavior_spine={sig.behavior_spine!r}"


def probe_scenario_in_signature() -> tuple[bool, str]:
    from portal.modules.security.core.bully import signatures

    sig = _signature({"windows:security": ["EventCode=4688 New_Process_Name=a.exe"]})
    family = signatures.signature_family(sig)
    return family == "kerberoast_chain", f"signature family={family!r} (the Red scenario name)"


def probe_defense_constant() -> tuple[bool, str]:
    from portal.modules.security.core.bully import loop_grader

    value = loop_grader._defense_response(True, True)
    return (
        value == "COVERED",
        f"_defense_response(observable, healthy) -> {value!r} with no detection consulted",
    )


def probe_novel_unreachable() -> tuple[bool, str]:
    tree = ast.parse(_read(BULLY / "organ.py"))
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "_search_table":
            cutoffs = []
            for cmp in (n for n in ast.walk(node) if isinstance(n, ast.Compare)):
                operands = [cmp.left, *cmp.comparators]
                has_const_str = any(
                    isinstance(o, ast.Constant) and isinstance(o.value, str) for o in operands
                )
                if not has_const_str and any("dist" in ast.unparse(o).lower() for o in operands):
                    cutoffs.append(ast.unparse(cmp))
            return not cutoffs, f"_search_table distance-value comparisons: {cutoffs or 'none'}"
    return False, "Organ._search_table not found"


def probe_dead_dial() -> tuple[bool, str]:
    hunt = _read(REPO / "config" / "security" / "hunt.yaml")
    grader = _read(BULLY / "loop_grader.py")
    if not grader:
        raise ModuleNotFoundError("bully.loop_grader")
    dial = "thresholds:" in hunt
    reads = "load_hunt_config" in grader or "hunt_config" in grader
    return (
        dial and not reads,
        f"hunt.yaml has thresholds block={dial}; loop_grader reads hunt config={reads}",
    )


def probe_verdict_deadend() -> tuple[bool, str]:
    if not (BULLY / "orchestrator.py").is_file():
        raise ModuleNotFoundError("bully.orchestrator")
    users = [
        p.name
        for p in BULLY.rglob("*.py")
        if p.name != "orchestrator.py" and "investigation_verdict" in _read(p)
    ]
    return (
        not users,
        f"modules consuming investigation_verdict besides orchestrator: {users or 'none'}",
    )


def probe_agents_stub() -> tuple[bool, str]:
    text = _read(CORE / "investigation" / "agents.py")
    if not text:
        raise ModuleNotFoundError("investigation.agents")
    hard = '"reachability": True' in text
    calls = any(tok in text for tok in ("client.", ".complete(", "chat(", "httpx", "requests."))
    return hard and not calls, f"hardcoded checklist={hard}; makes model/tool calls={calls}"


def probe_single_iteration() -> tuple[bool, str]:
    text = _read(BULLY / "orchestrator.py")
    if not text:
        raise ModuleNotFoundError("bully.orchestrator")
    return (
        "single-iteration P1 proof" in text,
        "run_hunt reports iterations=1 / 'single-iteration P1 proof'",
    )


def probe_name_table() -> tuple[bool, str]:
    from portal.modules.security.core.bully import behavior_values

    size = len(getattr(behavior_values, "_FIELDS", {}))
    return size > 40, f"behavior_values._FIELDS hand-listed field names: {size}"


def probe_circular_fixtures() -> tuple[bool, str]:
    text = _read(
        REPO / "tests" / "security" / "bully" / "test_reintegration_r3_behavioral_signatures.py"
    )
    if not text:
        raise ModuleNotFoundError("tests/security/bully/test_reintegration_r3...")
    return (
        "AssumeRole" in text,
        "R.3 signature tests feed AWS API verbs the production adapter never emits",
    )


PROBES: list[tuple[str, str, Callable[[], tuple[bool, str]]]] = [
    ("D-UNITS-CAP", "enumerate_units silently caps units per level", probe_units_cap),
    (
        "D-ENTITY-FIELDNAME",
        "the same host under two field names never links across sources",
        probe_entity_fieldname,
    ),
    (
        "D-SIG-WIN-SPINE",
        "Windows EventCode telemetry yields an empty behavior spine",
        probe_sig_windows_spine,
    ),
    (
        "D-SIG-DICT-NOCONTENT",
        "dict-shaped records collapse to event-N:record",
        probe_sig_dict_records,
    ),
    (
        "D-SIG-WEB-HTTPVERB",
        "web 'behaviors' come from HTTP verb substrings",
        probe_sig_web_http_verbs,
    ),
    (
        "D-LABEL-IN-SIGNATURE",
        "the Red scenario name is the signature's family",
        probe_scenario_in_signature,
    ),
    (
        "D-DEFENSE-CONSTANT",
        "defense_response is COVERED without consulting a detection",
        probe_defense_constant,
    ),
    ("D-NOVEL-UNREACHABLE", "retrieval has no 'too far to count' cutoff", probe_novel_unreachable),
    ("D-DEAD-DIAL", "hunt.yaml thresholds are never read by the product grader", probe_dead_dial),
    (
        "D-VERDICT-DEADEND",
        "the investigation verdict is consumed by nothing",
        probe_verdict_deadend,
    ),
    (
        "D-AGENTS-STUB",
        "investigation/agents.py is a scaffold with a hardcoded checklist",
        probe_agents_stub,
    ),
    ("D-SINGLE-ITERATION", "the 'hunt' is one iteration", probe_single_iteration),
    ("D-NAME-TABLE", "behavior terms come from a hand-listed field-name table", probe_name_table),
    (
        "D-CIRCULAR-FIXTURES",
        "tests feed the classifier its own vocabulary",
        probe_circular_fixtures,
    ),
]


# ── import census ────────────────────────────────────────────────────────────


def _mod_of(path: Path) -> str:
    rel = path.relative_to(REPO).with_suffix("")
    parts = list(rel.parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _is_type_checking(test: ast.expr) -> bool:
    return (isinstance(test, ast.Name) and test.id == "TYPE_CHECKING") or (
        isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING"
    )


def _imports(path: Path) -> tuple[set[str], set[str]]:
    """(module-level imports, function-level imports). ``if TYPE_CHECKING`` bodies are skipped."""
    mod = _mod_of(path)
    pkg = mod if path.name == "__init__.py" else mod.rsplit(".", 1)[0]
    eager: set[str] = set()
    lazy: set[str] = set()

    def names(node: ast.Import | ast.ImportFrom) -> set[str]:
        if isinstance(node, ast.Import):
            return {a.name for a in node.names}
        if node.level:
            parts = pkg.split(".")
            base = ".".join(parts[: len(parts) - (node.level - 1)])
            target = f"{base}.{node.module}" if node.module else base
        else:
            target = node.module or ""
        return {target, *(f"{target}.{a.name}" for a in node.names)}

    def visit(nodes: list[ast.stmt], in_function: bool) -> None:
        for node in nodes:
            if isinstance(node, ast.Import | ast.ImportFrom):
                (lazy if in_function else eager).update(names(node))
            elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                visit(node.body, True)
            elif isinstance(node, ast.If):
                if not _is_type_checking(node.test):
                    visit(node.body, in_function)
                visit(node.orelse, in_function)
            elif isinstance(node, ast.Try):
                for block in (
                    node.body,
                    node.orelse,
                    node.finalbody,
                    *(h.body for h in node.handlers),
                ):
                    visit(block, in_function)
            elif isinstance(node, ast.ClassDef | ast.With | ast.For | ast.While):
                visit(node.body, in_function)

    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError):
        return eager, lazy
    visit(tree.body, False)
    return eager, lazy


def _closure(roots: set[str], adjacency: dict[str, set[str]]) -> set[str]:
    seen: set[str] = set()
    stack = list(roots)
    while stack:
        item = stack.pop()
        if item in seen:
            continue
        seen.add(item)
        stack.extend(adjacency.get(item, set()) - seen)
    return seen


def _resolver(modules: dict[str, Path]) -> Callable[[str], str | None]:
    def resolve(name: str) -> str | None:
        parts = name.split(".")
        while parts:
            cand = ".".join(parts)
            if cand in modules:
                return cand
            parts.pop()
        return None

    return resolve


def _kind(path: Path) -> str:
    if path.is_relative_to(BULLY):
        return "internal"
    return {"tests": "tests", "scripts": "scripts"}.get(path.relative_to(REPO).parts[0], "product")


def _graphs(
    files: list[Path], modules: dict[str, Path]
) -> tuple[dict[str, set[str]], dict[str, set[str]], dict[str, set[str]], dict[str, set[str]]]:
    """(eager seeds by importer kind, all seeds, eager adjacency, all adjacency)."""
    resolve = _resolver(modules)

    def hits(names: set[str]) -> set[str]:
        return {h for n in names if (n == PKG or n.startswith(PKG + ".")) and (h := resolve(n))}

    seeds_eager: dict[str, set[str]] = {"product": set(), "scripts": set(), "tests": set()}
    seeds_all: dict[str, set[str]] = {"product": set(), "scripts": set(), "tests": set()}
    adj_eager: dict[str, set[str]] = {m: set() for m in modules}
    adj_all: dict[str, set[str]] = {m: set() for m in modules}
    for path in files:
        eager, lazy = _imports(path)
        kind = _kind(path)
        if kind == "internal":
            src = _mod_of(path)
            if src in adj_all:
                adj_eager[src] |= hits(eager) - {src}
                adj_all[src] |= hits(eager | lazy) - {src}
        else:
            seeds_eager[kind] |= hits(eager)
            seeds_all[kind] |= hits(eager | lazy)
    return seeds_eager, seeds_all, adj_eager, adj_all


def _curated_lines(path: Path, min_elements: int = 10) -> int:
    """Lines spanned by module-level literal containers with >= ``min_elements`` elements:
    data masquerading as code (curated tables). A counted fact, not a judgement."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError):
        return 0
    total = 0
    for node in tree.body:
        value = node.value if isinstance(node, ast.Assign | ast.AnnAssign) else None
        if isinstance(value, ast.Call) and value.args:
            value = value.args[0]
        size = 0
        if isinstance(value, ast.Dict):
            size = len(value.keys)
        elif isinstance(value, ast.Set | ast.List | ast.Tuple):
            size = len(value.elts)
        if size >= min_elements:
            total += (node.end_lineno or node.lineno) - node.lineno + 1
    return total


def census() -> dict[str, Any]:
    if not BULLY.is_dir():
        return {"status": "module_absent"}
    files = [
        p for p in REPO.rglob("*.py") if ".git" not in p.parts and "node_modules" not in p.parts
    ]
    modules = {_mod_of(p): p for p in BULLY.rglob("*.py") if "migrations" not in p.parts}
    seeds_eager, seeds_all, adj_eager, adj_all = _graphs(files, modules)
    prod_strict = _closure(seeds_eager["product"], adj_eager)
    prod_lazy = _closure(seeds_all["product"], adj_all)
    scripts = _closure(seeds_all["scripts"], adj_all)
    tests = _closure(seeds_all["tests"], adj_all)
    order = (
        ("production", prod_strict),
        ("production-lazy", prod_lazy),
        ("script-only", scripts),
        ("tests-only", tests),
    )
    classes = {
        m: next((label for label, members in order if m in members), "orphan") for m in modules
    }
    summary = {
        label: {
            "modules": sum(1 for c in classes.values() if c == label),
            "lines": sum(
                sum(1 for _ in modules[m].open(encoding="utf-8", errors="ignore"))
                for m, c in classes.items()
                if c == label
            ),
        }
        for label in ("production", "production-lazy", "script-only", "tests-only", "orphan")
    }
    for label in summary:
        summary[label]["curated_literal_lines"] = sum(
            _curated_lines(modules[m]) for m, c in classes.items() if c == label
        )
    return {
        "modules": len(modules),
        "summary": summary,
        "by_module": {m.replace(PKG + ".", ""): c for m, c in sorted(classes.items())},
        "note": (
            "production = reachable through module-level imports; production-lazy = only through "
            "function-level imports (reached only if that function is called)"
        ),
    }


def run(out_dir: Path | None) -> dict[str, Any]:
    findings = [_probe(fid, title, fn) for fid, title, fn in PROBES]
    doc: dict[str, Any] = {
        "schema": "bully-review-defect-census-v1",
        "created_at": time.time(),
        "findings": [asdict(f) for f in findings],
        "tally": dict(Counter(f.status for f in findings)),
        "census": census(),
    }
    if out_dir is not None:
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / f"census_{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}.json"
        path.write_text(json.dumps(doc, indent=2, sort_keys=True), encoding="utf-8")
        doc["written"] = str(path)
    return doc


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("--out", type=Path, default=None, help="directory for the JSON report")
    parser.add_argument(
        "--expect-absent", default="", help="comma list of finding ids that must not be present"
    )
    args = parser.parse_args()
    doc = run(args.out)
    for f in doc["findings"]:
        print(f"{f['status']:>13}  {f['id']:<22} {f['evidence'][:110]}")
    print("tally:", doc["tally"])
    summary = doc["census"].get("summary", {})
    if summary:
        print("census:", {k: (v["modules"], v["lines"]) for k, v in summary.items()})
    wanted = {x.strip() for x in args.expect_absent.split(",") if x.strip()}
    still = sorted(
        f["id"] for f in doc["findings"] if f["id"] in wanted and f["status"] == "present"
    )
    if still:
        print("STILL PRESENT:", still)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
