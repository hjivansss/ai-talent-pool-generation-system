# Embedding service — generates vector embeddings via Ollama nomic-embed-text.
# Used for semantic similarity between JD and candidate profiles.
# Results cached in memory to avoid re-embedding the same text twice per session.

import logging
import httpx
from app.core.config import settings

logger = logging.getLogger(__name__)

_cache: dict[str, list[float]] = {}

EMBED_MODEL = "nomic-embed-text"


class EmbeddingService:

    async def embed(self, text: str) -> list[float] | None:
        """
        Returns a 768-dim embedding vector for the given text.
        Returns None if the Ollama embedding model is unavailable — but logs why.
        """
        if not text or not text.strip():
            logger.warning("[EmbeddingService] empty text passed to embed(), skipping.")
            return None

        key = text[:200]
        if key in _cache:
            return _cache[key]

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(
                    f"{settings.OLLAMA_URL}/api/embeddings",
                    json={"model": EMBED_MODEL, "prompt": text},
                )
                response.raise_for_status()
            data = response.json()
            vector = data.get("embedding")
            if not vector:
                logger.error(
                    "[EmbeddingService] Ollama returned no 'embedding' field. Response: %s",
                    data,
                )
                return None
            if len(vector) != 768:
                logger.error(
                    "[EmbeddingService] Unexpected embedding dim %d (expected 768) — "
                    "model '%s' may not be nomic-embed-text. Check your OLLAMA setup.",
                    len(vector), EMBED_MODEL,
                )
                return None
            _cache[key] = vector
            return vector
        except httpx.ConnectError as e:
            logger.error(
                "[EmbeddingService] Could not connect to Ollama at %s — is it running? (%s)",
                settings.OLLAMA_URL, e,
            )
            return None
        except httpx.HTTPStatusError as e:
            logger.error(
                "[EmbeddingService] Ollama returned HTTP %s for model '%s'. "
                "Likely the model isn't pulled — run: ollama pull %s. Body: %s",
                e.response.status_code, EMBED_MODEL, EMBED_MODEL, e.response.text,
            )
            return None
        except Exception as e:
            logger.error("[EmbeddingService] Unexpected embed failure: %s", e, exc_info=True)
            return None

    def cosine_similarity(self, a: list[float], b: list[float]) -> float:
        """Cosine similarity between two vectors. Returns 0.0 on error."""
        try:
            dot = sum(x * y for x, y in zip(a, b))
            norm_a = sum(x ** 2 for x in a) ** 0.5
            norm_b = sum(x ** 2 for x in b) ** 0.5
            if norm_a == 0 or norm_b == 0:
                return 0.0
            return dot / (norm_a * norm_b)
        except Exception:
            return 0.0

    def build_candidate_text(self, candidate) -> str:
        """Builds a rich text representation of a UnifiedCandidate for embedding."""
        parts = [
            candidate.name or "",
            candidate.current_role or "",
            candidate.current_company or "",
            " ".join(candidate.skills[:20]),
            " ".join(candidate.certifications or []),
            candidate.domain_inferred or "",
        ]
        for exp in (candidate.experience or [])[:3]:
            if hasattr(exp, "title"):
                parts.append(f"{exp.title} at {exp.company}")
        return " ".join(p for p in parts if p).strip()

    def build_jd_text(self, jd) -> str:
        """Builds a rich text representation of a JobDescription for embedding."""
        parts = [
            jd.job_role,
            jd.seniority_level or "",
            " ".join(jd.required_skills or []),
            " ".join(jd.nice_to_have_skills or []),
            " ".join(jd.tools_and_platforms or []),
            " ".join((jd.key_responsibilities or [])[:3]),
            jd.domain or "",
        ]
        return " ".join(p for p in parts if p).strip()


embedding_service = EmbeddingService()