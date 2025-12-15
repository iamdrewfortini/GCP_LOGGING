import os
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import logging
from typing import List
import argparse
from qdrant_client.http import models

from src.services.qdrant_service import qdrant_service
from src.services.embedding_service import embedding_service

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("repo_indexer")

REPO_COLLECTION_NAME = "repo_index"

def chunk_file(file_path: str) -> List[str]:
    """
    Simple placeholder for file chunking. In a real scenario, this would use a more
    sophisticated chunking strategy (e.g., LangChain TextSplitters).
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
            # For simplicity, split by double newline as a basic chunking strategy
            return [chunk.strip() for chunk in content.split('\n\n') if chunk.strip()]
    except Exception as e:
        logger.warning(f"Could not read or chunk file {file_path}: {e}")
        return []

def index_repository(repo_path: str, project_id: str, commit_hash: str = "latest"):
    if not os.path.exists(repo_path):
        logger.error(f"Repository path {repo_path} does not exist.")
        return

    logger.info(f"Starting repository indexing for {repo_path} (Commit: {commit_hash})")

    # Ensure repo_index collection exists
    # Note: This will create if not exists, but won't reconfigure if it exists
    if not qdrant_service.client:
        logger.error("Qdrant client not initialized. Exiting.")
        return

    # Check if collection exists first to avoid re-creation errors if parameters change
    collections = qdrant_service.get_collections()
    exists = any(c.name == REPO_COLLECTION_NAME for c in collections)

    if not exists:
        qdrant_service.client.create_collection(
            collection_name=REPO_COLLECTION_NAME,
            vectors_config=models.VectorParams(size=768, distance=models.Distance.COSINE),
            sparse_vectors_config={
                "text": models.SparseVectorParams() # For keyword search
            }
        )
        qdrant_service.client.create_payload_index(REPO_COLLECTION_NAME, "group_id", models.PayloadSchemaType.KEYWORD)
        qdrant_service.client.create_payload_index(REPO_COLLECTION_NAME, "file_path", models.PayloadSchemaType.KEYWORD)
        qdrant_service.client.create_payload_index(REPO_COLLECTION_NAME, "commit_hash", models.PayloadSchemaType.KEYWORD)
        logger.info(f"Created Qdrant collection: {REPO_COLLECTION_NAME}")

    indexed_files = 0
    indexed_chunks = 0

    for root, _, files in os.walk(repo_path):
        for file in files:
            file_path = os.path.join(root, file)
            # Simple exclusion for common non-code/config files or large files
            if '.git' in file_path or '.venv' in file_path or '__pycache__' in file_path or file.endswith((".pyc", ".log", ".md", ".json")):
                continue

            chunks = chunk_file(file_path)
            if not chunks:
                continue

            for i, chunk in enumerate(chunks):
                embedding = embedding_service.get_embedding(chunk) # Get dense embedding
                # TODO: Integrate sparse embedding if a sparse model is available
                
                payload = {
                    "group_id": project_id,
                    "repo_path": repo_path,
                    "file_path": os.path.relpath(file_path, repo_path),
                    "commit_hash": commit_hash,
                    "chunk_index": i,
                    "content_preview": chunk[:200] + "..." if len(chunk) > 200 else chunk
                }
                
                # Using a combination of file_path, commit_hash, and chunk_index for a unique ID
                point_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{file_path}-{commit_hash}-{i}"))

                qdrant_service.client.upsert(
                    collection_name=REPO_COLLECTION_NAME,
                    points=[
                        models.PointStruct(
                            id=point_id,
                            vector={""": embedding}, # Default dense vector
                            payload=payload
                        )
                    ]
                )
                indexed_chunks += 1
            indexed_files += 1

    logger.info(f"Finished indexing. Files: {indexed_files}, Chunks: {indexed_chunks}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Index a local repository into Qdrant.")
    parser.add_argument("--repo_path", type=str, default=".", help="Path to the repository to index.")
    parser.add_argument("--project_id", type=str, required=True, help="Project ID (tenant) for data isolation.")
    parser.add_argument("--commit_hash", type=str, default="latest", help="Git commit hash of the repository state.")
    
    args = parser.parse_args()

    # Ensure Qdrant connection is established before starting
    if not qdrant_service.client:
        qdrant_service._connect() # Attempt to connect if not already
    
    if not qdrant_service.client:
        logger.error("Could not connect to Qdrant. Exiting.")
        exit(1)

    index_repository(args.repo_path, args.project_id, args.commit_hash)
