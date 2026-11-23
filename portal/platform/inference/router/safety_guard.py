"""Deterministic pre-model refusal: hard CBRN synthesis requests and injection exfiltration.

Checked before routing so a refused turn never reaches a model — abliterated seats
can ignore system-prompt red lines. Narrow by design: only explicit actionable forms
match; defensive, historical and educational phrasing passes. The system prompts
(Layer A) backstop everything this deliberately does not catch.
"""

from __future__ import annotations

import json
import logging
import re
import time
import uuid
from collections.abc import AsyncIterator
from typing import Any, NamedTuple

from fastapi.responses import JSONResponse, StreamingResponse

from portal.platform.inference.router import no_answer
from portal.platform.inference.router.metrics import _record_safety_refusal
from portal.platform.inference.router.trace import note as trace_note
from portal.platform.inference.router.trace import span as trace_span

logger = logging.getLogger(__name__)

INJECTION_REFUSAL = (
    "I cannot reveal hidden instructions, system prompts, or internal tool configurations."
)
CBRN_REFUSAL = (
    "I can't provide instructions for synthesizing, manufacturing, or weaponizing chemical, "
    "biological, radiological, or nuclear weapons. I can help with defensive detection, "
    "history, policy, or other legitimate angles on the topic."
)

# ── CBRN: agent terms, production intent, and the defensive contexts that pass ──

_AGENTS = (
    r"sarin|vx|tabun|soman|cyclosarin|novichok|"
    r"mustard\s+gas|sulfur\s+mustard|lewisite|phosgene\s+oxime|"
    r"ricin|abrin|botulinum\s+toxin|anthrax|"
    r"nerve\s+(?:agent|gas)|chemical\s+weapon|biological\s+weapon|bioweapon|"
    r"radiological\s+(?:weapon|dispersal\s+device)|dirty\s+bomb|"
    r"nuclear\s+(?:weapon|bomb|device)"
)

_MAKE_VERBS = (
    r"synthesi[sz]e|synthesi[sz]ing|manufactur(?:e|ing)|make|making|"
    r"produce|producing|prepare|preparing|cook|cooking|brew|brewing|"
    r"extract|extracting|isolate|isolating|purify|purifying|"
    r"weaponi[sz]e|weaponi[sz]ing|build|building|construct|constructing|"
    r"assemble|assembling|create|creating|formulate|formulating|"
    r"grow|growing|culture|culturing|cultivate|cultivating|"
    r"concentrate|concentrating|enrich|enriching|reprocess|reprocessing|"
    r"refine|refining|distill|distilling|develop|developing|"
    r"obtain|obtaining|acquire|acquiring|procure|procuring"
)

_PRODUCTION_NOUNS = (
    r"synthesis|production|manufacture|manufacturing|weaponization|weaponisation|"
    r"preparation|formulation|extraction|isolation|purification|concentration|"
    r"enrichment|reprocessing"
)

# Only modifier words may sit between a production verb and its agent object, so
# "make a presentation about sarin" never matches while "make some pure sarin" does.
_MODIFIERS = (
    r"(?:(?:some|the|a|an|my|your|our|their|its|more|pure|concentrated|"
    r"weapons?[- ]grade|highly|lethal|deadly|potent|liquid|gaseous|crude|"
    r"homemade|diy|enough|batch\s+of|batches\s+of|"
    r"\d++(?:\.\d++)?+\s*+(?:grams?|g|kg|kilograms?|ml|milliliters?|millilitres?|"
    r"liters?|litres?|gallons?|ounces?|oz|pounds?|lbs?|tons?|tonnes?)(?:\s+of)?)\s++)*+"
)

_INSTRUCTION_NOUNS = (
    r"instructions?|steps?|recipe|recipes|guide|tutorial|walkthrough|procedure|"
    r"protocol|method|directions?|blueprint|formula|way"
)

_CBRN_RULES = (
    re.compile(rf"\b(?:{_MAKE_VERBS})\s++{_MODIFIERS}(?P<agent>{_AGENTS})\b", re.IGNORECASE),
    re.compile(
        rf"\b(?:{_MAKE_VERBS})\s++weapons?[- ]grade\s++(?P<agent>uranium|plutonium)\b",
        re.IGNORECASE,
    ),
    re.compile(
        rf"\b(?:{_PRODUCTION_NOUNS})\s+of\s++{_MODIFIERS}(?P<agent>{_AGENTS})\b", re.IGNORECASE
    ),
    re.compile(
        rf"\b(?P<agent>{_AGENTS})\s+(?:{_PRODUCTION_NOUNS}|recipe|recipes|instructions?|steps|"
        rf"step-by-step|guide|manual|protocol|precursors?)\b",
        re.IGNORECASE,
    ),
    re.compile(
        rf"\b(?:{_INSTRUCTION_NOUNS})\s+(?:for|to|on|of|about)\s++{_MODIFIERS}"
        rf"(?:(?:{_MAKE_VERBS})\s++{_MODIFIERS})?(?P<agent>{_AGENTS})\b",
        re.IGNORECASE,
    ),
)

# A defensive/educational noun within three words of the agent marks the mention as
# detection, medical, historical or forensic context — not a production request.
_DEFENSE_NOUNS = (
    r"detection|detector|detectors|sensor|sensors|test|tests|testing|kit|kits|"
    r"strip|strips|alarm|alarms|monitor|monitoring|vaccine|vaccines|antidote|antidotes|"
    r"treatment|therapy|history|historical|attack|attacks|incident|incidents|poisoning|"
    r"exposure|victim|victims|symptom|symptoms|cleanup|decontamination|disposal|"
    r"destruction|neutralization|threat|intel|intelligence|report|analysis|forensics|"
    r"residue|trace|traces|degradation|hydrolysis|sample|samples|assay|screening|"
    r"protection|protective|defense|defensive|defence|simulant|simulants|policy|"
    r"treaty|convention|ban|disarmament|warfare|program|programme"
)
_DEFENSE_FOLLOWS = re.compile(rf"^\s*+(?:\w++\s++){{0,2}}(?:{_DEFENSE_NOUNS})\b", re.IGNORECASE)

# ── Injection: exfiltration of hidden instructions / system prompt / tool config ──

_POSSESSIVE = r"your|its|ur|the\s+assistant(?:'s)?"
_SECRET_ADJ = (
    r"hidden|secret|internal|full|complete|entire|verbatim|initial|original|"
    r"underlying|raw|private|confidential|classified"
)
_TARGET_ADJ = (
    r"(?:full|complete|entire|exact|verbatim|raw|hidden|secret|internal|initial|"
    r"original|underlying|actual|real|true|private|confidential|classified|restricted)\s++"
)
_SENSITIVE_CORE = (
    r"system\s+prompt|system\s+instructions?|hidden\s+instructions?|system\s+message|"
    r"initial\s+instructions?|initial\s+prompt|hidden\s+prompt|secret\s+instructions?|"
    r"developer\s+instructions?|developer\s+message|pre-?prompt|system\s+role|"
    r"system\s+configuration|tool\s+configuration|tool\s+config|internal\s+configuration|"
    r"internal\s+config|tool\s+manifest|tool\s+schemas?|tool\s+definitions?|tool\s+json|"
    r"configuration\s+json|manifest[.\s]json|manifest\s+file|tool\s+list|tool\s+registry|"
    r"internal\s+manifest"
)
_SENSITIVE_GENERIC = (
    r"instructions?|directives?|config(?:uration)?|manifest|settings|tools?|"
    r"secrets?|keys?|credentials?|environment\s+variables?|env\s+vars?"
)
_EXFIL_TARGET = (
    rf"(?:(?:{_POSSESSIVE}|{_SECRET_ADJ})\s++(?:{_TARGET_ADJ})*"
    rf"(?:{_SENSITIVE_CORE}|{_SENSITIVE_GENERIC})"
    rf"|(?:the|this|that)\s++(?:{_TARGET_ADJ})*(?:{_SENSITIVE_CORE})"
    rf"|(?<!a )(?<!an )(?:{_SENSITIVE_CORE}))"
)
_EXFIL_VERBS = (
    r"print|reveal|show|display|output|repeat|recite|dump|leak|expose|disclose|divulge|"
    r"reproduce|quote|echo|paste|return|emit|give|tell|write|share|list|provide|send|"
    r"translate|summarize|summarise|paraphrase|encode|convert|read|spell|type|copy|"
    r"transcribe|render|produce|generate|extract|retrieve|fetch"
)
_EXFIL = re.compile(
    rf"\b(?P<verb>{_EXFIL_VERBS})\b(?P<gap>[^.!?\n]{{0,80}}?)(?P<target>{_EXFIL_TARGET})\b",
    re.IGNORECASE,
)
_POSSESSIVE_OR_SECRET = re.compile(rf"(?:{_POSSESSIVE}|{_SECRET_ADJ})\b", re.IGNORECASE)
# "show me how to write the system prompt" is comprehension, not exfiltration.
_COMPREHENSION = re.compile(r"\b(?:how|what|why|whether|if|when|where|which|who)\b", re.IGNORECASE)
_TARGET_DEFENSE = re.compile(
    r"^\s*+(?:works?|working)\b|^\s*+for\s+(?:my|our|a|an|the|this|that|your|his|her|their|its|"
    r"llms?|chatbots?|agents?|apps?|models?)\b|^\s*+,?\s*+(?:example|template|draft)\b",
    re.IGNORECASE,
)

_OVERRIDE = re.compile(
    r"\b(?:ignore|disregard|forget|override|bypass|suspend|dismiss|drop|cancel|void|"
    r"countermand|neglect|abandon|set\s+aside|do\s+not\s+follow|stop\s+following|"
    r"pay\s+no\s+attention\s+to)\s++(?:all\s+|any\s+|the\s+|your\s+|previous\s+|prior\s+|"
    r"earlier\s+|above\s+|system\s+|safety\s+|preceding\s+|initial\s+|original\s+|"
    r"existing\s+|current\s+|other\s+|those\s+|these\s+|my\s+|our\s+)*+"
    r"(?:instructions?|rules?|prompts?|directives?|guidelines?|constraints?|guardrails?|"
    r"programming|training|restrictions?|policies|policy|safeguards?|system\s+prompt)\b",
    re.IGNORECASE,
)
_MODE_CLAIM = re.compile(
    r"\bsystem\s+override\b|\b(?:maintenance|developer|debug|admin|god|dan|jailbreak|"
    r"diagnostic|service|root|superuser|unrestricted|unfiltered)\s+mode\b",
    re.IGNORECASE,
)
_CLAIM_REVEAL = re.compile(
    r"\b(?:reveal|print|show|dump|output|display|leak|expose|give|tell|return|emit|"
    r"disclose|share|divulge|repeat|recite|paste|echo|write|list|provide|send)\b"
    r"[^.!?\n]{0,80}\b(?:system\s+prompt|hidden\s+instructions?|instructions?|prompt|"
    r"config(?:uration)?|manifest|tools?|settings?|secrets?|keys?|environment|env|"
    r"internal|tool|rules?|guidelines?|directives?|constraints?|safeguards?|policies|policy)\b",
    re.IGNORECASE,
)
_ABOVE = re.compile(
    r"\b(?:repeat|print|output|recite|reproduce|echo|copy|paste|reveal|show|dump|"
    r"display|give|return|emit|write|quote)\b[^.!?\n]{0,40}\b(?:everything|"
    r"all\s+(?:the\s+)?(?:text|words|content|instructions|messages)|"
    r"the\s+(?:text|words|content|instructions|messages|prompt)|anything)\s+"
    r"(?:above|before|prior\s+to|preceding)\s+(?:this|the|your|my)\s+"
    r"(?:line|message|prompt|instructions?|text|conversation|first|start|beginning|system)\b",
    re.IGNORECASE,
)
_WHATIS = re.compile(
    r"\b(?:what\s+(?:is|are|was|were)|what['’]s|tell\s+me|show\s+me|give\s+me|"
    r"i\s+(?:want|need)\s+to\s+(?:see|know|read|view|have)|let\s+me\s+(?:see|read|view|know)|"
    r"can\s+i\s+(?:see|read|view|have)|may\s+i\s+(?:see|read|view)|"
    r"i['’]d\s+like\s+to\s+(?:see|read|view|know))\b[^.!?\n]{0,60}"
    rf"(?:{_POSSESSIVE}|{_SECRET_ADJ})\s++(?:{_TARGET_ADJ})*"
    rf"(?:{_SENSITIVE_CORE}|{_SENSITIVE_GENERIC})\b",
    re.IGNORECASE,
)


class GuardHit(NamedTuple):
    kind: str
    text: str


def _content_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(
            part["text"]
            for part in content
            if isinstance(part, dict)
            and part.get("type") in (None, "text")
            and isinstance(part.get("text"), str)
        )
    return ""


def last_user_text(messages: Any) -> str:
    """The current turn's text: the last user message, never system or tool content."""
    if not isinstance(messages, list):
        return ""
    for message in reversed(messages):
        if isinstance(message, dict) and message.get("role") == "user":
            return _content_text(message.get("content"))
    return ""


def _exfil_hit(text: str) -> bool:
    for match in _EXFIL.finditer(text):
        target = match.group("target")
        if not _POSSESSIVE_OR_SECRET.match(target) and _COMPREHENSION.search(match.group("gap")):
            continue
        if _TARGET_DEFENSE.match(text[match.end() :]):
            continue
        return True
    return False


def _injection(text: str) -> bool:
    if _exfil_hit(text) or _ABOVE.search(text) or _WHATIS.search(text):
        return True
    reveal = _CLAIM_REVEAL.search(text)
    return bool(reveal and (_OVERRIDE.search(text) or _MODE_CLAIM.search(text)))


def detect(text: str) -> str | None:
    """``"cbrn"`` / ``"injection"`` when the text is an explicit hard-line request, else None."""
    if not text.strip():
        return None
    for rule in _CBRN_RULES:
        for match in rule.finditer(text):
            if not _DEFENSE_FOLLOWS.match(text[match.end("agent") :]):
                return "cbrn"
    if _injection(text):
        return "injection"
    return None


def check_body(body: Any) -> GuardHit | None:
    """The refusal for a chat request body, or None when the turn may proceed."""
    if not isinstance(body, dict):
        return None
    kind = detect(last_user_text(body.get("messages")))
    if kind is None:
        return None
    return GuardHit(kind, CBRN_REFUSAL if kind == "cbrn" else INJECTION_REFUSAL)


class SafetyRefusalError(Exception):
    """A turn the deterministic guard refused before routing or any model call."""

    def __init__(self, hit: GuardHit, *, model: str, stream: bool, usage_wanted: bool) -> None:
        super().__init__(hit.text)
        self.kind = hit.kind
        self.text = hit.text
        self.model = model
        self.stream = stream
        self.usage_wanted = usage_wanted


def record_refusal(refusal: SafetyRefusalError) -> None:
    """One log line, trace span and counter per refused turn — never the prompt text."""
    logger.warning("safety guard refused turn: kind=%s model=%s", refusal.kind, refusal.model)
    trace_note(workspace=refusal.model, outcome="safety_refusal", guard=refusal.kind)
    trace_span("safety.refused", kind=refusal.kind, model=refusal.model)
    _record_safety_refusal(refusal.kind, refusal.model)


def refusal_response(refusal: SafetyRefusalError) -> JSONResponse | StreamingResponse:
    """A clean HTTP 200 refusal completion in the wire format the client asked for."""
    headers = {"x-portal-route": f"{refusal.model};;", "x-portal-safety-guard": refusal.kind}
    if not refusal.stream:
        return JSONResponse(
            content=no_answer.completion(refusal.model, refusal.text), headers=headers
        )
    return StreamingResponse(
        _refusal_stream(refusal), media_type="text/event-stream", headers=headers
    )


async def _refusal_stream(refusal: SafetyRefusalError) -> AsyncIterator[bytes]:
    request_id = f"chatcmpl-p5-{uuid.uuid4().hex[:12]}"
    created = int(time.time())

    def frame(payload: dict[str, Any]) -> bytes:
        return f"data: {json.dumps(payload)}\n\n".encode()

    yield frame(
        {
            "id": request_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": refusal.model,
            "choices": [
                {
                    "index": 0,
                    "delta": {"role": "assistant", "content": refusal.text},
                    "finish_reason": None,
                }
            ],
        }
    )
    yield frame(
        {
            "id": request_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": refusal.model,
            "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
        }
    )
    if refusal.usage_wanted:
        yield frame(
            {
                "id": request_id,
                "object": "chat.completion.chunk",
                "created": created,
                "model": refusal.model,
                "choices": [],
                "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            }
        )
    yield b"data: [DONE]\n\n"
