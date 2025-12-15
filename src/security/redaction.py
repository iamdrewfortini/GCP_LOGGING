import re
from typing import Any, Dict, List, Union

class Redactor:
    """Redacts PII and secrets from text and data structures."""

    # Patterns to match
    PATTERNS = {
        "email": r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
        "ipv4": r'\b(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\b',
        "bearer_token": r'(?<=Authorization:\sBearer\s)[a-zA-Z0-9_\-\.]+',
        "api_key": r'(?<=key=)[A-Za-z0-9_\-]+',
    }

    def __init__(self):
        self.compiled_patterns = {
            name: re.compile(pattern)
            for name, pattern in self.PATTERNS.items()
        }

    def scrub_text(self, text: str) -> str:
        """Redact PII from a string."""
        if not text:
            return text
            
        redacted = text
        for name, pattern in self.compiled_patterns.items():
            replacement = f"<{name.upper()}_REDACTED>"
            redacted = pattern.sub(replacement, redacted)
            
        return redacted

    def scrub_data(self, data: Any) -> Any:
        """Recursively redact PII from dicts, lists, and strings."""
        if isinstance(data, str):
            return self.scrub_text(data)
        elif isinstance(data, dict):
            return {k: self.scrub_data(v) for k, v in data.items()}
        elif isinstance(data, list):
            return [self.scrub_data(v) for v in data]
        else:
            return data

redactor = Redactor()
