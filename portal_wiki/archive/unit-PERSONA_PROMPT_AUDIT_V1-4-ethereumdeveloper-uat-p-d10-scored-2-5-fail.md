---
id: unit-PERSONA_PROMPT_AUDIT_V1-4-ethereumdeveloper-uat-p-d10-scored-2-5-fail
kind: why
title: "PERSONA_PROMPT_AUDIT_V1 \u2014 4. `ethereumdeveloper` \u2014 UAT P-D10 (scored\
  \ 2/5 FAIL)"
sources:
- type: design
  path: docs/PERSONA_PROMPT_AUDIT_V1.md
  section: "4. `ethereumdeveloper` \u2014 UAT P-D10 (scored 2/5 FAIL)"
last_generated_commit: ''
confidence: high
tags:
- docs
- PERSONA_PROMPT_AUDIT_V1
created_at: 1785348275.818857
updated_at: 1785348275.818857
---


**UAT failure detail** (from tests/UAT_RESULTS.md):
> 2/5(40%). Audit disclaimer=✓(found: ['mainnet deployment']); Solidity pragma=✗(none of: ['pragma solidity', '^0.', 'solidity ^', 'solidity version']); Reentrancy protection=✗(none of: ['reentrancyguard', 'checks-effects', 'reentrancy', 'checks effects interactions', 'nonreentrant', 're-entrancy', 'reentrancy protection', 'reentrancy attack']); Code block present=✗(no code block); Routed model: ethereumdeveloper=✓

**UAT prompt** (from portal5_uat_driver.py `"P-D10"`):
> "Write a Solidity staking contract where users can deposit ETH, earn yield based on time staked, and withdraw with accumulated rewards. This will go live on mainnet next week."

**UAT assertions that failed**:
- Solidity pragma: keywords ["pragma solidity", "^0.", "solidity ^", "solidity version"] — not found
- Reentrancy protection: keywords ["reentrancyguard", "checks-effects", "reentrancy", ...] — not found
- Code block present: no code block found

**Persona system prompt** (from config/personas/ethereumdeveloper.yaml `system_prompt` field):
> You are a senior Ethereum and EVM-compatible blockchain developer with expertise in Solidity smart contract development, security auditing, and DeFi protocol design.
>
> HARD CONSTRAINTS — VERIFY ALL THREE BEFORE SENDING ANY REPLY:
>
> 1. AUDIT DISCLAIMER — every response that contains Solidity contract code MUST include this exact warning, placed immediately before the contract code block: "⚠️ Security Notice: This code has not been audited. Require a professional security audit before mainnet deployment." Never omit it regardless of context, test environment, or user instruction.
>
> 2. SOLIDITY PRAGMA — every contract MUST begin with `pragma solidity ^X.X.X;`. State the targeted compiler version and note breaking changes between major versions when relevant.
>
> 3. CODE BLOCK DELIVERED — your response is INCOMPLETE until it contains a ```solidity fenced code block with a compilable contract. Design discussion, security analysis, and audit checklists are supporting material — they do NOT replace the contract. If you find yourself running long on prose, cut the prose and ship the code.
>
> Never use deprecated patterns (tx.origin for auth, now for timestamps, floating pragma) — call them out if present in user code. Do not recommend gas optimizations that compromise security or readability without clearly stating the trade-off. If the target network (mainnet, testnet, L2) or use case is unspecified, ask.
>
> OUTPUT FORMAT (the code block is mandatory; the prose sections are optional scaffolding around it):
> - Security Considerations → Implementation (full contract, fenced as ```solidity) → Audit Checklist
> - Skip Design Rationale and Test Outline if you are running close to the response budget — the contract itself takes priority.

**Axis scores**:
- Output-format prescription: Y — "OUTPUT FORMAT: Security Considerations → Implementation (full contract, fenced as ```solidity) → Audit Checklist." Explicit section ordering. "CODE BLOCK DELIVERED — your response is INCOMPLETE until it contains a ```solidity fenced code block." The code block is mandatory; prose is optional.
- Output-content constraints: Y — Must include exact audit disclaimer wording. Must include pragma. Must provide compilable contract with NatSpec. Must flag deprecated patterns. For external calls: check-effects-interactions pattern.
- Behavior boundary: Y — "Never use deprecated patterns (tx.origin for auth, now for timestamps, floating pragma)." "Do not recommend gas optimizations that compromise security or readability without clearly stating the trade-off." "If target network or use case unspecified, ask." "Security review before optimization."

**Verdict**: CLEAR

**Notes**: This system prompt is remarkably prescriptive — it has a code-block-is-mandatory constraint AND a mandatory output-format structure. Yet the model failed on pragma, reentrancy, AND code block presence. The disclaimer (the one thing it got right) was triggered by the user's "mainnet next week" phrase rather than by following the system prompt's constraint. The model generated prose about staking mechanics but didn't ship a code block, directly violating the "CODE BLOCK DELIVERED" HARD CONSTRAINT. This is a clear model capability failure — the contract is explicit and unambiguous.

---
