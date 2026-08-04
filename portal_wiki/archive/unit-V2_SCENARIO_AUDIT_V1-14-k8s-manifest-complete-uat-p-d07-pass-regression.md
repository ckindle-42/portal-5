---
id: unit-V2_SCENARIO_AUDIT_V1-14-k8s-manifest-complete-uat-p-d07-pass-regression
kind: why
title: "V2_SCENARIO_AUDIT_V1 \u2014 14. `k8s-manifest-complete` (UAT P-D07 \u2014\
  \ PASS regression guard)"
sources:
- type: design
  path: docs/V2_SCENARIO_AUDIT_V1.md
  section: "14. `k8s-manifest-complete` (UAT P-D07 \u2014 PASS regression guard)"
last_generated_commit: ''
confidence: high
tags:
- docs
- V2_SCENARIO_AUDIT_V1
created_at: 1783195000.926222
updated_at: 1783195000.926222
---


**UAT P-D07 status**: PASS with Laguna
**V2 Laguna result**: PASS

**UAT prompt** (verbatim from line 3377):
> Generate a Kubernetes Deployment manifest for a Python FastAPI app. Image: ghcr.io/myorg/api:v1.2.3, port 8000, 2 replicas, readiness probe on /health, resource limits 512Mi/0.5CPU.

**V2 prompt** (verbatim from coding_scenarios.yaml):
> Provide a complete Kubernetes manifest (Deployment + Service) for
> a Python web service with these requirements:
>   - image: myorg/webapp pinned to tag v1.2.3
>   - readiness probe on /health
>   - resource limits: 512Mi memory, 0.5 CPU
>   - 3 replicas
>   - rolling update strategy
>   - includes a `kubectl rollout undo` command in a comment for
>     rollback reference
>
> Single fenced code block. Complete YAML, no placeholders.

**Verdict**: NO COMPARISON

**Notes**: UAT PASS regression guard. UAT asks for a Deployment; V2 asks for Deployment + Service (broader scope). UAT specifies 2 replicas, V2 specifies 3. V2 adds rolling update and rollback comment requirements. V2's "Single fenced code block" directive is an output-format prescription that UAT lacks, but since this is a PASS regression guard (the original test passed), the format prescription doesn't rescue a failure — it's a different task framing. The core requirements (image pin, readiness probe, resource limits) are present in both.

---
