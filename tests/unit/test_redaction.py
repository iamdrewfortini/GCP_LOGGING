from src.security.redaction import redactor

def test_redact_email():
    text = "Contact me at user@example.com please."
    redacted = redactor.scrub_text(text)
    assert "<EMAIL_REDACTED>" in redacted
    assert "user@example.com" not in redacted

def test_redact_ip():
    text = "Server is at 192.168.1.1 now."
    redacted = redactor.scrub_text(text)
    assert "<IPV4_REDACTED>" in redacted
    assert "192.168.1.1" not in redacted

def test_redact_bearer():
    text = "Authorization: Bearer abc123XYZtoken"
    redacted = redactor.scrub_text(text)
    assert "Authorization: Bearer <BEARER_TOKEN_REDACTED>" in redacted
    assert "abc123XYZtoken" not in redacted

def test_scrub_data_structure():
    data = {
        "user": {"email": "test@test.com"},
        "logs": ["Connection from 10.0.0.1"],
        "safe": "value"
    }
    cleaned = redactor.scrub_data(data)
    assert cleaned["user"]["email"] == "<EMAIL_REDACTED>" 
    # Wait, regex was \b... so it should match full email.
    
    assert "<EMAIL_REDACTED>" in cleaned["user"]["email"]
    assert "test@test.com" not in cleaned["user"]["email"]
    assert "<IPV4_REDACTED>" in cleaned["logs"][0]
    assert cleaned["safe"] == "value"
