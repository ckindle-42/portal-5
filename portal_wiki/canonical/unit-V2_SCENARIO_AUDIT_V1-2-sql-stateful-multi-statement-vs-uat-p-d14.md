---
id: unit-V2_SCENARIO_AUDIT_V1-2-sql-stateful-multi-statement-vs-uat-p-d14
kind: why
title: "V2_SCENARIO_AUDIT_V1 \u2014 2. `sql-stateful-multi-statement` vs UAT P-D14"
sources:
- type: design
  path: docs/V2_SCENARIO_AUDIT_V1.md
  section: 2. `sql-stateful-multi-statement` vs UAT P-D14
last_generated_commit: ''
confidence: high
tags:
- docs
- V2_SCENARIO_AUDIT_V1
created_at: 1783195000.922961
updated_at: 1783195000.922961
---


**UAT P-D14 status**: FAIL (1/4 with Laguna)
**V2 Laguna result**: PASS

**UAT prompt** (verbatim from line 3614-3616):
> SELECT TOP 3 Username, Role FROM Users ORDER BY CreatedAt DESC;
> INSERT INTO Users (Username, Email, Role) VALUES ('newuser', 'new@lab.local', 'analyst');
> SELECT Username, Role FROM Users WHERE Username = 'newuser';

**V2 prompt** (verbatim from coding_scenarios.yaml):
> You are a SQL terminal. I will give you statements one block at a time.
> Respond as a real PostgreSQL REPL would — show the result of each
> statement (row count, returned rows, or INSERT/UPDATE acks).
>
> Block 1:
>   CREATE TABLE users (id SERIAL PRIMARY KEY, username TEXT NOT NULL, role TEXT);
>   INSERT INTO users (username, role) VALUES ('alice', 'analyst'), ('bob', 'admin'), ('carol', 'analyst');
>   SELECT username, role FROM users WHERE role = 'analyst';
>   INSERT INTO users (username, role) VALUES ('newuser', 'analyst');
>   SELECT username FROM users WHERE username = 'newuser';
>
> Show the output of each statement in order, in the format a psql
> terminal would print.

**Axis scores**:
- Output-format prescription: **Y** — V2: "Respond as a real PostgreSQL REPL would — show the result of each statement (row count, returned rows, or INSERT/UPDATE acks)." and "in the format a psql terminal would print." UAT: raw SQL only, no format guidance.
- Required-element naming: **N** — V2 provides different SQL content (CREATE TABLE preamble, different INSERT values) but does not explicitly name assertion-checked strings in a directive manner. The assertion elements ("hello portal"-style equivalents) emerge from the SQL content, not from V2 naming them.
- Algorithm prescription: **N** — No algorithm prescribed. Both are SQL execution tasks.

**Verdict**: MIXED

**Notes**: V2 adds explicit REPL format instructions that UAT omitted. UAT P-D14's `model_slug: "sqlterminal"` likely carried a system prompt setting REPL context, but the user-facing prompt had no format guidance. V2
