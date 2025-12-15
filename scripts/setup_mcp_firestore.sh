#!/bin/bash
# Setup Firestore collection for MCP tools
# Phase 4, Task 4.8: mcp_tools Firestore collection

set -e

PROJECT_ID="${PROJECT_ID:-diatonic-ai-gcp}"

echo "🔧 Setting up MCP tools Firestore collection"
echo "Project: $PROJECT_ID"
echo ""

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Step 1: Update Firestore rules
echo -e "${YELLOW}Step 1: Updating Firestore rules...${NC}"

# Add MCP tools rules to firestore.rules
cat >> firestore.rules << 'EOF'

    // MCP Tools collection
    match /mcp_tools/{toolId} {
      // Allow authenticated users to read tool metadata
      allow read: if request.auth != null;
      
      // Only backend/admin can write
      allow write: if false;
    }
EOF

echo -e "${GREEN}✓ Firestore rules updated${NC}"
echo ""

# Step 2: Create Firestore indexes
echo -e "${YELLOW}Step 2: Creating Firestore indexes...${NC}"

# Add indexes to firestore.indexes.json
cat > firestore.indexes.json << 'EOF'
{
  "indexes": [
    {
      "collectionGroup": "mcp_tools",
      "queryScope": "COLLECTION",
      "fields": [
        { "fieldPath": "status", "order": "ASCENDING" },
        { "fieldPath": "created_at", "order": "DESCENDING" }
      ]
    },
    {
      "collectionGroup": "mcp_tools",
      "queryScope": "COLLECTION",
      "fields": [
        { "fieldPath": "spec_hash", "order": "ASCENDING" }
      ]
    },
    {
      "collectionGroup": "checkpoints",
      "queryScope": "COLLECTION",
      "fields": [
        { "fieldPath": "run_id", "order": "ASCENDING" },
        { "fieldPath": "created_at", "order": "DESCENDING" }
      ]
    }
  ],
  "fieldOverrides": []
}
EOF

echo -e "${GREEN}✓ Firestore indexes configured${NC}"
echo ""

# Step 3: Deploy to Firebase
echo -e "${YELLOW}Step 3: Deploying to Firebase...${NC}"

firebase deploy --only firestore:rules,firestore:indexes --project=$PROJECT_ID

echo ""
echo -e "${GREEN}✅ MCP Firestore setup complete!${NC}"
echo ""
echo "Collection: mcp_tools"
echo "Indexes:"
echo "  - status + created_at (for listing)"
echo "  - spec_hash (for lookups)"
echo ""
echo "Next steps:"
echo "  1. Generate tools: python -m src.mcp.cli generate <spec_file>"
echo "  2. List tools: python -m src.mcp.cli list"
echo "  3. View stats: python -m src.mcp.cli stats"
