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
./setup.sh                # one-time, idempotent (builds both images)
./start.sh                # bring up both containers
./stop.sh                 # shut them down (containers preserved for revival)
./clean.sh                # remove containers + images (full teardown)

knowledge/seed.sh         # first-time KB seed
```

To validate setup works from bare state:

```bash
./clean.sh && ./setup.sh && ./start.sh
```

Both containers use host networking (ports above). The knowledge
container needs an NVIDIA GPU + container toolkit for accelerated
embeddings (see `knowledge/setup-gpu.sh`).

## Design

See `knowledge/CLAUDE.md` for the knowledge service's design
(chunking strategy, ingest routing, metadata schema, known concerns).
