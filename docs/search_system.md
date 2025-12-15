# GCP Logging Search System Architecture

## Overview
This system provides advanced semantic search, filtering, and analytics over GCP logs using Qdrant vector database and Ollama embeddings/chat.

## Data Model
- **Collection**: `logs_v1`
- **Vector**: Dense embeddings (1024-dim, Cosine distance) from qwen3-embedding:0.6b
- **Payload Schema**: See `src/schemas/log_payload_schema.py` (v1, Pydantic-validated)

## Indexing and Storage Strategy

### Payload Indexes
Payload indexes are created for frequently filtered fields to improve query planning and filtering performance via cardinality estimates.

Indexed fields:
- `tenant_id` (keyword) - For multitenancy isolation
- `service_name` (keyword) - Common service-based queries
- `severity` (keyword) - ERROR/WARNING filters
- `log_type` (keyword) - Application/system/audit types
- `timestamp_year`, `timestamp_month`, `timestamp_day`, `timestamp_hour` (integers) - Time-based slicing
- `http_status` (integer) - HTTP error codes
- `http_method` (keyword) - GET/POST etc.
- `source_table` (keyword) - BigQuery source table
- `trace_id` (keyword) - Trace correlation
- `log_id` (keyword) - Exact log lookup

Large text fields (`message`, `body`) are not keyword-indexed to avoid bloat; use semantic search instead.

### Storage Mode
- **Mode**: InMemory (default)
- **Rationale**: Log payloads are moderate size (~1-5KB per point), latency targets (p50 <150ms) prioritize speed over disk savings. For very large datasets (>10M points), consider OnDisk if memory becomes bottleneck.

### Optimizer Settings
- **HNSW**: Default parameters (ef_construct=100, m=16) suitable for log similarity. Tune `hnsw_ef` per query (semantic: 64, filtered: 32) for recall/latency tradeoffs.
- **Indexing Thresholds**: Default (memmap_threshold=1000, indexing_threshold=10000) - adjust for initial bulk loads.
- **Quantization**: None (float32 vectors) - add PQ/FP16 if memory constrained.
- **Dataset Scale**: Tested for 1M-10M logs; re-evaluate thresholds at 100M+.

## Query Patterns
- **Semantic Search**: Pure vector similarity on message/body text (use `semantic_search`).
- **Filtered Search**: Filters + vector (use `filtered_search` with `build_filter`).
- **Hybrid Search**: Prefetch dense/sparse, fuse RRF (use `hybrid_search`).
- **Grouped Search**: De-duplicate by field (use `query_groups`).
- **Formula Rescoring**: Business ranking (use `formula_rescore`, e.g., boost ERROR logs).

## Chat Tool Integration
Ollama chat supports natural language queries via tools:
- `search_logs`: Semantic/filtered search.
- `search_logs_grouped`: Grouped results.
- `get_log_by_id`: Exact lookup.
- `benchmark_query`: Latency check.
- `suggest_indexes`: Tuning advice.

## Tuning Recommendations
- Monitor query latencies; increase hnsw_ef for higher recall.
- Add more indexes if new filter patterns emerge.
- Use benchmark harness to validate changes.