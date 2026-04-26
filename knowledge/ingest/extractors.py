"""Source-specific extraction for Python / pygame knowledge."""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path

# Patterns that indicate interesting systems in Python / pygame code
PATTERN_TAGS: list[tuple[re.Pattern, str]] = [
    # pygame surface + rect
    (re.compile(r"\bSurface\b|pygame\.Surface|get_surface"), "surface"),
    (re.compile(r"\bRect\b|pygame\.Rect|get_rect"), "rect"),
    (re.compile(r"\.blit\(|blits\("), "blit"),
    (re.compile(r"pygame\.draw\.|draw_rect|draw_line|draw_circle"), "draw"),
    (re.compile(r"pygame\.transform|\.scale\(|\.rotate\(|\.flip\("), "transform"),

    # events + input
    (re.compile(r"pygame\.event|event\.get\(|event\.poll\(|event\.post\("), "event"),
    (re.compile(r"\bK_[A-Z0-9_]+\b|pygame\.KEYDOWN|pygame\.KEYUP|pygame\.key\."), "input-keyboard"),
    (re.compile(r"pygame\.MOUSEBUTTONDOWN|pygame\.MOUSEMOTION|pygame\.mouse\."), "input-mouse"),
    (re.compile(r"pygame\.joystick|JOY(?:BUTTON|AXIS|HAT)"), "input-joystick"),

    # display + timing
    (re.compile(r"pygame\.display|display\.set_mode|display\.flip|display\.update"), "display"),
    (re.compile(r"pygame\.time\.Clock|\.tick\(|get_ticks\("), "clock"),

    # sprites
    (re.compile(r"pygame\.sprite|\bSprite\b|\bGroup\b|sprite\.Group|spritecollide"), "sprite"),

    # audio
    (re.compile(r"pygame\.mixer|\.Sound\(|\.Music\(|music\.load|music\.play"), "audio"),

    # assets
    (re.compile(r"pygame\.image|image\.load|pygame\.font|font\.Font"), "asset-loading"),

    # generic Python: concurrency + patterns
    (re.compile(r"\basyncio\b|async\s+def|\bawait\b"), "async"),
    (re.compile(r"\bthreading\b|Thread\(|\bLock\(|\bRLock\("), "threading"),
    (re.compile(r"@dataclass|@dataclasses\."), "dataclass"),
    (re.compile(r"typing\.Protocol|Protocol\)"), "protocol"),
    (re.compile(r"from\s+abc\s+import|ABC\)|abstractmethod"), "abc"),
    (re.compile(r"@pytest\.fixture|@fixture"), "pytest-fixture"),

    # project idioms from UltimatePyve
    (re.compile(r"ServiceProvider|service_provider|service_composition"), "service-locator"),
    (re.compile(r"dark_events|EventBus|event_bus"), "event-bus"),
]


def detect_tags(text: str) -> list[str]:
    """Scan text for known patterns and return matching tags (deduped, preserving order)."""
    tags = []
    seen = set()
    for pattern, tag in PATTERN_TAGS:
        if tag in seen:
            continue
        if pattern.search(text):
            tags.append(tag)
            seen.add(tag)
    return tags


# ── Python source structure (ast-based) ───────────────────────────────────────

def extract_top_level_nodes(source: str) -> list[dict]:
    """Return one dict per top-level class or function from a Python source string.

    Each dict: {name, kind, body, start_line, decorators}

    Silently returns [] on syntax errors — don't crash on WIP code.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    lines = source.split("\n")
    out = []
    for node in tree.body:
        if not isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        kind = "class" if isinstance(node, ast.ClassDef) else "function"
        # Include decorators: they start a line before the def/class line
        start_line = (
            min([d.lineno for d in node.decorator_list]) - 1
            if node.decorator_list
            else node.lineno - 1
        )
        end_line = node.end_lineno or start_line + 1
        body = "\n".join(lines[start_line:end_line]).rstrip()
        out.append({
            "name": node.name,
            "kind": kind,
            "body": body,
            "start_line": start_line,
            "decorators": [_decorator_name(d) for d in node.decorator_list],
        })
    return out


def _decorator_name(node: ast.expr) -> str:
    """Best-effort name for a decorator node."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return _decorator_name(node.value) + "." + node.attr
    if isinstance(node, ast.Call):
        return _decorator_name(node.func)
    return "<decorator>"


def extract_module_name(source_path: str, project_root: str) -> str:
    """Derive dotted module name from a file path relative to its project root.

    e.g. /opt/projects/UltimatePyve/services/display_service.py
         + /opt/projects/UltimatePyve
         -> services.display_service
    """
    try:
        p = Path(source_path).resolve()
        root = Path(project_root).resolve()
        rel = p.relative_to(root)
    except (ValueError, OSError):
        return Path(source_path).stem
    parts = list(rel.with_suffix("").parts)
    # Drop __init__ — the package IS the module path
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts) or Path(source_path).stem


# ── Traceback extraction ──────────────────────────────────────────────────────

def extract_tracebacks(text: str) -> list[dict]:
    """Extract Python tracebacks from arbitrary text output.

    Returns a list of {exception, message, frames, raw} dicts. `frames` is a
    list of {file, line, func}.
    """
    results = []
    # Split on the start of each traceback, keeping each block together.
    parts = re.split(r"(?=Traceback \(most recent call last\):)", text)
    for part in parts:
        if not part.startswith("Traceback"):
            continue
        frames = []
        exception_type = ""
        exception_msg = ""
        file_re = re.compile(r"^\s+File \"(.+?)\", line (\d+), in (.+?)\s*$")
        # Walk lines looking for frame lines; the exception line is the last
        # non-indented line before the next "Traceback" (or EOF).
        for line in part.split("\n"):
            m = file_re.match(line)
            if m:
                frames.append({
                    "file": m.group(1),
                    "line": int(m.group(2)),
                    "func": m.group(3),
                })
                continue
            # Unindented line that isn't the header — candidate exception
            if line and not line.startswith(" ") and not line.startswith("Traceback"):
                # e.g. "ValueError: something went wrong"
                em = re.match(r"([\w.]+)(?:\s*:\s*(.*))?\s*$", line)
                if em:
                    exception_type = em.group(1)
                    exception_msg = em.group(2) or ""
        if exception_type or frames:
            results.append({
                "exception": exception_type,
                "message": exception_msg,
                "frames": frames,
                "raw": part.rstrip(),
            })
    return results


# ── pytest-json-report extraction ─────────────────────────────────────────────

def extract_pytest_failures(report_json_str: str) -> list[dict]:
    """Parse a pytest-json-report payload; return structured failure info.

    Each returned dict has:
      node_id, outcome, duration, phase (setup|call|teardown),
      longrepr (the failure message/traceback text), stdout, stderr.
    """
    try:
        r = json.loads(report_json_str) if isinstance(report_json_str, str) else report_json_str
    except Exception:
        return []

    failures = []
    for test in r.get("tests", []):
        if test.get("outcome") not in ("failed", "error"):
            continue
        # Pick the phase that actually failed
        longrepr = ""
        failed_phase = ""
        for phase in ("setup", "call", "teardown"):
            p = test.get(phase, {})
            if p.get("outcome") in ("failed", "error") and p.get("longrepr"):
                longrepr = p["longrepr"]
                failed_phase = phase
                break
        call = test.get("call", {})
        failures.append({
            "node_id": test.get("nodeid", ""),
            "outcome": test.get("outcome", "failed"),
            "duration": test.get("duration", 0),
            "phase": failed_phase,
            "longrepr": longrepr,
            "stdout": call.get("stdout", ""),
            "stderr": call.get("stderr", ""),
        })
    return failures


def extract_pytest_passes(report_json_str: str) -> list[str]:
    """Return node ids that passed in a pytest-json-report."""
    try:
        r = json.loads(report_json_str) if isinstance(report_json_str, str) else report_json_str
    except Exception:
        return []
    return [t.get("nodeid", "") for t in r.get("tests", []) if t.get("outcome") == "passed"]
