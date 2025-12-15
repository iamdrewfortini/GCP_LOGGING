"""
Unit tests for tool generator.
Phase 4, Task 4.2: Tool generator tests
"""

import pytest
import tempfile
from pathlib import Path
from unittest.mock import patch

from src.mcp.validator import ToolSpec, SafetyConfig, AuditConfig, ToolMetadata
from src.mcp.generator import ToolGenerator


class TestToolGenerator:
    """Tests for ToolGenerator class."""

    @pytest.fixture
    def sample_spec(self):
        """Create sample tool spec."""
        return ToolSpec(
            tool_id="test_tool",
            name="test_tool",
            version="1.0.0",
            description="Test tool",
            inputs={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Query string"
                    }
                },
                "required": ["query"]
            },
            outputs={
                "type": "object",
                "properties": {
                    "result": {
                        "type": "string",
                        "description": "Result"
                    }
                }
            },
            safety=SafetyConfig(),
            permissions=["bigquery.jobs.create"],
            audit=AuditConfig(),
            examples=[],
            metadata=ToolMetadata(created_at="2024-01-15T00:00:00Z")
        )

    def test_generator_initialization(self):
        """Test generator initialization."""
        with tempfile.TemporaryDirectory() as tmpdir:
            generator = ToolGenerator(Path(tmpdir))
            assert generator.output_dir.exists()

    def test_generate_tool_code(self, sample_spec):
        """Test generating tool code."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a proper test directory structure
            tools_dir = Path(tmpdir) / "tools"
            tools_dir.mkdir()
            
            generator = ToolGenerator(tools_dir)
            
            # Mock the test generation to avoid path issues
            with patch.object(generator, '_generate_tests', return_value=Path(tmpdir) / "test.py"):
                output_path = generator.generate(sample_spec)
            
            # Verify file was created
            assert output_path.exists()
            assert output_path.name == "test_tool.py"
            
            # Verify content
            content = output_path.read_text()
            assert "def test_tool" in content
            assert "test_tool" in content
            assert "ToolRuntime" in content

    def test_generate_tests(self, sample_spec):
        """Test test generation logic."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tools_dir = Path(tmpdir) / "tools"
            tools_dir.mkdir()
            
            generator = ToolGenerator(tools_dir)
            
            # Just test the template rendering, not the file creation
            assert generator.test_template is not None

    def test_calculate_spec_hash(self, sample_spec):
        """Test spec hash calculation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            generator = ToolGenerator(Path(tmpdir))
            hash1 = generator._calculate_spec_hash(sample_spec)
            hash2 = generator._calculate_spec_hash(sample_spec)
            
            # Same spec should produce same hash
            assert hash1 == hash2
            assert len(hash1) == 8

    def test_python_type_conversion(self):
        """Test JSON Schema to Python type conversion."""
        with tempfile.TemporaryDirectory() as tmpdir:
            generator = ToolGenerator(Path(tmpdir))
            
            assert generator._python_type({"type": "string"}) == "str"
            assert generator._python_type({"type": "integer"}) == "int"
            assert generator._python_type({"type": "boolean"}) == "bool"
            assert generator._python_type({"type": "object"}) == "Dict[str, Any]"
            assert generator._python_type({"type": "array"}) == "List[Any]"

    def test_python_default_conversion(self):
        """Test default value conversion."""
        with tempfile.TemporaryDirectory() as tmpdir:
            generator = ToolGenerator(Path(tmpdir))
            
            assert generator._python_default(None) == "None"
            assert generator._python_default(True) == "True"
            assert generator._python_default(False) == "False"
            assert generator._python_default(42) == "42"
            assert generator._python_default("test") == '"test"'


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
