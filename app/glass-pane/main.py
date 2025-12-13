from flask import Flask, render_template, send_from_directory, make_response
from google.cloud import bigquery
from google.api_core.exceptions import BadRequest
import os

app = Flask(__name__)

# Config
PROJECT_ID = os.environ.get("PROJECT_ID", "diatonic-ai-gcp")
DATASET_ID = os.environ.get("DATASET_ID", "central_logging_v1")

@app.after_request
def add_security_headers(response):
    # Basic CSP: Allow self, unsafe-inline for styles, unsafe-eval for scripts (to fix reported issue)
    # Also explicitly allow cdn.jsdelivr.net for Bootstrap assets.
    csp = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdn.jsdelivr.net; "
        "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
        "img-src 'self' data:; "
        "connect-src 'self' https://cdn.jsdelivr.net; " # Allow source maps from CDN
        "font-src 'self' https://cdn.jsdelivr.net;" 
    )
    response.headers["Content-Security-Policy"] = csp
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    return response

@app.route('/favicon.ico')
def favicon():
    return "", 204

@app.route('/')
def index():
    try:
        client = bigquery.Client(project=PROJECT_ID)
        
        # 1. Dynamically find all tables in the dataset that look like log tables
        # We exclude internal BQ tables or temp tables if any
        tables_query = f"""
            SELECT table_name 
            FROM `{PROJECT_ID}.{DATASET_ID}.INFORMATION_SCHEMA.TABLES`
            WHERE table_type = 'BASE TABLE'
        """
        try:
            tables_job = client.query(tables_query)
            table_names = [row.table_name for row in tables_job]
        except Exception as e:
            # Dataset might not exist or no permission
            if "Not found" in str(e):
                return render_template('index.html', error="Waiting for dataset creation...", rows=[])
            return render_template('index.html', error=str(e), rows=[])

        if not table_names:
             return render_template('index.html', error="Dataset exists but is empty. Waiting for first log arrival...", rows=[])

        # 2. Construct a UNION ALL query across all found tables
        # We select common columns. 'jsonPayload' or 'textPayload' handling needs COALESCE logic
        # strictly casting to STRING to avoid schema mismatches between tables
        subqueries = []
        for tbl in table_names:
            subqueries.append(f"""
                SELECT 
                    timestamp, 
                    severity, 
                    logName, 
                    COALESCE(SAFE_CAST(jsonPayload AS STRING), textPayload, 'No Content') as message,
                    '{tbl}' as source_table
                FROM `{PROJECT_ID}.{DATASET_ID}.{tbl}`
                WHERE severity >= 'INFO'
            """)
        
        # Combine all subqueries
        final_query = " UNION ALL ".join(subqueries) + " ORDER BY timestamp DESC LIMIT 50"

        query_job = client.query(final_query)
        rows = [dict(row) for row in query_job]
        return render_template('index.html', rows=rows)

    except Exception as e:
        return render_template('index.html', error=f"System Error: {e}", rows=[])

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))
