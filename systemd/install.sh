#!/bin/bash
# Install the embedding worker systemd service

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_NAME="embedding-worker"

echo "Installing ${SERVICE_NAME} systemd service..."

# Copy service file
sudo cp "${SCRIPT_DIR}/${SERVICE_NAME}.service" /etc/systemd/system/

# Reload systemd
sudo systemctl daemon-reload

# Enable service (start on boot)
sudo systemctl enable ${SERVICE_NAME}

echo "Service installed successfully!"
echo ""
echo "Commands:"
echo "  sudo systemctl start ${SERVICE_NAME}     # Start the worker"
echo "  sudo systemctl stop ${SERVICE_NAME}      # Stop the worker"
echo "  sudo systemctl restart ${SERVICE_NAME}   # Restart the worker"
echo "  sudo systemctl status ${SERVICE_NAME}    # Check status"
echo "  journalctl -u ${SERVICE_NAME} -f         # View logs"
echo ""
echo "To start the worker now:"
echo "  sudo systemctl start ${SERVICE_NAME}"
