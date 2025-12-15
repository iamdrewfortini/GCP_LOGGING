# Schema/Index Change Playbook

## Overview
This document outlines the safe, versioned process for evolving the log schema, indexes, and query optimizations in the GCP Logging Search System.

## Principles
- **No Silent Schema Drift**: All changes are versioned and validated.
- **Benchmark-Gated**: Changes only land if benchmarks pass regression gates.
- **Reversible**: Changes can be rolled back via Qdrant collection recreation or point updates.
- **Incremental**: Apply changes in small, testable increments.

## Process
1. **Propose Change**: From benchmark analysis or user requirements.
2. **Validate**: Run what-if benchmarks or simulations.
3. **Apply**: Update schema, indexes, or defaults.
4. **Test**: Full benchmark suite + integration tests.
5. **Log**: Record in `schema_changes` table with `validated_by_run_id`.
6. **Monitor**: Watch for regressions in production metrics.

## Change Types

### Payload Schema Changes
- **Adding Fields**: Safe, add to `LogPayloadV1` model, update normalization.
- **Removing Fields**: Deprecate first, then remove after migration.
- **Type Changes**: Requires re-indexing collection.
- **Process**:
  1. Update Pydantic model.
  2. Run migration script to update existing points (if needed).
  3. Update version in SCHEMA_VERSION.
  4. Validate with benchmarks.

### Index Changes
- **Adding Indexes**: Use `QdrantLogWriter._ensure_collection` or optimizer agent.
- **Removing Indexes**: Drop via Qdrant API if no longer needed.
- **Process**:
  1. Propose via continuous optimizer.
  2. Apply if validation passes.
  3. Log change.

### Vector/Collection Config Changes
- **HNSW Tuning**: Update defaults in query engine.
- **Quantization**: Add PQ/FP16 for memory savings.
- **Sparse Vectors**: Enable for hybrid search.
- **Process**:
  1. Test on subset.
  2. Apply to collection.
  3. Re-run benchmarks.

### Query Defaults Changes
- **hnsw_ef Adjustments**: Update per-scenario defaults.
- **Formula Changes**: Add business logic reranking.
- **Process**:
  1. Update in `QdrantQueryEngine`.
  2. Validate quality improvements.

## Migration Scripts
- **Data Migration**: If schema changes, use Qdrant scroll + upsert to update points.
- **Index Rebuild**: Qdrant handles automatically on index add.
- **Rollback**: Recreate collection from backup if needed.

## Examples
- **Add Index for `user_id`**: Propose via optimizer, apply, log.
- **Increase hnsw_ef to 128**: Validate recall improvement, apply default.
- **Add ERROR Boost Formula**: Test on sample queries, apply.

## Monitoring
- Track latency/quality in bench tables.
- Alert on regressions >10% P50 or >5% recall drop.
- Use continuous optimizer for automation.