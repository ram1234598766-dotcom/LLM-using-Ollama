"""
config.py — Central configuration for LocalAI
"""

import os
from pathlib import Path

os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
os.environ.setdefault("TQDM_DISABLE", "1")

# ── Paths ───────────────────────────────────────────────────────────────────
BASE_DIR        = Path(__file__).parent
DB_DIR          = BASE_DIR / "data" / "chromadb"
LOGS_DIR        = BASE_DIR / "data" / "logs"
CACHE_DIR       = BASE_DIR / "data" / "cache"

for _d in [DB_DIR, LOGS_DIR, CACHE_DIR]:
    _d.mkdir(parents=True, exist_ok=True)

# ── Ollama (local LLM — no API key) ─────────────────────────────────────────
OLLAMA_BASE_URL  = "http://localhost:11434"
OLLAMA_MODEL     = "llama3.2"          # free, ~2GB, runs on most PCs
OLLAMA_FALLBACK  = "mistral"           # fallback if llama3.2 unavailable
LLM_TEMPERATURE  = 0.7
LLM_MAX_TOKENS   = 1024
LLM_CONTEXT_SIZE = 4096

# ── Embeddings (local sentence-transformer — no API key) ────────────────────
EMBED_MODEL      = "all-MiniLM-L6-v2"  # ~90MB, fast, accurate
EMBED_DIM        = 384

# ── Knowledge Base (ChromaDB) ───────────────────────────────────────────────
COLLECTION_NAME  = "localai_knowledge"
TOP_K_RESULTS    = 5                   # docs to retrieve per query
SIMILARITY_THRESHOLD = 0.4

# ── Web Data Collector ───────────────────────────────────────────────────────
MAX_SEARCH_RESULTS   = 8              # DuckDuckGo results per query
MAX_ARTICLE_CHARS    = 4000           # chars to extract per webpage
REQUEST_TIMEOUT      = 10            # seconds
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

# RSS news feeds (always fresh, no scraping needed)
RSS_FEEDS = [
    "https://feeds.bbci.co.uk/news/rss.xml",
    "https://rss.nytimes.com/services/xml/rss/nyt/Technology.xml",
    "https://feeds.arstechnica.com/arstechnica/technology-lab",
    "https://www.sciencedaily.com/rss/top.xml",
    "https://news.mit.edu/rss/research",
]

# ── Auto-Updater ─────────────────────────────────────────────────────────────
AUTO_UPDATE_INTERVAL_MIN  = 30    # update knowledge base every 30 min
MODEL_CHECK_INTERVAL_HRS  = 12    # check for newer Ollama model every 12 hrs
NEWS_FETCH_INTERVAL_MIN   = 15    # fetch RSS news every 15 min
MAX_DOCS_PER_UPDATE       = 20    # new docs per update cycle
VECTOR_DB_MAX_SIZE        = 5000  # prune oldest when exceeded

# ── Conversation Memory ───────────────────────────────────────────────────────
MAX_HISTORY_TURNS  = 20   # turns of dialogue kept in context
MEMORY_FILE        = BASE_DIR / "data" / "memory.json"

# ── UI ────────────────────────────────────────────────────────────────────────
APP_NAME    = "LocalAI"
APP_VERSION = "2.0.0"
BANNER = f"""
+----------------------------------------------------------+
|   {APP_NAME} v{APP_VERSION} - Local AI with Live Web Knowledge   |
|   Model : Llama 3.2 (local, no API key required)        |
|   Memory: ChromaDB  |  Search: DuckDuckGo               |
|   Auto-updates knowledge every {AUTO_UPDATE_INTERVAL_MIN} minutes              |
+----------------------------------------------------------+
"""
