#!/bin/bash
# validate_production_config.sh
# Validates that all required configuration is in place for production deployment

set -e

echo "=============================================="
echo "Glass Pane Production Configuration Validator"
echo "=============================================="
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

ERRORS=0
WARNINGS=0

check_pass() {
    echo -e "  ${GREEN}✓${NC} $1"
}

check_fail() {
    echo -e "  ${RED}✗${NC} $1"
    ((ERRORS++))
}

check_warn() {
    echo -e "  ${YELLOW}!${NC} $1"
    ((WARNINGS++))
}

# ============================================
# GCP Configuration
# ============================================
echo "1. GCP Configuration"
echo "--------------------"

# Check if gcloud is installed and authenticated
if command -v gcloud &> /dev/null; then
    check_pass "gcloud CLI installed"

    PROJECT=$(gcloud config get-value project 2>/dev/null)
    if [ -n "$PROJECT" ]; then
        check_pass "GCP project configured: $PROJECT"
    else
        check_fail "GCP project not configured. Run: gcloud config set project YOUR_PROJECT_ID"
    fi

    ACCOUNT=$(gcloud auth list --filter=status:ACTIVE --format="value(account)" 2>/dev/null)
    if [ -n "$ACCOUNT" ]; then
        check_pass "Authenticated as: $ACCOUNT"
    else
        check_fail "Not authenticated. Run: gcloud auth login"
    fi
else
    check_fail "gcloud CLI not installed"
fi
echo ""

# ============================================
# Secret Manager Secrets
# ============================================
echo "2. Secret Manager Secrets"
echo "-------------------------"

if command -v gcloud &> /dev/null && [ -n "$PROJECT" ]; then
    # Check REDIS_PASSWORD secret
    if gcloud secrets describe REDIS_PASSWORD --project="$PROJECT" &>/dev/null; then
        check_pass "REDIS_PASSWORD secret exists"
    else
        check_warn "REDIS_PASSWORD secret not found (will be created during deployment)"
    fi

    # Check QDRANT_API_KEY secret
    if gcloud secrets describe QDRANT_API_KEY --project="$PROJECT" &>/dev/null; then
        check_pass "QDRANT_API_KEY secret exists"
    else
        check_warn "QDRANT_API_KEY secret not found (will be created during deployment)"
    fi
else
    check_warn "Skipping Secret Manager checks (gcloud not configured)"
fi
echo ""

# ============================================
# Pub/Sub Topics
# ============================================
echo "3. Pub/Sub Topics"
echo "-----------------"

if command -v gcloud &> /dev/null && [ -n "$PROJECT" ]; then
    # Check chat-events topic
    if gcloud pubsub topics describe chat-events --project="$PROJECT" &>/dev/null; then
        check_pass "chat-events topic exists"
    else
        check_fail "chat-events topic not found. Run: gcloud pubsub topics create chat-events"
    fi

    # Check embedding-jobs topic
    if gcloud pubsub topics describe embedding-jobs --project="$PROJECT" &>/dev/null; then
        check_pass "embedding-jobs topic exists"
    else
        check_warn "embedding-jobs topic not found (required for Phase 2 embeddings)"
    fi
else
    check_warn "Skipping Pub/Sub checks (gcloud not configured)"
fi
echo ""

# ============================================
# Firebase Configuration
# ============================================
echo "4. Firebase Configuration"
echo "-------------------------"

# Check frontend env files
if [ -f "frontend/.env.production" ]; then
    check_pass "frontend/.env.production exists"

    # Check required variables
    if grep -q "VITE_FIREBASE_API_KEY=" frontend/.env.production && ! grep -q "VITE_FIREBASE_API_KEY=$" frontend/.env.production; then
        check_pass "VITE_FIREBASE_API_KEY is set"
    else
        check_fail "VITE_FIREBASE_API_KEY is not set in frontend/.env.production"
    fi

    if grep -q "VITE_FIREBASE_APP_ID=" frontend/.env.production && ! grep -q "VITE_FIREBASE_APP_ID=$" frontend/.env.production; then
        check_pass "VITE_FIREBASE_APP_ID is set"
    else
        check_fail "VITE_FIREBASE_APP_ID is not set in frontend/.env.production"
    fi

    if grep -q "VITE_USE_FIREBASE_EMULATORS=false" frontend/.env.production; then
        check_pass "Firebase emulators disabled for production"
    else
        check_warn "VITE_USE_FIREBASE_EMULATORS should be 'false' for production"
    fi
else
    check_fail "frontend/.env.production not found. Copy from frontend/.env.production.template"
fi
echo ""

# ============================================
# Backend Configuration
# ============================================
echo "5. Backend Configuration"
echo "------------------------"

# Check if .env.prod.template exists
if [ -f ".env.prod.template" ]; then
    check_pass ".env.prod.template exists"
else
    check_warn ".env.prod.template not found"
fi

# Check Python dependencies
if [ -f "requirements.txt" ]; then
    check_pass "requirements.txt exists"
else
    check_fail "requirements.txt not found"
fi

# Check Dockerfile
if [ -f "Dockerfile" ]; then
    check_pass "Dockerfile exists"
else
    check_fail "Dockerfile not found"
fi
echo ""

# ============================================
# GitHub Actions Configuration
# ============================================
echo "6. GitHub Actions Workflow"
echo "--------------------------"

if [ -f ".github/workflows/deploy-production.yml" ]; then
    check_pass "deploy-production.yml workflow exists"

    # Check for required secrets/vars references
    if grep -q "secrets.GCP_PROJECT_ID" .github/workflows/deploy-production.yml; then
        check_pass "GCP_PROJECT_ID secret referenced"
    else
        check_fail "GCP_PROJECT_ID secret not referenced in workflow"
    fi

    if grep -q "secrets.GCP_SA_KEY" .github/workflows/deploy-production.yml; then
        check_pass "GCP_SA_KEY secret referenced"
    else
        check_fail "GCP_SA_KEY secret not referenced in workflow"
    fi

    if grep -q "secrets.REDIS_PASSWORD" .github/workflows/deploy-production.yml; then
        check_pass "REDIS_PASSWORD secret referenced"
    else
        check_warn "REDIS_PASSWORD secret not referenced in workflow"
    fi

    if grep -q "secrets.QDRANT_API_KEY" .github/workflows/deploy-production.yml; then
        check_pass "QDRANT_API_KEY secret referenced"
    else
        check_warn "QDRANT_API_KEY secret not referenced in workflow"
    fi
else
    check_fail "deploy-production.yml workflow not found"
fi
echo ""

# ============================================
# Service Account Roles (informational)
# ============================================
echo "7. Required IAM Roles (for reference)"
echo "--------------------------------------"
echo "   The Cloud Run service account needs these roles:"
echo "   - roles/bigquery.dataViewer"
echo "   - roles/bigquery.jobUser"
echo "   - roles/aiplatform.user"
echo "   - roles/datastore.user"
echo "   - roles/pubsub.publisher"
echo "   - roles/logging.viewer"
echo "   - roles/cloudtrace.user"
echo "   - roles/secretmanager.secretAccessor"
echo ""

# ============================================
# Summary
# ============================================
echo "=============================================="
echo "Summary"
echo "=============================================="
if [ $ERRORS -eq 0 ] && [ $WARNINGS -eq 0 ]; then
    echo -e "${GREEN}All checks passed!${NC}"
elif [ $ERRORS -eq 0 ]; then
    echo -e "${YELLOW}$WARNINGS warning(s), 0 errors${NC}"
else
    echo -e "${RED}$ERRORS error(s), $WARNINGS warning(s)${NC}"
fi
echo ""

# ============================================
# GitHub Secrets Checklist
# ============================================
echo "=============================================="
echo "GitHub Secrets Checklist"
echo "=============================================="
echo "Add these secrets to GitHub repository settings:"
echo ""
echo "REQUIRED SECRETS:"
echo "  [ ] GCP_PROJECT_ID     - Your GCP project ID"
echo "  [ ] GCP_SA_KEY         - Service account JSON key"
echo "  [ ] REDIS_PASSWORD     - Redis/Memorystore password"
echo "  [ ] QDRANT_API_KEY     - Qdrant vector DB API key"
echo ""
echo "REQUIRED VARIABLES:"
echo "  [ ] GCP_REGION         - e.g., us-central1"
echo "  [ ] SERVICE_NAME       - e.g., glass-pane"
echo "  [ ] SERVICE_ACCOUNT    - e.g., glass-pane@PROJECT.iam.gserviceaccount.com"
echo "  [ ] CANONICAL_VIEW     - e.g., org_observability.logs_canonical_v2"
echo "  [ ] REDIS_HOST         - Redis server hostname"
echo "  [ ] REDIS_PORT         - Redis port (usually 6379)"
echo "  [ ] QDRANT_URL         - Qdrant server URL"
echo ""
echo "See docs/PRODUCTION_DEPLOYMENT.md for complete setup instructions."
echo ""

exit $ERRORS
