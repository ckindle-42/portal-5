# Portal 5 — Open WebUI Enhancement Layer

An intelligent routing and extension layer that runs on top of Open WebUI,
providing a complete local AI platform: text, code, security, images, video,
music, documents, and voice — all on your hardware, all private.

## Quick Start

```bash
git clone https://github.com/ckindle-42/portal-5.git
cd portal-5
./launch.sh up
```

On first run, Portal 5:
- Auto-generates secure secrets (printed to console — save them)
- Pulls core Ollama models (~4GB)
- Downloads FLUX.1-schnell for image generation (~12GB)
- Seeds Open WebUI with all 13 workspaces, 35 personas, and 7 MCP tools

**Web UI:** http://localhost:8080
**Metrics:** http://localhost:3000 (Grafana)

To pull all specialized models (security, coding, reasoning):
```bash
./launch.sh pull-models   # 30-90 minutes
```

## Workspaces (13 total)

| Workspace ID | Display Name | Purpose |
|---|---|---|
| `auto` | 🤖 Portal Auto Router | Intelligently routes to the best model for your task |
| `auto-coding` | 💻 Portal Code Expert | Code generation, debugging, architecture review |
| `auto-security` | 🔒 Portal Security Analyst | Security analysis, hardening, vulnerability assessment |
| `auto-redteam` | 🔴 Portal Red Team | Offensive security, penetration testing, exploit research |
| `auto-blueteam` | 🔵 Portal Blue Team | Defensive security, incident response, threat hunting |
| `auto-creative` | ✍️  Portal Creative Writer | Creative writing, storytelling, content generation |
| `auto-reasoning` | 🧠 Portal Deep Reasoner | Complex analysis, research synthesis, step-by-step reasoning |
| `auto-documents` | 📄 Portal Document Builder | Create Word, Excel, PowerPoint via MCP tools |
| `auto-video` | 🎬 Portal Video Creator | Generate videos via ComfyUI / Wan2.2 |
| `auto-music` | 🎵 Portal Music Producer | Generate music and audio via AudioCraft/MusicGen |
| `auto-research` | 🔍 Portal Research Assistant | Web research, information synthesis, fact-checking |
| `auto-vision` | 👁️  Portal Vision | Image understanding, visual analysis, multimodal tasks |
| `auto-data` | 📊 Portal Data Analyst | Data analysis, statistics, visualization guidance |

## Architecture

```
Open WebUI :8080  →  Portal Pipeline :9099  →  Ollama :11434
                 ↘  SearXNG :8088 (web search)
                 ↘  ComfyUI :8188 (images/video)
                 ↘  MCP Servers :8910-8916 (tools)
                 ↘  Prometheus :9090 / Grafana :3000 (metrics)
```

## User Management

```bash
./launch.sh add-user alice@team.local "Alice Smith"
./launch.sh list-users
```

## Model Management

```bash
./launch.sh pull-models    # Pull all specialized models
./launch.sh status         # Show service health
```

## Documentation

- [User Guide](docs/USER_GUIDE.md)
- [Admin Guide](docs/ADMIN_GUIDE.md)
- [ComfyUI Setup](docs/COMFYUI_SETUP.md)
- [Cluster Scaling](docs/CLUSTER_SCALE.md)
- [Backup & Restore](docs/BACKUP_RESTORE.md)
- [Known Issues](KNOWN_ISSUES.md)

## License

MIT