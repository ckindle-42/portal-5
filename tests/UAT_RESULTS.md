# Portal 5 — UAT Results

**Run:** 2026-04-23 23:51:03  
**Guide:** user_validation_guide_v3.docx  
**Reviewer:** (fill in)

## Summary

- **PASS**: 0
- **WARN**: 0
- **FAIL**: 4
- **SKIP**: 0
- **MANUAL**: 0

## Results

| # | Status | Test | Model | Detail | Elapsed |
|---|--------|------|-------|--------|---------|
| 1 | FAIL | [WS-13 Research Assistant — Post-Quantum Cryptography](http://localhost:8080/c/843f30a0-b839-451f-9958-9ad6a2bc1e23) | `auto-research` | 0/4(0%) NIST algorithms named=✗(none of: ['ml-kem', 'kyber', 'ml-dsa', 'dilithium', 'slh-dsa']); TLS library mentioned=✗(none of: ['openssl', 'boringssl', 'rustls', 'tls']); Migration timeline=✗(none of: ['phase', 'migrat', 'timeline', 'roadmap', 'step', 'schedule']); Substantive response=✗(len=0, min=500) | 292.2s |
| 2 | FAIL | [P-R05 Research Analyst — Evidence Quality Labeling](http://localhost:8080/c/0afb6a39-2230-4ff9-9eca-baa27514f235) | `researchanalyst` | 1/3(33%) Evidence labels present=✗(none of: ['established fact', 'strong evidence', 'inference', 'speculation', 'well established', 'widely accepted', 'evidence suggests', 'likely', 'inferred', 'speculative', 'uncertain', 'high confidence', 'medium confidence', 'low confidence', 'established:', 'evidence:', 'inference:', 'speculation:', '[established', '[strong', '[inference', '[speculation', 'fact:', 'based on evidence', 'limited evidence']); Counterpoints included=✗(none of: ['however', 'but', 'challenge', 'limitation', 'concern', 'caveat', 'drawback', 'disadvantage', 'on the other hand', 'critics', 'some argue', 'others argue', 'debate', 'not without', 'it should be noted', 'worth noting']); No absolute claim=✓(ok) | 1918.2s |
| 3 | FAIL | [P-R06 Gemma Research Analyst — AI Regulation with Evidence Framework](http://localhost:8080/c/f1d2e2f8-baaf-498f-9f57-afe393511c07) | `gemmaresearchanalyst` | 0/3(0%) Evidence labels present=✗(none of: ['established fact', 'strong evidence', 'inference', 'speculation', '[established', '[strong', '[inference', '[speculation']); EU AI Act covered=✗(none of: ['eu ai act', 'european', 'eu act', 'artificial intelligence act']); Expert disagreement surfaced=✗(none of: ['disagreement', 'debate', 'some argue', 'others argue', 'conflicting', 'contend', 'dispute', 'differ', 'not all', 'critics']) | 232.5s |
| 4 | FAIL | [P-R07 SuperGemma4 Uncensored — Adversarial ML Analysis](http://localhost:8080/c/0503da18-8e52-42ad-8eab-5231a2c3dcd2) | `supergemma4researcher` | 1/4(25%) Prompt injection covered=✗(none of: ['prompt injection', 'injecting', 'indirect injection', 'instruction injection']); Model extraction covered=✗(none of: ['model extraction', 'api', 'reconstruct', 'stealing', 'extraction attack', 'query budget']); Defenses included=✗(none of: ['detect', 'mitigat', 'defend', 'prevent', 'protect', 'filter', 'monitor', 'sanitiz']); No excessive refusal=✓(ok) | 232.2s |
