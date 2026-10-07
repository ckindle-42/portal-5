"""Probe: behaviour -> ATT&CK technique (consumer ``attack_mapping``).

Corpus = exactly what the MITRE MCP serves: the Enterprise subset from the
local SPL library (``siem/spl_detections.yaml``) plus ATT&CK for ICS
(``siem/mitre_ics_techniques.json``). Today there is no behaviour search: the
MCP looks up by technique ID, and ``spl_search_library`` is a substring match
over SPL descriptions — that substring logic, applied to the same corpus, is
the incumbent baseline. Fixtures: (1) key-independent ICS self-retrieval (query
= technique NAME, document = description without the name); (2) analyst-style
behaviour descriptions in ``tests/data/embedding_consumers/attack_behaviors.json``
(authored in Phase 3) when present.
"""

from __future__ import annotations

import json
from typing import Any

import yaml

from portal.platform.embedding.contract import Role, Task

from ..framework import (
    MEASURED,
    REPO_ROOT,
    ProbeContext,
    ProbeResult,
    compare,
    fixture_digest,
    probe,
    recall_at_k,
    top_k_by_cosine,
)

SIEM = REPO_ROOT / "portal" / "modules" / "security" / "core" / "siem"
BEHAVIORS = REPO_ROOT / "tests" / "data" / "embedding_consumers" / "attack_behaviors.json"


def corpus() -> dict[str, str]:
    out: dict[str, str] = {}
    spl = yaml.safe_load((SIEM / "spl_detections.yaml").read_text()) or {}
    for tid, entry in spl.items():
        if isinstance(entry, dict) and entry.get("description"):
            out[str(tid)] = str(entry["description"])
    ics = json.loads((SIEM / "mitre_ics_techniques.json").read_text())
    for tid, meta in ics.items():
        if meta.get("description"):
            out[str(tid)] = str(meta["description"])
    return out


def substring_rank(query: str, docs: dict[str, str], k: int = 10) -> list[str]:
    """spl_search_library's logic (id-or-substring), generalised to the corpus."""
    q = query.strip()
    return [tid for tid, d in docs.items() if q.upper() in tid.upper() or q.lower() in d.lower()][
        :k
    ]


@probe("attack_mapping")
async def run(ctx: ProbeContext) -> ProbeResult:
    docs_text = corpus()
    dim = int(ctx.opt("attack_dim", 768))
    ids = list(docs_text)
    vecs = await ctx.client.embed_texts(
        [docs_text[i] for i in ids], task=Task.SEARCH, role=Role.DOCUMENT, dim=dim
    )
    docs = dict(zip(ids, vecs, strict=True))
    ics = json.loads((SIEM / "mitre_ics_techniques.json").read_text())
    names = [(tid, str(m["name"])) for tid, m in ics.items() if m.get("name") and tid in docs]
    results: dict[str, Any] = {}

    async def score(queries: list[str], gold: list[list[str]]) -> dict[str, Any]:
        inc = [substring_rank(q, docs_text) for q in queries]
        qv = await ctx.client.embed_texts(queries, task=Task.SEARCH, role=Role.QUERY, dim=dim)
        cand = [top_k_by_cosine(v, docs, 10) for v in qv]
        return {
            "incumbent": {
                "recall@1": round(recall_at_k(inc, gold, 1), 4),
                "recall@5": round(recall_at_k(inc, gold, 5), 4),
            },
            "candidate": {
                "recall@1": round(recall_at_k(cand, gold, 1), 4),
                "recall@5": round(recall_at_k(cand, gold, 5), 4),
            },
        }

    results["ics_name_self_retrieval"] = await score([n for _, n in names], [[t] for t, _ in names])
    notes = []
    if BEHAVIORS.is_file():
        beh = json.loads(BEHAVIORS.read_text())
        results["behaviors"] = await score(
            [b["behavior"] for b in beh], [b["technique_ids"] for b in beh]
        )
    else:
        notes.append(f"{BEHAVIORS.relative_to(REPO_ROOT)} absent — behaviour fixture not measured")
    block = results.get("behaviors", results["ics_name_self_retrieval"])
    return ProbeResult(
        consumer="attack_mapping",
        status=MEASURED,
        incumbent={
            "primary": block["incumbent"]["recall@5"],
            **{k: v["incumbent"] for k, v in results.items()},
        },
        candidate={
            "primary": block["candidate"]["recall@5"],
            **{k: v["candidate"] for k, v in results.items()},
        },
        hint=compare(block["incumbent"]["recall@5"], block["candidate"]["recall@5"]),
        fixture={"techniques": len(ids), "corpus_sha": fixture_digest(docs_text)},
        identity=await ctx.client.version_tag(dim),
        notes=notes,
    )
