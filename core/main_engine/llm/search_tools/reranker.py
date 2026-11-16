"""Semantic rerank: chunk pages, embed with a small multilingual encoder, keep chunks closest to query."""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Protocol
from urllib.request import Request, urlopen

import numpy as np


class Embedder(Protocol):
    """Must return L2-normalized float32 vectors."""

    def embed_query(self, text: str) -> np.ndarray: ...
    def embed_passages(self, texts: list[str]) -> np.ndarray: ...


class SentenceTransformerEmbedder:
    """Small local multilingual encoder, no Ollama needed.

    Default: intfloat/multilingual-e5-small (~118M params, 384-dim, 100 langs, RU ok).
    Needs the "query: " / "passage: " prefixes (e5 requirement).
    Other options (set prefixes to ""):
      - sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2 (~118M, 50+ langs)
      - sentence-transformers/distiluse-base-multilingual-cased-v2
    Model is downloaded from Hugging Face on first use, then cached.
    """

    def __init__(
        self,
        model: str = "intfloat/multilingual-e5-small",
        device: str | None = None,  
        batch_size: int = 32,
        max_seq_length: int = 256,
        query_prefix: str = "query: ",
        passage_prefix: str = "passage: ",
    ) -> None:
        self.model_name = model
        self.device = device
        self.batch_size = batch_size
        self.max_seq_length = max_seq_length
        self.query_prefix = query_prefix
        self.passage_prefix = passage_prefix
        self._model = None

    def _load(self):
        if self._model is None:  
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self.model_name, device=self.device)
            self._model.max_seq_length = self.max_seq_length
        return self._model

    def _encode(self, texts: list[str]) -> np.ndarray:
        vecs = self._load().encode(
            texts,
            batch_size=self.batch_size,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return np.asarray(vecs, dtype=np.float32)

    def embed_query(self, text: str) -> np.ndarray:
        return self._encode([self.query_prefix + text])[0]

    def embed_passages(self, texts: list[str]) -> np.ndarray:
        return self._encode([self.passage_prefix + t for t in texts])


class OllamaEmbedder:
    """Needs: `ollama pull bge-m3` (multilingual, good for RU). Ollama >= 0.3 (/api/embed)."""

    def __init__(
        self,
        model: str = "bge-m3",
        base_url: str = "http://localhost:11434",
        timeout: float = 60.0,
        batch_size: int = 32,
    ) -> None:
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.batch_size = batch_size

    def embed(self, texts: list[str]) -> np.ndarray:
        vectors: list[list[float]] = []
        for i in range(0, len(texts), self.batch_size):
            body = json.dumps(
                {"model": self.model, "input": texts[i : i + self.batch_size]}
            ).encode("utf-8")
            req = Request(
                f"{self.base_url}/api/embed",
                data=body,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            vectors.extend(data["embeddings"])

        arr = np.asarray(vectors, dtype=np.float32)
        norms = np.linalg.norm(arr, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        return arr / norms 

    def embed_query(self, text: str) -> np.ndarray:
        return self.embed([text])[0]

    def embed_passages(self, texts: list[str]) -> np.ndarray:
        return self.embed(texts)


@dataclass
class Chunk:
    text: str
    url: str
    title: str
    score: float = 0.0


def chunk_text(text: str, size: int = 600, overlap: int = 100) -> list[str]:
    text = text.strip()
    if len(text) <= size:
        return [text] if text else []

    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + size, len(text))
        if end < len(text):
            cut = text.rfind(" ", start + size // 2, end)  
            if cut != -1:
                end = cut
        piece = text[start:end].strip()
        if piece:
            chunks.append(piece)
        if end >= len(text):
            break
        start = max(end - overlap, start + 1)
    return chunks


def rerank(
    query: str,
    chunks: list[Chunk],
    embedder: Embedder,
    top_k: int = 5,
    per_url: int = 2,
    min_score: float = 0.0,
) -> list[Chunk]:
    """Return top_k chunks by cosine sim, max `per_url` per source, best first."""
    if not chunks:
        return []

    q = embedder.embed_query(query)
    m = embedder.embed_passages([c.text for c in chunks])
    scores = m @ q
    for chunk, score in zip(chunks, scores):
        chunk.score = float(score)

    chosen: list[Chunk] = []
    used: dict[str, int] = {}
    for chunk in sorted(chunks, key=lambda c: c.score, reverse=True):
        if chunk.score < min_score:
            break
        if used.get(chunk.url, 0) >= per_url:
            continue
        chosen.append(chunk)
        used[chunk.url] = used.get(chunk.url, 0) + 1
        if len(chosen) >= top_k:
            break
    return chosen