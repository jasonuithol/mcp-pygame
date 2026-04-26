#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MODEL_DIR="$SCRIPT_DIR/models/all-MiniLM-L6-v2"
SIBLING_MODEL="$HOME/Projects/claude-sandbox/mcp-knowledge/models/all-MiniLM-L6-v2"

# Reuse claude-sandbox's downloaded model if present — saves ~90MB on disk
# and avoids a second download.
if [ ! -f "$MODEL_DIR/onnx/model.onnx" ]; then
    mkdir -p "$SCRIPT_DIR/models"
    if [ -f "$SIBLING_MODEL/onnx/model.onnx" ]; then
        echo "Linking embedding model from claude-sandbox..."
        ln -sfn "$SIBLING_MODEL" "$MODEL_DIR"
    else
        echo "Downloading all-MiniLM-L6-v2 embedding model..."
        mkdir -p "$MODEL_DIR"
        TARBALL="$MODEL_DIR/onnx.tar.gz"
        curl -fSL -o "$TARBALL" \
            "https://chroma-onnx-models.s3.amazonaws.com/all-MiniLM-L6-v2/onnx.tar.gz"
        tar -xzf "$TARBALL" -C "$MODEL_DIR"
        rm -f "$TARBALL"
        echo "Model downloaded to $MODEL_DIR"
    fi
fi

docker build -t pygame-mcp-knowledge "$SCRIPT_DIR"
