# MCP Tool Generator Template

**Date:** 2025-12-15  
**Status:** Proposed - MUST BE SCRIPTABLE  
**Version:** 1.0

---

## Overview

The MCP Tool Generator enables the AI agent to safely generate its own tools for BigQuery queries, dashboard operations, and system introspection. This is a **meta-capability** that allows the system to extend itself.

**Key Requirements:**
1. **Safe by default** - Generated tools must have guardrails
2. **Auditable** - All tool generation and execution logged
3. **Deterministic** - Same spec → same tool code
4. **Testable** - Auto-generate unit tests
5. **Versioned** - Track tool evolution

---

## Tool Spec Schema (YAML)

```yaml
# src/mcp/specs/bq_query_readonly.yaml
tool_id: bq_query_readonly
name: bq_query_readonly
version: "1.0.0"
description: "Execute read-only BigQuery queries with safety guardrails"

# Input schema (JSON Schema)
inputs:
  type: object
  properties:
    sql:
      type: string
      description: "SQL query to execute"
      maxLength: 10000
    params:
      type: object
      description: "Query parameters"
      additionalProperties: true
    dry_run:
      type: boolean
      description: "Run dry-run first"
      default: true
    max_bytes_billed:
      type: integer
      description: "Maximum bytes to bill"
      default: 50000000000  # 50GB
  required: [sql]

# Output schema
outputs:
  type: object
  properties:
    job_id:
      type: string
    rows:
      type: array
      items:
        type: object
    bytes_processed:
      type: integer
    cache_hit:
      type: boolean

# Safety policies
safety:
  # SQL keyword allowlist/denylist
  deny_keywords:
    - "DROP"
    - "DELETE"
    - "UPDATE"
    - "INSERT"
    - "TRUNCATE"
    - "ALTER"
    - "CREATE"
    - "GRANT"
    - "REVOKE"
  
  allow_keywords:
    - "SELECT"
    - "WITH"
    - "FROM"
    - "WHERE"
    - "GROUP BY"
    - "ORDER BY"
    - "LIMIT"
  
  # Dataset/table restrictions
  allowed_datasets:
    - "central_logging_v1"
    - "chat_analytics"
    - "org_agent"
  
  # Row limits
  max_rows_returned: 1000
  
  # Require partition filters
  require_partition_filter: true
  
  # Timeout
  timeout_seconds: 60

# Permissions (IAM-style)
permissions:
  - "bigquery.jobs.create"
  - "bigquery.tables.getData"

# Logging requirements
audit:
  log_input: true
  log_output: true
  redact_fields: ["email", "ip_address", "user_id"]
  log_destination: "chat_analytics.tool_invocations"

# Examples (for testing and documentation)
examples:
  - name: "Query recent errors"
    input:
      sql: |
        SELECT event_ts, severity, service, display_message
        FROM `diatonic-ai-gcp.central_logging_v1.view_canonical_logs`
        WHERE DATE(event_ts) = CURRENT_DATE()
          AND severity = 'ERROR'
        LIMIT 10
      dry_run: true
    expected_output:
      job_id: "job_123"
      rows: []
      bytes_processed: 1024
      cache_hit: false

# Metadata
metadata:
  author: "system"
  created_at: "2025-12-15T00:00:00Z"
  tags: ["bigquery", "read-only", "safe"]
  cost_estimate_usd: 0.0001  # Per invocation
```

---

## Generator Implementation

### 1. Spec Validator

```python
# src/mcp/validator.py
from pydantic import BaseModel, Field, validator
from typing import List, Dict, Any, Optional
import yaml

class ToolSpec(BaseModel):
    tool_id: str
    name: str
    version: str
    description: str
    inputs: Dict[str, Any]
    outputs: Dict[str, Any]
    safety: Dict[str, Any]
    permissions: List[str]
    audit: Dict[str, Any]
    examples: List[Dict[str, Any]]
    metadata: Dict[str, Any]
    
    @validator("tool_id")
    def validate_tool_id(cls, v):
        if not v.replace("_", "").isalnum():
            raise ValueError("tool_id must be alphanumeric with underscores")
        return v
    
    @validator("safety")
    def validate_safety(cls, v):
        required_keys = ["deny_keywords", "allow_keywords", "allowed_datasets"]
        for key in required_keys:
            if key not in v:
                raise ValueError(f"safety.{key} is required")
        return v

def load_tool_spec(spec_path: str) -> ToolSpec:
    """Load and validate tool spec from YAML"""
    with open(spec_path, "r") as f:
        spec_data = yaml.safe_load(f)
    return ToolSpec(**spec_data)
```

### 2. Code Generator

```python
# src/mcp/generator.py
from jinja2 import Template
from pathlib import Path
import hashlib

TOOL_TEMPLATE = """
# Auto-generated tool: {{ spec.name }}
# Version: {{ spec.version }}
# Generated at: {{ timestamp }}
# Spec hash: {{ spec_hash }}

from langchain_core.tools import tool
from pydantic import BaseModel, Field
from typing import Dict, Any, Optional
from src.mcp.runtime import ToolRuntime
import json

class {{ spec.name | title }}Input(BaseModel):
    {% for prop_name, prop_schema in spec.inputs.properties.items() %}
    {{ prop_name }}: {{ python_type(prop_schema) }} = Field(
        description="{{ prop_schema.description }}",
        {% if prop_schema.get('default') %}default={{ prop_schema.default }},{% endif %}
    )
    {% endfor %}

@tool
def {{ spec.name }}(
    {% for prop_name in spec.inputs.properties.keys() %}
    {{ prop_name }}: {{ python_type(spec.inputs.properties[prop_name]) }}{% if not loop.last %},{% endif %}
    {% endfor %}
) -> Dict[str, Any]:
    \"\"\"{{ spec.description }}\"\"\"
    
    # Initialize runtime with safety policies
    runtime = ToolRuntime(
        tool_id="{{ spec.tool_id }}",
        version="{{ spec.version }}",
        safety_config={{ spec.safety | tojson }},
        audit_config={{ spec.audit | tojson }}
    )
    
    # Validate inputs
    input_data = {{ spec.name | title }}Input(
        {% for prop_name in spec.inputs.properties.keys() %}
        {{ prop_name }}={{ prop_name }}{% if not loop.last %},{% endif %}
        {% endfor %}
    )
    
    # Execute with safety checks
    result = runtime.execute(
        input_data=input_data.dict(),
        executor=_execute_{{ spec.name }}
    )
    
    return result

def _execute_{{ spec.name }}(input_data: Dict[str, Any]) -> Dict[str, Any]:
    \"\"\"Actual execution logic\"\"\"
    # TODO: Implement tool-specific logic
    {% if spec.tool_id.startswith('bq_') %}
    from google.cloud import bigquery
    client = bigquery.Client()
    
    # Execute query
    job_config = bigquery.QueryJobConfig(
        maximum_bytes_billed=input_data.get('max_bytes_billed', 50000000000),
        use_query_cache=True
    )
    
    query_job = client.query(input_data['sql'], job_config=job_config)
    rows = [dict(row) for row in query_job.result(max_results=1000)]
    
    return {
        "job_id": query_job.job_id,
        "rows": rows,
        "bytes_processed": query_job.total_bytes_processed,
        "cache_hit": query_job.cache_hit
    }
    {% else %}
    raise NotImplementedError("Tool execution not implemented")
    {% endif %}
"""

class ToolGenerator:
    def __init__(self, output_dir: Path):
        self.output_dir = output_dir
        self.template = Template(TOOL_TEMPLATE)
    
    def generate(self, spec: ToolSpec) -> Path:
        """Generate tool code from spec"""
        # Calculate spec hash for versioning
        spec_hash = hashlib.sha256(spec.json().encode()).hexdigest()[:8]
        
        # Render template
        code = self.template.render(
            spec=spec,
            timestamp=datetime.utcnow().isoformat(),
            spec_hash=spec_hash,
            python_type=self._python_type
        )
        
        # Write to file
        output_path = self.output_dir / f"{spec.tool_id}.py"
        output_path.write_text(code)
        
        # Generate tests
        self._generate_tests(spec, output_path)
        
        # Register tool
        self._register_tool(spec, spec_hash)
        
        return output_path
    
    def _python_type(self, schema: Dict[str, Any]) -> str:
        """Convert JSON Schema type to Python type"""
        type_map = {
            "string": "str",
            "integer": "int",
            "number": "float",
            "boolean": "bool",
            "object": "Dict[str, Any]",
            "array": "List[Any]"
        }
        return type_map.get(schema.get("type"), "Any")
    
    def _generate_tests(self, spec: ToolSpec, tool_path: Path):
        """Generate unit tests from examples"""
        test_code = f"""
# Auto-generated tests for {spec.name}
import pytest
from {tool_path.stem} import {spec.name}

"""
        for example in spec.examples:
            test_code += f"""
def test_{spec.name}_{example['name'].replace(' ', '_')}():
    result = {spec.name}(**{example['input']})
    assert result is not None
    # Add more assertions based on expected_output
"""
        
        test_path = self.output_dir.parent / "tests" / f"test_{spec.tool_id}.py"
        test_path.parent.mkdir(parents=True, exist_ok=True)
        test_path.write_text(test_code)
    
    def _register_tool(self, spec: ToolSpec, spec_hash: str):
        """Register tool in registry"""
        from src.mcp.registry import tool_registry
        tool_registry.register(
            tool_id=spec.tool_id,
            version=spec.version,
            spec_hash=spec_hash,
            module_path=f"src.mcp.tools.{spec.tool_id}",
            safety_config=spec.safety,
            permissions=spec.permissions
        )
```

### 3. Runtime with Safety Checks

```python
# src/mcp/runtime.py
from typing import Dict, Any, Callable
from google.cloud import bigquery, firestore
import re
import time

class ToolRuntime:
    def __init__(
        self,
        tool_id: str,
        version: str,
        safety_config: Dict[str, Any],
        audit_config: Dict[str, Any]
    ):
        self.tool_id = tool_id
        self.version = version
        self.safety = safety_config
        self.audit = audit_config
        self.db = firestore.Client()
        self.bq = bigquery.Client()
    
    def execute(
        self,
        input_data: Dict[str, Any],
        executor: Callable
    ) -> Dict[str, Any]:
        """Execute tool with safety checks and audit logging"""
        invocation_id = generate_id()
        start_time = time.time()
        
        try:
            # 1. Pre-execution safety checks
            self._validate_input(input_data)
            
            # 2. Execute
            result = executor(input_data)
            
            # 3. Post-execution validation
            self._validate_output(result)
            
            # 4. Audit log
            duration_ms = (time.time() - start_time) * 1000
            self._log_invocation(
                invocation_id=invocation_id,
                input_data=input_data,
                output_data=result,
                status="success",
                duration_ms=duration_ms
            )
            
            return result
        
        except Exception as e:
            # Log error
            duration_ms = (time.time() - start_time) * 1000
            self._log_invocation(
                invocation_id=invocation_id,
                input_data=input_data,
                output_data=None,
                status="error",
                duration_ms=duration_ms,
                error_message=str(e)
            )
            raise
    
    def _validate_input(self, input_data: Dict[str, Any]):
        """Validate input against safety policies"""
        # Check for denied keywords (e.g., in SQL)
        if "sql" in input_data:
            sql = input_data["sql"].upper()
            for keyword in self.safety.get("deny_keywords", []):
                if keyword in sql:
                    raise ValueError(f"Denied keyword: {keyword}")
        
        # Check dataset restrictions
        if "sql" in input_data and "allowed_datasets" in self.safety:
            sql = input_data["sql"]
            datasets = re.findall(r"`([^`]+)`", sql)
            for dataset in datasets:
                if not any(allowed in dataset for allowed in self.safety["allowed_datasets"]):
                    raise ValueError(f"Dataset not allowed: {dataset}")
    
    def _validate_output(self, output_data: Dict[str, Any]):
        """Validate output against safety policies"""
        # Check row count limit
        if "rows" in output_data:
            max_rows = self.safety.get("max_rows_returned", 1000)
            if len(output_data["rows"]) > max_rows:
                output_data["rows"] = output_data["rows"][:max_rows]
                output_data["truncated"] = True
    
    def _log_invocation(
        self,
        invocation_id: str,
        input_data: Dict[str, Any],
        output_data: Dict[str, Any],
        status: str,
        duration_ms: float,
        error_message: str = None
    ):
        """Log tool invocation to BigQuery"""
        # Redact sensitive fields
        if self.audit.get("redact_fields"):
            input_data = self._redact(input_data, self.audit["redact_fields"])
            if output_data:
                output_data = self._redact(output_data, self.audit["redact_fields"])
        
        # Insert to BigQuery
        table_id = f"diatonic-ai-gcp.{self.audit['log_destination']}"
        row = {
            "invocation_id": invocation_id,
            "tool_name": self.tool_id,
            "tool_version": self.version,
            "started_at": datetime.utcnow().isoformat(),
            "duration_ms": duration_ms,
            "status": status,
            "input_summary": str(input_data)[:500],
            "output_summary": str(output_data)[:500] if output_data else None,
            "error_message": error_message
        }
        
        self.bq.insert_rows_json(table_id, [row])
    
    def _redact(self, data: Dict[str, Any], fields: List[str]) -> Dict[str, Any]:
        """Redact sensitive fields"""
        redacted = data.copy()
        for field in fields:
            if field in redacted:
                redacted[field] = "[REDACTED]"
        return redacted
```

### 4. Tool Registry

```python
# src/mcp/registry.py
from typing import Dict, Any, List
from google.cloud import firestore

class ToolRegistry:
    def __init__(self):
        self.db = firestore.Client()
        self._cache = {}
    
    def register(
        self,
        tool_id: str,
        version: str,
        spec_hash: str,
        module_path: str,
        safety_config: Dict[str, Any],
        permissions: List[str]
    ):
        """Register a generated tool"""
        self.db.collection("mcp_tools").document(tool_id).set({
            "tool_id": tool_id,
            "version": version,
            "spec_hash": spec_hash,
            "module_path": module_path,
            "safety_config": safety_config,
            "permissions": permissions,
            "created_at": firestore.SERVER_TIMESTAMP,
            "status": "active"
        })
        
        # Invalidate cache
        self._cache.pop(tool_id, None)
    
    def get_tool(self, tool_id: str):
        """Get tool metadata"""
        if tool_id in self._cache:
            return self._cache[tool_id]
        
        doc = self.db.collection("mcp_tools").document(tool_id).get()
        if doc.exists:
            self._cache[tool_id] = doc.to_dict()
            return self._cache[tool_id]
        
        return None
    
    def list_tools(self, status: str = "active") -> List[Dict[str, Any]]:
        """List all registered tools"""
        query = self.db.collection("mcp_tools").where("status", "==", status)
        return [doc.to_dict() for doc in query.stream()]

tool_registry = ToolRegistry()
```

---

## Usage Example

### Generate Tool from Spec

```bash
# Generate tool from YAML spec
python -m src.mcp.cli generate src/mcp/specs/bq_query_readonly.yaml

# Output:
# ✓ Validated spec: bq_query_readonly v1.0.0
# ✓ Generated code: src/mcp/tools/bq_query_readonly.py
# ✓ Generated tests: tests/mcp/test_bq_query_readonly.py
# ✓ Registered tool: bq_query_readonly (hash: a1b2c3d4)
```

### Use Generated Tool

```python
# Import generated tool
from src.mcp.tools.bq_query_readonly import bq_query_readonly

# Use in LangGraph
result = bq_query_readonly(
    sql="SELECT * FROM `diatonic-ai-gcp.central_logging_v1.view_canonical_logs` WHERE DATE(event_ts) = CURRENT_DATE() LIMIT 10",
    dry_run=True
)

print(result["job_id"])
print(f"Would process {result['bytes_processed']} bytes")
```

---

## Example Tool Specs

### 1. bq_list_datasets

```yaml
tool_id: bq_list_datasets
name: bq_list_datasets
version: "1.0.0"
description: "List all BigQuery datasets in a project"
inputs:
  type: object
  properties:
    project_id:
      type: string
      description: "GCP project ID"
      default: "diatonic-ai-gcp"
outputs:
  type: object
  properties:
    datasets:
      type: array
      items:
        type: object
safety:
  deny_keywords: []
  allow_keywords: []
  allowed_projects: ["diatonic-ai-gcp"]
  max_results: 100
permissions:
  - "bigquery.datasets.get"
audit:
  log_input: true
  log_output: true
  log_destination: "chat_analytics.tool_invocations"
```

### 2. dashboard_get_widget_config

```yaml
tool_id: dashboard_get_widget_config
name: dashboard_get_widget_config
version: "1.0.0"
description: "Get configuration for a dashboard widget"
inputs:
  type: object
  properties:
    widget_id:
      type: string
      description: "Widget identifier"
  required: [widget_id]
outputs:
  type: object
  properties:
    config:
      type: object
safety:
  allowed_widget_ids: ["*"]  # All widgets readable
permissions:
  - "dashboard.widgets.get"
audit:
  log_input: true
  log_output: false
  log_destination: "chat_analytics.tool_invocations"
```

---

## Security Considerations

1. **Spec validation** - All specs must pass schema validation
2. **Code review** - Generated code should be reviewed before deployment
3. **Sandboxing** - Tools run with limited permissions
4. **Rate limiting** - Enforce per-user rate limits
5. **Audit trail** - All tool generation and execution logged
6. **Versioning** - Track tool evolution, allow rollback

---

**Next:** See `08_implementation_tasks.toon.json` for phased rollout plan.

**End of MCP Tool Generator Template**
