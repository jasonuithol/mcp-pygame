#!/usr/bin/env bash
# start.sh — bring up both mcp-pygame containers.
# Idempotent: each inner script revives an existing container or creates a new one.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "Starting pygame-mcp-build..."
"$SCRIPT_DIR/service/start-container.sh"

echo "Starting pygame-mcp-knowledge..."
"$SCRIPT_DIR/knowledge/start-container.sh"

echo "Done. Services on :5172 (build) and :5174 (knowledge)."
