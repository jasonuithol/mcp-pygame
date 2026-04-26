#!/usr/bin/env bash
# seed.sh — seed the mcp-knowledge database with docs and project source
# Run from the host. Requires mcp-knowledge (port 5174) running.
set -euo pipefail

BASE="http://localhost:5174/mcp"

# ---------------------------------------------------------------------------
# MCP session helpers
# ---------------------------------------------------------------------------

get_session() {
    local url="$1"
    curl -si -X POST "$url" \
        -H 'Content-Type: application/json' \
        -H 'Accept: application/json, text/event-stream' \
        -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"seed","version":"0"}}}' \
        2>/dev/null | grep -i 'mcp-session-id' | tr -d '\r' | awk '{print $2}'
}

call_tool() {
    local url="$1"
    local session="$2"
    local id="$3"
    local name="$4"
    local args="$5"
    local max_time="${6:-300}"
    RESPONSE=$(echo "{\"jsonrpc\":\"2.0\",\"id\":$id,\"method\":\"tools/call\",\"params\":{\"name\":\"$name\",\"arguments\":$args}}" \
        | curl -s -X POST "$url" \
            -H 'Content-Type: application/json' \
            -H 'Accept: application/json, text/event-stream' \
            -H "mcp-session-id: $session" \
            --data-binary @- \
            --max-time "$max_time")
    echo "$RESPONSE" | grep '^data:' | tail -1 | sed 's/^data: //' | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    for c in d.get('result',{}).get('content',[]):
        if c.get('type')=='text': print(c['text'])
except: print('(parse error)')
" 2>/dev/null || echo "(no response)"
}

# ---------------------------------------------------------------------------
# Get session
# ---------------------------------------------------------------------------

echo "Connecting to mcp-knowledge..."
K_SESSION=$(get_session "$BASE")
if [ -z "$K_SESSION" ]; then
    echo "ERROR: Could not get MCP session from mcp-knowledge ($BASE)"
    echo "Is the container running? (Check: docker ps | grep mcp-knowledge)"
    exit 1
fi
echo "  Session: $K_SESSION"

# ---------------------------------------------------------------------------
# Seed docs
# ---------------------------------------------------------------------------

echo ""
echo "=== Seeding claude-pygame docs ==="
call_tool "$BASE" "$K_SESSION" 2 "seed_docs" \
    '{"docs_path":"/opt/projects/claude-pygame/claude/docs"}'

# ---------------------------------------------------------------------------
# Seed UltimatePyve source
# ---------------------------------------------------------------------------

if [ -d "$HOME/Projects/UltimatePyve" ]; then
    echo ""
    echo "=== Seeding UltimatePyve source ==="
    call_tool "$BASE" "$K_SESSION" 3 "seed_python_source" \
        '{"project":"UltimatePyve","source_dir":"/opt/projects/UltimatePyve","extra_tags":["successful-example"]}' \
        600
else
    echo ""
    echo "=== Skipping UltimatePyve (not found at ~/Projects/UltimatePyve) ==="
fi

# ---------------------------------------------------------------------------
# Optionally: pygame-ce source if the user has cloned it
# ---------------------------------------------------------------------------

if [ -d "$HOME/Projects/pygame-ce" ]; then
    echo ""
    echo "=== Seeding pygame-ce library source ==="
    call_tool "$BASE" "$K_SESSION" 4 "seed_python_source" \
        '{"project":"pygame-ce","source_dir":"/opt/projects/pygame-ce","extra_tags":["library","pygame-ce"]}' \
        900
else
    echo ""
    echo "(skipping pygame-ce — clone to ~/Projects/pygame-ce to include)"
fi

# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------

echo ""
echo "=== Stats ==="
call_tool "$BASE" "$K_SESSION" 5 "stats" '{}'

echo ""
echo "Done."
