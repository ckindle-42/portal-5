"""The Pipeline image must ship every prompt file a persona references.

2026-10-22: `Dockerfile.pipeline` COPYed `portal/platform/` but not
`portal/modules/eval/persona_matrix/prompts/`, so the one bench persona using
`prompt_template:` failed to load in the container (`[Errno 2] No such file or
directory: .../prompts/qwen36_pair.txt`, then `1 personas skipped`). The
shipped set is derived from the Dockerfile's COPY instructions and
`.dockerignore` — never hardcoded — so a later COPY or ignore pattern is
picked up without touching this test.
"""

from __future__ import annotations

import fnmatch
import json
from pathlib import Path

import yaml

from portal.platform.inference.config import _PROMPT_TEMPLATES_DIR

_ROOT = Path(__file__).resolve().parents[2]
_DOCKERFILE = _ROOT / "Dockerfile.pipeline"


def _instructions(text: str) -> list[str]:
    """Fold backslash-continued lines into single instruction strings."""
    folded: list[str] = []
    pending = ""
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        pending = f"{pending} {line}".strip()
        if pending.endswith("\\"):
            pending = pending[:-1].rstrip()
            continue
        folded.append(pending)
        pending = ""
    if pending:
        folded.append(pending)
    return folded


def _copy_sources() -> list[str]:
    """Build-context source operands of every COPY, shell or JSON form."""
    sources: list[str] = []
    for insn in _instructions(_DOCKERFILE.read_text()):
        if not insn.startswith("COPY "):
            continue
        if any(tok.startswith("--from") for tok in insn.split()):
            continue  # cross-stage copy: reads another stage, not the context
        payload = insn[len("COPY ") :].strip()
        tokens = json.loads(payload) if payload.startswith("[") else payload.split()
        sources.extend(tok for tok in tokens[:-1] if not tok.startswith("--"))
    return sources


def _ignore_patterns() -> list[str]:
    ignore = _ROOT / ".dockerignore"
    if not ignore.is_file():
        return []
    return [
        line.strip()
        for line in ignore.read_text().splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]


def _covers(path: str, source: str) -> bool:
    """True when COPY operand `source` puts repo path `path` into the image."""
    source = source[2:] if source.startswith("./") else source
    if any(ch in source for ch in "*?["):
        return fnmatch.fnmatchcase(path, source)
    base = source.rstrip("/")
    if path == base:
        return True
    return path.startswith(f"{base}/") and (source.endswith("/") or (_ROOT / source).is_dir())


def _ignored(path: str, patterns: list[str]) -> bool:
    """Docker's last-match-wins ignore semantics, applied to a file path."""
    ignored = False
    for pattern in patterns:
        negate = pattern.startswith("!")
        body = pattern[1:] if negate else pattern
        body = body[2:] if body.startswith("./") else body
        body = body.strip("/")
        if not body:
            continue
        parts = path.split("/")
        if any(fnmatch.fnmatchcase("/".join(parts[:i]), body) for i in range(1, len(parts) + 1)):
            ignored = not negate
    return ignored


def _prompt_template_personas() -> list[tuple[str, str]]:
    """``(persona filename, prompt_template)`` for personas that use one."""
    personas_dir = _ROOT / "config" / "personas"
    files = sorted(personas_dir.glob("*.yaml")) + sorted((personas_dir / "bench").glob("*.yaml"))
    found: list[tuple[str, str]] = []
    for yf in files:
        spec = yaml.safe_load(yf.read_text()) or {}
        if spec.get("prompt_template"):
            found.append((yf.name, str(spec["prompt_template"])))
    return found


def test_prompt_template_files_are_shipped_by_the_pipeline_image() -> None:
    """Every referenced prompt body is inside what Dockerfile.pipeline COPYs."""
    personas = _prompt_template_personas()
    assert personas, "no prompt_template persona found — this packaging guard covers nothing"
    sources = _copy_sources()
    assert sources, f"no COPY sources parsed from {_DOCKERFILE.name}"
    patterns = _ignore_patterns()
    unshipped: list[str] = []
    for filename, template in personas:
        rel = (_PROMPT_TEMPLATES_DIR / f"{template}.txt").relative_to(_ROOT).as_posix()
        if not any(_covers(rel, source) for source in sources) or _ignored(rel, patterns):
            unshipped.append(f"{filename} -> {rel}")
    assert not unshipped, (
        "persona prompt file(s) missing from the Pipeline image — add a COPY line "
        f"to Dockerfile.pipeline: {unshipped}"
    )
