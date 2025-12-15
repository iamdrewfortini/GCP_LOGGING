"""Unit tests for BigQuery provisioning."""

import pytest
from unittest.mock import Mock, patch, MagicMock
from google.cloud import bigquery

from src.cli.provision_bq import (
    get_chat_events_schema,
    get_tool_invocations_schema,
    create_dataset,
    create_table,
    create_views,
    provision_chat_analytics,
    DEFAULT_DATASET,
    DEFAULT_PROJECT,
    DEFAULT_LOCATION,
    PARTITION_EXPIRATION_DAYS,
)


class TestSchemaDefinitions:
    """Test schema definitions."""

    def test_chat_events_schema_has_required_fields(self):
        """Test chat_events schema has all required fields."""
        schema = get_chat_events_schema()

        required_fields = ["event_id", "event_timestamp", "session_id", "user_id", "event_type"]
        field_names = [f.name for f in schema]

        for field in required_fields:
            assert field in field_names, f"Missing required field: {field}"

    def test_chat_events_schema_modes(self):
        """Test chat_events schema field modes."""
        schema = get_chat_events_schema()
        schema_dict = {f.name: f for f in schema}

        # Required fields
        assert schema_dict["event_id"].mode == "REQUIRED"
        assert schema_dict["event_timestamp"].mode == "REQUIRED"
        assert schema_dict["session_id"].mode == "REQUIRED"

        # Nullable fields
        assert schema_dict["content"].mode == "NULLABLE"
        assert schema_dict["metadata"].mode == "NULLABLE"

    def test_chat_events_schema_types(self):
        """Test chat_events schema field types."""
        schema = get_chat_events_schema()
        schema_dict = {f.name: f for f in schema}

        assert schema_dict["event_id"].field_type == "STRING"
        assert schema_dict["event_timestamp"].field_type == "TIMESTAMP"
        assert schema_dict["content"].field_type == "JSON"
        assert schema_dict["token_usage"].field_type == "RECORD"

    def test_chat_events_token_usage_nested_fields(self):
        """Test chat_events token_usage nested fields."""
        schema = get_chat_events_schema()
        schema_dict = {f.name: f for f in schema}

        token_usage = schema_dict["token_usage"]
        nested_names = [f.name for f in token_usage.fields]

        assert "prompt_tokens" in nested_names
        assert "completion_tokens" in nested_names
        assert "total_tokens" in nested_names

    def test_tool_invocations_schema_has_required_fields(self):
        """Test tool_invocations schema has all required fields."""
        schema = get_tool_invocations_schema()

        required_fields = ["invocation_id", "session_id", "user_id", "tool_name", "started_at", "status"]
        field_names = [f.name for f in schema]

        for field in required_fields:
            assert field in field_names, f"Missing required field: {field}"

    def test_tool_invocations_schema_has_metrics_fields(self):
        """Test tool_invocations schema has metrics fields."""
        schema = get_tool_invocations_schema()
        field_names = [f.name for f in schema]

        assert "duration_ms" in field_names
        assert "bytes_billed" in field_names
        assert "tokens_used" in field_names


class TestDryRun:
    """Test dry run functionality."""

    def test_create_dataset_dry_run(self, capsys):
        """Test create_dataset in dry run mode."""
        result = create_dataset(
            client=None,
            project_id="test-project",
            dataset_id="test-dataset",
            location="US",
            dry_run=True,
        )

        assert result is True
        captured = capsys.readouterr()
        assert "[DRY RUN]" in captured.out
        assert "test-project.test-dataset" in captured.out

    def test_create_table_dry_run(self, capsys):
        """Test create_table in dry run mode."""
        schema = get_chat_events_schema()
        result = create_table(
            client=None,
            project_id="test-project",
            dataset_id="test-dataset",
            table_id="chat_events",
            schema=schema,
            partition_field="event_timestamp",
            clustering_fields=["session_id", "user_id", "event_type"],
            partition_expiration_days=2555,
            dry_run=True,
        )

        assert result is True
        captured = capsys.readouterr()
        assert "[DRY RUN]" in captured.out
        assert "chat_events" in captured.out
        assert "DATE(event_timestamp)" in captured.out

    def test_create_views_dry_run(self, capsys):
        """Test create_views in dry run mode."""
        result = create_views(
            client=None,
            project_id="test-project",
            dataset_id="test-dataset",
            dry_run=True,
        )

        assert result is True
        captured = capsys.readouterr()
        assert "[DRY RUN]" in captured.out
        assert "v_chat_sessions_summary" in captured.out

    def test_provision_chat_analytics_dry_run(self, capsys):
        """Test provision_chat_analytics in dry run mode."""
        result = provision_chat_analytics(
            project_id="test-project",
            dataset_id="chat_analytics",
            location="US",
            dry_run=True,
        )

        assert result is True
        captured = capsys.readouterr()
        assert "Dry run: True" in captured.out
        assert "chat_events" in captured.out
        assert "tool_invocations" in captured.out


class TestCreateDataset:
    """Test create_dataset function."""

    def test_create_dataset_success(self):
        """Test successful dataset creation."""
        mock_client = Mock()
        mock_client.create_dataset.return_value = None

        result = create_dataset(
            client=mock_client,
            project_id="test-project",
            dataset_id="test-dataset",
            location="US",
            dry_run=False,
        )

        assert result is True
        mock_client.create_dataset.assert_called_once()

    def test_create_dataset_exists_ok(self):
        """Test dataset creation with exists_ok."""
        mock_client = Mock()
        mock_client.create_dataset.return_value = None

        result = create_dataset(
            client=mock_client,
            project_id="test-project",
            dataset_id="existing-dataset",
            location="US",
            dry_run=False,
        )

        assert result is True
        # Verify exists_ok=True was passed
        call_args = mock_client.create_dataset.call_args
        assert call_args.kwargs.get("exists_ok") is True


class TestCreateTable:
    """Test create_table function."""

    def test_create_table_success(self):
        """Test successful table creation."""
        mock_client = Mock()
        mock_client.create_table.return_value = None

        result = create_table(
            client=mock_client,
            project_id="test-project",
            dataset_id="test-dataset",
            table_id="chat_events",
            schema=get_chat_events_schema(),
            partition_field="event_timestamp",
            clustering_fields=["session_id", "user_id"],
            partition_expiration_days=2555,
            dry_run=False,
        )

        assert result is True
        mock_client.create_table.assert_called_once()

    def test_create_table_with_partitioning(self):
        """Test table creation with partitioning configuration."""
        mock_client = Mock()

        create_table(
            client=mock_client,
            project_id="test-project",
            dataset_id="test-dataset",
            table_id="test_table",
            schema=get_chat_events_schema(),
            partition_field="event_timestamp",
            clustering_fields=["session_id"],
            partition_expiration_days=365,
            dry_run=False,
        )

        # Get the table object passed to create_table
        call_args = mock_client.create_table.call_args
        table = call_args.args[0]

        assert table.time_partitioning is not None
        assert table.time_partitioning.field == "event_timestamp"
        assert table.clustering_fields == ["session_id"]


class TestDefaults:
    """Test default configuration values."""

    def test_default_project(self):
        """Test default project value."""
        assert DEFAULT_PROJECT == "diatonic-ai-gcp"

    def test_default_dataset(self):
        """Test default dataset value."""
        assert DEFAULT_DATASET == "chat_analytics"

    def test_default_location(self):
        """Test default location value."""
        assert DEFAULT_LOCATION == "US"

    def test_partition_expiration_days(self):
        """Test partition expiration is ~7 years."""
        assert PARTITION_EXPIRATION_DAYS == 2555
        # Verify it's approximately 7 years (within 10 days)
        expected_days = 7 * 365
        assert abs(PARTITION_EXPIRATION_DAYS - expected_days) <= 10
