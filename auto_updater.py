"""
auto_updater.py — Background threads that keep knowledge fresh automatically.

Schedules:
  · Every 15 min : fetch RSS news headlines
  · Every 30 min : enrich knowledge base from recent query topics
  · Every 12 hrs : check for newer Ollama model version
"""

import logging
import threading
from collections import deque

import schedule

from config import (
    AUTO_UPDATE_INTERVAL_MIN, NEWS_FETCH_INTERVAL_MIN,
    MODEL_CHECK_INTERVAL_HRS, MAX_DOCS_PER_UPDATE
)

log = logging.getLogger("AutoUpdater")


class AutoUpdater:
    """
    Background daemon that continuously updates the knowledge base
    without interrupting the user's chat session.
    """

    def __init__(self, knowledge_base, llm_engine, web_collector_module):
        self.kb   = knowledge_base
        self.llm  = llm_engine
        self.wc   = web_collector_module        # web_collector module

        self._running = False
        self._thread  = None
        self._recent_topics: deque[str] = deque(maxlen=50)   # topics user asked about
        self._update_count  = 0
        self._lock = threading.Lock()
        self._stop_event = threading.Event()

    # ── Public API ─────────────────────────────────────────────────────────

    def register_topic(self, topic: str):
        """Call this whenever the user asks about something — enables smart updates."""
        with self._lock:
            self._recent_topics.append(topic.strip()[:120])

    def start(self):
        """Start the background update daemon."""
        if self._running:
            return
        self._running = True
        self._stop_event.clear()

        # Schedule jobs
        schedule.every(NEWS_FETCH_INTERVAL_MIN).minutes.do(self._job_news)
        schedule.every(AUTO_UPDATE_INTERVAL_MIN).minutes.do(self._job_topics)
        schedule.every(MODEL_CHECK_INTERVAL_HRS).hours.do(self._job_model_check)

        # Kick off initial news pull after 5 seconds
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        log.info(
            "AutoUpdater started - news every %dm, topics every %dm, "
            "model check every %dh.",
            NEWS_FETCH_INTERVAL_MIN, AUTO_UPDATE_INTERVAL_MIN,
            MODEL_CHECK_INTERVAL_HRS
        )

    def stop(self):
        """Stop the background daemon."""
        self._running = False
        self._stop_event.set()
        schedule.clear()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)
        log.info("AutoUpdater stopped.")

    def force_update(self, topic: str = "") -> int:
        """Manually trigger an immediate update on a topic."""
        if topic:
            self.register_topic(topic)
        return self._job_topics()

    def status(self) -> dict:
        return {
            "running":        self._running,
            "updates_done":   self._update_count,
            "tracked_topics": list(self._recent_topics)[-10:],
            "kb_size":        self.kb.count(),
            "next_news":      str(schedule.next_run()),
        }

    # ── Internal jobs ──────────────────────────────────────────────────────

    def _run_loop(self):
        """Main scheduler loop running in a daemon thread."""
        while not self._stop_event.is_set():
            try:
                schedule.run_pending()
            except Exception as e:
                log.warning("Scheduler error: %s", e)
            self._stop_event.wait(30)

    def _initial_fetch(self):
        """Fetch a broad set of topics on startup to warm up the knowledge base."""
        seed_topics = [
            "latest AI research 2025",
            "Python programming best practices",
            "technology news today",
            "machine learning neural networks",
            "science breakthroughs 2025",
        ]
        log.info("Warming up knowledge base with seed topics...")
        added = 0
        for topic in seed_topics:
            if self._stop_event.is_set():
                break
            try:
                docs = self.wc.search_and_scrape(topic, max_results=2)
                if self._stop_event.is_set():
                    break
                added += self.kb.add_documents_batch(docs)
                if self._stop_event.wait(1):
                    break
            except Exception as e:
                log.debug("Seed fetch error (%s): %s", topic, e)
        log.info("Warm-up complete: %d documents added.", added)

    def _job_news(self) -> int:
        """Fetch latest RSS news headlines."""
        log.info("[AutoUpdater] Fetching RSS news...")
        try:
            docs  = self.wc.fetch_rss_news(max_per_feed=4)
            added = self.kb.add_documents_batch(docs)
            log.info("[AutoUpdater] News update: +%d documents.", added)
            self._update_count += 1
            return added
        except Exception as e:
            log.warning("[AutoUpdater] News fetch failed: %s", e)
            return 0

    def _job_topics(self) -> int:
        """Enrich the knowledge base from topics the user has been asking about."""
        with self._lock:
            topics = list(self._recent_topics)

        if not topics:
            log.debug("[AutoUpdater] No recent topics to update.")
            return 0

        # Take the 3 most recent unique topics
        seen, unique = set(), []
        for t in reversed(topics):
            key = t[:40].lower()
            if key not in seen:
                seen.add(key)
                unique.append(t)
            if len(unique) >= 3:
                break

        log.info("[AutoUpdater] Updating knowledge for topics: %s", unique)
        total_added = 0
        for topic in unique:
            try:
                docs  = self.wc.collect_for_query(topic)
                added = self.kb.add_documents_batch(docs[:MAX_DOCS_PER_UPDATE])
                total_added += added
                if self._stop_event.wait(1):
                    break
            except Exception as e:
                log.warning("[AutoUpdater] Topic update failed (%s): %s", topic, e)

        log.info("[AutoUpdater] Topic update done: +%d new documents.", total_added)
        self._update_count += 1
        return total_added

    def _job_model_check(self):
        """Check if there's a newer version of the current Ollama model."""
        log.info("[AutoUpdater] Checking for model updates...")
        try:
            updated = self.llm.check_for_model_update()
            if updated:
                log.info("[AutoUpdater] Model is up to date.")
        except Exception as e:
            log.warning("[AutoUpdater] Model update check failed: %s", e)
