"""Adaptive UAT — agent first-pass assessment (TASK_UAT_ADAPTIVE_OVERHAUL_V1).

After the OWUI run, the Claude Code agent — independent of the system under test
and highly capable — reads each captured response and proposes a rubric
assessment: a 1-5 score per criterion, a PASS/PARTIAL/FAIL verdict, and a short
rationale. These land in the corpus as ``agent_*`` fields (distinct from
``operator_*``). The review packet pre-fills them so the operator confirms or
overrides rather than scoring 276 challenges from a blank slate.

The agent's assessment never sets the sign-off [GATE] — the operator does. It
makes the operator's review fast and well-grounded, and because the author/judge
is independent of the fleet, it is not a self-graded exam.
"""

from __future__ import annotations

import json
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[3]
CORPUS_DIR = _ROOT / "tests" / "uat_corpus"


def _latest_corpus() -> Path | None:
    if not CORPUS_DIR.exists():
        return None
    files = sorted(CORPUS_DIR.glob("uat_*.jsonl"))
    return files[-1] if files else None


def _load(corpus: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in Path(corpus).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def pending(corpus: Path | None = None) -> list[dict]:
    """Return adaptive rows still needing an agent assessment.

    Each item gives the agent exactly what it needs to judge: the challenge id,
    dimension, the prompt, the full response, and the rubric criteria (with
    guidance). The agent reasons over these and calls ``record`` for each.
    """
    corpus = corpus or _latest_corpus()
    if not corpus:
        return []
    out = []
    for r in _load(corpus):
        if not r.get("adaptive"):
            continue
        if r.get("agent_verdict"):
            continue
        out.append(
            {
                "test_id": r.get("test_id"),
                "space_id": (r.get("rubric") or {}).get("space_id", r.get("workspace")),
                "dimension": r.get("dimension"),
                "prompt": r.get("prompt"),
                "response_text": r.get("response_text"),
                "chat_url": r.get("chat_url"),
                "machine_status": r.get("status"),
                "rubric": r.get("rubric"),
                "auto_scores": r.get("auto_scores", {}),
            }
        )
    return out


def record(
    test_id: str,
    scores: dict,
    verdict: str,
    rationale: str,
    corpus: Path | None = None,
) -> Path:
    """Write the agent's proposed assessment for one challenge into the corpus."""
    corpus = corpus or _latest_corpus()
    if not corpus:
        raise SystemExit("assess: no corpus found")
    rows = _load(corpus)
    hit = False
    for r in rows:
        if r.get("test_id") == test_id and r.get("adaptive"):
            r["agent_scores"] = dict(scores)
            r["agent_verdict"] = verdict
            r["agent_rationale"] = rationale
            hit = True
    if not hit:
        raise KeyError(f"no adaptive corpus row for test_id={test_id}")
    Path(corpus).write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
        encoding="utf-8",
    )
    return corpus


if __name__ == "__main__":  # pragma: no cover
    p = pending()
    print(f"{len(p)} adaptive challenge(s) awaiting agent assessment")
    for item in p[:5]:
        print(f"  - {item['test_id']} [{item['dimension']}] {item['space_id']}")
