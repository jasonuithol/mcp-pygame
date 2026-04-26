# mcp-pygame

MCP service pair for Python / pygame development. Two containers:

| Subdir | Container | Port | Purpose |
|--------|-----------|------|---------|
| `service/` | `pygame-mcp-build` | 5172 | `run_tests`, `lint`, `install_deps` for pygame projects |
| `knowledge/` | `pygame-mcp-knowledge` | 5174 | RAG over pygame source, project source, curated docs |

The two halves are paired: `service/` fires fire-and-forget POSTs at
`knowledge/`'s `/ingest` endpoint, so test failures, fixes, and lint
errors accumulate as retrievable context.

## Consumers

Currently launched by [`claude-pygame`](../claude-pygame/) via its
`start.sh`. Any MCP client speaking streamable HTTP can mount these
services — the protocol is provider-agnostic.

## Usage

```bash
# Build images (first time, or after Dockerfile changes)
service/build-container.sh
knowledge/build-container.sh

# Start
service/start-container.sh
knowledge/start-container.sh

# First-time KB seed
knowledge/seed.sh
```

Both containers use host networking (ports above). The knowledge
container needs an NVIDIA GPU + container toolkit for accelerated
embeddings (see `knowledge/setup-gpu.sh`).

## Design

See `knowledge/CLAUDE.md` for the knowledge service's design
(chunking strategy, ingest routing, metadata schema, known concerns).
