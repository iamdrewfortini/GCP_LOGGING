# Risks & Mitigations

**Date:** 2025-12-15

## 1. Security Risks

| Risk | Mitigation |
| :--- | :--- |
| **Prompt Injection** | Strict separation of System/User prompts. Policy enforcement on tool inputs. |
| **Data Leakage (Logs)** | Redaction Middleware for all Tool I/O. PII scanning before BQ write. |
| **Excessive Permissions** | Tools use "On-Behalf-Of" (OBO) flow where possible. Read-only Service Accounts for BQ. |

## 2. Cost Risks

| Risk | Mitigation |
| :--- | :--- |
| **LLM Token Costs** | Implement strict context window management (summarization). Cache common queries. |
| **BigQuery Analysis** | Enforce `max_bytes_billed` per query. Partition tables by day. |
| **Vector Storage** | Use "Standard" tier for Vertex AI. Clean up old sessions/indices. |

## 3. Performance Risks

| Risk | Mitigation |
| :--- | :--- |
| **Cold Starts** | Keep one Cloud Run instance warm (min-instances=1). |
| **Stream Latency** | Use optimistic UI updates. Ensure SSE buffer is flushed immediately. |
| **Embedding Lag** | Use separate queues for "User Message" (High Priority) vs "Repo Index" (Low Priority). |

## 4. Data Integrity

| Risk | Mitigation |
| :--- | :--- |
| **Hallucination** | Force Tool use for factual queries. Implement "Verifier" node in Graph. |
| **Stale Context** | Clear session context on specific triggers ("New Topic"). |
