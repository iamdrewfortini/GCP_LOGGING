# GENERATED CODE - DO NOT EDIT
# Tool ID: bq_list_datasets
# Version: 1.0.0

from typing import Optional, Any, Dict
from langchain_core.tools import tool
from langchain_core.pydantic_v1 import BaseModel, Field

# Import the actual implementation
from src.services.bigquery_service import list_datasets

# Import Governance
from src.security.policy import enforce_policy
from src.agent.audit import log_tool_use

class BqListDatasetsInput(BaseModel):
    project_id: Optional[str] = Field(default=None, description="Optional project ID. Defaults to the configured logs project.")

@tool("bq_list_datasets", args_schema=BqListDatasetsInput)
def bq_list_datasets(project_id) -> Any:
    '''Lists all datasets in the configured BigQuery project.'''
    
    inputs = locals()
    
    # 1. Policy Check
    enforce_policy("bq_list_datasets", inputs)
    
    # 2. Audit Start
    audit_id = log_tool_use("start", "bq_list_datasets", inputs if True else { "redacted": True })
    
    try:
        # 3. Execution
        result = list_datasets(project_id=project_id)
        
        # 4. Audit End
        log_tool_use("end", "bq_list_datasets", { "result_summary": str(result)[:200] } if False else { "redacted": True }, audit_id=audit_id)
        return result
        
    except Exception as e:
        log_tool_use("error", "bq_list_datasets", str(e), audit_id=audit_id)
        raise e
