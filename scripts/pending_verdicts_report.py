#!/usr/bin/env python3
"""Full per-model informed-decision report for pending verdicts.

Evidence miner captures numbers (TPS, quality, closeout signals, freshness).
This script captures *context*: why the model was pulled, what it claims to
do, what fleet role it targets, what disappears if removed, and whether the
fleet's architecture/vendor diversity survives. Every model in the pending
backlog was pulled with intent — the informed decision needs to surface
that intent alongside the numbers.

Emits reports/PENDING_VERDICTS_ANALYSIS_<UTC>.md. Report-only; never writes
the ledger, never calls ollama, no network calls.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import glob
import hashlib
import json
import re
import statistics
import subprocess
from collections import Counter
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
LEDGER_PATH = REPO_ROOT / "config" / "PENDING_MODEL_VERDICTS.md"
PORTAL_PATH = REPO_ROOT / "config" / "portal.yaml"
CARD_CACHE_DIR = REPO_ROOT / "reports" / "model_cards"

STALE_DAYS = 60
# See pending_verdicts_evidence.py — evidence older than this is INVALID
# for numeric decisions because the inference stack changed. Override via
# --stack-boundary-days.
STACK_BOUNDARY_DAYS = 3
RECENT_INTAKE_DAYS = 21

ENTRY_RE = re.compile(r"^- \[[x ]\] `([^`]+)` — ([\d.]+) GB")
EVIDENCE_RE = re.compile(r"^  - evidence: `([^`]+)`")
TS_RE = re.compile(r"(20\d{6})T?\d*Z?")


def parse_ledger() -> list[dict]:
    if not LEDGER_PATH.exists():
        return []
    out: list[dict] = []
    cur = None
    for line in LEDGER_PATH.read_text(encoding="utf-8").splitlines():
        m = ENTRY_RE.match(line)
        if m:
            cur = {"tag": m.group(1), "size_gb": float(m.group(2)), "evidence": []}
            out.append(cur)
            continue
        me = EVIDENCE_RE.match(line)
        if me and cur is not None:
            cur["evidence"].append(me.group(1))
    return out


def parse_tag_features(tag: str) -> dict:
    """Distill facts from the tag string using pattern rules. Everything
    here is derivable from the tag alone — no network, no external lookup."""
    features: dict = {"tag": tag, "distinguishing": []}
    lower = tag.lower()

    if lower.startswith("hf.co/"):
        rest = tag[6:]
        parts = rest.split("/", 1)
        features["source"] = "huggingface"
        features["source_org"] = parts[0]
    elif lower.startswith("portal5/"):
        features["source"] = "portal5-local-build"
        features["source_org"] = "portal5"
    elif "/" in lower and ":" in lower:
        features["source"] = "ollama-library-namespaced"
        features["source_org"] = tag.split("/", 1)[0]
    else:
        features["source"] = "ollama-library"
        features["source_org"] = "ollama-library"

    m = re.search(r"[-:]?(\d+(?:\.\d+)?)b(?:[-:_]|$)", lower)
    if m:
        features["params"] = f"{m.group(1)}B"

    arch_patterns = [
        ("Qwen3.6", ["qwen3.6", "qwen-3.6", "qwen3-6", "qwable-3.6", "deepwen-3.6", "superqwen"]),
        ("Qwen3-Coder", ["qwen3-coder", "qwen3_coder"]),
        ("Qwen3", ["qwen3"]),
        ("Qwen2.5", ["qwen2.5"]),
        ("Qwen2", ["qwen2"]),
        ("Granite4", ["granite4", "granite-4", "granite4.1"]),
        ("Nanbeige4.2", ["nanbeige4.2", "nanbeige-4.2", "nanbeige4-2"]),
        ("Instella-MoE", ["instella-moe", "instella_moe"]),
        ("GPT-OSS", ["gpt-oss", "gpt_oss"]),
        ("Nex-N2", ["nex-n2", "nex_n2"]),
        ("Muse-Glimmer", ["muse-glimmer"]),
        ("Fara", ["fara1.5", "fara-1.5", "fara"]),
        ("Antares", ["antares"]),
        ("XYZ-Aquila", ["xyz-aquila", "aquila"]),
        ("BugTraceAI", ["bugtrace"]),
        ("GLM", ["glm-z1", "glm-4", "glm4", "thudm_glm", "thudm-glm"]),
        ("Agents-A1", ["agents-a1", "agents_a1"]),
        ("LFM2.5", ["lfm2.5", "lfm-2.5", "lfm2_5"]),
        ("Gemma4", ["gemma4", "gemma-4"]),
        ("Gemma3", ["gemma3", "gemma-3"]),
        ("Laguna", ["laguna"]),
        ("Llama3", ["llama3", "llama-3"]),
        ("Mistral", ["mistral"]),
        ("Kimi", ["kimi"]),
        ("DeepSeek", ["deepseek"]),
    ]
    for arch, patterns in arch_patterns:
        if any(p in lower for p in patterns):
            features["arch"] = arch
            break

    feature_patterns = [
        (
            "MoE architecture (routes tokens to expert subsets)",
            ["moe", "-a3b-", "-a3b:", ":a3b-", "-a2b-", "mixtral", "instella-moe"],
        ),
        ("MTP speculative drafting (draft model bound to base)", ["-mtp", "-drafted"]),
        ("Abliterated (safety-vector ablation)", ["abliterated", "-ablit-", "-ablit:"]),
        ("Heretic-modified (jailbreak retraining)", ["heretic"]),
        (
            "Explicit thinking / reasoning traces",
            ["-think:", "-thinking:", "-think-", "-thinking-"],
        ),
        ("MLX-native (Apple silicon; not GGUF)", ["-mlx:", "-mlx-"]),
        ("Agent-tuned", ["-agent:", "-agent-", "agentworld"]),
        ("Tool-use tuned", ["-tool:", "-toolcall"]),
        ("Vision / multimodal", ["-vl:", "-vl-", "-vision-", "-mm-"]),
        ("Blue-team security tuned", ["blueteam", "blue-team"]),
        ("Red-team security tuned", ["redteam", "red-team"]),
        ("Cyber / security domain training", ["cyber", "bugtrace", "cybersec"]),
        ("Instruction-tuned", ["-instruct:", "-instruct-"]),
        ("Long-context extension", ["-1m-", "-1m:", "-long-", "-longcontext-"]),
        ("Unsloth Dynamic quantization", ["ud-q4_k_xl", "ud-q5_k_xl", "ud-q3_k_xl"]),
    ]
    for label, patterns in feature_patterns:
        if any(p in lower for p in patterns):
            features["distinguishing"].append(label)

    quant_map = [
        ("UD-Q4_K_XL", "Unsloth Dynamic Q4 XL"),
        ("UD-Q5_K_XL", "Unsloth Dynamic Q5 XL"),
        ("Q4_K_M", "Q4_K_M (mixed)"),
        ("Q4_K_S", "Q4_K_S (small)"),
        ("Q6_K", "Q6_K"),
        ("Q8_0", "Q8_0"),
        ("Q3_K_M", "Q3_K_M"),
        ("Q3_K_S", "Q3_K_S"),
        ("Q3_K_L", "Q3_K_L"),
        ("Q5_K_M", "Q5_K_M"),
        ("F16", "F16 (unquantized)"),
        ("BF16", "BF16 (unquantized)"),
    ]
    for pattern, label in quant_map:
        if pattern.lower() in lower:
            features["quant"] = label
            break

    if features["source"] == "portal5-local-build":
        features["re_pull"] = (
            "NOT registry-pullable — local build; reconstruct via original derivation task"
        )
    else:
        features["re_pull"] = f"ollama pull '{tag}'"

    return features


TASK_FILE_PATTERNS = ("TASK_*.md", "docs/**/*.md", "portal_wiki/canonical/*.md")


def mine_intake_rationale(tag: str) -> dict:
    hits: list[dict] = []
    tag_l = tag.lower()
    short_form = tag.rsplit("/", 1)[-1].split(":", 1)[0].lower()

    files: list[Path] = []
    for pat in TASK_FILE_PATTERNS:
        for p in glob.glob(str(REPO_ROOT / pat), recursive=True):
            files.append(Path(p))

    for path in files:
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        tl = text.lower()
        idx = -1
        if tag_l in tl:
            idx = tl.find(tag_l)
        elif short_form in tl and len(short_form) > 4:
            idx = tl.find(short_form)
        if idx == -1:
            continue
        lines = text.splitlines()
        cum = 0
        hit_line = 0
        for i, ln in enumerate(lines):
            if cum + len(ln) + 1 > idx:
                hit_line = i
                break
            cum += len(ln) + 1
        nearest_heading = None
        for j in range(hit_line, -1, -1):
            if lines[j].startswith(("## ", "### ", "# ")):
                nearest_heading = lines[j].strip()
                break
        ctx_start = max(0, hit_line - 2)
        ctx_end = min(len(lines), hit_line + 4)
        snippet = "\n".join(lines[ctx_start:ctx_end]).strip()
        hits.append(
            {
                "path": str(path.relative_to(REPO_ROOT)),
                "heading": nearest_heading,
                "snippet": snippet[:600],
            }
        )

    days_since_intake = None
    first_seen_commit = None
    try:
        r = subprocess.run(
            [
                "git",
                "log",
                "--all",
                "--reverse",
                "--pretty=format:%h|%ai|%s",
                "-S",
                tag,
                "--",
                "config/portal.yaml",
                "config/PENDING_MODEL_VERDICTS.md",
            ],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=15,
        )
        first = r.stdout.splitlines()[:1]
        if first:
            parts = first[0].split("|", 2)
            first_seen_commit = parts[0]
            dt_s = parts[1].split(" ")[0]
            first_dt = _dt.date.fromisoformat(dt_s)
            days_since_intake = (_dt.date.today() - first_dt).days
    except Exception:
        pass

    return {
        "hits": hits[:5],
        "first_seen_commit": first_seen_commit,
        "days_since_intake": days_since_intake,
    }


def load_portal() -> dict:
    return yaml.safe_load(PORTAL_PATH.read_text(encoding="utf-8"))


def bench_workspaces_routing_to(tag: str, portal: dict) -> list[str]:
    hits = []
    for slug, spec in portal.get("workspaces", {}).items():
        if not slug.startswith("bench-"):
            continue
        if spec.get("model_hint") == tag:
            hits.append(slug)
            continue
        for var in (spec.get("variants") or {}).values():
            if isinstance(var, dict) and var.get("model_hint") == tag:
                hits.append(slug)
                break
    return hits


def workspace_role_tags(slug: str, portal: dict) -> tuple[str, ...]:
    spec = portal.get("workspaces", {}).get(slug) or {}
    return tuple(spec.get("tags") or ())


def fleet_position_analysis(tag: str, features: dict, portal: dict) -> dict:
    """Where does this model live in the fleet? Iterates workspaces directly
    since portal.yaml's `tags:` field is unused in practice — arch family
    match is the reliable signal for 'covers the same territory'."""
    my_arch = features.get("arch")
    my_source_org = features.get("source_org")
    my_distinguishing = set(features.get("distinguishing", []))

    same_arch_production: list[dict] = []
    same_arch_bench: list[dict] = []
    other_arches: set[str] = set()
    other_sources: set[str] = set()
    other_distinguishing: set[str] = set()

    for slug, spec in portal.get("workspaces", {}).items():
        hint = spec.get("model_hint")
        if not hint or hint == tag:
            continue
        f = parse_tag_features(hint)
        h_arch = f.get("arch")
        if h_arch:
            other_arches.add(h_arch)
        if f.get("source_org"):
            other_sources.add(f.get("source_org"))
        for d in f.get("distinguishing", []):
            other_distinguishing.add(d)
        if my_arch and h_arch == my_arch:
            entry = {"workspace": slug, "model_hint": hint}
            if slug.startswith("bench-"):
                same_arch_bench.append(entry)
            else:
                same_arch_production.append(entry)

    # Net-new signals
    net_new = []
    if my_arch and my_arch not in other_arches:
        net_new.append(f"arch family: `{my_arch}` (not in fleet elsewhere)")
    if (
        my_source_org
        and my_source_org not in other_sources
        and my_source_org not in ("ollama-library", "ollama-library-namespaced")
    ):
        net_new.append(f"vendor: `{my_source_org}` (not in fleet elsewhere)")
    for d in my_distinguishing - other_distinguishing:
        net_new.append(f"capability: {d}")

    return {
        "same_arch_production": same_arch_production,
        "same_arch_bench": same_arch_bench,
        "other_arches_in_fleet": sorted(other_arches),
        "net_new": net_new,
        "coverage_gap_if_removed": my_arch is not None
        and not same_arch_production
        and not same_arch_bench,
    }


def fleet_diversity_analysis(tag: str, features: dict, portal: dict, position: dict) -> dict:
    my_arch = features.get("arch") or "unknown"
    my_source_org = features.get("source_org") or "unknown"

    total_arch_count = len(position["same_arch_production"]) + len(position["same_arch_bench"])

    same_source_count = 0
    for slug, spec in portal.get("workspaces", {}).items():
        hint = spec.get("model_hint")
        if not hint or hint == tag:
            continue
        f = parse_tag_features(hint)
        if f.get("source_org") == my_source_org:
            same_source_count += 1

    return {
        "total_arch_count_in_fleet_ex_this": total_arch_count,
        "removes_arch_from_fleet_entirely": my_arch != "unknown" and total_arch_count == 0,
        "total_source_count_in_fleet_ex_this": same_source_count,
        "removes_source_from_fleet_entirely": my_source_org
        not in ("ollama-library", "ollama-library-namespaced", "unknown")
        and same_source_count == 0,
    }


def evidence_date(rel_path: str) -> _dt.date | None:
    m = TS_RE.search(rel_path)
    if m:
        try:
            return _dt.datetime.strptime(m.group(1), "%Y%m%d").date()
        except ValueError:
            pass
    p = REPO_ROOT / rel_path
    try:
        return _dt.date.fromtimestamp(p.stat().st_mtime)
    except OSError:
        return None


# TASK_BENCH_VALIDITY_V1: which harness (results-file prefix) produces valid
# evidence for which capability category. A category's evidence is only
# instrument-appropriate if it came from a listed harness. bench_tps counts as
# a TPS-floor data point for every category, but for capability-specialized
# categories it is NOT the capability-appropriate signal on its own.
_HARNESS_FOR_CATEGORY: dict[str, set[str]] = {
    "security-tooling": {"security_exec_probe"},  # harness to be built; bench_tps insufficient
    "cua": {"cad_probe", "fara_cua_probe"},
    "vision": {"vision_probe"},
    "mtp-speculative": {"mtp_probe"},
    "reasoning-explicit": {"persona_matrix", "capability_probe"},  # reasoning-aware grading
    "agent-toolcall": {"tool_use_probe"},  # harness to be built; bench_tps insufficient
    "long-context": {"long_context_probe"},
    "abliterated": {"refusal_preservation_probe"},
    "moe": {"bench_tps"},  # bench_tps + MoE profile — bench_tps is acceptable
    "general": {"bench_tps", "persona_matrix"},
}


def _harness_of_path(rel_path: str) -> str:
    base = rel_path.rsplit("/", 1)[-1]
    for prefix, harness in (
        ("bench_tps_", "bench_tps"),
        ("mtp_probe_", "mtp_probe"),
        ("vision_probe_", "vision_probe"),
        ("refusal_preservation_probe_", "refusal_preservation_probe"),
        ("long_context_probe_", "long_context_probe"),
        ("cad_probe_", "cad_probe"),
        ("fara_cua_probe_", "fara_cua_probe"),
        ("security_exec_probe_", "security_exec_probe"),
        ("tool_use_probe_", "tool_use_probe"),
        ("research_probe_", "research_probe"),
        ("persona_matrix_", "persona_matrix"),
        ("v11_capability_", "capability_probe"),
    ):
        if base.startswith(prefix):
            return harness
    return "unknown"


def collect_numeric_evidence(
    tag: str,
    evidence_paths: list[str],
    bench_slugs: list[str],
    stack_boundary_days: int = STACK_BOUNDARY_DAYS,
) -> dict:
    needles = {tag.lower(), *(s.lower() for s in bench_slugs)}
    today = _dt.date.today()
    boundary = today - _dt.timedelta(days=stack_boundary_days)

    tps_rows_valid = []
    tps_rows_invalid = []
    closeouts_valid = []
    closeouts_invalid = []
    dates = []
    valid_harnesses: set[str] = set()
    for rel in evidence_paths:
        p = REPO_ROOT / rel
        if not p.exists():
            continue
        d = evidence_date(rel)
        if d:
            dates.append(d)
        is_valid = d is not None and d >= boundary
        _harness = _harness_of_path(rel)
        if p.suffix == ".json":
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                continue
            rows = data.get("results") if isinstance(data, dict) else data
            if not isinstance(rows, list):
                continue
            for r in rows:
                if not isinstance(r, dict):
                    continue
                model_l = str(r.get("model") or "").lower()
                routed_l = str(r.get("routed_model") or "").lower()
                if any(n in model_l or n in routed_l for n in needles):
                    r = dict(r)
                    r["_harness"] = _harness
                    if is_valid:
                        tps_rows_valid.append(r)
                        valid_harnesses.add(_harness)
                    else:
                        tps_rows_invalid.append(r)
        elif p.suffix == ".md":
            tl = p.read_text(encoding="utf-8", errors="ignore").lower()
            for token in (
                "promote-candidate",
                "decline",
                "declined",
                "not-adopted",
                "stage-pending",
                "pass",
                "blocked",
            ):
                if token in tl and tag.lower() in tl:
                    (closeouts_valid if is_valid else closeouts_invalid).append((token, rel))
                    break

    def _avg(xs):
        xs = [x for x in xs if isinstance(x, (int, float))]
        return round(statistics.mean(xs), 2) if xs else None

    newest = max(dates) if dates else None
    age = (today - newest).days if newest else None
    newest_valid = max((d for d in dates if d >= boundary), default=None)
    return {
        # legacy-shaped fields (post-boundary only — the safe defaults)
        "n_rows": len(tps_rows_valid),
        "avg_tps": _avg([r.get("avg_tps") for r in tps_rows_valid]),
        "avg_quality": _avg([r.get("quality_score") for r in tps_rows_valid]),
        "closeout_signals": sorted({v for v, _ in closeouts_valid}),
        "closeout_sources": [src for _, src in closeouts_valid[:3]],
        "newest_date": newest.isoformat() if newest else None,
        "newest_age_days": age,
        "stale": age is not None and age > STALE_DAYS,
        # new fields for stack-boundary awareness
        "n_valid_rows": len(tps_rows_valid),
        "n_invalid_rows": len(tps_rows_invalid),
        "avg_tps_invalid": _avg([r.get("avg_tps") for r in tps_rows_invalid]),
        "closeout_signals_invalid": sorted({v for v, _ in closeouts_invalid}),
        "closeout_sources_invalid": [src for _, src in closeouts_invalid[:3]],
        "newest_valid_date": newest_valid.isoformat() if newest_valid else None,
        "stack_boundary_date": boundary.isoformat(),
        "has_valid_evidence": len(tps_rows_valid) > 0 or len(closeouts_valid) > 0,
        # TASK_BENCH_VALIDITY_V1: harnesses that produced post-boundary rows,
        # for the category-coherence gate applied once the category is known.
        "valid_harnesses": sorted(valid_harnesses),
    }


def apply_coherence_gate(numeric: dict, category_id: str) -> dict:
    """TASK_BENCH_VALIDITY_V1 coherence gate: post-boundary evidence only counts
    as *capability-appropriate* if it came from a harness listed for the model's
    category. A bench_tps coding row on a reasoning-explicit or security-tooling
    model is retained as a data point (visible on the sheet) but does NOT satisfy
    has_valid_evidence — because it measured the wrong thing.

    Mutates and returns `numeric` with:
      - instrument_ok: bool — at least one valid row came from a right harness
      - wrong_instrument_harnesses: harnesses present but not category-appropriate
      - has_valid_evidence: ANDed with instrument_ok (closeouts still count)
      - rebench_reason: why a re-bench is still owed, if any
    """
    appropriate = _HARNESS_FOR_CATEGORY.get(category_id, {"bench_tps", "persona_matrix"})
    present = set(numeric.get("valid_harnesses") or [])
    right = present & appropriate
    wrong = present - appropriate

    instrument_ok = bool(right)
    numeric["instrument_ok"] = instrument_ok
    numeric["wrong_instrument_harnesses"] = sorted(wrong)
    numeric["appropriate_harnesses"] = sorted(appropriate)

    had_closeout = bool(numeric.get("closeout_signals"))
    # Evidence is decision-grade only if a right instrument ran (or a
    # post-boundary closeout exists). Wrong-instrument rows stay as data points.
    numeric["has_valid_evidence"] = instrument_ok or had_closeout

    if instrument_ok or had_closeout:
        numeric["rebench_reason"] = None
    elif wrong:
        numeric["rebench_reason"] = (
            f"only wrong-instrument evidence ({', '.join(sorted(wrong))}) for a "
            f"`{category_id}` model — needs {', '.join(sorted(appropriate))}"
        )
    else:
        numeric["rebench_reason"] = f"no post-boundary evidence for a `{category_id}` model"
    return numeric


# ---------------- Bench prescription (capability-appropriate re-bench) ----------------

# Categories map a model's advertised capability to the appropriate bench
# harness, prompt corpus, and metrics. Order matters — first match wins,
# so specific categories (security-tooling, cua, mtp) come before general
# ones (moe, general).
CAPABILITY_CATEGORIES: list[dict] = [
    {
        "id": "security-tooling",
        "label": "Security tooling (exploit / artifact generation)",
        "match_deployment": ["cyber", "security"],
        "match_features": [
            "Cyber / security domain training",
            "Blue-team security tuned",
            "Red-team security tuned",
        ],
        "match_card_text": [
            "exploit",
            "nuclei",
            "penetration",
            "bug bounty",
            "cve reproduction",
            "poc",
            "vulnerability writeup",
        ],
        "harness": "security exec-chain scorer — measures artifact runnability, not chat quality",
        "prompt_corpus": "CVE writeup → PoC; vulnerability description → Nuclei template; exploit-target descriptions",
        "metrics": [
            "artifact runnability (compiles / executes as-emitted)",
            "refusal rate on offensive prompts (should be near-zero for these models)",
            "attack-chain success on synthetic targets",
        ],
        "dont_measure": [
            "MMLU / general chat quality — model was not trained for chat",
            "refusal on benign prompts — irrelevant to the capability",
        ],
        "slot_requirements": {
            "tools": "empty ([]) — tool exposure causes reasoning-loop failures per BugTraceAI card guidance",
            "emits_reasoning": "true — capture the reasoning trace, don't suppress it",
            "temperature": "0.1–0.3 for reproducibility",
        },
    },
    {
        "id": "cua",
        "label": "Computer-use agent (CUA)",
        "match_deployment": ["computer-use agent (CUA)"],
        "match_features": [],
        "match_card_text": [
            "computer-use",
            "browser control",
            "screenshot",
            "gui automation",
            "ui element",
            "click",
            "screen",
        ],
        "harness": "CUA probe (screenshot → action) — TPS alone is not the capability signal",
        "prompt_corpus": "browser task description + rendered screenshot pairs; UI element grounding tasks",
        "metrics": [
            "action accuracy on browser screenshots",
            "element grounding precision (click coordinate error)",
            "multi-step task completion rate",
        ],
        "dont_measure": [
            "general chat quality — model is agent-tuned, chat quality is a distraction",
            "text-only benchmarks",
        ],
        "slot_requirements": {
            "mmproj": "vision projector configuration REQUIRED — the bench cannot produce valid data without it",
            "tools": "browser/screenshot tool definitions if the CUA harness expects them",
            "workspace_description": "must reflect CUA intent, not general chat",
        },
    },
    {
        "id": "vision",
        "label": "Vision / multimodal (non-CUA)",
        "match_deployment": ["vision / multimodal capability advertised"],
        "match_features": ["Vision / multimodal"],
        "match_card_text": ["image input", "image understanding", "visual question"],
        "harness": "vision probe (image → text tasks)",
        "prompt_corpus": "image + question pairs across VQA, captioning, OCR",
        "metrics": [
            "VQA accuracy",
            "caption quality",
            "OCR fidelity if advertised",
        ],
        "dont_measure": [
            "text-only quality alone — misses the modality that justifies the model",
        ],
        "slot_requirements": {
            "mmproj": "vision projector REQUIRED",
        },
    },
    {
        "id": "mtp-speculative",
        "label": "MTP / speculative drafting",
        "match_deployment": ["speculative / MTP drafting"],
        "match_features": ["MTP speculative drafting"],
        "match_card_text": [],
        "harness": "MTP-aware bench — draft acceptance rate + wall-time speedup vs base",
        "prompt_corpus": "IDENTICAL to base model's bench for direct comparison",
        "metrics": [
            "draft token acceptance rate (headline signal)",
            "wall-time speedup vs base model on identical prompts",
            "quality parity vs base (any regression kills the value proposition)",
        ],
        "dont_measure": [
            "raw TPS without comparing to base — meaningless in isolation",
        ],
        "slot_requirements": {
            "paired_draft": "draft model config must be present, correct, and pinned to matching base",
        },
    },
    {
        "id": "reasoning-explicit",
        "label": "Explicit reasoning / thinking traces",
        "match_deployment": ["reasoning-trace capability"],
        "match_features": ["Explicit thinking / reasoning traces"],
        "match_card_text": [
            "<think>",
            "chain-of-thought",
            "reasoning trace",
            "deliberation before answer",
        ],
        "harness": "reasoning-aware persona matrix — capture and score the thinking traces, not just final answers",
        "prompt_corpus": "multi-step reasoning tasks: math, logic, planning, code with edge cases",
        "metrics": [
            "task success rate WITH reasoning captured",
            "reasoning coherence score",
            "TPS separated by reasoning-on vs reasoning-off runs",
            "trace length vs task complexity",
        ],
        "dont_measure": [
            "single-turn factual recall (doesn't exercise reasoning)",
        ],
        "slot_requirements": {
            "emits_reasoning": "true — otherwise the harness sees a truncated model",
            "predict_limit": "high enough to fit thinking traces (8k+ typical)",
        },
    },
    {
        "id": "agent-toolcall",
        "label": "Agent / tool-use tuned",
        "match_deployment": ["advertises tool-use / function-calling"],
        "match_features": ["Agent-tuned", "Tool-use tuned"],
        "match_card_text": ["function call", "tool use", "agent framework", "tool orchestration"],
        "harness": "tool-use probe — schema conformance + multi-turn tool chain success",
        "prompt_corpus": "tool definitions + tasks requiring their invocation across turns",
        "metrics": [
            "tool-call schema conformance (parses, correct args)",
            "argument correctness for supplied schemas",
            "multi-turn tool chain success",
        ],
        "dont_measure": [
            "single-turn text quality alone — misses the agent capability",
        ],
        "slot_requirements": {
            "tools": "populated with representative tool definitions",
        },
    },
    {
        "id": "long-context",
        "label": "Long-context extension",
        "match_deployment": ["explicit context-length claim"],
        "match_features": ["Long-context extension"],
        "match_card_text": [
            "long context",
            "extended context",
            "million token",
            "128k",
            "256k",
            "1m context",
        ],
        "harness": "long-context probe — needle-in-haystack + coherence@length",
        "prompt_corpus": "graduated-length synthetic (needle) + real long documents",
        "metrics": [
            "needle recall at 8k / 32k / 128k+ / advertised max",
            "coherence degradation curve across length",
            "TPS at length (attention scaling reality check)",
        ],
        "dont_measure": [
            "short-context TPS alone — misses the whole capability",
        ],
        "slot_requirements": {
            "predict_limit": "≥ card's advertised context length",
        },
    },
    {
        "id": "abliterated",
        "label": "Abliterated / uncensored",
        "match_deployment": ["abliterated / uncensored"],
        "match_features": [
            "Abliterated (safety-vector ablation)",
            "Heretic-modified (jailbreak retraining)",
        ],
        "match_card_text": ["safety-vector ablation", "uncensored", "refusal removed"],
        "harness": "refusal-rate probe + capability-preservation vs base",
        "prompt_corpus": "safety-elicitation set + standard capability set matched to base",
        "metrics": [
            "refusal rate on safety prompts (should be low — the point of the model)",
            "capability preservation vs base (chat quality, task success) — did ablation break the model?",
        ],
        "dont_measure": [],
        "slot_requirements": {},
    },
    {
        "id": "moe",
        "label": "MoE architecture",
        "match_deployment": ["MoE architecture confirmed"],
        "match_features": ["MoE architecture (routes tokens to expert subsets)"],
        "match_card_text": ["mixture of experts", "active parameters", "experts per token"],
        "harness": "bench_tps + MoE-aware profile (active-param observation)",
        "prompt_corpus": "mixed-domain prompt matrix to exercise routing",
        "metrics": [
            "standard TPS",
            "active-param distribution across prompt buckets",
            "expert routing stability (does the same prompt route consistently)",
        ],
        "dont_measure": [],
        "slot_requirements": {},
    },
    {
        "id": "general",
        "label": "General / no specific capability advertised",
        "match_deployment": [],
        "match_features": [],
        "match_card_text": [],
        "harness": "bench_tps + portal5_persona_matrix (standard fleet path)",
        "prompt_corpus": "default persona matrix across the model's target lane",
        "metrics": [
            "avg_tps vs the 20 t/s floor",
            "quality_score vs same-lane incumbent",
        ],
        "dont_measure": [],
        "slot_requirements": {},
    },
]


def _matches_category(category: dict, features: dict, card_claims: dict) -> bool:
    if not any(
        category["match_deployment"] or category["match_features"] or category["match_card_text"]
    ):
        return True  # general / fallback
    deployment = set(card_claims.get("deployment_notes") or [])
    features_set = set(features.get("distinguishing") or [])
    caps_text = " ".join(
        [
            (card_claims.get("description") or ""),
            *(section for section in (card_claims.get("capabilities") or {}).values()),
        ]
    ).lower()

    for token in category["match_deployment"]:
        if any(token in d for d in deployment):
            return True
    for token in category["match_features"]:
        if any(token in f for f in features_set):
            return True
    return any(token in caps_text for token in category["match_card_text"])


def bench_prescription(
    features: dict, card_claims: dict, alignment: dict, slots: list[dict], numeric: dict
) -> dict:
    """Emit a capability-appropriate re-bench prescription. Only interesting
    when the model needs refreshing — but always computed so the operator
    can cross-check slot configuration even against valid-evidence models."""
    # Categorize
    matched = None
    for cat in CAPABILITY_CATEGORIES:
        if _matches_category(cat, features, card_claims):
            matched = cat
            break
    if matched is None:
        matched = CAPABILITY_CATEGORIES[-1]  # general fallback

    # Slot-fix analysis: what MUST change in workspace config for a bench
    # to produce valid data? A CUA model with no mmproj = benching wrong
    # thing even if the prompts are right.
    slot_fixes: list[str] = []
    requirements = matched.get("slot_requirements") or {}

    if not slots and requirements:
        slot_fixes.append(
            f"model is bench-orphaned — a workspace must be added to portal.yaml before benching "
            f"(recommended: `bench-{features['tag'].split('/')[-1].split(':')[0][:20]}`)"
        )

    for slot in slots:
        slot_text = " ".join(
            [
                slot.get("description", ""),
                slot.get("name", ""),
                slot.get("system_prompt", "") or "",
            ]
        ).lower()

        for req_key, req_value in requirements.items():
            if req_key == "tools":
                if "empty" in req_value.lower() or "[]" in req_value:
                    if slot.get("tools"):
                        slot_fixes.append(
                            f"`{slot['workspace']}`: card requires `tools: []` but slot has {slot['tools']} — clear before benching"
                        )
                elif "populated" in req_value.lower() or "definitions" in req_value.lower():
                    if not slot.get("tools"):
                        slot_fixes.append(
                            f"`{slot['workspace']}`: bench harness needs tools populated but slot has `tools: []` — configure representative tools"
                        )
            elif req_key == "emits_reasoning":
                if "true" in req_value.lower() and not slot.get("emits_reasoning"):
                    slot_fixes.append(
                        f"`{slot['workspace']}`: needs `emits_reasoning: true` — otherwise reasoning trace is suppressed"
                    )
            elif req_key == "mmproj":
                if not any(k in slot_text for k in ("mmproj", "vision", "projector", "image")):
                    slot_fixes.append(
                        f"`{slot['workspace']}`: needs vision projector (`mmproj`) — the bench cannot produce valid multimodal data without it"
                    )
            elif req_key == "predict_limit":
                if not slot.get("predict_limit") or (
                    isinstance(slot.get("predict_limit"), int) and slot["predict_limit"] < 8192
                ):
                    slot_fixes.append(
                        f"`{slot['workspace']}`: `predict_limit` needs to accommodate {req_value.lower()}"
                    )
            elif req_key == "workspace_description":
                # Compare intent
                mismatch = any(k in slot_text for k in ("general chat", "chat eval")) and matched[
                    "id"
                ] in (
                    "cua",
                    "security-tooling",
                    "vision",
                    "agent-toolcall",
                )
                if mismatch:
                    slot_fixes.append(
                        f"`{slot['workspace']}`: description says general/chat but capability is `{matched['id']}` — update description and bench intent"
                    )
            elif req_key == "paired_draft":
                if "draft" not in slot_text and "mtp" not in slot_text:
                    slot_fixes.append(
                        f"`{slot['workspace']}`: MTP benching requires paired draft model config — check `predict_limit` and draft binding"
                    )

    # Alignment mismatches from Part B3 count as slot fixes too
    for m in alignment.get("mismatches", []):
        # Only add if we haven't already got a related slot fix
        if not any(m[:40].lower() in existing.lower() for existing in slot_fixes):
            slot_fixes.append(m)

    return {
        "category_id": matched["id"],
        "category_label": matched["label"],
        "harness": matched["harness"],
        "prompt_corpus": matched["prompt_corpus"],
        "metrics": matched["metrics"],
        "dont_measure": matched["dont_measure"],
        "slot_requirements": requirements,
        "slot_fixes_required": slot_fixes,
        "blocked_by_slot": bool(slot_fixes),
        "needs_rebench": not numeric["has_valid_evidence"],
    }


def render_prescription(rx: dict) -> list[str]:
    lines = []
    if rx["needs_rebench"]:
        lines.append("- **Re-bench REQUIRED** (no post-boundary evidence)")
    lines.append(f"- **Capability category:** `{rx['category_id']}` — {rx['category_label']}")
    lines.append(f"- **Recommended harness:** {rx['harness']}")
    lines.append(f"- **Prompt corpus:** {rx['prompt_corpus']}")
    if rx["metrics"]:
        lines.append("- **Metrics to capture (beyond raw TPS):**")
        for m in rx["metrics"]:
            lines.append(f"  - {m}")
    if rx["dont_measure"]:
        lines.append("- **Do NOT measure (would produce invalid signal for this capability):**")
        for d in rx["dont_measure"]:
            lines.append(f"  - {d}")
    if rx["slot_requirements"]:
        lines.append("- **Workspace slot requirements for valid bench data:**")
        for k, v in rx["slot_requirements"].items():
            lines.append(f"  - `{k}`: {v}")
    if rx["slot_fixes_required"]:
        lines.append(
            "- ⚠ **Slot fixes REQUIRED before re-bench** (bench data invalid until resolved):"
        )
        for f in rx["slot_fixes_required"]:
            lines.append(f"  - {f}")
    return lines


# ---------------- Model card cache + slotting analysis ----------------


def tag_hash(tag: str) -> str:
    return hashlib.sha256(tag.encode("utf-8")).hexdigest()[:16]


def load_card_cache(tag: str) -> dict:
    """Read Part B2's card cache for this tag. Returns a dict with
    'status', 'url', 'body' (or None), 'available' (bool). Absent cache
    entries return {'available': False, 'status': 'not-fetched'}."""
    h = tag_hash(tag)
    card_p = CARD_CACHE_DIR / f"{h}.card.md"
    meta_p = CARD_CACHE_DIR / f"{h}.meta.json"
    if not meta_p.exists():
        return {"available": False, "status": "not-fetched", "body": None, "url": None}
    try:
        meta = json.loads(meta_p.read_text())
    except Exception:
        return {"available": False, "status": "meta-parse-error", "body": None, "url": None}
    body = card_p.read_text(encoding="utf-8", errors="ignore") if card_p.exists() else ""
    return {
        "available": meta.get("status") == "ok" and bool(body.strip()),
        "status": meta.get("status", "unknown"),
        "body": body if body.strip() else None,
        "url": meta.get("url"),
        "fetched_at": meta.get("fetched_at"),
    }


# Section headings a model card typically uses to advertise strengths
CAPABILITY_HEADING_RE = re.compile(
    r"^#{1,4}\s*(?:"
    r"Capabilit(?:y|ies)|"
    r"(?:Use|Recommended|Intended|Primary|Best|Ideal)[- ]?[Cc]ases?|"
    r"(?:Strength|Highlight|Feature|Task|Ability|Skill)s?|"
    r"(?:Designed|Trained|Optimized|Built|Best)\s+[Ff]or|"
    r"(?:Excel|Perform)s?\s+[Aa]t|"
    r"Deployment(?:\s+Notes?)?|"
    r"What This Model (?:Is|Does)"
    r")\s*[:.]?\s*$",
    re.MULTILINE,
)

ANTI_CAPABILITY_HEADING_RE = re.compile(
    r"^#{1,4}\s*(?:"
    r"What This Model Is NOT|"
    r"Not (?:For|Recommended|Suitable)|"
    r"Limitations?|"
    r"Do NOT"
    r")\s*.*$",
    re.MULTILINE,
)


def extract_card_claims(body: str) -> dict:
    """Pull structured signals from a model card:
    - description: first substantive paragraph after title
    - capability sections: heading -> extracted bullet/paragraph text
    - anti-capability sections: what the model is NOT for
    - deployment notes: mentions of tools, chat template, mmproj, context
    Aggressively bounded — never returns more than ~4kb per section."""
    if not body:
        return {
            "description": None,
            "capabilities": {},
            "anti_capabilities": {},
            "deployment_notes": [],
        }

    # Strip YAML frontmatter
    text = body
    if text.startswith("---\n"):
        end = text.find("\n---\n", 4)
        if end != -1:
            text = text[end + 5 :]

    lines = text.splitlines()

    # First substantive paragraph (skip title lines and blanks)
    desc_lines = []
    in_prose = False
    for ln in lines:
        s = ln.strip()
        if not in_prose:
            if not s or s.startswith("#") or s.startswith("!") or s.startswith("["):
                continue
            in_prose = True
        if in_prose:
            if not s:
                if desc_lines:
                    break
                continue
            if s.startswith("#"):
                break
            desc_lines.append(s)
            if sum(len(x) for x in desc_lines) > 500:
                break
    description = " ".join(desc_lines)[:600] if desc_lines else None

    def _extract_sections(regex):
        out = {}
        for m in regex.finditer(text):
            heading = m.group(0).strip().lstrip("#").strip().rstrip(":.").strip()
            start = m.end()
            # Take up to next heading or 1500 chars
            rest = text[start : start + 1500]
            next_h = re.search(r"\n#{1,4}\s", rest)
            if next_h:
                rest = rest[: next_h.start()]
            body_str = rest.strip()
            if body_str:
                out[heading] = body_str[:1200]
        return out

    capabilities = _extract_sections(CAPABILITY_HEADING_RE)
    anti_capabilities = _extract_sections(ANTI_CAPABILITY_HEADING_RE)

    # Deployment-note signals (single-line matches anywhere)
    deployment_notes = []
    deploy_patterns = [
        (r"(?i)do\s*not\s+(?:provide|expose|use)\s+tool[s]?", "advises against tool exposure"),
        (r"(?i)tool[- ]?use\s+(?:disabled|not\s+supported|discouraged)", "tool-use not supported"),
        (
            r"(?i)supports?\s+(?:function[- ]?calling|tool[- ]?use)",
            "advertises tool-use / function-calling",
        ),
        (
            r"(?i)vision|multimodal|mmproj|image\s+input",
            "vision / multimodal capability advertised",
        ),
        (
            r"(?i)context(?:\s+length|\s+window)?[:\s]+(\d+)[k]?\s*(?:tokens?)?",
            "explicit context-length claim",
        ),
        (r"(?i)chat[- ]?template", "specific chat template requirement"),
        (r"(?i)computer[- ]?use|CUA|browser\s+control", "computer-use agent (CUA)"),
        (r"(?i)reasoning|<think>|chain[- ]?of[- ]?thought", "reasoning-trace capability"),
        (
            r"(?i)abliterated|uncensored|(?:safety[- ]?vector\s+)?ablation",
            "abliterated / uncensored",
        ),
        (
            r"(?i)MoE|mixture\s+of\s+experts|(?:experts?\s+per\s+token)|active\s+params",
            "MoE architecture confirmed",
        ),
        (
            r"(?i)(?:speculative|MTP|multi[- ]?token\s+prediction|draft(?:ing)?\s+model)",
            "speculative / MTP drafting",
        ),
    ]
    negation_re = re.compile(
        r"(?i)\b(?:no|not|without|removed|lacks?|isn'?t|doesn'?t\s+(?:have|support)|"
        r"was\s+removed|has\s+been\s+removed)\b"
    )
    for pat, label in deploy_patterns:
        m = re.search(pat, text)
        if not m:
            continue
        window = text[max(0, m.start() - 40) : m.end() + 60]
        if not negation_re.search(window):
            deployment_notes.append(label)

    return {
        "description": description,
        "capabilities": capabilities,
        "anti_capabilities": anti_capabilities,
        "deployment_notes": deployment_notes,
    }


def workspace_slotting_for_tag(tag: str, portal: dict) -> list[dict]:
    """Return the descriptive context for every bench workspace routing
    to this tag. portal.yaml's `description` field on each workspace
    contains our team's intake rationale + slotting intent — this is
    'what we think the model does' vs the card's 'what the model does'."""
    slots = []
    for slug, spec in portal.get("workspaces", {}).items():
        if not slug.startswith("bench-"):
            continue
        if spec.get("model_hint") != tag:
            # also check variants
            hit = False
            for var in (spec.get("variants") or {}).values():
                if isinstance(var, dict) and var.get("model_hint") == tag:
                    hit = True
                    break
            if not hit:
                continue
        slots.append(
            {
                "workspace": slug,
                "name": spec.get("name", slug),
                "description": (spec.get("description") or "").strip(),
                "module": spec.get("module"),
                "tools": spec.get("tools") or [],
                "expose_to_owui": spec.get("expose_to_owui", False),
                "emits_reasoning": spec.get("emits_reasoning", False),
                "system_prompt": spec.get("owui_system_prompt")
                or spec.get("system_prompt_append", ""),
                "temperature": spec.get("temperature"),
                "predict_limit": spec.get("predict_limit"),
            }
        )
    return slots


def alignment_analysis(claims: dict, slots: list[dict]) -> dict:
    """Compare card claims against workspace slotting. Surface mismatches
    the operator should probe before deciding. Never authoritative — the
    operator eyeballs both sides."""
    if not claims or not claims.get("description") and not claims.get("capabilities"):
        return {"available": False, "mismatches": [], "matches": [], "untested": []}

    mismatches = []
    matches = []

    if not slots:
        # Bench-orphaned: card exists but nothing routes to it
        return {
            "available": True,
            "mismatches": [
                "**bench-orphaned**: card advertises capabilities but no workspace routes to this tag — every advertised strength is untested here"
            ],
            "matches": [],
            "untested": list(claims.get("capabilities", {}).keys()),
        }

    all_slot_text = " ".join(
        (s.get("description", "") + " " + s.get("name", "") + " " + str(s.get("system_prompt", "")))
        for s in slots
    ).lower()

    # Tool-use disagreement: card says no tools, slot exposes tools (or vice versa)
    card_says_no_tools = "advises against tool exposure" in claims.get(
        "deployment_notes", []
    ) or "tool-use not supported" in claims.get("deployment_notes", [])
    card_says_yes_tools = "advertises tool-use / function-calling" in claims.get(
        "deployment_notes", []
    )
    for s in slots:
        slot_has_tools = bool(s.get("tools"))
        if card_says_no_tools and slot_has_tools:
            mismatches.append(
                f"card advises AGAINST tool exposure but `{s['workspace']}` has tools configured: {s['tools']}"
            )
        elif card_says_no_tools and not slot_has_tools:
            matches.append(
                f"card advises against tools; `{s['workspace']}` correctly has `tools: []`"
            )
        if card_says_yes_tools and not slot_has_tools:
            mismatches.append(
                f"card advertises tool-use / function-calling but `{s['workspace']}` has no tools — advertised capability untested"
            )

    # Vision / CUA claims: does any slot indicate vision/CUA testing?
    if "vision / multimodal capability advertised" in claims.get("deployment_notes", []):
        if not any(
            k in all_slot_text
            for k in ("vision", "image", "mmproj", "cua", "computer-use", "screenshot")
        ):
            mismatches.append(
                "card advertises vision/multimodal but no slot text mentions vision, mmproj, or image tasks — advertised capability likely untested"
            )
    if "computer-use agent (CUA)" in claims.get("deployment_notes", []):
        if not any(
            k in all_slot_text for k in ("cua", "computer-use", "browser", "screenshot", "ui")
        ):
            mismatches.append(
                "card advertises CUA (computer-use agent) but no slot text mentions CUA, browser, or UI tasks — advertised capability untested"
            )

    # Reasoning claim: does slot enable reasoning capture?
    if "reasoning-trace capability" in claims.get("deployment_notes", []):
        if not any(s.get("emits_reasoning") for s in slots):
            mismatches.append(
                "card advertises reasoning traces but no slot has `emits_reasoning: true` — advertised capability untested"
            )
        else:
            matches.append("card advertises reasoning; slot has `emits_reasoning: true`")

    # Coarse capability-heading vs slot-text overlap: for each advertised
    # capability header, does any word from it appear in slot text?
    untested = []
    for heading, section_body in (claims.get("capabilities") or {}).items():
        # Extract distinctive words from the capability heading and section body
        section_words = set(re.findall(r"\b([a-z]{5,})\b", (heading + " " + section_body).lower()))
        # drop common noise
        section_words -= {
            "model",
            "capabilities",
            "using",
            "based",
            "trained",
            "supported",
            "recommended",
            "tasks",
            "cases",
            "these",
            "provides",
            "includes",
            "example",
            "including",
            "context",
            "response",
            "designed",
            "recommend",
            "should",
            "quality",
            "output",
            "features",
            "language",
            "generally",
            "generation",
        }
        if not section_words:
            continue
        overlap = [w for w in section_words if w in all_slot_text]
        if not overlap:
            untested.append(f"`{heading}` — no keyword overlap with any slot description")

    return {
        "available": True,
        "mismatches": mismatches,
        "matches": matches,
        "untested": untested[:5],
    }


def what_wed_lose(features: dict, position: dict, diversity: dict) -> list[str]:
    losses = []
    my_arch = features.get("arch") or "unknown"
    if diversity["removes_arch_from_fleet_entirely"]:
        losses.append(
            f"**{my_arch} disappears from the fleet entirely** — no other workspace uses this arch family"
        )
    if diversity["removes_source_from_fleet_entirely"]:
        losses.append(
            f"**last model from `{features.get('source_org', 'unknown')}`** — vendor exits the fleet"
        )
    for signal in position["net_new"]:
        losses.append(f"NET-NEW {signal}")
    for feat in features.get("distinguishing", []):
        if any(
            k in feat
            for k in (
                "Vision",
                "MoE",
                "MTP",
                "Abliterated",
                "Heretic",
                "Blue-team",
                "Red-team",
                "Cyber",
                "Long-context",
                "Unsloth Dynamic",
                "Agent-tuned",
            )
        ):
            if not any(feat in loss for loss in losses):
                losses.append(f"capability: {feat}")
    if position["coverage_gap_if_removed"]:
        losses.append(f"only exploration of `{my_arch}` arch — no other workspace tests it")
    if not losses:
        losses.append(
            "nothing distinctive — arch/vendor/capability all remain represented after removal"
        )
    return losses


def hypothesis(
    features: dict, rationale: dict, position: dict, diversity: dict, numeric: dict, alignment: dict
) -> tuple[str, str, list[str]]:
    signals: list[tuple[str, int]] = []

    # Post-boundary closeout is authoritative
    for tok in numeric["closeout_signals"]:
        if tok in ("decline", "declined", "not-adopted"):
            return (
                "decline",
                f"post-boundary closeout already declined ({tok})",
                [f"AUTHORITATIVE: post-boundary closeout says {tok}"],
            )
        if tok == "promote-candidate":
            return (
                "promote",
                "post-boundary closeout marked promote-candidate",
                [f"AUTHORITATIVE: post-boundary closeout says {tok}"],
            )

    # No valid (post-boundary) numeric evidence — cannot decide numerically.
    # KEEP signals (arch loss, net-new, unique capability) still stand;
    # DECLINE signals from stale numbers are refused.
    if not numeric["has_valid_evidence"]:
        # Still surface KEEP-side signals as info; force the verdict to refresh
        info_signals = []
        if diversity["removes_arch_from_fleet_entirely"]:
            info_signals.append(f"KEEP: removes {features.get('arch', 'unknown')} arch entirely")
        if position["net_new"]:
            info_signals.append(f"KEEP: {position['net_new'][0]}")
        if alignment.get("mismatches"):
            info_signals.append(
                f"KEEP: {len(alignment['mismatches'])} card/slot mismatches untested"
            )
        if numeric["closeout_signals_invalid"]:
            info_signals.append(
                f"PRE-BOUNDARY closeout: {', '.join(numeric['closeout_signals_invalid'])} — re-affirm on current stack"
            )
        if numeric["n_invalid_rows"]:
            info_signals.append(
                f"{numeric['n_invalid_rows']} pre-boundary rows exist but are INVALID (avg TPS was {numeric['avg_tps_invalid']} on prior stack)"
            )
        return (
            "investigate-refresh",
            "no post-boundary evidence — stack changed, must re-bench before any decision",
            info_signals or ["no evidence at all — re-bench required"],
        )

    # Card-vs-slotting mismatches — advertised capability we haven't tested
    if alignment.get("mismatches"):
        signals.append(
            (
                f"card/slot mismatch: {len(alignment['mismatches'])} advertised capabilities untested",
                -3,
            )
        )

    # KEEP signals (negative = bias toward keep)
    if diversity["removes_arch_from_fleet_entirely"]:
        signals.append((f"removes {features.get('arch', 'unknown')} arch from fleet entirely", -3))
    if diversity["removes_source_from_fleet_entirely"]:
        signals.append((f"removes vendor `{features.get('source_org', 'unknown')}` from fleet", -2))
    if position["net_new"]:
        signals.append((f"net-new: {position['net_new'][0]}", -2))
    if position["coverage_gap_if_removed"]:
        signals.append(("only exploration of this arch in the fleet", -2))
    unique_feats = [
        f
        for f in features.get("distinguishing", [])
        if any(
            k in f for k in ("MoE", "MTP", "Vision", "Long-context", "Abliterated", "Agent-tuned")
        )
    ]
    if unique_feats and not position["net_new"]:
        signals.append((f"unique capability: {unique_feats[0]}", -1))
    if (
        rationale["days_since_intake"] is not None
        and rationale["days_since_intake"] < RECENT_INTAKE_DAYS
    ):
        signals.append(
            (f"introduced {rationale['days_since_intake']}d ago — still in eval window", -2)
        )

    # DECLINE signals — ONLY apply to post-boundary numbers
    if numeric["avg_tps"] and numeric["avg_tps"] < 20:
        signals.append((f"post-boundary: below 20 t/s floor (avg {numeric['avg_tps']})", 2))
    if (
        diversity["total_arch_count_in_fleet_ex_this"] >= 3
        and not unique_feats
        and not alignment.get("mismatches")
    ):
        signals.append(
            (
                f"arch already {diversity['total_arch_count_in_fleet_ex_this']}-strong; this adds no capability",
                1,
            )
        )

    # Note pre-boundary signal but don't score it
    if numeric["closeout_signals_invalid"]:
        signals.append(
            (
                f"PRE-BOUNDARY closeout ({', '.join(numeric['closeout_signals_invalid'])}) — not authoritative on current stack",
                0,
            )
        )

    decline_score = sum(b for _, b in signals if b > 0)
    keep_score = sum(-b for _, b in signals if b < 0)

    if decline_score - keep_score >= 3:
        verdict = "decline"
    elif keep_score - decline_score >= 2:
        verdict = "keep-open"
    elif alignment.get("mismatches"):
        verdict = "probe-untested-capability"
    else:
        verdict = "investigate"

    para = "; ".join(s for s, _ in signals) or "no signals extracted — pure investigate"
    return verdict, para, [s for s, _ in signals]


def render_intake(rationale: dict) -> list[str]:
    lines = []
    if rationale["days_since_intake"] is not None:
        lines.append(
            f"- **Intake age:** {rationale['days_since_intake']}d ago (first-seen commit `{rationale['first_seen_commit'] or 'unknown'}`)"
        )
    else:
        lines.append("- **Intake age:** unknown (no `git log -S` match in config/)")
    if not rationale["hits"]:
        lines.append(
            "- **Documented rationale:** none found in TASK_*.md, docs/, or portal_wiki/canonical/"
        )
        return lines
    lines.append(f"- **Mentioned in {len(rationale['hits'])} doc file(s):**")
    for h in rationale["hits"][:3]:
        heading = h["heading"] or "(no nearby heading)"
        lines.append(f"  - `{h['path']}` — {heading}")
        preview = h["snippet"].replace("\n", " \\ ").strip()
        if len(preview) > 200:
            preview = preview[:200] + "…"
        lines.append(f"    > {preview}")
    return lines


def render_capability(features: dict) -> list[str]:
    lines = []
    lines.append(f"- **Architecture:** {features.get('arch', 'unknown')}")
    if "params" in features:
        lines.append(f"- **Parameters:** {features['params']}")
    if "quant" in features:
        lines.append(f"- **Quantization:** {features['quant']}")
    lines.append(
        f"- **Source:** {features.get('source', 'unknown')} (`{features.get('source_org', '')}`)"
    )
    if features["distinguishing"]:
        lines.append("- **Distinguishing features (from tag pattern):**")
        for feat in features["distinguishing"]:
            lines.append(f"  - {feat}")
    else:
        lines.append("- **Distinguishing features:** none extractable from tag alone")
    lines.append(f"- **Reversibility:** {features['re_pull']}")
    return lines


def render_position(position: dict, features: dict) -> list[str]:
    lines = []
    routing = position.get("routing") or bench_workspaces_routing_to(features["tag"], load_portal())
    if routing:
        lines.append(f"- **Bench workspaces routing here:** {', '.join(f'`{r}`' for r in routing)}")
    else:
        lines.append("- **Bench workspaces routing here:** none (bench-orphaned)")
    lines.append(
        f"- **Same-arch (`{features.get('arch', 'unknown')}`) production workspaces:** {len(position['same_arch_production'])}"
    )
    for m in position["same_arch_production"][:4]:
        lines.append(f"  - `{m['model_hint']}` (via `{m['workspace']}`)")
    lines.append(f"- **Same-arch bench workspaces:** {len(position['same_arch_bench'])}")
    for m in position["same_arch_bench"][:4]:
        lines.append(f"  - `{m['model_hint']}` (via `{m['workspace']}`)")
    if position["net_new"]:
        lines.append("- **Net-new signals (fleet has no other with these):**")
        for n in position["net_new"]:
            lines.append(f"  - {n}")
    else:
        lines.append(
            "- **Net-new signals:** none — arch/vendor/capabilities all present elsewhere in fleet"
        )
    if position["coverage_gap_if_removed"]:
        lines.append(
            f"- ⚠ **Removal ends all fleet exploration of `{features.get('arch', 'unknown')}`**"
        )
    return lines


def render_diversity(diversity: dict, features: dict) -> list[str]:
    lines = []
    my_arch = features.get("arch", "unknown")
    my_source = features.get("source_org", "unknown")
    if diversity["removes_arch_from_fleet_entirely"]:
        lines.append(f"- ⚠ **ARCH LOSS**: `{my_arch}` disappears from fleet entirely if removed")
    else:
        lines.append(
            f"- **Other `{my_arch}` workspaces in fleet:** {diversity['total_arch_count_in_fleet_ex_this']}"
        )
    if diversity["removes_source_from_fleet_entirely"]:
        lines.append(f"- ⚠ **VENDOR LOSS**: `{my_source}` exits the fleet")
    else:
        lines.append(
            f"- **Other workspaces from `{my_source}`:** {diversity['total_source_count_in_fleet_ex_this']}"
        )
    return lines


def render_numeric(numeric: dict) -> list[str]:
    lines = []
    lines.append(
        f"- **Evidence rows mined:** {numeric['n_valid_rows']} valid (post-boundary), {numeric['n_invalid_rows']} invalid (pre-boundary)"
    )
    if numeric["avg_tps"] is not None:
        floor = " (**BELOW** 20 t/s floor)" if numeric["avg_tps"] < 20 else " (above floor)"
        lines.append(f"- **Avg TPS (post-boundary only):** {numeric['avg_tps']}{floor}")
    elif numeric["avg_tps_invalid"] is not None:
        lines.append(
            f"- **Avg TPS (pre-boundary — INVALID for decisions):** {numeric['avg_tps_invalid']} — captured under prior stack"
        )
    if numeric["avg_quality"] is not None:
        lines.append(f"- **Avg quality_score (post-boundary):** {numeric['avg_quality']}")
    if numeric["newest_valid_date"]:
        lines.append(f"- **Newest post-boundary evidence:** {numeric['newest_valid_date']}")
    elif numeric["newest_date"]:
        stale = " ⚠ **all pre-boundary**"
        lines.append(
            f"- **Newest evidence:** {numeric['newest_date']} ({numeric['newest_age_days']}d){stale}"
        )
    if numeric["closeout_signals"]:
        lines.append(
            f"- **Post-boundary closeout signals (authoritative):** {', '.join(numeric['closeout_signals'])}"
        )
        for src in numeric["closeout_sources"]:
            lines.append(f"  - `{src}`")
    if numeric["closeout_signals_invalid"]:
        lines.append(
            f"- **Pre-boundary closeout signals (NOT authoritative — re-affirm on current stack):** {', '.join(numeric['closeout_signals_invalid'])}"
        )
        for src in numeric["closeout_sources_invalid"]:
            lines.append(f"  - `{src}`")
    # TASK_BENCH_VALIDITY_V1: harness/category coherence
    if numeric.get("valid_harnesses"):
        lines.append(
            f"- **Harness(es) that produced valid rows:** {', '.join(numeric['valid_harnesses'])}"
        )
    if numeric.get("wrong_instrument_harnesses"):
        lines.append(
            f"- ⚠ **Wrong-instrument evidence (kept as data point, does NOT count as valid):** "
            f"{', '.join(numeric['wrong_instrument_harnesses'])} — this category needs "
            f"{', '.join(numeric.get('appropriate_harnesses') or [])}"
        )
    if not numeric["has_valid_evidence"]:
        reason = numeric.get("rebench_reason") or "no post-boundary evidence"
        lines.append(
            f"- ⚠ **Not decision-grade — {reason}. Capability-appropriate re-bench required.**"
        )
    return lines


def render_card_vs_slotting(
    card: dict, claims: dict, slots: list[dict], alignment: dict
) -> list[str]:
    lines = []
    if not card["available"]:
        status_desc = {
            "not-fetched": "run `python3 scripts/fetch_pending_model_cards.py` first (Part B2)",
            "skipped-local-build": "local portal5/* build — no external card",
            "gated-or-forbidden": "card is gated or the repo is private",
            "not-found": "card fetch returned 404 — repo may have been renamed or removed",
        }.get(card.get("status"), card.get("status", "unavailable"))
        lines.append(f"- **Card status:** {status_desc}")
        # still show slotting so operator sees at least one side
        if slots:
            lines.append(
                f"- **What portal.yaml says we slotted it for** ({len(slots)} bench workspace(s)):"
            )
            for s in slots[:3]:
                desc = s["description"][:400] + ("…" if len(s["description"]) > 400 else "")
                lines.append(f"  - `{s['workspace']}` ({s['name']})")
                if desc:
                    lines.append(f"    > {desc}")
        return lines

    # Card side
    lines.append(f"- **Card source:** `{card['url']}` (fetched {card.get('fetched_at', '?')[:10]})")
    if claims.get("description"):
        lines.append("- **Card description (first paragraph):**")
        lines.append(f"  > {claims['description']}")

    if claims.get("capabilities"):
        lines.append("- **Card-advertised strengths:**")
        for heading, section in list(claims["capabilities"].items())[:4]:
            preview = section.replace("\n", " ").strip()
            if len(preview) > 350:
                preview = preview[:350] + "…"
            lines.append(f"  - **{heading}:** {preview}")

    if claims.get("anti_capabilities"):
        lines.append("- **Card says model is NOT for:**")
        for heading, section in list(claims["anti_capabilities"].items())[:2]:
            preview = section.replace("\n", " ").strip()
            if len(preview) > 250:
                preview = preview[:250] + "…"
            lines.append(f"  - **{heading}:** {preview}")

    if claims.get("deployment_notes"):
        lines.append(f"- **Deployment signals extracted:** {', '.join(claims['deployment_notes'])}")

    # Slotting side
    if slots:
        lines.append(
            f"- **What portal.yaml says we slotted it for** ({len(slots)} bench workspace(s)):"
        )
        for s in slots[:3]:
            desc = s["description"][:400] + ("…" if len(s["description"]) > 400 else "")
            tools_note = (
                f" | tools: {len(s['tools'])} configured" if s["tools"] else " | tools: none"
            )
            reasoning_note = " | emits_reasoning" if s["emits_reasoning"] else ""
            lines.append(f"  - `{s['workspace']}`{tools_note}{reasoning_note}")
            if desc:
                lines.append(f"    > {desc}")
    else:
        lines.append("- **Slotting:** bench-orphaned — nothing routes to this tag")

    # Alignment side
    if alignment.get("mismatches"):
        lines.append("- ⚠ **Card vs slotting MISMATCHES** (probe before deciding):")
        for m in alignment["mismatches"]:
            lines.append(f"  - {m}")
    if alignment.get("matches"):
        lines.append("- **Card vs slotting alignment ✓:**")
        for m in alignment["matches"]:
            lines.append(f"  - {m}")
    if alignment.get("untested"):
        lines.append(
            "- **Card-advertised capabilities with no keyword overlap in slot config** (may be untested):"
        )
        for u in alignment["untested"]:
            lines.append(f"  - {u}")
    if (
        not alignment.get("mismatches")
        and not alignment.get("matches")
        and not alignment.get("untested")
        and alignment.get("available")
    ):
        lines.append(
            "- **Alignment:** no distinctive claim/slot mismatch detected — slot config appears consistent with card"
        )

    return lines


def render_analysis_row(row: dict) -> str:
    tag = row["tag"]
    size = row["size_gb"]
    hyp_verdict, hyp_reason, _ = row["hypothesis"]
    out = []
    out.append(f"## `{tag}` — {size:.1f} GB")
    out.append("")
    out.append("### At a glance")
    out.append("")
    out.append(f"- **Hypothesis (non-authoritative):** `{hyp_verdict}` — {hyp_reason}")
    out.append("- **What we'd lose if removed:**")
    for loss in row["losses"]:
        out.append(f"  - {loss}")
    out.append(f"- **What we'd gain:** {size:.1f} GB disk")
    out.append("")
    out.append("### Intake rationale")
    out.append("")
    out.extend(render_intake(row["rationale"]))
    out.append("")
    out.append("### Capability profile")
    out.append("")
    out.extend(render_capability(row["features"]))
    out.append("")
    out.append("### Fleet position")
    out.append("")
    out.extend(render_position(row["position"], row["features"]))
    out.append("")
    out.append("### Diversity impact")
    out.append("")
    out.extend(render_diversity(row["diversity"], row["features"]))
    out.append("")
    out.append("### Card claims vs our slotting")
    out.append("")
    out.extend(
        render_card_vs_slotting(row["card"], row["card_claims"], row["slots"], row["alignment"])
    )
    out.append("")
    out.append("### Prescribed re-bench (capability-appropriate)")
    out.append("")
    out.extend(render_prescription(row["prescription"]))
    out.append("")
    out.append("")
    out.append("### Numeric evidence")
    out.append("")
    out.extend(render_numeric(row["numeric"]))
    out.append("")
    return "\n".join(out) + "\n"


def render_header(rows: list[dict], stack_boundary_days: int) -> str:
    n = len(rows)
    total_gb = sum(r["size_gb"] for r in rows)
    hyp_hist = Counter(r["hypothesis"][0] for r in rows)
    coverage_gaps = sum(1 for r in rows if r["position"]["coverage_gap_if_removed"])
    net_new = sum(1 for r in rows if r["position"]["net_new"])
    arch_family_loss = sum(1 for r in rows if r["diversity"]["removes_arch_from_fleet_entirely"])
    unique_capabilities = sum(
        1
        for r in rows
        if any(
            k in feat
            for feat in r["features"].get("distinguishing", [])
            for k in ("MoE", "MTP", "Vision", "Long-context", "Abliterated", "Agent-tuned")
        )
    )
    card_available = sum(1 for r in rows if r["card"]["available"])
    mismatch_count = sum(1 for r in rows if r["alignment"].get("mismatches"))
    card_missing = sum(1 for r in rows if r["card"]["status"] == "not-fetched")
    no_valid_evidence = sum(1 for r in rows if not r["numeric"]["has_valid_evidence"])
    only_pre_boundary = sum(
        1 for r in rows if r["numeric"]["n_invalid_rows"] > 0 and r["numeric"]["n_valid_rows"] == 0
    )
    boundary_date = (_dt.date.today() - _dt.timedelta(days=stack_boundary_days)).isoformat()

    lines = [
        f"# Pending model verdicts — informed-decision analysis ({_dt.datetime.now(_dt.UTC).strftime('%Y-%m-%d %H:%M')} UTC)",
        "",
        f"{n} pending entries, {total_gb:.1f} GB total.",
        "",
        "## ⚠ Stack boundary in effect",
        "",
        f"**Boundary date: {boundary_date}** (`--stack-boundary-days={stack_boundary_days}`).",
        "",
        "The Ollama + oMLX inference stack has changed materially. Evidence",
        "captured before the boundary was measured under a prior stack and",
        "**does not reflect current behavior**. TPS/quality averages here",
        "are post-boundary-only. Numeric-driven decline verdicts require",
        "≥1 post-boundary row — otherwise the hypothesis defaults to",
        "`investigate-refresh` (re-bench required).",
        "",
        f"- models with NO post-boundary evidence: **{no_valid_evidence} / {n}**"
        + (
            f" (of which {only_pre_boundary} have only pre-boundary rows)"
            if only_pre_boundary
            else ""
        ),
        "",
        "**Closeout reports from before the boundary are surfaced but are",
        "NOT treated as authoritative** — the human decided on numbers",
        "that no longer hold. Re-affirm any pre-boundary closeout signal",
        "against a fresh bench before treating it as current guidance.",
        "",
        "## Purpose",
        "",
        "Every pending model was pulled with intent. The evidence miner",
        "(`pending_verdicts_evidence.py`) gave the numbers; this report gives",
        "the *context*: why the model was pulled, what it does, where it sits",
        "in the fleet, what the model card advertises vs how we actually",
        "slotted it, what disappears on removal, and whether the fleet's",
        "arch/vendor diversity survives.",
        "",
        "The hypothesis at the top of each entry is a mechanical score across",
        "the axes below. It is **not authoritative**. Read the sections; write",
        "the verdict as a paragraph across the axes.",
        "",
        "## KEEP signals across the backlog (attend to these before declining)",
        "",
        f"- models where removal ends the fleet's only exploration of that arch: **{coverage_gaps}**",
        f"- models with a net-new signal (arch/vendor/capability not in fleet): **{net_new}**",
        f"- models whose removal drops their arch family from the fleet entirely: **{arch_family_loss}**",
        f"- models with a distinctive capability (MoE / MTP / vision / abliteration / etc.): **{unique_capabilities}**",
        f"- models where the card advertises capabilities we HAVEN'T tested (probe first): **{mismatch_count}**",
        "",
        "## Model card cache coverage",
        "",
        f"- Cards available for analysis: **{card_available} / {n}**",
    ]
    if card_missing:
        lines.append(
            f"- ⚠ **{card_missing} card(s) not yet fetched** — run `python3 scripts/fetch_pending_model_cards.py` (Part B2) then re-run this analyzer for the full alignment picture"
        )

    # Bench prescription distribution — grouping the fleet re-bench work
    rx_categories = Counter(
        r["prescription"]["category_id"] for r in rows if r["prescription"]["needs_rebench"]
    )
    slot_blocked = sum(1 for r in rows if r["prescription"]["blocked_by_slot"])
    total_rx_needed = sum(1 for r in rows if r["prescription"]["needs_rebench"])

    lines.extend(
        [
            "",
            "## Re-bench work required (grouped by capability)",
            "",
            f"Total models needing re-bench (no post-boundary evidence): **{total_rx_needed} / {n}**",
            f"Of those, models blocked by workspace slot issues (must fix config before benching): **{slot_blocked}**",
            "",
            "**Category distribution** — group re-bench work by shared harness/prompt-corpus:",
            "",
        ]
    )
    for cat_id, count in sorted(rx_categories.items(), key=lambda x: -x[1]):
        # Find the label
        label = next((c["label"] for c in CAPABILITY_CATEGORIES if c["id"] == cat_id), cat_id)
        gb = sum(
            r["size_gb"]
            for r in rows
            if r["prescription"]["category_id"] == cat_id and r["prescription"]["needs_rebench"]
        )
        lines.append(f"- `{cat_id}` ({label}): **{count} models, {gb:.1f} GB**")
    if slot_blocked:
        lines.extend(
            [
                "",
                "⚠ **Slot-fix priority list** — models where the workspace config prevents valid benching regardless of prompt corpus:",
                "",
            ]
        )
        for r in rows:
            if r["prescription"]["blocked_by_slot"]:
                fixes = r["prescription"]["slot_fixes_required"]
                lines.append(f"- `{r['tag']}` — {len(fixes)} fix(es): {fixes[0][:120]}")
    lines.extend(
        [
            "",
            "## Hypothesis histogram (not authoritative)",
            "",
        ]
    )
    for verdict, count in sorted(hyp_hist.items(), key=lambda x: -x[1]):
        gb = sum(r["size_gb"] for r in rows if r["hypothesis"][0] == verdict)
        lines.append(f"- `{verdict}`: {count} models, {gb:.1f} GB")
    lines.append("")
    lines.append("## How to record a verdict")
    lines.append("")
    lines.append("Open `config/PENDING_MODEL_VERDICTS.md`. For each entry, either")
    lines.append("leave `- [ ]` or check `- [x]` and add a verdict paragraph that")
    lines.append("reasons across the axes. Example:")
    lines.append("")
    lines.append("```")
    lines.append("- [x] `qwen3.6:27b-q8_0` — 27.9 GB")
    lines.append("  - verdict: decline (bench-orphaned, no active role; Q8 doesn't earn 2x")
    lines.append("    memory over Q4_K_M peer; no coverage gap — Q4_K_M and Q6_K remain;")
    lines.append("    no diversity loss — Qwen3.6 family still 3-strong; TPS 12.3 below 20 floor)")
    lines.append("```")
    lines.append("")
    lines.append("The executor writes that reason **verbatim** into the DROPPED catalog")
    lines.append("stub, so the reasoning is documented permanently in the wiki spine —")
    lines.append("not just in this report file, which lives in `reports/` (gitignored).")
    lines.append("")
    lines.append("Sorted biggest-reclaim-first below.")
    lines.append("")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Informed-decision analysis for pending verdicts.")
    ap.add_argument(
        "--stack-boundary-days",
        type=int,
        default=STACK_BOUNDARY_DAYS,
        help=f"Evidence older than N days is INVALID (stack changed). Default {STACK_BOUNDARY_DAYS}.",
    )
    args = ap.parse_args(argv)
    boundary_days = args.stack_boundary_days

    entries = parse_ledger()
    print(f"Parsed {len(entries)} ledger entries")
    print(
        f"Stack boundary: {boundary_days} days ({(_dt.date.today() - _dt.timedelta(days=boundary_days)).isoformat()})"
    )
    portal = load_portal()

    rows: list[dict] = []
    for e in entries:
        tag = e["tag"]
        features = parse_tag_features(tag)
        rationale = mine_intake_rationale(tag)
        position = fleet_position_analysis(tag, features, portal)
        position["routing"] = bench_workspaces_routing_to(tag, portal)
        diversity = fleet_diversity_analysis(tag, features, portal, position)
        numeric = collect_numeric_evidence(
            tag, e["evidence"], position["routing"], stack_boundary_days=boundary_days
        )
        card = load_card_cache(tag)
        card_claims = (
            extract_card_claims(card["body"])
            if card["available"]
            else {
                "description": None,
                "capabilities": {},
                "anti_capabilities": {},
                "deployment_notes": [],
            }
        )
        slots = workspace_slotting_for_tag(tag, portal)
        alignment = alignment_analysis(card_claims, slots)
        losses = what_wed_lose(features, position, diversity)
        prescription = bench_prescription(features, card_claims, alignment, slots, numeric)
        # TASK_BENCH_VALIDITY_V1: now that the capability category is known,
        # gate the evidence on harness/category coherence. Wrong-instrument
        # post-boundary rows are kept as data points but no longer satisfy
        # has_valid_evidence — so a bench_tps-only reasoning model correctly
        # still needs its capability-appropriate re-bench. Re-derive the
        # prescription's needs_rebench off the gated evidence.
        numeric = apply_coherence_gate(numeric, prescription["category_id"])
        prescription["needs_rebench"] = not numeric["has_valid_evidence"]
        hyp = hypothesis(features, rationale, position, diversity, numeric, alignment)
        rows.append(
            {
                "tag": tag,
                "size_gb": e["size_gb"],
                "features": features,
                "rationale": rationale,
                "position": position,
                "diversity": diversity,
                "numeric": numeric,
                "card": card,
                "card_claims": card_claims,
                "slots": slots,
                "alignment": alignment,
                "prescription": prescription,
                "losses": losses,
                "hypothesis": hyp,
            }
        )

    rows.sort(key=lambda r: -r["size_gb"])
    text = render_header(rows, boundary_days) + "\n".join(render_analysis_row(r) for r in rows)
    stamp = _dt.datetime.now(_dt.UTC).strftime("%Y%m%dT%H%M%SZ")
    out_path = REPO_ROOT / "reports" / f"PENDING_VERDICTS_ANALYSIS_{stamp}.md"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(text)
    print(f"Wrote {out_path.relative_to(REPO_ROOT)} ({len(rows)} rows, {len(text)} bytes)")

    hyp_hist = Counter(r["hypothesis"][0] for r in rows)
    print("\nHypothesis histogram (NOT authoritative — operator decides):")
    for v, n in sorted(hyp_hist.items(), key=lambda x: -x[1]):
        gb = sum(r["size_gb"] for r in rows if r["hypothesis"][0] == v)
        print(f"  {v}: {n} models, {gb:.1f} GB")

    coverage_gaps = sum(1 for r in rows if r["position"]["coverage_gap_if_removed"])
    net_new = sum(1 for r in rows if r["position"]["net_new"])
    arch_family_loss = sum(1 for r in rows if r["diversity"]["removes_arch_from_fleet_entirely"])
    card_available = sum(1 for r in rows if r["card"]["available"])
    card_not_fetched = sum(1 for r in rows if r["card"]["status"] == "not-fetched")
    mismatch_count = sum(1 for r in rows if r["alignment"].get("mismatches"))
    no_valid_evidence = sum(1 for r in rows if not r["numeric"]["has_valid_evidence"])
    print("\nKEEP signals:")
    print(f"  coverage gap (only exploration of arch): {coverage_gaps}")
    print(f"  net-new signals (arch/vendor/capability not in fleet): {net_new}")
    print(f"  arch family loss (removes arch from fleet entirely): {arch_family_loss}")
    print(f"  card/slot mismatches (advertised capability not tested): {mismatch_count}")
    print(f"\nCard cache: {card_available}/{len(rows)} available; {card_not_fetched} not fetched")
    if card_not_fetched:
        print("  → run `python3 scripts/fetch_pending_model_cards.py` (Part B2) to populate")
    print("\nEvidence validity:")
    print(f"  models with NO post-boundary evidence: {no_valid_evidence}/{len(rows)}")

    # Prescription grouping
    rx_dist = Counter(
        r["prescription"]["category_id"] for r in rows if r["prescription"]["needs_rebench"]
    )
    slot_blocked = sum(1 for r in rows if r["prescription"]["blocked_by_slot"])
    print("\nRe-bench prescriptions (for models needing refresh):")
    for cat_id, count in sorted(rx_dist.items(), key=lambda x: -x[1]):
        print(f"  {cat_id}: {count} models")
    if slot_blocked:
        print(
            f"  ⚠ {slot_blocked} model(s) blocked by workspace slot fixes — see report for details"
        )
    if no_valid_evidence >= len(rows) * 0.7 and len(rows) >= 10:
        print(f"\n  ⚠ {no_valid_evidence}/{len(rows)} pending models lack post-boundary evidence.")
        print("  ⚠ Re-bench work groups by category above; slot fixes precede prompt work.")
        print("  ⚠ File a fleet re-bench task BEFORE the operator decision gate.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
