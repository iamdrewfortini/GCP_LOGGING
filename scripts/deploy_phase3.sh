#!/bin/bash
# Deploy Phase 3 components to production
# This script deploys all Phase 3 infrastructure

set -e

PROJECT_ID="${PROJECT_ID:-diatonic-ai-gcp}"
REGION="${REGION:-us-central1}"

echo "🚀 Deploying Phase 3 Components"
echo "Project: $PROJECT_ID"
echo "Region: $REGION"
echo ""

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Step 1: Deploy BigQuery table
echo -e "${YELLOW}Step 1: Deploying BigQuery table...${NC}"
./scripts/create_tool_invocations_table.sh
echo -e "${GREEN}✓ BigQuery table deployed${NC}"
echo ""

# Step 2: Create Pub/Sub topic for tool metrics
echo -e "${YELLOW}Step 2: Creating Pub/Sub topic...${NC}"
if gcloud pubsub topics describe tool-invocation-metrics --project=$PROJECT_ID &>/dev/null; then
    echo "Topic already exists"
else
    gcloud pubsub topics create tool-invocation-metrics \
        --project=$PROJECT_ID \
        --message-retention-duration=7d
    echo -e "${GREEN}✓ Topic created${NC}"
fi

# Create subscription
if gcloud pubsub subscriptions describe tool-metrics-to-bq --project=$PROJECT_ID &>/dev/null; then
    echo "Subscription already exists"
else
    gcloud pubsub subscriptions create tool-metrics-to-bq \
        --topic=tool-invocation-metrics \
        --ack-deadline=60 \
        --message-retention-duration=7d \
        --project=$PROJECT_ID
    echo -e "${GREEN}✓ Subscription created${NC}"
fi
echo ""

# Step 3: Deploy Firestore rules
echo -e "${YELLOW}Step 3: Deploying Firestore rules...${NC}"
firebase deploy --only firestore:rules --project=$PROJECT_ID
echo -e "${GREEN}✓ Firestore rules deployed${NC}"
echo ""

# Step 4: Deploy Firestore indexes
echo -e "${YELLOW}Step 4: Deploying Firestore indexes...${NC}"
firebase deploy --only firestore:indexes --project=$PROJECT_ID
echo -e "${GREEN}✓ Firestore indexes deployed${NC}"
echo ""

# Step 5: Verify deployments
echo -e "${YELLOW}Step 5: Verifying deployments...${NC}"

# Verify BigQuery table
if bq show $PROJECT_ID:chat_analytics.tool_invocations &>/dev/null; then
    echo -e "${GREEN}✓ BigQuery table verified${NC}"
else
    echo -e "${RED}✗ BigQuery table not found${NC}"
    exit 1
fi

# Verify Pub/Sub topic
if gcloud pubsub topics describe tool-invocation-metrics --project=$PROJECT_ID &>/dev/null; then
    echo -e "${GREEN}✓ Pub/Sub topic verified${NC}"
else
    echo -e "${RED}✗ Pub/Sub topic not found${NC}"
    exit 1
fi

echo ""
echo -e "${GREEN}✅ Phase 3 deployment complete!${NC}"
echo ""
echo "Next steps:"
echo "1. Update backend API to emit new SSE events (token_count, checkpoint, citation)"
echo "2. Integrate MeteredToolNode in src/agent/nodes.py"
echo "3. Add checkpoint node to LangGraph workflow"
echo "4. Update frontend chat route to use new components"
echo "5. Run integration tests"
echo ""
echo "See docs/research/ai-stack/PHASE3_INTEGRATION_GUIDE.md for details"
