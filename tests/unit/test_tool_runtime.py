"""
Unit tests for tool runtime.
Phase 4, Task 4.3: Tool runtime tests
"""

import pytest
from unittest.mock import Mock, patch

from src.mcp.runtime import ToolRuntime


class TestToolRuntime:
    """Tests for ToolRuntime class."""

    @pytest.fixture
    def runtime(self):
        """Create runtime instance."""
        return ToolRuntime(
            tool_id="test_tool",
            version="1.0.0",
            safety_config={
                "deny_keywords": ["DROP", "DELETE"],
                "allow_keywords": ["SELECT", "FROM"],
                "allowed_datasets": ["test_dataset"],
                "max_rows_returned": 100,
                "timeout_seconds": 30
            },
            audit_config={
                "log_input": True,
                "log_output": True,
                "redact_fields": ["email"],
                "log_destination": "test.logs"
            }
        )

    def test_runtime_initialization(self, runtime):
        """Test runtime initialization."""
        assert runtime.tool_id == "test_tool"
        assert runtime.version == "1.0.0"
        assert runtime.safety["deny_keywords"] == ["DROP", "DELETE"]

    def test_validate_input_sql_denied_keywords(self, runtime):
        """Test SQL denied keyword validation."""
        # Should raise for denied keywords
        with pytest.raises(ValueError, match="Denied keyword"):
            runtime._validate_input({"sql": "DROP TABLE users"})
        
        with pytest.raises(ValueError, match="Denied keyword"):
            runtime._validate_input({"sql": "DELETE FROM users"})

    def test_validate_input_sql_allowed(self, runtime):
        """Test SQL allowed keywords."""
        # Should pass for allowed keywords (without allow_keywords check)
        runtime_no_allow = ToolRuntime(
            tool_id="test_tool",
            version="1.0.0",
            safety_config={
                "deny_keywords": ["DROP", "DELETE"],
                "max_rows_returned": 100
            },
            audit_config={"log_input": False, "log_output": False}
        )
        runtime_no_allow._validate_input({"sql": "SELECT * FROM users"})

    def test_validate_input_dataset_restrictions(self, runtime):
        """Test dataset restriction validation."""
        # Create runtime without allow_keywords for this test
        runtime_dataset = ToolRuntime(
            tool_id="test_tool",
            version="1.0.0",
            safety_config={
                "deny_keywords": [],
                "allowed_datasets": ["test_dataset"],
                "max_rows_returned": 100
            },
            audit_config={"log_input": False, "log_output": False}
        )
        
        # Should pass for allowed dataset
        runtime_dataset._validate_input({
            "sql": "SELECT * FROM `project.test_dataset.table`"
        })
        
        # Should fail for disallowed dataset
        with pytest.raises(ValueError, match="Dataset not allowed"):
            runtime_dataset._validate_input({
                "sql": "SELECT * FROM `project.other_dataset.table`"
            })

    def test_validate_output_row_limit(self, runtime):
        """Test output row limit validation."""
        # Create output with too many rows
        output = {
            "rows": [{"id": i} for i in range(150)]
        }
        
        # Should truncate to max_rows_returned
        validated = runtime._validate_output(output)
        
        assert len(validated["rows"]) == 100
        assert validated["truncated"] is True

    def test_validate_output_within_limit(self, runtime):
        """Test output within limit."""
        output = {
            "rows": [{"id": i} for i in range(50)]
        }
        
        validated = runtime._validate_output(output)
        
        assert len(validated["rows"]) == 50
        assert "truncated" not in validated

    def test_redact_sensitive_fields(self, runtime):
        """Test field redaction."""
        data = {
            "email": "user@example.com",
            "name": "John Doe",
            "ip_address": "192.168.1.1"
        }
        
        redacted = runtime._redact(data, ["email", "ip_address"])
        
        assert redacted["email"] == "[REDACTED]"
        assert redacted["name"] == "John Doe"

    @patch("src.mcp.runtime.bigquery.Client")
    def test_execute_success(self, mock_bq_client, runtime):
        """Test successful tool execution."""
        # Mock executor
        def mock_executor(input_data):
            return {"result": "success"}
        
        # Execute
        result = runtime.execute(
            input_data={"query": "test"},
            executor=mock_executor
        )
        
        assert result["result"] == "success"

    @patch("src.mcp.runtime.bigquery.Client")
    def test_execute_with_error(self, mock_bq_client, runtime):
        """Test tool execution with error."""
        # Mock executor that raises
        def mock_executor(input_data):
            raise ValueError("Test error")
        
        # Should raise and log error
        with pytest.raises(ValueError, match="Test error"):
            runtime.execute(
                input_data={"query": "test"},
                executor=mock_executor
            )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
