import os
import logging
from typing import List, Optional
import vertexai
from vertexai.language_models import TextEmbeddingModel, TextEmbeddingInput

from src.glass_pane.config import glass_config

logger = logging.getLogger(__name__)

class EmbeddingService:
    def __init__(self):
        self.project_id = glass_config.logs_project_id
        # Default region to us-central1 if not set
        self.location = os.getenv("REGION", "us-central1")
        # Using text-embedding-004 as the latest stable model, fallback to gecko if needed
        self.model_name = os.getenv("EMBEDDING_MODEL", "text-embedding-004")
        self._model: Optional[TextEmbeddingModel] = None
        self._init_vertex()

    def _init_vertex(self):
        try:
            # Initialize Vertex AI SDK
            vertexai.init(project=self.project_id, location=self.location)
            self._model = TextEmbeddingModel.from_pretrained(self.model_name)
            logger.info(f"Vertex AI Embedding Model '{self.model_name}' initialized for project '{self.project_id}'.")
        except Exception as e:
            logger.error(f"Failed to initialize Vertex AI: {e}")
            self._model = None

    def get_embedding(self, text: str) -> List[float]:
        """
        Generates an embedding for the given text using Vertex AI.
        Returns a 768-dimensional vector (or whatever the model outputs).
        """
        if not self._model:
            # Try to re-init if it failed previously (e.g. transient network issue at startup)
            self._init_vertex()
            if not self._model:
                logger.error("Vertex AI model not available. Returning zero vector.")
                return [0.0] * 768

        if not text or not text.strip():
            logger.warning("Empty text provided for embedding.")
            return [0.0] * 768

        try:
            # Vertex AI expects a list of inputs. 
            # task_type="SEMANTIC_SIMILARITY" is standard for vector search/clustering.
            inputs = [TextEmbeddingInput(text, "SEMANTIC_SIMILARITY")]
            embeddings = self._model.get_embeddings(inputs)
            
            if not embeddings:
                logger.error("No embeddings returned from Vertex AI.")
                return [0.0] * 768
                
            return embeddings[0].values

        except Exception as e:
            logger.error(f"Error generating embedding with Vertex AI: {e}")
            # Return zero vector to allow processing to continue, but data will be unsearchable
            return [0.0] * 768

    def get_embeddings_batch(self, texts: List[str]) -> List[List[float]]:
        """
        Batch generation for efficiency (up to 5 inputs per request usually for Vertex).
        """
        if not self._model:
            self._init_vertex()
            if not self._model:
                return [[0.0] * 768 for _ in texts]

        valid_texts = [t for t in texts if t and t.strip()]
        if not valid_texts:
            return [[0.0] * 768 for _ in texts]

        try:
            # Vertex AI batch limit is often 5 or 250 tokens. 
            # We'll just pass the list and let the SDK/API handle (or chunk if we were fancy).
            # For now, simplistic implementation.
            inputs = [TextEmbeddingInput(t, "SEMANTIC_SIMILARITY") for t in texts]
            # Note: get_embeddings accepts a list. 
            # If the list is too long, this might fail. 
            # A real production implementation should chunk this list into batches of 5.
            
            BATCH_SIZE = 5
            all_embeddings = []
            
            for i in range(0, len(inputs), BATCH_SIZE):
                batch = inputs[i : i + BATCH_SIZE]
                results = self._model.get_embeddings(batch)
                all_embeddings.extend([r.values for r in results])
                
            return all_embeddings

        except Exception as e:
            logger.error(f"Error generating batch embeddings: {e}")
            return [[0.0] * 768 for _ in texts]

embedding_service = EmbeddingService()
