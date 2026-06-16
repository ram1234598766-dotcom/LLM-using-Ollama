"""
web_collector.py — Live web data collection (zero API key required)
Sources: DuckDuckGo · Wikipedia · RSS feeds · Direct scraping
"""

import logging
import time
import re
from typing import Optional
from urllib.parse import urlparse

import requests
import feedparser
import wikipedia
import trafilatura

try:
    from ddgs import DDGS
except ImportError:
    from duckduckgo_search import DDGS

from config import (
    MAX_SEARCH_RESULTS, MAX_ARTICLE_CHARS,
    REQUEST_TIMEOUT, USER_AGENT, RSS_FEEDS
)

log = logging.getLogger("WebCollector")

HEADERS = {"User-Agent": USER_AGENT}

_BLOCKED_DOMAINS = {
    "facebook.com", "twitter.com", "instagram.com",
    "tiktok.com", "pinterest.com", "reddit.com",
}


def _is_scrapable(url: str) -> bool:
    domain = urlparse(url).netloc.lstrip("www.")
    return domain not in _BLOCKED_DOMAINS


def _clean(text: str) -> str:
    """Remove excess whitespace and control chars."""
    text = re.sub(r"\s{3,}", "\n\n", text)
    return text.strip()[:MAX_ARTICLE_CHARS]


# ── DuckDuckGo Search ──────────────────────────────────────────────────────

def search_web(query: str, max_results: int = MAX_SEARCH_RESULTS) -> list[dict]:
    """
    Search DuckDuckGo — completely free, no API key.
    Returns list of {title, url, snippet}.
    """
    results = []
    try:
        with DDGS() as ddgs:
            for r in ddgs.text(query, max_results=max_results):
                results.append({
                    "title":   r.get("title", ""),
                    "url":     r.get("href", ""),
                    "snippet": r.get("body", ""),
                })
    except Exception as e:
        log.warning("DuckDuckGo search failed for '%s': %s", query, e)
    return results


def fetch_page_text(url: str) -> Optional[str]:
    """
    Extract readable text from a webpage using trafilatura.
    Returns None on failure.
    """
    if not _is_scrapable(url):
        return None
    try:
        resp = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        text = trafilatura.extract(resp.text, include_comments=False,
                                   include_tables=True)
        return _clean(text) if text else None
    except Exception as e:
        log.debug("fetch_page_text failed for %s: %s", url, e)
        return None


def search_and_scrape(query: str, max_results: int = 5) -> list[dict]:
    """
    Full pipeline: search DuckDuckGo → scrape each result.
    Returns list of {text, source, title, topic}.
    """
    docs = []
    search_results = search_web(query, max_results=max_results + 3)

    for r in search_results:
        url  = r["url"]
        title = r["title"]

        # Use snippet if scraping fails
        full_text = fetch_page_text(url) if _is_scrapable(url) else None
        text = full_text or r["snippet"]

        if text and len(text) > 60:
            docs.append({
                "text":   text,
                "source": url,
                "title":  title,
                "topic":  query,
            })
            if len(docs) >= max_results:
                break

        time.sleep(0.3)   # polite crawl delay

    log.info("search_and_scrape('%s'): %d docs.", query, len(docs))
    return docs


# ── Wikipedia ─────────────────────────────────────────────────────────────

def fetch_wikipedia(topic: str, sentences: int = 10) -> Optional[dict]:
    """
    Fetch a Wikipedia summary — free, reliable, authoritative.
    """
    try:
        wikipedia.set_lang("en")
        page    = wikipedia.page(topic, auto_suggest=True)
        summary = wikipedia.summary(topic, sentences=sentences, auto_suggest=True)
        return {
            "text":   _clean(summary),
            "source": page.url,
            "title":  page.title,
            "topic":  topic,
        }
    except wikipedia.DisambiguationError as e:
        try:
            page    = wikipedia.page(e.options[0])
            summary = wikipedia.summary(e.options[0], sentences=sentences)
            return {
                "text":   _clean(summary),
                "source": page.url,
                "title":  page.title,
                "topic":  topic,
            }
        except Exception:
            return None
    except Exception as e:
        log.debug("Wikipedia fetch failed for '%s': %s", topic, e)
        return None


# ── RSS News Feeds ────────────────────────────────────────────────────────

def fetch_rss_news(feeds: list[str] = None, max_per_feed: int = 5) -> list[dict]:
    """
    Pull latest articles from RSS feeds — no API key, always fresh.
    """
    feeds = feeds or RSS_FEEDS
    docs  = []

    for feed_url in feeds:
        try:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries[:max_per_feed]:
                title    = getattr(entry, "title", "")
                link     = getattr(entry, "link", feed_url)
                summary  = getattr(entry, "summary", "")

                # Try to get full text
                full_text = fetch_page_text(link) if link else None
                text = full_text or summary

                if text and len(text) > 60:
                    docs.append({
                        "text":   _clean(text),
                        "source": link,
                        "title":  title,
                        "topic":  "news",
                    })
        except Exception as e:
            log.debug("RSS feed failed (%s): %s", feed_url, e)

    log.info("fetch_rss_news: collected %d articles.", len(docs))
    return docs


# ── Smart Collector (query-aware) ─────────────────────────────────────────

def collect_for_query(query: str) -> list[dict]:
    """
    Intelligently collect data relevant to a user query:
    1. DuckDuckGo search + scrape
    2. Wikipedia article (if informational query)
    """
    docs = []

    # Web search
    web_docs = search_and_scrape(query, max_results=4)
    docs.extend(web_docs)

    # Wikipedia for factual / knowledge queries
    info_signals = ["what is", "how does", "explain", "define", "who is",
                    "history of", "how to", "why does", "what are"]
    if any(q in query.lower() for q in info_signals):
        wiki_topic = re.sub(
            r"^(what is|how does|explain|define|who is|how to|why does)\s+",
            "", query, flags=re.IGNORECASE
        ).strip()
        wiki_doc = fetch_wikipedia(wiki_topic)
        if wiki_doc:
            docs.append(wiki_doc)

    return docs
