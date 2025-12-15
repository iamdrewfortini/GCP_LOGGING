"""
Ollama chat service with tool calling for log queries.

Streaming chat, tool dispatcher, deterministic planner prompt.

Based on spec: ollama_integration.chat.
"""

import os
import json
import time
import logging
from typing import List, Dict, Any, Optional, Generator
import httpx
from src.services.ollama_embed import OllamaEmbedService
from src.services.qdrant_query_engine import QdrantQueryEngine
from src.services.firebase_service import FirebaseService

logger = logging.getLogger(__name__)

# Config
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_CHAT_MODEL = os.getenv("OLLAMA_CHAT_MODEL", "qwen2.5:7b")  # Use available model
EMBED_DIM = int(os.getenv("EMBED_DIM", "1024"))

# Tool definitions for Ollama
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_logs",
            "description": "Search logs semantically or with filters. Use for natural language queries about logs.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query_text": {"type": "string", "description": "Natural language query to embed and search"},
                    "limit": {"type": "integer", "default": 10, "description": "Number of results"},
                    "tenant_id": {"type": "string", "description": "Filter by tenant"},
                    "service_name": {"type": "string", "description": "Filter by service"},
                    "severity": {"type": "string", "description": "Filter by severity (ERROR, WARNING, etc.)"},
                    "timestamp_from": {"type": "integer", "description": "Unix timestamp from"},
                    "timestamp_to": {"type": "integer", "description": "Unix timestamp to"},
                },
                "required": ["query_text"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_logs_grouped",
            "description": "Search logs grouped by a field (e.g., one per trace).",
            "parameters": {
                "type": "object",
                "properties": {
                    "query_text": {"type": "string", "description": "Natural language query"},
                    "group_by": {"type": "string", "default": "trace_id", "description": "Field to group by"},
                    "limit": {"type": "integer", "default": 5, "description": "Number of groups"},
                },
                "required": ["query_text"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_log_by_id",
            "description": "Get a specific log by its log_id.",
            "parameters": {
                "type": "object",
                "properties": {
                    "log_id": {"type": "string", "description": "The log_id to retrieve"},
                },
                "required": ["log_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "benchmark_query",
            "description": "Run a benchmark on a query to measure latency and quality.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query_text": {"type": "string", "description": "Query to benchmark"},
                    "scenario": {"type": "string", "default": "semantic", "description": "Benchmark scenario"},
                },
                "required": ["query_text"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "suggest_indexes",
            "description": "Suggest new payload indexes based on query patterns.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query_patterns": {"type": "array", "items": {"type": "string"}, "description": "List of common query filters"},
                },
                "required": ["query_patterns"]
            }
        }
    }
]

PLANNER_PROMPT = """
You are a log search assistant. Turn user intent into a structured query plan.

Output ONLY valid JSON with this structure:
{
  "intent": "brief description",
  "query_type": "semantic|filtered|grouped|exact",
  "tools": [
    {
      "tool": "search_logs",
      "params": {...}
    }
  ]
}

Do not include extra text.
"""


class OllamaChatService:
    """Streaming chat with tool calling."""

    def __init__(self):
        self.base_url = OLLAMA_BASE_URL.rstrip("/")
        self.chat_url = f"{self.base_url}/api/chat"
        self.model = OLLAMA_CHAT_MODEL
        self.embed_service = OllamaEmbedService()
        self.query_engine = QdrantQueryEngine()
        self.firebase = FirebaseService()
        self.tools = TOOLS

    def chat_with_tools(
        self,
        messages: List[Dict[str, Any]],
        stream: bool = True
    ) -> Generator[Dict[str, Any], None, None]:
        """
        Chat with tool calling. Yields streaming responses.
        """
        payload = {
            "model": self.model,
            "messages": messages,
            "tools": self.tools,
            "stream": stream
        }

        with httpx.Client(timeout=300.0) as client:
            with client.stream("POST", self.chat_url, json=payload) as response:
                response.raise_for_status()
                tool_calls = []
                for line in response.iter_lines():
                    if line:
                        data = json.loads(line)
                        yield data

                        if "tool_calls" in data.get("message", {}):
                            tool_calls.extend(data["message"]["tool_calls"])

                # Execute tools if any
                if tool_calls:
                    for call in tool_calls:
                        start_time = time.time()
                        result = self._execute_tool(call["function"])
                        elapsed = time.time() - start_time
                        logger.info(f"Tool {call['function']['name']} executed in {elapsed:.3f}s")
                        # TODO: Log to bench tables

                        # Push to Firebase for realtime
                        query_id = f"query_{call['id']}"
                        self.firebase.push_query_result(query_id, result)

                        # Add tool result to messages
                        messages.append({
                            "role": "tool",
                            "content": json.dumps(result),
                            "tool_call_id": call["id"]
                        })

                    # Continue chat with tool results
                    yield from self.chat_with_tools(messages, stream)

    def _execute_tool(self, function: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a tool call."""
        name = function["name"]
        args = function.get("arguments", {})

        if name == "search_logs":
            return self._tool_search_logs(**args)
        elif name == "search_logs_grouped":
            return self._tool_search_logs_grouped(**args)
        elif name == "get_log_by_id":
            return self._tool_get_log_by_id(**args)
        elif name == "benchmark_query":
            return self._tool_benchmark_query(**args)
        elif name == "suggest_indexes":
            return self._tool_suggest_indexes(**args)
        else:
            return {"error": f"Unknown tool {name}"}

    def _tool_search_logs(
        self,
        query_text: str,
        limit: int = 10,
        **filters
    ) -> Dict[str, Any]:
        """Search logs."""
        # Embed query
        query_vector = self.embed_service.embed_single(query_text)

        # Build filter
        query_filter = QdrantQueryEngine.build_filter(**filters)

        # Query
        if query_filter:
            response = self.query_engine.filtered_search(
                query_vector=query_vector,
                query_filter=query_filter,
                limit=limit
            )
        else:
            response = self.query_engine.semantic_search(
                query_vector=query_vector,
                limit=limit
            )

        return {
            "results": [
                {
                    "id": point.id,
                    "score": point.score,
                    "payload": point.payload
                }
                for point in response.points
            ]
        }

    def _tool_search_logs_grouped(
        self,
        query_text: str,
        group_by: str = "trace_id",
        limit: int = 5
    ) -> Dict[str, Any]:
        """Grouped search."""
        query_vector = self.embed_service.embed_single(query_text)

        response = self.query_engine.query_groups(
            query_vector=query_vector,
            group_by=group_by,
            limit=limit
        )

        return {
            "groups": [
                {
                    "group_value": group.id,
                    "hits": [
                        {
                            "id": hit.id,
                            "score": hit.score,
                            "payload": hit.payload
                        }
                        for hit in group.hits
                    ]
                }
                for group in response.groups
            ]
        }

    def _tool_get_log_by_id(self, log_id: str) -> Dict[str, Any]:
        """Get log by ID."""
        # Use filter on log_id
        query_filter = QdrantQueryEngine.build_filter(log_id=log_id)
        response = self.query_engine.query_points(
            query_filter=query_filter,
            limit=1
        )
        if response.points:
            return {"log": response.points[0].payload}
        return {"error": "Log not found"}

    def _tool_benchmark_query(self, query_text: str, scenario: str = "semantic") -> Dict[str, Any]:
        """Benchmark query (placeholder)."""
        # TODO: Integrate with bench harness
        return {"benchmark": f"Scenario {scenario} for '{query_text}' - latency: TBD"}

    def _tool_suggest_indexes(self, query_patterns: List[str]) -> Dict[str, Any]:
        """Suggest indexes (placeholder)."""
        # TODO: Analyze patterns
        return {"suggestions": ["Add index for 'new_field'" for _ in query_patterns]}