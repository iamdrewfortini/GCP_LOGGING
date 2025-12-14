from langchain_google_genai import ChatGoogleGenerativeAI
from src.config import config
import os

def get_llm():
    project_id = config.PROJECT_ID_AGENT # Still useful for context/logging
    location = config.VERTEX_REGION # Still useful for context/logging
    model = "gemini-2.5-flash"
    
    print(f"Initializing ChatGoogleGenerativeAI for Vertex AI with: project={project_id}, location={location}, model={model}")
    return ChatGoogleGenerativeAI(
        model=model,
        temperature=0.1,
        streaming=True,
        project=project_id,
        location=location
    )
