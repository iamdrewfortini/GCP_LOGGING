from fastapi.testclient import TestClient
from src.api.main import app
from src.api.auth import get_current_user_uid
import pytest

client = TestClient(app)

def test_public_health_check():
    response = client.get("/health")
    assert response.status_code == 200

def test_sessions_unauthorized():
    # Override dependency to simulate missing auth
    # Actually, if we don't send header, HTTPBearer raises 403 or 401?
    # We set auto_error=False, so it returns None.
    # get_current_user_uid checks if creds is None and raises 401.
    
    # We need to ensure FIREBASE_ENABLED is not "false" for this test, 
    # but the app might have initialized with it.
    # However, get_current_user_uid checks env var at runtime.
    
    import os
    os.environ["FIREBASE_ENABLED"] = "true"
    
    response = client.get("/api/sessions")
    assert response.status_code == 401
    
    response = client.post("/api/sessions", json={"title": "Test"})
    assert response.status_code == 401

def test_sessions_authorized_mock():
    # Mock the auth dependency
    app.dependency_overrides[get_current_user_uid] = lambda: "test-user-123"
    
    # We also need to mock firebase_service because it tries to connect to Firestore
    # unittest.mock.patch might be needed for firebase_service
    from unittest.mock import MagicMock
    from src.api.main import firebase_service
    
    firebase_service.list_sessions = MagicMock(return_value=[])
    firebase_service.create_session = MagicMock(return_value="sess-123")
    
    response = client.get("/api/sessions")
    assert response.status_code == 200
    
    response = client.post("/api/sessions", json={"title": "Test"})
    assert response.status_code == 201
    
    # Clean up
    app.dependency_overrides = {}

def test_cross_user_access_denied():
    app.dependency_overrides[get_current_user_uid] = lambda: "attacker-user"
    
    from unittest.mock import MagicMock
    from src.api.main import firebase_service
    
    # Mock session belonging to victim
    firebase_service.get_session = MagicMock(return_value={"userId": "victim-user", "id": "sess-victim"})
    
    response = client.get("/api/sessions/sess-victim")
    assert response.status_code == 403
    
    # Clean up
    app.dependency_overrides = {}

def test_own_session_access_allowed():
    app.dependency_overrides[get_current_user_uid] = lambda: "victim-user"
    
    from unittest.mock import MagicMock
    from src.api.main import firebase_service
    
    firebase_service.get_session = MagicMock(return_value={"userId": "victim-user", "id": "sess-victim"})
    firebase_service.get_messages = MagicMock(return_value=[])
    
    response = client.get("/api/sessions/sess-victim")
    assert response.status_code == 200
    
    # Clean up
    app.dependency_overrides = {}
