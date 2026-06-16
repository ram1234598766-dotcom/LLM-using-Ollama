"""
llm_engine.py — Local LLM via Ollama (Llama 3.2 / Mistral / Phi-3)
No API key. Runs 100% on your Windows 11 machine.
"""

import logging
import subprocess
import sys
import time
from typing import Generator, Optional

import requests

from config import (
    OLLAMA_BASE_URL, OLLAMA_MODEL, OLLAMA_FALLBACK,
    LLM_TEMPERATURE, LLM_MAX_TOKENS, LLM_CONTEXT_SIZE
)

log = logging.getLogger("LLMEngine")

# Models ranked by capability vs hardware requirement
MODEL_PRIORITY = [
    "llama3.1:8b",    # best quality,  ~5 GB VRAM / 8 GB RAM
    "llama3.2",       # fast & light,  ~2 GB VRAM / 4 GB RAM
    "mistral",        # great reasoning, ~4 GB
    "phi3",           # very fast,     ~2 GB
    "gemma2:2b",      # tiny but good, ~1.5 GB
]

SYSTEM_PROMPT = """You are LocalAI - a highly capable, honest AI assistant running
entirely on the user's machine with live web knowledge.

Rules:
- Be concise yet thorough.
- When web context is provided under '### Relevant Knowledge', use it to give
  up-to-date, accurate answers and cite it where helpful.
- If you are unsure, say so - do not hallucinate.
- Adapt your tone: technical with developers, simple with beginners.
- You can write code, explain concepts, analyse data, and answer questions.
"""


class OllamaEngine:
    """
    Interfaces with a locally running Ollama process.
    Supports streaming, auto model selection, and model updates.
    """

    def __init__(self):
        self.model   = OLLAMA_MODEL
        self.base_url = OLLAMA_BASE_URL
        self._ensure_ollama_running()
        self.model   = self._resolve_model()

    # ── Setup ─────────────────────────────────────────────────────────────

    def _ensure_ollama_running(self) -> bool:
        """Ping Ollama. Launch it if not running."""
        try:
            r = requests.get(f"{self.base_url}/api/tags", timeout=3)
            if r.ok:
                log.info("Ollama is running.")
                return True
        except requests.ConnectionError:
            pass

        log.warning("Ollama not detected - attempting to start...")
        try:
            subprocess.Popen(
                ["ollama", "serve"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
            )
            time.sleep(3)
            r = requests.get(f"{self.base_url}/api/tags", timeout=5)
            if r.ok:
                log.info("Ollama started successfully.")
                return True
        except FileNotFoundError:
            log.error(
                "Ollama is not installed. Run setup_windows.bat or visit https://ollama.com"
            )
        return False

    def _list_local_models(self) -> list[str]:
        """Return model names already pulled to disk."""
        try:
            r = requests.get(f"{self.base_url}/api/tags", timeout=5)
            models = r.json().get("models", [])
            return [m["name"] for m in models]
        except Exception:
            return []

    def _pull_model(self, model: str) -> bool:
        """Pull a model from Ollama library (downloads weights)."""
        print(f"  Downloading model '{model}' - this may take a few minutes...")
        try:
            resp = requests.post(
                f"{self.base_url}/api/pull",
                json={"name": model},
                stream=True, timeout=600
            )
            for line in resp.iter_lines():
                if line and b'"status"' in line:
                    import json as _json
                    data = _json.loads(line)
                    status = data.get("status", "")
                    if "pulling" in status.lower() or "success" in status.lower():
                        print(f"\r  [{status}]", end="", flush=True)
            print()
            return True
        except Exception as e:
            log.error("Model pull failed: %s", e)
            return False

    def _resolve_model(self) -> str:
        """Choose the best available model, downloading if needed."""
        local = self._list_local_models()
        local_names = {m.split(":")[0] for m in local}

        # Try the configured model first
        for preferred in [self.model, OLLAMA_FALLBACK]:
            if preferred in local or preferred.split(":")[0] in local_names:
                log.info("Using model: %s", preferred)
                return preferred

        # Pull configured model
        log.info("Pulling model '%s'...", self.model)
        if self._pull_model(self.model):
            return self.model

        # Try fallbacks in priority order
        for m in MODEL_PRIORITY:
            if m.split(":")[0] in local_names:
                log.info("Falling back to: %s", m)
                return m

        log.error("No usable model found.")
        return self.model

    # ── Inference ─────────────────────────────────────────────────────────

    def chat(
        self,
        user_message: str,
        context: str = "",
        history: Optional[list[dict]] = None,
        stream: bool = True,
    ) -> Generator[str, None, None]:
        """
        Stream a response from the local LLM.
        Yields text tokens as they arrive.
        """
        import json

        messages = [{"role": "system", "content": SYSTEM_PROMPT}]

        # Inject RAG web context as a system-level message
        if context:
            messages.append({
                "role": "system",
                "content": context
            })

        # Conversation history
        for turn in (history or []):
            messages.append(turn)

        # Current user message
        messages.append({"role": "user", "content": user_message})

        payload = {
            "model":   self.model,
            "messages": messages,
            "stream":  stream,
            "options": {
                "temperature":  LLM_TEMPERATURE,
                "num_predict":  LLM_MAX_TOKENS,
                "num_ctx":      LLM_CONTEXT_SIZE,
            },
        }

        try:
            resp = requests.post(
                f"{self.base_url}/api/chat",
                json=payload, stream=stream, timeout=120
            )
            resp.raise_for_status()

            if stream:
                for line in resp.iter_lines():
                    if line:
                        data = json.loads(line)
                        token = data.get("message", {}).get("content", "")
                        if token:
                            yield token
                        if data.get("done"):
                            break
            else:
                data = resp.json()
                yield data.get("message", {}).get("content", "")

        except requests.ConnectionError:
            yield "\n[Error: Ollama is not running. Please start it with: ollama serve]\n"
        except Exception as e:
            yield f"\n[LLM Error: {e}]\n"

    def get_full_response(
        self,
        user_message: str,
        context: str = "",
        history: Optional[list[dict]] = None,
    ) -> str:
        """Non-streaming version — returns complete response string."""
        return "".join(self.chat(user_message, context, history, stream=False))

    # ── Model Management ──────────────────────────────────────────────────

    def check_for_model_update(self) -> bool:
        """Re-pull the current model to get the latest version."""
        log.info("Checking for model update: %s", self.model)
        try:
            resp = requests.post(
                f"{self.base_url}/api/pull",
                json={"name": self.model},
                stream=True, timeout=120
            )
            for line in resp.iter_lines():
                if line:
                    import json
                    data = json.loads(line)
                    if data.get("status") == "success":
                        log.info("Model '%s' is up to date.", self.model)
                        return True
            return True
        except Exception as e:
            log.warning("Model update check failed: %s", e)
            return False

    def info(self) -> dict:
        return {
            "model":    self.model,
            "endpoint": self.base_url,
            "local":    True,
            "api_key":  "not required",
        }
