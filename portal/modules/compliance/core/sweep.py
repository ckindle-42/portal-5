"""The standard-ordered sweep (PROVE_THEN_SCALE_V1 P3.2/P4).

The map unit is one requirement, a deterministic population, one call, a
receipt — :func:`reader.read` was never wrong as a unit, only as a
conversational path that made the model navigate for what the graph already
knows. Here it gets its correct job: the material is handed over complete
(:mod:`reading_material`), the mapping question is asked, and the reading's
determinations come back as typed, provenance-carrying edges written by
:func:`candidate_links.record_determination`.

**Order is a design choice, recorded as one.** Standards run in dependency
order — CIP-002's categorisation decides which systems are in scope for
everything after it, so a sweep that reads CIP-011 before CIP-002 reads it
without knowing its scope — and within a standard, requirements run in the
standard's own numbering so the shared fixed body stays in the prompt cache's
prefix. The shared body is per standard, which is also why the standard is the
shard key on a cluster: a sweep ordered any other way thrashes the cache every
twenty calls.
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

#: The dependency order over the register's standards, and the reason each
#: placement claims. Foundational first: categorisation (CIP-002) before
#: governance (CIP-003) before people (CIP-004) before perimeters (CIP-005)
#: before the systems inside them (CIP-007), physical (CIP-006) alongside,
#: then the lifecycle standards that build on scope — incidents (CIP-008),
#: recovery (CIP-009), change (CIP-010), information protection (CIP-011),
#: communications (CIP-012), and finally supply chain (CIP-013) and physical
#: attack (CIP-014), which reference the others' definitions and assets.
#: Recorded here because an incidental order is an unrecorded design decision
#: waiting to be depended on by accident.
STANDARD_ORDER: tuple[tuple[str, str], ...] = (
    ("CIP-002", "categorisation — determines which systems are in scope for every later standard"),
    ("CIP-003", "senior management and policy — the governance the rest operates under"),
    ("CIP-004", "personnel and training — who may hold access, before access controls"),
    ("CIP-005", "electronic security perimeters — the boundary systems sit inside"),
    ("CIP-006", "physical security — the physical analogue of the perimeter"),
    ("CIP-007", "systems security — the per-system controls the scope and perimeter gate"),
    ("CIP-008", "incident reporting and response — operates on systems CIP-007 secures"),
    ("CIP-009", "recovery — operates on the same asset base after incidents"),
    ("CIP-010", "change management and vulnerability assessments — modifies CIP-007 systems"),
    ("CIP-011", "information protection — protects data the earlier standards define"),
    ("CIP-012", "communications — protects data flows between defined Control Centers"),
    ("CIP-013", "supply chain — risk management over the assets and vendors above"),
    ("CIP-014", "physical attack — references the perimeter and critical assets defined above"),
)

#: CIP-002 ships two revisions in the register (5.1a and the -5.1a attachment
#: spelling); the sweep reads each register node as its own row, so the order
#: above is by STANDARD PREFIX and register nodes carry their own revision.

#: Where the mapping prompt lives — an artifact like the reading prompt, with
#: a declared version and a content sha recorded on every run.
MAPPING_PROMPT_PATH = (
    Path(__file__).resolve().parents[4] / "config" / "compliance" / "mapping_prompt.md"
)

#: Confidence words the prompt allows, and the numeric band each lands in for
#: stratification (P5.3 stratifies the sample by confidence).
CONFIDENCE_BANDS = {"high": 0.9, "medium": 0.6, "low": 0.3}

_DETERMINATIONS_RE = re.compile(
    r"```json\s*(\{.*?\"determinations\".*?\})\s*```",
    re.S,
)


def load_mapping_prompt(path: Path | None = None) -> tuple[str, str, str]:
    """The mapping prompt body, its declared version, and the sha of its body —
    the same artifact discipline as ``reader.load_prompt``."""
    from portal.modules.compliance.core.reader import load_prompt

    return load_prompt(path or MAPPING_PROMPT_PATH)


def parse_determinations(answer: str) -> tuple[list[dict[str, Any]], str]:
    """The determinations block from an answer, and a parse failure reason.

    Lenient about where the block sits — the model is answering in prose and
    the block comes last — strict about what an entry must carry. Returns
    ``([], reason)`` when no parseable block exists; the reason travels in the
    receipt rather than dying in a log line.
    """
    candidates = _DETERMINATIONS_RE.findall(answer or "")
    if not candidates:
        # a model that dropped the fence but kept the shape
        brace = answer.rfind('{"determinations"')
        if brace >= 0:
            end = answer.find("}]", brace)
            if end >= 0:
                candidates = [answer[brace : end + 2]]
    if not candidates:
        return [], "no determinations block found in the answer"
    try:
        parsed = json.loads(candidates[-1])
    except json.JSONDecodeError as exc:
        return [], f"the determinations block does not parse: {exc}"
    entries = parsed.get("determinations")
    if not isinstance(entries, list):
        return [], '"determinations" is not a list'
    return entries, ""


def map_read(
    repo: Any,
    ref: str,
    *,
    model: str,
    prompt_path: Path | None = None,
    fixed: dict[str, Any] | None = None,
    num_ctx: int = 32768,
    answer_budget: int = 3072,
    timeout: int = 1800,
    keep_alive: str = "30m",
    write: bool = True,
    dialect: Any = None,
) -> dict[str, Any]:
    """One map reading: the population as one message, the mapping prompt as
    the question, one call, a receipt.

    ``write=False`` runs the reading and reports what it would determine
    without touching the store — the smoke path. Determinations are written
    through :func:`candidate_links.record_determination`, which enforces the
    two bounds the task puts on this loop: provenance is mandatory, and a
    pairing the store already holds is corroborated, never re-created.

    ``dialect`` names the wire protocol the call travels on
    (:mod:`transport_dialects`). None means the default resolution —
    ``ollama-native`` unless ``COMPLIANCE_TRANSPORT`` says otherwise — and the
    resolved engine is stamped onto the payload either way.
    """
    from portal.modules.compliance.core import candidate_links, reading_material
    from portal.modules.compliance.core.reading_transport import chat

    prompt_body, prompt_version, prompt_sha = load_mapping_prompt(prompt_path)
    material = reading_material.render(repo, ref, question=prompt_body, fixed=fixed)
    if "error" in material:
        return {"ref": ref, "error": material["error"], "model": model}
    started = time.time()
    # A transient transport failure is a RECORDED cell, never a dead sweep:
    # reader.read learned this the hard way (an HTTP 500 killed a 1,522 s
    # reading and lost the receipt). A failed cell here returns an error row
    # the sweep records, and a re-run of the standard redoes only that ref.
    try:
        result = chat(
            model,
            messages=[{"role": "user", "content": material["text"]}],
            tools=None,
            fmt=None,
            think=False,
            num_ctx=num_ctx,
            answer_budget=answer_budget,
            timeout=timeout,
            keep_alive=keep_alive,
            dialect=dialect,
        )
    except Exception as exc:  # noqa: BLE001 — a failed cell is a recorded cell
        return {
            "ref": ref,
            "error": f"transport failure: {type(exc).__name__}: {exc}",
            "model": model,
            "wall_s": round(time.time() - started, 2),
        }
    wall = round(time.time() - started, 2)
    answer = (result.content or "").strip()
    entries, parse_error = parse_determinations(answer)

    from portal.modules.compliance.core.reader import store_run, verify_citations

    # Determinations are written BEFORE the receipt lands, so the outcomes —
    # including rejections with their reasons — travel in the retained run and
    # a rejection is auditable instead of living only in a lost return value.
    # (The CIP-007-6 cache-sweep receipts predate this order: their written
    # rows are in the store, their rejection reasons are not.)
    answer_id = f"map-{ref}"
    outcomes: list[dict[str, Any]] = []
    if write:
        for entry in entries:
            outcomes.append(
                candidate_links.record_determination(
                    repo,
                    requirement_id=str(entry.get("requirement_id", "")),
                    section_id=str(entry.get("section_id", "")),
                    relation_type=str(entry.get("relation_type", "")).upper(),
                    answer_id=answer_id,
                    sentence=str(entry.get("sentence", "")),
                    confidence=CONFIDENCE_BANDS.get(str(entry.get("confidence", "")).lower(), 0.0),
                    read_ref=ref,
                )
            )

    payload: dict[str, Any] = {
        "question": f"[mapping] {ref} — determinations from the population",
        "ref": ref,
        "answer": answer,
        # Which engine produced this cell. A receipt that cannot say this can be
        # filed under the wrong engine — which is how a splash measurement gets
        # taken on Ollama and written into a promotion decision.
        "dialect": result.get("dialect", "ollama-native"),
        "endpoint": result.get("endpoint", ""),
        "context_source": result.get("context_source", "request_num_ctx"),
        "thinking_chars": len(result.thinking),
        "model": model,
        "prompt_version": prompt_version,
        "prompt_sha": prompt_sha,
        "num_ctx": num_ctx,
        "verification": verify_citations(repo, answer, material["text"]),
        "failed": bool(parse_error) or not answer,
        "failure": parse_error or ("" if answer else "the model produced no answer"),
        "closure_receipt": {
            "population_detail": material.get("population_detail", ""),
            "n_sections": material.get("n_sections", 0),
            "by_side": material.get("by_side", {}),
            "stop_reason": "map reading — one call, no tools",
            # outcomes ride INSIDE the closure receipt because that is what
            # store_run persists — payload-level keys are lost (measured:
            # the family pass's rejection reasons died exactly this way)
            "determinations": {},
        },
        "latency": {
            "elapsed_s": wall,
            "load_duration_s": result.get("load_duration_s"),
            "prompt_eval_duration_s": result.get("prompt_eval_duration_s"),
            "eval_duration_s": result.get("eval_duration_s"),
            "eval_count": result.get("eval_count"),
            "prompt_eval_count": result.get("prompt_eval_count"),
            "prompt_bytes": result.get("prompt_bytes"),
        },
        "determinations": {
            "requested": len(entries),
            "parse_error": parse_error,
            "outcomes": outcomes,
            "determined": sum(1 for o in outcomes if o["action"] == "determined"),
            "corroborated": sum(1 for o in outcomes if o["action"] == "corroborated"),
            "rejected": sum(1 for o in outcomes if o["action"] == "rejected"),
        },
    }
    # A6.3 fix: the outcomes — INCLUDING rejection reasons — now ride inside
    # the closure receipt. The previous line stripped them (kept everything
    # except "outcomes"), so every rejection reason died at write time and the
    # quote-discipline-vs-checker-strictness analysis was impossible from the
    # store: the family pass's rejection reasons died exactly this way once
    # already (see the comment above), and the CIP-003-8/CIP-004-7 re-run
    # reproduced the loss live before this fix.
    payload["closure_receipt"]["determinations"] = {
        **{k: v for k, v in payload["determinations"].items() if k != "outcomes"},
        "outcomes": outcomes,
    }
    payload["run_id"] = store_run(
        repo,
        {**payload, "failed": False},
        {"ref": ref, "revision_id": ""},
        thread=[
            {"role": "user", "content": material["text"]},
            {"role": "assistant", "content": answer},
        ],
    )
    payload["determinations"]["run_id"] = payload["run_id"]
    return payload


def sweep_order(repo: Any) -> list[str]:
    """Every register requirement ref, standards in dependency order, and
    within a standard the standard's own numbering — R2 before R10 (numeric,
    not string order), Parts before nothing: the shared body stays in the
    cache prefix either way, and the numbering order keeps a standard's
    receipt readable against the standard itself."""
    from portal.modules.compliance.core.cip_register import Register

    def _numbering(node_id: str) -> tuple:
        tail = node_id.split(" ", 1)[1] if " " in node_id else ""
        pieces: list[tuple[int, Any]] = []
        for token in re.split(r"[\s.]+", tail):
            pieces.append((0, int(token)) if token.isdigit() else (1, token))
        return pieces

    reg = Register.load()
    by_standard: dict[str, list[str]] = {}
    for node in reg.nodes:
        prefix = node.id.split(" ")[0]
        base = prefix.rsplit("-", 1)[0]
        by_standard.setdefault(base, []).append(node.id)
    ordered: list[str] = []
    for standard, _reason in STANDARD_ORDER:
        for node_id in sorted(by_standard.get(standard, []), key=_numbering):
            ordered.append(node_id)
    # standards the order table does not name yet — never silently dropped
    for base in sorted(by_standard):
        if base not in {s for s, _ in STANDARD_ORDER}:
            ordered.extend(sorted(by_standard[base], key=_numbering))
    return ordered


def refs_for_standard(reg: Any, standard: str) -> list[str]:
    """The register nodes of exactly ONE standard revision, in the standard's
    own numbering. Node ids prefix to their revision (`CIP-003-8 R1 …`), so
    the match is on the full revision id — matching the FAMILY instead swept
    both CIP-003 revisions' 83 nodes under each revision's banner (measured
    live, PROVE_THEN_SCALE_V1 §P7), double-reading 44 requirements under the
    wrong fixed body."""

    def _numbering(node_id: str) -> tuple:
        tail = node_id.split(" ", 1)[1] if " " in node_id else ""
        return [(0, int(t)) if t.isdigit() else (1, t) for t in re.split(r"[\s.]+", tail)]

    return sorted(
        (n.id for n in reg.nodes if n.id.split(" ")[0] == standard),
        key=_numbering,
    )


def sweep_standard(
    repo: Any,
    standard: str,
    *,
    model: str,
    prompt_path: Path | None = None,
    num_ctx: int = 32768,
    write: bool = True,
    refs: list[str] | None = None,
    dialect: Any = None,
) -> dict[str, Any]:
    """Map every requirement of one standard, sequentially, shared body first.

    The cache story of this loop has now been measured THREE times, and the
    latest measurement wins:

    * PROVE_THEN_SCALE_V1 §P4.1 (2026-09-17): this exact shape — twenty
      sequential map readings, shared body first — prefilled at full price
      every call (collapse ×1.0); the mechanism was isolated as "Ollama 0.34.2
      reuses a prefix WITHIN an append-only conversation and NOT across
      independent requests that merely share one".
    * TASK_COMPLIANCE_DELIVER_AND_SETTLE_ENGINE_V1 §B2 (2026-09-19), State B:
      that negative no longer reproduces. The §P4.1 shape re-run through this
      module's own transport fields (gemma4, real fixed body, ``/api/chat``,
      ``think:false``, keep_alive 30m) now reuses 16,708 of 16,730 tokens —
      prefill 0.27 s against 31.82 s full price (×118). The daemon
      environment was rewritten between the two measurements
      (``.env`` mtime Sep 18; ``OLLAMA_NUM_PARALLEL=4``, ``OLLAMA_KV_CACHE_TYPE
      =q8_0``, ``OLLAMA_FLASH_ATTENTION=1`` are the prime suspects — not
      isolated). A genuinely-unshared control still prefills at full price, so
      the reuse is real prefix sharing, not a broken clock.
    * Consequence: the sequential loop's fixed-body-first ordering is not
      "correct by accident" any more — on State B it buys the collapse for
      independent sequential calls. Whether a CONCURRENT fan-out still beats
      it on wall clock, on any engine, is exactly what
      tests/benchmarks/bench_engine_concurrency.py measures; this docstring
      deliberately does not preempt that verdict.
    (``prompt_eval_duration`` remains the honest cache signal on Ollama;
    ``prompt_eval_count`` reads the FULL prompt length on a hit — and
    ``prompt_eval_cached_count`` on the native surface is the corroborating
    counter.) Returns the per-call rows and the summary the family report
    scales from.
    """
    from portal.modules.compliance.core import reading_material
    from portal.modules.compliance.core.cip_register import Register

    if refs is None:
        refs = refs_for_standard(Register.load(), standard)
    fixed = reading_material.fixed_body(repo, standard)
    if "error" in fixed:
        return {"standard": standard, "error": fixed["error"]}
    rows: list[dict[str, Any]] = []
    started = time.time()
    for ref in refs:
        payload = map_read(
            repo,
            ref,
            model=model,
            prompt_path=prompt_path,
            fixed=fixed,
            num_ctx=num_ctx,
            write=write,
            dialect=dialect,
        )
        if "error" in payload:
            rows.append({"ref": ref, "error": payload["error"]})
            continue
        latency = payload.get("latency", {})
        determinations = payload.get("determinations", {})
        rows.append(
            {
                "ref": ref,
                "wall_s": latency.get("elapsed_s"),
                "prompt_tokens": latency.get("prompt_eval_count"),
                "prompt_eval_duration_s": latency.get("prompt_eval_duration_s"),
                "eval_count": latency.get("eval_count"),
                "determined": determinations.get("determined", 0),
                "corroborated": determinations.get("corroborated", 0),
                "rejected": determinations.get("rejected", 0),
                "parse_error": determinations.get("parse_error", ""),
                "run_id": payload.get("run_id", ""),
            }
        )
        print(
            f"  {ref:<28} wall={rows[-1]['wall_s']:>6} s "
            f"prefill={rows[-1]['prompt_eval_duration_s']:>7} s "
            f"determined={rows[-1]['determined']} corroborated={rows[-1]['corroborated']} "
            f"rejected={rows[-1]['rejected']}"
        )
    total_wall = round(time.time() - started, 2)
    durations = [r["prompt_eval_duration_s"] for r in rows if r.get("prompt_eval_duration_s")]
    summary = {
        "standard": standard,
        "n_requirements": len(rows),
        "total_wall_s": total_wall,
        "wall_per_requirement_s": round(total_wall / len(rows), 2) if rows else None,
        "prompt_eval_durations_s": durations,
        "first_call_prefill_s": durations[0] if durations else None,
        "rest_mean_prefill_s": (
            round(sum(durations[1:]) / len(durations[1:]), 3) if len(durations) > 1 else None
        ),
        "cache_collapse_ratio": (
            round(durations[0] / (sum(durations[1:]) / len(durations[1:])), 1)
            if len(durations) > 1 and durations[0]
            else None
        ),
        "determined": sum(r.get("determined", 0) for r in rows),
        "corroborated": sum(r.get("corroborated", 0) for r in rows),
        "rejected": sum(r.get("rejected", 0) for r in rows),
        "rows": rows,
    }
    return summary


def sweep_answers(repo: Any, standard: str) -> list[dict[str, Any]]:
    """The retained map answers of one standard's sweep, in sweep order — the
    reduce's input, read back from the receipts so no caller has to have been
    the process that ran the map."""
    family = standard.rsplit("-", 1)[0] if re.match(r"^CIP-\d{3}-", standard) else standard
    rows = repo._conn.execute(
        "SELECT subject_ref, answer, asked_at FROM reading_runs "
        "WHERE question LIKE ? ORDER BY asked_at",
        (f"[mapping] {family}%",),
    ).fetchall()
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for row in rows:
        ref = str(row["subject_ref"])
        if ref in seen or not str(row["answer"]).strip():
            continue
        seen.add(ref)
        out.append({"ref": ref, "answer": str(row["answer"])})
    return out


def reduce_standard(
    repo: Any,
    standard: str,
    answers: list[dict[str, Any]],
    *,
    model: str,
    num_ctx: int = 32768,
    answer_budget: int = 4096,
) -> dict[str, Any]:
    """The reduce half of map-reduce: one call over the standard's map ANSWERS.

    Reduce runs over the answers — each a receipt-backed reading of one
    requirement — never over the twenty populations, which would re-prefill
    the whole standard to synthesize what the readings already said. The
    question is the standard-level rollup an operator actually wants: which
    requirements the operator's documents cover, where the readings found no
    operator side, and what the new determinations connect. No tools; the
    input is the twenty answers and their refs.
    """
    from portal.modules.compliance.core.reader import store_run
    from portal.modules.compliance.core.reading_transport import chat

    lines = [
        f"# Standard review: {standard}",
        "",
        "Below are the per-requirement reading answers from a sweep over this "
        "standard, in the standard's own order. Each answer is the reading of "
        "one requirement against the operator's documents, as retained.",
        "",
    ]
    for entry in answers:
        lines.append(f"## {entry.get('ref', '')}")
        lines.append(str(entry.get("answer", "")).strip())
        lines.append("")
    lines.append("## The question")
    lines.append("")
    lines.append(
        "Across this standard: which requirements do the operator's documents "
        "cover, which requirements have no operator side or a thin one, what "
        "cross-requirement observations did the readings surface, and what "
        "should the operator look at first? Cite requirement ids for every "
        "claim. Say plainly where the answers disagree or where evidence is thin."
    )
    message = "\n".join(lines)
    started = time.time()
    result = chat(
        model,
        messages=[{"role": "user", "content": message}],
        tools=None,
        fmt=None,
        think=False,
        num_ctx=num_ctx,
        answer_budget=answer_budget,
    )
    wall = round(time.time() - started, 2)
    answer = (result.content or "").strip()
    payload = {
        "question": f"[reduce] {standard} — rollup over the sweep answers",
        "ref": standard,
        "answer": answer,
        "model": model,
        "failed": not answer,
        "failure": "" if answer else "the model produced no answer",
        "closure_receipt": {"n_answers": len(answers), "stop_reason": "reduce — one call"},
        "latency": {
            "elapsed_s": wall,
            "prompt_eval_count": result.get("prompt_eval_count"),
            "prompt_eval_duration_s": result.get("prompt_eval_duration_s"),
            "eval_count": result.get("eval_count"),
        },
    }
    payload["run_id"] = store_run(
        repo,
        {**payload, "failed": False},
        {"ref": standard, "revision_id": ""},
        thread=[
            {"role": "user", "content": message},
            {"role": "assistant", "content": answer},
        ],
    )
    return payload


__all__ = [
    "CONFIDENCE_BANDS",
    "STANDARD_ORDER",
    "load_mapping_prompt",
    "map_read",
    "parse_determinations",
    "reduce_standard",
    "sweep_answers",
    "sweep_order",
    "sweep_standard",
]
