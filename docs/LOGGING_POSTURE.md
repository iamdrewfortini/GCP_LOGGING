# GCP Logging Posture

## Overview
This document describes the current logging topology for Diatonic AI's GCP environment.

## 1. Ingestion Strategy
We utilize **Organization-level Logging Sinks** to aggregate logs from all child projects into a central observability project (`diatonic-ai-gcp`).

| Sink Name | Destination | Filter | Purpose |
| :--- | :--- | :--- | :--- |
| `org-central-sink-bq` | BigQuery: `central_logging_v1` | `severity >= INFO` | **Hot Path:** Analytics, Glass Pane UI, Debugging. |
| `org-central-sink-gcs` | GCS: `dacvisuals-central-logs-archive-v1` | `severity >= INFO` | **Cold Path:** Compliance, Long-term Retention (1 year). |
| `org-central-sink-alerts` | Pub/Sub: `logging-critical-alerts` | `severity >= ERROR` | **Real-time:** Triggering alerts and automated remediation functions. |

## 2. Storage & Schema (BigQuery)
- **Dataset:** `central_logging_v1`
- **Table Strategy:** **Partitioned Tables** (`--use-partitioned-tables`).
  - Tables are created based on the log name (e.g., `syslog`, `cloudaudit_googleapis_com_activity`).
  - Tables are **partitioned by day** (ingestion time) to optimize cost and performance for time-range queries.
- **Schema Challenges:**
  - `jsonPayload` schema varies by log source.
  - Currently, `jsonPayload` is often cast to `STRING` to enable `UNION` operations across disparate tables.

## 3. Query & Consumption
- **Current Pattern:** The Glass Pane application dynamically queries `INFORMATION_SCHEMA.TABLES` to discover active log tables and constructs a `UNION ALL` query at runtime.
- **Pain Points:** 
  - Latency in discovery.
  - Complexity in "blind" UNIONs (potential for schema mismatch errors).
  - Lack of standardized fields (normalization).

## 4. Recommendations
- Move to a **Canonical View** that handles the `UNION` and normalization once, exposing a consistent interface (`CanonicalLogEvent`) to the application layer.
- Ensure all queries filter on `timestamp` (the partitioning column) to prune bytes processed.
