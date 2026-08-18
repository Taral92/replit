"""
Resolves how a project is started and previewed.

The problem this replaces: the dev-server manager hardcoded `npm run dev` and
refused to start anything without a package.json. That made the preview pane a
Next.js feature rather than a workspace feature — an Express API, a Flask app,
a Go binary, or a plain index.html could not be run or previewed at all, and
each new stack would have needed its own branch in the server manager.

The fix is one concept, not N branches: a project declares (or we detect) a run
command, a port, and a kind. Everything downstream consumes that. This is the
same approach Replit takes with `.replit`, and it is why adding a language there
is a config change rather than a code change.

Resolution order, most authoritative first:
  1. an explicit `runnerid.json` in the project directory
  2. detection from package.json scripts
  3. detection from language manifests (Python, Go, Rust)
  4. a static directory containing index.html
"""
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("RunnerIDE-RunConfig")

CONFIG_FILENAME = "runnerid.json"

# Preference order when a package.json has several plausible scripts. `dev`
# first because it implies hot reload; `start` before `serve` because it is the
# npm convention.
SCRIPT_PREFERENCE = ("dev", "start", "serve", "develop")

# Default ports by framework, used only when nothing else tells us. The port a
# process actually binds is authoritative — see PortResolution below.
FRAMEWORK_PORTS = {
    "next": 3000,
    "vite": 5173,
    "react-scripts": 3000,
    "nuxt": 3000,
    "astro": 4321,
    "remix": 3000,
    "svelte": 5173,
    "express": 3000,
    "fastify": 3000,
    "flask": 5000,
    "django": 8000,
    "fastapi": 8000,
    "static": 8080,
}

IGNORED_DIRS = {"node_modules", ".git", ".next", "dist", "build", "__pycache__", ".venv", "venv"}


class RunConfigError(Exception):
    """Raised when a project cannot be started and the reason is actionable."""


@dataclass
class RunConfig:
    command: str
    port: int
    kind: str                    # "server" | "static" | "script"
    cwd: Path
    framework: str = "unknown"
    source: str = "detected"     # "runnerid.json" | "package.json" | "manifest" | "static"
    install_command: Optional[str] = None
    needs_install: bool = False
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "command": self.command,
            "port": self.port,
            "kind": self.kind,
            "cwd": str(self.cwd),
            "framework": self.framework,
            "source": self.source,
            "install_command": self.install_command,
            "needs_install": self.needs_install,
            "warnings": self.warnings,
        }

    def describe(self) -> str:
        line = f"{self.command} (port {self.port}, {self.framework})"
        if self.needs_install and self.install_command:
            line += f" — dependencies missing, run `{self.install_command}` first"
        return line


def _detect_framework(deps: Dict[str, Any]) -> str:
    for name in ("next", "vite", "react-scripts", "nuxt", "astro", "remix",
                 "express", "fastify", "svelte"):
        if name in deps:
            return name
    return "node"


def _from_config_file(root: Path) -> Optional[RunConfig]:
    """An explicit runnerid.json always wins. Detection is a fallback, not a policy."""
    path = root / CONFIG_FILENAME
    if not path.is_file():
        return None
    try:
        raw = json.loads(path.read_text())
    except json.JSONDecodeError as e:
        raise RunConfigError(f"{CONFIG_FILENAME} is not valid JSON: {e}")

    command = raw.get("run") or raw.get("command")
    if not command:
        raise RunConfigError(f'{CONFIG_FILENAME} must contain a "run" field.')

    return RunConfig(
        command=str(command),
        port=int(raw.get("port", 3000)),
        kind=str(raw.get("kind", "server")),
        cwd=root,
        framework=str(raw.get("framework", "custom")),
        source=CONFIG_FILENAME,
        install_command=raw.get("install"),
        needs_install=False,
    )


def _from_package_json(root: Path) -> Optional[RunConfig]:
    path = root / "package.json"
    if not path.is_file():
        return None
    try:
        pkg = json.loads(path.read_text())
    except json.JSONDecodeError as e:
        raise RunConfigError(f"package.json is not valid JSON: {e}")

    scripts = pkg.get("scripts") or {}
    deps = {**(pkg.get("dependencies") or {}), **(pkg.get("devDependencies") or {})}
    framework = _detect_framework(deps)

    # Package manager follows the lockfile, not a guess. Running npm in a pnpm
    # project produces a second, conflicting lockfile.
    if (root / "pnpm-lock.yaml").is_file():
        pm, install = "pnpm", "pnpm install"
    elif (root / "yarn.lock").is_file():
        pm, install = "yarn", "yarn install"
    else:
        pm, install = "npm", "npm install"

    script = next((s for s in SCRIPT_PREFERENCE if s in scripts), None)
    warnings: List[str] = []

    # A tsconfig.json with no typescript dependency is a fatal Next.js startup
    # error ("It looks like you're trying to use TypeScript but do not have the
    # required package(s) installed"), and it happens constantly: the agent
    # scaffolds a tsconfig and forgets the devDependencies. The message Next
    # prints reads like a project problem rather than a missing install, so
    # catch it here where the cause is unambiguous.
    if (root / "tsconfig.json").is_file():
        missing = [p for p in ("typescript", "@types/react", "@types/node") if p not in deps]
        if missing:
            warnings.append(
                f"tsconfig.json exists but {', '.join(missing)} "
                f"{'is' if len(missing) == 1 else 'are'} not in package.json. "
                f"Either run `{'npm' if (root / 'package-lock.json').is_file() or True else 'npm'} "
                f"install -D {' '.join(missing)}`, or delete tsconfig.json if the "
                f"project is plain JavaScript."
            )

    if script:
        command = f"{pm} run {script}" if pm == "npm" else f"{pm} {script}"
    else:
        main = pkg.get("main")
        if not main:
            raise RunConfigError(
                f"package.json has no dev/start/serve script and no 'main' entry, "
                f"so there is no way to know how to run this project. "
                f"Add a script, or create a {CONFIG_FILENAME} with a \"run\" field."
            )
        command = f"node {main}"
        warnings.append(f"No start script found; falling back to `node {main}`.")

    return RunConfig(
        command=command,
        port=FRAMEWORK_PORTS.get(framework, 3000),
        kind="server",
        cwd=root,
        framework=framework,
        source="package.json",
        install_command=install,
        needs_install=not (root / "node_modules").is_dir(),
        warnings=warnings,
    )


def _from_manifest(root: Path) -> Optional[RunConfig]:
    """Python, Go and Rust. Detected from manifests rather than file extensions."""
    if (root / "manage.py").is_file():
        return RunConfig("python3 manage.py runserver 0.0.0.0:8000", 8000, "server",
                         root, "django", "manifest", "pip install -r requirements.txt")

    for entry, fw, port in (("app.py", "flask", 5000), ("main.py", "fastapi", 8000)):
        if (root / entry).is_file():
            text = (root / entry).read_text(errors="replace")[:4000].lower()
            if "fastapi" in text:
                mod = entry[:-3]
                return RunConfig(f"uvicorn {mod}:app --host 0.0.0.0 --port 8000", 8000,
                                 "server", root, "fastapi", "manifest",
                                 "pip install -r requirements.txt")
            if "flask" in text:
                return RunConfig(f"python3 {entry}", 5000, "server", root, "flask",
                                 "manifest", "pip install -r requirements.txt")

    if (root / "go.mod").is_file():
        return RunConfig("go run .", 8080, "server", root, "go", "manifest")
    if (root / "Cargo.toml").is_file():
        return RunConfig("cargo run", 8080, "server", root, "rust", "manifest")
    return None


def _from_static(root: Path) -> Optional[RunConfig]:
    """
    A directory with an index.html and no manifest. Previously unreachable —
    the server manager refused anything without package.json, so the single
    simplest case ("just show me this page") was the one thing it could not do.
    """
    if not (root / "index.html").is_file():
        return None
    return RunConfig("python3 -m http.server 8080", 8080, "static", root, "static", "static")


def _candidate_roots(workspace_dir: Path) -> List[Path]:
    """
    The workspace root, then immediate subdirectories.

    Nested projects are supported because agents habitually scaffold into a
    subfolder (`create-next-app todo-app`), but the root is checked first so an
    in-place project always wins.
    """
    roots = [workspace_dir]
    try:
        roots.extend(
            sorted(
                p for p in workspace_dir.iterdir()
                if p.is_dir() and p.name not in IGNORED_DIRS and not p.name.startswith(".")
            )
        )
    except OSError:
        pass
    return roots


def resolve(workspace_dir: Path, cwd: Optional[str] = None) -> RunConfig:
    """
    Resolve the run configuration, or raise RunConfigError with an actionable
    message. Never returns a guess dressed up as a certainty.
    """
    workspace_dir = Path(workspace_dir)

    if cwd:
        root = (workspace_dir / cwd).resolve()
        if not str(root).startswith(str(workspace_dir.resolve())):
            raise RunConfigError(f"cwd '{cwd}' is outside the workspace.")
        if not root.is_dir():
            raise RunConfigError(f"cwd '{cwd}' does not exist.")
        roots = [root]
    else:
        roots = _candidate_roots(workspace_dir)

    detectors = (_from_config_file, _from_package_json, _from_manifest, _from_static)
    found: List[RunConfig] = []

    for root in roots:
        for detect in detectors:
            cfg = detect(root)
            if cfg:
                # First detector to match at the workspace root wins outright.
                if root == workspace_dir:
                    logger.info(f"Run config: {cfg.describe()} [{cfg.source}]")
                    return cfg
                found.append(cfg)
                break

    if len(found) == 1:
        logger.info(f"Run config in {found[0].cwd.name}/: {found[0].describe()}")
        return found[0]

    if len(found) > 1:
        names = ", ".join(c.cwd.name for c in found)
        raise RunConfigError(
            f"Multiple runnable projects found ({names}). Specify which one with the "
            f"cwd argument, or add a {CONFIG_FILENAME} to the workspace root."
        )

    raise RunConfigError(
        "Nothing runnable found. Expected one of: a package.json with a dev/start "
        "script, manage.py, app.py, main.py, go.mod, Cargo.toml, an index.html, or a "
        f"{CONFIG_FILENAME} declaring a \"run\" command."
    )
