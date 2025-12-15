# MCP Tool Generator Template

**Date:** 2025-12-15
**Goal:** Automate the creation of safe, standardized tools for the AI Agent.

## 1. Tool Definition Schema (`tool_spec.yaml`)

This schema defines *what* a tool does, *how* it's called, and *who* can use it.

```yaml
id: "bq_query_readonly"
name: "BigQuery Read-Only Query"
description: "Executes a SQL query against BigQuery. Strictly read-only."
version: "1.0.0"

inputs:
  type: "object"
  properties:
    sql:
      type: "string"
      description: "Standard SQL query."
    dry_run:
      type: "boolean"
      default: false
  required: ["sql"]

policy:
  requires_approval: false
  max_duration_ms: 30000
  allowed_datasets: ["glass_logging_v2"]
  deny_keywords: ["DROP", "DELETE", "UPDATE", "INSERT", "ALTER"]

execution:
  runtime: "python"
  module: "src.services.bigquery"
  function: "execute_query"
  
audit:
  log_inputs: true
  log_outputs: true # Set false if PII risk is high
```

## 2. Generator Workflow

A script (`scripts/generate_mcp_tool.py`) will process these specs.

1.  **Validation:** Check schema validity, ensure `module` and `function` exist.
2.  **Wrapper Gen:** Create `src/agent/tools/generated/{id}.py`.
    - Inject Redaction logic.
    - Inject Policy checks (regex for keywords).
    - Inject Audit logging.
    - Inject Timeout handling.
3.  **Registration:** Update `src/agent/tools/registry.py` to include the new tool.
4.  **Docs Gen:** Append to `docs/TOOLS.md`.

## 3. Example Generated Code (Python)

```python
# GENERATED CODE - DO NOT EDIT
from langchain_core.tools import tool
from src.services.bigquery import execute_query
from src.security.policy import enforce_policy
from src.agent.audit import log_tool_use

@tool
def bq_query_readonly(sql: str, dry_run: bool = False):
    """Executes a SQL query against BigQuery. Strictly read-only."""
    
    # 1. Policy Check
    enforce_policy("bq_query_readonly", {"sql": sql})
    
    # 2. Audit Start
    audit_id = log_tool_use("start", "bq_query_readonly", {"sql": sql})
    
    try:
        # 3. Execution
        result = execute_query(sql=sql, dry_run=dry_run)
        
        # 4. Audit End
        log_tool_use("end", "bq_query_readonly", {"result_summary": "..."})
        return result
        
    except Exception as e:
        log_tool_use("error", "bq_query_readonly", str(e))
        raise e
```

## 4. Standard Tool Catalog

### BigQuery
- `bq_list_datasets`: List available datasets.
- `bq_list_tables(dataset)`: List tables and metadata.
- `bq_get_schema(dataset, table)`: Get field names and types.
- `bq_query_readonly(sql)`: Execute SELECT queries.

### Dashboard / Config
- `dashboard_get_config(id)`: Retrieve JSON spec of a dashboard.
- `dashboard_patch_config(id, patch)`: Update config (requires approval).

### Repository
- `repo_read_file(path)`: Read file content.
- `repo_search(query)`: Semantic search over code.
- `repo_list_dir(path)`: List directory contents.

## 5. Security Guardrails

- **AST Analysis:** For Python tools, parse the code to ensure it imports only allowed modules.
- **SQL Parsing:** Use `sqlglot` to verify SQL queries are strictly `SELECT` statements if defined as read-only.
- **Rate Limiting:** Per-user/Per-session limits defined in the Spec.
