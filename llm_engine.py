"""
llm_engine.py — Local LLM via Ollama (Qwen 3)
No API key. Runs 100% on your Windows 11 machine.
"""

import logging
import json
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
    "qwen3:8b",       # configured Qwen 3 model
    "qwen3:4b",       # smaller Qwen 3 fallback
    "qwen3:1.7b",     # lightweight Qwen 3 fallback
    "qwen3:0.6b",     # tiny Qwen 3 fallback
    "qwen3:14b",      # larger Qwen 3 fallback if already installed
    "qwen3:32b",      # strong Qwen 3 fallback if already installed
]

DOWNLOAD_PRIORITY = [
    OLLAMA_MODEL,
    OLLAMA_FALLBACK,
    "qwen3:1.7b",
    "qwen3:0.6b",
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

    def _find_local_model(self, requested: str, local: list[str]) -> Optional[str]:
        """Return the exact local model tag, or a family match for untagged names."""
        if requested in local:
            return requested

        if ":" in requested:
            return None

        requested_base = requested.split(":")[0]
        for model in local:
            if model.split(":")[0] == requested_base:
                return model

        return None

    def _pull_model(self, model: str) -> bool:
        """Pull a model from Ollama library (downloads weights)."""
        print(f"  Downloading model '{model}' - this may take a few minutes...")
        try:
            resp = requests.post(
                f"{self.base_url}/api/pull",
                json={"name": model},
                stream=True, timeout=1800
            )
            resp.raise_for_status()

            success = False
            for line in resp.iter_lines():
                if not line:
                    continue

                data = json.loads(line)
                if data.get("error"):
                    print(f"\n  Download failed: {data['error']}")
                    log.error("Model pull failed for '%s': %s", model, data["error"])
                    return False

                status = data.get("status", "")
                total = data.get("total", 0)
                completed = data.get("completed", 0)
                if total and completed:
                    pct = int(completed / total * 100)
                    print(f"\r  [{status} {pct}%]", end="", flush=True)
                elif status:
                    print(f"\r  [{status}]", end="", flush=True)

                if status.lower() == "success":
                    success = True

            print()
            if success or self._find_local_model(model, self._list_local_models()):
                return True

            log.error("Model pull ended without success: %s", model)
            return False
        except Exception as e:
            log.error("Model pull failed: %s", e)
            return False

    def _resolve_model(self) -> str:
        """Choose the best available model, downloading if needed."""
        local = self._list_local_models()

        local_match = self._find_local_model(self.model, local)
        if local_match:
            log.info("Using model: %s", local_match)
            return local_match

        for candidate in dict.fromkeys(DOWNLOAD_PRIORITY):
            log.info("Downloading model '%s'...", candidate)
            if self._pull_model(candidate):
                log.info("Using downloaded model: %s", candidate)
                return candidate

        local = self._list_local_models()
        for m in MODEL_PRIORITY:
            local_match = self._find_local_model(m, local)
            if local_match:
                log.info("Falling back to: %s", local_match)
                return local_match

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

    def download_model(self, model: Optional[str] = None) -> bool:
        """Download a model on demand and use it for this session."""
        requested = (model or OLLAMA_MODEL).strip()
        local_match = self._find_local_model(requested, self._list_local_models())
        if local_match:
            self.model = local_match
            log.info("Model already available: %s", self.model)
            return True

        if self._pull_model(requested):
            self.model = requested
            log.info("Downloaded and switched to model: %s", self.model)
            return True

        return False

    # ── Model Management ──────────────────────────────────────────────────

    def check_for_model_update(self) -> bool:
        """Re-pull the current model to get the latest version."""
        log.info("Checking for model update: %s", self.model)
        return self._pull_model(self.model)

    def info(self) -> dict:
        return {
            "model":    self.model,
            "endpoint": self.base_url,
            "local":    True,
            "api_key":  "not required",
        }
