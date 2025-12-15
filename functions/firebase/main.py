"""Cloud Functions for Firebase integration.

This module contains Cloud Functions that:
1. Generate embeddings for error/critical logs
2. Store embeddings in Firestore for semantic search
"""

from __future__ import annotations

import base64
import json
import os
from datetime import datetime
from typing import Any, Optional

import functions_framework
from google.cloud import firestore
from google.cloud import aiplatform


# Initialize clients lazily
_db: Optional[firestore.Client] = None
_embedding_model: Optional[Any] = None


def get_firestore_client() -> firestore.Client:
    """Get or create Firestore client."""
    global _db
    if _db is None:
        _db = firestore.Client()
    return _db


def get_embedding_model():
    """Get or create the embedding model."""
    global _embedding_model
    if _embedding_model is None:
        project_id = os.getenv("PROJECT_ID", "diatonic-ai-gcp")
        location = os.getenv("REGION", "us-central1")
        aiplatform.init(project=project_id, location=location)
        _embedding_model = aiplatform.TextEmbeddingModel.from_pretrained(
            "text-embedding-004"
        )
    return _embedding_model


def generate_embedding(text: str) -> list[float]:
    """Generate embedding for text using Vertex AI.

    Args:
        text: The text to embed.

    Returns:
        List of embedding values.
    """
    model = get_embedding_model()
    embeddings = model.get_embeddings([text])
    return embeddings[0].values


@functions_framework.cloud_event
def generate_log_embedding(cloud_event):
    """Generate embedding for error/critical logs and store in Firestore.

    Triggered by Pub/Sub when ERROR/CRITICAL log arrives via the
    logging-critical-alerts topic.

    Args:
        cloud_event: The CloudEvent containing the log data.
    """
    try:
        # Decode the Pub/Sub message
        message_data = cloud_event.data.get("message", {})
        data_bytes = message_data.get("data", "")

        if isinstance(data_bytes, str):
            data_bytes = base64.b64decode(data_bytes)

        log_data = json.loads(data_bytes)

        # Extract log information
        severity = log_data.get("severity", "UNKNOWN")

        # Only process ERROR/CRITICAL/ALERT/EMERGENCY logs
        high_severity_levels = {"ERROR", "CRITICAL", "ALERT", "EMERGENCY"}
        if severity not in high_severity_levels:
            print(f"Skipping log with severity: {severity}")
            return

        # Extract relevant fields
        service = log_data.get("resource", {}).get("labels", {}).get(
            "service_name", "unknown"
        )
        message = ""

        # Try to get message from various payload types
        if "textPayload" in log_data:
            message = log_data["textPayload"]
        elif "jsonPayload" in log_data:
            jp = log_data["jsonPayload"]
            message = jp.get("message", jp.get("msg", str(jp)))
        elif "protoPayload" in log_data:
            pp = log_data["protoPayload"]
            message = pp.get("status", {}).get("message", str(pp)[:500])

        # Truncate message if too long
        if len(message) > 1000:
            message = message[:1000] + "..."

        # Create text for embedding
        embedding_text = f"{severity} | {service} | {message}"

        print(f"Generating embedding for: {embedding_text[:100]}...")

        # Generate embedding
        embedding = generate_embedding(embedding_text)

        # Store in Firestore
        db = get_firestore_client()
        doc_ref = db.collection("embeddings").document()
        doc_ref.set(
            {
                "vector": embedding,
                "text": embedding_text,
                "metadata": {
                    "severity": severity,
                    "service": service,
                    "timestamp": log_data.get("timestamp"),
                    "insertId": log_data.get("insertId"),
                    "logName": log_data.get("logName"),
                    "resourceType": log_data.get("resource", {}).get("type"),
                },
                "createdAt": firestore.SERVER_TIMESTAMP,
            }
        )

        print(f"Successfully stored embedding for log: {log_data.get('insertId')}")

    except json.JSONDecodeError as e:
        print(f"Failed to parse log data: {e}")
    except Exception as e:
        print(f"Error processing log: {e}")
        raise


@functions_framework.http
def health_check(request):
    """Health check endpoint for the function.

    Args:
        request: The HTTP request object.

    Returns:
        A simple health status response.
    """
    return {"status": "ok", "service": "firebase-functions"}, 200


@functions_framework.cloud_event
def analyze_error_patterns(cloud_event):
    """Analyze error patterns and generate insights.

    This function runs periodically (via Cloud Scheduler) to:
    1. Aggregate recent error logs
    2. Detect patterns and anomalies
    3. Store insights in Firestore

    Args:
        cloud_event: The CloudEvent trigger.
    """
    try:
        db = get_firestore_client()

        # Query recent embeddings (last 24 hours)
        cutoff = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

        query = (
            db.collection("embeddings")
            .where("createdAt", ">=", cutoff)
            .order_by("createdAt", direction=firestore.Query.DESCENDING)
            .limit(1000)
        )

        embeddings = [doc.to_dict() for doc in query.stream()]

        if not embeddings:
            print("No recent embeddings to analyze")
            return

        # Group by service
        service_errors: dict[str, int] = {}
        severity_counts: dict[str, int] = {}

        for emb in embeddings:
            meta = emb.get("metadata", {})
            service = meta.get("service", "unknown")
            severity = meta.get("severity", "UNKNOWN")

            service_errors[service] = service_errors.get(service, 0) + 1
            severity_counts[severity] = severity_counts.get(severity, 0) + 1

        # Generate insights
        insights = []

        # Find services with high error counts
        for service, count in service_errors.items():
            if count >= 10:  # Threshold for "high" errors
                insights.append(
                    {
                        "type": "high_error_rate",
                        "severity": "warning" if count < 50 else "critical",
                        "service": service,
                        "errorCount": count,
                        "message": f"Service '{service}' has {count} errors in the last 24 hours",
                        "status": "new",
                        "createdAt": firestore.SERVER_TIMESTAMP,
                    }
                )

        # Store insights
        for insight in insights:
            db.collection("insights").add(insight)

        print(f"Generated {len(insights)} insights from {len(embeddings)} embeddings")

    except Exception as e:
        print(f"Error analyzing patterns: {e}")
        raise
