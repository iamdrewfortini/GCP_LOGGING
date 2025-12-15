"""
Tool Spec Validator

Validates YAML tool specifications against schema.
Phase 4, Task 4.1: Create tool spec schema and validator
"""

from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field, field_validator
import yaml
from pathlib import Path


class SafetyConfig(BaseModel):
    """Safety configuration for tool execution."""
    deny_keywords: List[str] = Field(default_factory=list)
    allow_keywords: List[str] = Field(default_factory=list)
    allowed_datasets: Optional[List[str]] = None
    allowed_projects: Optional[List[str]] = None
    allowed_widget_ids: Optional[List[str]] = None
    max_rows_returned: int = Field(default=1000)
    require_partition_filter: bool = Field(default=False)
    timeout_seconds: int = Field(default=60)
    max_results: Optional[int] = None


class AuditConfig(BaseModel):
    """Audit logging configuration."""
    log_input: bool = Field(default=True)
    log_output: bool = Field(default=True)
    redact_fields: List[str] = Field(default_factory=list)
    log_destination: str = Field(default="chat_analytics.tool_invocations")


class ToolExample(BaseModel):
    """Example usage of the tool."""
    name: str
    input: Dict[str, Any]
    expected_output: Optional[Dict[str, Any]] = None


class ToolMetadata(BaseModel):
    """Tool metadata."""
    author: str = Field(default="system")
    created_at: str
    tags: List[str] = Field(default_factory=list)
    cost_estimate_usd: float = Field(default=0.0001)


class ToolSpec(BaseModel):
    """Complete tool specification."""
    tool_id: str
    name: str
    version: str
    description: str
    inputs: Dict[str, Any]
    outputs: Dict[str, Any]
    safety: SafetyConfig
    permissions: List[str]
    audit: AuditConfig
    examples: List[ToolExample] = Field(default_factory=list)
    metadata: ToolMetadata

    @field_validator("tool_id")
    @classmethod
    def validate_tool_id(cls, v: str) -> str:
        """Validate tool_id format."""
        if not v.replace("_", "").replace("-", "").isalnum():
            raise ValueError("tool_id must be alphanumeric with underscores or hyphens")
        if len(v) < 3:
            raise ValueError("tool_id must be at least 3 characters")
        if len(v) > 64:
            raise ValueError("tool_id must be at most 64 characters")
        return v

    @field_validator("version")
    @classmethod
    def validate_version(cls, v: str) -> str:
        """Validate semantic version format."""
        parts = v.split(".")
        if len(parts) != 3:
            raise ValueError("version must be in format X.Y.Z")
        for part in parts:
            if not part.isdigit():
                raise ValueError("version parts must be numeric")
        return v

    @field_validator("inputs")
    @classmethod
    def validate_inputs(cls, v: Dict[str, Any]) -> Dict[str, Any]:
        """Validate inputs schema."""
        if "type" not in v:
            raise ValueError("inputs must have 'type' field")
        if v["type"] != "object":
            raise ValueError("inputs type must be 'object'")
        if "properties" not in v:
            raise ValueError("inputs must have 'properties' field")
        return v

    @field_validator("outputs")
    @classmethod
    def validate_outputs(cls, v: Dict[str, Any]) -> Dict[str, Any]:
        """Validate outputs schema."""
        if "type" not in v:
            raise ValueError("outputs must have 'type' field")
        if v["type"] != "object":
            raise ValueError("outputs type must be 'object'")
        if "properties" not in v:
            raise ValueError("outputs must have 'properties' field")
        return v

    @field_validator("permissions")
    @classmethod
    def validate_permissions(cls, v: List[str]) -> List[str]:
        """Validate permissions format."""
        if not v:
            raise ValueError("At least one permission is required")
        
        valid_prefixes = [
            "bigquery.",
            "dashboard.",
            "firestore.",
            "storage.",
            "pubsub.",
            "logging.",
        ]
        
        for perm in v:
            if not any(perm.startswith(prefix) for prefix in valid_prefixes):
                raise ValueError(f"Invalid permission format: {perm}")
        
        return v


def load_tool_spec(spec_path: str | Path) -> ToolSpec:
    """Load and validate tool spec from YAML file.

    Args:
        spec_path: Path to YAML spec file

    Returns:
        Validated ToolSpec

    Raises:
        FileNotFoundError: If spec file doesn't exist
        ValueError: If spec is invalid
        yaml.YAMLError: If YAML is malformed
    """
    spec_path = Path(spec_path)
    
    if not spec_path.exists():
        raise FileNotFoundError(f"Spec file not found: {spec_path}")
    
    with open(spec_path, "r") as f:
        spec_data = yaml.safe_load(f)
    
    if not spec_data:
        raise ValueError("Spec file is empty")
    
    # Parse and validate
    try:
        spec = ToolSpec(**spec_data)
    except Exception as e:
        raise ValueError(f"Invalid tool spec: {e}")
    
    return spec


def validate_tool_spec_dict(spec_data: Dict[str, Any]) -> ToolSpec:
    """Validate tool spec from dictionary.

    Args:
        spec_data: Tool spec as dictionary

    Returns:
        Validated ToolSpec

    Raises:
        ValueError: If spec is invalid
    """
    try:
        spec = ToolSpec(**spec_data)
    except Exception as e:
        raise ValueError(f"Invalid tool spec: {e}")
    
    return spec


def save_tool_spec(spec: ToolSpec, output_path: str | Path) -> None:
    """Save tool spec to YAML file.

    Args:
        spec: Tool specification
        output_path: Path to save YAML file
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Convert to dict and save as YAML
    spec_dict = spec.model_dump()
    
    with open(output_path, "w") as f:
        yaml.dump(spec_dict, f, default_flow_style=False, sort_keys=False)
