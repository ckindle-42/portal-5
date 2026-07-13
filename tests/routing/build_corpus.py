#!/usr/bin/env python3
"""Assemble the routing-integrity corpus (BUILD_PROGRAM_ROUTING_INTEGRITY_V1.md Phase R0).

Sources (per the build program):
1. config/routing_examples.json — all 44 entries, present on both sides of
   the collapse (byte-identical at 45edb25 and HEAD — verified).
2. tests/benchmarks/bench/prompts.py — per-discipline TPS prompts.
3. The corpus already assembled by scripts/routing_regression.py (s06/s21
   representative prompts + the 12 hand-authored variant/role discriminators).
4. Fold-coverage additions — one unambiguous prompt per pre-collapse
   discipline that mapped to a workspace later folded or deleted, authored
   from the pre-collapse routing_descriptions.json (45edb25) so each prompt
   reflects what that lane was actually *for*.

Writes tests/routing/corpus.json: a flat list of
{id, message, source, expected_workspace?} records.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))


def build() -> list[dict]:
    corpus: list[dict] = []
    seen_ids: set[str] = set()

    def add(entry: dict) -> None:
        if entry["id"] in seen_ids:
            raise ValueError(f"duplicate corpus id: {entry['id']}")
        seen_ids.add(entry["id"])
        corpus.append(entry)

    # 1. routing_examples.json — all 44, both stale and canonical labels kept
    # as-authored (the staleness of some labels is itself part of what R2
    # measures — see docs/ROUTING_INTEGRITY_FINDINGS.md finding #2).
    examples_path = REPO_ROOT / "config" / "routing_examples.json"
    data = json.loads(examples_path.read_text())
    for i, ex in enumerate(data.get("examples", [])):
        add(
            {
                "id": f"routing_examples[{i}]",
                "message": ex["message"],
                "source": "config/routing_examples.json",
                "expected_workspace": ex.get("workspace"),
            }
        )

    # 2. bench prompts.py
    from tests.benchmarks.bench.prompts import PROMPTS

    for category, text in PROMPTS.items():
        add(
            {
                "id": f"bench_prompts[{category}]",
                "message": text,
                "source": "tests/benchmarks/bench/prompts.py",
            }
        )

    # 3. Reuse scripts/routing_regression.py's existing corpus (s06/s21
    # representative prompts + variant discriminators) verbatim.
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    from routing_regression import _build_corpus as _rr_build_corpus

    for item in _rr_build_corpus():
        # routing_examples[i] entries are already included above (same
        # source file) — skip to avoid duplicate ids.
        if item["id"].startswith("routing_examples["):
            continue
        entry = {
            "id": f"rr_{item['id']}",
            "message": item["message"],
            "source": "scripts/routing_regression.py",
        }
        if "expected_workspace" in item:
            entry["expected_workspace"] = item["expected_workspace"]
        if "expected_variant_hint" in item:
            entry["expected_variant_hint"] = item["expected_variant_hint"]
        add(entry)

    # 4. Fold-coverage — one prompt per pre-collapse discipline that mapped
    # to a now-folded/deleted workspace. Authored from 45edb25's
    # routing_descriptions.json so each is unambiguous for that lane's
    # actual intent (DESIGN_COLLAPSE_V1.md §D4/§D5 folds).
    fold_coverage = [
        # Keyword-layer folds (auto-security variants)
        (
            "fold_blueteam",
            "How do you respond to a ransomware incident — SOC triage, "
            "EDR/XDR containment, and SIEM log analysis for the intrusion?",
            "auto-blueteam",
        ),
        (
            "fold_purpleteam",
            "Generate a red-team attack chain and the matching blue-team "
            "detection rules and IR playbook for lateral movement via SMB.",
            "auto-purpleteam",
        ),
        (
            "fold_purpleteam_deep",
            "Run a four-hop purple team simulation: full ATT&CK-mapped "
            "attack chain, detection analysis, and synthesis of Sigma rules.",
            "auto-purpleteam-deep",
        ),
        (
            "fold_purpleteam_exec",
            "Execute a live purple-team chain: run real bash/Python "
            "commands against the authorized lab target, then produce "
            "detection engineering artifacts and an IR playbook.",
            "auto-purpleteam-exec",
        ),
        (
            "fold_pentest",
            "Authorized pentest: enumerate kerberoastable service accounts "
            "on the domain controller and execute the extraction commands.",
            "auto-pentest",
        ),
        (
            "fold_redteam_deep",
            "Full kill-chain walkthrough with AD pivoting and EDR evasion "
            "techniques mapped to ATT&CK, deep red-team simulation.",
            "auto-redteam-deep",
        ),
        (
            "fold_security_uncensored",
            "Uncensored security analysis with no safety filtering — "
            "authorized research, skip the content-policy preamble.",
            "auto-security-uncensored",
        ),
        (
            "fold_coding_agentic_laguna",
            "Fix this bug, refactor and add feature, then run tests and "
            "update the code — agentic coding with devstral.",
            "auto-coding-agentic",
        ),
        (
            "fold_agentic_heavy",
            "Autonomous agentic multi-file long-horizon codebase refactor, "
            "full codebase, repository-wide, heavy coder big model.",
            "auto-agentic",
        ),
        (
            "fold_coding_northmini",
            "Quick single-file code generation task, small and fast model.",
            "auto-coding-northmini",
        ),
        (
            "fold_coding_uncensored",
            "Write code with no content restrictions, uncensored coding assistant, no refusals.",
            "auto-coding-uncensored",
        ),
        (
            "fold_coding_uncensored_agentic",
            "Agentic multi-file uncensored code generation with no "
            "content restrictions across the whole repository.",
            "auto-coding-uncensored-agentic",
        ),
        # LLM-description-layer folds (model-tied, D5 — intended deletion,
        # included here as a documented blind spot, not a keyword-layer
        # risk: these were never in the pre-collapse keyword scorer).
        (
            "fold_mistral_llm",
            "Use Magistral to reason through this strategic business "
            "decision with explicit thinking-mode traces.",
            "auto-mistral",
        ),
        (
            "fold_phi4_llm",
            "Rigorous multi-step STEM reasoning and chain-of-thought math "
            "proof, Phi-4 model family style analysis.",
            "auto-phi4",
        ),
        # Model-tied, manual-selection-only both before and after (D5) —
        # included as a documented non-risk (no auto-routing path existed
        # pre-collapse either).
        (
            "fold_glm_manual_only",
            "Route this directly to the GLM-4.7-Flash model lane.",
            "auto-glm",
        ),
        (
            "fold_devstral_manual_only",
            "Route this directly to the devstral model lane.",
            "auto-devstral",
        ),
    ]
    for fid, message, expected in fold_coverage:
        add(
            {
                "id": fid,
                "message": message,
                "source": "fold-coverage (R0 step 5, hand-authored)",
                "expected_workspace": expected,
            }
        )

    return corpus


def main() -> None:
    corpus = build()
    out_path = REPO_ROOT / "tests" / "routing" / "corpus.json"
    out_path.write_text(json.dumps(corpus, indent=2, sort_keys=False) + "\n")
    print(f"Wrote {len(corpus)} corpus entries to {out_path}")


if __name__ == "__main__":
    main()
