#!/usr/bin/env python3
"""P4 — measure the substrate (store joins, material, coverage, search) against the answer key.

For every key entry and its governing requirement refs, four surfaces are
measured with the module's OWN functions (never a second SQL path):

(a) **edges**      — ``requirement_scope.population(repo, ref)``: the operator
                     sections and notes joined to the Part, at every link
                     status (status recorded, never flattened);
(b) **material**   — ``reading_material.render(repo, ref, citation="quote")``:
                     the operator sections the conversation is actually handed;
(c) **coverage**   — ``compliance_coverage(standard, requirement)``: the
                     recorded links the coverage tool reports (deterministic);
(d) **search**     — ``compliance_search(question)`` as the persona instructs
                     it: once with no jurisdiction filter, then once per side
                     (conversational entries only).

Metrics per entry and aggregate:
* ``key_operator_recall`` per surface — |key operator evidence ∩ surface| / |key|;
* ``edges_not_in_key`` for (a) and (c) — substrate sections the key never cites;
* ``coverage_verdict_agrees`` — for each per-Part coverage fact, whether the
  key's cited operator section is among the coverage tool's linked sections.

Predeclared (task P4.3): material recall below 0.95 on any dev entry confirms
S2 and triggers P6.2.

Everything written goes through ``scripts.compliance.truth._local`` (local
only). No model inference: store + deterministic tools.
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import pathlib
import re
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))

from scripts.compliance.truth._local import PRIVATE  # noqa: E402

DEFAULT_KEY = PRIVATE / "reading_truth" / "answer_key.yaml"
DEFAULT_OUT = PRIVATE / "reading_truth" / "p4"


def _clean_ref(ref: str) -> str:
    """Strip the key's parenthetical annotations ('... (breadth example)')."""
    return re.sub(r"\s*\([^)]*\)\s*$", "", ref.strip()).strip()


def _ref_parts(ref: str) -> tuple[str, str]:
    """'CIP-007-6 R2 Part 2.2' -> ('CIP-007-6', 'R2'); unparseable -> (cleaned, '')."""
    cleaned = _clean_ref(ref)
    m = re.match(r"^(CIP-\d+(?:-\d+(?:\.[0-9a-z]+)*)?)\s+R(\d+)(?:\s+Part\s+(.*))?$", cleaned)
    if not m:
        return cleaned, ""
    return m.group(1), f"R{m.group(2)}"


def _population_surface(repo, requirement_scope, render, ref):
    """(edges ids with statuses, material ids) for one regulatory ref."""
    edges: dict[str, str] = {}
    material: set[str] = set()
    pop = requirement_scope.population(repo, ref)
    for sid, e in (pop.get("sections") or {}).items():
        if e.get("side") == "regulatory":
            continue
        edges[sid] = str(e.get("link_status") or "")
    rendered = render(repo, ref, citation="quote")
    by_sid = getattr(rendered.get("contract"), "by_section_id", None) or {}
    for sid, token in by_sid.items():
        if getattr(token, "side", "") != "regulatory":
            material.add(str(sid))
    return edges, material


def _coverage_surface(compliance_coverage, std: str, req: str) -> set[str]:
    cov = compliance_coverage(standard=std, requirement=req)
    ids: set[str] = set()
    for block in cov.get("requirements") or []:
        if block.get("requirement") == f"{std} {req}":
            ids |= {str(x.get("section_id")) for x in block.get("linked_sections") or []}
    return ids


def _search_surface(compliance_search, question: str) -> tuple[set[str], list[dict]]:
    surface: set[str] = set()
    runs: list[dict] = []
    for label, kwargs in (
        ("no-filter", {}),
        ("operator", {"jurisdiction": "internal"}),
        ("regulatory", {"jurisdiction": "US"}),
    ):
        try:
            res = compliance_search(question, top_k=10, **kwargs)
        except Exception as exc:  # noqa: BLE001 - search failures are recorded, not fatal
            runs.append({"label": label, "error": str(exc)[:120]})
            continue
        hits = res.get("sections") or res.get("results") or []
        ids = [str(h.get("section_id")) for h in hits]
        surface.update(ids)
        runs.append({"label": label, "n": len(ids), "ids": ids})
    return surface, runs


def _measure_entry(entry, repo, requirement_scope, render, compliance_coverage, compliance_search):
    """All four surfaces for one key entry, plus its coverage-verdict checks."""
    qid = entry["question_id"]
    key_ops = {str(i["section_id"]) for i in entry.get("operator_evidence") or []}
    refs = sorted({_clean_ref(str(g["ref"])) for g in entry.get("governing") or [] if g.get("ref")})
    requirements: dict[str, set[str]] = {}
    for ref in refs:
        std, req = _ref_parts(ref)
        if req:
            requirements.setdefault(std, set()).add(req)

    edges: dict[str, str] = {}
    material: set[str] = set()
    coverage: set[str] = set()
    errors: list[dict] = []
    for ref in refs:
        try:
            e_ids, m_ids = _population_surface(repo, requirement_scope, render, ref)
        except Exception as exc:  # noqa: BLE001 - a bad ref must not kill the run
            errors.append({"question_id": qid, "ref": ref, "error": f"population/render: {exc}"})
            continue
        edges.update(e_ids)
        material.update(m_ids)
    for std, reqs in requirements.items():
        for req in sorted(reqs):
            try:
                coverage |= _coverage_surface(compliance_coverage, std, req)
            except Exception as exc:  # noqa: BLE001
                errors.append(
                    {"question_id": qid, "ref": f"{std} {req}", "error": f"coverage: {exc}"}
                )

    search_surface, search_runs = _search_surface(
        compliance_search, str(entry.get("question") or "")
    )
    surfaces = {"edges": set(edges), "material": material, "coverage": coverage}
    row: dict = {
        "question_id": qid,
        "suite": entry.get("suite"),
        "split": entry.get("split"),
        "refs": refs,
        "key_operator_sections": sorted(key_ops),
        "recall": {},
        "search_runs": search_runs,
    }
    for surface, ids in surfaces.items():
        hit = key_ops & ids
        recall = (len(hit) / len(key_ops)) if key_ops else None
        row["recall"][surface] = None if recall is None else round(recall, 4)
        row[f"{surface}_n"] = len(ids)
        row[f"{surface}_missing"] = sorted(key_ops - ids)
        if surface in ("edges", "coverage"):
            row[f"{surface}_not_in_key"] = sorted(ids - key_ops)
    if entry.get("suite") == "conversational":
        hit = key_ops & search_surface
        row["recall"]["search"] = round(len(hit) / len(key_ops), 4) if key_ops else None
        row["search_n"] = len(search_surface)
        row["search_missing"] = sorted(key_ops - search_surface)
    row["edge_statuses"] = dict(sorted(edges.items()))
    return errors, row, _verdict_checks(entry, requirements, linked_by_req := coverage, key_ops)


def _verdict_checks(entry, requirements, coverage_ids: set[str], key_ops: set[str]) -> list[dict]:
    """Per-Part coverage facts vs the coverage tool's recorded links."""
    checks: list[dict] = []
    for fact in entry.get("facts") or []:
        part = fact.get("part")
        if not part or "coverage" not in fact:
            continue
        cited = [str(x) for x in fact.get("evidence") or [] if str(x).startswith("isection")]
        if cited:
            if fact["coverage"] == "covered":
                agrees = all(c in coverage_ids for c in cited)
            else:
                agrees = not any(c in coverage_ids for c in cited)
        else:
            agrees = (fact["coverage"] == "not_covered") == (len(coverage_ids) == 0)
        checks.append(
            {
                "question_id": entry["question_id"],
                "part": part,
                "key_coverage": fact["coverage"],
                "tool_linked_n": len(coverage_ids),
                "cited_in_linked": sorted(set(cited) & coverage_ids),
                "agrees": agrees,
            }
        )
    return checks


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--key", type=pathlib.Path, default=DEFAULT_KEY)
    parser.add_argument("--out-dir", type=pathlib.Path, default=DEFAULT_OUT)
    args = parser.parse_args(argv)

    out_dir = args.out_dir.resolve()
    repo_root = pathlib.Path(__file__).resolve().parents[3]
    if out_dir.is_relative_to(repo_root) and not out_dir.is_relative_to(PRIVATE.resolve()):
        raise SystemExit(f"REFUSED: outputs are local-only, not {out_dir}")

    import yaml

    from portal.modules.compliance.core import requirement_scope
    from portal.modules.compliance.core.reading_material import render
    from portal.modules.compliance.core.repository import Repository
    from portal.modules.compliance.tools.compliance_mcp import (
        compliance_coverage,
        compliance_search,
    )

    key = yaml.safe_load(args.key.read_text(encoding="utf-8"))
    repo = Repository()
    db_sha = hashlib.sha256(pathlib.Path(repo.path).read_bytes()).hexdigest()
    generated = datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    results: list[dict] = []
    not_in_key: dict[str, set[str]] = {"edges": set(), "coverage": set()}
    verdict_checks: list[dict] = []
    for entry in key.get("entries") or []:
        errors, row, checks = _measure_entry(
            entry, repo, requirement_scope, render, compliance_coverage, compliance_search
        )
        results.extend(errors)
        results.append(row)
        for surface in ("edges", "coverage"):
            not_in_key[surface] |= set(row.get(f"{surface}_not_in_key") or [])
        verdict_checks.extend(checks)

    def _agg(surface: str) -> dict:
        recalls = [
            r["recall"][surface] for r in results if r.get("recall", {}).get(surface) is not None
        ]
        if not recalls:
            return {"n": 0}
        return {
            "n": len(recalls),
            "mean": round(sum(recalls) / len(recalls), 4),
            "min": min(recalls),
            "n_below_0_95": sum(1 for r in recalls if r < 0.95),
        }

    aggregate = {
        "generated_utc": generated,
        "key_sha256": hashlib.sha256(args.key.read_bytes()).hexdigest(),
        "key_status": key.get("status"),
        "live_db_sha256": db_sha,
        "recall": {s: _agg(s) for s in ("edges", "material", "coverage", "search")},
        "edges_not_in_key": {s: sorted(ids) for s, ids in not_in_key.items()},
        "coverage_verdict": {
            "n": len(verdict_checks),
            "agrees": sum(1 for v in verdict_checks if v["agrees"]),
            "disagreements": [v for v in verdict_checks if not v["agrees"]],
        },
        "s2_triggered": any(
            r.get("recall", {}).get("material") is not None and r["recall"]["material"] < 0.95
            for r in results
            if r.get("split") == "dev"
        ),
    }

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "substrate_vs_key.json").write_text(
        json.dumps({"aggregate": aggregate, "entries": results}, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    lines = [
        "# P4 — substrate vs key",
        "",
        f"generated {generated} · key {aggregate['key_sha256'][:12]} · live db {db_sha[:12]}",
        "",
        "| surface | n | mean recall | min | entries < 0.95 |",
        "| --- | --- | --- | --- | --- |",
    ]
    for surface in ("edges", "material", "coverage", "search"):
        a = aggregate["recall"][surface]
        if a.get("n"):
            lines.append(
                f"| {surface} | {a['n']} | {a['mean']} | {a['min']} | {a['n_below_0_95']} |"
            )
    lines += [
        "",
        f"S2 triggered (material recall < 0.95 on any dev entry): **{aggregate['s2_triggered']}**",
        "",
        f"edges_not_in_key: {len(aggregate['edges_not_in_key']['edges'])} (edges), "
        f"{len(aggregate['edges_not_in_key']['coverage'])} (coverage)",
        f"coverage verdict checks: {aggregate['coverage_verdict']['agrees']}/{aggregate['coverage_verdict']['n']} agree",
    ]
    (out_dir / "substrate_vs_key.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
