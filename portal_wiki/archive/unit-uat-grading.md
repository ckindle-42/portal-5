---
id: unit-uat-grading
kind: mixed
title: "UAT grading \u2014 format + response validators"
sources:
- type: code
  path: tests/uat/grading.py
  commit: 85bb65bd
last_generated_commit: 85bb65bd
claims: []
confidence: high
tags:
- authored-v1
- tests
- uat
created_at: 1785799311.958262
updated_at: 1785799311.958262
---

The grading logic: response validators and the heavy format validators (docx, xlsx, pptx, wav, png, mp4) that check an artifact is a real file of the right kind.

## Why

A UAT section that asked for a document and got text is a failure even if the model answered, and the grading module is what detects that — validating the artifact's actual format rather than trusting the response. The heavy validators keep their inline imports so a section that never produces that format does not pay the import cost.

## Interfaces

The response validators and the format validators.

## Gotchas

The heavy format validators import lazily — a grading call for an absent format must not crash the run.
