# Code Refactor Tasks

## Overview

This document details the required code changes to refactor the Glass Pane service to use the canonical view.

## File Changes

### 1. main.py - Complete Refactor

**File:** `/home/daclab-ai/GCP_LOGGING/app/glass-pane/main.py`

#### Current Issues
- Dynamic schema discovery on every request (lines 62-177)
- Hardcoded column assumptions (lines 99-130)
- No use of existing canonical view
- Raw BigQuery errors exposed to users

#### Target Architecture

```python
# New simplified structure
from flask import Flask, render_template, jsonify, request
from google.cloud import bigquery
from google.api_core.exceptions import BadRequest, GoogleAPICallError
import os
import json

app = Flask(__name__)

# Configuration
PROJECT_ID = os.environ.get("PROJECT_ID", "diatonic-ai-gcp")
CANONICAL_VIEW = os.environ.get("CANONICAL_VIEW", "org_observability.logs_canonical_v2")
DEFAULT_LIMIT = int(os.environ.get("DEFAULT_LIMIT", "100"))
MAX_LIMIT = int(os.environ.get("MAX_LIMIT", "1000"))
DEFAULT_TIME_WINDOW_HOURS = int(os.environ.get("DEFAULT_TIME_WINDOW_HOURS", "24"))

# Initialize BigQuery client once
bq_client = None

def get_bq_client():
    global bq_client
    if bq_client is None:
        bq_client = bigquery.Client(project=PROJECT_ID)
    return bq_client

@app.route('/api/logs')
def api_logs():
    """API endpoint for log queries."""
    try:
        client = get_bq_client()

        # Parse parameters
        limit = min(int(request.args.get('limit', DEFAULT_LIMIT)), MAX_LIMIT)
        hours = int(request.args.get('hours', DEFAULT_TIME_WINDOW_HOURS))
        severity = request.args.get('severity', None)
        service = request.args.get('service', None)
        search = request.args.get('search', None)

        # Build parameterized query
        query = build_log_query(
            view=CANONICAL_VIEW,
            limit=limit,
            hours=hours,
            severity=severity,
            service=service,
            search=search
        )

        # Execute query
        job = client.query(query['sql'], job_config=bigquery.QueryJobConfig(
            query_parameters=query['params']
        ))

        rows = [dict(row) for row in job]

        return jsonify({
            'status': 'success',
            'count': len(rows),
            'data': rows
        })

    except GoogleAPICallError as e:
        return jsonify({
            'status': 'error',
            'error_type': 'bigquery_error',
            'message': str(e)
        }), 500
    except Exception as e:
        return jsonify({
            'status': 'error',
            'error_type': 'internal_error',
            'message': str(e)
        }), 500

def build_log_query(view, limit, hours, severity=None, service=None, search=None):
    """Build parameterized query with filters."""
    params = []
    where_clauses = [
        "event_timestamp >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL @hours HOUR)"
    ]

    params.append(bigquery.ScalarQueryParameter("hours", "INT64", hours))

    if severity:
        where_clauses.append("severity = @severity")
        params.append(bigquery.ScalarQueryParameter("severity", "STRING", severity.upper()))

    if service:
        where_clauses.append("service_name LIKE @service")
        params.append(bigquery.ScalarQueryParameter("service", "STRING", f"%{service}%"))

    if search:
        where_clauses.append("(display_message LIKE @search OR json_payload LIKE @search)")
        params.append(bigquery.ScalarQueryParameter("search", "STRING", f"%{search}%"))

    params.append(bigquery.ScalarQueryParameter("limit", "INT64", limit))

    sql = f"""
        SELECT
            insert_id,
            event_timestamp,
            severity,
            service_name,
            log_name,
            display_message,
            source_table,
            trace_id,
            span_id
        FROM `{PROJECT_ID}.{view}`
        WHERE {' AND '.join(where_clauses)}
        ORDER BY event_timestamp DESC
        LIMIT @limit
    """

    return {'sql': sql, 'params': params}
```

### 2. New File: query_builder.py

**File:** `/home/daclab-ai/GCP_LOGGING/app/glass-pane/query_builder.py`

```python
"""
Query builder module for canonical log queries.
Provides type-safe, parameterized query construction.
"""

from dataclasses import dataclass
from typing import Optional, List
from google.cloud import bigquery
from enum import Enum

class Severity(Enum):
    DEFAULT = "DEFAULT"
    DEBUG = "DEBUG"
    INFO = "INFO"
    NOTICE = "NOTICE"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"
    ALERT = "ALERT"
    EMERGENCY = "EMERGENCY"

@dataclass
class LogQueryParams:
    """Parameters for log query."""
    limit: int = 100
    hours: int = 24
    severity: Optional[str] = None
    service: Optional[str] = None
    search: Optional[str] = None
    trace_id: Optional[str] = None

    def validate(self):
        if self.limit < 1 or self.limit > 1000:
            raise ValueError("Limit must be between 1 and 1000")
        if self.hours < 1 or self.hours > 720:  # Max 30 days
            raise ValueError("Hours must be between 1 and 720")
        if self.severity and self.severity.upper() not in [s.value for s in Severity]:
            raise ValueError(f"Invalid severity: {self.severity}")

class CanonicalQueryBuilder:
    """Builder for canonical log view queries."""

    CANONICAL_FIELDS = [
        'insert_id', 'event_timestamp', 'severity', 'log_name',
        'service_name', 'display_message', 'source_table',
        'trace_id', 'span_id', 'resource_type', 'resource_labels',
        'text_payload', 'json_payload', 'proto_payload',
        'source_dataset', 'ingestion_method'
    ]

    def __init__(self, project_id: str, view_name: str):
        self.project_id = project_id
        self.view_name = view_name

    def build_list_query(self, params: LogQueryParams) -> dict:
        """Build query for listing logs."""
        params.validate()

        bq_params = []
        where_clauses = []

        # Time window filter (required)
        where_clauses.append(
            "event_timestamp >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL @hours HOUR)"
        )
        bq_params.append(bigquery.ScalarQueryParameter("hours", "INT64", params.hours))

        # Optional filters
        if params.severity:
            where_clauses.append("severity = @severity")
            bq_params.append(bigquery.ScalarQueryParameter(
                "severity", "STRING", params.severity.upper()
            ))

        if params.service:
            where_clauses.append("service_name LIKE @service")
            bq_params.append(bigquery.ScalarQueryParameter(
                "service", "STRING", f"%{params.service}%"
            ))

        if params.search:
            where_clauses.append(
                "(display_message LIKE @search OR json_payload LIKE @search)"
            )
            bq_params.append(bigquery.ScalarQueryParameter(
                "search", "STRING", f"%{params.search}%"
            ))

        if params.trace_id:
            where_clauses.append("trace_id = @trace_id")
            bq_params.append(bigquery.ScalarQueryParameter(
                "trace_id", "STRING", params.trace_id
            ))

        bq_params.append(bigquery.ScalarQueryParameter("limit", "INT64", params.limit))

        sql = f"""
            SELECT
                insert_id,
                event_timestamp,
                severity,
                service_name,
                log_name,
                display_message,
                source_table,
                trace_id,
                span_id
            FROM `{self.project_id}.{self.view_name}`
            WHERE {' AND '.join(where_clauses)}
            ORDER BY event_timestamp DESC
            LIMIT @limit
        """

        return {'sql': sql, 'params': bq_params}

    def build_aggregate_query(self, params: LogQueryParams, group_by: str) -> dict:
        """Build query for aggregation."""
        params.validate()

        if group_by not in ['severity', 'service_name', 'source_table', 'resource_type']:
            raise ValueError(f"Invalid group_by field: {group_by}")

        bq_params = [
            bigquery.ScalarQueryParameter("hours", "INT64", params.hours)
        ]

        sql = f"""
            SELECT
                {group_by},
                COUNT(*) as count
            FROM `{self.project_id}.{self.view_name}`
            WHERE event_timestamp >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL @hours HOUR)
            GROUP BY {group_by}
            ORDER BY count DESC
        """

        return {'sql': sql, 'params': bq_params}
```

### 3. New File: config.py

**File:** `/home/daclab-ai/GCP_LOGGING/app/glass-pane/config.py`

```python
"""
Configuration module for Glass Pane service.
"""

import os
from dataclasses import dataclass, field
from typing import List

@dataclass
class Config:
    """Application configuration."""

    # GCP Settings
    project_id: str = field(default_factory=lambda: os.environ.get("PROJECT_ID", "diatonic-ai-gcp"))

    # BigQuery Settings
    canonical_view: str = field(default_factory=lambda: os.environ.get("CANONICAL_VIEW", "org_observability.logs_canonical_v2"))
    bq_location: str = field(default_factory=lambda: os.environ.get("BQ_LOCATION", "US"))

    # Query Limits
    default_limit: int = field(default_factory=lambda: int(os.environ.get("DEFAULT_LIMIT", "100")))
    max_limit: int = field(default_factory=lambda: int(os.environ.get("MAX_LIMIT", "1000")))
    default_time_window_hours: int = field(default_factory=lambda: int(os.environ.get("DEFAULT_TIME_WINDOW_HOURS", "24")))
    max_time_window_hours: int = field(default_factory=lambda: int(os.environ.get("MAX_TIME_WINDOW_HOURS", "720")))

    # Feature Flags
    enable_trace_lookup: bool = field(default_factory=lambda: os.environ.get("ENABLE_TRACE_LOOKUP", "true").lower() == "true")
    enable_search: bool = field(default_factory=lambda: os.environ.get("ENABLE_SEARCH", "true").lower() == "true")

    def validate(self) -> List[str]:
        """Validate configuration and return list of errors."""
        errors = []

        if not self.project_id:
            errors.append("PROJECT_ID is required")

        if self.default_limit > self.max_limit:
            errors.append("DEFAULT_LIMIT cannot exceed MAX_LIMIT")

        if self.default_time_window_hours > self.max_time_window_hours:
            errors.append("DEFAULT_TIME_WINDOW_HOURS cannot exceed MAX_TIME_WINDOW_HOURS")

        return errors

# Global config instance
config = Config()
```

### 4. Update: templates/index.html

**File:** `/home/daclab-ai/GCP_LOGGING/app/glass-pane/templates/index.html`

Changes needed:
- Update column references to match canonical schema
- Add filter controls (severity, service, time window)
- Add search functionality
- Improve error display

### 5. New File: tests/test_query_builder.py

**File:** `/home/daclab-ai/GCP_LOGGING/app/glass-pane/tests/test_query_builder.py`

```python
"""
Unit tests for query builder module.
"""

import pytest
from query_builder import CanonicalQueryBuilder, LogQueryParams

class TestLogQueryParams:
    def test_valid_params(self):
        params = LogQueryParams(limit=50, hours=12)
        params.validate()  # Should not raise

    def test_invalid_limit(self):
        params = LogQueryParams(limit=2000)
        with pytest.raises(ValueError):
            params.validate()

    def test_invalid_severity(self):
        params = LogQueryParams(severity="INVALID")
        with pytest.raises(ValueError):
            params.validate()

class TestCanonicalQueryBuilder:
    def setup_method(self):
        self.builder = CanonicalQueryBuilder(
            project_id="test-project",
            view_name="org_observability.logs_canonical_v2"
        )

    def test_basic_query(self):
        params = LogQueryParams(limit=10, hours=1)
        result = self.builder.build_list_query(params)

        assert 'sql' in result
        assert 'params' in result
        assert 'LIMIT @limit' in result['sql']
        assert len(result['params']) == 2  # hours + limit

    def test_query_with_filters(self):
        params = LogQueryParams(
            limit=10,
            hours=1,
            severity="ERROR",
            service="glass-pane"
        )
        result = self.builder.build_list_query(params)

        assert 'severity = @severity' in result['sql']
        assert 'service_name LIKE @service' in result['sql']
        assert len(result['params']) == 4  # hours + severity + service + limit
```

## Implementation Steps

### Step 1: Create New Modules
1. Create `config.py`
2. Create `query_builder.py`
3. Create `tests/` directory

### Step 2: Refactor main.py
1. Replace dynamic discovery with canonical view query
2. Add parameterized query support
3. Add structured error responses
4. Add API endpoints (/api/logs, /api/logs/aggregate)

### Step 3: Update Templates
1. Update column names in index.html
2. Add filter controls
3. Add error handling display

### Step 4: Add Tests
1. Add unit tests for query builder
2. Add integration tests with dry-run
3. Add end-to-end tests

### Step 5: Update Dependencies
```
# requirements.txt additions
pytest==7.4.0
pytest-cov==4.1.0
```

### Step 6: Deployment
1. Deploy canonical view v2 to BigQuery
2. Update Cloud Run environment variables
3. Deploy updated service
4. Verify functionality
