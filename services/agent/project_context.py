"""
Deterministic project context, built without an LLM call.

Injected once at the start of every turn. Without it the agent has no grounding
and rediscovers the workspace from scratch — a single observed turn spent ten
tool calls on `pwd`, `ls -la`, `cat package.json`, `test -f ...` and `find`
before doing any work. Worse, an earlier turn grepped for "*.js" in a
TypeScript project, found nothing, concluded the workspace was empty, and
converted a Next.js App Router app to Create React App.

This is pure file reading. It costs nothing and it is part of the STATIC tier
of the context model (see PHASE_6 §6C.0.2), so it sits in the cached prefix.
"""
import json
import logging
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger("RunnerIDE-ProjectContext")

# Read into context verbatim, the way Codex and Claude Code treat AGENTS.md.
AGENT_DOC_NAMES = ("AGENTS.md", "CLAUDE.md")
MAX_DOC_CHARS = 8000

IGNORED_DIRS = {"node_modules", ".git", ".next", "dist", "build", "__pycache__", ".venv", "venv"}


def _detect_framework(deps: dict) -> str:
    """Framework from dependencies, not from guessing at file extensions."""
    if "next" in deps:
        return "Next.js"
    if "react-scripts" in deps:
        return "Create React App"
    if "vite" in deps:
        return "Vite"
    if "@angular/core" in deps:
        return "Angular"
    if "vue" in deps:
        return "Vue"
    if "svelte" in deps:
        return "Svelte"
    if "express" in deps or "fastify" in deps:
        return "Node server"
    if "react" in deps:
        return "React"
    return "unknown"


def _router_style(root: Path) -> Optional[str]:
    """
    App Router vs Pages Router. Getting this wrong breaks the build — an agent
    that writes pages/index.js into an App Router project leaves two routes
    claiming "/".
    """
    has_app = (root / "app").is_dir()
    has_pages = (root / "pages").is_dir()
    if has_app and has_pages:
        return "BOTH app/ and pages/ exist — this is a conflict and should be reported, not added to"
    if has_app:
        return "App Router (app/)"
    if has_pages:
        return "Pages Router (pages/)"
    return None


def build(workspace_dir: Path) -> str:
    """Render the <project_context> block. Never raises — returns a minimal
    block on any failure, because failing to build context must not fail a turn."""
    try:
        return _build(workspace_dir)
    except Exception as e:  # pragma: no cover
        logger.warning(f"Failed to build project context: {e}")
        return "<project_context>\n  Unavailable.\n</project_context>"


def _build(workspace_dir: Path) -> str:
    root = Path(workspace_dir)
    lines: List[str] = ["<project_context>"]

    # Stated explicitly because the agent otherwise guesses. An observed turn
    # ran `cd /workspace && npm run build` — a path that does not exist — so the
    # build and lint both failed silently, and the agent then reported the
    # changes as verified. Every shell command already runs with the workspace
    # as its cwd, so any `cd` is not just unnecessary but actively harmful.
    lines.append("  working directory: the workspace root (all commands already run here)")
    lines.append("  paths: use paths RELATIVE to the workspace root. Never use absolute")
    lines.append("         paths and never `cd` — there is no /workspace directory.")

    entries = sorted(
        p.name + ("/" if p.is_dir() else "")
        for p in root.iterdir()
        if p.name not in IGNORED_DIRS and not p.name.startswith(".")
    ) if root.is_dir() else []

    if not entries:
        lines.append("  The workspace is EMPTY. There is no existing project.")
        lines.append("</project_context>")
        return "\n".join(lines)

    pkg_path = root / "package.json"
    if pkg_path.is_file():
        try:
            pkg = json.loads(pkg_path.read_text())
        except json.JSONDecodeError:
            pkg = {}
        deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}

        lines.append(f"  name: {pkg.get('name', 'unnamed')}")
        lines.append(f"  framework: {_detect_framework(deps)}")

        router = _router_style(root)
        if router:
            lines.append(f"  router: {router}")

        lines.append(f"  typescript: {'yes' if (root / 'tsconfig.json').is_file() else 'no'}")

        scripts = pkg.get("scripts", {})
        if scripts:
            lines.append(f"  scripts: {', '.join(sorted(scripts))}")

        pm = "npm"
        if (root / "pnpm-lock.yaml").is_file():
            pm = "pnpm"
        elif (root / "yarn.lock").is_file():
            pm = "yarn"
        lines.append(f"  package manager: {pm}")
        lines.append(f"  dependencies installed: {'yes' if (root / 'node_modules').is_dir() else 'NO — run install first'}")
    else:
        lines.append("  No package.json at the workspace root — this is not a Node project.")

    lines.append(f"  top level: {', '.join(entries[:25])}")

    # State how this project runs, so the agent does not invent a command. It
    # previously guessed `npm run dev` and variations of it, which is wrong for
    # Express, Flask, Go, and a plain index.html.
    try:
        from services.workspace_manager import run_config
        cfg = run_config.resolve(root)
        lines.append(f"  run command: {cfg.command}  (port {cfg.port}, from {cfg.source})")
        if cfg.needs_install and cfg.install_command:
            lines.append(f"  ⚠ dependencies NOT installed — run `{cfg.install_command}` first")
        for w in cfg.warnings:
            lines.append(f"  ⚠ {w}")
        if cfg.cwd != root:
            lines.append(f"  project directory: {cfg.cwd.name}/")
    except Exception as e:
        lines.append(f"  run command: undetermined — {e}")

    for doc in AGENT_DOC_NAMES:
        p = root / doc
        if p.is_file():
            content = p.read_text()[:MAX_DOC_CHARS]
            lines.append(f"\n  --- {doc} ---\n{content}")

    lines.append("</project_context>")
    lines.append(
        "\nThis is accurate as of the start of this turn. Do not spend tool calls "
        "rediscovering it. Never scaffold a new project when a package.json already "
        "exists, and never change the framework or router unless explicitly asked."
    )
    return "\n".join(lines)
