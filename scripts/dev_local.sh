#!/bin/bash
# Local development script with Firebase emulator support
# Usage: ./scripts/dev_local.sh [--emulators-only] [--app-only]

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Parse arguments
EMULATORS_ONLY=false
APP_ONLY=false

for arg in "$@"; do
    case $arg in
        --emulators-only)
            EMULATORS_ONLY=true
            shift
            ;;
        --app-only)
            APP_ONLY=true
            shift
            ;;
    esac
done

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
    jobs -p | xargs -r kill 2>/dev/null || true
    echo -e "${GREEN}Cleanup complete${NC}"
}
trap cleanup EXIT

# Firebase Emulator Ports
AUTH_PORT=9099
FIRESTORE_PORT=8181
STORAGE_PORT=9199
FUNCTIONS_PORT=5001
PUBSUB_PORT=8085
DATABASE_PORT=9000
HOSTING_PORT=5000
UI_PORT=4000
HUB_PORT=4400

# Start Firebase emulators
if [ "$APP_ONLY" = false ]; then
    echo -e "\n${YELLOW}Starting Firebase emulators...${NC}"
    firebase emulators:start &
    EMULATOR_PID=$!

    # Wait for emulators to be ready
    echo -e "${YELLOW}Waiting for emulators to be ready...${NC}"
    MAX_ATTEMPTS=60
    ATTEMPT=0
    while ! curl -s http://localhost:$UI_PORT > /dev/null 2>&1; do
        sleep 1
        ATTEMPT=$((ATTEMPT + 1))
        if [ $ATTEMPT -ge $MAX_ATTEMPTS ]; then
            echo -e "${RED}Emulators failed to start after ${MAX_ATTEMPTS} seconds${NC}"
            exit 1
        fi
        echo -ne "\r${YELLOW}Waiting... ($ATTEMPT/$MAX_ATTEMPTS)${NC}"
    done
    echo -e "\n${GREEN}✓ Firebase emulators ready${NC}"

    echo -e "\n${CYAN}Emulator Ports:${NC}"
    echo -e "  Auth:           http://localhost:${AUTH_PORT}"
    echo -e "  Firestore:      http://localhost:${FIRESTORE_PORT}"
    echo -e "  Storage:        http://localhost:${STORAGE_PORT}"
    echo -e "  Functions:      http://localhost:${FUNCTIONS_PORT}"
    echo -e "  PubSub:         http://localhost:${PUBSUB_PORT}"
    echo -e "  Realtime DB:    http://localhost:${DATABASE_PORT}"
    echo -e "  Hosting:        http://localhost:${HOSTING_PORT}"
    echo -e "  Emulator UI:    ${GREEN}http://localhost:${UI_PORT}${NC}"
fi

if [ "$EMULATORS_ONLY" = true ]; then
    echo -e "\n${GREEN}Emulators running. Press Ctrl+C to stop.${NC}"
    wait
    exit 0
fi

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

# Firebase Emulator Environment Variables
export FIRESTORE_EMULATOR_HOST=localhost:${FIRESTORE_PORT}
export FIREBASE_AUTH_EMULATOR_HOST=localhost:${AUTH_PORT}
export FIREBASE_STORAGE_EMULATOR_HOST=localhost:${STORAGE_PORT}
export PUBSUB_EMULATOR_HOST=localhost:${PUBSUB_PORT}
export FIREBASE_DATABASE_EMULATOR_HOST=localhost:${DATABASE_PORT}

echo -e "\n${GREEN}Environment configured:${NC}"
echo -e "  PROJECT_ID=${PROJECT_ID}"
echo -e "  FIRESTORE_EMULATOR_HOST=${FIRESTORE_EMULATOR_HOST}"
echo -e "  FIREBASE_AUTH_EMULATOR_HOST=${FIREBASE_AUTH_EMULATOR_HOST}"
echo -e "  FIREBASE_STORAGE_EMULATOR_HOST=${FIREBASE_STORAGE_EMULATOR_HOST}"
echo -e "  PUBSUB_EMULATOR_HOST=${PUBSUB_EMULATOR_HOST}"

# Start the app server
APP_PORT=8080
echo -e "\n${YELLOW}Starting Glass Pane server on port ${APP_PORT}...${NC}"
echo -e "${BLUE}========================================${NC}"
echo -e "${GREEN}App URL:        http://localhost:${APP_PORT}${NC}"
echo -e "${GREEN}Emulator UI:    http://localhost:${UI_PORT}${NC}"
echo -e "${BLUE}========================================${NC}"
echo -e "${YELLOW}Press Ctrl+C to stop${NC}\n"

uvicorn src.api.main:app --host 0.0.0.0 --port $APP_PORT --reload
