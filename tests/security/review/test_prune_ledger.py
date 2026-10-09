"""The prune ledger decides by reachability: keep-roots, lazy imports, traces, tests, scripts."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).parents[3]
SCRIPT = ROOT / "scripts" / "bully_review_prune_ledger.py"
PKG = "portal.modules.security.core.bully"
REVIEW = "portal.modules.security.core.review"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("bully_review_prune_ledger", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _write(root: Path, rel: str, text: str = "") -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _mini_repo(root: Path) -> None:
    b = "portal/modules/security/core/bully"
    r = "portal/modules/security/core/review"
    for pkg in (
        "portal",
        "portal/modules",
        "portal/modules/security",
        "portal/modules/security/core",
        b,
        r,
    ):
        _write(root, f"{pkg}/__init__.py")
    _write(root, f"{b}/a.py", "def f():\n    from . import b\n    return b\n")  # a -> b only lazily
    _write(root, f"{b}/b.py", "X = 1\n")
    _write(root, f"{b}/c.py", f"from {PKG} import d\n")
    _write(root, f"{b}/d.py", "Y = 2\n")
    _write(root, f"{b}/e.py", "Z = 3\n")  # nothing reaches it
    _write(root, f"{b}/f.py", "W = 4\n")  # reached only through the package __init__'s lazy import
    _write(root, f"{b}/__init__.py", "def run():\n    from . import f\n    return f\n")
    _write(root, f"{r}/x.py", f"from {PKG} import a\n")
    _write(root, "tests/security/bully/test_a.py", f"from {PKG} import a\n")
    _write(root, "tests/security/bully/test_d.py", f"from {PKG} import d\n")
    _write(root, "tests/unrelated.py", "import json\n")
    _write(root, "scripts/run_a.py", f"from {PKG} import a\n")
    _write(root, "scripts/run_c.py", f"from {PKG} import c\n")
    _write(root, "docs/BULLY_OLD_RUN.md", "# old\n")


def _decisions(ledger: dict[str, object]) -> dict[str, str]:
    modules = ledger["modules"]
    assert isinstance(modules, list)
    return {m["module"].rsplit(".", 1)[-1]: m["decision"] for m in modules}


def test_reachability_decides_keep_and_delete(tmp_path: Path) -> None:
    ledger_mod = _load()
    _mini_repo(tmp_path)
    ledger = ledger_mod.build_ledger(tmp_path, keep_prefixes=[REVIEW])
    decisions = _decisions(ledger)
    assert decisions["a"] == "KEEP" and decisions["b"] == "KEEP"  # b only through a's lazy import
    assert decisions["c"] == decisions["d"] == decisions["e"] == "DELETE"
    assert decisions["f"] == "KEEP"  # the lazy edge from __init__ is honoured by default
    assert ledger["tally"] == {
        "KEEP": 4,
        "KEEP_DYNAMIC": 0,
        "DELETE": 3,
    }  # __init__, a, b, f | c, d, e


def test_tests_and_scripts_follow_the_modules_they_exercise(tmp_path: Path) -> None:
    ledger_mod = _load()
    _mini_repo(tmp_path)
    ledger = ledger_mod.build_ledger(tmp_path, keep_prefixes=[REVIEW])
    tests = {Path(r["path"]).name: r["decision"] for r in ledger["tests"]}
    scripts = {Path(r["path"]).name: r["decision"] for r in ledger["scripts"]}
    assert tests == {
        "test_a.py": "KEEP",
        "test_d.py": "DELETE",
    }  # unrelated.py imports no package module
    assert scripts == {"run_a.py": "KEEP", "run_c.py": "DELETE"}
    assert ledger["docs_to_review"] == ["docs/BULLY_OLD_RUN.md"]


def test_a_trace_rescues_what_static_analysis_cannot_see(tmp_path: Path) -> None:
    ledger_mod = _load()
    _mini_repo(tmp_path)
    ledger = ledger_mod.build_ledger(tmp_path, keep_prefixes=[REVIEW], dynamic={f"{PKG}.e"})
    assert _decisions(ledger)["e"] == "KEEP_DYNAMIC"
    protected = ledger_mod.build_ledger(tmp_path, keep_prefixes=[REVIEW], protect={f"{PKG}.c"})
    assert _decisions(protected)["c"] == "KEEP" and _decisions(protected)["d"] == "KEEP"


def test_batches_are_generated_not_executed(tmp_path: Path) -> None:
    ledger_mod = _load()
    _mini_repo(tmp_path)
    ledger = ledger_mod.build_ledger(tmp_path, keep_prefixes=[REVIEW])
    script = ledger_mod.render_batches(ledger)
    assert "git rm -q scripts/run_c.py" in script and "tests/security/bully/test_d.py" in script
    assert script.index("batch 1") < script.index("batch 2") < script.index("batch 3")
    assert "Nothing here has been executed" in script
    assert (tmp_path / "scripts" / "run_c.py").exists()  # still there
    assert json.loads(json.dumps(ledger))["schema"] == "bully-review-prune-ledger-v1"


def test_trace_records_the_modules_a_real_process_imports(tmp_path: Path) -> None:
    ledger_mod = _load()
    out = tmp_path / "trace"
    code = subprocess.run(  # noqa: S603
        [
            sys.executable,
            str(SCRIPT),
            "trace",
            "--out",
            str(out),
            "--",
            sys.executable,
            "-c",
            "import portal.modules.security.core.review.calibration",
        ],
        cwd=ROOT,
        check=False,
    ).returncode
    assert code == 0
    seen = ledger_mod.load_trace(out)
    assert "portal.modules.security.core.review.calibration" in seen


def test_a_known_lazy_edge_can_be_cut_explicitly_and_is_recorded(tmp_path: Path) -> None:
    ledger_mod = _load()
    _mini_repo(tmp_path)
    cut = {(PKG, f"{PKG}.f")}
    ledger = ledger_mod.build_ledger(tmp_path, keep_prefixes=[REVIEW], ignore_edges=cut)
    assert _decisions(ledger)["f"] == "DELETE"
    assert ledger["cut_edges"] == [f"{PKG} => {PKG}.f"]
