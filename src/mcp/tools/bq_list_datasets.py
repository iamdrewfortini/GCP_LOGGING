
# Auto-generated tool: bq_list_datasets
# Version: 1.0.0
# Generated at: 2025-12-15T15:58:05.151737+00:00
# Spec hash: 9acd4ac5
# DO NOT EDIT - This file is auto-generated from bq_list_datasets.yaml

from typing import Dict, Any, Optional, List
from langchain_core.tools import tool
from pydantic import BaseModel, Field
from src.mcp.runtime import ToolRuntime
import json

class BqlistdatasetsInput(BaseModel):
    """Input schema for bq_list_datasets tool."""
    
    project_id: Optional[str] = Field(
        description="GCP project ID",
        default="diatonic-ai-gcp"
    )
    

@tool
def bq_list_datasets(
    
    project_id: Optional[str] = "diatonic-ai-gcp"
    
) -> Dict[str, Any]:
    """List all BigQuery datasets in a project
    
    Args:
    
        project_id: GCP project ID
    
    
    Returns:
        Dict containing:
        
        - datasets: List of datasets
        
    
    Raises:
        ValueError: If input validation fails
        RuntimeError: If tool execution fails
    """
    
    # Initialize runtime with safety policies
    runtime = ToolRuntime(
        tool_id="bq_list_datasets",
        version="1.0.0",
        safety_config={"allow_keywords": [], "allowed_datasets": null, "allowed_projects": ["diatonic-ai-gcp"], "allowed_widget_ids": null, "deny_keywords": [], "max_results": 100, "max_rows_returned": 1000, "require_partition_filter": false, "timeout_seconds": 30},
        audit_config={"log_destination": "chat_analytics.tool_invocations", "log_input": true, "log_output": true, "redact_fields": []}
    )
    
    # Validate inputs
    input_data = BqlistdatasetsInput(
        
        project_id=project_id
        
    )
    
    # Execute with safety checks
    result = runtime.execute(
        input_data=input_data.model_dump(),
        executor=_execute_bq_list_datasets
    )
    
    return result


def _execute_bq_list_datasets(input_data: Dict[str, Any]) -> Dict[str, Any]:
    """Execute bq_list_datasets tool logic.
    
    This function contains the actual implementation logic.
    It is called by the runtime after safety checks.
    """
    
    # BigQuery tool implementation
    from google.cloud import bigquery
    
    client = bigquery.Client()
    
    
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
    
    


# Tool metadata
__tool_id__ = "bq_list_datasets"
__version__ = "1.0.0"
__spec_hash__ = "9acd4ac5"
__generated_at__ = "2025-12-15T15:58:05.151737+00:00"