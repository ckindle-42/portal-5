# Portal 5.2 — Cluster Scale-Out Guide

Portal 5.1 is designed to grow from a single M4 Mac to a 12-node Mac Studio
cluster without any code changes. All scaling is done by editing config/backends.yaml.

## Stage 1 → Stage 2: Add a Second Mac Studio

1. Install Ollama on the new Mac Studio
2. Configure it to listen on the network:
   ```bash
   OLLAMA_HOST=0.0.0.0 ollama serve
   ```
3. Add to config/backends.yaml:
   ```yaml
   - id: ollama-node-2
     type: ollama
     url: "http://192.168.1.102:11434"
     group: general
     models: [dolphin-llama3:8b]
   ```
4. Restart the pipeline container:
   ```bash
   docker compose restart portal-pipeline
   ```

Portal automatically discovers the new backend and load-balances across both.

## Stage 3: vLLM for 70B Models

When ready to run 70B+ models (Llama 3.1 70B, etc.) via vLLM:

1. Install vLLM on the target machine
2. Start vLLM:
   ```bash
   vllm serve meta-llama/Llama-3.1-70B-Instruct --port 8000
   ```
3. Add to config/backends.yaml:
   ```yaml
   - id: vllm-70b
     type: openai_compatible
     url: "http://192.168.1.103:8000"
     group: general
     models: [meta-llama/Llama-3.1-70B-Instruct]
   ```

## Stage 4-5: Specialized Model Groups

Assign different machines to different workspace groups for optimal routing:

```yaml
- id: vllm-coding
  url: "http://192.168.1.104:8000"
  group: coding      # auto-coding workspace routes here first
  models: [Qwen/Qwen2.5-Coder-32B-Instruct]

- id: vllm-creative
  url: "http://192.168.1.105:8000"
  group: creative    # auto-creative routes here first
  models: [mistral-7b-instruct-abliterated]
```

Open WebUI, the MCP tools, and the Telegram/Slack channels all continue working
unchanged. The only edit is a YAML file.
