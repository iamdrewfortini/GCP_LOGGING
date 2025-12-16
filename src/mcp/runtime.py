"""
Tool Runtime with Safety Checks

Executes generated tools with safety validation and audit logging.
Phase 4, Task 4.3: ToolRuntime with safety checks
"""

import logging
import re
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from google.cloud import bigquery

logger = logging.getLogger(__name__)


def generate_id() -> str:
    """Generate unique ID."""
    return str(uuid.uuid4())


class ToolRuntime:
    """Runtime for executing generated tools with safety checks.

    NOTE: This class must be safe to import and instantiate in unit tests.
    Do not create Google Cloud clients (BigQuery/Firestore/etc.) at import time
    or in __init__.
    """

    def __init__(
        self,
        tool_id: str,
        version: str,
        safety_config: Dict[str, Any],
        audit_config: Dict[str, Any],
        *,
        bq_client: Optional[bigquery.Client] = None,
    ):
        """Initialize tool runtime.
        
        Args:
            tool_id: Tool identifier
            version: Tool version
            safety_config: Safety policies
            audit_config: Audit logging configuration
        """
        self.tool_id = tool_id
        self.version = version
        self.safety = safety_config
        self.audit = audit_config

        # Lazy-init clients only when needed (e.g., audit logging).
        self._bq: Optional[bigquery.Client] = bq_client
    
    def execute(
        self,
        input_data: Dict[str, Any],
        executor: Callable[[Dict[str, Any]], Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Execute tool with safety checks and audit logging.
        
        Args:
            input_data: Tool input parameters
            executor: Function that executes the tool logic
            
        Returns:
            Tool execution result
            
        Raises:
            ValueError: If safety validation fails
            RuntimeError: If execution fails
        """
        invocation_id = generate_id()
        start_time = time.time()
        
        try:
            # 1. Pre-execution safety checks
            self._validate_input(input_data)
            
            # 2. Check timeout
            timeout = self.safety.get("timeout_seconds", 60)
            
            # 3. Execute tool logic
            result = executor(input_data)
            
            # 4. Post-execution validation
            result = self._validate_output(result)
            
            # 5. Calculate duration
            duration_ms = (time.time() - start_time) * 1000
            
            # 6. Audit log
            self._log_invocation(
                invocation_id=invocation_id,
                input_data=input_data,
                output_data=result,
                status="success",
                duration_ms=duration_ms
            )
            
            logger.info(
                f"Tool {self.tool_id} executed successfully "
                f"(invocation={invocation_id}, duration={duration_ms:.0f}ms)"
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
            
            logger.error(
                f"Tool {self.tool_id} execution failed "
                f"(invocation={invocation_id}, error={e})"
            )
            
            raise
    
    def _validate_input(self, input_data: Dict[str, Any]) -> None:
        """Validate input against safety policies.
        
        Args:
            input_data: Tool input parameters
            
        Raises:
            ValueError: If validation fails
        """
        # Check for denied keywords (e.g., in SQL)
        if "sql" in input_data:
            sql = input_data["sql"].upper()
            
            # Check denied keywords
            deny_keywords = self.safety.get("deny_keywords", [])
            for keyword in deny_keywords:
                if keyword.upper() in sql:
                    raise ValueError(f"Denied keyword: {keyword}")
            
            # Check allowed keywords (if specified)
            allow_keywords = self.safety.get("allow_keywords", [])
            if allow_keywords:
                # Extract SQL keywords
                sql_keywords = re.findall(r'\b[A-Z]+\b', sql)
                for keyword in sql_keywords:
                    if keyword not in allow_keywords and keyword not in ["AND", "OR", "NOT", "AS", "ON", "IN"]:
                        raise ValueError(f"Keyword not allowed: {keyword}")
        
        # Check dataset restrictions
        if "sql" in input_data and "allowed_datasets" in self.safety:
            sql = input_data["sql"]
            
            # Extract dataset references (format: `project.dataset.table`)
            dataset_refs = re.findall(r'`([^`]+)`', sql)
            
            allowed_datasets = self.safety["allowed_datasets"]
            for ref in dataset_refs:
                # Check if any allowed dataset is in the reference
                if not any(allowed in ref for allowed in allowed_datasets):
                    raise ValueError(f"Dataset not allowed: {ref}")
        
        # Check project restrictions
        if "project_id" in input_data and "allowed_projects" in self.safety:
            project_id = input_data["project_id"]
            allowed_projects = self.safety["allowed_projects"]
            
            if project_id not in allowed_projects:
                raise ValueError(f"Project not allowed: {project_id}")
        
        # Check widget ID restrictions
        if "widget_id" in input_data and "allowed_widget_ids" in self.safety:
            widget_id = input_data["widget_id"]
            allowed_ids = self.safety["allowed_widget_ids"]
            
            # "*" means all widgets allowed
            if "*" not in allowed_ids and widget_id not in allowed_ids:
                raise ValueError(f"Widget not allowed: {widget_id}")
    
    def _validate_output(self, output_data: Dict[str, Any]) -> Dict[str, Any]:
        """Validate output against safety policies.
        
        Args:
            output_data: Tool output
            
        Returns:
            Validated (possibly truncated) output
        """
        # Check row count limit
        if "rows" in output_data:
            max_rows = self.safety.get("max_rows_returned", 1000)
            
            if len(output_data["rows"]) > max_rows:
                output_data["rows"] = output_data["rows"][:max_rows]
                output_data["truncated"] = True
                
                logger.warning(
                    f"Output truncated to {max_rows} rows "
                    f"(tool={self.tool_id})"
                )
        
        # Check result count limit
        if "datasets" in output_data:
            max_results = self.safety.get("max_results", 100)
            
            if len(output_data["datasets"]) > max_results:
                output_data["datasets"] = output_data["datasets"][:max_results]
                output_data["truncated"] = True
        
        return output_data
    
    def _get_bq_client(self) -> Optional[bigquery.Client]:
        """Return a BigQuery client if audit logging is enabled.

        We only construct this lazily to keep unit tests fast and to avoid
        requiring ADC during import/collection in CI.
        """
        if self._bq is not None:
            return self._bq

        try:
            self._bq = bigquery.Client()
            return self._bq
        except Exception as e:
            logger.warning(f"BigQuery client init failed (audit disabled): {e}")
            return None

    def _log_invocation(
        self,
        invocation_id: str,
        input_data: Dict[str, Any],
        output_data: Dict[str, Any] | None,
        status: str,
        duration_ms: float,
        error_message: str | None = None
    ) -> None:
        """Log tool invocation to BigQuery.
        
        Args:
            invocation_id: Unique invocation ID
            input_data: Tool input
            output_data: Tool output (if successful)
            status: Execution status
            duration_ms: Execution duration
            error_message: Error message (if failed)
        """
        if not self.audit.get("log_input") and not self.audit.get("log_output"):
            return
        
        # Redact sensitive fields
        redact_fields = self.audit.get("redact_fields", [])
        if redact_fields:
            input_data = self._redact(input_data, redact_fields)
            if output_data:
                output_data = self._redact(output_data, redact_fields)
        
        # Prepare log entry
        log_entry = {
            "invocation_id": invocation_id,
            "tool_name": self.tool_id,
            "tool_version": self.version,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "duration_ms": int(duration_ms),
            "status": status,
            "error_message": error_message
        }
        
        # Add input/output if logging enabled
        if self.audit.get("log_input"):
            log_entry["input_summary"] = str(input_data)[:500]
        
        if self.audit.get("log_output") and output_data:
            log_entry["output_summary"] = str(output_data)[:500]
        
        bq = self._get_bq_client()
        if bq is None:
            return

        # Insert to BigQuery
        try:
            table_id = f"{bq.project}.{self.audit['log_destination']}"
            errors = bq.insert_rows_json(table_id, [log_entry])

            if errors:
                logger.error(f"Failed to log invocation: {errors}")
        except Exception as e:
            logger.error(f"Failed to log invocation: {e}")
    
    def _redact(self, data: Dict[str, Any], fields: List[str]) -> Dict[str, Any]:
        """Redact sensitive fields from data.
        
        Args:
            data: Data to redact
            fields: Fields to redact
            
        Returns:
            Redacted data
        """
        redacted = data.copy()
        
        for field in fields:
            if field in redacted:
                redacted[field] = "[REDACTED]"
        
        return redacted
