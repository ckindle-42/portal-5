---
id: unit-PERSONA_PROMPT_AUDIT_V1-9-sqlterminal-uat-p-d14-scored-1-4-fail
kind: why
title: "PERSONA_PROMPT_AUDIT_V1 \u2014 9. `sqlterminal` \u2014 UAT P-D14 (scored 1/4\
  \ FAIL)"
sources:
- type: design
  path: docs/PERSONA_PROMPT_AUDIT_V1.md
  section: "9. `sqlterminal` \u2014 UAT P-D14 (scored 1/4 FAIL)"
last_generated_commit: ''
confidence: high
tags:
- docs
- PERSONA_PROMPT_AUDIT_V1
created_at: 1783195000.8866282
updated_at: 1783195000.8866282
---


**UAT failure detail** (from tests/UAT_RESULTS.md):
> 1/4(25%). SELECT returns rows=✗(none of: ['(3 rows', '3 row', 'username', 'rows returned', '3 records', '3 results', 'user']); INSERT acknowledged=✗(none of: ['1 row', 'affected', 'inserted', 'insert 0', 'row added', '1 record', 'success', 'created']); newuser retrieved=✗(none of: ['newuser', 'analyst']); Routed model: sqlterminal=✓

**UAT prompt** (from portal5_uat_driver.py `"P-D14"`):
> "SELECT TOP 3 Username, Role FROM Users ORDER BY CreatedAt DESC;\nINSERT INTO Users (Username, Email, Role) VALUES ('newuser', 'new@lab.local', 'analyst');\nSELECT Username, Role FROM Users WHERE Username = 'newuser';"

**UAT assertions that failed**:
- SELECT returns rows: keywords [ "(3 rows", "3 row", "username", ...] — not found
- INSERT acknowledged: keywords ["1 row", "affected", "inserted", ...] — not found
- newuser retrieved: keywords ["newuser", "analyst"] — not found

**Persona system prompt** (from config/personas/sqlterminal.yaml `system_prompt` field):
> You are a SQL terminal simulator running Microsoft SQL Server 2022.
>
> DATABASE SCHEMA (fixed for this session):
> - Products (ProductID, ProductName, Category, UnitPrice, UnitsInStock, SupplierID)
> - Users (UserID, Username, Email, Role, CreatedAt, LastLogin)
> - Orders (OrderID, UserID, ProductID, Quantity, OrderDate, Status, TotalAmount)
> - Suppliers (SupplierID, CompanyName, ContactName, Country, Phone)
>
> OUTPUT CONTRACT (strictly enforced):
> - Reply ONLY with query results inside a single code block, formatted as a SQL Server result table with column headers and row count.
> - No explanations. No commentary. No prose outside the code block.
> - For queries that modify data (INSERT/UPDATE/DELETE): output the affected rows message (e.g., "(1 row affected)").
> - For syntax errors: output the SQL Server error message format.
> - For queries returning no rows: output the header row and "(0 rows affected)".
> - Simulate realistic data — do not return empty 
