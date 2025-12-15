# Vector & Queue Strategy (Redis + Qdrant)

**Date:** 2025-12-15
**Goal:** High-performance retrieval with temporal precision.

## 1. Redis (The Hot Layer)

Used for **Queues** and **Short-Term Memory**.

### Queues (List / Stream)
- `q:embeddings:realtime`: High priority. Process immediately.
- `q:indexing:repo`: Low priority. Background processing.
- `q:logs:analysis`: Batch processing of log entries.

### In-Session Embeddings
- **Key:** `session:{id}:vectors`
- **Type:** Redis Vector (if utilizing RediSearch) or simple serialized cache if Qdrant is fast enough ( < 20ms).
- **Strategy:** For this architecture, we will use Redis primarily as a *buffer* and *queue*, relying on Qdrant for the actual vector math to keep the stack simple, unless latency demands otherwise.

## 2. Qdrant (The Long-Term Layer)

### Collection: `conversation_history`
Stores every interaction.

**Point ID:** UUIDv7 (Time-sortable)
**Vector:** 768d (Gemini/Vertex) or 1536d (OpenAI).
**Payload Schema:**
```json
{
  "session_id": "uuid",
  "project_id": "string",
  "role": "user|assistant|tool",
  "content_hash": "sha256",
  "timestamp": {
    "iso": "2025-12-15T14:30:00Z",
    "year": 2025,
    "month": 12,
    "day": 15,
    "hour": 14,
    "minute": 30,
    "second": 0
  },
  "context_tags": ["billing", "error", "critical"]
}
```

### Collection: `repo_index`
Stores codebase knowledge.

**Payload Schema:**
```json
{
  "repo_id": "string",
  "commit_hash": "string",
  "file_path": "src/api/main.py",
  "line_start": 10,
  "line_end": 50,
  "symbol_type": "function|class"
}
```

## 3. Retrieval Logic

1.  **Incoming Query:** "What errors did we see yesterday?"
2.  **Time Extraction:** NLP identifies "Yesterday" -> `2025-12-14`.
3.  **Qdrant Filter:**
    ```python
    Filter(
        must=[
            FieldCondition(key="project_id", match=MatchValue(value="current_proj")),
            FieldCondition(key="timestamp.year", match=MatchValue(value=2025)),
            FieldCondition(key="timestamp.month", match=MatchValue(value=12)),
            FieldCondition(key="timestamp.day", match=MatchValue(value=14))
        ]
    )
    ```
4.  **Semantic Search:** Vector Search within that time window.