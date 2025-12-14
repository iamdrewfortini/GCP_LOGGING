import os
import datetime
from flask import Flask, render_template, request, jsonify
from google.cloud import bigquery
from services.query_builder import QueryBuilder
from services.agent_service import agent_service

print("STARTING APP...", flush=True)
app = Flask(__name__)

import json
import time
from flask import Response, stream_with_context

# Config
PROJECT_ID = os.environ.get("PROJECT_ID", "diatonic-ai-gcp")
DATASET_ID = os.environ.get("DATASET_ID", "central_logging_v1")
VERTEX_ENABLED = os.environ.get("VERTEX_ENABLED", "false").lower() == "true"

# Initialize BigQuery Client
try:
    client = bigquery.Client(project=PROJECT_ID)
except Exception as e:
    client = None
    print(f"Failed to initialize BigQuery client: {e}")

@app.route('/api/tail')
def tail_logs():
    if not client:
        return Response("data: {\"error\": \"BigQuery client not initialized\"}\n\n", mimetype="text/event-stream")

    start_timestamp = request.args.get('from', (datetime.datetime.utcnow() - datetime.timedelta(minutes=5)).isoformat() + "Z")

    def generate_logs(last_timestamp):
        start_time = datetime.datetime.utcnow()
        max_duration = datetime.timedelta(minutes=4)  # Cloud Run timeout is 5 min, stop at 4

        while True:
            # Check if we've been running too long
            elapsed = datetime.datetime.utcnow() - start_time
            if elapsed > max_duration:
                yield f"data: {{\"info\": \"Tailing session ended after {int(elapsed.total_seconds())} seconds. Refresh to continue.\"}}\n\n"
                break

            now = datetime.datetime.utcnow()
            current_time = now.isoformat() + "Z"

            sql = f"""
                SELECT *
                FROM `{PROJECT_ID}.{DATASET_ID}.view_canonical_logs`
                WHERE event_ts > @last_timestamp
                ORDER BY event_ts ASC
                LIMIT 10
            """
            params = [
                bigquery.ScalarQueryParameter("last_timestamp", "TIMESTAMP", last_timestamp)
            ]

            try:
                job = client.query(sql, job_config=bigquery.QueryJobConfig(query_parameters=params))
                rows = [dict(row) for row in job]

                if rows:
                    for r in rows:
                        if 'event_ts' in r and r['event_ts'] and not isinstance(r['event_ts'], str):
                            r['event_ts'] = r['event_ts'].isoformat()
                        yield f"data: {json.dumps(r)}\n\n"
                        # Update last_timestamp to ensure we only get newer logs next time
                        if r['event_ts'] > last_timestamp:
                            last_timestamp = r['event_ts']
                else:
                    # Send keepalive comment to prevent timeout
                    yield f": keepalive at {current_time}\n\n"

            except Exception as e:
                error_data = {"error": str(e)}
                yield f"data: {json.dumps(error_data)}\n\n"
                print(f"BigQuery Error in tail_logs: {e}")

            time.sleep(5) # Poll every 5 seconds

    return Response(generate_logs(start_timestamp), mimetype="text/event-stream")

@app.route('/api/facets')
def get_facets():
    if not client:
        return jsonify({"error": "BigQuery client not initialized"}), 500

    try:
        now = datetime.datetime.utcnow()
        default_start = (now - datetime.timedelta(hours=1)).isoformat() + "Z"
        default_end = now.isoformat() + "Z"

        start_time = request.args.get('from', default_start)
        end_time = request.args.get('to', default_end)

        # Query for severities
        severity_sql = f"""
            SELECT severity, COUNT(*) as count
            FROM `{PROJECT_ID}.{DATASET_ID}.view_canonical_logs`
            WHERE event_ts BETWEEN @start_time AND @end_time
            GROUP BY severity
            ORDER BY count DESC
        """
        severity_params = [
            bigquery.ScalarQueryParameter("start_time", "TIMESTAMP", start_time),
            bigquery.ScalarQueryParameter("end_time", "TIMESTAMP", end_time)
        ]
        severity_job = client.query(severity_sql, job_config=bigquery.QueryJobConfig(query_parameters=severity_params))
        severities = {row['severity']: row['count'] for row in severity_job}

        # Query for services
        service_sql = f"""
            SELECT service, COUNT(*) as count
            FROM `{PROJECT_ID}.{DATASET_ID}.view_canonical_logs`
            WHERE event_ts BETWEEN @start_time AND @end_time
            GROUP BY service
            ORDER BY count DESC
            LIMIT 10 # Limit to top 10 services for brevity
        """
        service_job = client.query(service_sql, job_config=bigquery.QueryJobConfig(query_parameters=severity_params))
        services = {row['service']: row['count'] for row in service_job}

        # Query for source tables
        source_table_sql = f"""
            SELECT source_table, COUNT(*) as count
            FROM `{PROJECT_ID}.{DATASET_ID}.view_canonical_logs`
            WHERE event_ts BETWEEN @start_time AND @end_time
            GROUP BY source_table
            ORDER BY count DESC
        """
        source_table_job = client.query(source_table_sql, job_config=bigquery.QueryJobConfig(query_parameters=severity_params))
        source_tables = {row['source_table']: row['count'] for row in source_table_job}

        return jsonify({
            "severities": severities,
            "services": services,
            "source_tables": source_tables
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/logs/<string:insert_id>')
def get_single_log(insert_id: str):
    if not client:
        return jsonify({"error": "BigQuery client not initialized"}), 500

    try:
        # Fetch log by insertId (unique identifier)
        sql = f"""
            SELECT *
            FROM `{PROJECT_ID}.{DATASET_ID}.view_canonical_logs`
            WHERE insertId = @insert_id
            LIMIT 1
        """
        params = [
            bigquery.ScalarQueryParameter("insert_id", "STRING", insert_id),
        ]
        job = client.query(sql, job_config=bigquery.QueryJobConfig(query_parameters=params))
        rows = [dict(row) for row in job]

        if not rows:
            return jsonify({"error": "Log not found"}), 404

        log_entry = rows[0]
        if 'event_ts' in log_entry and log_entry['event_ts'] and not isinstance(log_entry['event_ts'], str):
            log_entry['event_ts'] = log_entry['event_ts'].isoformat()

        return jsonify({"data": log_entry})

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/chat', methods=['POST'])
def chat_agent():
    try:
        data = request.json
        query = data.get('query', '')
        if not query:
            return jsonify({"error": "Query required"}), 400
            
        if not VERTEX_ENABLED:
             return jsonify({"response": "Vertex AI is currently disabled."})

        def generate():
            try:
                for chunk in agent_service.run_stream(query):
                    yield json.dumps({"chunk": chunk}) + "\n"
            except Exception as e:
                yield json.dumps({"error": str(e)}) + "\n"

        return Response(stream_with_context(generate()), mimetype='application/x-ndjson')
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.after_request
def add_security_headers(response):
    csp = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdn.jsdelivr.net; "
        "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
        "img-src 'self' data:; "
        "connect-src 'self' https://cdn.jsdelivr.net; "
        "font-src 'self' https://cdn.jsdelivr.net; " 
    )
    response.headers["Content-Security-Policy"] = csp
    return response

@app.route('/health')
def health():
    return jsonify({"status": "ok", "project": PROJECT_ID})

@app.route('/')
def index():
    # Serve the Single Page App (SPA) shell
    return render_template('index.html')

@app.route('/api/logs')
def get_logs():
    if not client:
        return jsonify({"error": "BigQuery client not initialized"}), 500

    try:
        # Defaults
        now = datetime.datetime.utcnow()
        default_start = (now - datetime.timedelta(hours=1)).isoformat() + "Z"
        default_end = now.isoformat() + "Z"

        start_time = request.args.get('from', default_start)
        end_time = request.args.get('to', default_end)
        severity = request.args.get('severity')
        service = request.args.get('service')
        limit = int(request.args.get('limit', 50))
        offset = int(request.args.get('cursor', 0))

        sql, params = QueryBuilder.get_canonical_sql(
            start_time=start_time, 
            end_time=end_time, 
            severity=severity, 
            service=service, 
            limit=limit, 
            offset=offset
        )

        job = client.query(sql, job_config=bigquery.QueryJobConfig(query_parameters=params))
        rows = [dict(row) for row in job]
        
        # Serialize datetime objects
        for r in rows:
            if 'event_ts' in r and r['event_ts'] and not isinstance(r['event_ts'], str):
                r['event_ts'] = r['event_ts'].isoformat()

        return jsonify({"data": rows, "meta": {"count": len(rows)}})

    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))
