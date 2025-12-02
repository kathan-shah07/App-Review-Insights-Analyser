"""
Gemini LLM client that powers cluster-aware theme classification.
"""
from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from typing import Any, Dict, List, Sequence, Tuple

import chromadb
import google.generativeai as genai
import numpy as np
from datetime import datetime

try:  # pragma: no cover - optional dependency
    import hdbscan  # type: ignore
except ImportError:  # pragma: no cover - executed only when hdbscan missing
    hdbscan = None
    from sklearn.cluster import DBSCAN

from config.settings import settings
from utils.embeddings_client import GeminiEmbeddingsClient
from utils.logger import get_logger

logger = get_logger(__name__)


class LLMClient:
    """Wrapper that handles Gemini text generation and cluster labeling."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        generation_config: Dict[str, Any] | None = None,
    ):
        self.api_key = api_key or settings.GEMINI_API_KEY
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY is not set; cannot initialize LLM client.")

        genai.configure(api_key=self.api_key)

        self.model_name = model or settings.GEMINI_MODEL
        self.generation_config = generation_config or {
            "temperature": 0.2,
            "top_p": 0.9,
            "top_k": 40,
        }
        self.model = genai.GenerativeModel(
            model_name=self.model_name,
            generation_config=genai.types.GenerationConfig(**self.generation_config),
        )
        self.embedding_client = GeminiEmbeddingsClient(api_key=self.api_key)
        self.chroma_client = chromadb.PersistentClient(path=settings.CHROMA_DB_DIR)
        self.chroma_collection = self.chroma_client.get_or_create_collection(
            name="review_embeddings",
            metadata={"hnsw:space": "cosine"},
        )

    def generate(self, prompt: str) -> str:
        """Generate raw text from the Gemini model."""
        response = self.model.generate_content(prompt)
        return getattr(response, "text", "") or ""

    def classify_reviews(
        self,
        reviews: Sequence[Dict[str, Any]],
        themes: Sequence[str],
        theme_descriptions: Dict[str, str] | None = None,
        fallback_theme: str | None = None,
    ) -> List[Dict[str, Any]]:
        """
        Classify reviews into predefined themes using embeddings + HDBSCAN + Gemini.
        """
        if not reviews:
            return []

        fallback = fallback_theme or (themes[0] if themes else "Other")

        try:
            enriched = self._embed_and_store(reviews)
            cluster_records = self._assign_clusters(enriched)
            contexts = self._build_cluster_contexts(cluster_records)
            cluster_labels = self._label_clusters_with_llm(
                contexts,
                themes,
                theme_descriptions or {},
                fallback,
            )
            return self._expand_cluster_labels(cluster_records, cluster_labels, fallback)
        except Exception as exc:  # pragma: no cover - defensive fallback
            logger.error("Gemini classification failed, using fallback: %s", exc, exc_info=True)
            return [
                {
                    "review_id": review.get("review_id", f"review_{idx}"),
                    "chosen_theme": fallback,
                    "short_reason": "Fallback classification due to runtime error.",
                }
                for idx, review in enumerate(reviews)
            ]

    # --------------------------------------------------------------------- #
    # Embeddings + vector store helpers
    # --------------------------------------------------------------------- #
    def _embed_and_store(self, reviews: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Embed reviews and cache them in Chroma for traceability."""
        enriched = self.embedding_client.embed_reviews(reviews)

        ids = [record.get("review_id", str(idx)) for idx, record in enumerate(enriched)]
        self.chroma_collection.add(
            ids=ids,
            documents=[record.get("text", "") for record in enriched],
            embeddings=[record["embedding"] for record in enriched],
            metadatas=[
                {
                    "platform": record.get("platform"),
                    "date": _ensure_iso(record.get("date")),
                }
                for record in enriched
            ],
        )

        # Clean up embeddings for this batch to keep the collection lean.
        try:
            self.chroma_collection.delete(ids=ids)
        except Exception as exc:  # pragma: no cover - best effort cleanup
            logger.debug("Failed to delete Chroma records: %s", exc)

        return enriched

    def _assign_clusters(self, records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Assign cluster IDs using HDBSCAN."""
        if len(records) <= 1:
            for record in records:
                record["cluster_id"] = 0
                record["cluster_score"] = 1.0
            return records

        embeddings = np.array([record["embedding"] for record in records])
        min_cluster_size = min(settings.HDBSCAN_MIN_CLUSTER_SIZE, len(records))
        min_samples = min(settings.HDBSCAN_MIN_SAMPLES, max(1, len(records) - 1))

        if hdbscan is not None:
            clusterer = hdbscan.HDBSCAN(
                min_cluster_size=max(2, min_cluster_size),
                min_samples=max(1, min_samples),
                metric="euclidean",
            )
            labels = clusterer.fit_predict(embeddings)
            probabilities = getattr(clusterer, "probabilities_", [1.0] * len(records))
        else:
            logger.warning(
                "HDBSCAN is unavailable. Falling back to DBSCAN. "
                "Install the 'hdbscan' wheel with Microsoft C++ Build Tools for better clustering."
            )
            eps = self._estimate_eps(embeddings)
            clusterer = DBSCAN(eps=eps, min_samples=max(1, min_samples), metric="euclidean")
            labels = clusterer.fit_predict(embeddings)
            probabilities = [1.0] * len(records)

        for record, label, probability in zip(records, labels, probabilities):
            record["cluster_id"] = int(label)
            record["cluster_score"] = float(probability)
        return records

    # --------------------------------------------------------------------- #
    # Cluster summarization + prompting
    # --------------------------------------------------------------------- #
    def _build_cluster_contexts(self, clustered: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Summarize each cluster for prompt conditioning."""
        grouped = defaultdict(list)
        for record in clustered:
            grouped[record.get("cluster_id", -1)].append(record)

        contexts: List[Dict[str, Any]] = []
        for cluster_id, items in grouped.items():
            snippets = [item.get("text", "")[:220] for item in items[:3]]
            keywords = self._extract_keywords([item.get("text", "") for item in items])
            avg_prob = sum(item.get("cluster_score", 0.0) for item in items) / max(1, len(items))

            contexts.append(
                {
                    "cluster_id": int(cluster_id),
                    "size": len(items),
                    "snippets": snippets,
                    "keywords": keywords,
                    "avg_confidence": round(avg_prob, 3),
                }
            )

        contexts.sort(key=lambda ctx: ctx["size"], reverse=True)
        return contexts[: settings.MAX_THEME_CLUSTERS]

    def _estimate_eps(self, embeddings: np.ndarray) -> float:
        """Heuristic epsilon for DBSCAN fallback."""
        if len(embeddings) <= 1:
            return 0.5
        centroid = np.mean(embeddings, axis=0)
        distances = np.linalg.norm(embeddings - centroid, axis=1)
        eps = float(np.median(distances))
        return max(eps, 0.3)

    def _extract_keywords(self, texts: Sequence[str]) -> List[str]:
        """Very lightweight keyword extractor for cluster descriptions."""
        token_pattern = re.compile(r"[A-Za-z]{3,}")
        counts: Counter[str] = Counter()
        for text in texts:
            counts.update(token_pattern.findall(text.lower()))
        return [word for word, _ in counts.most_common(6)]

    def _label_clusters_with_llm(
        self,
        contexts: Sequence[Dict[str, Any]],
        themes: Sequence[str],
        theme_descriptions: Dict[str, str],
        fallback_theme: str,
    ) -> Dict[int, Tuple[str, str]]:
        """Use Gemini to map clusters to predefined themes."""
        if not contexts:
            return {}

        theme_block = "\n".join(
            f"- {theme}: {theme_descriptions.get(theme, 'No description provided.')}"
            for theme in themes
        )

        cluster_block = ""
        for ctx in contexts:
            snippet_block = "\n    ".join(f"• {snippet}" for snippet in ctx["snippets"])
            keyword_block = ", ".join(ctx["keywords"]) or "general experience"
            cluster_block += (
                f"\nCluster {ctx['cluster_id']} (size={ctx['size']}, confidence={ctx['avg_confidence']}):\n"
                f"  Keywords: {keyword_block}\n"
                f"  Snippets:\n    {snippet_block}\n"
            )

        prompt = f"""
You are an insights analyst. Map each review cluster to ONE of the predefined product themes.
Themes:\n{theme_block}\n
Return a JSON array. Each object MUST have:
  - "cluster_id": integer
  - "chosen_theme": exact theme name from the list above
  - "short_reason": <=20 words

Clusters to label:{cluster_block}
"""
        raw = self.generate(prompt)
        parsed = self._safe_json_load(raw)

        cluster_labels: Dict[int, Tuple[str, str]] = {}
        for entry in parsed:
            cluster_id = int(entry.get("cluster_id", -1))
            theme = entry.get("chosen_theme", fallback_theme)
            reason = entry.get("short_reason", "LLM did not return a reason.")
            if theme not in themes:
                theme = fallback_theme
                reason = f"Fallback applied because '{entry.get('chosen_theme')}' is invalid."
            cluster_labels[cluster_id] = (theme, reason)

        # Ensure every context has a label.
        for ctx in contexts:
            cluster_id = ctx["cluster_id"]
            if cluster_id not in cluster_labels:
                cluster_labels[cluster_id] = (
                    fallback_theme,
                    "Fallback label because Gemini skipped this cluster.",
                )

        return cluster_labels

    def _safe_json_load(self, text: str) -> List[Dict[str, Any]]:
        """Best-effort JSON parsing that ignores Markdown fences."""
        cleaned = text.strip()
        if "```" in cleaned:
            segments = [segment.strip() for segment in cleaned.split("```") if segment.strip()]
            for segment in segments:
                if segment.startswith("{") or segment.startswith("["):
                    cleaned = segment
                    break
        cleaned = cleaned.strip()
        try:
            data = json.loads(cleaned)
            if isinstance(data, list):
                return data
        except json.JSONDecodeError:
            logger.debug("Failed to parse JSON, defaulting to empty list. Payload: %s", cleaned)
        return []

    def _expand_cluster_labels(
        self,
        clustered: Sequence[Dict[str, Any]],
        cluster_labels: Dict[int, Tuple[str, str]],
        fallback_theme: str,
    ) -> List[Dict[str, Any]]:
        """Map cluster-level labels back to each review."""
        results: List[Dict[str, Any]] = []
        for record in clustered:
            cluster_id = record.get("cluster_id", -1)
            theme, reason = cluster_labels.get(
                cluster_id,
                (fallback_theme, "Fallback label because cluster had no assignment."),
            )
            results.append(
                {
                    "review_id": record.get("review_id"),
                    "chosen_theme": theme,
                    "short_reason": reason,
                    "cluster_id": cluster_id,
                    "cluster_confidence": record.get("cluster_score", 0.0),
                }
            )
        return results


def _ensure_iso(value: Any) -> Any:
    """Convert datetime objects to ISO strings."""
    if isinstance(value, datetime):
        return value.isoformat()
    return value

