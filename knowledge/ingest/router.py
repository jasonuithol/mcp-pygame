"""Ingest router: decides what to do with each tool execution payload.

Python/pygame variant. Key differences from the Valheim router:

- Tests are the primary signal, not builds. Each test node id is tracked
  independently for fail→pass transitions, instead of keying by project.
- Payloads from run_tests carry a structured pytest-json-report that we
  parse directly — no regex scraping.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING

from mcp_knowledge_base import IngestRouter

from .chunker import (
    chunk_lint_error,
    chunk_test_failure,
    chunk_test_fix,
    upsert_chunks,
)
from .extractors import extract_pytest_failures, extract_pytest_passes

if TYPE_CHECKING:
    import chromadb

logger = logging.getLogger("mcp-knowledge.router")

# Persist pending failures across container restarts
BUFFER_PATH = Path("/opt/knowledge/test_failure_buffer.json")
MAX_BUFFER_ENTRIES = 500  # plenty for per-node-id history

# Tools we skip entirely
SKIP_TOOLS = {
    "install_deps",
    "refresh_path_map",
}


class PygameIngestRouter(IngestRouter):
    """Routes incoming tool payloads to chunking/indexing logic.

    Internal state: a dict keyed by node_id with the most recent failure
    longrepr per node. Persisted to BUFFER_PATH between restarts.
    """

    def __init__(self, collection: "chromadb.Collection"):
        self.collection = collection
        self._pending_failures: dict[str, dict] = self._load_buffer()

    # ── buffer persistence ────────────────────────────────────────────────

    def _load_buffer(self) -> dict[str, dict]:
        try:
            if BUFFER_PATH.exists():
                data = json.loads(BUFFER_PATH.read_text())
                if isinstance(data, dict):
                    return data
        except Exception:
            logger.warning("Failed to load test failure buffer, starting fresh")
        return {}

    def _save_buffer(self) -> None:
        try:
            BUFFER_PATH.parent.mkdir(parents=True, exist_ok=True)
            # Trim if it's grown too large — keep most-recently-touched
            if len(self._pending_failures) > MAX_BUFFER_ENTRIES:
                items = sorted(
                    self._pending_failures.items(),
                    key=lambda kv: kv[1].get("timestamp", ""),
                    reverse=True,
                )[:MAX_BUFFER_ENTRIES]
                self._pending_failures = dict(items)
            BUFFER_PATH.write_text(json.dumps(self._pending_failures))
        except Exception:
            logger.warning("Failed to persist test failure buffer")

    # ── indexing helper ──────────────────────────────────────────────────

    def _index_chunks(self, chunks: list[dict]) -> None:
        if not chunks:
            return
        upsert_chunks(self.collection, chunks)
        logger.info("Indexed %d chunks", len(chunks))

    # ── route ────────────────────────────────────────────────────────────

    def route(self, payload: dict) -> dict:
        """Route a payload and return {action, chunks}."""
        tool = payload.get("tool", "")
        success = payload.get("success", True)
        result = payload.get("result", "")
        args = payload.get("args", {})
        timestamp = payload.get("timestamp", "")

        if tool in SKIP_TOOLS:
            return {"action": "skipped", "chunks": 0}

        if tool == "run_tests":
            return self._handle_run_tests(result, args, timestamp, success)

        if tool == "lint":
            if success:
                return {"action": "skipped_lint_clean", "chunks": 0}
            project = args.get("project", "unknown")
            chunk = chunk_lint_error(result, project)
            self._index_chunks([chunk])
            return {"action": "indexed_lint_error", "chunks": 1}

        logger.debug("Unhandled tool: %s", tool)
        return {"action": "skipped_unknown", "chunks": 0}

    # ── run_tests ────────────────────────────────────────────────────────

    def _handle_run_tests(
        self,
        result: str,
        args: dict,
        timestamp: str,
        overall_success: bool,
    ) -> dict:
        project = args.get("project", "unknown")

        # Payload is a JSON envelope: {"summary", "json_report", "stdout"}.
        # The json_report itself is a JSON string inside.
        try:
            envelope = json.loads(result) if isinstance(result, str) else result
            report_str = envelope.get("json_report", "") if isinstance(envelope, dict) else ""
        except Exception:
            report_str = ""

        if not report_str:
            logger.info("run_tests payload had no json_report; skipping")
            return {"action": "skipped_no_report", "chunks": 0}

        failures = extract_pytest_failures(report_str)
        passes = extract_pytest_passes(report_str)

        new_chunks: list[dict] = []

        # 1. Index every failure as its own chunk.
        for f in failures:
            node_id = f["node_id"]
            if not node_id:
                continue
            chunk = chunk_test_failure(
                node_id=node_id,
                longrepr=f["longrepr"],
                stdout=f.get("stdout", ""),
                project=project,
            )
            new_chunks.append(chunk)
            self._pending_failures[node_id] = {
                "project": project,
                "longrepr": f["longrepr"],
                "timestamp": timestamp,
            }

        # 2. For every passing test that has a pending failure, record a fix.
        fix_count = 0
        for node_id in passes:
            if node_id in self._pending_failures:
                pending = self._pending_failures.pop(node_id)
                fix_chunk = chunk_test_fix(
                    node_id=node_id,
                    failure_longrepr=pending.get("longrepr", ""),
                    project=pending.get("project", project),
                )
                new_chunks.append(fix_chunk)
                fix_count += 1

        self._save_buffer()
        self._index_chunks(new_chunks)

        action = (
            "indexed_test_failures_and_fixes"
            if failures and fix_count
            else "indexed_test_failures"
            if failures
            else "indexed_test_fixes"
            if fix_count
            else "skipped_routine_success"
        )
        return {"action": action, "chunks": len(new_chunks)}
