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
created_at: 1783195000.885349
updated_at: 1783195000.885349
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
> 3. CODE BLOCK DELIVERED — your response is INCOMPLETE until it contains a ```solidity fenced code block with a compilable contract. Design d
