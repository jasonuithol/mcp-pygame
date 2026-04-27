# UltimatePyve

A pygame reimplementation of Ultima V, living at `~/Projects/UltimatePyve`.

## Architecture at a glance

- **Service locator / DI** via `dark_libraries.service_provider.ServiceProvider`.
  Modules register implementations through a `service_composition.compose()`
  entry point. See `service_composition.py` at the root.
- **Module tree**: `controllers/`, `data/`, `models/`, `services/`,
  `service_implementations/`, `view/`, and the shared `dark_libraries/`
  framework layer.
- **Entry point**: `main.py`. Uses `configure.py::check_python_version` and
  `get_u5_path` to locate an installed copy of Ultima V on the host.
- **Launchers**: `UltimatePyve.cmd` (Windows) and `update.cmd`.

## dark_libraries/

Reusable, project-agnostic Python scaffolding: event bus, collection helpers,
networking (both raw socket and tuple-protocol), surface wrappers, logging,
service provider / registry, math, wave helpers. Worth seeding into the
knowledge base as framework reference.

## Mods directory

`mods/` exists but mod support is rudimentary and not a core requirement yet.
Don't invest in mod tooling until it earns its keep.

## External data

- The game needs a copy of Ultima V installed on the host; `u5/` is in
  `.gitignore`. The game reads its data files from there, not from the repo.

## Distribution

Not yet decided. Options under consideration: PyInstaller, zipapp, or a
setup script that creates a venv on the user's machine. The `.venv-mcp/`
dev venv is kept namespaced so it doesn't collide with a future `.venv/`
from whichever distribution model wins.
