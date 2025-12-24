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
