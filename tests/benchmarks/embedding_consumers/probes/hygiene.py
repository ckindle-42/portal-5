"""Hygiene, companion and measurement probes: config_lint, doc_affinity, generation_dedup,
data_schema_linking, failure_clustering, assertion_coverage, fleet_behavior."""

from __future__ import annotations

import glob
import itertools
import json
import re
import statistics
import subprocess
from collections import Counter, defaultdict
from typing import Any

import yaml

from portal.platform.embedding.contract import Role, Task

from ..framework import (
    MEASURED,
    REPO_ROOT,
    ProbeContext,
    ProbeResult,
    blocked,
    compare,
    fixture_digest,
    probe,
    top_k_by_cosine,
)
from ._common import auc_roc, content_words, cos, load_fixture, threshold_sweep

# ── generation_dedup ────────────────────────────────────────────────────────


@probe("generation_dedup")
async def generation_dedup(ctx: ProbeContext) -> ProbeResult:
    fx = load_fixture("generation_dedup.json")
    base = [p["prompt"] for p in fx["pairs"]]
    para = [p["paraphrase"] for p in fx["pairs"]]
    distinct = fx["distinct"]
    emb = lambda ts: ctx.client.embed_texts(ts, task=Task.SENTENCE_SIMILARITY, dim=768)  # noqa: E731
    vb, vp, vd = await emb(base), await emb(para), await emb(distinct)
    pos = [cos(a, b) for a, b in zip(vb, vp, strict=True)]
    # negatives: every base prompt vs every OTHER base prompt/distinct prompt (a new request is
    # compared against the whole existing history)
    neg = [cos(a, b) for i, a in enumerate(vb) for j, b in enumerate(vb) if i != j]
    neg += [cos(a, b) for a in vb for b in vd]
    neg += [cos(a, b) for a in vp for b in vd]
    t80 = sorted(pos)[int(0.2 * len(pos))]  # catches >= 80% of paraphrases
    fp = sum(n >= t80 for n in neg)
    tp = sum(p >= t80 for p in pos)
    cand = {
        "primary": round(tp / (tp + fp), 4) if tp + fp else 0.0,
        "threshold_catching_80pct": round(t80, 4),
        "paraphrase_recall": round(tp / len(pos), 4),
        "false_flags": fp,
        "negative_pairs": len(neg),
        "sweep_fp0": threshold_sweep(pos, neg, fp_budget=0.0),
        "auc": auc_roc(pos, neg),
    }
    return ProbeResult(
        "generation_dedup",
        MEASURED,
        {"primary": None, "note": "no pre-generation check exists today"},
        cand,
        "BETTER" if cand["primary"] >= 0.8 else "INCONCLUSIVE",
        fixture={
            "paraphrase_pairs": len(pos),
            "negative_pairs": len(neg),
            "sha": fixture_digest(fx),
        },
        identity=await ctx.client.version_tag(768),
        notes=[
            "precision = TP/(TP+FP) at the threshold that catches >=80% of paraphrases, over all cross-prompt pairs; prompt<->existing-artifact cosine is covered by unified_recall/media_alignment"
        ],
    )


# ── data_schema_linking ─────────────────────────────────────────────────────


@probe("data_schema_linking")
async def data_schema_linking(ctx: ProbeContext) -> ProbeResult:
    fx = load_fixture("data_schema_linking.json")
    cols = fx["columns"]
    ids = list(cols)
    docs = [f"{c}: {v}" for c, v in cols.items()]
    qs = fx["questions"]
    dv = await ctx.client.embed_texts(docs, task=Task.SEARCH, role=Role.DOCUMENT, dim=768)
    qv = await ctx.client.embed_texts(
        [q["question"] for q in qs], task=Task.SEARCH, role=Role.QUERY, dim=768
    )
    d = dict(zip(ids, dv, strict=True))
    cand_hits = sum(
        bool(set(top_k_by_cosine(v, d, 3)) & set(q["gold"])) for v, q in zip(qv, qs, strict=True)
    )

    # lexical reference: shared content words between the question and "table column" tokens
    def lex(q: str) -> list[str]:
        qw = content_words(q)
        sc = {c: len(qw & content_words(c.replace(".", " ").replace("_", " "))) for c in ids}
        return [c for c, _ in sorted(sc.items(), key=lambda kv: -kv[1])[:3]]

    inc_hits = sum(bool(set(lex(q["question"])) & set(q["gold"])) for q in qs)
    inc = {
        "primary": round(inc_hits / len(qs), 4),
        "note": "no linker exists (the model reads schemas); this is a lexical name-overlap reference",
    }
    cand = {
        "primary": round(cand_hits / len(qs), 4),
        "metric": "recall@3 (any gold column in top 3)",
    }
    return ProbeResult(
        "data_schema_linking",
        MEASURED,
        inc,
        cand,
        compare(inc["primary"], cand["primary"]),
        fixture={"columns": len(ids), "questions": len(qs), "sha": fixture_digest(fx)},
        identity=await ctx.client.version_tag(768),
        notes=[
            "the Data MCP ships no sample tables; fixture = five authored tables, questions avoid the column names"
        ],
    )


# ── config_lint ─────────────────────────────────────────────────────────────


def _personas() -> dict[str, str]:
    out = {}
    for f in sorted(glob.glob(str(REPO_ROOT / "config" / "personas" / "*.yaml"))):
        d = yaml.safe_load(open(f)) or {}
        text = str(d.get("system_prompt") or d.get("prompt_template") or "")[:600]
        out[str(d.get("slug") or f)] = f"{d.get('name', '')}: {text}"
    return out


@probe("config_lint")
async def config_lint(ctx: ProbeContext) -> ProbeResult:
    from .router import base, build_labels, load_golden

    desc = {
        k: v
        for k, v in json.loads(
            (REPO_ROOT / "config" / "routing_descriptions.json").read_text()
        ).items()
        if not k.startswith("_") and isinstance(v, str)
    }
    ws_ids = list(desc)
    wv = await ctx.client.embed_texts(
        [desc[k] for k in ws_ids], task=Task.SENTENCE_SIMILARITY, dim=768
    )
    pairs = sorted(
        (
            (cos(wv[i], wv[j]), ws_ids[i], ws_ids[j])
            for i, j in itertools.combinations(range(len(ws_ids)), 2)
        ),
        reverse=True,
    )
    # router confusion (EG2 classifier misroutes on the golden set), base-workspace level
    from portal.platform.embedding.classifier import AnchorClassifier, AnchorSet

    golden = load_golden()
    labels = {k: v for k, v in build_labels({g for _, g, _ in golden}).items() if v}
    clf = await AnchorClassifier.build(
        AnchorSet("lint", Task.CLASSIFICATION, 256, labels, 0, 0, 3), ctx.client
    )
    gv = await ctx.client.embed_texts([m for m, _, _ in golden], task=Task.CLASSIFICATION, dim=256)
    conf: Counter[frozenset[str]] = Counter()
    for v, (_, g, _) in zip(gv, golden, strict=True):
        p = clf.classify(v).label
        if p and p != g:
            conf[frozenset((p, g))] += 1
    sim_by_pair = {frozenset((a, b)): s for s, a, b in pairs}
    base_pairs = {}
    for k, s in sim_by_pair.items():
        a, b = sorted(k)
        key = frozenset((base(a), base(b)))
        if len(key) == 2:
            base_pairs[key] = max(s, base_pairs.get(key, -1))
    top = sorted(base_pairs.items(), key=lambda kv: -kv[1])[:10]
    flagged_hit = sum(1 for k, _ in top if conf.get(k))
    both = [(base_pairs[k], conf.get(k, 0)) for k in base_pairs]
    from statistics import correlation

    rho = (
        correlation([s for s, _ in both], [float(c) for _, c in both])
        if len({c for _, c in both}) > 1
        else 0.0
    )
    per = _personas()
    pids = list(per)
    pv = await ctx.client.embed_texts(
        [per[k] for k in pids], task=Task.SENTENCE_SIMILARITY, dim=768
    )
    ppairs = sorted(
        (
            (cos(pv[i], pv[j]), pids[i], pids[j])
            for i, j in itertools.combinations(range(len(pids)), 2)
        ),
        reverse=True,
    )[:15]
    cand = {
        "primary": round(flagged_hit / 10, 4),
        "metric": "of the 10 most-similar workspace pairs, the share that the router actually confuses on the golden set",
        "top_confusable_workspace_pairs": [[round(s, 3), sorted(k)] for k, s in top],
        "router_confusions_on_those": [[sorted(k), conf.get(k, 0)] for k, _ in top],
        "pearson_similarity_vs_confusions": round(rho, 3),
        "top_confusable_persona_pairs": [[round(s, 3), a, b] for s, a, b in ppairs],
        "workspaces": len(ws_ids),
        "personas": len(pids),
    }
    return ProbeResult(
        "config_lint",
        MEASURED,
        {"primary": None, "note": "no lint exists"},
        cand,
        "INCONCLUSIVE",
        fixture={
            "workspace_descriptions": len(ws_ids),
            "personas": len(pids),
            "golden": len(golden),
        },
        identity=await ctx.client.version_tag(768),
        notes=[
            "tool manifests are not linted: tool descriptions are discovered live from the MCP servers and have no static source (tool-schema similarity is measured in the tool_preselect probe)"
        ],
    )


# ── doc_affinity ────────────────────────────────────────────────────────────

_CLEAN = re.compile(r"[#*`>\[\]_|-]+")


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=REPO_ROOT, capture_output=True, text=True, check=False
    ).stdout


@probe("doc_affinity")
async def doc_affinity(ctx: ProbeContext) -> ProbeResult:
    from portal.platform.wiki.store import load_all

    units = [u for u in load_all() if u.title and u.body]
    by_id = {u.id: u for u in units}
    dv = await ctx.client.embed_texts(
        [f"{u.title}\n{_CLEAN.sub(' ', u.body)[:1500]}" for u in units],
        task=Task.SEARCH,
        role=Role.DOCUMENT,
        dim=768,
    )
    docs = dict(zip([u.id for u in units], dv, strict=True))
    cites: dict[str, set[str]] = defaultdict(set)
    for u in units:
        for s in getattr(u, "sources", []) or []:
            p = s.get("path") if isinstance(s, dict) else getattr(s, "path", None)
            if p:
                cites[p].add(u.id)
    log = _git("log", "-n", "300", "--name-only", "--format=@@%h|%s").split("@@")[1:]
    cases = []
    for block in log:
        head, *files = block.strip().splitlines()
        sha, subj = head.split("|", 1)
        files = [f for f in files if f]
        code = [
            f
            for f in files
            if not f.startswith("portal_wiki/canonical/") and f.endswith((".py", ".sh", ".yaml"))
        ]
        edited = {
            f.rsplit("/", 1)[-1][:-3]
            for f in files
            if f.startswith("portal_wiki/canonical/") and f.endswith(".md")
        }
        edited = {e for e in edited if e in by_id}
        if code and edited:
            bound = set().union(*(cites.get(c, set()) for c in code))
            cases.append(
                {"sha": sha, "subject": subj, "code": code[:12], "gold": edited, "bound": bound}
            )
    unbound_total = hit5 = bound_total = bound_hit = 0
    detail = []
    for c in cases:
        q = c["subject"] + "\n" + "\n".join(c["code"])
        [qv] = await ctx.client.embed_texts([q], task=Task.SEARCH, role=Role.QUERY, dim=768)
        top5 = set(top_k_by_cosine(qv, docs, 5))
        unbound = c["gold"] - c["bound"]
        unbound_total += len(unbound)
        hit5 += len(unbound & top5)
        bound_total += len(c["gold"] & c["bound"])
        bound_hit += len(c["gold"] & c["bound"])  # path binding finds these by construction
        detail.append(
            {"sha": c["sha"], "unbound_gold": len(unbound), "found_in_top5": len(unbound & top5)}
        )
    if not cases:
        return blocked("doc_affinity", "no recent commit changed both code and canonical units")
    ids = list(docs)
    dups = []
    for i in range(len(ids)):
        for j in range(i + 1, len(ids)):
            s = cos(dv[i], dv[j])
            if s >= 0.97:
                dups.append([round(s, 4), ids[i], ids[j]])
    dups.sort(reverse=True)
    inc = {
        "primary": 0.0,
        "note": "cited-path binding cannot name a unit whose sources do not cite the changed path",
        "gold_found_by_binding": bound_total,
        "unbound_gold": unbound_total,
    }
    cand = {
        "primary": round(hit5 / unbound_total, 4) if unbound_total else 0.0,
        "metric": "recall@5 of later-edited units NOT bound by path",
        "commits": len(cases),
        "unbound_gold": unbound_total,
        "near_duplicate_unit_pairs_cos>=0.97": dups[:15],
        "near_duplicate_count": len(dups),
    }
    return ProbeResult(
        "doc_affinity",
        MEASURED,
        inc,
        cand,
        "BETTER" if cand["primary"] >= 0.25 else "INCONCLUSIVE",
        fixture={
            "commits": len(cases),
            "units": len(units),
            "sha": fixture_digest([c["sha"] for c in cases]),
        },
        identity=await ctx.client.version_tag(768),
        notes=[
            "gold = units edited in the same commit as the code change (the only 'later edit' signal git offers without human labelling)"
        ],
    )


# ── failure_clustering ──────────────────────────────────────────────────────

_MODE = (
    (re.compile(r"no PERSONA_PROMPTS entry"), "missing_prompt_fixture"),
    (re.compile(r"ROUTING MISMATCH|no signals in"), "routing_mismatch"),
    (re.compile(r"SHOULD failed: .*structural\.table_columns|table_columns"), "table_structure"),
    (re.compile(r"classification\.exact_token"), "classification_token"),
    (re.compile(r"refuse_to_certify"), "refuse_to_certify"),
    (re.compile(r"anti_fabrication"), "anti_fabrication"),
    (re.compile(r"citation\.format"), "citation_format"),
    (re.compile(r"policy\.modal_verbs"), "modal_verbs"),
    (re.compile(r"HTTP \d+|timeout"), "timeout_http"),
    (re.compile(r"limit=\d+, expected"), "concurrency_limit"),
)
_MASK = re.compile(
    r"(SHOULD|MUST) failed: [\w.,\[\] ]+|ROUTING MISMATCH|no PERSONA_PROMPTS entry|HTTP \d+: timeout|"
    r"limit=\d+, expected \d+|classification\.exact_token|table_columns|refuse_to_certify|anti_fabrication\.\w+|citation\.format|policy\.modal_verbs"
)


def _mode(detail: str, name: str) -> str | None:
    for rx, lab in _MODE:
        if rx.search(detail) or rx.search(name):
            return lab
    return None


def _kmeans_purity(vecs: list[list[float]], labels: list[str], k: int, seed: int = 0) -> float:
    import numpy as np

    x = np.asarray(vecs, dtype=np.float32)
    rng = np.random.default_rng(seed)
    cent = x[rng.choice(len(x), k, replace=False)]
    for _ in range(50):
        assign = np.argmax(x @ cent.T, axis=1)
        new = np.stack(
            [x[assign == c].mean(0) if (assign == c).any() else cent[c] for c in range(k)]
        )
        new /= np.linalg.norm(new, axis=1, keepdims=True) + 1e-9
        if np.allclose(new, cent):
            break
        cent = new
    pur = 0
    for c in range(k):
        ls = [labels[i] for i in range(len(labels)) if assign[i] == c]
        if ls:
            pur += Counter(ls).most_common(1)[0][1]
    return pur / len(labels)


@probe("failure_clustering")
async def failure_clustering(ctx: ProbeContext) -> ProbeResult:
    rows: dict[tuple[str, str], dict[str, Any]] = {}
    for f in glob.glob(str(REPO_ROOT / "tests" / "acceptance_corpus" / "*.jsonl")):
        for ln in open(f):
            r = json.loads(ln)
            if r.get("status") == "FAIL":
                rows.setdefault((r["tid"], r["detail"][:80]), r)
    lab, txt = [], []
    for r in rows.values():
        m = _mode(r["detail"], r["name"])
        if m:
            lab.append(m)
            txt.append(f"{r['name']} :: {_MASK.sub(' ', r['detail'])}"[:500])
    if len(txt) < 40:
        return blocked("failure_clustering", f"only {len(txt)} labelled failures (floor 40)")
    vecs = await ctx.client.embed_texts(txt, task=Task.CLUSTERING, dim=768)
    k = len(set(lab))
    purity = max(_kmeans_purity(vecs, lab, k, s) for s in range(5))
    majority = Counter(lab).most_common(1)[0][1] / len(lab)
    # adaptive UAT frozen-suite diversity
    prompts = []
    for f in glob.glob(str(REPO_ROOT / "tests" / "uat_adaptive" / "frozen" / "*.json")):
        for c in json.load(open(f)):
            if isinstance(c, dict) and c.get("prompt"):
                prompts.append(str(c["prompt"])[:600])
    sv = await ctx.client.embed_texts(prompts, task=Task.CLUSTERING, dim=256)
    import numpy as np

    m = np.asarray(sv, dtype=np.float32)
    sims = m @ m.T
    iu = np.triu_indices(len(m), 1)
    near = int((sims[iu] >= 0.97).sum())
    cand = {
        "primary": round(purity, 4),
        "metric": f"k-means (k={k}) cluster purity over {len(txt)} labelled failures",
        "majority_baseline": round(majority, 4),
        "suite_prompts": len(prompts),
        "suite_mean_pairwise_distance": round(float(1 - sims[iu].mean()), 4),
        "suite_near_duplicate_pairs_cos>=0.97": near,
    }
    return ProbeResult(
        "failure_clustering",
        MEASURED,
        {
            "primary": round(majority, 4),
            "note": "no clustering exists; value is the majority-class baseline",
        },
        cand,
        compare(majority, purity),
        fixture={
            "labelled_failures": len(txt),
            "modes": dict(Counter(lab)),
            "sha": fixture_digest(txt),
        },
        identity=await ctx.client.version_tag(768),
        notes=[
            "labels come from the failing check family in the stored acceptance row; the clustered text has those check names masked, so purity measures whether persona/test-name semantics alone recover the mode (a weak instrument: most failures here are one repeated seat)"
        ],
    )


# ── WFE-row based probes ─────────────────────────────────────────────────────


def _wfe_rows(limit_campaign: str = "wfe_full_20260911") -> list[dict[str, Any]]:
    out = []
    for f in glob.glob(
        str(
            REPO_ROOT
            / "tests"
            / "wfe"
            / "results"
            / "campaigns"
            / limit_campaign
            / "rows"
            / "*.json"
        )
    ):
        try:
            r = json.loads(open(f).read())
        except json.JSONDecodeError:
            continue
        if r.get("final_text_head") and r.get("outcome") in ("PASS", "FAIL"):
            out.append(r)
    return out


@probe("assertion_coverage")
async def assertion_coverage(ctx: ProbeContext) -> ProbeResult:
    rows = _wfe_rows()
    by_task: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        by_task[f"{r['workspace']}|{r['task_id']}"].append(r)
    usable = {
        k: v
        for k, v in by_task.items()
        if sum(x["outcome"] == "PASS" for x in v) >= 3
        and sum(x["outcome"] == "FAIL" for x in v) >= 2
    }
    if not usable:
        return blocked(
            "assertion_coverage",
            "no task has >=3 PASS and >=2 FAIL stored answers in the WFE campaign rows",
        )
    pos_all: list[float] = []
    neg_all: list[float] = []
    for v in usable.values():
        vec = await ctx.client.embed_texts(
            [x["final_text_head"][:1500] for x in v], task=Task.SENTENCE_SIMILARITY, dim=768
        )
        passes = [i for i, x in enumerate(v) if x["outcome"] == "PASS"]
        for i, x in enumerate(v):
            others = [vec[j] for j in passes if j != i]
            cent = [sum(c) / len(others) for c in zip(*others, strict=True)]
            s = cos(vec[i], cent)
            (pos_all if x["outcome"] == "PASS" else neg_all).append(s)
    cand = {
        "primary": auc_roc(pos_all, neg_all),
        "metric": "AUC: similarity-to-PASS-centroid (leave-one-out) separating PASS from FAIL answers",
        "tasks": len(usable),
        "pass_answers": len(pos_all),
        "fail_answers": len(neg_all),
        "mean_sim_pass": round(statistics.mean(pos_all), 4),
        "mean_sim_fail": round(statistics.mean(neg_all), 4),
    }
    return ProbeResult(
        "assertion_coverage",
        MEASURED,
        {
            "primary": 1.0,
            "note": "the stored verdict IS the phrase-assertion/regex grader output, so agreement with it is 1.0 by construction; the question is whether a semantic channel adds signal",
        },
        cand,
        "INCONCLUSIVE",
        fixture={"tasks": len(usable), "rows": len(pos_all) + len(neg_all)},
        identity=await ctx.client.version_tag(768),
        notes=[
            "WFE rows keep only final_text_head (truncated) and regex graders; there are no expected-concept statements to score coverage against, so this measures answer-vs-passing-answers similarity as a proxy"
        ],
    )


@probe("fleet_behavior")
async def fleet_behavior(ctx: ProbeContext) -> ProbeResult:
    rows = _wfe_rows()
    cell: dict[tuple[str, str], dict[str, dict[str, Any]]] = defaultdict(dict)
    for r in rows:
        if r.get("repeat", 1) == 1:
            cell[(r["workspace"], r["task_id"])][r["arm"]] = r
    per_ws: dict[str, list[tuple[float, bool]]] = defaultdict(list)
    cache: dict[str, list[float]] = {}
    items = [(k, v) for k, v in cell.items() if len(v) >= 2]
    texts = sorted({a["final_text_head"][:1200] for _, v in items for a in v.values()})
    vecs = await ctx.client.embed_texts(texts, task=Task.SENTENCE_SIMILARITY, dim=256)
    cache = dict(zip(texts, vecs, strict=True))
    for (ws, _), v in items:
        for a, b in itertools.combinations(v.values(), 2):
            per_ws[ws].append(
                (
                    cos(cache[a["final_text_head"][:1200]], cache[b["final_text_head"][:1200]]),
                    a["outcome"] == b["outcome"],
                )
            )
    if not per_ws:
        return blocked(
            "fleet_behavior", "no (workspace, task) cell has two arms with stored answers"
        )
    table = {
        ws: {
            "arm_pairs": len(v),
            "mean_behavioural_similarity": round(statistics.mean(s for s, _ in v), 4),
            "outcome_agreement": round(sum(o for _, o in v) / len(v), 4),
        }
        for ws, v in sorted(per_ws.items())
    }
    allv = [x for v in per_ws.values() for x in v]
    agree = [s for s, o in allv if o]
    dis = [s for s, o in allv if not o]
    cand = {
        "primary": auc_roc(agree, dis),
        "metric": "AUC: behavioural similarity separating arm-pairs with the same outcome from different outcomes",
        "per_workspace": table,
        "evidence_only": True,
    }
    return ProbeResult(
        "fleet_behavior",
        MEASURED,
        {
            "primary": None,
            "note": "metadata net-new (pending_verdicts_report.py) compares outcomes only",
        },
        cand,
        "INCONCLUSIVE",
        fixture={"cells": len(items), "arm_pairs": len(allv)},
        identity=await ctx.client.version_tag(256),
        notes=[
            "EVIDENCE ONLY for the WFE fitness matrix — never a removal verdict (WFE doctrine: short probes cannot judge fitness)"
        ],
    )
