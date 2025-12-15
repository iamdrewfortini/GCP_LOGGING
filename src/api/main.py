from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, Query, Request, Response, Depends
from fastapi.responses import JSONResponse, StreamingResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from google.api_core.exceptions import BadRequest, GoogleAPICallError
from google.cloud import bigquery
from langchain_core.messages import HumanMessage, ToolMessage
from pydantic import BaseModel, Field

from src.agent.graph import graph
from src.glass_pane.config import glass_config
from src.glass_pane.query_builder import CanonicalQueryBuilder, LogQueryParams
from src.services.firebase_service import firebase_service
from src.services.redis_service import redis_service
from src.services.qdrant_service import qdrant_service
from src.services.dual_write_service import dual_write_service, ChatEvent, ToolInvocation
from src.api.auth import get_current_user_uid
from src.api.etl_routes import router as etl_router
from strawberry.fastapi import GraphQLRouter
from src.api.graphql.schema import schema
from src.api.graphql.context import get_context

app = FastAPI(
    title="Glass Pane API",
    description="Centralized logging API for GCP Organization logs",
    version="2.0.0",
)

# Startup Event
@app.on_event("startup")
async def startup_event():
    # Ensure Qdrant collections exist
    try:
        qdrant_service.ensure_collections()
        print("Qdrant collections verified.")
    except Exception as e:
        print(f"Warning: Qdrant init failed: {e}")

# CORS configuration for frontend
allowed_origins_str = os.getenv("ALLOWED_ORIGINS", "http://localhost:5173,http://localhost:3000")
allowed_origins = [origin.strip() for origin in allowed_origins_str.split(",") if origin.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include ETL routes
app.include_router(etl_router)

# Include GraphQL routes
app.include_router(GraphQLRouter(schema, context_getter=get_context), prefix="/graphql", tags=["graphql"])

_bq_client: Optional[bigquery.Client] = None


def get_bq_client() -> bigquery.Client:
    global _bq_client
    if _bq_client is None:
        _bq_client = bigquery.Client(project=glass_config.logs_project_id)
    return _bq_client


def get_query_builder() -> CanonicalQueryBuilder:
    return CanonicalQueryBuilder(
        project_id=glass_config.logs_project_id,
        view_name=glass_config.canonical_view,
    )


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    """Add security headers to all API responses."""
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    return response


class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None
    # user_id is now handled via auth token, but keeping optional for backward compat/transition if needed
    context: Dict[str, Any] = Field(default_factory=dict)


class SessionRequest(BaseModel):
    # user_id is now inferred from token
    title: str = "New Session"


class SaveQueryRequest(BaseModel):
    # user_id is now inferred from token
    name: str
    query_params: Dict[str, Any]


@app.get("/health")
def health():
    """Health check endpoint for load balancers and monitoring."""
    redis_status = redis_service.ping()
    # Basic check if Qdrant client is initialized
    qdrant_status = qdrant_service.client is not None
    
    return {
        "status": "ok",
        "services": {
            "redis": "connected" if redis_status else "disconnected",
            "qdrant": "connected" if qdrant_status else "disconnected"
        }
    }


@app.get("/api")
def api_root():
    """API root - returns API info and available endpoints."""
    return {
        "name": "Glass Pane API",
        "version": "2.0.0",
        "description": "Centralized logging API for GCP Organization logs",
        "docs_url": "/docs",
        "endpoints": {
            "health": "/health",
            "logs": "/api/logs",
            "logs_v2": "/api/v2/logs (supports envelope=true for Universal Envelope)",
            "stats": {
                "severity": "/api/stats/severity",
                "services": "/api/stats/services",
            },
            "sessions": "/api/sessions",
            "chat": "/api/chat",
            "saved_queries": "/api/saved-queries",
        },
    }


@app.get("/favicon.ico")
def favicon():
    """Return empty favicon response."""
    return Response(status_code=204)


@app.get("/api/logs")
def api_logs(
    hours: int = Query(default=glass_config.default_time_window_hours, ge=1),
    limit: int = Query(default=glass_config.default_limit, ge=1),
    severity: Optional[str] = Query(default=None),
    service: Optional[str] = Query(default=None),
    search: Optional[str] = Query(default=None),
    source_table: Optional[str] = Query(default=None),
):
    try:
        client = get_bq_client()
        builder = get_query_builder()

        safe_hours = min(hours, glass_config.max_time_window_hours)
        safe_limit = min(limit, glass_config.max_limit)

        params = LogQueryParams(
            limit=safe_limit,
            hours=safe_hours,
            severity=severity or None,
            service=service or None,
            search=search or None,
            source_table=source_table or None,
        )

        errors = params.validate(
            max_limit=glass_config.max_limit,
            max_hours=glass_config.max_time_window_hours,
        )
        if errors:
            return JSONResponse(
                {
                    "status": "error",
                    "error_type": "validation_error",
                    "errors": errors,
                },
                status_code=400,
            )

        query = builder.build_list_query(params)
        job_config = bigquery.QueryJobConfig(query_parameters=query["params"])
        job = client.query(query["sql"], job_config=job_config)
        rows = [dict(row) for row in job]

        for row in rows:
            if row.get("event_timestamp"):
                row["event_timestamp"] = row["event_timestamp"].isoformat()

        return JSONResponse({"status": "success", "count": len(rows), "data": rows})

    except BadRequest as e:
        return JSONResponse(
            {"status": "error", "error_type": "bigquery_error", "message": e.message},
            status_code=400,
        )
    except GoogleAPICallError as e:
        return JSONResponse(
            {"status": "error", "error_type": "bigquery_error", "message": str(e)},
            status_code=500,
        )
    except Exception as e:
        return JSONResponse(
            {"status": "error", "error_type": "internal_error", "message": str(e)},
            status_code=500,
        )


@app.get("/api/v2/logs")
def api_logs_v2(
    hours: int = Query(default=glass_config.default_time_window_hours, ge=1),
    limit: int = Query(default=glass_config.default_limit, ge=1),
    severity: Optional[str] = Query(default=None),
    service: Optional[str] = Query(default=None),
    search: Optional[str] = Query(default=None),
    source_table: Optional[str] = Query(default=None),
    envelope: bool = Query(default=False, description="Include Universal Data Envelope fields"),
):
    """
    Get logs with optional Universal Data Envelope support.

    When envelope=true, queries the canonical view and includes
    envelope fields like environment, PII risk, and correlation IDs.
    """
    try:
        client = get_bq_client()
        builder = get_query_builder()

        safe_hours = min(hours, glass_config.max_time_window_hours)
        safe_limit = min(limit, glass_config.max_limit)

        params = LogQueryParams(
            limit=safe_limit,
            hours=safe_hours,
            severity=severity or None,
            service=service or None,
            search=search or None,
            source_table=source_table or None,
        )

        errors = params.validate(
            max_limit=glass_config.max_limit,
            max_hours=glass_config.max_time_window_hours,
        )
        if errors:
            return JSONResponse(
                {
                    "status": "error",
                    "error_type": "validation_error",
                    "errors": errors,
                },
                status_code=400,
            )

        # Use envelope parameter to include Universal Envelope fields
        query = builder.build_list_query(params, use_envelope=envelope)
        job_config = bigquery.QueryJobConfig(query_parameters=query["params"])
        job = client.query(query["sql"], job_config=job_config)
        rows = [dict(row) for row in job]

        for row in rows:
            if row.get("event_timestamp"):
                row["event_timestamp"] = row["event_timestamp"].isoformat()
            if row.get("envelope_event_ts"):
                row["envelope_event_ts"] = row["envelope_event_ts"].isoformat()

        return JSONResponse({
            "status": "success",
            "count": len(rows),
            "envelope_enabled": envelope,
            "data": rows
        })

    except BadRequest as e:
        return JSONResponse(
            {"status": "error", "error_type": "bigquery_error", "message": e.message},
            status_code=400,
        )
    except GoogleAPICallError as e:
        return JSONResponse(
            {"status": "error", "error_type": "bigquery_error", "message": str(e)},
            status_code=500,
        )
    except Exception as e:
        return JSONResponse(
            {"status": "error", "error_type": "internal_error", "message": str(e)},
            status_code=500,
        )


@app.get("/api/stats/severity")
def api_stats_severity(
    hours: int = Query(default=glass_config.default_time_window_hours, ge=1),
):
    try:
        client = get_bq_client()
        builder = get_query_builder()

        safe_hours = min(hours, glass_config.max_time_window_hours)

        query = builder.build_count_by_severity_query(hours=safe_hours)
        job = client.query(
            query["sql"],
            job_config=bigquery.QueryJobConfig(query_parameters=query["params"]),
        )

        data = {row["severity"]: row["count"] for row in job}

        return JSONResponse({"status": "success", "hours": safe_hours, "data": data})

    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)


@app.get("/api/stats/services")
def api_stats_services(
    hours: int = Query(default=glass_config.default_time_window_hours, ge=1),
):
    try:
        client = get_bq_client()
        builder = get_query_builder()

        safe_hours = min(hours, glass_config.max_time_window_hours)

        query = builder.build_count_by_service_query(hours=safe_hours)
        job = client.query(
            query["sql"],
            job_config=bigquery.QueryJobConfig(query_parameters=query["params"]),
        )

        data = [
            {
                "service": row["service_name"],
                "count": row["count"],
                "error_count": row["error_count"],
            }
            for row in job
        ]

        return JSONResponse({"status": "success", "hours": safe_hours, "data": data})

    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)


# ============================================
# SESSION MANAGEMENT ENDPOINTS
# ============================================


@app.post("/api/sessions")
def create_session(
    request: SessionRequest,
    current_user_uid: str = Depends(get_current_user_uid),
):
    """Create a new chat session."""
    try:
        session_id = firebase_service.create_session(
            user_id=current_user_uid,
            title=request.title,
        )
        return JSONResponse(
            {"status": "success", "session_id": session_id},
            status_code=201,
        )
    except Exception as e:
        return JSONResponse(
            {"status": "error", "message": str(e)},
            status_code=500,
        )


@app.get("/api/sessions")
def list_sessions(
    current_user_uid: str = Depends(get_current_user_uid),
    status: str = Query(default="active"),
    limit: int = Query(default=50, ge=1, le=100),
):
    """List user's chat sessions."""
    try:
        sessions = firebase_service.list_sessions(
            user_id=current_user_uid,
            status=status,
            limit=limit,
        )
        return JSONResponse({"status": "success", "sessions": sessions})
    except Exception as e:
        return JSONResponse(
            {"status": "error", "message": str(e)},
            status_code=500,
        )


@app.get("/api/sessions/{session_id}")
def get_session(
    session_id: str,
    current_user_uid: str = Depends(get_current_user_uid),
):
    """Get a specific session with its messages."""
    try:
        session = firebase_service.get_session(session_id)
        if not session:
            return JSONResponse(
                {"status": "error", "message": "Session not found"},
                status_code=404,
            )
        
        # Enforce ownership
        if session.get("userId") != current_user_uid and current_user_uid != "anonymous":
            return JSONResponse(
                 {"status": "error", "message": "Access denied"},
                 status_code=403,
            )

        messages = firebase_service.get_messages(session_id)
        return JSONResponse(
            {"status": "success", "session": session, "messages": messages}
        )
    except Exception as e:
        return JSONResponse(
            {"status": "error", "message": str(e)},
            status_code=500,
        )


@app.post("/api/sessions/{session_id}/archive")
def archive_session(
    session_id: str,
    current_user_uid: str = Depends(get_current_user_uid),
):
    """Archive a session."""
    try:
        # Check ownership first
        session = firebase_service.get_session(session_id)
        if not session:
             return JSONResponse(
                {"status": "error", "message": "Session not found"},
                status_code=404,
            )
        
        if session.get("userId") != current_user_uid and current_user_uid != "anonymous":
             return JSONResponse(
                 {"status": "error", "message": "Access denied"},
                 status_code=403,
            )

        firebase_service.archive_session(session_id)
        return JSONResponse({"status": "success"})
    except Exception as e:
        return JSONResponse(
            {"status": "error", "message": str(e)},
            status_code=500,
        )


# ============================================
# SAVED QUERIES ENDPOINTS
# ============================================


@app.post("/api/saved-queries")
def save_query(
    request: SaveQueryRequest,
    current_user_uid: str = Depends(get_current_user_uid),
):
    """Save a reusable log query."""
    try:
        query_id = firebase_service.save_query(
            user_id=current_user_uid,
            name=request.name,
            query_params=request.query_params,
        )
        return JSONResponse(
            {"status": "success", "query_id": query_id},
            status_code=201,
        )
    except Exception as e:
        return JSONResponse(
            {"status": "error", "message": str(e)},
            status_code=500,
        )


@app.get("/api/saved-queries")
def list_saved_queries(
    current_user_uid: str = Depends(get_current_user_uid),
    limit: int = Query(default=50, ge=1, le=100),
):
    """List user's saved queries."""
    try:
        queries = firebase_service.list_saved_queries(user_id=current_user_uid, limit=limit)
        return JSONResponse({"status": "success", "queries": queries})
    except Exception as e:
        return JSONResponse(
            {"status": "error", "message": str(e)},
            status_code=500,
        )


# ============================================
# AI CHAT ENDPOINT
# ============================================


import uuid
import logging
from datetime import datetime, timezone
from src.security.redaction import redactor
from src.agent.nodes import get_token_manager, reset_token_manager, update_token_budget
from src.agent.state import AgentState

logger = logging.getLogger(__name__)


def create_token_count_event(
    phase: str,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    total_tokens: int = 0,
    remaining: int = 100_000,
    budget_max: int = 100_000,
) -> dict:
    """Create a token_count SSE event payload.

    Args:
        phase: Current phase (ingress, retrieval, model_stream, tool, finalize)
        prompt_tokens: Input/prompt token count
        completion_tokens: Output/completion token count
        total_tokens: Total token count
        remaining: Remaining budget
        budget_max: Maximum budget

    Returns:
        Token count event payload
    """
    return {
        "type": "token_count",
        "data": {
            "prompt": prompt_tokens,
            "completion": completion_tokens,
            "total": total_tokens,
            "remaining": remaining,
            "budget_max": budget_max,
            "ts": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "phase": phase,
        },
    }

@app.post("/api/chat")
async def chat(
    request: ChatRequest,
    current_user_uid: str = Depends(get_current_user_uid),
):
    # Verify session ownership/existence if provided
    session_id = request.session_id
    if session_id and firebase_service.enabled:
        session = firebase_service.get_session(session_id)
        if not session:
            # If client claims a session that doesn't exist, strictly we should error or create new.
            # For simplicity and security, let's error.
             return JSONResponse(
                {"status": "error", "message": "Session not found"},
                status_code=404,
            )
        if session.get("userId") != current_user_uid and current_user_uid != "anonymous":
             return JSONResponse(
                 {"status": "error", "message": "Access denied"},
                 status_code=403,
            )

    # Create new session if needed
    if not session_id and firebase_service.enabled:
        session_id = firebase_service.create_session(
            user_id=current_user_uid,
            title=request.message[:50] + "..." if len(request.message) > 50 else request.message,
        )

    # Persist user message using dual-write service (hot + cold paths)
    if session_id:
        user_event = ChatEvent.create_message_event(
            session_id=session_id,
            user_id=current_user_uid,
            role="user",
            content=request.message,
        )
        dual_write_service.write_event(user_event, firebase_service=firebase_service)

        # Enqueue for async embedding and Qdrant storage
        redis_service.enqueue(
            "q:embeddings:realtime",
            {
                "session_id": session_id,
                "project_id": current_user_uid,
                "role": "user",
                "content": request.message,
            },
        )

    inputs = {
        "messages": [HumanMessage(content=request.message)],
        "scope": request.context,
        "phase": "diagnose",
    }

    async def event_stream():
        full_response = ""
        tools_used: List[str] = []
        completion_tokens = 0
        active_tool_invocation: Optional[ToolInvocation] = None

        # Reset and get token manager for this request
        reset_token_manager()
        token_manager = get_token_manager()

        # Track initial user message tokens (ingress phase)
        user_msg_tokens = token_manager.count_tokens(request.message) + 4  # +4 for message overhead
        token_manager.reserve_tokens(user_msg_tokens)

        try:
            # Send session info first
            if session_id:
                session_payload = {"type": "session", "data": {"session_id": session_id}}
                yield f"data: {json.dumps(session_payload)}\n\n"

            # Emit initial token_count event (ingress phase)
            status = token_manager.get_budget_status()
            ingress_event = create_token_count_event(
                phase="ingress",
                prompt_tokens=status["tokens_used"],
                completion_tokens=0,
                total_tokens=status["tokens_used"],
                remaining=status["tokens_remaining"],
                budget_max=status["max_tokens"],
            )
            yield f"data: {json.dumps(ingress_event)}\n\n"

            async for event in graph.astream_events(inputs, version="v2"):
                kind = event["event"]

                payload = {"type": kind, "data": {}}

                if kind == "on_chat_model_stream":
                    chunk_content = event["data"]["chunk"].content
                    if chunk_content:
                        # Handle both string and list content (Gemini can return list of content blocks)
                        if isinstance(chunk_content, list):
                            # Extract text from content blocks
                            text_parts = []
                            for part in chunk_content:
                                if isinstance(part, str):
                                    text_parts.append(part)
                                elif isinstance(part, dict) and "text" in part:
                                    text_parts.append(part["text"])
                                elif hasattr(part, "text"):
                                    text_parts.append(part.text)
                            content = "".join(text_parts)
                        else:
                            content = chunk_content

                        if content:
                            full_response += content

                            # Track completion tokens (approximate by counting chunk tokens)
                            chunk_tokens = token_manager.count_tokens(content)
                            completion_tokens += chunk_tokens

                            payload["data"] = {"content": content}
                            yield f"data: {json.dumps(payload)}\n\n"

                            # Emit token_count event periodically during streaming (every ~50 tokens)
                            if completion_tokens % 50 < chunk_tokens:
                                status = token_manager.get_budget_status()
                                stream_event = create_token_count_event(
                                    phase="model_stream",
                                    prompt_tokens=status["tokens_used"],
                                    completion_tokens=completion_tokens,
                                    total_tokens=status["tokens_used"] + completion_tokens,
                                    remaining=status["tokens_remaining"] - completion_tokens,
                                    budget_max=status["max_tokens"],
                                )
                                yield f"data: {json.dumps(stream_event)}\n\n"

                elif kind == "on_tool_start":
                    tool_name = event["name"]
                    tools_used.append(tool_name)
                    # Redact tool input
                    tool_input = event["data"].get("input", {})
                    safe_input = redactor.scrub_data(tool_input)
                    payload["data"] = {
                        "tool": tool_name,
                        "input": safe_input,
                    }
                    yield f"data: {json.dumps(payload)}\n\n"

                    # Start tool invocation tracking for dual-write
                    if session_id:
                        active_tool_invocation = ToolInvocation.start(
                            session_id=session_id,
                            user_id=current_user_uid,
                            tool_name=tool_name,
                            input_args=safe_input if isinstance(safe_input, dict) else {"raw": str(safe_input)},
                        )

                    # Emit token_count event for tool start
                    status = token_manager.get_budget_status()
                    tool_start_event = create_token_count_event(
                        phase="tool",
                        prompt_tokens=status["tokens_used"],
                        completion_tokens=completion_tokens,
                        total_tokens=status["tokens_used"] + completion_tokens,
                        remaining=status["tokens_remaining"] - completion_tokens,
                        budget_max=status["max_tokens"],
                    )
                    yield f"data: {json.dumps(tool_start_event)}\n\n"

                elif kind == "on_tool_end":
                    output = event["data"].get("output")
                    output_summary = None
                    if isinstance(output, ToolMessage):
                        output_data = {
                            "content": output.content,
                            "name": output.name,
                            "tool_call_id": output.tool_call_id,
                        }
                        output_summary = str(output.content)[:200] if output.content else None
                        # Track tool output tokens
                        tool_output_tokens = token_manager.count_tokens(str(output.content))
                        try:
                            token_manager.reserve_tokens(tool_output_tokens)
                        except Exception:
                            pass  # Don't fail on token budget exceeded during tool output
                    else:
                        output_data = output
                        output_summary = str(output)[:200] if output else None
                        # Track tool output tokens
                        tool_output_tokens = token_manager.count_tokens(str(output))
                        try:
                            token_manager.reserve_tokens(tool_output_tokens)
                        except Exception:
                            pass

                    # Complete tool invocation and write to dual-write
                    if active_tool_invocation:
                        active_tool_invocation.complete(
                            output_summary=output_summary,
                            tokens_used=tool_output_tokens,
                        )
                        dual_write_service.write_tool_invocation(active_tool_invocation)
                        active_tool_invocation = None

                    # Redact tool output
                    safe_output = redactor.scrub_data(output_data)
                    payload["data"] = {"output": safe_output}
                    yield f"data: {json.dumps(payload)}\n\n"

                    # Emit token_count event after tool completion
                    status = token_manager.get_budget_status()
                    tool_end_event = create_token_count_event(
                        phase="tool",
                        prompt_tokens=status["tokens_used"],
                        completion_tokens=completion_tokens,
                        total_tokens=status["tokens_used"] + completion_tokens,
                        remaining=status["tokens_remaining"] - completion_tokens,
                        budget_max=status["max_tokens"],
                    )
                    yield f"data: {json.dumps(tool_end_event)}\n\n"

            # Reserve completion tokens in the manager
            try:
                token_manager.reserve_tokens(completion_tokens)
            except Exception:
                pass  # Don't fail on budget exceeded at finalize

            # Get final token budget status
            final_status = token_manager.get_budget_status()

            # Emit final token_count event (finalize phase)
            finalize_event = create_token_count_event(
                phase="finalize",
                prompt_tokens=final_status["tokens_used"] - completion_tokens,
                completion_tokens=completion_tokens,
                total_tokens=final_status["tokens_used"],
                remaining=final_status["tokens_remaining"],
                budget_max=final_status["max_tokens"],
            )
            yield f"data: {json.dumps(finalize_event)}\n\n"

            # Persist assistant response using dual-write service (hot + cold paths)
            if session_id and full_response:
                assistant_event = ChatEvent.create_message_event(
                    session_id=session_id,
                    user_id=current_user_uid,
                    role="assistant",
                    content=full_response,
                    metadata={
                        "tools_used": tools_used,
                        "word_count": len(full_response.split()),
                    },
                    token_usage={
                        "prompt_tokens": final_status["tokens_used"] - completion_tokens,
                        "completion_tokens": completion_tokens,
                        "total_tokens": final_status["tokens_used"],
                    },
                )
                dual_write_service.write_event(assistant_event, firebase_service=firebase_service)

                # Enqueue for async embedding and Qdrant storage
                redis_service.enqueue(
                    "q:embeddings:realtime",
                    {
                        "session_id": session_id,
                        "project_id": current_user_uid,
                        "role": "assistant",
                        "content": full_response,
                    },
                )

        except Exception as e:
            import traceback
            error_id = str(uuid.uuid4())
            # Log full details server-side
            logger.error(f"Error in event_stream (ref: {error_id}): {e}\n{traceback.format_exc()}")

            # Return safe error to client
            error_details = {
                "message": "An internal error occurred processing your request.",
                "reference_id": error_id
            }
            err_payload = {"type": "error", "data": error_details}
            yield f"data: {json.dumps(err_payload)}\n\n"

        finally:
            # Clean up token manager
            reset_token_manager()

        yield "event: end\ndata: [DONE]\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


# Mount static files for frontend (must be after all routes)
frontend_dist = Path(__file__).parent.parent.parent / "frontend" / "dist"
if frontend_dist.exists():
    # Mount static assets
    app.mount("/assets", StaticFiles(directory=str(frontend_dist / "assets")), name="assets")
    
    # SPA fallback - serve index.html for all non-API routes
    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str):
        """Serve frontend SPA or fallback to index.html for client-side routing."""
        # Don't interfere with API routes
        if full_path.startswith(("api/", "health", "docs", "openapi.json", "redoc")):
            return Response(status_code=404)
        
        # Try to serve the requested file
        file_path = frontend_dist / full_path
        if file_path.is_file():
            return FileResponse(file_path)
        
        # Fallback to index.html for SPA routing
        index_path = frontend_dist / "index.html"
        if index_path.exists():
            return FileResponse(index_path)
        
        return Response(status_code=404)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=glass_config.port)
