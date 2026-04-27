# pygame MCP services

Two MCP services are registered in this sandbox:

## pygame-build (port 5172)

Runs inside a Python 3.12 container. Tools:

| Tool | Args | Purpose |
|------|------|---------|
| `install_deps` | `project: str` | Create `<project>/.venv-mcp/` if missing, then `pip install -r requirements.txt` (and `requirements-dev.txt` if present). Idempotent. |
| `run_tests` | `project: str, test_filter: str = ""` | Run pytest inside the container's venv with `SDL_VIDEODRIVER=dummy` and `SDL_AUDIODRIVER=dummy`. Returns summary; full JSON report fires to mcp-knowledge. |
| `lint` | `project: str` | `ruff check <project>/`. |

Tests run **headless**: pygame initialises without a display or audio device.
Tests that need to render should blit to an off-screen `Surface` and assert on
pixel arrays.

## pygame-knowledge (port 5174)

See `mcp-knowledge/CLAUDE.md` for the full design.

Query tools: `ask`, `ask_tagged`, `ask_module`, `list_sources`, `stats`.

Maintenance tools: `forget`, `seed_docs`, `seed_python_source`, `retag_all`.

The knowledge base is **domain-scoped, not project-scoped** — all pygame
projects share one `pygame_knowledge` collection so cross-project patterns
surface in retrieval.

## What's not here (yet)

- **No `mcp-control`.** Running the game interactively happens on the host
  shell, not through MCP. Add a control service when process lifecycle gets
  complex enough to need it.
- **No interactive display forwarding.** The build container is headless.
  Play the game on the host.
- **No Thunderstore/distribution tools.** Distribution model (PyInstaller,
  zipapp, setup script) is still open — no MCP surface yet.
