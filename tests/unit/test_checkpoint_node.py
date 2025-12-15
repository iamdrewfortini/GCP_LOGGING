"""Unit tests for checkpoint functionality.

Phase 3, Task 3.2: Checkpoint Node
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timezone
from src.agent.checkpoint import (
    save_checkpoint,
    load_checkpoint,
    restore_state_from_checkpoint,
    list_checkpoints_for_run,
    delete_checkpoint,
)
from src.agent.state import AgentState, create_initial_state
from src.agent.schemas import CheckpointMetadata
from langchain_core.messages import HumanMessage, AIMessage


@pytest.fixture
def sample_state():
    """Create sample agent state for testing."""
    return create_initial_state(
        run_id="test-run-123",
        user_query="Check logs for errors",
        messages=[
            HumanMessage(content="Check logs for errors"),
            AIMessage(content="I'll analyze the logs"),
        ],
        scope={"project": "test-project"},
        budget_max=100000,
        model="gpt-4",
    )


@pytest.fixture
def mock_firestore():
    """Mock Firestore client."""
    with patch("src.agent.checkpoint.db") as mock_db:
        yield mock_db


class TestSaveCheckpoint:
    """Tests for save_checkpoint function."""

    def test_save_checkpoint_success(self, sample_state, mock_firestore):
        """Test successful checkpoint save."""
        # Setup mock
        mock_doc_ref = Mock()
        mock_firestore.collection.return_value.document.return_value = mock_doc_ref

        # Save checkpoint
        metadata = save_checkpoint(sample_state)

        # Verify metadata
        assert metadata.run_id == "test-run-123"
        assert metadata.phase == "diagnose"
        assert metadata.message_count == 2
        assert metadata.tool_call_count == 0
        assert "checkpoint_id" in metadata.model_dump()

        # Verify Firestore was called
        mock_firestore.collection.assert_called_once_with("checkpoints")
        mock_doc_ref.set.assert_called_once()

    def test_save_checkpoint_with_custom_id(self, sample_state, mock_firestore):
        """Test checkpoint save with custom ID."""
        mock_doc_ref = Mock()
        mock_firestore.collection.return_value.document.return_value = mock_doc_ref

        custom_id = "custom-checkpoint-123"
        metadata = save_checkpoint(sample_state, checkpoint_id=custom_id)

        assert metadata.checkpoint_id == custom_id
        mock_firestore.collection.return_value.document.assert_called_with(custom_id)

    def test_save_checkpoint_with_token_usage(self, sample_state, mock_firestore):
        """Test checkpoint includes token usage."""
        mock_doc_ref = Mock()
        mock_firestore.collection.return_value.document.return_value = mock_doc_ref

        # Update state with token usage
        sample_state["token_budget"]["total_tokens"] = 5000
        sample_state["token_budget"]["budget_remaining"] = 95000

        metadata = save_checkpoint(sample_state)

        # Verify token usage in metadata
        assert metadata.token_usage["total_tokens"] == 5000
        assert metadata.token_usage["budget_remaining"] == 95000

    def test_save_checkpoint_firestore_error(self, sample_state, mock_firestore):
        """Test checkpoint save handles Firestore errors."""
        mock_doc_ref = Mock()
        mock_doc_ref.set.side_effect = Exception("Firestore error")
        mock_firestore.collection.return_value.document.return_value = mock_doc_ref

        with pytest.raises(Exception, match="Firestore error"):
            save_checkpoint(sample_state)


class TestLoadCheckpoint:
    """Tests for load_checkpoint function."""

    def test_load_checkpoint_success(self, mock_firestore):
        """Test successful checkpoint load."""
        # Setup mock
        mock_doc = Mock()
        mock_doc.exists = True
        mock_doc.to_dict.return_value = {
            "checkpoint_id": "ckpt-123",
            "run_id": "run-456",
            "phase": "verify",
            "state": {"user_query": "test query"},
            "metadata": {},
        }
        mock_doc_ref = Mock()
        mock_doc_ref.get.return_value = mock_doc
        mock_firestore.collection.return_value.document.return_value = mock_doc_ref

        # Load checkpoint
        checkpoint_data = load_checkpoint("ckpt-123")

        assert checkpoint_data is not None
        assert checkpoint_data["checkpoint_id"] == "ckpt-123"
        assert checkpoint_data["run_id"] == "run-456"

    def test_load_checkpoint_not_found(self, mock_firestore):
        """Test load checkpoint when not found."""
        mock_doc = Mock()
        mock_doc.exists = False
        mock_doc_ref = Mock()
        mock_doc_ref.get.return_value = mock_doc
        mock_firestore.collection.return_value.document.return_value = mock_doc_ref

        checkpoint_data = load_checkpoint("nonexistent")

        assert checkpoint_data is None

    def test_load_checkpoint_firestore_error(self, mock_firestore):
        """Test load checkpoint handles Firestore errors."""
        mock_doc_ref = Mock()
        mock_doc_ref.get.side_effect = Exception("Firestore error")
        mock_firestore.collection.return_value.document.return_value = mock_doc_ref

        with pytest.raises(Exception, match="Firestore error"):
            load_checkpoint("ckpt-123")


class TestRestoreStateFromCheckpoint:
    """Tests for restore_state_from_checkpoint function."""

    def test_restore_state_success(self):
        """Test successful state restoration."""
        checkpoint_data = {
            "checkpoint_id": "ckpt-123",
            "run_id": "run-456",
            "phase": "verify",
            "state": {
                "user_query": "test query",
                "phase": "verify",
                "status": "running",
                "mode": "interactive",
                "scope": {"project": "test"},
                "hypotheses": ["hyp1"],
                "evidence": [{"type": "log"}],
                "tool_calls": [],
                "runbook_ids": [],
                "error": None,
            },
            "token_usage": {
                "total_tokens": 1000,
                "budget_remaining": 99000,
            },
            "metadata": {},
        }

        restored_state = restore_state_from_checkpoint(checkpoint_data)

        assert restored_state["run_id"] == "run-456"
        assert restored_state["user_query"] == "test query"
        assert restored_state["phase"] == "verify"
        assert len(restored_state["hypotheses"]) == 1
        assert len(restored_state["evidence"]) == 1

    def test_restore_state_minimal_data(self):
        """Test state restoration with minimal data."""
        checkpoint_data = {
            "run_id": "run-123",
            "state": {},
            "token_usage": {},
            "metadata": {},
        }

        restored_state = restore_state_from_checkpoint(checkpoint_data)

        assert restored_state["run_id"] == "run-123"
        assert restored_state["user_query"] == ""
        assert restored_state["messages"] == []


class TestListCheckpointsForRun:
    """Tests for list_checkpoints_for_run function."""

    def test_list_checkpoints_success(self, mock_firestore):
        """Test successful checkpoint listing."""
        # Setup mock
        mock_doc1 = Mock()
        mock_doc1.to_dict.return_value = {"checkpoint_id": "ckpt-1"}
        mock_doc2 = Mock()
        mock_doc2.to_dict.return_value = {"checkpoint_id": "ckpt-2"}

        mock_query = Mock()
        mock_query.stream.return_value = [mock_doc1, mock_doc2]

        mock_collection = Mock()
        mock_collection.where.return_value.order_by.return_value.limit.return_value = mock_query
        mock_firestore.collection.return_value = mock_collection

        # List checkpoints
        checkpoints = list_checkpoints_for_run("run-123")

        assert len(checkpoints) == 2
        assert checkpoints[0]["checkpoint_id"] == "ckpt-1"
        assert checkpoints[1]["checkpoint_id"] == "ckpt-2"

    def test_list_checkpoints_empty(self, mock_firestore):
        """Test listing when no checkpoints exist."""
        mock_query = Mock()
        mock_query.stream.return_value = []

        mock_collection = Mock()
        mock_collection.where.return_value.order_by.return_value.limit.return_value = mock_query
        mock_firestore.collection.return_value = mock_collection

        checkpoints = list_checkpoints_for_run("run-123")

        assert len(checkpoints) == 0

    def test_list_checkpoints_error(self, mock_firestore):
        """Test listing handles errors gracefully."""
        mock_collection = Mock()
        mock_collection.where.side_effect = Exception("Firestore error")
        mock_firestore.collection.return_value = mock_collection

        checkpoints = list_checkpoints_for_run("run-123")

        assert len(checkpoints) == 0


class TestDeleteCheckpoint:
    """Tests for delete_checkpoint function."""

    def test_delete_checkpoint_success(self, mock_firestore):
        """Test successful checkpoint deletion."""
        mock_doc_ref = Mock()
        mock_firestore.collection.return_value.document.return_value = mock_doc_ref

        result = delete_checkpoint("ckpt-123")

        assert result is True
        mock_doc_ref.delete.assert_called_once()

    def test_delete_checkpoint_error(self, mock_firestore):
        """Test delete handles errors."""
        mock_doc_ref = Mock()
        mock_doc_ref.delete.side_effect = Exception("Firestore error")
        mock_firestore.collection.return_value.document.return_value = mock_doc_ref

        result = delete_checkpoint("ckpt-123")

        assert result is False


class TestCheckpointIntegration:
    """Integration tests for checkpoint workflow."""

    def test_save_and_restore_workflow(self, sample_state, mock_firestore):
        """Test complete save and restore workflow."""
        # Setup mocks
        mock_doc_ref = Mock()
        mock_firestore.collection.return_value.document.return_value = mock_doc_ref

        # Save checkpoint
        metadata = save_checkpoint(sample_state)
        assert metadata.run_id == "test-run-123"

        # Simulate loading
        checkpoint_data = {
            "checkpoint_id": metadata.checkpoint_id,
            "run_id": metadata.run_id,
            "phase": metadata.phase,
            "state": {
                "user_query": sample_state["user_query"],
                "phase": sample_state["phase"],
                "status": sample_state["status"],
                "mode": sample_state["mode"],
                "scope": sample_state["scope"],
                "hypotheses": sample_state["hypotheses"],
                "evidence": sample_state["evidence"],
                "tool_calls": sample_state["tool_calls"],
                "runbook_ids": sample_state["runbook_ids"],
                "error": sample_state["error"],
            },
            "token_usage": metadata.token_usage,
            "metadata": metadata.model_dump(),
        }

        # Restore state
        restored_state = restore_state_from_checkpoint(checkpoint_data)

        # Verify restoration
        assert restored_state["run_id"] == sample_state["run_id"]
        assert restored_state["user_query"] == sample_state["user_query"]
        assert restored_state["phase"] == sample_state["phase"]
