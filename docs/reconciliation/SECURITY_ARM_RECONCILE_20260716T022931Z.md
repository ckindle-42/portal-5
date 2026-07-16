# Security-Arm Reconciliation Report

- ollama models discovered: 157
- fleet UP: 20 / start-needed: 0

## Models (bench-reachable)
- keep (pulled): 6
- pull-then-keep: 1
  - REMAP-if-pull-fails `hf.co/mradermacher/VulnLLM-R-7B-GGUF:Q4_K_M-ctx8k` -> `hf.co/mradermacher/VulnLLM-R-7B-GGUF:q4_K_M-ctx8k`
- non-bench hints (report only): 77

## Targets
- active: ['vulhub-log4shell-solr', 'vulhub-tomcat-manager', 'vulhub-redis-rce', 'vulhub-nginx-lfi']
- ip-set: []
- aspirational (gated): ['pb-phpipam-lfi', 'pb-myvesta-rce', 'ptai-webapp-twin']

## Challenges
- active: 0
- aspirational (gated): 80

## Fleet
- UP: ['portal-comfyui', 'portal-video', 'portal-music', 'portal-documents', 'portal-sandbox', 'portal-whisper', 'portal-tts', 'portal-security', 'portal-memory', 'portal-rag', 'portal-research', 'portal-browser', 'portal-mlx-transcribe', 'portal-reranker', 'portal-cad-render', 'portal-proxmox', 'portal-pipeline', 'portal-mitre', 'portal-detections', 'portal-wiki']
- start-needed: []