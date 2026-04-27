# mcp-knowledge — Python / pygame Knowledge Service

A RAG-backed MCP service that accumulates knowledge from indexing project
source, curated docs, and test failures. Runs alongside `service/`
(`pygame-mcp-build`) inside `claude-sandbox-core`'s `pygame` domain.

The Valheim-side service (`mcp-valheim/knowledge`) is this service's
sibling; both share the same scaffolding (via `mcp-knowledge-base`) but
are kept isolated — only one sandbox runs at a time.

---

## Design principle: domain-scoped collection

All pygame projects share a single ChromaDB collection: `pygame_knowledge`.
Retrieval crosses project boundaries deliberately — a pattern solved in
project A is discoverable while working in project B. Each chunk carries a
`project` metadata field, so scoped queries are still possible via
`ask_project(question, project)`.

This is the opposite decision from "one collection per project." It's
correct here because the Python/pygame domain is the unit of shared
knowledge, not any single app.

---

## Passive ingest, active query

Tool executions in `mcp-build` fire fire-and-forget POSTs to `/ingest`. The
router (`ingest/router.py`) decides what to index. See
`docs/INGEST_MCP.md` for the payload shape and routing table.

Signals we care about:

- **Test failures** (from `run_tests`) — indexed per node id, with the
  pytest-json-report's structured failure payload (exception, traceback,
  captured stdout).
- **Test fixes** — when a previously-failing test passes, a `test-fix`
  chunk pairs the old failure with the resolution timestamp. The buffer
  that tracks pending failures persists across container restarts at
  `/opt/knowledge/test_failure_buffer.json`.
- **Lint errors** (from `lint`) — indexed on failure; skipped on success.

`install_deps` is skipped — no signal worth keeping.

---

## MCP tools

### Query

| Tool | Purpose |
|------|---------|
| `ask(question)` | Semantic search across the whole collection |
| `ask_module(module)` | Filter by dotted module path (e.g. `services.display_service`) |
| `ask_tagged(question, tags)` | Filter by one or more tags — returns most relevant within that subset |
| `ask_project(question, project)` | Scope to one project |

### Maintenance

| Tool | Purpose |
|------|---------|
| `list_sources()` | Every indexed source with chunk count |
| `stats()` | Totals by project, source, type, tag |
| `forget(source)` | Delete all chunks matching a source (supports prefix, e.g. `py-source/UltimatePyve`) |
| `seed_docs(docs_path)` | Index every `.md` under a directory by `##` section |
| `seed_python_source(project, source_dir, extra_tags=[...])` | Index a Python source tree |
| `retag_all()` | Re-run tag auto-detection across every chunk |

---

## Chunking strategy

| Source | Boundary | Typical size |
|--------|----------|--------------|
| Python file | One chunk per top-level class or top-level function (via `ast`) | 20-300 lines |
| Python file (no top-level defs) | One whole-file chunk | variable |
| Markdown doc | One chunk per `## ` section | 10-100 lines |
| Test failure | One chunk per failing node id per run | small |
| Test fix | One chunk per fail→pass transition | small |

Class-level chunks keep method context together, which is what
"how does X implement Y" questions need. Function-level would be finer but
loses the class's instance state and sibling methods.

Syntax errors during ingest don't crash — `extract_top_level_nodes` returns
`[]` and the caller can decide whether to emit a whole-file chunk or skip.

---

## Metadata schema

```python
{
    "source":      "py-source/UltimatePyve/services.display_service",
    "type":        "class",                 # class | function | module | section | error | pattern
    "module":      "services.display_service",
    "class_name":  "DisplayService",        # or ""
    "func_name":   "",                      # or "", or the top-level function name
    "tags":        "surface,display,UltimatePyve,successful-example",
    "indexed_at":  "2026-04-22T08:00:00Z",
    "project":     "UltimatePyve",
    # Plus per-tag boolean keys for filtering:
    "tag_surface":             True,
    "tag_display":              True,
    "tag_ultimatepyve":         True,
    "tag_successful_example":   True,
}
```

Tag keys are normalised via `tag_key()` in `ingest/chunker.py` — lowercase,
non-alphanumeric → underscore. ChromaDB's metadata filter has no
`$contains` operator, so boolean keys are how `ask_tagged` works.

---

## Container layout

```
mcp-knowledge/
├── CLAUDE.md              ← this file
├── Dockerfile             ← CUDA base for GPU-accelerated embeddings
├── requirements.txt       ← fastmcp, chromadb, httpx, uvicorn, onnxruntime-gpu
├── build-container.sh     ← downloads (or links) the embedding model, builds image
├── start-container.sh     ← runs with --device nvidia.com/gpu=all
├── setup-gpu.sh           ← one-shot NVIDIA Container Toolkit install
├── reset-knowledge.sh     ← wipe ChromaDB and restart
├── seed.sh                ← seed docs + UltimatePyve source
├── mcp-service.py         ← FastMCP server + /ingest HTTP endpoint
├── ingest/
│   ├── chunker.py         ← Python source chunking + tag flag scaffolding
│   ├── extractors.py      ← pygame PATTERN_TAGS, ast node walker, pytest report parser
│   └── router.py          ← run_tests / lint routing, per-node-id fail→pass detection
├── models/                ← embedding model (downloaded by build-container.sh)
└── knowledge/             ← ChromaDB persistent storage (gitignored)
```

---

## Seeding workflow

First-time setup after `start-container.sh`:

```bash
./seed.sh
```

Which does:

1. `seed_docs("/opt/projects/mcp-pygame/docs")`
2. `seed_python_source("UltimatePyve", "/opt/projects/UltimatePyve")`

After that, the knowledge base grows automatically from `run_tests` and
`lint` invocations.

### Seeding the pygame source (optional)

If you want pygame-ce's source code indexed as library reference, clone it
locally and call `seed_python_source` with a `library` tag:

```bash
git clone https://github.com/pygame-community/pygame-ce ~/Projects/pygame-ce
# From inside the claude container, call:
#   seed_python_source("pygame-ce", "/opt/projects/pygame-ce",
#                      extra_tags=["library", "pygame-ce"])
```

Not automated in `seed.sh` because cloning external repos is a user choice.

---

## Known concerns

### 1. Python C extensions are invisible

pygame's hot paths are C, not Python. Indexing pygame-ce's Python source
gives you wrappers and type stubs, not the rendering code. For "how does
`blit` actually work" questions, the RAG can only point you at the public
interface.

### 2. Buffer grows without explicit eviction

The test-failure buffer is capped at 500 entries by most-recent-touched.
Heavy test churn on many unique node ids could push older still-failing
tests out before they get fixed. Bump `MAX_BUFFER_ENTRIES` in
`router.py` if this ever matters.

### 3. No deduplication on re-seed

`seed_python_source` uses deterministic IDs
(`py-source/{project}/{module}/{kind}/{name}`), so re-seeding the same tree
*upserts* rather than duplicating. But if a class is renamed or deleted,
the old chunk sits in the index until explicitly forgotten. Run
`forget("py-source/<project>")` before re-seeding a refactored project.

### 4. Flakiness is not filtered

Every failure is indexed, per the explicit "hoover up mistakes" call. If a
flaky test pollutes retrieval, the mitigation is post-hoc:
`ask_tagged(..., ["test-fix"])` restricts to high-signal fix pairs, which
are far less likely to be flaky artefacts.

---

## Non-goals

- Not a replacement for the curated `docs/*.md` reference — those
  remain the human-reviewed source of truth.
- Not a general-purpose knowledge base — scoped to pygame / Python
  gamedev. Other Python domains (Django, FastAPI, etc.) would warrant
  their own sandbox.
- No fine-tuning or model training — pure retrieval.
