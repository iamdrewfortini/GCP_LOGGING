# ADR 0001: Log Storage & Query Strategy

## Status
Accepted

## Context
We need to evolve the "Glass Pane" logging tool into a sophisticated AI-assisted platform. The current implementation relies on dynamic, brittle `UNION ALL` queries across raw BigQuery sink tables. We evaluated moving to Cloud Logging "Log Analytics" (linked dataset) versus optimizing the current BigQuery Sink approach.

## Options Considered

### Option A: Cloud Logging "Log Analytics" (Linked Dataset)
- **Pros:** Unified management in Cloud Logging UI; standard `_AllLogs` view; SQL access managed by GCP.
- **Cons:** Requires changing the Org-level sink configuration (infra change); potential migration downtime; different pricing model for Log Analytics buckets.

### Option B: Optimized BigQuery Sink (Partitioned Tables) + Canonical View
- **Pros:** Leveraging existing infrastructure (no sink recreation needed); full control over the `VIEW` logic; effectively zero cost for the `VIEW` definition itself; standard BQ pricing.
- **Cons:** We must maintain the `UNION` logic in the View manually (or via a script).

## Decision
We choose **Option B: Optimized BigQuery Sink + Canonical View**.

**Rationale:**
1.  **Stability:** We avoid modifying the Organization-level logging sink, which is a critical infrastructure component.
2.  **Performance:** The existing sink uses `--use-partitioned-tables`, which is the performant standard.
3.  **Control:** Defining our own `CanonicalLogView` allows us to normalize fields (e.g., `trace`, `spanId`, `jsonPayload`) exactly how our AI agent needs them, without being locked into the `_AllLogs` schema.

## Implementation Plan
1.  **Inventory:** Identify the most active tables (e.g., `syslog`, `cloudaudit`, `nginx_access`).
2.  **View Definition:** Create a `CREATE OR REPLACE VIEW` SQL script that unions these tables and normalizes columns into a `CanonicalLogEvent` schema.
3.  **Application Update:** Refactor `main.py` to query this View instead of dynamic discovery.
