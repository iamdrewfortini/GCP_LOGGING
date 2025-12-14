import os

print(f"Environment variables at config load: {dict(os.environ)}")

class Config:
    PROJECT_ID_AGENT = os.getenv("PROJECT_ID_AGENT", "your-agent-project")
    PROJECT_ID_LOGS = os.getenv("PROJECT_ID_LOGS", "your-logs-project")
    PROJECT_ID_FINOPS = os.getenv("PROJECT_ID_FINOPS", "your-finops-project")
    BQ_LOCATION = os.getenv("BQ_LOCATION", "US")
    MAX_BQ_BYTES_ESTIMATE = int(os.getenv("MAX_BQ_BYTES_ESTIMATE", "50000000000"))  # 50GB
    MAX_ROWS_RETURNED = int(os.getenv("MAX_ROWS_RETURNED", "1000"))
    REQUIRE_PARTITION_FILTERS = os.getenv("REQUIRE_PARTITION_FILTERS", "true").lower() == "true"
    AGENT_DATASET = os.getenv("AGENT_DATASET", "org_agent")
    LOG_ANALYTICS_LINKED_DATASET = os.getenv("LOG_ANALYTICS_LINKED_DATASET", "org_observability.logs_linked")
    VERTEX_REGION = os.getenv("VERTEX_REGION", "us-central1")
    
config = Config()
