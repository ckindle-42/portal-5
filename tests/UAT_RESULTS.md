# Portal 5 — UAT Results

**Run:** 2026-04-27 21:57:18  
**Catalog:** TEST_CATALOG (see tests/portal5_uat_driver.py)  
**Reviewer:** (fill in)

## Summary

- **PASS**: 4
- **WARN**: 0
- **FAIL**: 3
- **SKIP**: 0
- **MANUAL**: 1

## Results

| # | Status | Test | Model | Detail | Elapsed |
|---|--------|------|-------|--------|---------|
| 1 | PASS | [A-01 Document RAG — Upload, Query, Follow-Up](http://localhost:8080/c/2773aa7b-2031-4d2b-87d7-13670546151f) | `auto` | 3/3(100%) Turn 1 summary substantive=✓(len=298, min=150); Not generic=✓(ok); Turn 2 retrieval substantive=✓(len=211, min=100) | 409.2s |
| 2 | PASS | [A-02 Knowledge Base — Persistent Collection Query](http://localhost:8080/c/34149be8-d1b8-4976-8b65-11aec6f431f3) | `auto` | 2/2(100%) Response substantive=✓(len=395, min=100); Collection found=✓(ok) | 161.0s |
| 3 | FAIL | [A-03 Cross-Session Memory — Fact Persistence](http://localhost:8080/c/795d40f7-93a7-4b58-bba4-817d880bdf29) | `auto` | 0/1(0%) [routed: auto] exception=✗(Page.screenshot: Timeout 30000ms exceeded.
Call log:
  - taking page screenshot
  - waiting for fonts to load...
  - fon) | 579.0s |
| 4 | FAIL | [A-04 Routing Validation — Content-Aware Selection](http://localhost:8080/c/7db1cd97-d112-4db8-8bc5-4d5055cfa04d) | `auto` | 0/1(0%) [routed: auto] exception=✗(Locator.click: Timeout 30000ms exceeded.
Call log:
  - waiting for locator("textarea, [contenteditable='true']").first
 ) | 349.5s |
| 5 | MANUAL | [A-07 Grafana Monitoring — Metrics Visibility](http://localhost:8080/c/3319b5cb-0e34-49d9-9f12-1ac5214b4456) | `auto` | 0/0  | 0.0s |
| 6 | FAIL | [P-B06 Paywalled Researcher — Source Strategy](http://localhost:8080/c/394a714f-1eae-4d97-b9ac-99a2272d4fbe) | `paywalledresearcher` | 0/1(0%) exception=✗(Locator.click: Timeout 30000ms exceeded.
Call log:
  - waiting for locator("textarea, [contenteditable='true']").first
 ) | 63.5s |
| 7 | PASS | [P-W03 Tech Reviewer — Training Data Caveat on Benchmarks](http://localhost:8080/c/5fae772a-d73e-4752-b9b2-14b903543fc3) | `techreviewer` | 3/3(100%) Training data caveat=✓(found: ['current', 'manufacturer']); Both chips compared=✓(found: ['m4 pro and m4 max']); Recommendation given=✓(found: ['recommend', 'buy']) | 509.6s |
| 8 | PASS | [P-B03 Web Navigator — Task Decomposition](http://localhost:8080/c/fd484f4c-ed8c-4495-97ef-6b3a56ec06cc) | `webnavigator` | 2/2(100%) Task decomposition=✓(found: ['navigate', 'billing', 'first']); Safety awareness=✓(found: ['ask']) | 81.1s |
