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
