from typing import Optional
import os
import logging

try:
    import firebase_admin
    from firebase_admin import auth
except ModuleNotFoundError:  # Optional dependency for some dev/test environments
    firebase_admin = None  # type: ignore
    auth = None  # type: ignore

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

logger = logging.getLogger(__name__)

security = HTTPBearer(auto_error=False)


def _firebase_auth_enabled() -> bool:
    # Default disabled so CI/tests don't require ADC.
    # Also disable if Firebase Admin SDK isn't installed.
    if firebase_admin is None or auth is None:
        return False
    return os.getenv("FIREBASE_ENABLED", "false").lower() == "true"


def _ensure_firebase_app_initialized() -> None:
    """Ensure a default Firebase app exists.

    Firebase Admin uses ADC by default; only call this when FIREBASE_ENABLED=true.
    """
    if firebase_admin is None:
        raise RuntimeError("Firebase Admin SDK not installed")

    try:
        firebase_admin.get_app()
    except ValueError:
        firebase_admin.initialize_app()


def get_current_user_uid(
    creds: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> str:
    """Verify Firebase ID token and return the user's UID.

    If FIREBASE_ENABLED is false (local dev/CI without auth), returns 'anonymous'.
    """
    if not _firebase_auth_enabled():
        return "anonymous"

    if not creds:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = creds.credentials

    try:
        _ensure_firebase_app_initialized()

        decoded_token = auth.verify_id_token(token)
        uid = decoded_token.get("uid")
        if not uid:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token: no uid found",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return uid

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Auth error: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
