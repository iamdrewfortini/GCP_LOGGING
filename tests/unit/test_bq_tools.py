import pytest
from unittest.mock import MagicMock, patch
from src.agent.tools.bq import run_bq_query, BQQueryInput
from src.config import config

@patch("src.agent.tools.bq.client")
def test_bq_query_dry_run_limit_exceeded(mock_client):
    # Setup mock for dry run
    mock_job = MagicMock()
    mock_job.total_bytes_processed = config.MAX_BQ_BYTES_ESTIMATE + 1
    mock_client.query.return_value = mock_job
    
    with pytest.raises(ValueError) as excinfo:
        run_bq_query(BQQueryInput(sql="SELECT * FROM large_table"))
    
    assert "Query exceeds byte limit" in str(excinfo.value)

@patch("src.agent.tools.bq.client")
def test_bq_query_success(mock_client):
    # Setup mock for dry run (safe)
    mock_dry_run = MagicMock()
    mock_dry_run.total_bytes_processed = 100
    
    # Setup mock for execution
    mock_exec_job = MagicMock()
    mock_exec_job.job_id = "job_123"
    mock_exec_job.total_bytes_processed = 100
    mock_exec_job.cache_hit = False
    mock_exec_job.result.return_value = [{"col": "val"}]
    
    # We need to handle multiple calls to client.query (dry run then execute)
    mock_client.query.side_effect = [mock_dry_run, mock_exec_job]
    
    res = run_bq_query(BQQueryInput(sql="SELECT * FROM small_table"))
    
    assert res.job_id == "job_123"
    assert res.rows == [{"col": "val"}]
