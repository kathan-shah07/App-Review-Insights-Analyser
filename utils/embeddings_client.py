"""
Embeddings client wrapper for Gemini embeddings.
"""
from __future__ import annotations

import time
from typing import Iterable, List, Sequence, Dict, Any

import google.generativeai as genai

from config.settings import settings
from utils.logger import get_logger

logger = get_logger(__name__)


class GeminiEmbeddingsClient:
    """
    Lightweight wrapper around the Gemini embedding endpoint.

    This client handles batching, retries, and returns plain Python lists
    so downstream components (Chroma, NumPy, etc.) can consume them easily.
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        batch_size: int = 32,
        retry_attempts: int | None = None,
        retry_delay: float | None = None,
    ):
        self.api_key = api_key or settings.GEMINI_API_KEY
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY is not set; cannot generate embeddings.")

        genai.configure(api_key=self.api_key)

        self.model = model or settings.GEMINI_EMBEDDING_MODEL
        self.batch_size = max(1, batch_size)
        self.retry_attempts = retry_attempts or settings.LLM_RETRY_ATTEMPTS
        self.retry_delay = retry_delay or settings.LLM_RETRY_DELAY_BASE

    def embed_texts(self, texts: Sequence[str]) -> List[List[float]]:
        """
        Generate embeddings for a list of texts using batch API for efficiency.

        Args:
            texts: Sequence of text inputs.

        Returns:
            List of embedding vectors preserving the input order.
        """
        clean_texts = [text if (text and text.strip()) else " " for text in texts]
        if not clean_texts:
            return []

        embeddings: List[List[float]] = []
        total_batches = (len(clean_texts) + self.batch_size - 1) // self.batch_size

        for batch_idx in range(0, len(clean_texts), self.batch_size):
            batch = clean_texts[batch_idx : batch_idx + self.batch_size]
            batch_num = (batch_idx // self.batch_size) + 1
            
            logger.debug(
                "Embedding batch %s/%s (%s texts)",
                batch_num,
                total_batches,
                len(batch),
            )
            
            batch_embeddings = self._embed_batch(batch)
            embeddings.extend(batch_embeddings)

        return embeddings

    def embed_reviews(self, reviews: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Embed review payloads and return enriched records.

        Args:
            reviews: Sequence of dicts containing at least `review_id` and `text`.

        Returns:
            Same metadata with an `embedding` key appended.
        """
        texts = [review.get("text", "") for review in reviews]
        vectors = self.embed_texts(texts)

        enriched: List[Dict[str, Any]] = []
        for review, vector in zip(reviews, vectors):
            enriched.append({**review, "embedding": vector})
        return enriched

    def _embed_single(self, text: str) -> List[float]:
        """Embed a single text with retries."""
        attempts = 0
        while attempts < self.retry_attempts:
            try:
                response = genai.embed_content(model=self.model, content=text)
                if isinstance(response, dict):
                    embedding = response.get("embedding") or response.get("values")
                    if embedding:
                        return embedding
                if hasattr(response, "embedding"):
                    return response.embedding
                raise ValueError("Unexpected embedding response shape.")
            except Exception as exc:
                attempts += 1
                logger.warning(
                    "Embedding call failed (attempt %s/%s): %s",
                    attempts,
                    self.retry_attempts,
                    exc,
                )
                if attempts >= self.retry_attempts:
                    raise
                time.sleep(self.retry_delay * attempts)

        return []
