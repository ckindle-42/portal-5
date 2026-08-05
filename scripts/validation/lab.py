"""Lab-target checks: the lab target/challenge-class catalog and setup readiness."""

from __future__ import annotations

from ._shared import REPO_ROOT
from .registry import register


@register("lab_target", "R. lab target catalog", order=17)
def check_lab_target_catalog() -> tuple[str, str, list[dict]]:
    """U. lab_targets.yaml entries have source + ground_truth; challenge_classes.yaml no orphans."""
    import yaml

    subs: list[dict] = []
    problems: list[str] = []

    # Check lab_targets.yaml
    lt_path = REPO_ROOT / "config" / "lab_targets.yaml"
    if lt_path.exists():
        try:
            lt = yaml.safe_load(lt_path.read_text())
            for t in lt.get("targets", []):
                tid = t.get("id", "?")
                if "source" not in t:
                    problems.append(f"{tid}: missing source")
                if "ground_truth" not in t:
                    problems.append(f"{tid}: missing ground_truth")
            subs.append({"name": "lab_targets.yaml", "status": "PASS" if not problems else "FAIL"})
        except Exception as e:
            problems.append(f"lab_targets.yaml parse error: {e}")

    # Check challenge_classes.yaml
    cc_path = REPO_ROOT / "config" / "challenge_classes.yaml"
    if cc_path.exists():
        try:
            cc = yaml.safe_load(cc_path.read_text())
            cc_problems = []
            for c in cc.get("classes", []):
                cid = c.get("id", "?")
                has_vulhub = len(c.get("vulhub", [])) > 0
                has_purpose = c.get("purpose_built") is not None
                if not has_vulhub and not has_purpose:
                    cc_problems.append(f"{cid}: orphan — no vulhub path or purpose_built dir")
            cc_status = "PASS" if not cc_problems else "FAIL"
            subs.append({"name": "challenge_classes.yaml", "status": cc_status})
            problems.extend(cc_problems)
        except Exception as e:
            problems.append(f"challenge_classes.yaml parse error: {e}")

    if problems:
        return "FAIL", f"{len(problems)} catalog issue(s): {problems[:5]}", subs
    return "PASS", "lab target catalog + challenge classes valid", subs


@register("lab_setup", "T. lab setup readiness", order=19)
def check_lab_setup_readiness() -> tuple[str, str, list[dict]]:
    """V. Lab setup/readiness scripts import and parse correctly."""
    import contextlib
    import io

    subs: list[dict] = []
    try:
        from scripts.lab_setup import run_setup

        with contextlib.redirect_stdout(io.StringIO()):
            result = run_setup(skip_heavy=True, dry_run=True)
        subs.append({"name": "lab_setup", "status": "PASS" if "vulhub" in result else "FAIL"})
    except Exception as e:
        subs.append({"name": "lab_setup", "status": "FAIL", "error": str(e)})

    try:
        from scripts.lab_ready import run_readiness

        passed, results = run_readiness()
        subs.append({"name": "lab_ready", "status": "PASS" if len(results) >= 5 else "FAIL"})
    except Exception as e:
        subs.append({"name": "lab_ready", "status": "FAIL", "error": str(e)})

    try:
        from scripts.lab_targets import cmd_list

        targets = cmd_list()
        subs.append(
            {"name": "lab_targets catalog", "status": "PASS" if len(targets) >= 7 else "FAIL"}
        )
    except Exception as e:
        subs.append({"name": "lab_targets catalog", "status": "FAIL", "error": str(e)})

    failed = [s["name"] for s in subs if s["status"] == "FAIL"]
    if failed:
        return "FAIL", f"{len(failed)} lab setup check(s) failed: {failed}", subs
    return "PASS", "all lab setup/readiness/targets modules operational", subs
