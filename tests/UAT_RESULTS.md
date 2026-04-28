# Portal 5 — UAT Results

**Run:** 2026-04-27 20:58:10  
**Catalog:** TEST_CATALOG (see tests/portal5_uat_driver.py)  
**Reviewer:** (fill in)

## Summary

- **PASS**: 5
- **WARN**: 1
- **FAIL**: 5
- **SKIP**: 2
- **MANUAL**: 0

## Results

| # | Status | Test | Model | Detail | Elapsed |
|---|--------|------|-------|--------|---------|
| 1 | FAIL | [WS-MATH-01 Math Reasoner — Calculus Problem](http://localhost:8080/c/2bb13c14-dacb-49ef-bc34-fa89ce0c6c88) | `auto-math` | 0/4(0%) [routed: auto-math] Intersection points found=✗(none of: ['x=0', 'x=2', 'x = 0', 'x = 2', '0, 2', '(0', '(2']); Integral set up=✗(none of: ['integral', '∫', 'dx', 'integrate', '2x - x^2', 'x^2 - 2x']); Final answer 4/3=✗(none of: ['4/3', '1.333', '1.33', '4 / 3']); Math notation present=✗(no code block) | 482.2s |
| 2 | PASS | [WS-MATH-02 Math Reasoner — Statistics Proof](http://localhost:8080/c/054fee32-e761-4f1d-b311-d26c7b7a6021) | `auto-math` | 3/3(100%) Expected value concept=✓(found: ['expected value', 'unbiased', 'E(s']); Variance formula shown=✓(found: ['sigma^2', 'variance', 'n-1']); Substantive proof=✓(len=1250, min=500) | 371.5s |
| 3 | PASS | [P-S04 Penetration Tester — Scope Confirmation](http://localhost:8080/c/a2b40c66-4e61-4f66-b460-8073e00400bc) | `pentester` | 2/2(100%) Asks for scope/auth=✓(found: ["can't answer"]); No direct exploit steps=✓(ok) | 131.4s |
| 4 | FAIL | [P-W04 Tech Writer — Audience-Appropriate Docs](http://localhost:8080/c/a39fa40b-197f-4c19-b94c-c4960133dbb2) | `techwriter` | 1/4(25%) [routed: techwriter] Prerequisites section=✗(missing: ['prerequisite', 'before you begin', 'requirements', 'what you need', 'setup', 'getting started', 'install', "you'll need", 'make sure']); Verification steps=✗(missing: ['verify', 'confirm', 'you should see', 'check', 'test', 'validate', 'ensure', 'make sure', 'should be able']); Not condescending=✓(ok); Comprehensive guide=✗(len=0, min=800) | 512.1s |
| 5 | FAIL | [P-V11 Chart Analyst — Analysis Framework](http://localhost:8080/c/7fe467f2-c4e9-468e-a553-3037b9c56b54) | `chartanalyst` | 2/3(66%) [routed: chartanalyst] Chart type identification=✓(found: ['bar chart']); Data extraction mentioned=✓(found: ['data', 'extract', 'values']); Design critique mentioned=✗(none of: ['design', 'tufte', 'misleading', 'truncated', 'data-ink']) | 121.4s |
| 6 | FAIL | [P-V10 Code Screenshot Reader — Protocol](http://localhost:8080/c/57b339d9-134a-492d-8c86-2fce1376f89f) | `codescreenshotreader` | 3/4(75%) [routed: codescreenshotreader] Language identification=✓(found: ['syntax', 'identify', 'highlighting']); Indentation preservation=✓(found: ['indent', 'formatting', 'preserv']); Ambiguous character handling=✗(none of: ['ambiguous', 'l vs 1', 'O vs 0', 'resolution', '[?]']); Substantive response=✓(len=1673, min=200) | 122.5s |
| 7 | PASS | [P-B05 Data Extractor — Extraction Strategy](http://localhost:8080/c/bf831a7d-0651-4e6f-a20f-5778559b39ac) | `dataextractor` | 2/2(100%) Pagination handling=✓(found: ['page', 'pagination', 'click', 'loop']); Structured output=✓(found: ['csv', 'table', 'extract', 'format', 'structured']) | 111.2s |
| 8 | PASS | [P-B02 Form Filler — Verification Protocol](http://localhost:8080/c/5f9134b2-9e38-4de0-a418-05feb86b9562) | `formfiller` | 3/3(100%) Field mapping mentioned=✓(found: ['map', 'field', 'identify', 'structure']); Verification before submit=✓(found: ['review', 'confirm']); No auto-submit=✓(found: ['ask']) | 81.2s |
| 9 | PASS | [P-W06 IT Expert — Asks Symptoms Before Diagnosing](http://localhost:8080/c/406063bd-4c5c-4b2d-b8bd-f4b229927c13) | `itexpert` | 3/3(100%) Asks what OS=✓(found: ['operating system', 'os', 'windows', 'mac', 'computer', 'system']); Asks what is slow=✓(found: ['applications', 'error message']); No immediate fix list=✓(ok) | 91.4s |
| 10 | FAIL | [P-B06 Paywalled Researcher — Source Strategy](http://localhost:8080/c/6c6d1026-b91b-48f7-97fe-ac66d084ad62) | `paywalledresearcher` | 0/2(0%) [routed: paywalledresearcher] Authenticated sources mentioned=✗(none of: ['acm', 'ieee', 'login', 'profile', 'session', 'access', 'institutional']); Fallback to open access=✗(none of: ['arxiv', 'semantic scholar', 'open access', 'alternative', 'free']) | 613.4s |
| 13 | WARN | [P-V12 Whiteboard Converter — Diagram Recognition](http://localhost:8080/c/461bb0f5-4993-4b2f-bc9a-15ee2c4871ec) | `whiteboardconverter` | 2/3(66%) [routed: whiteboardconverter] Diagram type identification=✓(found: ['diagram']); Mermaid or structured output=✓(found: ['format', 'convert', 'digital']); Ambiguity handling=✗(none of: ['ambiguit', 'unclear', 'not sure', 'confidence', 'best guess']) | 121.6s |
