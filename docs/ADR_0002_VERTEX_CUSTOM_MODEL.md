# ADR 0002: Vertex AI Deployment Pattern

## Status
Accepted

## Context
The application requires AI capabilities for log summarization, root cause analysis, and natural language querying of logs. We need to decide between:
1.  **Custom Model Deployment**: Training/fine-tuning a model (e.g., Llama 2, Mistral) and deploying it to a Vertex AI Endpoint using Custom Prediction Routines (CPR).
2.  **Foundation Model (Publisher Model)**: Using Google's pre-trained Gemini models directly via the Vertex AI API.

## Decision
We will use **Gemini Foundation Models (Publisher Model)** via the Vertex AI API.

## Rationale
1.  **Simplicity**: No need to manage infrastructure, Docker containers, or model servers.
2.  **Cost**: Pay-per-character/image rather than paying for 24/7 provisioned compute nodes (endpoints) which are required for custom models.
3.  **Performance**: Gemini Pro 1.5 is state-of-the-art for context retention (long context window for logs) and reasoning.
4.  **Maintenance**: Google manages the model updates and availability.

## Consequences
-   We will not use `gcloud ai endpoints create` in the infrastructure scripts.
-   We will use `langchain-google-vertexai` or `google-cloud-aiplatform` SDK.
-   We must implement **Redaction Middleware** to ensure PII is not sent to the public API (even though Vertex AI has data governance guarantees, we prefer defense-in-depth).
-   We are subject to **Quotas** (Requests Per Minute) which need to be handled with retries and rate limiting.

## Alternatives Considered
-   **Tuned Model**: If base Gemini performance is poor for specific log formats, we can create a *Tuned Model* later. This would still be managed via Vertex AI Pipelines but served via a specific endpoint.
-   **Self-Hosted OSS Model**: Deploying Mistral-7B on Cloud Run with GPU. This offers privacy but high operational complexity and cold-start issues on Cloud Run (or high cost on GKE).
