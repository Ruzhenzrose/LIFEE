# LIFEE - Let Them Argue, You Decide

AI-powered multi-perspective decision assistant. Multiple AI personas debate your life questions from different angles, helping you think through decisions.

Google Hackathon 2025 Project

## Two Ways to Use

| | Web Demo | CLI |
|---|---------|-----|
| **Setup** | Open `index.html` in browser | `pip install -r requirements.txt` |
| **Backend** | Supabase + Cloudflare Workers | Local Python + LLM API |
| **Features** | Full UI, community, persona builder | Terminal-based, knowledge base, skills |
| **Best for** | Quick start, sharing | Deep customization, local roles |

---

## Web Demo

A standalone single-page app — no server required, just open `index.html`.

### Features

- **Multi-persona debate**: Select 2+ AI personas to discuss your question from different perspectives
- **8+ built-in personas**: Krishnamurti, Lacan, Audrey Hepburn, The Entrepreneur, The Positive Psychologist, etc.
- **Custom personas**: Create your own advisors with custom avatars and personality
- **Chat history**: Auto-saved, exportable, shareable to community
- **Community**: Browse shared conversations and personas
- **Account system**: Sign up / sign in via Supabase auth

### Tech Stack

- React 18 (CDN, no build step)
- Tailwind CSS
- Supabase (auth, database, storage)
- LIFEE API on Cloudflare Workers (LLM calls)

---

## CLI

### Quick Start

```bash
pip install -r requirements.txt
python -m lifee.main
```

On first run, you'll be prompted to choose an LLM provider and model.

### Supported Providers

| Provider | Free Tier | Description |
|----------|-----------|-------------|
| **Gemini** | Free | Google AI, recommended |
| **Qwen** | 2000 calls/day | Alibaba Tongyi Qianwen |
| **Ollama** | Completely free | Local inference |
| **OpenCode** | Free (Big Pickle) | GLM-4.7 |
| **Claude** | Paid | Anthropic Claude API |

### How It Works

```
Main Menu → Select Roles → Conversation Loop
    ↑                            ↓
    └────────── /menu ───────────┘
```

1. **Main menu**: Continue last session, start new conversation, browse history, or change settings
2. **Role selection**: Pick 1 or more AI personas (checkbox UI with arrow keys)
3. **Conversation**: AI responds in character, suggestion menu after each round
4. **`/menu`** returns to main menu, **`/quit`** exits

### Commands

```
/help     - Show help
/history  - Show conversation history
/clear    - Clear conversation history
/sessions - Browse and restore historical sessions
/memory   - View knowledge base status
/config   - Switch LLM provider
/model    - Switch model
/menu     - Return to main menu
/quit     - Exit
```

### Session Management

- **Auto-save**: Every turn saved to `~/.lifee/sessions/current.json`
- **Auto-restore**: Main menu offers to continue previous session
- **History**: Browse and restore archived sessions
- **24-hour expiry**: Old sessions automatically archived
- **User memory**: Remembers user info across sessions (`~/.lifee/memory/USER.md`)

---

## Role System

Custom AI roles with unique personalities and optional knowledge bases.

### Directory Structure

```
lifee/roles/
└── <role_name>/
    ├── SOUL.md           # Core personality (required)
    ├── IDENTITY.md       # Name, emoji, metadata (optional)
    ├── skills/           # Behavioral skills (optional)
    │   └── *.md
    └── knowledge/        # Documents for RAG (optional)
        └── *.md
```

### Skill System (Three Tiers)

| Tier | Trigger | When Loaded |
|------|---------|-------------|
| **Tier 1** | `trigger: always` | Always in system prompt |
| **Tier 2** | `trigger: [keyword1, keyword2]` | When user input matches keywords |
| **Tier 3** | Knowledge base | RAG search on every turn |

Skill file format (`.md` with YAML frontmatter):

```markdown
---
name: dream-analysis
description: Techniques for interpreting dreams
trigger: [dream, nightmare, sleep]
---

## Dream Interpretation Framework
...
```

### Knowledge Base

Role-specific documents indexed for semantic search.

```
1. Indexing: Documents → Chunking (~400 tokens) → Embedding (Gemini API) → SQLite
2. Search:  User input → Embedding → Hybrid search (70% vector + 30% keyword) → Inject into prompt
```

Commands: `/memory` for status, `/memory search <query>` to test.

### Creating a New Role

1. Create directory: `lifee/roles/your_role/`
2. Write `SOUL.md` (personality)
3. Optionally add `IDENTITY.md`, `skills/`, `knowledge/`
4. Start the program — new role appears in selection menu

---

## Project Structure

```
lifee/
├── config/         # Configuration (.env)
├── providers/      # LLM providers (Gemini, Qwen, Ollama, Claude...)
├── sessions/       # Session persistence
├── roles/          # Role definitions
│   └── <role>/
│       ├── SOUL.md, IDENTITY.md
│       ├── skills/
│       └── knowledge/
├── memory/         # RAG + user memory
├── debate/         # Multi-agent conversation engine
│   ├── moderator.py    # Flow control, speaker rotation
│   ├── participant.py  # Per-role LLM calls + skill injection
│   ├── context.py      # Multi-agent awareness prompts
│   └── suggestions.py  # Reply suggestion generation
├── cli/            # Terminal UI
│   ├── app.py          # Main menu + entry point
│   ├── debate.py       # Unified conversation loop
│   └── setup.py        # Interactive selection UIs
└── main.py         # CLI entry point

web/
└── ui/             # Standalone web demo
    ├── index.html      # Single-page app
    ├── settings/       # Account management
    ├── my-chats/       # Chat history
    ├── my-personas/    # Persona management
    └── help/           # Quick guide
```

## Development Progress

- [x] Basic conversation + multi-provider support
- [x] Role system with SOUL/IDENTITY
- [x] Knowledge base (RAG with hybrid search)
- [x] Multi-agent debate with streaming
- [x] Session persistence + user memory
- [x] Tiered skill loading system
- [x] Unified flow (main menu + single conversation loop)
- [x] Web demo (React + Supabase)
