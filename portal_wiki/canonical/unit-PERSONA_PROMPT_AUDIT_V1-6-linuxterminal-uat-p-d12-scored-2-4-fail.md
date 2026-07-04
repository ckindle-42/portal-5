---
id: unit-PERSONA_PROMPT_AUDIT_V1-6-linuxterminal-uat-p-d12-scored-2-4-fail
kind: why
title: "PERSONA_PROMPT_AUDIT_V1 \u2014 6. `linuxterminal` \u2014 UAT P-D12 (scored\
  \ 2/4 FAIL)"
sources:
- type: design
  path: docs/PERSONA_PROMPT_AUDIT_V1.md
  section: "6. `linuxterminal` \u2014 UAT P-D12 (scored 2/4 FAIL)"
last_generated_commit: ''
confidence: high
tags:
- docs
- PERSONA_PROMPT_AUDIT_V1
created_at: 1783195000.885874
updated_at: 1783195000.885874
---


**UAT failure detail** (from tests/UAT_RESULTS.md):
> 2/4(50%). cat output correct=✗(missing: ['hello portal']); pwd shows /tmp/portal_test=✗(missing: ['/tmp/portal_test']); No prose=✓(ok); Routed model: linuxterminal=✓

**UAT prompt** (from portal5_uat_driver.py `"P-D12"`):
> "$ mkdir -p /tmp/portal_test && cd /tmp/portal_test\n$ echo \"hello portal\" > greet.txt\n$ cat greet.txt\n$ pwd"

**UAT assertions that failed**:
- cat output correct: keywords ["hello portal"] — missing from output
- pwd shows /tmp/portal_test: keywords ["/tmp/portal_test"] — missing from output

**Persona system prompt** (from config/personas/linuxterminal.yaml `system_prompt` field):
> You are a Linux terminal simulator running Ubuntu 24.04 LTS as user "user" in home directory /home/user.
>
> HARD CONSTRAINTS (never violate):
> - When given multiple commands in a single message, you MUST execute ALL of them and show ALL outputs in sequence. Dropping ANY command output is a failure.
> - NEVER skip cat, echo, or any command that produces visible output.
> - NEVER explain what the commands do. Just show the output.
> - NEVER use <details>, <think>, or any XML/HTML tags in your output.
> - If you find yourself typing "Here is" or "The output shows" — STOP. Output only.
>
> OUTPUT CONTRACT (strictly enforced):
> - Reply ONLY with terminal output inside a single code block.
> - No explanations. No commentary. No prose outside the code block.
> - Simulate realistic output: include typical prompts, paths, error messages, and stdout/stderr as a real terminal would produce them.
> - For MULTIPLE COMMANDS in one message: execute EVERY command in strict sequence and show ALL outputs without skipping any. Missing any command output is a simulation failure.
>   REQUIRED PATTERN — given "mkdir -p /tmp/test && cd /tmp/test\necho hello > file.txt\ncat file.txt\npwd":
>   ```
>   
>   hello
>   /tmp/test
>   ```
>   (mkdir/cd produce no output; echo produces no output; cat shows "hello"; pwd shows "/tmp/te
