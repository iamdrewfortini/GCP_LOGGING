from typing import Optional
import os
import logging
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from firebase_admin import auth

logger = logging.getLogger(__name__)

security = HTTPBearer(auto_error=False)

def get_current_user_uid(creds: Optional[HTTPAuthorizationCredentials] = Depends(security)) -> str:
    """
    Verifies the Firebase ID token and returns the user's UID.
    If FIREBASE_ENABLED is false (local dev without auth), returns 'anonymous'.
    """
    if os.getenv("FIREBASE_ENABLED", "true").lower() != "true":
        return "anonymous"

    if not creds:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = creds.credentials
    try:
        decoded_token = auth.verify_id_token(token)
        uid = decoded_token.get("uid")
        if not uid:
             raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token: no uid found",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return uid
    except Exception as e:
        logger.error(f"Auth error: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
