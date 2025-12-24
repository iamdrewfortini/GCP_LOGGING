import os
import sys
import yaml
import argparse
import logging
from typing import Dict, Any

# Add project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("mcp_generator")

TEMPLATE = """# GENERATED CODE - DO NOT EDIT
# Tool ID: {tool_id}
# Version: {version}

from typing import Optional, Any, Dict
from langchain_core.tools import tool
from langchain_core.pydantic_v1 import BaseModel, Field

# Import the actual implementation
from {service_module} import {service_function}

# Import Governance
from src.security.policy import enforce_policy
from src.agent.audit import log_tool_use

class {class_name}Input(BaseModel):
{input_fields}

@tool("{tool_id}", args_schema={class_name}Input)
def {func_name}({func_args}) -> Any:
    '''{description}'''
    
    inputs = locals()
    
    # 1. Policy Check
    enforce_policy("{tool_id}", inputs)
    
    # 2. Audit Start
    audit_id = log_tool_use("start", "{tool_id}", inputs if {log_inputs} else {{ "redacted": True }})
    
    try:
        # 3. Execution
        result = {service_function}({call_args})
        
        # 4. Audit End
        log_tool_use("end", "{tool_id}", {{ "result_summary": str(result)[:200] }} if {log_outputs} else {{ "redacted": True }}, audit_id=audit_id)
        return result
        
    except Exception as e:
        log_tool_use("error", "{tool_id}", str(e), audit_id=audit_id)
        raise e
"""

def generate_pydantic_fields(inputs: Dict[str, Any]) -> str:
    fields = []
    props = inputs.get("properties", {})
    required = set(inputs.get("required", []))
    
    for name, schema in props.items():
        py_type = "str"
        if schema.get("type") == "integer": py_type = "int"
        elif schema.get("type") == "boolean": py_type = "bool"
        elif schema.get("type") == "number": py_type = "float"
        elif schema.get("type") == "array": py_type = "list"
        
        description = schema.get("description", "")
        default = schema.get("default")
        
        if name in required:
            field_str = f"    {name}: {py_type} = Field(description=\"{description}\")"
        else:
            default_val = f"\"{default}\"" if isinstance(default, str) else default
            if default is None: default_val = "None"
            # Optional fields
            if "Optional" not in py_type and default is None:
                py_type = f"Optional[{py_type}]"
                
            field_str = f"    {name}: {py_type} = Field(default={default_val}, description=\"{description}\")"
        
        fields.append(field_str)
        
    return "\n".join(fields) if fields else "    pass"

def generate_tool(spec_path: str, output_dir: str):
    with open(spec_path, 'r') as f:
        spec = yaml.safe_load(f)
        
    tool_id = spec["id"]
    class_name = "".join(x.title() for x in tool_id.split('_'))
    func_name = tool_id
    
    # Inputs
    input_fields = generate_pydantic_fields(spec["inputs"])
    
    # Func Args
    props = spec["inputs"].get("properties", {})
    func_args_list = []
    call_args_list = []
    
    for name in props.keys():
        # strict typing hints in signature could be complex, simplifying for generated code
        # relying on Pydantic validation wrapper
        func_args_list.append(name)
        call_args_list.append(f"{name}={name}")
        
    func_args = ", ".join(func_args_list)
    call_args = ", ".join(call_args_list)
    
    # Metadata
    execution = spec["execution"]
    audit = spec.get("audit", {})
    
    code = TEMPLATE.format(
        tool_id=tool_id,
        version=spec["version"],
        service_module=execution["service_module"],
        service_function=execution["service_function"],
        class_name=class_name,
        input_fields=input_fields,
        func_name=func_name,
        func_args=func_args,
        call_args=call_args,
        description=spec["description"],
        log_inputs=audit.get("log_inputs", True),
        log_outputs=audit.get("log_outputs", True)
    )
    
    output_path = os.path.join(output_dir, f"{tool_id}.py")
    with open(output_path, 'w') as f:
        f.write(code)
        
    logger.info(f"Generated tool wrapper: {output_path}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate MCP Tool from Spec")
    parser.add_argument("--spec", required=True, help="Path to YAML spec")
    parser.add_argument("--out", default="src/agent/tools/generated", help="Output directory")
    
    args = parser.parse_args()
    generate_tool(args.spec, args.out)
