"""
GraphQL Auth using Firebase ID tokens
"""

from typing import Optional
from strawberry.fastapi import BaseContext
from src.api.auth import get_current_user_uid

def get_user_from_context(context: BaseContext) -> Optional[str]:
    """Extract user ID from Authorization header in GraphQL context."""
    request = context.request
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        return None
    token = auth_header[7:]  # Remove "Bearer "
    try:
        return get_current_user_uid(token)
    except Exception:
        return None

def require_auth(user_id: Optional[str]) -> str:
    """Require authentication, raise error if not."""
    if not user_id:
        raise ValueError("Authentication required")
    return user_id