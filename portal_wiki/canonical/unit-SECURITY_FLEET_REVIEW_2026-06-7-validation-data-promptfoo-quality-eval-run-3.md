---
id: unit-SECURITY_FLEET_REVIEW_2026-06-7-validation-data-promptfoo-quality-eval-run-3
kind: why
title: "SECURITY_FLEET_REVIEW_2026-06 \u2014 7. Validation Data \u2014 Promptfoo Quality\
  \ Eval (Run 3)"
sources:
- type: design
  path: docs/SECURITY_FLEET_REVIEW_2026-06.md
  section: "7. Validation Data \u2014 Promptfoo Quality Eval (Run 3)"
last_generated_commit: ''
confidence: high
tags:
- docs
- SECURITY_FLEET_REVIEW_2026-06
created_at: 1783195000.917409
updated_at: 1783195000.917409
---


**Config**: `config/promptfoo/security_quality.yaml`  
**4 tests**: Log4Shell CVE, SQLi/XSS, ransomware IR, Splunk SSH search  
**5 providers**: baronllm-abliterated (auto-security-baronllm), VulnLLM (auto-security-vulnllm), qwen3.5-abliterated (auto-redteam), Gemma-4-31B-JANG (auto-pentest), sylink (auto-blueteam)  
**Result**: 19/20 (95%) — duration 17m 58s

| Workspace | Model | Score | Notes |
|---|---|---|---|
| `auto-security` (primary) | baronllm-abliterated | **4/4** | All pass — clean across Log4Shell, SQLi/XSS, IR, Splunk |
| `auto-security` (specialist) | VulnLLM-R-7B Q4_K_M | **3/4** | FAIL: Log4Shell — describes CVE as "deserialization flaw" + wrong class ref; JNDI/LDAP not mentioned. Real knowledge gap, consistent across 3 runs. |
| `auto-redteam` | qwen3.5-abliterated:9b | **4/4** | All pass |
| `auto-pentest` | Gemma-4-31B-JANG Q4_K_M | **4/4** | All pass |
| `auto-blueteam` | sylink/sylink:8b | **4/4** | All pass |

**baronllm-abliterated confirmed 4/4**: The auto-security primary passes all quality checks including Log4Shell (correctly identifies JNDI injection, not deserialization). Higher quality than VulnLLM on this dimension despite being a generalist cybersec model vs. a vuln-specialist.

**VulnLLM Log4Shell gap**: Consistent across 3 promptfoo runs. The model knows Log4j is involved but misidentifies the vulnerability class (calls it "deserialization" rather than JNDI injection). This is a genuine training gap for Log4Shell specifically. VulnLLM remains in `auto-security` for its vuln research depth in other areas — the gap should inform prompt engineering for Log4Shell-specific work.

---
