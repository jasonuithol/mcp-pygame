"""Chunking logic for Python / pygame knowledge sources.

The cross-domain primitives — `tag_key`, `tag_flags`, `upsert_chunks`,
`sanitize_for_id`, `now_iso` — live in `mcp_knowledge_base.chunks` and are
re-exported here for the convenience of existing call-sites in
`router.py` / `mcp-service.py`.
"""

from __future__ import annotations

import re

from mcp_knowledge_base import (
    now_iso,
    sanitize_for_id,
    tag_flags,
    tag_key,
    upsert_chunks,
)

from .extractors import (
    detect_tags,
    extract_module_name,
    extract_top_level_nodes,
)

__all__ = [
    "chunk_python_source",
    "chunk_docs",
    "chunk_test_failure",
    "chunk_test_fix",
    "chunk_lint_error",
    # Re-exports from mcp_knowledge_base for downstream convenience
    "tag_key",
    "tag_flags",
    "upsert_chunks",
]


# ── Python source ────────────────────────────────────────────────────────────

def chunk_python_source(
    source: str,
    file_path: str,
    project: str,
    project_root: str,
    extra_tags: list[str] | None = None,
) -> list[dict]:
    """Chunk a Python file by top-level class / function.

    One chunk per class (including its methods) and per top-level function.
    Module-level statements (imports, constants) are not chunked separately —
    they'd produce noise. A file with no top-level class/function becomes a
    single chunk of its entire content.

    Args:
        source: Python source as a string.
        file_path: Absolute path to the file (used for module name + ID).
        project: Project name (goes into metadata.project and as a tag).
        project_root: Project root for computing the dotted module name.
        extra_tags: Additional tags prepended to every chunk.
    """
    extra_tags = extra_tags or []
    module = extract_module_name(file_path, project_root)
    nodes = extract_top_level_nodes(source)
    now = now_iso()
    chunks = []

    if not nodes:
        # Whole-file chunk
        tags = [*extra_tags, project.lower(), *detect_tags(source)]
        chunks.append({
            "id": f"py-source/{project}/{sanitize_for_id(module)}",
            "document": source,
            "metadata": {
                "source": f"py-source/{project}/{module}",
                "type": "module",
                "module": module,
                "class_name": "",
                "func_name": "",
                "tags": ",".join(tags),
                "indexed_at": now,
                "project": project,
            },
        })
        return chunks

    for node in nodes:
        tags = [*extra_tags, project.lower(), *detect_tags(node["body"])]
        # Tag decorators too — pytest fixtures, dataclasses, etc.
        for dec in node.get("decorators", []):
            if dec == "dataclass" or dec.endswith(".dataclass"):
                if "dataclass" not in tags:
                    tags.append("dataclass")
            if "fixture" in dec:
                if "pytest-fixture" not in tags:
                    tags.append("pytest-fixture")

        class_name = node["name"] if node["kind"] == "class" else ""
        func_name = node["name"] if node["kind"] == "function" else ""
        chunk_id = f"py-source/{project}/{sanitize_for_id(module)}/{node['kind']}/{sanitize_for_id(node['name'])}"

        chunks.append({
            "id": chunk_id,
            "document": node["body"],
            "metadata": {
                "source": f"py-source/{project}/{module}",
                "type": node["kind"],
                "module": module,
                "class_name": class_name,
                "func_name": func_name,
                "tags": ",".join(tags),
                "indexed_at": now,
                "project": project,
            },
        })

    return chunks


# ── Docs ─────────────────────────────────────────────────────────────────────

def chunk_docs(text: str, filename: str) -> list[dict]:
    """Chunk a markdown doc by ## headers."""
    sections = re.split(r"(?=^## )", text, flags=re.MULTILINE)
    now = now_iso()
    chunks = []

    for i, section in enumerate(sections):
        section = section.strip()
        if not section:
            continue

        title_match = re.match(r"^##\s+(.+)", section)
        title = title_match.group(1).strip() if title_match else f"section_{i}"
        safe_title = re.sub(r"[^a-zA-Z0-9_-]", "_", title)[:80]

        tags = detect_tags(section)
        # Filename-derived tag, e.g. PYGAME_BASICS.md -> pygame_basics
        file_tag = filename.replace(".md", "").lower()
        if file_tag and file_tag not in tags:
            tags.insert(0, file_tag)

        chunks.append({
            "id": f"docs/{filename}/{safe_title}",
            "document": section,
            "metadata": {
                "source": f"docs/{filename}",
                "type": "section",
                "module": "",
                "class_name": "",
                "func_name": "",
                "tags": ",".join(tags),
                "indexed_at": now,
                "project": "",
                **tag_flags(tags),
            },
        })

    return chunks


# ── Test failures and fixes ──────────────────────────────────────────────────

def chunk_test_failure(
    node_id: str,
    longrepr: str,
    stdout: str,
    project: str,
) -> dict:
    """One chunk for a single failing pytest test."""
    document = f"NODE: {node_id}\n\n"
    if longrepr:
        document += f"FAILURE:\n{longrepr}\n\n"
    if stdout:
        document += f"STDOUT (tail):\n{stdout[-2000:]}\n"
    tags = ["test-failure", project.lower()] + detect_tags(document)
    now = now_iso()
    sanitized = sanitize_for_id(node_id)
    return {
        "id": f"test-failure/{project}/{sanitized}/{now}",
        "document": document,
        "metadata": {
            "source": f"test-failure/{project}/{node_id}",
            "type": "error",
            "module": "",
            "class_name": "",
            "func_name": "",
            "tags": ",".join(tags),
            "indexed_at": now,
            "project": project,
            "node_id": node_id,
        },
    }


def chunk_test_fix(
    node_id: str,
    failure_longrepr: str,
    project: str,
    test_body: str = "",
) -> dict:
    """One chunk for a test-failure → test-pass transition.

    `test_body` is the current (passing) test source, if available — it's the
    clearest encoding of the fix. Without it, the chunk records only that the
    failure stopped recurring.
    """
    document = f"NODE: {node_id}\n\nFAILED WITH:\n{failure_longrepr}\n"
    if test_body:
        document += f"\nNOW PASSING. Current test source:\n{test_body}\n"
    else:
        document += "\nNOW PASSING.\n"
    tags = ["test-fix", project.lower()] + detect_tags(document)
    now = now_iso()
    sanitized = sanitize_for_id(node_id)
    return {
        "id": f"test-fix/{project}/{sanitized}/{now}",
        "document": document,
        "metadata": {
            "source": f"test-fix/{project}/{node_id}",
            "type": "pattern",
            "module": "",
            "class_name": "",
            "func_name": "",
            "tags": ",".join(tags),
            "indexed_at": now,
            "project": project,
            "node_id": node_id,
        },
    }


# ── Lint errors ──────────────────────────────────────────────────────────────

def chunk_lint_error(output: str, project: str) -> dict:
    """One chunk for a ruff failure."""
    tags = ["lint-error", project.lower()]
    now = now_iso()
    return {
        "id": f"lint-error/{project}/{now}",
        "document": output,
        "metadata": {
            "source": f"lint-error/{project}",
            "type": "error",
            "module": "",
            "class_name": "",
            "func_name": "",
            "tags": ",".join(tags),
            "indexed_at": now,
            "project": project,
        },
    }
