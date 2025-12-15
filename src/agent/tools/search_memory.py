from typing import Optional, List
from langchain_core.tools import tool
from langchain_core.pydantic_v1 import BaseModel, Field

from src.services.qdrant_service import qdrant_service
from src.services.embedding_service import embedding_service

class SearchMemoryInput(BaseModel):
    query: str = Field(description="The semantic search query to find relevant memories or code.")
    project_id: str = Field(description="The project ID (tenant) to scope the search to.")
    limit: int = Field(default=5, description="Max number of results to return.")
    collection: str = Field(default="conversation_history", description="Target collection: 'conversation_history' or 'repo_index'.")

@tool("search_memory", args_schema=SearchMemoryInput)
def search_memory(query: str, project_id: str, limit: int = 5, collection: str = "conversation_history") -> str:
    """
    Searches long-term memory (Qdrant) for relevant conversation history or repository code.
    Use this to recall past decisions, errors, or find code snippets.
    """
    try:
        # 1. Generate embedding for the query
        query_vector = embedding_service.get_embedding(query)
        
        # 2. Search Qdrant
        # Note: We might need to adjust qdrant_service to allow dynamic collection selection
        # For now, we'll assume the service method defaults to conversation_history but we can override key logic if needed.
        # Actually, let's update the service or just rely on the default for now. 
        # Ideally qdrant_service.search_memory should take a collection_name.
        
        # Temporary hack: direct client access if service wrapper is too rigid, 
        # or better: we update the service. Let's assume we updated the service to accept collection_name in next step.
        # For this file, I'll call the service method. *Self-Correction*: The current service method is hardcoded to 'conversation_history'.
        
        # Let's do a direct client call here for flexibility until we refactor the service 
        # OR better, update the service method to accept `collection_name`.
        # I'll update the service in the next tool call.
        
        # Assuming service update happens, let's proceed with the ideal call:
        results = qdrant_service.search_memory(
            query_vector=query_vector,
            project_id=project_id,
            limit=limit,
            collection_name=collection
        )
        
        if not results:
            return "No relevant memories found."

        # 3. Format results
        formatted = []
        for hit in results:
            payload = hit.payload
            score = hit.score
            content = payload.get("content") or payload.get("content_preview") or "No content"
            meta = f"Score: {score:.2f} | Date: {payload.get('timestamp', {}).get('iso', 'N/A')}"
            formatted.append(f"[{meta}]\n{content}\n---")
            
        return "\n".join(formatted)

    except Exception as e:
        return f"Error searching memory: {str(e)}"