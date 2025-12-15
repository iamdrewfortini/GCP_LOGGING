# Audit Report: Current State of GCP Logging Qdrant + Ollama Integration

## Qdrant Status
- **Version**: 1.16.2 (commit d2834de0b51be23a7b22b023e424cbb9456d0e75)
- **URL**: http://localhost:6333
- **Collections**: None (fresh instance)
- **Notes**: No existing collections. Current code uses 'conversation_history' and 'logs_embedded' in different scripts.

## Ollama Status
- **Base URL**: http://localhost:11434
- **Available Models**:
  - qwen3-embedding:0.6b (dim: unknown, but qwen3 family)
  - nomic-embed-text:latest (dim: 768, tested)
  - gcp-db-agent:latest (qwen2 family)
  - qwen2.5:7b
  - llama2:latest
  - llama3.2:1b
- **API Endpoints**: /api/embed and /api/chat reachable.
- **Notes**: Spec requires 'embeddinggemma' and 'gemma3', but not available. Using 'nomic-embed-text' for embeddings in existing scripts.

## Existing Code Inventory
### Ingestion + Embedding
- `scripts/batch_embed_logs_to_qdrant.py`: Fetches logs from BigQuery, normalizes, embeds via Ollama (`nomic-embed-text`), upserts to 'logs_embedded' collection. Includes chunking, batching, checkpointing.
- Maps to: ingest.normalizer (partial), embed.ollama (OllamaEmbedder class), store.qdrant_writer (upsert logic).

### Query Services
- `src/services/qdrant_service.py`: Basic Qdrant client for 'conversation_history' collection. Supports create collection, upsert, search (basic).
- `src/services/qdrant_optimized.py`: Additional Qdrant ops.
- Maps to: store.qdrant_writer (partial), query.engine (basic search, needs universal query API).

### Embedding Services
- `src/services/embedding_service.py`: Vertex AI embeddings (text-embedding-004).
- `src/workers/embedding_worker.py`: Related to embedding queue.
- Notes: Spec requires Ollama, not Vertex. Existing Ollama embedding only in scripts.

### Chat + Tools
- `scripts/ollama_db_agent.py`: Ollama chat with tool calling for DB access (BigQuery, Firestore, Redis, Qdrant).
- Maps to: agent.continuous_optimizer (partial, has tool loop).

### Other
- Benchmark harness: None yet.
- Schema validators: None yet.
- Continuous optimizer: None yet.

## Gaps vs Spec
- No canonical payload schema validators.
- No universal Query API wrapper (filters, prefetch, hybrid, formulas, groups).
- No benchmark tables or harness.
- No versioned migrations.
- Embedding service needs to be Ollama-based, not Vertex.
- Collection naming: spec wants 'logs_v1', existing 'logs_embedded'.

## Recommendations
- Refactor embedding to Ollama service in src/services/.
- Implement universal query engine using /points/query endpoint.
- Add payload schema validation.
- Create benchmark harness with tables.
- Pull required Ollama models (embeddinggemma, gemma3) or adjust spec to use available ones.