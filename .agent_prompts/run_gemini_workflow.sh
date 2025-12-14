#!/bin/bash
# Helper script to launch Gemini CLI with the Vertex validation workflow

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROMPT_FILE="$SCRIPT_DIR/vertex_validate_prompt.txt"

if [ ! -f "$PROMPT_FILE" ]; then
    echo "Error: Prompt file not found: $PROMPT_FILE"
    exit 1
fi

echo "========================================="
echo "Gemini CLI - Vertex AI Validation Workflow"
echo "========================================="
echo ""
echo "This will launch Gemini CLI in interactive mode with the workflow prompt."
echo "The workflow has 6 phases (N0→N6) covering validation, inventory, research,"
echo "design, implementation, and verification."
echo ""
echo "Press Enter to continue or Ctrl+C to cancel..."
read

# Read the prompt file and launch gemini in interactive mode
PROMPT=$(cat "$PROMPT_FILE")

echo "Launching Gemini CLI..."
echo ""

# Run the workflow prompt, then continue in interactive mode
gemini --prompt-interactive "$PROMPT"
