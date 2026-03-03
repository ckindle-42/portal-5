# Portal 5.0 — Open WebUI Enhancement Layer

Portal 5.0 is an intelligent routing and extension layer that works *on top of*
Open WebUI rather than duplicating its functionality.

## Architecture

- **Open WebUI**: The full web interface, auth, RAG, knowledge base, and tool system
- **Portal Pipeline**: Config-driven intelligent router (selects Ollama/vLLM backends)
- **Portal MCP Servers**: Tool servers for document generation, video, audio, TTS
- **Portal Channels**: Thin Telegram/Slack adapters that call the Pipeline API

## Quick Start

```bash
# Clone and enter project
git clone <repo> portal-5
cd portal-5

# Start the stack
./launch.sh up

# Open WebUI available at http://localhost:8080
# Portal Pipeline API at http://localhost:9099
```

## Workspace Routing

The Pipeline exposes 10 workspace models:

| Workspace | Purpose |
|-----------|---------|
| `auto` | Smart routing based on request context |
| `auto-coding` | Software development tasks |
| `auto-document` | Document creation |
| `auto-security` | Security analysis |
| `auto-images` | Image generation |
| `auto-creative` | Creative writing |
| `auto-documents` | Office document generation (Word/Excel/PowerPoint) |
| `auto-video` | Video generation via ComfyUI |
| `auto-music` | Music/audio generation |
| `auto-research` | Web research |

## Configuration

Edit `config/backends.yaml` to add/remove backends:

```yaml
backends:
  - id: local-ollama
    type: ollama
    url: http://host.docker.internal:11434
    group: general
    models: [dolphin-llama3:8b]
```

## Scaling to Cluster

See [docs/CLUSTER_SCALE.md](docs/CLUSTER_SCALE.md) for scaling from single-node
to multi-node Mac Studio cluster.

## License

MIT
