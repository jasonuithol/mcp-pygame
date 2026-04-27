#!/usr/bin/env python3
"""
mcp-service.py — pygame-build

Runs inside a Docker container. Exposes Python/pygame build + test tools to
Claude Code.

Register with Claude Code (run this inside the claude-sandbox-core container):
    claude mcp add pygame-build --transport http http://localhost:5172/mcp
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path

from fastmcp import FastMCP
from mcp_knowledge_base import KnowledgeReporter

# ── Config ────────────────────────────────────────────────────────────────────

PROJECTS_DIR = Path(os.environ.get("PROJECTS_DIR", "/opt/projects"))
VENV_DIRNAME = os.environ.get("VENV_DIRNAME", ".venv-mcp")

# Tools that always belong in .venv-mcp so run_tests / lint have something to call.
# These are installed automatically by install_deps regardless of whether the project
# listed them in requirements-dev.txt.
DEV_BASELINE = ["pytest", "pytest-json-report", "ruff"]

# ── Knowledge reporter ────────────────────────────────────────────────────────

_reporter = KnowledgeReporter(service="mcp-build")
_report = _reporter.report


# ── Venv helpers ──────────────────────────────────────────────────────────────

def _project_dir(project: str) -> Path:
    if not project or "/" in project or ".." in project:
        raise ValueError(f"Invalid project name: {project!r}")
    d = PROJECTS_DIR / project
    if not d.is_dir():
        raise FileNotFoundError(f"Project directory not found: {d}")
    return d


def _venv_dir(project: str) -> Path:
    return _project_dir(project) / VENV_DIRNAME


def _venv_python(project: str) -> Path:
    return _venv_dir(project) / "bin" / "python"


def _ensure_venv(project: str) -> tuple[bool, str]:
    """Create .venv-mcp if missing. Returns (created, log_text)."""
    vd = _venv_dir(project)
    if vd.exists():
        return False, f"venv already exists at {vd}"
    vd.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [sys.executable, "-m", "venv", str(vd)],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"venv creation failed:\nstdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
        )
    return True, f"created venv at {vd}\n{proc.stdout}"


# ── Subprocess helpers ────────────────────────────────────────────────────────

def _run(
    cmd: list[str],
    cwd: str | None = None,
    env: dict | None = None,
) -> tuple[bool, str]:
    """Run a command synchronously, capture combined stdout+stderr."""
    full_env = os.environ.copy()
    if env:
        full_env.update(env)
    proc = subprocess.run(
        cmd,
        cwd=cwd,
        env=full_env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    return proc.returncode == 0, proc.stdout


async def _run_async(
    cmd: list[str],
    cwd: str | None = None,
    env: dict | None = None,
) -> tuple[bool, str]:
    return await asyncio.to_thread(_run, cmd, cwd, env)


# ── MCP server ────────────────────────────────────────────────────────────────

mcp = FastMCP(
    name="pygame-build",
    instructions=(
        "Tools for installing deps, running tests, and linting Python/pygame "
        "projects. Tests run headless via SDL_VIDEODRIVER=dummy. Each project "
        "has its own container-managed venv at <project>/.venv-mcp. Test "
        "failures and lint errors are automatically reported to mcp-knowledge."
    ),
)


# ── install_deps ──────────────────────────────────────────────────────────────

@mcp.tool()
async def install_deps(project: str) -> str:
    """
    Create `.venv-mcp/` if missing and install project dependencies.

    Installs `requirements.txt` (if present), `requirements-dev.txt` (if present),
    plus the dev baseline (pytest, pytest-json-report, ruff) so run_tests and
    lint have something to invoke.

    Idempotent — re-running syncs any new deps.

    Args:
        project: Folder name under ~/Projects (no path separators).
    """
    try:
        _project_dir(project)
    except Exception as e:
        result = f"FAILED\n\n{e}"
        _report("install_deps", {"project": project}, result, False)
        return result

    lines = []
    try:
        created, log = _ensure_venv(project)
        lines.append(log)
    except Exception as e:
        result = f"FAILED\n\n{e}"
        _report("install_deps", {"project": project}, result, False)
        return result

    pip = str(_venv_python(project))
    pd = _project_dir(project)

    # Upgrade pip first
    ok, out = await _run_async([pip, "-m", "pip", "install", "-U", "pip"])
    lines.append(f"-- pip upgrade ({'ok' if ok else 'failed'}) --\n{out}")
    if not ok:
        result = "INSTALL_DEPS FAILED\n\n" + "\n\n".join(lines)
        _report("install_deps", {"project": project}, result, False)
        return result

    # requirements.txt (runtime)
    req = pd / "requirements.txt"
    if req.exists():
        ok, out = await _run_async([pip, "-m", "pip", "install", "-r", str(req)])
        lines.append(f"-- requirements.txt ({'ok' if ok else 'failed'}) --\n{out}")
        if not ok:
            result = "INSTALL_DEPS FAILED\n\n" + "\n\n".join(lines)
            _report("install_deps", {"project": project}, result, False)
            return result

    # requirements-dev.txt (optional)
    req_dev = pd / "requirements-dev.txt"
    if req_dev.exists():
        ok, out = await _run_async([pip, "-m", "pip", "install", "-r", str(req_dev)])
        lines.append(f"-- requirements-dev.txt ({'ok' if ok else 'failed'}) --\n{out}")
        if not ok:
            result = "INSTALL_DEPS FAILED\n\n" + "\n\n".join(lines)
            _report("install_deps", {"project": project}, result, False)
            return result

    # Dev baseline
    ok, out = await _run_async([pip, "-m", "pip", "install", *DEV_BASELINE])
    lines.append(f"-- dev baseline ({'ok' if ok else 'failed'}) --\n{out}")
    if not ok:
        result = "INSTALL_DEPS FAILED\n\n" + "\n\n".join(lines)
        _report("install_deps", {"project": project}, result, False)
        return result

    result = "INSTALL_DEPS SUCCEEDED ✓\n\n" + "\n\n".join(lines)
    _report("install_deps", {"project": project}, result, True)
    return result


# ── run_tests ─────────────────────────────────────────────────────────────────

@mcp.tool()
async def run_tests(project: str, test_filter: str = "") -> str:
    """
    Run pytest inside the project's .venv-mcp with headless SDL.

    Generates a pytest-json-report and fires it (plus plaintext stdout) to
    mcp-knowledge. Returns a concise summary to the caller.

    Args:
        project: Folder name under ~/Projects.
        test_filter: Optional pytest path/filter, e.g. 'tests/test_foo.py::test_bar'
                     or 'tests/ -k "physics"'. Empty = run all tests.
    """
    try:
        pd = _project_dir(project)
    except Exception as e:
        result = f"RUN_TESTS FAILED\n\n{e}"
        _report("run_tests", {"project": project, "test_filter": test_filter}, result, False)
        return result

    py = _venv_python(project)
    if not py.exists():
        result = (
            f"RUN_TESTS FAILED\n\n"
            f"No venv found at {_venv_dir(project)}. "
            f"Run install_deps('{project}') first."
        )
        _report("run_tests", {"project": project, "test_filter": test_filter}, result, False)
        return result

    report_path = Path(f"/tmp/{project}-pytest-report.json")
    report_path.unlink(missing_ok=True)

    cmd = [
        str(py), "-m", "pytest",
        f"--json-report",
        f"--json-report-file={report_path}",
        "-v",
    ]
    if test_filter:
        # Split on whitespace so "tests/ -k foo" works as a filter
        cmd += test_filter.split()

    env = {
        "SDL_VIDEODRIVER": "dummy",
        "SDL_AUDIODRIVER": "dummy",
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    ok, stdout = await _run_async(cmd, cwd=str(pd), env=env)

    # Read JSON report if pytest managed to write one (it writes even on failure)
    report_json = ""
    if report_path.exists():
        try:
            report_json = report_path.read_text()
        except Exception:
            pass

    # Summary for the caller
    summary_lines = []
    if report_json:
        try:
            r = json.loads(report_json)
            s = r.get("summary", {})
            summary_lines.append(
                f"total={s.get('total', 0)} "
                f"passed={s.get('passed', 0)} "
                f"failed={s.get('failed', 0)} "
                f"errors={s.get('errors', 0)} "
                f"skipped={s.get('skipped', 0)} "
                f"duration={r.get('duration', 0):.2f}s"
            )
            # List failing node ids
            failed = [t for t in r.get("tests", []) if t.get("outcome") == "failed"]
            if failed:
                summary_lines.append("\nFailures:")
                for t in failed[:20]:
                    summary_lines.append(f"  {t['nodeid']}")
                if len(failed) > 20:
                    summary_lines.append(f"  ... and {len(failed) - 20} more")
        except Exception as e:
            summary_lines.append(f"(failed to parse json report: {e})")
    else:
        summary_lines.append("(no json report produced — pytest may have failed before running)")

    header = "TESTS PASSED ✓" if ok else "TESTS FAILED ✗"
    summary = f"{header}\n\n" + "\n".join(summary_lines)

    # Send the FULL json report + stdout to ingest so the router has structured
    # data to work with. Caller only sees the summary to keep response size down.
    ingest_payload = json.dumps({
        "summary": summary,
        "json_report": report_json,
        "stdout": stdout[-8000:],  # trim long stdout
    })
    _report("run_tests", {"project": project, "test_filter": test_filter}, ingest_payload, ok)

    # Show a bit of stdout in the response too — helps when json report is empty
    tail = stdout[-2000:] if stdout else ""
    return f"{summary}\n\n--- pytest stdout (tail) ---\n{tail}"


# ── lint ──────────────────────────────────────────────────────────────────────

@mcp.tool()
async def lint(project: str) -> str:
    """
    Run `ruff check` against the project. Reports failures to mcp-knowledge.

    Args:
        project: Folder name under ~/Projects.
    """
    try:
        pd = _project_dir(project)
    except Exception as e:
        result = f"LINT FAILED\n\n{e}"
        _report("lint", {"project": project}, result, False)
        return result

    py = _venv_python(project)
    if not py.exists():
        result = (
            f"LINT FAILED\n\n"
            f"No venv found at {_venv_dir(project)}. "
            f"Run install_deps('{project}') first."
        )
        _report("lint", {"project": project}, result, False)
        return result

    ok, out = await _run_async([str(py), "-m", "ruff", "check", "."], cwd=str(pd))
    header = "LINT CLEAN ✓" if ok else "LINT FAILED ✗"
    result = f"{header}\n\n{out}"
    _report("lint", {"project": project}, result, ok)
    return result


# ── Entrypoint ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print(f"PROJECTS_DIR={PROJECTS_DIR}")
    print(f"VENV_DIRNAME={VENV_DIRNAME}")
    print(f"KNOWLEDGE_URL={_reporter.url}")
    print("Starting pygame-build MCP on http://0.0.0.0:5172")
    print()
    print("Register with Claude Code:")
    print("  claude mcp add pygame-build --transport http http://localhost:5172/mcp")
    print()
    mcp.run(transport="streamable-http", host="0.0.0.0", port=5172)
