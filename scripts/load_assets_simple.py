#!/usr/bin/env python3
"""
Simple loader for asset inventory data into BigQuery
"""

import json
import logging
from datetime import datetime
from google.cloud import bigquery, storage

# Configuration
PROJECT_ID = "diatonic-ai-gcp"
BUCKET_NAME = "diatonic-ai-gcp-asset-inventory"
DATASET_ID = "org_enterprise"
TABLE_ID = "stg_asset_inventory"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def main():
    """Load latest asset inventory export into BigQuery"""
    try:
        # Initialize clients
        storage_client = storage.Client()
        bq_client = bigquery.Client()
        
        # Find latest export file
        bucket = storage_client.bucket(BUCKET_NAME)
        blobs = list(bucket.list_blobs(prefix="assets-"))
        
        if not blobs:
            logger.error("No asset export files found")
            return
        
        # Get most recent file
        latest_blob = max(blobs, key=lambda x: x.time_created)
        logger.info(f"Loading {latest_blob.name}")
        
        # Download and parse export
        export_content = latest_blob.download_as_text()
        export_data = json.loads(export_content)
        
        # Prepare rows for BigQuery
        rows = []
        fetched_at = datetime.utcnow()
        
        for asset in export_data:
            row = {
                "fetched_at": fetched_at.isoformat(),
                "asset_type": asset.get("assetType", "unknown"),
                "payload": asset
            }
            rows.append(row)
        
        # Load into BigQuery
        table_ref = bq_client.dataset(DATASET_ID).table(TABLE_ID)
        
        job_config = bigquery.LoadJobConfig(
            write_disposition="WRITE_APPEND",
            schema_update_options=[bigquery.SchemaUpdateOption.ALLOW_FIELD_ADDITION]
        )
        
        job = bq_client.load_table_from_json(rows, table_ref, job_config=job_config)
        job.result()  # Wait for completion
        
        logger.info(f"✅ Loaded {len(rows)} asset records successfully")
        
    except Exception as e:
        logger.error(f"❌ Asset loading failed: {e}")
        raise

if __name__ == "__main__":
    main()