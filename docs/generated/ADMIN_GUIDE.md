<!-- GENERATED FROM portal_wiki/canonical/ — edit the source unit, not this file -->

# Portal 5 Admin Guide

*Deterministic projection of 733 canonical units.*

## Architecture Overview

### ADMIN_GUIDE — Add a Cluster Node
*Source: config/backends.yaml*

Cluster scaling is a config-only operation. Adding a node means appending a backend entry to `config/backends.yaml`: a unique `id`, a `type` (`ollama` or `openai_compatible`), the node's `url`, the routing `group`, and the model list it serves. The pipeline discovers new backends through `BackendRegistry` at startup and the auto-routing layer load-balances across healthy backends. After editing, restart the pipeline container so the registry re-reads the file.

### ADMIN_GUIDE — Alternative: LAN reverse proxy (Caddy / nginx)
*Source: deploy/portal-5/docker-compose.yml*

For deployments that skip Cloudflare Tunnel, a Caddy or nginx proxy on the same host plays the same role: proxy Open WebUI on `:8080`, set `PORTAL_PUBLIC_URL` to the proxy's public address and `OWUI_API_KEY` to an Open WebUI `sk-` key. Generated files then come back as `${PORTAL_PUBLIC_URL}/api/v1/files/{id}/content/{name}` on `:8080` — the same one-port story as the tunnel.

### ADMIN_GUIDE — Approve Pending Users
*Source: .env.example*

Self-registration arrives with the `pending` role because `DEFAULT_USER_ROLE=pending` in `.env.example` is the shipped default, and a pending account has no access until an admin promotes it. Two promotion paths exist. The web path is Open WebUI's Admin Panel > Users: locate the pending account and change its role to `user`. The CLI path is `./launch.sh add-user <email> [name] [role]` with an explicit `pending` role, whose role values scripts/lib/users.sh documents as `user | admin | pending`.

### ADMIN_GUIDE — Backup
*Source: scripts/lib/backup.sh*

`./launch.sh backup [output-dir]` writes a timestamped directory (default under `./backups/`) via `_launch_backup` in scripts/lib/backup.sh. It tars the `portal-5_open-webui-data` volume into `openwebui-data.tar.gz` (accounts, chats, settings), tars `portal-5_grafana-data` into `grafana-data.tar.gz`, and copies `.env`, `config/`, and `imports/` alongside. Ollama weights in `portal-5_ollama-models` are intentionally excluded — they are re-pullable.

### ADMIN_GUIDE — Changing the Router Model
*Source: .env.example*

The router model is chosen through `.env`: `LLM_ROUTER_MODEL` (default `hf.co/mradermacher/gemma-4-E4B-it-OBLITERATED-GGUF:Q4_K_M`), `LLM_ROUTER_TIMEOUT_MS` (1000 for the primary, 500 for standby/fallback), plus `LLM_ROUTER_CONFIDENCE_THRESHOLD` and `LLM_ROUTER_ENABLED`. routing.py reads these into `_LLM_ROUTER_MODEL` and `_LLM_ROUTER_TIMEOUT_MS` at startup, and lifespan.py's `_warmup_llm_router` pre-loads the configured model with `keep_alive: -1`.

### ADMIN_GUIDE — Check pipeline logs for router decisions
*Source: launch.sh*

Router decisions are logged by the pipeline. The LLM layer logs each confident classification from `_route_with_llm` in routing.py as `LLM router: '<text>' → workspace='<id>' confidence=<n>`, and every timeout, low-confidence result, or error logs "falling back to keywords". The dispatch layer logs `Routing workspace=<id>` in handlers.py when a request is sent to a backend.

### ADMIN_GUIDE — Check which models Ollama currently has loaded
*Source: portal/platform/mcp_host/pipeline_mcp.py*

Ollama reports resident models through its `/api/ps` endpoint. The shell check is:

### ADMIN_GUIDE — Create Users via CLI
*Source: scripts/lib/users.sh*

`./launch.sh add-user <email> [name] [role]` invokes `_launch_add_user` in scripts/lib/users.sh, which signs in as the admin via `get_admin_token` (scripts/lib/util.sh), POSTs to Open WebUI's `/api/v1/auths/add`, and prints the generated temporary password once. Roles are `user` (default), `admin`, and `pending`. `./launch.sh list-users` calls `_launch_list_users`, GETs `/api/v1/users/`, and prints `[role] name <email>` per account. Both commands fail loudly when the stack is down.

### ADMIN_GUIDE — First Login
*Source: scripts/lib/util.sh*

`./launch.sh up` creates `.env` from `.env.example` if absent, then `bootstrap_secrets` in scripts/lib/util.sh replaces every `CHANGEME` placeholder, printing a credentials box with the admin email and the generated `OPENWEBUI_ADMIN_PASSWORD` to the console. The account is `OPENWEBUI_ADMIN_EMAIL` (default `admin@portal.local`) and the password is written into `.env` for later retrieval. Log in at `http://localhost:8080`, or at the hostname printed when `ENABLE_REMOTE_ACCESS=true`.

### ADMIN_GUIDE — How the LLM Router Works
*Source: portal/platform/inference/router/routing.py*

Every `auto` request goes through two layers in routing.py. Layer 1 `_route_with_llm` sends the last user message to Ollama `/api/generate` with `format: _ROUTER_JSON_SCHEMA` — grammar-enforced JSON returning `{"workspace": ..., "confidence": ...}` — and accepts the result only when confidence is at least `LLM_ROUTER_CONFIDENCE_THRESHOLD`. Layer 2 `_detect_workspace` runs weighted keyword scoring over `_WORKSPACE_ROUTING` and fires on timeout, low confidence, or error.

## Components

- **10 security canonical variants**: 1 source(s)
- **135 personas**: 6 source(s)
- **137 MCP tools across 33 servers**: 1 source(s)
- **246 model ids, 7 backend groups**: 1 source(s)
- **25 production + 53 eval workspaces**: 1 source(s)
- **33 MCP fleet servers**: 1 source(s)
- **4/23 docs migrated (17.4%)**: 1 source(s)
- **ADMIN_GUIDE — Debugging crashes**: 3 source(s)
- **ADMIN_GUIDE — Pull Additional Models**: 3 source(s)
- **AGENT_LOOP — Agent Loop (platform core)**: 9 source(s)
- **AGENT_LOOP — Consumers**: 5 source(s)
- **AGENT_LOOP — Contracts (the "key" modules implement)**: 2 source(s)
- **AGENT_LOOP — Discipline (borrowed from the Campaign Supervisor)**: 2 source(s)
- **AGENT_LOOP — Operator surface**: 1 source(s)
- **AGENT_LOOP — Record path (writing enabled, CI-gated)**: 2 source(s)

---
*733 knowledge units referenced.*