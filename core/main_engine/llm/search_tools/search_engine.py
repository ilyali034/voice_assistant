"""Web search and reranking for the Ollama response engine.

The public interface remains:
    LangchainOllamaSearchEngine().standart_search(request=...) -> str
"""
from __future__ import annotations

import asyncio
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

import requests
from bs4 import BeautifulSoup
from ddgs import DDGS

try:
    from .reranker import Chunk, Embedder, SentenceTransformerEmbedder, chunk_text, rerank
except ImportError:  # run as a plain script
    from reranker import Chunk, Embedder, SentenceTransformerEmbedder, chunk_text, rerank

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
SNIPPET_SELECTOR = "div[data-sncf], div.VwiC3b, span.VwiC3b"


class SearchBlockedError(RuntimeError):
    """Reserved for provider-specific blocking errors."""


@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str
    page_text: str = ""


class LangchainOllamaSearchEngine:
    def __init__(
        self,
        max_results: int = 5,
        lang: str = "ru",
        headless: bool = True,
        timeout: float = 15.0,
        fetch_pages: bool = False,
        page_chars: int = 6000,
        max_context_chars: int = 6000,
        # --- semantic rerank ---
        rerank: bool = True,
        candidates: int = 10,
        top_chunks: int = 4,
        chunks_per_url: int = 1,
        min_score: float = 0.24,
        embedder: Embedder | None = None,
        embed_model: str = "intfloat/multilingual-e5-small",
    ) -> None:
        self.max_results = max_results
        self.lang = lang
        self.headless = headless
        self.timeout = timeout
        self.fetch_pages = fetch_pages
        self.page_chars = page_chars
        self.max_context_chars = max_context_chars
        self.use_rerank = rerank
        self.candidates = candidates
        self.top_chunks = top_chunks
        self.chunks_per_url = chunks_per_url
        self.min_score = min_score
        self.embedder = embedder or SentenceTransformerEmbedder(model=embed_model)

    # ---------- public ----------

    def _build_search_query(self, request: str) -> str:
        """Convert a natural-language question into a concise search query."""
        text = re.sub(r"\s+", " ", request).strip(" ?!.,;:")
        if not text:
            return request

        # Stop phrases are not useful in search and often dilute the ranking.
        stop_phrases = (
            r"^\s*(what is|what are|what's|who is|who are|tell me|please)",
            r"^\s*(что такое|что есть|кто такой|кто такая|скажи мне|пожалуйста)",
            r"^\s*(що таке|хто такий|хто така|розкажи мені|будь ласка)",
        )
        for pattern in stop_phrases:
            text = re.sub(pattern, "", text, count=1, flags=re.IGNORECASE).strip()

        return text

    async def standart_search(self, request: str, **kwargs) -> str:
        """Return a concise, reranked context string. Empty string on failure."""
        search_query = self._build_search_query(request)
        try:
            results = await asyncio.to_thread(self.search, search_query)
        except SearchBlockedError:
            print("[search] Google blocked request (captcha). Try later / other IP.")
            return ""
        except Exception as error:
            print(f"[search] failed: {error!r}")
            return ""

        if self.use_rerank and results:
            try:
                return await asyncio.to_thread(self.rerank_context, request, results)
            except Exception as error:  # noqa: BLE001
                print(f"[search] rerank failed, plain order used: {error!r}")
        return self.format_context(results[: self.max_results])

    def search(self, query: str) -> list[SearchResult]:
        """Run a bounded metasearch request in a worker thread."""
        limit = self.candidates if self.use_rerank else self.max_results
        region = {
            "ru": "ru-ru", "uk": "ua-uk", "be": "by-be", "en": "us-en",
            "de": "de-de", "fr": "fr-fr", "es": "es-es", "it": "it-it",
            "pt": "pt-pt", "pl": "pl-pl", "tr": "tr-tr", "ar": "sa-ar",
            "zh": "cn-zh", "ja": "jp-ja", "ko": "kr-ko",
        }.get(self.lang, "us-en")

        try:
            fresh_markers = (
                "сегодня", "сейчас", "последн", "актуаль",
                "today", "now", "latest", "current", "recent", "this week",
            )
            timelimit_options = ["d", None] if any(
                marker in query.casefold() for marker in fresh_markers
            ) else [None]

            raw_results: list[dict[str, str]] = []
            last_error: Exception | None = None
            for timelimit in timelimit_options:
                try:
                    with DDGS(timeout=int(self.timeout), verify=True) as ddgs:
                        raw_results = ddgs.text(
                            query,
                            region=region,
                            safesearch="moderate",
                            timelimit=timelimit,
                            max_results=limit,
                            backend="auto",
                        )
                    if raw_results:
                        break
                except Exception as error:
                    last_error = error

            if not raw_results:
                if last_error:
                    print(f"[search] DDGS failed: {last_error!r}")
                else:
                    print("[search] DDGS returned no results")
                return []
        except Exception as error:
            print(f"[search] DDGS failed: {error!r}")
            return []

        parsed_results: list[SearchResult] = []
        seen_urls: set[str] = set()
        for item in raw_results:
            title = str(item.get("title", "")).strip()
            url = str(item.get("href") or item.get("url", "")).strip()
            snippet = str(item.get("body") or item.get("snippet", "")).strip()
            if not title or not url.startswith("http") or url in seen_urls:
                continue
            seen_urls.add(url)
            parsed_results.append(SearchResult(title=title, url=url, snippet=snippet))

        if self.fetch_pages or self.use_rerank:
            with ThreadPoolExecutor(max_workers=6) as pool:
                texts = list(pool.map(self._fetch_page_text, [r.url for r in parsed_results]))
            for item, text in zip(parsed_results, texts):
                item.page_text = text
        return parsed_results

    def rerank_context(self, query: str, results: list[SearchResult]) -> str:
        """Chunk snippets + pages, keep chunks most similar to query."""
        chunks: list[Chunk] = []
        for r in results:
            if r.snippet:
                chunks.append(Chunk(r.snippet, r.url, r.title))
            for piece in chunk_text(r.page_text):
                chunks.append(Chunk(piece, r.url, r.title))
        if not chunks:
            return ""

        best = rerank(
            query, chunks, self.embedder,
            top_k=self.top_chunks, per_url=self.chunks_per_url, min_score=self.min_score,
        )
        print("[search] rerank scores:", [round(c.score, 3) for c in best])
        if not best:
            return "" 

        parts: list[str] = []
        total = 0
        for i, c in enumerate(best, 1):
            block = f"[{i}] {c.title}\nURL: {c.url}\n{c.text}"
            if total + len(block) > self.max_context_chars:
                break
            parts.append(block)
            total += len(block) + 2
        return "\n\n".join(parts)

    def format_context(self, results: list[SearchResult]) -> str:
        parts: list[str] = []
        total = 0
        for i, r in enumerate(results, 1):
            block = f"[{i}] {r.title}\nURL: {r.url}\n{r.snippet}"
            if r.page_text:
                block += f"\n{r.page_text}"
            if total + len(block) > self.max_context_chars:
                break
            parts.append(block)
            total += len(block) + 2
        return "\n\n".join(parts)

    # ---------- optional page fetch ----------

    def _fetch_page_text(self, url: str) -> str:
        try:
            resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=8)
            if "text/html" not in resp.headers.get("Content-Type", ""):
                return ""
            soup = BeautifulSoup(resp.text, "html.parser")
            for tag in soup(["script", "style", "nav", "footer", "header", "aside", "noscript"]):
                tag.decompose()
            text = re.sub(r"\s+", " ", soup.get_text(" ", strip=True))
            return text[: self.page_chars]
        except requests.RequestException:
            return ""


if __name__ == "__main__":
    import sys

    engine = LangchainOllamaSearchEngine(headless=False, fetch_pages=False)
    query = " ".join(sys.argv[1:]) or "python selenium tutorial"
    print(asyncio.run(engine.standart_search(query)))