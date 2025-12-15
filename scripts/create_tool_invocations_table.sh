#!/bin/bash
# Create tool_invocations table in BigQuery
# Phase 3, Task 3.3: Add tool_invocations BigQuery table

set -e

PROJECT_ID="${PROJECT_ID:-diatonic-ai-gcp}"
DATASET="chat_analytics"
TABLE="tool_invocations"
SCHEMA_FILE="schemas/bigquery/tool_invocations.json"

echo "Creating tool_invocations table in ${PROJECT_ID}:${DATASET}.${TABLE}"

# Create table with partitioning and clustering
bq mk \
  --table \
  --project_id="${PROJECT_ID}" \
  --time_partitioning_field=started_at \
  --time_partitioning_type=DAY \
  --time_partitioning_expiration=220752000 \
  --clustering_fields=tool_name,status,session_id \
  --description="Tool invocation metrics for agent runs" \
  "${PROJECT_ID}:${DATASET}.${TABLE}" \
  "${SCHEMA_FILE}"

echo "✅ Table created successfully"
echo ""
echo "Table details:"
bq show "${PROJECT_ID}:${DATASET}.${TABLE}"
