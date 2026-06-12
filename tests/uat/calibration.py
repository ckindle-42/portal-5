"""Portal 5 UAT — calibration corpus + quality-signal emission.

Extracted verbatim from tests/portal5_uat_driver.py (TASK_UAT_MODULARIZE_V1
phase C).
"""

from __future__ import annotations

import time
from pathlib import Path


def _emit_corpus_row(
    corpus_run_id: str,
    test: dict,
    routed_model: str,
    response_text: str,
    chat_url: str,
    status: str,
    assertions_result: list,
    elapsed: float,
) -> None:
    """Append one JSONL row to the UAT response corpus.

    The corpus is always-on (no flag required) and one file per UAT run.
    Emission is incremental — each call opens the file in append mode,
    writes one line, and closes, so a crashed run leaves valid JSONL.

    See TASK_UAT_CORPUS_CAPTURE_V1.md for schema + rationale.
    """
    import json as _json

    corpus_dir = Path("tests/uat_corpus")
    corpus_dir.mkdir(parents=True, exist_ok=True)
    corpus_path = corpus_dir / f"uat_{corpus_run_id}.jsonl"

    # Convert tuple assertion results to JSON-safe lists. The in-memory
    # format is tuples of (label:str, passed:bool, detail:str); JSON has
    # no tuple type, so we serialize as lists.
    safe_assertions = [list(a) if isinstance(a, tuple) else a for a in (assertions_result or [])]

    row = {
        "schema_version": 1,
        "corpus_run_id": corpus_run_id,
        "test_id": test.get("id", ""),
        "test_name": test.get("name", ""),
        "section": test.get("section", ""),
        "workspace": test.get("model_slug", ""),
        "expected_models": test.get("expected_models", {}),
        "routed_model": routed_model or "",
        "prompt": test.get("prompt", ""),
        "response_text": response_text or "",
        "chat_url": chat_url or "",
        "status": status,
        "assertions_result": safe_assertions,
        "elapsed_seconds": float(elapsed) if elapsed is not None else 0.0,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    try:
        with corpus_path.open("a", encoding="utf-8") as f:
            f.write(_json.dumps(row, ensure_ascii=False) + "\n")
    except Exception as exc:
        # Corpus emission is best-effort — never fail a test because the
        # corpus write failed. Log and continue.
        print(f"  [corpus] WARN: failed to write {test.get('id', '?')}: {exc}", flush=True)


def _emit_signals_from_calibration(json_path: str, output_path: str = "updated_signals.py") -> None:
    """Read calibration JSON, extract keywords from 'good' responses, write a signals suggestion file."""
    import json as _json
    import math as _math
    import re as _re

    records = _json.loads(Path(json_path).read_text())
    good = [r for r in records if r.get("review_tag") == "good"]

    if not good:
        print(f"No 'good'-tagged records found in {json_path}.")
        print(
            "Open the JSON, set review_tag to 'good' / 'bad' / 'skip' for each entry, then re-run."
        )
        return

    # Group by section
    by_section: dict[str, list[str]] = {}
    for rec in good:
        sec = rec.get("section") or "general"
        by_section.setdefault(sec, []).append(rec.get("response_text", ""))

    def _tokenize(text: str) -> list[str]:
        return _re.findall(r"\b[a-zA-Z][a-zA-Z0-9_]{2,}\b", text.lower())

    _STOPWORDS = {
        "the",
        "and",
        "for",
        "this",
        "that",
        "with",
        "from",
        "are",
        "can",
        "will",
        "not",
        "you",
        "your",
        "have",
        "has",
        "was",
        "but",
        "all",
        "more",
        "into",
        "use",
        "used",
        "using",
        "would",
        "should",
        "could",
        "when",
        "which",
        "here",
        "there",
        "also",
        "each",
        "such",
        "then",
        "they",
        "them",
        "their",
        "been",
        "its",
        "any",
        "how",
        "what",
        "where",
        "who",
        "why",
        "may",
        "one",
        "two",
        "three",
        "just",
        "like",
        "make",
        "made",
        "note",
        "see",
        "get",
        "set",
    }

    # IDF: inverse of how many sections a word appears in
    idf: dict[str, int] = {}
    for texts in by_section.values():
        words_in_sec = set(_tokenize(" ".join(texts)))
        for w in words_in_sec:
            idf[w] = idf.get(w, 0) + 1
    n_sections = len(by_section)
    idf_score = {w: _math.log((n_sections + 1) / (cnt + 1)) for w, cnt in idf.items()}

    section_keywords: dict[str, list[str]] = {}
    for sec, texts in by_section.items():
        words = _tokenize(" ".join(texts))
        tf: dict[str, int] = {}
        for w in words:
            if w not in _STOPWORDS and len(w) > 3:
                tf[w] = tf.get(w, 0) + 1
        total = sum(tf.values()) or 1
        scored = {w: (cnt / total) * idf_score.get(w, 0.0) for w, cnt in tf.items()}
        section_keywords[sec] = sorted(scored, key=lambda x: -scored[x])[:10]

    out_lines = [
        '"""Auto-generated quality signals from calibration data.',
        "",
        "Generated by: python3 tests/portal5_uat_driver.py --emit-signals-from <json>",
        "",
        "Review and integrate into tests/quality_signals.py or the UAT test catalog.",
        '"""',
        "",
        "CALIBRATION_SIGNALS: dict[str, list[str]] = {",
    ]
    for sec in sorted(section_keywords):
        kws = section_keywords[sec]
        out_lines.append(f"    {sec!r}: {kws!r},")
    out_lines.append("}")
    out_lines.append("")
    out_lines.append("# Suggested assert_contains additions for TEST_CATALOG entries:")
    for sec in sorted(section_keywords):
        kws = section_keywords[sec][:5]
        out_lines.append(
            f"# section={sec!r}: "
            + '{"type": "any_of", "label": "Quality signal", "keywords": '
            + repr(kws)
            + "}"
        )

    Path(output_path).write_text("\n".join(out_lines) + "\n")
    print(f"Signals written to {output_path}")
    for sec, kws in sorted(section_keywords.items()):
        print(f"  {sec}: {kws}")
