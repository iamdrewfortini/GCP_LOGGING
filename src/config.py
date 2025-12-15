import os


class Config:
    PROJECT_ID_AGENT = os.getenv("PROJECT_ID_AGENT", "your-agent-project")
    PROJECT_ID_LOGS = os.getenv("PROJECT_ID_LOGS", "your-logs-project")
    PROJECT_ID_FINOPS = os.getenv("PROJECT_ID_FINOPS", "your-finops-project")

    # BigQuery location (e.g. US, EU)
    BQ_LOCATION = os.getenv("BQ_LOCATION", "US")

    MAX_BQ_BYTES_ESTIMATE = int(os.getenv("MAX_BQ_BYTES_ESTIMATE", "50000000000"))  # 50GB
    MAX_ROWS_RETURNED = int(os.getenv("MAX_ROWS_RETURNED", "1000"))
    REQUIRE_PARTITION_FILTERS = os.getenv("REQUIRE_PARTITION_FILTERS", "true").lower() == "true"

    AGENT_DATASET = os.getenv("AGENT_DATASET", "org_agent")

    # Accept either:
    # - dataset only: "org_observability" (will be qualified with PROJECT_ID_LOGS)
    # - fully qualified: "my-project.org_observability"
    LOG_ANALYTICS_LINKED_DATASET = os.getenv(
        "LOG_ANALYTICS_LINKED_DATASET", "org_observability.logs_linked"
    )

    VERTEX_REGION = os.getenv("VERTEX_REGION", "us-central1")

    @property
    def log_analytics_linked_dataset_fqn(self) -> str:
        """Returns the fully qualified dataset name for the linked log analytics dataset."""
        ds = self.LOG_ANALYTICS_LINKED_DATASET
        if "." in ds:
            return ds
        return f"{self.PROJECT_ID_LOGS}.{ds}"


config = Config()
