"""
Tool Code Generator

Generates Python tool code from YAML specifications using Jinja2 templates.
Phase 4, Task 4.2: Code generator with Jinja2 templates
"""

import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any
from jinja2 import Template

from src.mcp.validator import ToolSpec


# Jinja2 template for generated tool code
TOOL_TEMPLATE = """
# Auto-generated tool: {{ spec.name }}
# Version: {{ spec.version }}
# Generated at: {{ timestamp }}
# Spec hash: {{ spec_hash }}
# DO NOT EDIT - This file is auto-generated from {{ spec.tool_id }}.yaml

from typing import Dict, Any, Optional, List
from langchain_core.tools import tool
from pydantic import BaseModel, Field
from src.mcp.runtime import ToolRuntime
import json

class {{ spec.name | title | replace('_', '') }}Input(BaseModel):
    \"\"\"Input schema for {{ spec.name }} tool.\"\"\"
    {% for prop_name, prop_schema in spec.inputs.properties.items() %}
    {{ prop_name }}: {{ python_type(prop_schema) }} = Field(
        description="{{ prop_schema.get('description', '') }}"{% if prop_schema.get('default') is not none %},
        default={{ python_default(prop_schema.get('default')) }}{% endif %}
    )
    {% endfor %}

@tool
def {{ spec.name }}(
    {% for prop_name, prop_schema in spec.inputs.properties.items() %}
    {{ prop_name }}: {{ python_type(prop_schema) }}{% if prop_schema.get('default') is not none %} = {{ python_default(prop_schema.get('default')) }}{% endif %}{% if not loop.last %},{% endif %}
    {% endfor %}
) -> Dict[str, Any]:
    \"\"\"{{ spec.description }}
    
    Args:
    {% for prop_name, prop_schema in spec.inputs.properties.items() %}
        {{ prop_name }}: {{ prop_schema.get('description', '') }}
    {% endfor %}
    
    Returns:
        Dict containing:
        {% for prop_name, prop_schema in spec.outputs.properties.items() %}
        - {{ prop_name }}: {{ prop_schema.get('description', '') }}
        {% endfor %}
    
    Raises:
        ValueError: If input validation fails
        RuntimeError: If tool execution fails
    \"\"\"
    
    # Initialize runtime with safety policies
    runtime = ToolRuntime(
        tool_id="{{ spec.tool_id }}",
        version="{{ spec.version }}",
        safety_config={{ spec.safety.model_dump() | tojson }},
        audit_config={{ spec.audit.model_dump() | tojson }}
    )
    
    # Validate inputs
    input_data = {{ spec.name | title | replace('_', '') }}Input(
        {% for prop_name in spec.inputs.properties.keys() %}
        {{ prop_name }}={{ prop_name }}{% if not loop.last %},{% endif %}
        {% endfor %}
    )
    
    # Execute with safety checks
    result = runtime.execute(
        input_data=input_data.model_dump(),
        executor=_execute_{{ spec.name }}
    )
    
    return result


def _execute_{{ spec.name }}(input_data: Dict[str, Any]) -> Dict[str, Any]:
    \"\"\"Execute {{ spec.name }} tool logic.
    
    This function contains the actual implementation logic.
    It is called by the runtime after safety checks.
    \"\"\"
    {% if spec.tool_id.startswith('bq_') %}
    # BigQuery tool implementation
    from google.cloud import bigquery
    
    client = bigquery.Client()
    
    {% if 'query' in spec.tool_id or 'readonly' in spec.tool_id %}
    # Execute read-only query
    sql = input_data['sql']
    
    # Configure job
    job_config = bigquery.QueryJobConfig(
        maximum_bytes_billed=input_data.get('max_bytes_billed', 50000000000),
        use_query_cache=True,
        dry_run=input_data.get('dry_run', False)
    )
    
    # Execute query
    query_job = client.query(sql, job_config=job_config)
    
    if input_data.get('dry_run', False):
        # Dry run - return metadata only
        return {
            "job_id": query_job.job_id,
            "rows": [],
            "bytes_processed": query_job.total_bytes_processed or 0,
            "cache_hit": False,
            "dry_run": True
        }
    
    # Get results
    results = query_job.result(max_results=1000)
    rows = [dict(row) for row in results]
    
    return {
        "job_id": query_job.job_id,
        "rows": rows,
        "bytes_processed": query_job.total_bytes_processed or 0,
        "cache_hit": query_job.cache_hit or False
    }
    {% elif 'list' in spec.tool_id %}
    # List datasets
    project_id = input_data.get('project_id', client.project)
    datasets = list(client.list_datasets(project=project_id))
    
    return {
        "datasets": [
            {
                "dataset_id": ds.dataset_id,
                "project": ds.project,
                "full_id": ds.full_dataset_id
            }
            for ds in datasets
        ]
    }
    {% elif 'schema' in spec.tool_id %}
    # Get table schema
    table_id = input_data['table_id']
    table = client.get_table(table_id)
    
    return {
        "table_id": table.table_id,
        "schema": [
            {
                "name": field.name,
                "type": field.field_type,
                "mode": field.mode,
                "description": field.description
            }
            for field in table.schema
        ],
        "num_rows": table.num_rows,
        "num_bytes": table.num_bytes
    }
    {% endif %}
    {% elif spec.tool_id.startswith('dashboard_') %}
    # Dashboard tool implementation
    from google.cloud import firestore
    
    db = firestore.Client()
    
    {% if 'get' in spec.tool_id %}
    # Get widget config
    widget_id = input_data['widget_id']
    doc = db.collection('dashboard_widgets').document(widget_id).get()
    
    if not doc.exists:
        raise ValueError(f"Widget not found: {widget_id}")
    
    return {
        "widget_id": widget_id,
        "config": doc.to_dict()
    }
    {% endif %}
    {% else %}
    # Generic implementation
    raise NotImplementedError(
        f"Tool execution not implemented for {{ spec.tool_id }}. "
        "Please implement _execute_{{ spec.name }} function."
    )
    {% endif %}


# Tool metadata
__tool_id__ = "{{ spec.tool_id }}"
__version__ = "{{ spec.version }}"
__spec_hash__ = "{{ spec_hash }}"
__generated_at__ = "{{ timestamp }}"
"""


# Template for generated tests
TEST_TEMPLATE = """
# Auto-generated tests for {{ spec.name }}
# Generated at: {{ timestamp }}
# DO NOT EDIT - This file is auto-generated

import pytest
from unittest.mock import Mock, patch
from {{ module_path }} import {{ spec.name }}


class Test{{ spec.name | title | replace('_', '') }}:
    \"\"\"Tests for {{ spec.name }} tool.\"\"\"
    
    {% for example in spec.examples %}
    def test_{{ spec.name }}_{{ example.name | replace(' ', '_') | lower }}(self):
        \"\"\"Test: {{ example.name }}\"\"\"
        # Input
        input_data = {{ example.input | tojson }}
        
        # Execute tool
        {% if 'bq_' in spec.tool_id %}
        with patch('google.cloud.bigquery.Client') as mock_client:
            # Mock BigQuery client
            mock_job = Mock()
            mock_job.job_id = "test_job_123"
            mock_job.total_bytes_processed = 1024
            mock_job.cache_hit = False
            mock_job.result.return_value = []
            
            mock_client.return_value.query.return_value = mock_job
            
            result = {{ spec.name }}(**input_data)
        {% else %}
        result = {{ spec.name }}(**input_data)
        {% endif %}
        
        # Verify result
        assert result is not None
        assert isinstance(result, dict)
        {% if example.expected_output %}
        {% for key in example.expected_output.keys() %}
        assert "{{ key }}" in result
        {% endfor %}
        {% endif %}
    
    {% endfor %}
    
    def test_{{ spec.name }}_input_validation(self):
        \"\"\"Test input validation.\"\"\"
        # Missing required field should raise error
        with pytest.raises(Exception):
            {{ spec.name }}()
    
    def test_{{ spec.name }}_safety_checks(self):
        \"\"\"Test safety checks are applied.\"\"\"
        {% if spec.safety.deny_keywords %}
        # Denied keywords should be blocked
        {% if 'sql' in spec.inputs.properties %}
        with pytest.raises(ValueError, match="Denied keyword"):
            {{ spec.name }}(sql="DROP TABLE users")
        {% endif %}
        {% endif %}
        pass


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
"""


class ToolGenerator:
    """Generate tool code from specifications."""
    
    def __init__(self, output_dir: Path):
        """Initialize generator.
        
        Args:
            output_dir: Directory to write generated tools
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        self.tool_template = Template(TOOL_TEMPLATE)
        self.test_template = Template(TEST_TEMPLATE)
    
    def generate(self, spec: ToolSpec) -> Path:
        """Generate tool code from spec.
        
        Args:
            spec: Tool specification
            
        Returns:
            Path to generated tool file
        """
        # Calculate spec hash for versioning
        spec_hash = self._calculate_spec_hash(spec)
        
        # Render tool code
        code = self.tool_template.render(
            spec=spec,
            timestamp=datetime.now(timezone.utc).isoformat(),
            spec_hash=spec_hash,
            python_type=self._python_type,
            python_default=self._python_default
        )
        
        # Write tool file
        output_path = self.output_dir / f"{spec.tool_id}.py"
        output_path.write_text(code)
        
        # Generate tests
        test_path = self._generate_tests(spec)
        
        return output_path
    
    def _generate_tests(self, spec: ToolSpec) -> Path:
        """Generate unit tests from examples.
        
        Args:
            spec: Tool specification
            
        Returns:
            Path to generated test file
        """
        # Render test code
        test_code = self.test_template.render(
            spec=spec,
            timestamp=datetime.now(timezone.utc).isoformat(),
            module_path=f"src.mcp.tools.{spec.tool_id}"
        )
        
        # Write test file
        test_dir = self.output_dir.parent.parent / "tests" / "mcp"
        test_dir.mkdir(parents=True, exist_ok=True)
        
        test_path = test_dir / f"test_{spec.tool_id}.py"
        test_path.write_text(test_code)
        
        return test_path
    
    def _calculate_spec_hash(self, spec: ToolSpec) -> str:
        """Calculate hash of spec for versioning.
        
        Args:
            spec: Tool specification
            
        Returns:
            8-character hex hash
        """
        import json
        spec_dict = spec.model_dump()
        spec_json = json.dumps(spec_dict, sort_keys=True)
        hash_obj = hashlib.sha256(spec_json.encode())
        return hash_obj.hexdigest()[:8]
    
    def _python_type(self, schema: Dict[str, Any]) -> str:
        """Convert JSON Schema type to Python type hint.
        
        Args:
            schema: JSON Schema property definition
            
        Returns:
            Python type hint string
        """
        json_type = schema.get("type", "any")
        
        type_map = {
            "string": "str",
            "integer": "int",
            "number": "float",
            "boolean": "bool",
            "object": "Dict[str, Any]",
            "array": "List[Any]",
            "null": "None"
        }
        
        python_type = type_map.get(json_type, "Any")
        
        # Handle optional fields
        if schema.get("default") is not None or not schema.get("required", True):
            python_type = f"Optional[{python_type}]"
        
        return python_type
    
    def _python_default(self, value: Any) -> str:
        """Convert default value to Python literal.
        
        Args:
            value: Default value
            
        Returns:
            Python literal string
        """
        if value is None:
            return "None"
        elif isinstance(value, bool):
            return str(value)
        elif isinstance(value, (int, float)):
            return str(value)
        elif isinstance(value, str):
            return f'"{value}"'
        elif isinstance(value, (list, dict)):
            return repr(value)
        else:
            return repr(value)
