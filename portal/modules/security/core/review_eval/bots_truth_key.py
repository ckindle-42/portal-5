"""review_eval.bots_truth_key -- the rebuilt, cited BOTS answer key (D-T11-ANSWER-KEY).

Scorer plane only. Each entry names its entities and sourcetypes with a citation to a public
BOTS write-up, and its entities are matched together in one event (AND), not each on its own.
Admission is decided by ``scripts/review_truth_audit.py``, never here: this module only loads
the transcription and refuses an entry that cites nothing. ``bully.bots_answer_key`` stays as the
control and is not edited.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from portal.modules.security.core.bully.corpus_bed import AnswerKeyEntry

KEY_PATH = Path(__file__).with_name("bots_truth_key.json")


@dataclass(frozen=True)
class CitedEntry:
    dataset: str
    technique: str
    entities: tuple[str, ...]
    sourcetypes: tuple[str, ...]
    citations: tuple[str, ...]
    note: str = ""

    def answer_key_entry(self) -> AnswerKeyEntry:
        return AnswerKeyEntry(
            dataset=self.dataset,
            technique=self.technique,
            behavioural_spine=(),
            entities=self.entities,
            sourcetypes=self.sourcetypes,
        )


def load(path: Path = KEY_PATH) -> tuple[CitedEntry, ...]:
    rows = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(rows, list):
        raise ValueError(f"{path} must hold a JSON list of entries")
    entries = []
    for number, row in enumerate(rows, 1):
        entry = CitedEntry(
            dataset=str(row["dataset"]),
            technique=str(row["technique"]),
            entities=tuple(str(x) for x in row["entities"]),
            sourcetypes=tuple(str(x) for x in row["sourcetypes"]),
            citations=tuple(str(x) for x in row["citations"]),
            note=str(row.get("note", "")),
        )
        if not (entry.entities and entry.sourcetypes and entry.citations):
            raise ValueError(f"{path} entry {number} needs entities, sourcetypes and citations")
        entries.append(entry)
    return tuple(entries)
