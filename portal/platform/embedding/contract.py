"""EmbeddingGemma 2 contract: task prefixes, Matryoshka dims, vector math, identity.

The prefix strings are transcribed verbatim from the google/embeddinggemma-2
model card ("Task Instruction Prefixes" table). They live here and nowhere
else: the service formats with these functions, the client passes ``task`` and
``role`` instead of pre-formatted strings, and the OpenAI-compatible endpoint is
raw passthrough for callers (Open WebUI) that apply their own configured
prefixes. One implementation, so a query and a document can never be formatted
by two different hands.

Prefixes apply to TEXT only. Images, video and audio are embedded without a
prefix (model card, "Prefixes apply to text only").

Pure stdlib (see package docstring).
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

NATIVE_DIM = 768
#: Matryoshka truncation dimensions the model was trained for. Anything else is
#: a contract violation, not a tuning knob.
MRL_DIMS: tuple[int, ...] = (768, 512, 256, 128)


class Task(StrEnum):
    """Model-card task names (the text that follows ``task:``)."""

    SEARCH = "search result"
    QUESTION_ANSWERING = "question answering"
    FACT_CHECKING = "fact checking"
    CODE_RETRIEVAL = "code retrieval"
    CLASSIFICATION = "classification"
    CLUSTERING = "clustering"
    SENTENCE_SIMILARITY = "sentence similarity"


class Role(StrEnum):
    QUERY = "query"
    DOCUMENT = "document"


#: Asymmetric tasks: queries and corpus items take different prefixes.
ASYMMETRIC_TASKS: frozenset[Task] = frozenset(
    {Task.SEARCH, Task.QUESTION_ANSWERING, Task.FACT_CHECKING, Task.CODE_RETRIEVAL}
)


def parse_task(value: str | Task) -> Task:
    if isinstance(value, Task):
        return value
    v = value.strip().lower().replace("_", " ")
    for t in Task:
        if v in (t.value, t.name.lower().replace("_", " ")):
            return t
    raise ValueError(f"unknown embedding task {value!r}; expected one of {[t.value for t in Task]}")


def parse_role(value: str | Role) -> Role:
    if isinstance(value, Role):
        return value
    v = value.strip().lower()
    for r in Role:
        if v == r.value:
            return r
    raise ValueError(f"unknown embedding role {value!r}; expected 'query' or 'document'")


def format_text(text: str, task: Task, role: Role, title: str | None = None) -> str:
    """Return ``text`` wrapped in the model-card prefix for ``task``/``role``.

    Asymmetric tasks: queries -> ``task: <task> | query: <text>``; documents ->
    ``title: <title or none> | text: <text>``. Symmetric tasks (classification,
    clustering, sentence similarity) apply the same task prefix to every input,
    so ``role`` is ignored for them.
    """
    if task in ASYMMETRIC_TASKS and role is Role.DOCUMENT:
        t = (title or "").strip() or "none"
        return f"title: {t} | text: {text}"
    return f"task: {task.value} | query: {text}"


def l2_normalize(vec: Sequence[float]) -> list[float]:
    norm = math.sqrt(sum(x * x for x in vec))
    if norm == 0.0 or math.isnan(norm):
        raise ValueError("cannot normalize a zero or NaN vector")
    return [x / norm for x in vec]


def truncate(vec: Sequence[float], dim: int) -> list[float]:
    """Matryoshka truncation: keep the leading ``dim`` values, then RE-NORMALIZE.

    Slicing a unit vector does not preserve unit length; skipping the
    re-normalization silently degrades cosine ranking (model card, "Re-normalize
    after truncating").
    """
    if dim not in MRL_DIMS:
        raise ValueError(f"dim {dim} is not a trained Matryoshka dimension {MRL_DIMS}")
    if len(vec) < dim:
        raise ValueError(f"vector has {len(vec)} dims, cannot truncate to {dim}")
    return l2_normalize(vec[:dim])


def dot(a: Sequence[float], b: Sequence[float]) -> float:
    if len(a) != len(b):
        raise ValueError(f"dimension mismatch {len(a)} != {len(b)}")
    return sum(x * y for x, y in zip(a, b, strict=True))


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot(a, b) / (na * nb)


def has_nan(vec: Sequence[float]) -> bool:
    return any(math.isnan(x) or math.isinf(x) for x in vec)


@dataclass(frozen=True)
class Identity:
    """What the live service is actually serving. Every stored vector is stamped
    with ``version_tag(dim)`` so a different model, revision or dimension can
    never silently share a table (the :8917 two-identity defect this task
    retires)."""

    model: str
    revision: str
    native_dim: int
    dtype: str
    device: str
    backend: str
    modalities: tuple[str, ...]

    def version_tag(self, dim: int = NATIVE_DIM) -> str:
        rev = (self.revision or "unknown")[:12]
        return f"{self.model}@{rev}:{dim}d"

    @classmethod
    def from_dict(cls, d: dict[str, object]) -> Identity:
        mods = d.get("modalities") or ()
        return cls(
            model=str(d.get("model", "")),
            revision=str(d.get("revision", "")),
            native_dim=int(str(d.get("native_dim", NATIVE_DIM))),
            dtype=str(d.get("dtype", "")),
            device=str(d.get("device", "")),
            backend=str(d.get("backend", "")),
            modalities=tuple(str(m) for m in mods) if isinstance(mods, list | tuple) else (),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "model": self.model,
            "revision": self.revision,
            "native_dim": self.native_dim,
            "dtype": self.dtype,
            "device": self.device,
            "backend": self.backend,
            "modalities": list(self.modalities),
        }
