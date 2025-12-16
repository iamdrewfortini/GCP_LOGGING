import os
import logging
import threading
from typing import List, Optional

from src.glass_pane.config import glass_config

logger = logging.getLogger(__name__)


def _vertex_enabled() -> bool:
    """Whether Vertex AI calls are enabled.

    Defaults to disabled so CI/tests never depend on Vertex/ADC.
    """
    return os.getenv("VERTEX_ENABLED", "false").lower() == "true"


class EmbeddingService:
    def __init__(self):
        # Config is safe to read at import; initialization must be lazy.
        self.project_id = glass_config.logs_project_id
        self.location = os.getenv("REGION", "us-central1")
        self.model_name = os.getenv("EMBEDDING_MODEL", "text-embedding-004")
        self.embedding_dim = int(os.getenv("EMBEDDING_DIM", "768"))

        self._model = None
        self._init_error: Optional[Exception] = None
        self._lock = threading.Lock()

    def _init_vertex(self) -> None:
        if self._model is not None:
            return

        if not _vertex_enabled():
            return

        with self._lock:
            if self._model is not None:
                return
            if self._init_error is not None:
                return

            try:
                import vertexai
                from vertexai.language_models import TextEmbeddingModel

                vertexai.init(project=self.project_id, location=self.location)
                self._model = TextEmbeddingModel.from_pretrained(self.model_name)
                logger.info(
                    f"Vertex AI Embedding Model '{self.model_name}' initialized for project '{self.project_id}'."
                )
            except Exception as e:
                self._init_error = e
                logger.warning(f"Failed to initialize Vertex AI embeddings: {e}")
                self._model = None

    def _zero_vector(self) -> List[float]:
        return [0.0] * self.embedding_dim

    def get_embedding(self, text: str) -> List[float]:
        """Generate an embedding for the given text.

        This is designed to be safe in CI:
        - If Vertex is disabled/unavailable, returns a zero vector.
        """
        if not text or not text.strip():
            logger.debug("Empty text provided for embedding")
            return self._zero_vector()

        self._init_vertex()
        if not self._model:
            return self._zero_vector()

        try:
            from vertexai.language_models import TextEmbeddingInput

            inputs = [TextEmbeddingInput(text, "SEMANTIC_SIMILARITY")]
            embeddings = self._model.get_embeddings(inputs)

            if not embeddings:
                return self._zero_vector()

            values = embeddings[0].values
            if not values:
                return self._zero_vector()

            # Update dimension from actual response (optional, but keeps zero-vectors consistent).
            self.embedding_dim = len(values)
            return values

        except Exception as e:
            logger.warning(f"Error generating embedding with Vertex AI: {e}")
            return self._zero_vector()

    def get_embeddings_batch(self, texts: List[str]) -> List[List[float]]:
        """Batch embedding generation.

        Returns a list of vectors aligned to `texts`.
        """
        if not texts:
            return []

        self._init_vertex()
        if not self._model:
            return [self._zero_vector() for _ in texts]

        # Build inputs for valid texts, keep index mapping.
        valid_inputs = []
        valid_indices = []
        for idx, t in enumerate(texts):
            if t and t.strip():
                valid_indices.append(idx)
                valid_inputs.append(t)

        # Default all outputs to zeros.
        out: List[List[float]] = [self._zero_vector() for _ in texts]
        if not valid_inputs:
            return out

        try:
            from vertexai.language_models import TextEmbeddingInput

            BATCH_SIZE = 5
            cursor = 0
            for start in range(0, len(valid_inputs), BATCH_SIZE):
                batch_texts = valid_inputs[start : start + BATCH_SIZE]
                batch_inputs = [TextEmbeddingInput(t, "SEMANTIC_SIMILARITY") for t in batch_texts]
                results = self._model.get_embeddings(batch_inputs)

                for r in results:
                    if cursor >= len(valid_indices):
                        break
                    out[valid_indices[cursor]] = r.values or self._zero_vector()
                    cursor += 1

            return out

        except Exception as e:
            logger.warning(f"Error generating batch embeddings: {e}")
            return [self._zero_vector() for _ in texts]

embedding_service = EmbeddingService()
