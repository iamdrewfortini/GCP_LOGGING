from typing import List
from google.cloud import bigquery
from src.glass_pane.config import glass_config

def list_datasets(project_id: str = None) -> List[str]:
    """
    Lists datasets in the specified project.
    """
    target_project = project_id or glass_config.logs_project_id
    client = bigquery.Client(project=target_project)
    
    datasets = list(client.list_datasets())
    return [d.dataset_id for d in datasets]
