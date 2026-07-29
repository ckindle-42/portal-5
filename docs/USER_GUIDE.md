# Portal 5 — User Guide

## Getting Access

<!-- WIKI:GENERATED unit=unit-user-guide-getting-access -->
Portal 5 requires an account. Contact your admin or sign up at the login page.
New accounts require admin approval — you'll see "pending" status until approved.
<!-- /WIKI:GENERATED -->

---

## Workspaces

<!-- WIKI:GENERATED unit=unit-user-guide-workspaces -->
Select your workspace from the model dropdown in the top bar. Each workspace
routes your request to the best-suited AI model for that task.

| Workspace | Best for |
|---|---|
| 🤖 Portal Auto Router | Not sure which to use — routes automatically |
| 💻 Portal Code Expert | Writing code, debugging, code review |
| ⚡ Portal Agentic Coder (Heavy) | Long-horizon multi-file agentic coding (Qwen3-Coder-Next 80B) |
| 🔒 Portal Security Analyst | Security questions, hardening guidance |
| 🔴 Portal Red Team | Offensive security, penetration testing |
| 🔵 Portal Blue Team | Incident response, threat detection, defense |
| ✍️ Portal Creative Writer | Stories, scripts, creative content |
| 🧠 Portal Deep Reasoner | Complex analysis, long reasoning chains |
| 🏛️ Portal Council Review | Evidence-backed review of decisions, plans, proposals, and policies |
| 📄 Portal Document Builder | Create Word/Excel/PowerPoint files |
| 🎬 Portal Video Creator | Shelved; hidden from the model dropdown and not currently in operation |
| 🎵 Portal Music Producer | Generate music and audio |
| 🔍 Portal Research Assistant | Research and information synthesis |
| 👁️ Portal Vision | Image analysis, visual tasks |
| 📊 Portal Data Analyst | Data analysis, statistics |
| 🔍 Portal SPL Engineer | Splunk SPL queries and detection searches |
| ⚖️ Portal Compliance Analyst | NERC CIP gap analysis, policy review, audit prep |
| 🧪 Portal Mistral Reasoner | Structured reasoning, strategic planning |

Council Review is opt-in because it runs three isolated reviewers and a final
synthesizer. Give it the goal, constraints, available evidence, and options or
artifact to review. It returns a code-determined recommendation, reviewer
participation, dissent, missing evidence, and next actions. A reviewer that
abstains or returns an invalid response does not silently shrink the quorum.
<!-- /WIKI:GENERATED -->

---

## Personas

<!-- WIKI:GENERATED unit=unit-user-guide-personas -->
Personas are pre-configured specialists. Access them in the model dropdown alongside
workspaces. Examples: `Cyber Security Specialist`, `Python Code Generator`, `Red Team Operator`.
<!-- /WIKI:GENERATED -->

---

## Tools (MCP Servers)

<!-- WIKI:GENERATED unit=unit-user-guide-tools-mcp-servers -->
In a chat, click the **+** icon to enable tools:
- **Portal Documents** — generate Word, Excel, PowerPoint files
- **Portal Code** — execute code in an isolated sandbox
- **Portal TTS** — convert text to speech
- **Portal Whisper** — transcribe audio files (with speaker diarization on Apple Silicon)
- **Portal ComfyUI** — generate or edit images with the installed Qwen-Image models
- **Portal Music** — generate audio clips via MusicGen
<!-- /WIKI:GENERATED -->

---

## Knowledge Base & Document RAG

<!-- WIKI:GENERATED unit=unit-user-guide-knowledge-base-document-rag -->
Portal 5 has full RAG (Retrieval-Augmented Generation) built in via Open WebUI.
You can upload documents and have conversations grounded in their content.
<!-- /WIKI:GENERATED -->

---

### Uploading Documents

<!-- WIKI:GENERATED unit=unit-user-guide-uploading-documents -->
1. Open the chat interface at http://localhost:8080
2. Click the **+** (paperclip) icon in the chat input area
3. Upload PDF, DOCX, TXT, Markdown, or other supported formats
4. The document is automatically chunked, embedded with `nomic-embed-text`, and indexed

For a persistent document library accessible across all chats:
1. Go to **Workspace → Knowledge** in the left sidebar
2. Click **+ New Collection** and give it a name (e.g., "Company Policies")
3. Upload documents to the collection
4. In any chat, type `#` to reference the collection
<!-- /WIKI:GENERATED -->

---

### Supported Formats

<!-- WIKI:GENERATED unit=unit-user-guide-supported-formats -->
PDF (with image extraction), DOCX, TXT, Markdown, CSV, HTML, and more.
PDF image content is extracted automatically (`PDF_EXTRACT_IMAGES=true`).
<!-- /WIKI:GENERATED -->

---

### How It Works

<!-- WIKI:GENERATED unit=unit-user-guide-how-it-works -->
Documents are split into 1500-character chunks with 100-character overlap, then
embedded using `nomic-embed-text` running locally in Ollama. Search uses hybrid
mode (semantic + keyword) for best results. No document content leaves your machine.
<!-- /WIKI:GENERATED -->

---

### Cross-Session Memory

<!-- WIKI:GENERATED unit=unit-user-guide-cross-session-memory -->
Portal 5 also has **persistent memory** across conversations. When you share
facts with the AI (e.g., "I'm working on a Python project"), it remembers them
in future sessions. Memory is stored and indexed with the same embedding model.

To view or edit memories: **Settings → Personalization → Memory**
<!-- /WIKI:GENERATED -->

---

## Tips

<!-- WIKI:GENERATED unit=unit-user-guide-tips -->
- Use **Ctrl+Shift+C** to copy code blocks
- Attach files with the paperclip icon for document analysis
- Use `#` to reference knowledge bases
- Long reasoning tasks (Deep Reasoner) may take 60-90 seconds — be patient
<!-- /WIKI:GENERATED -->

---
