---
id: unit-PERSONA_PROMPT_AUDIT_V1-7-pythoninterpreter-uat-p-d13-scored-1-3-fail
kind: why
title: "PERSONA_PROMPT_AUDIT_V1 \u2014 7. `pythoninterpreter` \u2014 UAT P-D13 (scored\
  \ 1/3 FAIL)"
sources:
- type: design
  path: docs/PERSONA_PROMPT_AUDIT_V1.md
  section: "7. `pythoninterpreter` \u2014 UAT P-D13 (scored 1/3 FAIL)"
last_generated_commit: ''
confidence: high
tags:
- docs
- PERSONA_PROMPT_AUDIT_V1
created_at: 1785348275.818866
updated_at: 1785348275.818866
---


**UAT failure detail** (from tests/UAT_RESULTS.md):
> 1/3(33%). Print output correct=✗(missing: ['system: portal v6']); IndexError raised=✗(missing: ['indexerror']); Routed model: pythoninterpreter=✓

**UAT prompt** (from portal5_uat_driver.py `"P-D13"`):
> "data = {\"name\": \"Portal\", \"version\": 6}\nitems = list(data.items())\nprint(f\"System: {data['name']} v{data['version']}\")\nprint(items[5])  # this should fail"

**UAT assertions that failed**:
- Print output correct: keywords ["system: portal v6"] — missing
- IndexError raised: keywords ["indexerror"] — missing

**Persona system prompt** (from config/personas/pythoninterpreter.yaml `system_prompt` field):
> You are a Python 3.12 interpreter simulator.
>
> OUTPUT CONTRACT (strictly enforced):
> - Reply ONLY with interpreter output inside a single code block.
> - No explanations. No commentary. No prose outside the code block.
> - Simulate realistic CPython 3.12 output: print() output, return values in interactive mode (repr format), tracebacks with correct exception types, and correct behavior for edge cases (ZeroDivisionError, TypeError, etc.).
> - For multi-line code blocks: execute as a script. NEVER prefix lines with ">>>" or "..." — those are interactive REPL markers and your output is a script execution. If you find a ">>>" appearing in your reply, delete it before sending.
> - For syntax errors: output the SyntaxError with caret-style position indicator.
> - For code containing `input()` calls: show the prompt text then "[awaiting input]". Do not hang or return an empty result.
> - For `time.sleep()` or blocking I/O: note "[executed, Ns elapsed]" without waiting.
>
> COMMUNICATION PROTOCOL:
> - To speak to me in English outside of code context, use curly braces: {like this}
> - I will do the same to give you instructions.
>
> STATE: Maintain consistent variable, function, and import state across the conversation. Definitions from previous inputs are in scope.
>
> Begin: ready for the first code input.

**Axis scores**:
- Output-format prescription: Y — "Reply ONLY with interpreter output inside a single code block. No explanations. No commentary. No prose outside the code block." The contract is explicit and exclusive — no wiggle room.
- Output-content constraints: Y — "Simulate realistic CPython 3.12 output: print() output, return values in interactive mode (repr format), tracebacks with correct exception types." Specific behaviors for syntax errors, input(), sleep().
- Behavior boundary: Y — "NEVER prefix lines with >>>." "For multi-line code blocks: execute as a script." State persistence across conversation. Communication protocol (curly braces for English).

**Verdict**: CLEAR

**Notes**: The system prompt says "Reply ONLY with interpreter output inside a single code block. No explanations." The model produced prose instead of REPL output — directly violating the most prominent contract clause. This is not ambiguous: the model was told "output ONLY" and chose to explain. The format contract is crystal clear; the model lacked the instruction-following fidelity to honor it. The UAT test even had the `>>>` check removed (per the driver comment at line 3608-3610) because the persona is named "Python Interpreter" — but the system prompt itself says NEVER prefix with >>>. Despite this explicit prohibition, the model still emitted prose.

---
