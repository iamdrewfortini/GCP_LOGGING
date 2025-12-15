from src.agent.persistence import persist_agent_run
from unittest.mock import MagicMock, patch

@patch("src.agent.persistence.client")
def test_mutable_defaults(mock_client):
    # Mock insert_rows_json to avoid actual BQ calls
    mock_client.insert_rows_json.return_value = []
    
    # Call 1: Modify the defaults (simulate side effect if they were mutable)
    # We can't easily "modify" the default from outside, but if we pass nothing, 
    # it uses the default. If the function modifies it, next call sees it.
    # But persist_agent_run doesn't modify its args in place visibly, 
    # except maybe if we passed a list and appended to it?
    # The function constructs a row.
    
    # Wait, the issue with mutable defaults is if the function *modifies* them.
    # The code was:
    # row = { "evidence": [json.dumps(e) for e in evidence], ... }
    # It didn't seem to append to evidence.
    # However, having them as defaults is bad practice anyway.
    
    # To test they are not shared:
    # inspect the function signature? Or just rely on code review.
    # But let's try to pass a list, modify it, and see if it persists? No.
    
    # Correct test:
    # 1. Inspect signature defaults to be None
    import inspect
    sig = inspect.signature(persist_agent_run)
    assert sig.parameters['scope'].default is None
    assert sig.parameters['evidence'].default is None
    
    # 2. Run it and ensure it works with None
    persist_agent_run("run1", "q", "status")
    
    # Check what was passed to insert_rows_json
    args, _ = mock_client.insert_rows_json.call_args
    row = args[1][0]
    assert row["scope"] == "{}"
    assert row["evidence"] == []
