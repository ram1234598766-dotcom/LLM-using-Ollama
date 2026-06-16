# 🤖 LocalAI — Local LLM + Live Web Knowledge

A fully local, self-updating AI assistant for **Windows 11 + PyCharm**.  
**No API key required. No cloud. Completely private.**

---

## ⚡ Quick Start

```bash
# Step 1 — Run the one-click setup (first time only)
setup_windows.bat

# Step 2 — Start chatting
python main.py
```

---

## 🏗️ Architecture

```
You (chat)
    │
    ▼
┌──────────────────────────────────────────┐
│               main.py                    │
│         Chat Loop + Memory               │
└──────────┬───────────────────────────────┘
           │
     ┌─────┴────────────────────────────┐
     │                                  │
     ▼                                  ▼
┌────────────────┐              ┌────────────────────┐
│  web_collector │              │   knowledge_base   │
│                │              │                    │
│ • DuckDuckGo   │──► adds to ►│ • ChromaDB (local) │
│ • Wikipedia    │              │ • Sentence-BERT    │
│ • RSS Feeds    │              │   embeddings       │
│ • Web scraping │              │ • Semantic search  │
└────────────────┘              └────────┬───────────┘
                                         │
                               RAG context injected
                                         │
                                         ▼
                               ┌─────────────────────┐
                               │     llm_engine      │
                               │                     │
                               │ Ollama (local)      │
                               │ • Llama 3.2         │
                               │ • Mistral           │
                               │ • Phi-3             │
                               │ No API key needed   │
                               └─────────────────────┘
                                         │
┌─────────────────────┐                  │
│    auto_updater     │     ◄────────────┘
│                     │
│ Background daemon:  │
│ • News every 15m    │
│ • Topics every 30m  │
│ • Model check 12h   │
└─────────────────────┘
```

---

## 📁 Files

| File | Purpose |
|------|---------|
| `main.py` | Entry point, chat loop, conversation memory |
| `llm_engine.py` | Ollama LLM — streams Llama 3.2 locally |
| `knowledge_base.py` | ChromaDB vector store for RAG |
| `web_collector.py` | DuckDuckGo search + Wikipedia + RSS scraping |
| `auto_updater.py` | Background scheduler — keeps knowledge fresh |
| `config.py` | All settings in one place |
| `requirements.txt` | Python dependencies |
| `setup_windows.bat` | One-click Windows 11 installer |

---

## 💬 Chat Commands

| Command | Action |
|---------|--------|
| `/update <topic>` | Force-fetch latest web data on a topic |
| `/stats` | Show knowledge base + updater status |
| `/search <query>` | Search the local knowledge base directly |
| `/clear` | Clear conversation history |
| `/model` | Show current LLM model info |
| `/help` | Show all commands |
| `/exit` | Quit |

---

## 🔧 Configuration (`config.py`)

| Setting | Default | Description |
|---------|---------|-------------|
| `OLLAMA_MODEL` | `llama3.2` | Primary model (2GB, fast) |
| `AUTO_UPDATE_INTERVAL_MIN` | `30` | Knowledge refresh interval |
| `NEWS_FETCH_INTERVAL_MIN` | `15` | RSS news fetch interval |
| `MAX_HISTORY_TURNS` | `20` | Conversation memory length |
| `TOP_K_RESULTS` | `5` | RAG documents per query |

**Want a more capable (but slower) model?** Change in `config.py`:
```python
OLLAMA_MODEL = "llama3.1:8b"   # better reasoning, needs ~8GB RAM
# or
OLLAMA_MODEL = "mistral"        # great for coding, ~4GB RAM
```

---

## 📋 Requirements

- **OS:** Windows 11
- **RAM:** 4 GB minimum (8 GB recommended)
- **Disk:** ~5 GB for model + dependencies
- **Python:** 3.11+
- **Ollama:** Installed by `setup_windows.bat`

---

## 🔒 Privacy

All data stays on your machine:
- The LLM runs locally via Ollama (no cloud calls)
- ChromaDB stores vectors on your disk (`data/chromadb/`)
- Web searches use DuckDuckGo (no account required)
- No telemetry, no API keys, no data sent to Anthropic or OpenAI

---

## 🚀 PyCharm Setup

1. **Open project:** `File → Open → select this folder`
2. **Set interpreter:** `File → Settings → Project → Python Interpreter → Add Local Interpreter`
3. **Install packages:** Open terminal in PyCharm → `pip install -r requirements.txt`
4. **Run:** Right-click `main.py` → `Run 'main'`
