#!/usr/bin/env bash
# Helper commands to populate staging tables in diatonic-ai-gcp
# NOTE: Fill in bucket, billing account, and Admin SDK credentials before running.

set -euo pipefail

PROJECT=diatonic-ai-gcp
SA=enterprise-ingest@${PROJECT}.iam.gserviceaccount.com

# 1) Cloud Asset Inventory export -> GCS -> BigQuery staging
# export BUCKET=your-bucket
# gcloud asset export \
#   --project=${PROJECT} \
#   --content-type=resource \
#   --output-path=gs://${BUCKET}/cai/resources.ndjson \
#   --impersonate-service-account=${SA}
# bq load --source_format=NEWLINE_DELIMITED_JSON \
#   ${PROJECT}:org_enterprise.stg_asset_inventory \
#   gs://${BUCKET}/cai/resources.ndjson

# 2) Service Usage export -> local JSON -> staging
# gcloud services list --available --format=json \
#   --project=${PROJECT} \
#   --impersonate-service-account=${SA} > /tmp/service_usage.json
# bq load --source_format=NEWLINE_DELIMITED_JSON \
#   ${PROJECT}:org_enterprise.stg_service_usage \
#   /tmp/service_usage.json

# 3) Admin SDK users/groups (requires Workspace domain-wide delegation)
# Replace <CUSTOMER_ID> and ensure OAuth client with delegated scopes:
#   https://www.googleapis.com/auth/admin.directory.user.readonly
#   https://www.googleapis.com/auth/admin.directory.group.readonly
# Example using directory_v1 via curl with an access token:
# ACCESS_TOKEN=$(gcloud auth print-access-token --impersonate-service-account=${SA})
# curl -s -H \"Authorization: Bearer ${ACCESS_TOKEN}\" \\
#   \"https://admin.googleapis.com/admin/directory/v1/users?customer=<CUSTOMER_ID>&maxResults=500\" \\
#   > /tmp/admin_users.json
# bq load --source_format=NEWLINE_DELIMITED_JSON \\
#   ${PROJECT}:org_enterprise.stg_admin_users \\
#   /tmp/admin_users.json

echo \"Staging load helper prepared. Uncomment and fill variables to run exports.\" 
