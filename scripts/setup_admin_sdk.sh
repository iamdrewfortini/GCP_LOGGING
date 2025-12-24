#!/bin/bash
# setup_admin_sdk.sh
# Set up Google Admin SDK for user/group data ingestion

set -e

echo "👥 Setting up Google Admin SDK Integration"
echo "========================================="

# Configuration
PROJECT_ID="${PROJECT_ID:-diatonic-ai-gcp}"
DATASET_ID="org_enterprise"
DOMAIN="${DOMAIN:-your-domain.com}"

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

# Enable Admin SDK API
echo ""
echo "🔧 Enabling Admin SDK API..."

gcloud services enable admin.googleapis.com

log_info "Admin SDK API enabled"

# Create service account for Admin SDK
echo ""
echo "🔑 Setting up service account..."

SA_NAME="admin-sdk-sa"
SA_EMAIL="$SA_NAME@$PROJECT_ID.iam.gserviceaccount.com"

if gcloud iam service-accounts describe $SA_EMAIL &>/dev/null; then
    log_info "Service account $SA_EMAIL already exists"
else
    gcloud iam service-accounts create $SA_NAME \
        --description="Service account for Google Admin SDK access" \
        --display-name="Admin SDK Service Account"
    log_info "Created service account $SA_EMAIL"
fi

# Grant BigQuery permissions
echo "🔐 Granting BigQuery permissions..."

ROLES=(
    "roles/bigquery.dataEditor"
    "roles/bigquery.jobUser"
)

for ROLE in "${ROLES[@]}"; do
    gcloud projects add-iam-policy-binding $PROJECT_ID \
        --member="serviceAccount:$SA_EMAIL" \
        --role="$ROLE" --quiet
done

log_info "Granted BigQuery IAM roles"

# Generate service account key for domain-wide delegation
echo ""
echo "🔐 Generating service account key..."

KEY_FILE="keys/admin-sdk-key.json"
mkdir -p keys

if [ ! -f "$KEY_FILE" ]; then
    gcloud iam service-accounts keys create $KEY_FILE \
        --iam-account=$SA_EMAIL
    log_info "Service account key created: $KEY_FILE"
    log_warn "Store this key securely and delete after domain-wide delegation setup"
else
    log_warn "Key file already exists: $KEY_FILE"
fi

# Manual setup instructions
cat << EOF

📋 MANUAL DOMAIN-WIDE DELEGATION SETUP REQUIRED
===============================================

To access Google Workspace user/group data, complete these steps:

1. 🔗 Set up domain-wide delegation:
   URL: https://admin.google.com/ac/owl/domainwidedelegation

2. ⚙️ Add the service account:
   - Client ID: $(gcloud iam service-accounts describe $SA_EMAIL --format="value(oauth2ClientId)")
   - OAuth Scopes:
     https://www.googleapis.com/auth/admin.directory.user.readonly
     https://www.googleapis.com/auth/admin.directory.group.readonly
     https://www.googleapis.com/auth/admin.directory.orgunit.readonly

3. 🎯 Admin requirements:
   - Must be a Google Workspace Super Admin
   - Domain must have Admin SDK API enabled
   - Service account must be authorized for domain-wide delegation

4. 🔍 Verification:
   After setup, test with: python3 scripts/test_admin_sdk.py

EOF

# Create Python script for Admin SDK data extraction
cat > scripts/fetch_admin_data.py << 'ADMIN_EOF'
#!/usr/bin/env python3
"""
Fetch Google Workspace user/group data via Admin SDK
"""

import json
import logging
from datetime import datetime
from google.oauth2 import service_account
from googleapiclient.discovery import build
from google.cloud import bigquery
import os

# Configuration
PROJECT_ID = os.getenv("PROJECT_ID", "diatonic-ai-gcp")
DATASET_ID = "org_enterprise"
TABLE_ID = "stg_admin_users"
DOMAIN = os.getenv("DOMAIN", "your-domain.com")
KEY_FILE = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "keys/admin-sdk-key.json")
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", f"admin@{DOMAIN}")

# Admin SDK scopes
SCOPES = [
    'https://www.googleapis.com/auth/admin.directory.user.readonly',
    'https://www.googleapis.com/auth/admin.directory.group.readonly',
    'https://www.googleapis.com/auth/admin.directory.orgunit.readonly'
]

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class AdminSDKClient:
    def __init__(self):
        """Initialize Admin SDK client with domain-wide delegation"""
        
        if not os.path.exists(KEY_FILE):
            raise FileNotFoundError(f"Service account key not found: {KEY_FILE}")
        
        # Create credentials with domain-wide delegation
        credentials = service_account.Credentials.from_service_account_file(
            KEY_FILE, scopes=SCOPES)
        
        delegated_credentials = credentials.with_subject(ADMIN_EMAIL)
        
        self.service = build('admin', 'directory_v1', credentials=delegated_credentials)
        self.bq_client = bigquery.Client()
    
    def fetch_users(self):
        """Fetch all users from Google Workspace"""
        users = []
        page_token = None
        
        while True:
            try:
                result = self.service.users().list(
                    domain=DOMAIN,
                    maxResults=500,
                    pageToken=page_token,
                    projection='full'
                ).execute()
                
                users.extend(result.get('users', []))
                page_token = result.get('nextPageToken')
                
                if not page_token:
                    break
                    
            except Exception as e:
                logger.error(f"Error fetching users: {e}")
                raise
        
        logger.info(f"Fetched {len(users)} users")
        return users
    
    def fetch_groups(self):
        """Fetch all groups from Google Workspace"""
        groups = []
        page_token = None
        
        while True:
            try:
                result = self.service.groups().list(
                    domain=DOMAIN,
                    maxResults=200,
                    pageToken=page_token
                ).execute()
                
                groups.extend(result.get('groups', []))
                page_token = result.get('nextPageToken')
                
                if not page_token:
                    break
                    
            except Exception as e:
                logger.error(f"Error fetching groups: {e}")
                raise
        
        logger.info(f"Fetched {len(groups)} groups")
        return groups
    
    def fetch_orgunits(self):
        """Fetch organizational units"""
        try:
            result = self.service.orgunits().list(
                customerId='my_customer',
                type='all'
            ).execute()
            
            orgunits = result.get('organizationUnits', [])
            logger.info(f"Fetched {len(orgunits)} organizational units")
            return orgunits
            
        except Exception as e:
            logger.error(f"Error fetching org units: {e}")
            raise
    
    def load_to_bigquery(self, data_type, data):
        """Load data into BigQuery staging table"""
        
        table_ref = self.bq_client.dataset(DATASET_ID).table(TABLE_ID)
        
        rows = []
        fetched_at = datetime.utcnow()
        
        for item in data:
            row = {
                "fetched_at": fetched_at.isoformat(),
                "data_type": data_type,
                "payload": item
            }
            rows.append(row)
        
        if rows:
            job_config = bigquery.LoadJobConfig(
                write_disposition="WRITE_APPEND",
                schema_update_options=[bigquery.SchemaUpdateOption.ALLOW_FIELD_ADDITION]
            )
            
            job = self.bq_client.load_table_from_json(rows, table_ref, job_config=job_config)
            job.result()
            
            logger.info(f"Loaded {len(rows)} {data_type} records to BigQuery")

def main():
    """Main execution function"""
    try:
        client = AdminSDKClient()
        
        # Fetch all data types
        logger.info("Fetching users...")
        users = client.fetch_users()
        client.load_to_bigquery("users", users)
        
        logger.info("Fetching groups...")
        groups = client.fetch_groups()
        client.load_to_bigquery("groups", groups)
        
        logger.info("Fetching organizational units...")
        orgunits = client.fetch_orgunits()
        client.load_to_bigquery("orgunits", orgunits)
        
        logger.info("✅ Admin SDK data fetch completed successfully")
        
    except Exception as e:
        logger.error(f"❌ Admin SDK fetch failed: {e}")
        raise

if __name__ == "__main__":
    main()
ADMIN_EOF

chmod +x scripts/fetch_admin_data.py

# Create test script
cat > scripts/test_admin_sdk.py << 'TEST_EOF'
#!/usr/bin/env python3
"""
Test Google Admin SDK connectivity and permissions
"""

import os
import sys
from google.oauth2 import service_account
from googleapiclient.discovery import build

# Configuration
DOMAIN = os.getenv("DOMAIN", "your-domain.com")
KEY_FILE = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "keys/admin-sdk-key.json")
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", f"admin@{DOMAIN}")

SCOPES = [
    'https://www.googleapis.com/auth/admin.directory.user.readonly',
    'https://www.googleapis.com/auth/admin.directory.group.readonly',
    'https://www.googleapis.com/auth/admin.directory.orgunit.readonly'
]

def test_connection():
    """Test Admin SDK connection and permissions"""
    
    print("🧪 Testing Admin SDK Connection")
    print("==============================")
    
    # Check key file exists
    if not os.path.exists(KEY_FILE):
        print(f"❌ Service account key not found: {KEY_FILE}")
        sys.exit(1)
    
    print(f"✓ Service account key found")
    
    try:
        # Create credentials
        credentials = service_account.Credentials.from_service_account_file(
            KEY_FILE, scopes=SCOPES)
        
        delegated_credentials = credentials.with_subject(ADMIN_EMAIL)
        service = build('admin', 'directory_v1', credentials=delegated_credentials)
        
        print(f"✓ Admin SDK client initialized")
        print(f"✓ Using domain: {DOMAIN}")
        print(f"✓ Impersonating: {ADMIN_EMAIL}")
        
        # Test user access
        print("\n📊 Testing user access...")
        result = service.users().list(domain=DOMAIN, maxResults=1).execute()
        user_count = result.get('users', [])
        print(f"✅ Users accessible: {len(user_count)} (sample)")
        
        # Test group access  
        print("\n👥 Testing group access...")
        result = service.groups().list(domain=DOMAIN, maxResults=1).execute()
        group_count = result.get('groups', [])
        print(f"✅ Groups accessible: {len(group_count)} (sample)")
        
        # Test org unit access
        print("\n🏢 Testing organizational unit access...")
        result = service.orgunits().list(customerId='my_customer').execute()
        orgunit_count = result.get('organizationUnits', [])
        print(f"✅ Org units accessible: {len(orgunit_count)}")
        
        print("\n🎉 All Admin SDK tests passed!")
        return True
        
    except Exception as e:
        print(f"\n❌ Admin SDK test failed: {e}")
        print("\nTroubleshooting:")
        print("1. Verify domain-wide delegation is configured")
        print("2. Check that the admin email has proper permissions")
        print("3. Ensure the service account client ID is authorized")
        return False

if __name__ == "__main__":
    success = test_connection()
    sys.exit(0 if success else 1)
TEST_EOF

chmod +x scripts/test_admin_sdk.py

# Create SCD2 merge for admin data
cat > scripts/merge_admin_to_dims.sql << 'MERGE_ADMIN_EOF'
-- Merge Admin SDK data into workforce dimensional tables
-- Run this after loading staging data

-- Merge users into dim_workforce_member
MERGE `diatonic-ai-gcp.org_enterprise.dim_workforce_member` AS target
USING (
  SELECT DISTINCT
    JSON_EXTRACT_SCALAR(payload, '$.id') as member_id,
    JSON_EXTRACT_SCALAR(payload, '$.primaryEmail') as email,
    JSON_EXTRACT_SCALAR(payload, '$.name.fullName') as display_name,
    JSON_EXTRACT_SCALAR(payload, '$.orgUnitPath') as org_id,
    JSON_EXTRACT_SCALAR(payload, '$.relations[0].value') as manager_id,
    JSON_EXTRACT_SCALAR(payload, '$.employeeType') as employment_type,
    CURRENT_DATE() as active_from,
    CAST(NULL AS DATE) as active_to,
    NOT JSON_EXTRACT_SCALAR(payload, '$.suspended') = 'true' as is_current,
    'google_admin_sdk' as source_system,
    GENERATE_UUID() as trace_id,
    GENERATE_UUID() as span_id,
    CURRENT_TIMESTAMP() as created_at,
    CURRENT_TIMESTAMP() as updated_at,
    payload as labels
  FROM `diatonic-ai-gcp.org_enterprise.stg_admin_users`
  WHERE data_type = 'users'
    AND DATE(fetched_at) = CURRENT_DATE()
) AS source
ON target.member_id = source.member_id AND target.is_current = TRUE

WHEN NOT MATCHED THEN
  INSERT (member_id, email, display_name, org_id, manager_id, employment_type,
          active_from, active_to, is_current, source_system, trace_id, span_id,
          created_at, updated_at, labels)
  VALUES (source.member_id, source.email, source.display_name, source.org_id,
          source.manager_id, source.employment_type, source.active_from,
          source.active_to, source.is_current, source.source_system,
          source.trace_id, source.span_id, source.created_at, source.updated_at,
          source.labels)

WHEN MATCHED AND (
  target.email != source.email OR
  target.display_name != source.display_name OR
  target.org_id != source.org_id OR
  target.employment_type != source.employment_type OR
  target.is_current != source.is_current
) THEN UPDATE SET
  active_to = CURRENT_DATE(),
  is_current = FALSE,
  updated_at = CURRENT_TIMESTAMP();
MERGE_ADMIN_EOF

# Create requirements file for Python dependencies
cat > requirements-admin.txt << 'REQ_EOF'
google-auth==2.23.4
google-auth-oauthlib==1.1.0
google-auth-httplib2==0.1.1
google-api-python-client==2.108.0
google-cloud-bigquery==3.11.4
google-cloud-storage==2.10.0
REQ_EOF

log_info "Created Admin SDK integration scripts"

echo ""
echo "🎯 NEXT STEPS:"
echo "1. Install Python dependencies: pip install -r requirements-admin.txt"
echo "2. Complete domain-wide delegation setup (see instructions above)"
echo "3. Set environment variables:"
echo "   export DOMAIN=\"your-domain.com\""
echo "   export ADMIN_EMAIL=\"admin@your-domain.com\""
echo "4. Test connection: python3 scripts/test_admin_sdk.py"
echo "5. Run data fetch: python3 scripts/fetch_admin_data.py"
echo "6. Merge to dimensions: bq query < scripts/merge_admin_to_dims.sql"
echo ""
echo "⚠️  SECURITY NOTE:"
echo "   Store the service account key in Google Secret Manager for production"
echo "   Delete local key file after testing"
echo ""
echo "✅ Admin SDK setup complete!"