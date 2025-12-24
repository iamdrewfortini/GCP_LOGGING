from __future__ import annotations

from src.config import config


def get_llm():
    """Construct the chat model.

    This is intentionally a lazy import so that modules/tests that don't need
    LLM execution can still import the codebase without Vertex/GenAI deps.
    """

    try:
        from langchain_google_genai import ChatGoogleGenerativeAI
    except ModuleNotFoundError as e:
        raise RuntimeError(
            "Missing optional dependency 'langchain_google_genai'. "
            "Install backend deps to enable /api/chat."
        ) from e

    project_id = config.PROJECT_ID_AGENT  # Still useful for context/logging
    location = config.VERTEX_REGION  # Still useful for context/logging
    model = "gemini-2.5-flash"

    print(
        f"Initializing ChatGoogleGenerativeAI for Vertex AI with: "
        f"project={project_id}, location={location}, model={model}"
    )

    return ChatGoogleGenerativeAI(
        model=model,
        temperature=0.1,
        streaming=True,
        project=project_id,
        location=location,
    )
