# LIFEE - Debate-Driven AI Decision Assistant

Google Hackathon 2025 Project

## Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Choose an LLM Provider

Multiple LLM providers are supported. Edit the `.env` file to select one:

| Provider | Free Tier | Description |
|----------|-----------|-------------|
| **Gemini** | Free | Google AI, recommended |
| **Qwen** | 2000 calls/day | Alibaba Tongyi Qianwen DashScope API |
| **Qwen Portal** | 2000 calls/day | Via clawdbot OAuth login |
| **Ollama** | Completely free | Local inference, requires Ollama installed |
| **OpenCode** | From $20 | Requires payment method |
| **Claude** | Paid | Anthropic Claude API |

### 3. Configuration

Copy the example config:

```bash
cp .env.example .env
```

Edit `.env` to set your Provider and API Key:

```bash
# Select Provider
LLM_PROVIDER=gemini

# Gemini (recommended)
GOOGLE_API_KEY=your-api-key

# Or Qwen
# LLM_PROVIDER=qwen
# QWEN_API_KEY=your-api-key

# Or Ollama (local)
# LLM_PROVIDER=ollama
# ollama pull qwen2.5
```

### 4. Start a Conversation

```bash
python -m lifee.main
```

On first run, you'll be prompted to choose a specific model.

### 5. Commands

```
/help    - Show help
/history - Show conversation history
/clear   - Clear conversation history
/role    - Switch role
/model   - Switch model
/memory  - View knowledge base status
/quit    - Exit
```

## Role System

LIFEE supports custom AI roles, each with a unique personality and optional knowledge base.

### Directory Structure

```
lifee/roles/
└── <role_name>/
    ├── SOUL.md           # Core personality (required)
    ├── IDENTITY.md       # Identity metadata (optional)
    ├── skills/           # Role-specific skills (optional)
    │   └── *.md          # trigger: always = core skill, trigger: [keywords] = triggered skill
    └── knowledge/        # Role-specific knowledge base (optional)
        └── *.md
```

### File Reference

| File | Purpose |
|------|---------|
| `SOUL.md` | Defines core personality, values, speaking style, behavioral boundaries |
| `IDENTITY.md` | Name, emoji, and other display metadata |
| `skills/` | Skill files that shape role behavior — always-on or triggered by context |
| `knowledge/` | Markdown/text files, auto-indexed, injected via semantic search during conversations |

## Skill System

LIFEE implements a tiered skill loading system inspired by Claude Code's skills architecture:

### Tier 1: Core Skills (Always-On)

Skills with `trigger: always` are injected into the system prompt at all times. Use for fundamental behavioral guidelines.

```markdown
---
name: psychoanalysis
description: Core psychoanalytic framework
trigger: always
---

## Analytic Framework

1. Listen for slips, repetitions, and hesitations
2. ...
```

### Tier 2: Triggered Skills (RAG-Activated)

Skills with `trigger: [keyword1, keyword2]` are loaded only when RAG search results match the specified keywords. This keeps the prompt lightweight while providing deep knowledge on demand.

```markdown
---
name: dream-analysis
description: Techniques for interpreting dreams
trigger: [dream, nightmare, sleep, unconscious imagery]
---

## Dream Interpretation Framework
...
```

### Skill File Format

Each skill is a `.md` file with optional YAML frontmatter:

| Field | Required | Description |
|-------|----------|-------------|
| `name` | No | Skill name (defaults to filename) |
| `description` | Recommended | Brief description of the skill |
| `trigger` | No | `always` for Tier 1, or list of keywords for Tier 2 (default: `always`) |

### How Tiered Loading Works

```
System Prompt composition:
┌──────────────────────────┐
│ SOUL.md (personality)    │
│ IDENTITY.md (identity)   │
│ Tier 1 Skills (always)   │  ← always loaded
├──────────────────────────┤
│ Tier 2 Skills (triggered)│  ← loaded only when RAG results match keywords
├──────────────────────────┤
│ User Memory              │
│ Debate Context           │
│ RAG Knowledge Base       │
└──────────────────────────┘
```

## Knowledge Base

The knowledge base allows AI roles to answer based on role-specific documents (books, articles, etc.) rather than generic knowledge.

### How It Works

```
1. Indexing (first run)
   Documents → Chunking (~400 tokens/chunk) → Embedding (Gemini API) → Stored in knowledge.db

2. Conversation
   User input → Query embedding → Search most similar chunks → Inject into system prompt → AI responds
```

**knowledge.db Schema (SQLite):**

| Table | Content |
|-------|---------|
| `files` | Indexed file list (path, hash, modification time) |
| `chunks` | Text chunks + embedding vectors (3072 dimensions) |
| `chunks_fts` | Full-text search index (FTS5, for keyword matching) |

**Search Algorithm:** Hybrid search = 70% vector similarity + 30% keyword matching (BM25)

### Building a Knowledge Base for Your Role

**Step 1: Prepare documents**

Create a `knowledge/` folder under your role directory and add `.md` or `.txt` files:

```
lifee/roles/your_role/
├── SOUL.md
├── IDENTITY.md
├── skills/
│   └── your_skill.md
└── knowledge/
    ├── book1.txt
    ├── book2.txt
    └── notes.md
```

**Step 2: Run the program**

```bash
python -m lifee.main
# Select your role — indexing happens automatically
# Progress: Indexing knowledge base: 1/5 ... 5/5
```

First-time indexing calls the Gemini Embedding API, ~5-10 seconds per file.

**Step 3: Test search**

```
/memory              # View knowledge base status
/memory search query # Test search results
```

### Knowledge Base Best Practices

1. **Text format**: Plain text works best. PDF/EPUB must be extracted first (see `tools/extract_books.py`)
2. **Chunk size**: Default 400 tokens, suitable for most cases
3. **File naming**: Use meaningful filenames — search results show the source
4. **Pre-built databases**: The repo includes pre-built `knowledge.db` files for teammates to use immediately
5. **Re-indexing**: After adding new documents, delete `knowledge.db` and re-run

## Creating a New Role

1. Create a directory under `lifee/roles/`, e.g. `lifee/roles/stoic/`
2. Write `SOUL.md` to define the personality
3. (Optional) Add `IDENTITY.md`
4. (Optional) Add skill files in `skills/`
5. (Optional) Add knowledge documents in `knowledge/`
6. Run the program and use `/role` to switch

## Supported Models

### Gemini
- `gemini-3-flash-preview` - Gemini 3 Fast
- `gemini-3-pro-preview` - Gemini 3 Most Capable
- `gemini-2.5-pro` - 2.5 Most Capable
- `gemini-2.5-flash` - 2.5 Fast
- `gemini-2.0-flash` - 2.0 Recommended

### Qwen
- `qwen-plus` - Enhanced general-purpose
- `qwen-turbo` - Fast
- `qwen-max` - Most capable

### Ollama
- `qwen2.5:latest` - Recommended
- `llama3.3:latest`
- `deepseek-r1:latest`

## Project Structure

```
lifee/
├── config/         # Configuration management
├── providers/      # LLM providers (Claude, Gemini, Qwen, Ollama...)
├── sessions/       # Session management
├── roles/          # Role system
│   └── <role>/
│       ├── SOUL.md
│       ├── IDENTITY.md
│       ├── skills/
│       └── knowledge/
├── memory/         # Knowledge base / RAG
│   ├── manager.py      # Index management
│   ├── embeddings.py   # Embedding providers (Gemini/OpenAI)
│   ├── search.py       # Hybrid search (vector + keyword)
│   ├── chunker.py      # Document chunking
│   └── user_memory.py  # Cross-session user memory
├── debate/         # Multi-agent debate
│   ├── moderator.py    # Debate moderator (flow control)
│   ├── participant.py  # Participant (per-role LLM calls)
│   ├── context.py      # Debate context (multi-agent awareness)
│   └── suggestions.py  # Reply suggestions
└── main.py         # CLI entry point
```

## Multi-Perspective Discussion Mode

LIFEE supports multiple AI roles participating in a discussion simultaneously, exploring questions from different perspectives.

### Start a Discussion

```bash
python -m lifee.main
# Type /debate to enter multi-perspective discussion mode
```

### Discussion Commands

```
/quit     - Exit discussion
/clear    - Clear current discussion history
/history  - View full discussion history
/sessions - View and restore historical sessions
```

### Session Management

- **Auto-save**: Automatically saved after each turn to `~/.lifee/sessions/current.json`
- **Auto-restore**: Option to continue previous discussion on startup
- **History**: Browse and restore any historical session
- **24-hour expiry**: Sessions older than 24 hours are automatically archived

### User Memory

LIFEE automatically remembers user information (name, preferences, etc.), stored in `~/.lifee/memory/USER.md`.

## Development Progress

- [x] Phase 1: Basic conversation
- [x] Multi LLM Provider support
- [x] Phase 2: Role system
- [x] Phase 3: Knowledge base / RAG
- [x] Phase 4: Multi-agent debate
- [x] Phase 5: Session persistence + User memory
- [x] Phase 6: Tiered skill loading system
