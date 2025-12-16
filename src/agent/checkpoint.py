"""Checkpoint functionality for LangGraph state persistence.

This module provides checkpoint functionality to save and restore
agent state to/from Firestore.

Phase 3, Task 3.2: Checkpoint Node
"""

import logging
import os
import threading
from typing import Dict, Any, Optional
from datetime import datetime, timezone

import firebase_admin
from firebase_admin import firestore

from src.agent.state import AgentState
from src.agent.schemas import CheckpointMetadata

logger = logging.getLogger(__name__)

# NOTE:
# Do NOT initialize Firebase/Firestore at import time.
# - GitHub Actions runners (and many local dev environments) do not have ADC.
# - Import-time side effects break pytest collection.
# We lazily create the client when checkpointing is actually used.

db: Optional[Any] = None
_db_init_error: Optional[Exception] = None
_db_lock = threading.Lock()


def _checkpoints_enabled() -> bool:
    """Whether checkpoint persistence is enabled.

    Defaults to FIREBASE_ENABLED to align with the Cloud Run deploy config.
    """
    v = os.getenv("CHECKPOINTS_ENABLED")
    if v is None:
        v = os.getenv("FIREBASE_ENABLED", "false")
    return v.lower() == "true"


def get_firestore_db() -> Any:
    """Get a Firestore client for checkpoint persistence.

    Raises:
        RuntimeError: if checkpoints are disabled.
        Exception: if Firestore can't be initialized.
    """
    global db, _db_init_error

    if db is not None:
        return db

    if not _checkpoints_enabled():
        raise RuntimeError(
            "Checkpointing is disabled (set CHECKPOINTS_ENABLED=true or FIREBASE_ENABLED=true)."
        )

    # Prevent repeated expensive/failed init attempts.
    if _db_init_error is not None:
        raise _db_init_error

    with _db_lock:
        if db is not None:
            return db
        if _db_init_error is not None:
            raise _db_init_error

        try:
            # Initialize Firebase if not already initialized.
            try:
                firebase_admin.get_app()
            except ValueError:
                firebase_admin.initialize_app()

            db = firestore.client()
            return db
        except Exception as e:
            # Cache the init error so subsequent calls fail fast and consistently.
            _db_init_error = e
            raise


def save_checkpoint(
    state: AgentState,
    checkpoint_id: Optional[str] = None,
) -> CheckpointMetadata:
    """Save agent state checkpoint to Firestore.

    Args:
        state: Current agent state
        checkpoint_id: Optional checkpoint ID (generated if not provided)

    Returns:
        CheckpointMetadata with checkpoint information

    Raises:
        Exception: If checkpoint save fails
    """
    run_id = state.get("run_id", "unknown")
    phase = state.get("phase", "unknown")

    # Generate checkpoint ID if not provided
    if checkpoint_id is None:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        checkpoint_id = f"{run_id}_{phase}_{timestamp}"

    # Extract token usage
    token_budget = state.get("token_budget", {})
    token_usage = {
        "prompt_tokens": token_budget.get("prompt_tokens", 0),
        "completion_tokens": token_budget.get("completion_tokens", 0),
        "total_tokens": token_budget.get("total_tokens", 0),
        "budget_remaining": token_budget.get("budget_remaining", 0),
    }

    # Count messages and tool calls
    messages = state.get("messages", [])
    tool_calls = state.get("tool_calls", [])

    # Create checkpoint metadata
    metadata = CheckpointMetadata(
        checkpoint_id=checkpoint_id,
        run_id=run_id,
        phase=phase,
        timestamp=datetime.now(timezone.utc).isoformat(),
        token_usage=token_usage,
        message_count=len(messages),
        tool_call_count=len(tool_calls),
    )

    # Prepare checkpoint document
    checkpoint_doc = {
        "checkpoint_id": checkpoint_id,
        "run_id": run_id,
        "phase": phase,
        "timestamp": firestore.SERVER_TIMESTAMP,
        "created_at": datetime.now(timezone.utc),
        # State snapshot
        "state": {
            "user_query": state.get("user_query", ""),
            "phase": phase,
            "status": state.get("status", "running"),
            "mode": state.get("mode", "interactive"),
            "scope": state.get("scope", {}),
            "hypotheses": state.get("hypotheses", []),
            "evidence": state.get("evidence", []),
            "tool_calls": tool_calls,
            "runbook_ids": state.get("runbook_ids", []),
            "error": state.get("error"),
        },
        # Metadata
        "metadata": metadata.model_dump(),
        # Token tracking
        "token_usage": token_usage,
        "message_count": len(messages),
        "tool_call_count": len(tool_calls),
    }

    try:
        # Save to Firestore
        client = get_firestore_db()
        doc_ref = client.collection("checkpoints").document(checkpoint_id)
        doc_ref.set(checkpoint_doc)

        logger.info(
            f"Checkpoint saved: {checkpoint_id} "
            f"(phase={phase}, tokens={token_usage['total_tokens']}, "
            f"messages={len(messages)})"
        )

        return metadata

    except Exception as e:
        logger.error(f"Failed to save checkpoint {checkpoint_id}: {e}")
        raise


def load_checkpoint(checkpoint_id: str) -> Optional[Dict[str, Any]]:
    """Load agent state checkpoint from Firestore.

    Args:
        checkpoint_id: Checkpoint identifier

    Returns:
        Checkpoint document or None if not found

    Raises:
        Exception: If checkpoint load fails
    """
    try:
        client = get_firestore_db()
        doc_ref = client.collection("checkpoints").document(checkpoint_id)
        doc = doc_ref.get()

        if not doc.exists:
            logger.warning(f"Checkpoint not found: {checkpoint_id}")
            return None

        checkpoint_data = doc.to_dict()
        logger.info(f"Checkpoint loaded: {checkpoint_id}")

        return checkpoint_data

    except Exception as e:
        logger.error(f"Failed to load checkpoint {checkpoint_id}: {e}")
        raise


def restore_state_from_checkpoint(checkpoint_data: Dict[str, Any]) -> AgentState:
    """Restore AgentState from checkpoint data.

    Args:
        checkpoint_data: Checkpoint document from Firestore

    Returns:
        Restored AgentState
    """
    state_snapshot = checkpoint_data.get("state", {})
    metadata = checkpoint_data.get("metadata", {})

    # Reconstruct AgentState
    # Note: Messages are not restored (too large), only state fields
    restored_state = AgentState(
        run_id=checkpoint_data.get("run_id", "unknown"),
        user_query=state_snapshot.get("user_query", ""),
        messages=[],  # Messages not persisted in checkpoint
        scope=state_snapshot.get("scope", {}),
        hypotheses=state_snapshot.get("hypotheses", []),
        evidence=state_snapshot.get("evidence", []),
        tool_calls=state_snapshot.get("tool_calls", []),
        cost_summary={},
        runbook_ids=state_snapshot.get("runbook_ids", []),
        phase=state_snapshot.get("phase", "diagnose"),
        mode=state_snapshot.get("mode", "interactive"),
        status=state_snapshot.get("status", "running"),
        error=state_snapshot.get("error"),
        token_budget=checkpoint_data.get("token_usage", {}),
    )

    logger.info(
        f"State restored from checkpoint: {checkpoint_data.get('checkpoint_id')} "
        f"(phase={restored_state.get('phase')})"
    )

    return restored_state


def list_checkpoints_for_run(run_id: str, limit: int = 10) -> list[Dict[str, Any]]:
    """List checkpoints for a specific run.

    Args:
        run_id: Agent run identifier
        limit: Maximum number of checkpoints to return

    Returns:
        List of checkpoint documents
    """
    try:
        client = get_firestore_db()
        query = (
            client.collection("checkpoints")
            .where("run_id", "==", run_id)
            .order_by("created_at", direction=firestore.Query.DESCENDING)
            .limit(limit)
        )

        checkpoints = []
        for doc in query.stream():
            checkpoint_data = doc.to_dict()
            checkpoints.append(checkpoint_data)

        logger.info(f"Found {len(checkpoints)} checkpoints for run {run_id}")
        return checkpoints

    except Exception as e:
        logger.error(f"Failed to list checkpoints for run {run_id}: {e}")
        return []


def delete_checkpoint(checkpoint_id: str) -> bool:
    """Delete a checkpoint from Firestore.

    Args:
        checkpoint_id: Checkpoint identifier

    Returns:
        True if deleted, False otherwise
    """
    try:
        client = get_firestore_db()
        doc_ref = client.collection("checkpoints").document(checkpoint_id)
        doc_ref.delete()
        logger.info(f"Checkpoint deleted: {checkpoint_id}")
        return True

    except Exception as e:
        logger.error(f"Failed to delete checkpoint {checkpoint_id}: {e}")
        return False
