from google.cloud import bigquery
from google.api_core.exceptions import GoogleAPICallError
from typing import List, Dict, Any, Optional
from src.config import config
from src.agent.tools.contracts import BQDryRunInput, BQDryRunOutput, BQQueryInput, BQQueryOutput

_client = None

def get_client():
    global _client
    if _client is None:
        _client = bigquery.Client(project=config.PROJECT_ID_AGENT, location=config.BQ_LOCATION)
    return _client

# For backwards compatibility with existing code
def __getattr__(name):
    if name == 'client':
        return get_client()
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")

def run_bq_dry_run(inp: BQDryRunInput) -> BQDryRunOutput:
    job_config = bigquery.QueryJobConfig(dry_run=True, use_query_cache=False)
    if inp.params:
        query_params = []
        for k, v in inp.params.items():
            if isinstance(v, int):
                query_params.append(bigquery.ScalarQueryParameter(k, "INT64", v))
            elif isinstance(v, bool):
                query_params.append(bigquery.ScalarQueryParameter(k, "BOOL", v))
            elif isinstance(v, float):
                query_params.append(bigquery.ScalarQueryParameter(k, "FLOAT64", v))
            else:
                query_params.append(bigquery.ScalarQueryParameter(k, "STRING", str(v)))
        job_config.query_parameters = query_params

    try:
        query_job = get_client().query(inp.sql, job_config=job_config)
        return BQDryRunOutput(
            bytes_estimate=query_job.total_bytes_processed,
            referenced_tables=[str(t) for t in query_job.referenced_tables] if query_job.referenced_tables else []
        )
    except Exception as e:
        # In a real tool, we might want to return the error in a structured way
        raise e

def run_bq_query(inp: BQQueryInput) -> BQQueryOutput:
    # 1. Dry Run First (Safety Gate)
    dry_run_out = run_bq_dry_run(BQDryRunInput(sql=inp.sql, params=inp.params))
    
    if dry_run_out.bytes_estimate > config.MAX_BQ_BYTES_ESTIMATE:
        raise ValueError(f"Query exceeds byte limit: {dry_run_out.bytes_estimate} > {config.MAX_BQ_BYTES_ESTIMATE}")

    # 2. Execute
    job_config = bigquery.QueryJobConfig()
    if inp.params:
        query_params = []
        for k, v in inp.params.items():
            if isinstance(v, int):
                query_params.append(bigquery.ScalarQueryParameter(k, "INT64", v))
            elif isinstance(v, bool):
                query_params.append(bigquery.ScalarQueryParameter(k, "BOOL", v))
            elif isinstance(v, float):
                query_params.append(bigquery.ScalarQueryParameter(k, "FLOAT64", v))
            else:
                query_params.append(bigquery.ScalarQueryParameter(k, "STRING", str(v)))
        job_config.query_parameters = query_params
    
    query_job = get_client().query(inp.sql, job_config=job_config)
    
    # Wait for result
    rows = query_job.result(max_results=inp.max_rows)
    
    row_data = [dict(row) for row in rows]
    
    return BQQueryOutput(
        job_id=query_job.job_id,
        rows=row_data,
        total_bytes_processed=query_job.total_bytes_processed or 0,
        cache_hit=query_job.cache_hit or False
    )
