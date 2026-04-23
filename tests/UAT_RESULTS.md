# Portal 5 — UAT Results

**Run:** 2026-04-22 22:12:57  
**Guide:** user_validation_guide_v3.docx  
**Reviewer:** (fill in)

## Summary

- **PASS**: 1
- **WARN**: 0
- **FAIL**: 5
- **SKIP**: 0
- **MANUAL**: 0

## Results

| # | Status | Test | Model | Detail | Elapsed |
|---|--------|------|-------|--------|---------|
| 1 | PASS | [WS-15 Data Analyst — SIEM Dataset Cleaning](http://localhost:8080/c/9d1ca553-c65d-4742-bd7e-eacd25962b99) | `auto-data` | Timestamp normalization=✓(found: ['pd.to_datetime', 'to_datetime', 'timestamp']); Missing src_ip handling=✓(found: ['fillna', 'dropna', 'isnull', 'isna', 'nan', 'NaN', 'null', 'missing', 'empty']); bytes_out sentinel=✓(found: ['bytes_out', 'invalid', 'fillna', 'replace', 'nan', 'NaN', '-1']); Pandas code present or referenced=✓(found: ['```python', '```', 'pd.', 'df.', 'import pandas', 'pandas']) | 480.9s |
| 2 | FAIL | [P-DA01 Data Analyst — Correlation vs Causation](http://localhost:8080/c/3b8a7a2d-59ce-40c3-9b38-cea1496e5190) | `dataanalyst` | Correlation/causation distinguished=✗(none of: ['correlation', 'causation', 'correlation does not', 'does not imply']); A/B test recommended=✗(none of: ['a/b test', 'experiment', 'randomized', 'causal']); Does not recommend forcing=✓(ok) | 111.8s |
| 3 | FAIL | [P-DA02 Data Scientist — Imbalanced Class Problem](http://localhost:8080/c/e03d7159-576a-4279-8c24-3350479ddee7) | `datascientist` | exception=✗(Page.goto: Timeout 15000ms exceeded.
Call log:
  - navigating to "http://localhost:8080/c/e03d7159-576a-4279-8c24-335047) | 15.0s |
| 4 | FAIL | [P-DA03 ML Engineer — Benchmark vs Production](http://localhost:8080/c/d05a3a5d-4d95-4567-b16f-a40fd1f027b8) | `machinelearningengineer` | exception=✗(Page.goto: Timeout 15000ms exceeded.
Call log:
  - navigating to "http://localhost:8080/c/d05a3a5d-4d95-4567-b16f-a40fd1) | 15.0s |
| 5 | FAIL | [P-DA04 Statistician — Check Assumptions Before t-test](http://localhost:8080/c/253787bf-0da7-4e88-bff7-bbeece371bf8) | `statistician` | exception=✗(Page.goto: Timeout 15000ms exceeded.
Call log:
  - navigating to "http://localhost:8080/c/253787bf-0da7-4e88-bff7-bbeece) | 15.0s |
| 6 | FAIL | [P-DA05 Phi-4 STEM Analyst — Binomial Derivation](http://localhost:8080/c/5a988482-d053-4e5a-80b5-ac971d2b4065) | `phi4stemanalyst` | exception=✗(Page.goto: Timeout 15000ms exceeded.
Call log:
  - navigating to "http://localhost:8080/c/5a988482-d053-4e5a-80b5-ac971d) | 15.0s |
