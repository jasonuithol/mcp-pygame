#!/usr/bin/env bash
# build-container.sh — build the pygame MCP build container image
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "Building pygame-mcp-build image..."
docker build -f "$SCRIPT_DIR/Dockerfile" -t pygame-mcp-build "$SCRIPT_DIR"
echo "Done. Run with: $SCRIPT_DIR/start-container.sh"
