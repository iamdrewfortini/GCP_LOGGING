from typing import List, Optional
from google.cloud import bigquery
from src.glass_pane.config import glass_config

_bq_client: Optional[bigquery.Client] = None

def get_bq_client() -> bigquery.Client:
    """Get or create a BigQuery client singleton."""
    global _bq_client
    if _bq_client is None:
        _bq_client = bigquery.Client(project=glass_config.logs_project_id)
    return _bq_client

def list_datasets(project_id: str = None) -> List[str]:
    """
    Lists datasets in the specified project.
    """
    target_project = project_id or glass_config.logs_project_id
    client = bigquery.Client(project=target_project)
    
    datasets = list(client.list_datasets())
    return [d.dataset_id for d in datasets]
