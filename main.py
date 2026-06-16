"""
main.py — LocalAI: Local LLM + Live Web Knowledge
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
• No API key required
• Runs on Windows 11 / PyCharm
• Powered by Llama 3.2 (via Ollama)
• RAG from live web data (DuckDuckGo + Wikipedia + RSS)
• Auto-updates knowledge every 30 minutes in background
• Conversation memory across sessions

Run:
    python main.py
"""

import json
import logging
import sys
import time
from pathlib import Path
from datetime import datetime

from rich.console import Console
from rich.markdown import Markdown
from rich.panel    import Panel
from rich.prompt   import Prompt
from rich.table    import Table
from rich.text     import Text
from rich.live     import Live
from rich          import box

import config
import web_collector as wc
from knowledge_base import KnowledgeBase
from llm_engine     import OllamaEngine
from auto_updater   import AutoUpdater

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(errors="replace")

# ── Logging ────────────────────────────────────────────────────────────────
logging.basicConfig(
    level   = logging.WARNING,          # quiet by default in chat
    format  = "%(levelname)s [%(name)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(config.LOGS_DIR / "localai.log", encoding="utf-8"),
    ]
)
logging.getLogger("huggingface_hub").setLevel(logging.ERROR)
logging.getLogger("sentence_transformers").setLevel(logging.ERROR)
log = logging.getLogger("LocalAI")

console = Console(emoji=False, safe_box=True)


# ── Conversation Memory ────────────────────────────────────────────────────

class ConversationMemory:
    def __init__(self, max_turns: int = config.MAX_HISTORY_TURNS):
        self.max_turns = max_turns
        self.history: list[dict] = []
        self._load()

    def add(self, role: str, content: str):
        self.history.append({"role": role, "content": content})
        if len(self.history) > self.max_turns * 2:
            self.history = self.history[-(self.max_turns * 2):]
        self._save()

    def get(self) -> list[dict]:
        return list(self.history)

    def clear(self):
        self.history = []
        self._save()
        console.print("[dim]Conversation memory cleared.[/dim]")

    def _save(self):
        try:
            config.MEMORY_FILE.write_text(
                json.dumps(self.history, indent=2), encoding="utf-8"
            )
        except Exception:
            pass

    def _load(self):
        try:
            if config.MEMORY_FILE.exists():
                self.history = json.loads(
                    config.MEMORY_FILE.read_text(encoding="utf-8")
                )
        except Exception:
            self.history = []


# ── Startup Banner ─────────────────────────────────────────────────────────

def print_banner(kb: KnowledgeBase, llm: OllamaEngine):
    table = Table(box=box.ASCII, show_header=False, border_style="cyan")
    table.add_column("Key",   style="bold cyan", width=22)
    table.add_column("Value", style="white")

    table.add_row("Model",         llm.model)
    table.add_row("Running on",    "your PC (no API key)")
    table.add_row("Knowledge base", f"{kb.count()} documents (ChromaDB)")
    table.add_row("Web search",    "DuckDuckGo + Wikipedia + RSS")
    table.add_row("Auto-update",   f"every {config.AUTO_UPDATE_INTERVAL_MIN} min")
    table.add_row("Embeddings",    config.EMBED_MODEL)

    console.print(
        Panel(
            table,
            title="[bold cyan]LocalAI[/]",
            subtitle="Type [bold]/help[/] for commands",
            border_style="cyan",
            box=box.ASCII,
        )
    )


# ── Help Menu ──────────────────────────────────────────────────────────────

HELP_TEXT = """
[bold cyan]LocalAI Commands:[/bold cyan]

  [bold]/help[/]          - Show this menu
  [bold]/update <topic>[/]- Force-fetch web data on a topic now
  [bold]/stats[/]         - Show knowledge base + updater stats
  [bold]/clear[/]         - Clear conversation memory
  [bold]/search <query>[/]- Search knowledge base directly
  [bold]/model[/]         - Show current LLM model info
  [bold]/exit[/]  or  [bold]/quit[/] - Exit LocalAI

[dim]Everything else is a question for the AI.[/dim]
"""


# ── Chat UI ────────────────────────────────────────────────────────────────

def stream_response(
    llm: OllamaEngine,
    message: str,
    context: str,
    history: list[dict]
) -> str:
    """Stream LLM tokens to terminal with live rendering."""
    full_response = ""
    with Live(console=console, refresh_per_second=12) as live:
        for token in llm.chat(message, context=context, history=history, stream=True):
            full_response += token
            live.update(
                    Panel(
                        Markdown(full_response),
                        title="[bold green]LocalAI[/]",
                        border_style="green",
                        padding=(0, 1),
                        box=box.ASCII,
                    )
                )
    return full_response


def handle_command(
    cmd: str,
    kb: KnowledgeBase,
    updater: AutoUpdater,
    llm: OllamaEngine,
) -> bool:
    """Handle slash commands. Returns True to continue, False to exit."""
    parts = cmd.strip().split(None, 1)
    verb  = parts[0].lower()
    arg   = parts[1] if len(parts) > 1 else ""

    if verb in ("/exit", "/quit"):
        console.print("[bold red]Goodbye![/bold red]")
        return False

    elif verb == "/help":
        console.print(Panel(HELP_TEXT, border_style="cyan", box=box.ASCII))

    elif verb == "/stats":
        kb_stats  = kb.stats()
        up_status = updater.status()
        table = Table(title="System Stats", box=box.ASCII, border_style="cyan")
        table.add_column("Item", style="bold cyan")
        table.add_column("Value", style="white")
        table.add_row("KB documents",    str(kb_stats["total_documents"]))
        table.add_row("Embed model",     kb_stats["embed_model"])
        table.add_row("Auto-updates",    str(up_status["updates_done"]))
        table.add_row("Recent topics",   ", ".join(up_status["tracked_topics"][-5:]))
        table.add_row("Next update",     up_status["next_news"])
        console.print(table)

    elif verb == "/update":
        topic = arg or "latest news technology science"
        console.print(f"[dim]Fetching web data on: '{topic}'...[/dim]")
        added = updater.force_update(topic)
        console.print(f"[green]OK Added {added} new documents.[/green]")

    elif verb == "/search":
        if not arg:
            console.print("[yellow]Usage: /search <query>[/yellow]")
        else:
            hits = kb.search(arg, top_k=5)
            if not hits:
                console.print("[yellow]No results found in knowledge base.[/yellow]")
            else:
                table = Table(title=f"KB Search: '{arg}'", box=box.ASCII)
                table.add_column("#",      width=3)
                table.add_column("Title",  width=30)
                table.add_column("Score",  width=7)
                table.add_column("Snippet", width=50)
                for i, h in enumerate(hits, 1):
                    table.add_row(
                        str(i), h["title"][:28], f"{h['score']:.3f}",
                        h["text"][:60].replace("\n", " ")
                    )
                console.print(table)

    elif verb == "/clear":
        console.print("[yellow]Clear conversation memory? (y/n)[/yellow]", end=" ")
        ans = input().strip().lower()
        if ans == "y":
            return "clear_memory"    # special signal

    elif verb == "/model":
        console.print(
            Panel(str(llm.info()), title="Model Info", border_style="cyan", box=box.ASCII)
        )

    else:
        console.print(f"[yellow]Unknown command: {verb}. Type /help.[/yellow]")

    return True


# ── Main ───────────────────────────────────────────────────────────────────

def main():
    console.print(config.BANNER, style="bold cyan")
    console.print("[dim]Initializing components - please wait...[/dim]\n")

    # 1. Boot components
    console.print("  [cyan]>[/cyan] Loading knowledge base & embeddings...")
    kb = KnowledgeBase()

    console.print("  [cyan]>[/cyan] Starting local LLM (Ollama)...")
    llm = OllamaEngine()

    console.print("  [cyan]>[/cyan] Starting background web updater...")
    updater = AutoUpdater(kb, llm, wc)
    updater.start()

    memory = ConversationMemory()

    print_banner(kb, llm)

    # 2. Chat loop
    while True:
        try:
            user_input = Prompt.ask("\n[bold blue]You[/bold blue]").strip()
            user_input = user_input.lstrip("\ufeff\xef\xbb\xbf").strip()
        except (KeyboardInterrupt, EOFError):
            console.print("\n[bold red]Goodbye![/bold red]")
            break

        if not user_input:
            continue

        # Slash commands
        if user_input.startswith("/"):
            result = handle_command(user_input, kb, updater, llm)
            if result is False:
                break
            if result == "clear_memory":
                memory.clear()
            continue

        # ── Normal chat turn ──────────────────────────────────────────────

        # 1. Register topic for background updater
        updater.register_topic(user_input)

        # 2. Fetch live web data for this specific query
        console.print("[dim]  Fetching live web context...[/dim]", end="\r")
        fresh_docs = wc.collect_for_query(user_input)
        if fresh_docs:
            kb.add_documents_batch(fresh_docs)

        # 3. Retrieve relevant knowledge from vector DB
        context = kb.build_rag_context(user_input)

        # 4. Stream LLM response
        console.print(" " * 40, end="\r")  # clear status line
        response = stream_response(llm, user_input, context, memory.get())

        # 5. Save to memory
        memory.add("user",      user_input)
        memory.add("assistant", response)

    updater.stop()
    console.print("[dim]Session ended.[/dim]")


if __name__ == "__main__":
    main()
