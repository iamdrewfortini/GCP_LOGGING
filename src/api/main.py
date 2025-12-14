from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
import json
import asyncio
from src.agent.graph import graph
from langchain_core.messages import HumanMessage, ToolMessage

app = FastAPI()

class ChatRequest(BaseModel):
    message: str
    run_id: Optional[str] = None
    context: Optional[Dict[str, Any]] = {}

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/api/chat")
async def chat(request: ChatRequest):
    inputs = {
        "messages": [HumanMessage(content=request.message)],
        "scope": request.context,
        "phase": "diagnose"
    }
    
    async def event_stream():
        try:
            # We use astream with 'updates' to see node transitions and 'messages' for tokens/chunks
            # But graph.astream(stream_mode='messages') gives full messages or chunks?
            # 'messages' mode usually streams individual message chunks (tokens).
            # 'updates' gives the state update after a node finishes.
            
            # Let's use 'events' (astream_events) for maximum granularity if supported, 
            # or just 'messages' for the LLM tokens.
            # The prompt asks for: "true streaming (progress + tokens + tool events)"
            
            # We will use astream_events for v2 behavior
            async for event in graph.astream_events(inputs, version="v2"):
                kind = event["event"]
                
                payload = {
                    "type": kind,
                    "data": {}
                }
                
                if kind == "on_chat_model_stream":
                    content = event["data"]["chunk"].content
                    if content:
                        payload["data"] = {"content": content}
                        yield f"data: {json.dumps(payload)}\n\n"
                        
                elif kind == "on_tool_start":
                    payload["data"] = {"tool": event["name"], "input": event["data"].get("input")}
                    yield f"data: {json.dumps(payload)}\n\n"
                    
                elif kind == "on_tool_end":
                    output = event["data"].get("output")
                    if isinstance(output, ToolMessage):
                        # Convert ToolMessage to a string for JSON serialization
                        output_data = {
                            "content": output.content,
                            "name": output.name,
                            "tool_call_id": output.tool_call_id
                        }
                    else:
                        output_data = output
                    payload["data"] = {"output": output_data}
                    yield f"data: {json.dumps(payload)}\n\n"
                    
                elif kind == "on_chain_start":
                     # Maybe track node transitions
                     pass

        except Exception as e:
            import traceback
            error_details = {"message": str(e), "traceback": traceback.format_exc()}
            print(f"Error in event_stream: {json.dumps(error_details)}") # Log to Cloud Run logs
            err_payload = {"type": "error", "data": error_details}
            yield f"data: {json.dumps(err_payload)}\n\n"
            
        yield "event: end\ndata: [DONE]\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
