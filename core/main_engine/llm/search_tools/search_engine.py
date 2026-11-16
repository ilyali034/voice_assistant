"""Google search via Selenium -> text context for an LLM.

Drop-in for core/main_engine/llm/search_tools/search_engine.py.
Keeps the interface ollama_engine.py already uses:
    LangchainOllamaSearchEngine().standart_search(request=...) -> str
"""
from __future__ import annotations

import asyncio
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from urllib.parse import quote_plus, urlparse

import requests
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

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
    """Google served captcha / 'unusual traffic' page."""


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
        candidates: int = 8,        
        top_chunks: int = 5,       
        chunks_per_url: int = 2,
        min_score: float = 0.0,    
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

    async def standart_search(self, request: str, **kwargs) -> str:
        """Return formatted context string. Empty string on any failure."""
        try:
            results = await asyncio.to_thread(self.search, request)
        except SearchBlockedError:
            print("[search] Google blocked request (captcha). Try later / other IP.")
            return ""
        except Exception as error: 
            print(f"[search] failed: {error!r}")
            return ""

        if self.use_rerank and results:
            try:
                return await asyncio.to_thread(self.rerank_context, request, results)
            except Exception as error:  # noqa: BLE001  (model download/load error...)
                print(f"[search] rerank failed, plain order used: {error!r}")
        return self.format_context(results[: self.max_results])

    def search(self, query: str) -> list[SearchResult]:
        """Blocking. Run in a thread from async code."""
        limit = self.candidates if self.use_rerank else self.max_results
        driver = self._make_driver()
        try:
            url = (
                "https://www.google.com/search"
                f"?q={quote_plus(query)}&hl={self.lang}&num={limit + 5}"
            )
            driver.get(url)
            self._handle_consent(driver)
            if "/sorry/" in driver.current_url:
                raise SearchBlockedError(driver.current_url)

            try:
                WebDriverWait(driver, self.timeout).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "#search, #rso"))
                )
            except TimeoutException:
                if "/sorry/" in driver.current_url or "captcha" in driver.page_source.lower():
                    raise SearchBlockedError(driver.current_url) from None
                return []

            results = self._parse(driver, limit)
        finally:
            driver.quit()

        if self.fetch_pages or self.use_rerank:
            with ThreadPoolExecutor(max_workers=6) as pool:
                texts = list(pool.map(self._fetch_page_text, [r.url for r in results]))
            for item, text in zip(results, texts):
                item.page_text = text
        return results

    def rerank_context(self, query: str, results: list[SearchResult]) -> str:
        """Chunk snippets + pages, keep chunks most similar to query."""
        chunks: list[Chunk] = []
        for r in results:
            if r.snippet:
                chunks.append(Chunk(r.snippet, r.url, r.title))
            for piece in chunk_text(r.page_text):
                chunks.append(Chunk(piece, r.url, r.title))
        if not chunks:
            return self.format_context(results[: self.max_results])

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

    # ---------- selenium ----------

    def _make_driver(self) -> webdriver.Chrome:
        opts = Options()
        if self.headless:
            opts.add_argument("--headless=new")
        opts.add_argument("--no-sandbox")
        opts.add_argument("--disable-gpu")
        opts.add_argument("--window-size=1280,900")
        opts.add_argument(f"--lang={self.lang}")
        opts.add_argument(f"--user-agent={USER_AGENT}")
        opts.add_argument("--disable-blink-features=AutomationControlled")
        opts.add_experimental_option("excludeSwitches", ["enable-automation"])
        opts.page_load_strategy = "eager"
        driver = webdriver.Chrome(options=opts)
        driver.set_page_load_timeout(self.timeout * 2)
        return driver

    @staticmethod
    def _handle_consent(driver: webdriver.Chrome) -> None:
        """Click cookie-consent button (EU etc.) if shown."""
        for button_id in ("L2AGLb", "W0wltc"):  
            try:
                buttons = driver.find_elements(By.ID, button_id)
                if buttons:
                    buttons[0].click()
                    return
            except WebDriverException:
                pass

    def _parse(self, driver: webdriver.Chrome, limit: int) -> list[SearchResult]:
        results: list[SearchResult] = []
        seen: set[str] = set()

        for h3 in driver.find_elements(By.CSS_SELECTOR, "#search a h3, #rso a h3"):
            if len(results) >= limit:
                break
            try:
                title = h3.text.strip()
                link = h3.find_element(By.XPATH, "./ancestor::a[1]").get_attribute("href") or ""
                host = urlparse(link).netloc
                if not title or not link.startswith("http") or "google." in host or link in seen:
                    continue

                snippet = ""
                node = h3
                for _ in range(6): 
                    node = node.find_element(By.XPATH, "..")
                    found = node.find_elements(By.CSS_SELECTOR, SNIPPET_SELECTOR)
                    if found:
                        snippet = found[0].text.strip()
                        break
            except WebDriverException: 
                continue

            seen.add(link)
            results.append(SearchResult(title=title, url=link, snippet=snippet))
        return results

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