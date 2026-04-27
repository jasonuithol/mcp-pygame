# Python conventions for this sandbox

## Venv layout

Each project has **two** independent venvs, kept separate by name:

| Path | Owner | Python | Purpose |
|------|-------|--------|---------|
| `<project>/.venv-mcp/` | mcp-build container | Linux, 3.12 | Dev-only: pytest, ruff, pytest-json-report, runtime deps |
| `<project>/.venv/` | host / end-user | host's Python | Running the game interactively, or end-user distribution |

Both are gitignored. Never commit a venv.

The container venv has shebangs pointing at the container's Python
(`/usr/local/bin/python3.12`) and is not usable from the host. If you
want to play the game on the host, create `.venv/` yourself outside the
container.

## requirements split

- `requirements.txt` — runtime dependencies only (what ships to end users).
- `requirements-dev.txt` — dev-only additions (pytest, ruff, etc.). Optional.

`install_deps(project)` installs both if present.

## Tests

Headless pytest inside the container:

```bash
SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy \
  <project>/.venv-mcp/bin/pytest --json-report --json-report-file=/tmp/report.json <project>
```

This is what `run_tests` wraps. You don't normally call it manually.

## The `project` arg

Every MCP tool that operates on a project takes `project: str` — a folder
name under `~/Projects` (no path separators). Inside the containers it
resolves to `/opt/projects/<project>`. Don't pass absolute paths.

## Host interactive play

Create and manage `<project>/.venv/` yourself:

```bash
cd ~/Projects/<project>
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python main.py
```

The container never touches `.venv/` — that path is yours.
