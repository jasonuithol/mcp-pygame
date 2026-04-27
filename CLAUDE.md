# claude-sandbox-core (pygame domain)

You are running inside a Podman container for Python/pygame development. Your
cwd is `/workspace/<project>/` — a bind-mount of `~/Projects/<project>` on the
host. Changes you make are real.

## MCP services

Two services are registered. Use them — don't reinvent.

- **pygame-knowledge** (`ask`, `ask_tagged`, `ask_module`, `ask_project`,
  `stats`, `list_sources`) — RAG over curated docs, indexed project source,
  pygame-ce library source, and accumulated test-failure/fix history.
  **Query this before writing non-trivial code.** Cross-project retrieval is
  the point.
- **pygame-build** (`install_deps`, `run_tests`, `lint`) — headless Python
  3.12 execution. `run_tests` runs with `SDL_VIDEODRIVER=dummy` and
  `SDL_AUDIODRIVER=dummy`; test failures auto-ingest into pygame-knowledge.

Detail: `/workspace/docs/PYGAME_MCP.md`, `/workspace/docs/INGEST_MCP.md`.

## Working loop

1. **Ask the knowledge base first.** e.g. `ask_tagged("how to blit with alpha",
   ["surface"])` or `ask_tagged("...", ["successful-example", "sprite"])` for
   known-good patterns from existing projects.
2. **Read before you write.** Use Read/Glob/Grep on the project rather than
   relying solely on knowledge retrieval — the code is the source of truth;
   the knowledge base is a lossy index of it.
3. **Run tests via `run_tests`**, not a raw shell. Failures feed back into
   the knowledge base and become retrievable next session.
4. **Lint via `lint`.** Cheap, and failures get indexed.

## Project conventions

- `<project>/.venv-mcp/` — container-owned (pytest, ruff, runtime deps).
  `install_deps` manages it. Don't touch manually.
- `<project>/.venv/` — host-owned for interactive play/distribution. Not your
  concern from inside the container.
- `requirements.txt` = runtime only (ships to end users).
- `requirements-dev.txt` = dev-only additions (optional).

Detail: `/workspace/docs/PYTHON_GENERAL.md`.

## What's not here

- No interactive display — pygame runs headless. Interactive play happens on
  the host shell, not through you.
- No process-control service. Process lifecycle is manual.
- No distribution tooling yet (PyInstaller, zipapp, etc. — open question).

## Per-project context

Look in `/workspace/docs/projects/<PROJECT>.md` for project-specific notes
before making architectural decisions. The project's own `CLAUDE.md` (if
present at `/workspace/<project>/CLAUDE.md`) takes precedence for anything
conflicting.
