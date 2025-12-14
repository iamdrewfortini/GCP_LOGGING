from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from datetime import datetime

class BQDryRunInput(BaseModel):
    sql: str
    params: Optional[Dict[str, Any]] = None

class BQDryRunOutput(BaseModel):
    bytes_estimate: int
    referenced_tables: List[str]
    warnings: List[str] = []

class BQQueryInput(BaseModel):
    sql: str
    params: Optional[Dict[str, Any]] = None
    max_rows: int = 1000

class BQQueryOutput(BaseModel):
    job_id: str
    rows: List[Dict[str, Any]]
    total_bytes_processed: int
    cache_hit: bool

class AgentRunArtifact(BaseModel):
    run_id: str
    kind: str
    payload: Dict[str, Any]
    timestamp: datetime = Field(default_factory=datetime.utcnow)
