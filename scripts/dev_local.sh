#!/bin/bash
# Local development script with Firebase emulator support
# Usage: ./scripts/dev_local.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}  Glass Pane Local Development Server${NC}"
echo -e "${BLUE}========================================${NC}"

# Check prerequisites
echo -e "\n${YELLOW}Checking prerequisites...${NC}"

if ! command -v firebase &> /dev/null; then
    echo -e "${RED}Firebase CLI not found. Install with: npm install -g firebase-tools${NC}"
    exit 1
fi

if ! command -v java &> /dev/null; then
    echo -e "${RED}Java not found. Firebase emulators require Java 11+${NC}"
    exit 1
fi

echo -e "${GREEN}✓ Prerequisites satisfied${NC}"

# Function to cleanup on exit
cleanup() {
    echo -e "\n${YELLOW}Shutting down...${NC}"
    # Kill background processes
    if [ -n "$EMULATOR_PID" ]; then
        kill $EMULATOR_PID 2>/dev/null || true
    fi
    if [ -n "$SERVER_PID" ]; then
        kill $SERVER_PID 2>/dev/null || true
    fi
    echo -e "${GREEN}Cleanup complete${NC}"
}
trap cleanup EXIT

# Start Firebase emulators in the background
echo -e "\n${YELLOW}Starting Firebase emulators...${NC}"
firebase emulators:start --only firestore &
EMULATOR_PID=$!

# Wait for emulators to be ready
echo -e "${YELLOW}Waiting for Firestore emulator to be ready...${NC}"
MAX_ATTEMPTS=30
ATTEMPT=0
while ! curl -s http://localhost:8181 > /dev/null 2>&1; do
    sleep 1
    ATTEMPT=$((ATTEMPT + 1))
    if [ $ATTEMPT -ge $MAX_ATTEMPTS ]; then
        echo -e "${RED}Firestore emulator failed to start after ${MAX_ATTEMPTS} seconds${NC}"
        exit 1
    fi
done
echo -e "${GREEN}✓ Firestore emulator ready on port 8181${NC}"

# Activate virtual environment if it exists
if [ -d ".venv" ]; then
    echo -e "\n${YELLOW}Activating virtual environment...${NC}"
    source .venv/bin/activate
fi

# Set environment variables for local development
export PROJECT_ID=diatonic-ai-gcp
export PROJECT_ID_LOGS=diatonic-ai-gcp
export PROJECT_ID_AGENT=diatonic-ai-gcp
export CANONICAL_VIEW=central_logging_v1.view_canonical_logs
export VERTEX_REGION=us-central1
export GOOGLE_GENAI_USE_VERTEXAI=true
export FIREBASE_ENABLED=true
export FIRESTORE_EMULATOR_HOST=localhost:8181

echo -e "\n${GREEN}Environment configured:${NC}"
echo -e "  PROJECT_ID=${PROJECT_ID}"
echo -e "  FIRESTORE_EMULATOR_HOST=${FIRESTORE_EMULATOR_HOST}"
echo -e "  FIREBASE_ENABLED=${FIREBASE_ENABLED}"

# Start the app server
echo -e "\n${YELLOW}Starting Glass Pane server on port 8080...${NC}"
echo -e "${BLUE}========================================${NC}"
echo -e "${GREEN}App URL:      http://localhost:8080${NC}"
echo -e "${GREEN}Emulator UI:  http://localhost:4000${NC}"
echo -e "${BLUE}========================================${NC}"
echo -e "${YELLOW}Press Ctrl+C to stop${NC}\n"

uvicorn src.api.main:app --host 0.0.0.0 --port 8080 --reload
