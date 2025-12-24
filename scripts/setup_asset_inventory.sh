#!/bin/bash
# setup_asset_inventory.sh
# Set up Cloud Asset Inventory export for enterprise resource discovery

set -e

echo "🏗️ Setting up Cloud Asset Inventory Export"
echo "=========================================="

# Configuration
PROJECT_ID="${PROJECT_ID:-diatonic-ai-gcp}"
BUCKET_NAME="${BUCKET_NAME:-${PROJECT_ID}-asset-inventory}"
DATASET_ID="org_enterprise"
LOCATION="US"

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

log_info() { echo -e "${GREEN}✓${NC} $1"; }
log_warn() { echo -e "${YELLOW}!${NC} $1"; }
log_error() { echo -e "${RED}✗${NC} $1"; }

# Check prerequisites
echo "🔍 Checking prerequisites..."

if ! command -v gcloud &> /dev/null; then
    log_error "gcloud CLI not installed"
    exit 1
fi

# Set project
gcloud config set project $PROJECT_ID
log_info "Using project: $PROJECT_ID"

# Enable required APIs
echo ""
echo "🔧 Enabling required APIs..."

gcloud services enable cloudasset.googleapis.com \
    storage.googleapis.com \
    bigquery.googleapis.com \
    cloudscheduler.googleapis.com \
    cloudworkflows.googleapis.com

log_info "Required APIs enabled"

# Create GCS bucket for asset exports
echo ""
echo "📦 Setting up GCS bucket..."

if gsutil ls gs://$BUCKET_NAME &>/dev/null; then
    log_info "Bucket gs://$BUCKET_NAME already exists"
else
    gsutil mb -l $LOCATION gs://$BUCKET_NAME
    log_info "Created bucket gs://$BUCKET_NAME"
fi

# Set bucket lifecycle to auto-delete old exports
cat > /tmp/lifecycle.json << 'LIFECYCLE_EOF'
{
  "lifecycle": {
    "rule": [
      {
        "action": {"type": "Delete"},
        "condition": {"age": 30}
      }
    ]
  }
}
LIFECYCLE_EOF

gsutil lifecycle set /tmp/lifecycle.json gs://$BUCKET_NAME
rm /tmp/lifecycle.json
log_info "Set bucket lifecycle (30 day retention)"

# Create service account for asset inventory
echo ""
echo "🔑 Setting up service account..."

SA_NAME="asset-inventory-sa"
SA_EMAIL="$SA_NAME@$PROJECT_ID.iam.gserviceaccount.com"

if gcloud iam service-accounts describe $SA_EMAIL &>/dev/null; then
    log_info "Service account $SA_EMAIL already exists"
else
    gcloud iam service-accounts create $SA_NAME \
        --description="Service account for Cloud Asset Inventory exports" \
        --display-name="Asset Inventory Service Account"
    log_info "Created service account $SA_EMAIL"
fi

# Grant necessary permissions
echo "🔐 Granting permissions..."

ROLES=(
    "roles/cloudasset.viewer"
    "roles/storage.objectAdmin"
    "roles/bigquery.dataEditor"
    "roles/bigquery.jobUser"
)

for ROLE in "${ROLES[@]}"; do
    gcloud projects add-iam-policy-binding $PROJECT_ID \
        --member="serviceAccount:$SA_EMAIL" \
        --role="$ROLE" --quiet
done

log_info "Granted required IAM roles"

# Create initial asset export
echo ""
echo "📊 Creating initial asset export..."

EXPORT_FILE="gs://$BUCKET_NAME/assets-$(date +%Y%m%d).json"

gcloud asset export \
    --project=$PROJECT_ID \
    --output-path=$EXPORT_FILE \
    --content-type=resource \
    --asset-types="*"

log_info "Initial export created: $EXPORT_FILE"

# Create BigQuery external table
echo ""
echo "📋 Creating BigQuery staging table..."

bq mk --table \
    --description="Asset inventory staging data" \
    --label=source_system:cloud_asset_inventory \
    --label=team:enterprise-data \
    --label=env:prod \
    $PROJECT_ID:$DATASET_ID.stg_asset_inventory \
    fetched_at:TIMESTAMP,asset_type:STRING,payload:JSON

log_info "Created staging table stg_asset_inventory"

# Create data loading script
cat > scripts/load_asset_inventory.py << 'LOADER_EOF'
#!/usr/bin/env python3
"""
Load Cloud Asset Inventory exports into BigQuery staging table
"""

import json
import logging
from datetime import datetime
from google.cloud import bigquery, storage
import os

# Configuration
PROJECT_ID = os.getenv("PROJECT_ID", "diatonic-ai-gcp")
BUCKET_NAME = f"{PROJECT_ID}-asset-inventory"
DATASET_ID = "org_enterprise"
TABLE_ID = "stg_asset_inventory"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def load_latest_export():
    """Load the latest asset inventory export into BigQuery"""
    
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
    export_data = json.loads(latest_blob.download_as_text())
    
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
    
    logger.info(f"Loaded {len(rows)} asset records")
    
if __name__ == "__main__":
    load_latest_export()
LOADER_EOF

chmod +x scripts/load_asset_inventory.py

# Create Workflow for scheduled exports
cat > workflows/asset_inventory_workflow.yaml << 'WORKFLOW_EOF'
main:
  steps:
    - export_assets:
        call: googleapis.cloudasset.v1.projects.exportAssets
        args:
          parent: ${sys.get_env("GOOGLE_CLOUD_PROJECT_ID")}
          body:
            outputConfig:
              gcsDestination:
                uri: ${"gs://" + sys.get_env("GOOGLE_CLOUD_PROJECT_ID") + "-asset-inventory/assets-" + text.split(sys.now(), "T")[0] + ".json"}
            contentType: "RESOURCE"
        result: export_result
    
    - wait_for_export:
        call: sys.sleep
        args:
          seconds: 300  # Wait 5 minutes for export to complete
    
    - load_to_bigquery:
        call: http.post
        args:
          url: ${"https://cloudfunctions.googleapis.com/v1/projects/" + sys.get_env("GOOGLE_CLOUD_PROJECT_ID") + "/locations/us-central1/functions/load-asset-inventory"}
          auth:
            type: OIDC
        result: load_result
    
    - return_result:
        return: 
          export_status: ${export_result}
          load_status: ${load_result}
WORKFLOW_EOF

# Create Cloud Scheduler job configuration
cat > scripts/create_scheduler_job.sh << 'SCHEDULER_EOF'
#!/bin/bash
# Create Cloud Scheduler job for daily asset inventory

PROJECT_ID="${PROJECT_ID:-diatonic-ai-gcp}"
WORKFLOW_NAME="asset-inventory-workflow"
JOB_NAME="asset-inventory-daily"

echo "📅 Creating Cloud Scheduler job..."

# Deploy workflow first
gcloud workflows deploy $WORKFLOW_NAME \
    --source=workflows/asset_inventory_workflow.yaml \
    --location=us-central1

# Create scheduler job
gcloud scheduler jobs create http $JOB_NAME \
    --location=us-central1 \
    --schedule="0 2 * * *" \
    --uri="https://workflowexecutions.googleapis.com/v1/projects/$PROJECT_ID/locations/us-central1/workflows/$WORKFLOW_NAME/executions" \
    --http-method=POST \
    --oauth-service-account-email="asset-inventory-sa@$PROJECT_ID.iam.gserviceaccount.com" \
    --headers="Content-Type=application/json" \
    --message-body="{}"

echo "✅ Scheduler job created: runs daily at 2 AM UTC"
SCHEDULER_EOF

chmod +x scripts/create_scheduler_job.sh

# Create SCD2 merge script template
cat > scripts/merge_assets_to_dims.sql << 'MERGE_EOF'
-- Merge asset inventory into dimensional tables
-- Run this after loading staging data

-- Example: Merge projects
MERGE `diatonic-ai-gcp.org_enterprise.dim_project` AS target
USING (
  SELECT DISTINCT
    JSON_EXTRACT_SCALAR(payload, '$.name') as project_id,
    JSON_EXTRACT_SCALAR(payload, '$.displayName') as project_name,
    JSON_EXTRACT_SCALAR(payload, '$.parent') as folder_id,
    JSON_EXTRACT_SCALAR(payload, '$.lifecycleState') as lifecycle_state,
    CURRENT_DATE() as active_from,
    CAST(NULL AS DATE) as active_to,
    TRUE as is_current,
    'cloud_asset_inventory' as source_system,
    GENERATE_UUID() as trace_id,
    GENERATE_UUID() as span_id,
    CURRENT_TIMESTAMP() as created_at,
    CURRENT_TIMESTAMP() as updated_at,
    payload as labels
  FROM `diatonic-ai-gcp.org_enterprise.stg_asset_inventory`
  WHERE asset_type = 'cloudresourcemanager.googleapis.com/Project'
    AND DATE(fetched_at) = CURRENT_DATE()
) AS source
ON target.project_id = source.project_id AND target.is_current = TRUE

WHEN NOT MATCHED THEN
  INSERT (project_id, project_name, folder_id, lifecycle_state, active_from, 
          active_to, is_current, source_system, trace_id, span_id, 
          created_at, updated_at, labels)
  VALUES (source.project_id, source.project_name, source.folder_id, 
          source.lifecycle_state, source.active_from, source.active_to, 
          source.is_current, source.source_system, source.trace_id, 
          source.span_id, source.created_at, source.updated_at, source.labels)

WHEN MATCHED AND (
  target.project_name != source.project_name OR
  target.folder_id != source.folder_id OR
  target.lifecycle_state != source.lifecycle_state
) THEN UPDATE SET
  active_to = CURRENT_DATE(),
  is_current = FALSE,
  updated_at = CURRENT_TIMESTAMP();

-- Insert new version for changed records
INSERT INTO `diatonic-ai-gcp.org_enterprise.dim_project`
SELECT 
  source.project_id, source.project_name, source.folder_id, source.lifecycle_state,
  source.active_from, source.active_to, source.is_current, source.source_system,
  source.trace_id, source.span_id, source.created_at, source.updated_at, source.labels
FROM (
  SELECT DISTINCT
    JSON_EXTRACT_SCALAR(payload, '$.name') as project_id,
    JSON_EXTRACT_SCALAR(payload, '$.displayName') as project_name,
    JSON_EXTRACT_SCALAR(payload, '$.parent') as folder_id,
    JSON_EXTRACT_SCALAR(payload, '$.lifecycleState') as lifecycle_state,
    CURRENT_DATE() as active_from,
    CAST(NULL AS DATE) as active_to,
    TRUE as is_current,
    'cloud_asset_inventory' as source_system,
    GENERATE_UUID() as trace_id,
    GENERATE_UUID() as span_id,
    CURRENT_TIMESTAMP() as created_at,
    CURRENT_TIMESTAMP() as updated_at,
    payload as labels
  FROM `diatonic-ai-gcp.org_enterprise.stg_asset_inventory`
  WHERE asset_type = 'cloudresourcemanager.googleapis.com/Project'
    AND DATE(fetched_at) = CURRENT_DATE()
) AS source
INNER JOIN `diatonic-ai-gcp.org_enterprise.dim_project` AS target
ON target.project_id = source.project_id 
WHERE target.is_current = FALSE  -- Only insert if we marked a record as historical
  AND target.updated_at = CURRENT_TIMESTAMP();
MERGE_EOF

log_info "Created asset inventory scripts and workflows"

echo ""
echo "🎯 NEXT STEPS:"
echo "1. Run initial test: python3 scripts/load_asset_inventory.py"
echo "2. Set up automated workflow: ./scripts/create_scheduler_job.sh"
echo "3. Test SCD2 merges: bq query < scripts/merge_assets_to_dims.sql"
echo "4. Monitor with: gsutil ls gs://$BUCKET_NAME/"
echo ""
echo "✅ Asset inventory setup complete!"