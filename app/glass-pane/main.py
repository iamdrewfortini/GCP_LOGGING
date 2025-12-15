"""
Glass Pane - Organization Logging Viewer
Cloud Run service for viewing logs from the canonical BigQuery view.
"""

from flask import Flask, render_template, jsonify, request
from google.cloud import bigquery
from google.api_core.exceptions import BadRequest, GoogleAPICallError
import logging
import traceback

from config import config
from query_builder import CanonicalQueryBuilder, LogQueryParams

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Initialize BigQuery client (lazy loading)
_bq_client = None


def get_bq_client():
    """Get or create BigQuery client."""
    global _bq_client
    if _bq_client is None:
        _bq_client = bigquery.Client(project=config.project_id)
    return _bq_client


def get_query_builder():
    """Get query builder instance."""
    return CanonicalQueryBuilder(
        project_id=config.project_id,
        view_name=config.canonical_view
    )


@app.after_request
def add_security_headers(response):
    """Add security headers to all responses."""
    csp = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdn.jsdelivr.net; "
        "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
        "img-src 'self' data:; "
        "connect-src 'self' https://cdn.jsdelivr.net; "
        "font-src 'self' https://cdn.jsdelivr.net;"
    )
    response.headers["Content-Security-Policy"] = csp
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    return response


@app.route('/health')
def health():
    """Health check endpoint for Cloud Run."""
    return jsonify({"status": "healthy", "service": "glass-pane"}), 200


@app.route('/favicon.ico')
def favicon():
    """Return empty favicon."""
    return "", 204


@app.route('/')
def index():
    """Main page - display logs from canonical view."""
    try:
        client = get_bq_client()
        builder = get_query_builder()

        # Get query parameters from request
        hours = min(
            int(request.args.get('hours', config.default_time_window_hours)),
            config.max_time_window_hours
        )
        limit = min(
            int(request.args.get('limit', config.default_limit)),
            config.max_limit
        )
        severity = request.args.get('severity')
        service = request.args.get('service')
        search = request.args.get('search')

        # Build query parameters
        params = LogQueryParams(
            limit=limit,
            hours=hours,
            severity=severity,
            service=service,
            search=search
        )

        # Validate parameters
        errors = params.validate(
            max_limit=config.max_limit,
            max_hours=config.max_time_window_hours
        )
        if errors:
            return render_template(
                'index.html',
                error="; ".join(errors),
                rows=[],
                stats={}
            )

        # Build and execute query
        query = builder.build_list_query(params)
        job_config = bigquery.QueryJobConfig(query_parameters=query['params'])
        job = client.query(query['sql'], job_config=job_config)
        rows = [dict(row) for row in job]

        # Get stats for display
        stats_query = builder.build_source_table_stats_query(hours=hours)
        stats_job = client.query(
            stats_query['sql'],
            job_config=bigquery.QueryJobConfig(query_parameters=stats_query['params'])
        )
        source_stats = {row['source_table']: row['count'] for row in stats_job}

        return render_template(
            'index.html',
            rows=rows,
            stats={
                'total_sources': len(source_stats),
                'total_logs': sum(source_stats.values()),
                'hours': hours
            },
            filters={
                'severity': severity,
                'service': service,
                'search': search,
                'hours': hours,
                'limit': limit
            }
        )

    except BadRequest as e:
        logger.error(f"BigQuery BadRequest: {e}")
        return render_template(
            'index.html',
            error=f"Query Error: {e.message}",
            rows=[],
            stats={}
        )
    except GoogleAPICallError as e:
        logger.error(f"BigQuery API Error: {e}")
        return render_template(
            'index.html',
            error=f"BigQuery Error: {str(e)}",
            rows=[],
            stats={}
        )
    except Exception as e:
        logger.error(f"Unexpected error: {traceback.format_exc()}")
        return render_template(
            'index.html',
            error=f"System Error: {str(e)}",
            rows=[],
            stats={}
        )


@app.route('/api/logs')
def api_logs():
    """REST API endpoint for log queries."""
    try:
        client = get_bq_client()
        builder = get_query_builder()

        # Parse parameters
        params = LogQueryParams(
            limit=min(
                int(request.args.get('limit', config.default_limit)),
                config.max_limit
            ),
            hours=min(
                int(request.args.get('hours', config.default_time_window_hours)),
                config.max_time_window_hours
            ),
            severity=request.args.get('severity'),
            service=request.args.get('service'),
            search=request.args.get('search'),
            source_table=request.args.get('source_table')
        )

        # Validate
        errors = params.validate(
            max_limit=config.max_limit,
            max_hours=config.max_time_window_hours
        )
        if errors:
            return jsonify({
                'status': 'error',
                'error_type': 'validation_error',
                'errors': errors
            }), 400

        # Execute query
        query = builder.build_list_query(params)
        job_config = bigquery.QueryJobConfig(query_parameters=query['params'])
        job = client.query(query['sql'], job_config=job_config)
        rows = [dict(row) for row in job]

        # Convert timestamps to ISO format for JSON
        for row in rows:
            if row.get('event_timestamp'):
                row['event_timestamp'] = row['event_timestamp'].isoformat()

        return jsonify({
            'status': 'success',
            'count': len(rows),
            'data': rows
        })

    except BadRequest as e:
        return jsonify({
            'status': 'error',
            'error_type': 'bigquery_error',
            'message': e.message
        }), 400
    except GoogleAPICallError as e:
        return jsonify({
            'status': 'error',
            'error_type': 'bigquery_error',
            'message': str(e)
        }), 500
    except Exception as e:
        logger.error(f"API error: {traceback.format_exc()}")
        return jsonify({
            'status': 'error',
            'error_type': 'internal_error',
            'message': str(e)
        }), 500


@app.route('/api/stats/severity')
def api_stats_severity():
    """Get log counts by severity."""
    try:
        client = get_bq_client()
        builder = get_query_builder()

        hours = min(
            int(request.args.get('hours', config.default_time_window_hours)),
            config.max_time_window_hours
        )

        query = builder.build_count_by_severity_query(hours=hours)
        job_config = bigquery.QueryJobConfig(query_parameters=query['params'])
        job = client.query(query['sql'], job_config=job_config)

        data = {row['severity']: row['count'] for row in job}

        return jsonify({
            'status': 'success',
            'hours': hours,
            'data': data
        })

    except Exception as e:
        logger.error(f"Stats error: {traceback.format_exc()}")
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


@app.route('/api/stats/services')
def api_stats_services():
    """Get log counts by service."""
    try:
        client = get_bq_client()
        builder = get_query_builder()

        hours = min(
            int(request.args.get('hours', config.default_time_window_hours)),
            config.max_time_window_hours
        )

        query = builder.build_count_by_service_query(hours=hours)
        job_config = bigquery.QueryJobConfig(query_parameters=query['params'])
        job = client.query(query['sql'], job_config=job_config)

        data = [
            {
                'service': row['service_name'],
                'count': row['count'],
                'error_count': row['error_count']
            }
            for row in job
        ]

        return jsonify({
            'status': 'success',
            'hours': hours,
            'data': data
        })

    except Exception as e:
        logger.error(f"Stats error: {traceback.format_exc()}")
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


if __name__ == "__main__":
    # Validate configuration at startup
    config_errors = config.validate()
    if config_errors:
        logger.warning(f"Configuration warnings: {config_errors}")

    logger.info(f"Starting Glass Pane on port {config.port}")
    logger.info(f"Project: {config.project_id}")
    logger.info(f"Canonical View: {config.canonical_view}")

    app.run(host='0.0.0.0', port=config.port)
