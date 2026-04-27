# Ingest pipeline — mcp-build → mcp-knowledge

Every tool execution in `mcp-build` fires a fire-and-forget HTTP POST to
`http://localhost:5174/ingest` with this payload:

```json
{
    "tool": "run_tests",
    "args": {"project": "UltimatePyve"},
    "result": "<pytest JSON report or plaintext>",
    "success": false,
    "timestamp": "2026-04-22T07:45:00Z",
    "service": "mcp-build"
}
```

mcp-knowledge's router (`ingest/router.py`) decides what to do:

| tool | success | Action |
|------|---------|--------|
| `run_tests` | false | Parse pytest JSON, index each failing test as a chunk keyed by node id, tag `test-failure` |
| `run_tests` | true | For each passing test that has a recent failure in the buffer, index a `test-fix` pair |
| `lint` | false | Index the ruff output, tag `lint-error` |
| `lint` | true | Skip (routine) |
| `install_deps` | any | Skip — no knowledge value |

## Design rules

- **mcp-build never blocks on mcp-knowledge.** The reporter
  (`mcp_knowledge_base.KnowledgeReporter`) uses a 5 second timeout and
  swallows exceptions. If the knowledge service is down, builds and
  tests still work.
- **mcp-build never decides what's worth indexing.** It sends everything;
  mcp-knowledge filters via the router.
- **Tests are the Python analogue of Valheim's build errors.** Failure
  payloads carry structured signal (pytest JSON: node id, file, line,
  exception, traceback, stdout) — much richer than a single-line compiler
  error. The router parses the JSON directly rather than regexing text.

## Buffer keying

Unlike Valheim (keys by `project` to detect build fail → fix), Python tests
key by `node id` (`tests/test_foo.py::test_bar`). Each test has its own
fail/fix history. The buffer persists at `/opt/knowledge/buffer.json`.
