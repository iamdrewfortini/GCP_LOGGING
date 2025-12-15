import logging
from typing import Dict, Any

logger = logging.getLogger("security_policy")

def enforce_policy(tool_id: str, inputs: Dict[str, Any]):
    """
    Validates tool inputs against security policies defined in the tool spec.
    Raises ValueError if policy is violated.
    """
    # In a full implementation, this would load the 'policy' section from the YAML spec
    # associated with 'tool_id'. For now, we'll implement a basic check logic.
    
    logger.info(f"Enforcing policy for {tool_id}")
    
    # Example hardcoded checks (should be dynamic)
    if tool_id == "bq_list_datasets":
        # Check permissions?
        pass
        
    if tool_id == "bq_query_readonly":
        sql = inputs.get("sql", "").upper()
        forbidden = ["DROP", "DELETE", "INSERT", "UPDATE", "ALTER", "TRUNCATE"]
        for word in forbidden:
            if word in sql:
                raise ValueError(f"Security Policy Violation: Forbidden SQL keyword '{word}'")

    # Pass by default if no specific violations found
    return True
