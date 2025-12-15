"""
Unit tests for tool spec validator.
Phase 4, Task 4.1: Tool spec validator tests
"""

import pytest
import tempfile
from pathlib import Path
from pydantic import ValidationError

from src.mcp.validator import (
    ToolSpec,
    SafetyConfig,
    AuditConfig,
    ToolExample,
    ToolMetadata,
    load_tool_spec,
    validate_tool_spec_dict,
    save_tool_spec,
)


class TestSafetyConfig:
    """Tests for SafetyConfig model."""

    def test_safety_config_defaults(self):
        """Test SafetyConfig with defaults."""
        config = SafetyConfig()
        
        assert config.deny_keywords == []
        assert config.allow_keywords == []
        assert config.max_rows_returned == 1000
        assert config.require_partition_filter is False
        assert config.timeout_seconds == 60

    def test_safety_config_with_values(self):
        """Test SafetyConfig with custom values."""
        config = SafetyConfig(
            deny_keywords=["DROP", "DELETE"],
            allow_keywords=["SELECT", "FROM"],
            allowed_datasets=["central_logging_v1"],
            max_rows_returned=500,
            timeout_seconds=30
        )
        
        assert len(config.deny_keywords) == 2
        assert len(config.allow_keywords) == 2
        assert config.max_rows_returned == 500


class TestAuditConfig:
    """Tests for AuditConfig model."""

    def test_audit_config_defaults(self):
        """Test AuditConfig with defaults."""
        config = AuditConfig()
        
        assert config.log_input is True
        assert config.log_output is True
        assert config.redact_fields == []
        assert config.log_destination == "chat_analytics.tool_invocations"

    def test_audit_config_with_redaction(self):
        """Test AuditConfig with redaction fields."""
        config = AuditConfig(
            redact_fields=["email", "ip_address", "user_id"]
        )
        
        assert len(config.redact_fields) == 3
        assert "email" in config.redact_fields


class TestToolSpec:
    """Tests for ToolSpec model."""

    def test_valid_tool_spec(self):
        """Test valid tool spec."""
        spec = ToolSpec(
            tool_id="test_tool",
            name="test_tool",
            version="1.0.0",
            description="Test tool",
            inputs={
                "type": "object",
                "properties": {
                    "query": {"type": "string"}
                }
            },
            outputs={
                "type": "object",
                "properties": {
                    "result": {"type": "string"}
                }
            },
            safety=SafetyConfig(),
            permissions=["bigquery.jobs.create"],
            audit=AuditConfig(),
            metadata=ToolMetadata(created_at="2024-01-15T00:00:00Z")
        )
        
        assert spec.tool_id == "test_tool"
        assert spec.version == "1.0.0"

    def test_tool_id_validation(self):
        """Test tool_id validation."""
        # Valid tool_ids
        valid_ids = ["test_tool", "bq-query", "tool_123", "my-tool-v2"]
        for tool_id in valid_ids:
            spec = ToolSpec(
                tool_id=tool_id,
                name=tool_id,
                version="1.0.0",
                description="Test",
                inputs={"type": "object", "properties": {}},
                outputs={"type": "object", "properties": {}},
                safety=SafetyConfig(),
                permissions=["bigquery.jobs.create"],
                audit=AuditConfig(),
                metadata=ToolMetadata(created_at="2024-01-15T00:00:00Z")
            )
            assert spec.tool_id == tool_id

        # Invalid tool_ids
        with pytest.raises(ValidationError):
            ToolSpec(
                tool_id="ab",  # Too short
                name="ab",
                version="1.0.0",
                description="Test",
                inputs={"type": "object", "properties": {}},
                outputs={"type": "object", "properties": {}},
                safety=SafetyConfig(),
                permissions=["bigquery.jobs.create"],
                audit=AuditConfig(),
                metadata=ToolMetadata(created_at="2024-01-15T00:00:00Z")
            )

    def test_version_validation(self):
        """Test version validation."""
        # Valid versions
        valid_versions = ["1.0.0", "2.1.3", "10.20.30"]
        for version in valid_versions:
            spec = ToolSpec(
                tool_id="test_tool",
                name="test_tool",
                version=version,
                description="Test",
                inputs={"type": "object", "properties": {}},
                outputs={"type": "object", "properties": {}},
                safety=SafetyConfig(),
                permissions=["bigquery.jobs.create"],
                audit=AuditConfig(),
                metadata=ToolMetadata(created_at="2024-01-15T00:00:00Z")
            )
            assert spec.version == version

        # Invalid versions
        invalid_versions = ["1.0", "v1.0.0", "1.0.0-beta", "abc"]
        for version in invalid_versions:
            with pytest.raises(ValidationError):
                ToolSpec(
                    tool_id="test_tool",
                    name="test_tool",
                    version=version,
                    description="Test",
                    inputs={"type": "object", "properties": {}},
                    outputs={"type": "object", "properties": {}},
                    safety=SafetyConfig(),
                    permissions=["bigquery.jobs.create"],
                    audit=AuditConfig(),
                    metadata=ToolMetadata(created_at="2024-01-15T00:00:00Z")
                )

    def test_inputs_validation(self):
        """Test inputs schema validation."""
        # Valid inputs
        valid_inputs = {
            "type": "object",
            "properties": {
                "query": {"type": "string"}
            }
        }
        
        spec = ToolSpec(
            tool_id="test_tool",
            name="test_tool",
            version="1.0.0",
            description="Test",
            inputs=valid_inputs,
            outputs={"type": "object", "properties": {}},
            safety=SafetyConfig(),
            permissions=["bigquery.jobs.create"],
            audit=AuditConfig(),
            metadata=ToolMetadata(created_at="2024-01-15T00:00:00Z")
        )
        assert spec.inputs == valid_inputs

        # Invalid inputs (missing type)
        with pytest.raises(ValidationError):
            ToolSpec(
                tool_id="test_tool",
                name="test_tool",
                version="1.0.0",
                description="Test",
                inputs={"properties": {}},  # Missing type
                outputs={"type": "object", "properties": {}},
                safety=SafetyConfig(),
                permissions=["bigquery.jobs.create"],
                audit=AuditConfig(),
                metadata=ToolMetadata(created_at="2024-01-15T00:00:00Z")
            )

    def test_permissions_validation(self):
        """Test permissions validation."""
        # Valid permissions
        valid_perms = [
            ["bigquery.jobs.create"],
            ["dashboard.widgets.get"],
            ["firestore.documents.read"],
            ["bigquery.jobs.create", "bigquery.tables.getData"]
        ]
        
        for perms in valid_perms:
            spec = ToolSpec(
                tool_id="test_tool",
                name="test_tool",
                version="1.0.0",
                description="Test",
                inputs={"type": "object", "properties": {}},
                outputs={"type": "object", "properties": {}},
                safety=SafetyConfig(),
                permissions=perms,
                audit=AuditConfig(),
                metadata=ToolMetadata(created_at="2024-01-15T00:00:00Z")
            )
            assert spec.permissions == perms

        # Invalid permissions (empty list)
        with pytest.raises(ValidationError):
            ToolSpec(
                tool_id="test_tool",
                name="test_tool",
                version="1.0.0",
                description="Test",
                inputs={"type": "object", "properties": {}},
                outputs={"type": "object", "properties": {}},
                safety=SafetyConfig(),
                permissions=[],  # Empty
                audit=AuditConfig(),
                metadata=ToolMetadata(created_at="2024-01-15T00:00:00Z")
            )

        # Invalid permissions (wrong format)
        with pytest.raises(ValidationError):
            ToolSpec(
                tool_id="test_tool",
                name="test_tool",
                version="1.0.0",
                description="Test",
                inputs={"type": "object", "properties": {}},
                outputs={"type": "object", "properties": {}},
                safety=SafetyConfig(),
                permissions=["invalid.permission"],  # Invalid prefix
                audit=AuditConfig(),
                metadata=ToolMetadata(created_at="2024-01-15T00:00:00Z")
            )


class TestLoadToolSpec:
    """Tests for load_tool_spec function."""

    def test_load_valid_spec(self):
        """Test loading valid YAML spec."""
        spec_yaml = """
tool_id: test_tool
name: test_tool
version: "1.0.0"
description: "Test tool"
inputs:
  type: object
  properties:
    query:
      type: string
outputs:
  type: object
  properties:
    result:
      type: string
safety:
  deny_keywords: []
  allow_keywords: []
  max_rows_returned: 1000
  require_partition_filter: false
  timeout_seconds: 60
permissions:
  - bigquery.jobs.create
audit:
  log_input: true
  log_output: true
  redact_fields: []
  log_destination: chat_analytics.tool_invocations
metadata:
  author: system
  created_at: "2024-01-15T00:00:00Z"
  tags: []
  cost_estimate_usd: 0.0001
"""
        
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(spec_yaml)
            temp_path = f.name
        
        try:
            spec = load_tool_spec(temp_path)
            assert spec.tool_id == "test_tool"
            assert spec.version == "1.0.0"
        finally:
            Path(temp_path).unlink()

    def test_load_nonexistent_file(self):
        """Test loading nonexistent file."""
        with pytest.raises(FileNotFoundError):
            load_tool_spec("nonexistent.yaml")

    def test_load_empty_file(self):
        """Test loading empty file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("")
            temp_path = f.name
        
        try:
            with pytest.raises(ValueError, match="empty"):
                load_tool_spec(temp_path)
        finally:
            Path(temp_path).unlink()


class TestSaveToolSpec:
    """Tests for save_tool_spec function."""

    def test_save_and_load_roundtrip(self):
        """Test saving and loading spec."""
        spec = ToolSpec(
            tool_id="test_tool",
            name="test_tool",
            version="1.0.0",
            description="Test tool",
            inputs={"type": "object", "properties": {"query": {"type": "string"}}},
            outputs={"type": "object", "properties": {"result": {"type": "string"}}},
            safety=SafetyConfig(),
            permissions=["bigquery.jobs.create"],
            audit=AuditConfig(),
            metadata=ToolMetadata(created_at="2024-01-15T00:00:00Z")
        )
        
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "test_tool.yaml"
            save_tool_spec(spec, output_path)
            
            # Verify file exists
            assert output_path.exists()
            
            # Load and verify
            loaded_spec = load_tool_spec(output_path)
            assert loaded_spec.tool_id == spec.tool_id
            assert loaded_spec.version == spec.version


class TestValidateToolSpecDict:
    """Tests for validate_tool_spec_dict function."""

    def test_validate_valid_dict(self):
        """Test validating valid spec dict."""
        spec_dict = {
            "tool_id": "test_tool",
            "name": "test_tool",
            "version": "1.0.0",
            "description": "Test tool",
            "inputs": {"type": "object", "properties": {}},
            "outputs": {"type": "object", "properties": {}},
            "safety": {},
            "permissions": ["bigquery.jobs.create"],
            "audit": {},
            "metadata": {"created_at": "2024-01-15T00:00:00Z"}
        }
        
        spec = validate_tool_spec_dict(spec_dict)
        assert spec.tool_id == "test_tool"

    def test_validate_invalid_dict(self):
        """Test validating invalid spec dict."""
        spec_dict = {
            "tool_id": "ab",  # Too short
            "name": "test",
            "version": "1.0.0"
        }
        
        with pytest.raises(ValueError):
            validate_tool_spec_dict(spec_dict)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
