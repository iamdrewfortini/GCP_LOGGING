from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, Query, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from google.api_core.exceptions import BadRequest, GoogleAPICallError
from google.cloud import bigquery
from langchain_core.messages import HumanMessage, ToolMessage
from pydantic import BaseModel, Field

from src.agent.graph import graph
from src.glass_pane.config import glass_config
from src.glass_pane.query_builder import CanonicalQueryBuilder, LogQueryParams
from src.services.firebase_service import firebase_service

app = FastAPI()

# Mount static files
STATIC_DIR = Path(__file__).resolve().parents[1] / "glass_pane" / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "glass_pane" / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

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
    response = await call_next(request)

    csp = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdn.jsdelivr.net https://www.gstatic.com; "
        "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
        "img-src 'self' data:; "
        "connect-src 'self' https://cdn.jsdelivr.net https://firestore.googleapis.com https://*.firebaseio.com; "
        "font-src 'self' https://cdn.jsdelivr.net;"
    )

    response.headers["Content-Security-Policy"] = csp
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"

    return response


class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None
    user_id: str = "anonymous"
    context: Dict[str, Any] = Field(default_factory=dict)


class SessionRequest(BaseModel):
    user_id: str
    title: str = "New Session"


class SaveQueryRequest(BaseModel):
    user_id: str
    name: str
    query_params: Dict[str, Any]


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/debug/paths")
def debug_paths():
    """Debug endpoint to check file paths."""
    import os
    static_dir = Path(__file__).resolve().parents[1] / "glass_pane" / "static"
    css_file = static_dir / "css" / "design-system.css"
    return {
        "cwd": os.getcwd(),
        "__file__": str(Path(__file__).resolve()),
        "static_dir": str(static_dir),
        "static_exists": static_dir.exists(),
        "css_file": str(css_file),
        "css_exists": css_file.exists(),
        "static_contents": os.listdir(static_dir) if static_dir.exists() else [],
    }


@app.get("/favicon.ico")
def favicon():
    return Response(status_code=204)


@app.get("/", response_class=HTMLResponse)
def index(
    request: Request,
    hours: int = Query(default=glass_config.default_time_window_hours, ge=1),
    limit: int = Query(default=glass_config.default_limit, ge=1),
    severity: Optional[str] = Query(default=None),
    service: Optional[str] = Query(default=None),
    search: Optional[str] = Query(default=None),
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
        )

        errors = params.validate(
            max_limit=glass_config.max_limit,
            max_hours=glass_config.max_time_window_hours,
        )

        filters = {
            "severity": params.severity,
            "service": params.service,
            "search": params.search,
            "hours": safe_hours,
            "limit": safe_limit,
        }

        if errors:
            return templates.TemplateResponse(
                "index.html",
                {
                    "request": request,
                    "error": "; ".join(errors),
                    "rows": [],
                    "stats": {},
                    "filters": filters,
                },
                status_code=400,
            )

        query = builder.build_list_query(params)
        job_config = bigquery.QueryJobConfig(query_parameters=query["params"])
        job = client.query(query["sql"], job_config=job_config)
        rows = [dict(row) for row in job]

        # Convert datetime objects to ISO strings for JSON serialization
        for row in rows:
            if row.get("event_timestamp"):
                row["event_timestamp"] = row["event_timestamp"].isoformat()

        stats_query = builder.build_source_table_stats_query(hours=safe_hours)
        stats_job = client.query(
            stats_query["sql"],
            job_config=bigquery.QueryJobConfig(query_parameters=stats_query["params"]),
        )
        source_stats = {row["source_table"]: row["count"] for row in stats_job}

        return templates.TemplateResponse(
            "index.html",
            {
                "request": request,
                "rows": rows,
                "stats": {
                    "total_sources": len(source_stats),
                    "total_logs": sum(source_stats.values()),
                    "hours": safe_hours,
                },
                "filters": filters,
            },
        )

    except BadRequest as e:
        return templates.TemplateResponse(
            "index.html",
            {"request": request, "error": f"Query Error: {e.message}", "rows": [], "stats": {}, "filters": {}},
            status_code=400,
        )
    except GoogleAPICallError as e:
        return templates.TemplateResponse(
            "index.html",
            {"request": request, "error": f"BigQuery Error: {str(e)}", "rows": [], "stats": {}, "filters": {}},
            status_code=500,
        )
    except Exception as e:
        return templates.TemplateResponse(
            "index.html",
            {"request": request, "error": f"System Error: {str(e)}", "rows": [], "stats": {}, "filters": {}},
            status_code=500,
        )


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
def create_session(request: SessionRequest):
    """Create a new chat session."""
    try:
        session_id = firebase_service.create_session(
            user_id=request.user_id,
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
    user_id: str = Query(...),
    status: str = Query(default="active"),
    limit: int = Query(default=50, ge=1, le=100),
):
    """List user's chat sessions."""
    try:
        sessions = firebase_service.list_sessions(
            user_id=user_id,
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
def get_session(session_id: str):
    """Get a specific session with its messages."""
    try:
        session = firebase_service.get_session(session_id)
        if not session:
            return JSONResponse(
                {"status": "error", "message": "Session not found"},
                status_code=404,
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
def archive_session(session_id: str):
    """Archive a session."""
    try:
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
def save_query(request: SaveQueryRequest):
    """Save a reusable log query."""
    try:
        query_id = firebase_service.save_query(
            user_id=request.user_id,
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
    user_id: str = Query(...),
    limit: int = Query(default=50, ge=1, le=100),
):
    """List user's saved queries."""
    try:
        queries = firebase_service.list_saved_queries(user_id=user_id, limit=limit)
        return JSONResponse({"status": "success", "queries": queries})
    except Exception as e:
        return JSONResponse(
            {"status": "error", "message": str(e)},
            status_code=500,
        )


# ============================================
# AI CHAT ENDPOINT
# ============================================


@app.post("/api/chat")
async def chat(request: ChatRequest):
    # Create or use existing session
    session_id = request.session_id
    if not session_id and firebase_service.enabled:
        session_id = firebase_service.create_session(
            user_id=request.user_id,
            title=request.message[:50] + "..." if len(request.message) > 50 else request.message,
        )

    # Persist user message
    if session_id and firebase_service.enabled:
        firebase_service.add_message(
            session_id=session_id,
            role="user",
            content=request.message,
        )

    inputs = {
        "messages": [HumanMessage(content=request.message)],
        "scope": request.context,
        "phase": "diagnose",
    }

    async def event_stream():
        full_response = ""
        tools_used: List[str] = []

        try:
            # Send session info first
            if session_id:
                session_payload = {"type": "session", "data": {"session_id": session_id}}
                yield f"data: {json.dumps(session_payload)}\n\n"

            async for event in graph.astream_events(inputs, version="v2"):
                kind = event["event"]

                payload = {"type": kind, "data": {}}

                if kind == "on_chat_model_stream":
                    content = event["data"]["chunk"].content
                    if content:
                        full_response += content
                        payload["data"] = {"content": content}
                        yield f"data: {json.dumps(payload)}\n\n"

                elif kind == "on_tool_start":
                    tool_name = event["name"]
                    tools_used.append(tool_name)
                    payload["data"] = {
                        "tool": tool_name,
                        "input": event["data"].get("input"),
                    }
                    yield f"data: {json.dumps(payload)}\n\n"

                elif kind == "on_tool_end":
                    output = event["data"].get("output")
                    if isinstance(output, ToolMessage):
                        output_data = {
                            "content": output.content,
                            "name": output.name,
                            "tool_call_id": output.tool_call_id,
                        }
                    else:
                        output_data = output
                    payload["data"] = {"output": output_data}
                    yield f"data: {json.dumps(payload)}\n\n"

            # Persist assistant response
            if session_id and firebase_service.enabled and full_response:
                firebase_service.add_message(
                    session_id=session_id,
                    role="assistant",
                    content=full_response,
                    metadata={
                        "tools_used": tools_used,
                        "word_count": len(full_response.split()),
                    },
                )

        except Exception as e:
            import traceback

            error_details = {"message": str(e), "traceback": traceback.format_exc()}
            print(f"Error in event_stream: {json.dumps(error_details)}")
            err_payload = {"type": "error", "data": error_details}
            yield f"data: {json.dumps(err_payload)}\n\n"

        yield "event: end\ndata: [DONE]\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=glass_config.port)
