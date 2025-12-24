import os
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import logging
from src.services.qdrant_service import qdrant_service
from qdrant_client.http import models

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("test_qdrant_collection")

REPO_COLLECTION_NAME = "repo_index"

def test_collection_creation():
    if not qdrant_service.client:
        qdrant_service._connect()
    
    if not qdrant_service.client:
        logger.error("Qdrant client not initialized.")
        return False

    try:
        # Check if collection exists first
        collections = qdrant_service.get_collections()
        exists = any(c.name == REPO_COLLECTION_NAME for c in collections)

        if exists:
            logger.info(f"Collection '{REPO_COLLECTION_NAME}' already exists. Skipping creation.")
            return True
            
        # Attempt to create collection
        qdrant_service.client.create_collection(
            collection_name=REPO_COLLECTION_NAME,
            vectors_config=models.VectorParams(size=768, distance=models.Distance.COSINE),
            sparse_vectors_config={
                "text": models.SparseVectorParams() # For keyword search
            }
        )
        # Create payload indexes
        qdrant_service.client.create_payload_index(REPO_COLLECTION_NAME, "group_id", models.PayloadSchemaType.KEYWORD)
        qdrant_service.client.create_payload_index(REPO_COLLECTION_NAME, "file_path", models.PayloadSchemaType.KEYWORD)
        qdrant_service.client.create_payload_index(REPO_COLLECTION_NAME, "commit_hash", models.PayloadSchemaType.KEYWORD)
        logger.info(f"Successfully created Qdrant collection: {REPO_COLLECTION_NAME}")
        return True
    except Exception as e:
        logger.error(f"Error creating collection {REPO_COLLECTION_NAME}: {e}")
        return False

if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    if test_collection_creation():
        logger.info("Qdrant collection test passed.")
    else:
        logger.error("Qdrant collection test failed.")
