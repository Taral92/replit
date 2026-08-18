import asyncio
import difflib
import os
import re
import shlex
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Union
from uuid import uuid4

from packages.config import settings
from services.agent.gateway.policy import PolicyEngine
from .base import Sandbox
from .models import (
    CommandResult,
    DirectoryItem,
    DirectoryResult,
    FilePatchResult,
    FileReadResult,
    FileWriteResult,
    PortInfo,
    ProcessInfo,
    SearchMatch,
    SearchResult,
)


class LocalSandbox(Sandbox):
    """
    Concrete Local Sandbox Implementation.
    Executes operations in a dedicated, isolated workspace directory.
    Uses safe argument-list subprocess execution (no raw shell string interpolation).
    """

    def __init__(
        self,
        workspace_dir: Path,
        session_id: str = "default",
        on_port_detected: Optional[Callable[[str], Any]] = None,
        on_status_change: Optional[Callable[[Dict[str, Any]], Any]] = None,
        on_terminal_output: Optional[Callable[[str], Any]] = None,
    ):
        self.workspace_dir = workspace_dir.resolve()
        self.session_id = session_id
        self.on_port_detected = on_port_detected
        self.on_terminal_output = on_terminal_output
        self.workspace_dir.mkdir(parents=True, exist_ok=True)
        self.processes: Dict[str, asyncio.subprocess.Process] = {}
        self.process_info: Dict[str, ProcessInfo] = {}
        self.detected_ports: Dict[str, PortInfo] = {}
        from services.workspace_manager.server_manager import DevServerManager
        self.server_manager = DevServerManager(
            self.workspace_dir,
            session_id=session_id,
            on_status_change=on_status_change,
            on_port_detected=on_port_detected
        )

    def _get_utc_now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _get_enhanced_env(self) -> Dict[str, str]:
        """Injects NVM, Homebrew, and user bin paths so Node 20+ / Node 22 is always resolved."""
        env = os.environ.copy()
        env["CI"] = "true"
        env["TERM"] = "xterm-256color"

        home = Path.home()
        extra_paths: List[str] = [
            "/opt/homebrew/bin",
            "/usr/local/bin",
            "/opt/homebrew/sbin",
            str(home / ".local" / "bin"),
        ]

        # Scan for NVM node versions with numerical semver sorting (e.g. v22.23.2 > v18.20.8)
        nvm_dir = home / ".nvm" / "versions" / "node"
        if nvm_dir.exists() and nvm_dir.is_dir():
            try:
                def parse_v(p: Path):
                    digits = re.findall(r"\d+", p.name)
                    return [int(d) for d in digits] if digits else [0]

                versions = sorted(nvm_dir.iterdir(), key=parse_v, reverse=True)
                for v in versions:
                    bin_path = v / "bin"
                    if bin_path.exists():
                        extra_paths.insert(0, str(bin_path))
                        break
            except Exception:
                pass

        current_path = env.get("PATH", "")
        env["PATH"] = ":".join(extra_paths) + ":" + current_path
        return env

    async def read_file(self, path: str) -> FileReadResult:
        valid, full_path, err = PolicyEngine.resolve_and_validate_path(self.workspace_dir, path)
        if not valid or not full_path:
            return FileReadResult(success=False, path=path, error=err)

        if not full_path.exists() or not full_path.is_file():
            return FileReadResult(success=False, path=path, error=f"File not found: '{path}'")

        try:
            stat = full_path.stat()
            if stat.st_size > settings.MAX_FILE_SIZE_BYTES:
                return FileReadResult(
                    success=False,
                    path=path,
                    error=f"File exceeds size limit ({stat.st_size} bytes > {settings.MAX_FILE_SIZE_BYTES} bytes)",
                    size_bytes=stat.st_size,
                )

            # Check for binary content
            with open(full_path, "rb") as f:
                chunk = f.read(1024)
                if b"\x00" in chunk:
                    return FileReadResult(success=True, path=path, is_binary=True, size_bytes=stat.st_size)

            with open(full_path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()

            return FileReadResult(success=True, path=path, content=content, size_bytes=stat.st_size)
        except Exception as e:
            return FileReadResult(success=False, path=path, error=str(e))

    async def write_file(self, path: str, content: str) -> FileWriteResult:
        valid, full_path, err = PolicyEngine.resolve_and_validate_path(self.workspace_dir, path)
        if not valid or not full_path:
            return FileWriteResult(success=False, path=path, error=err)

        try:
            full_path.parent.mkdir(parents=True, exist_ok=True)
            old_content = ""
            if full_path.exists() and full_path.is_file():
                with open(full_path, "r", encoding="utf-8", errors="replace") as f:
                    old_content = f.read()

            # Generate unified diff
            diff = list(
                difflib.unified_diff(
                    old_content.splitlines(keepends=True),
                    content.splitlines(keepends=True),
                    fromfile=path,
                    tofile=path,
                )
            )
            diff_text = "".join(diff)
            added = sum(1 for line in diff if line.startswith("+") and not line.startswith("+++"))
            removed = sum(1 for line in diff if line.startswith("-") and not line.startswith("---"))

            with open(full_path, "w", encoding="utf-8") as f:
                f.write(content)

            return FileWriteResult(success=True, path=path, diff=diff_text, added=added, removed=removed)
        except Exception as e:
            return FileWriteResult(success=False, path=path, error=str(e))

    async def patch_file(self, path: str, target_content: str, replacement_content: str) -> FilePatchResult:
        valid, full_path, err = PolicyEngine.resolve_and_validate_path(self.workspace_dir, path)
        if not valid or not full_path:
            return FilePatchResult(success=False, path=path, error=err)

        if not full_path.exists() or not full_path.is_file():
            return FilePatchResult(success=False, path=path, error=f"File not found: '{path}'")

        try:
            with open(full_path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()

            new_content = None
            if target_content in content:
                new_content = content.replace(target_content, replacement_content, 1)
            else:
                # Fuzzy whitespace matching
                def norm(s: str) -> str:
                    return re.sub(r"\s+", "", s)

                target_norm = norm(target_content)
                lines = content.splitlines(keepends=True)
                found = False

                for i in range(len(lines)):
                    for j in range(i + 1, len(lines) + 1):
                        window = "".join(lines[i:j])
                        if norm(window) == target_norm:
                            append_nl = "\n" if window.endswith("\n") and not replacement_content.endswith("\n") else ""
                            new_content = "".join(lines[:i]) + replacement_content + append_nl + "".join(lines[j:])
                            found = True
                            break
                    if found:
                        break

                if not found:
                    return FilePatchResult(success=False, path=path, error="Target content block not found in file.")

            diff = list(
                difflib.unified_diff(
                    content.splitlines(keepends=True),
                    new_content.splitlines(keepends=True),
                    fromfile=path,
                    tofile=path,
                )
            )
            diff_text = "".join(diff)
            added = sum(1 for line in diff if line.startswith("+") and not line.startswith("+++"))
            removed = sum(1 for line in diff if line.startswith("-") and not line.startswith("---"))

            with open(full_path, "w", encoding="utf-8") as f:
                f.write(new_content)

            return FilePatchResult(success=True, path=path, diff=diff_text, added=added, removed=removed)
        except Exception as e:
            return FilePatchResult(success=False, path=path, error=str(e))

    async def list_dir(self, path: str = "", recursive: bool = False) -> DirectoryResult:
        valid, full_path, err = PolicyEngine.resolve_and_validate_path(self.workspace_dir, path)
        if not valid or not full_path:
            return DirectoryResult(success=False, path=path, error=err)

        if not full_path.exists() or not full_path.is_dir():
            return DirectoryResult(success=False, path=path, error=f"Directory not found: '{path}'")

        ignored = {"node_modules", ".git", ".next", "dist", "build", ".venv", "__pycache__", ".DS_Store"}

        def scan(dir_path: Path) -> List[DirectoryItem]:
            items: List[DirectoryItem] = []
            try:
                for entry in sorted(dir_path.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
                    if entry.name in ignored or entry.name.startswith("."):
                        continue
                    rel = str(entry.relative_to(self.workspace_dir))
                    if entry.is_dir():
                        children = scan(entry) if recursive else None
                        items.append(DirectoryItem(name=entry.name, path=rel, type="directory", children=children))
                    else:
                        size = entry.stat().st_size if entry.exists() else 0
                        items.append(DirectoryItem(name=entry.name, path=rel, type="file", size_bytes=size))
            except Exception:
                pass
            return items

        try:
            items = scan(full_path)
            return DirectoryResult(success=True, path=path, items=items)
        except Exception as e:
            return DirectoryResult(success=False, path=path, error=str(e))

    async def search(self, query: str, path: str = "") -> SearchResult:
        valid, full_path, err = PolicyEngine.resolve_and_validate_path(self.workspace_dir, path)
        if not valid or not full_path:
            return SearchResult(success=False, query=query, error=err)

        # Execute safe grep command using argument list (NO SHELL STRING INTERPOLATION)
        cmd_args = [
            "grep",
            "-rn",
            "--exclude-dir=node_modules",
            "--exclude-dir=.git",
            "--exclude-dir=.next",
            "--exclude-dir=dist",
            "--exclude-dir=__pycache__",
            "-F",  # Fixed string matching to prevent regex exploits
            query,
            str(full_path),
        ]

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd_args,
                cwd=str(self.workspace_dir),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10.0)
            raw_output = stdout.decode("utf-8", errors="replace").strip()

            matches: List[SearchMatch] = []
            lines = raw_output.splitlines()
            for line in lines[:100]:  # Cap at 100 matches
                parts = line.split(":", 2)
                if len(parts) >= 3:
                    file_abs = parts[0]
                    line_num = int(parts[1]) if parts[1].isdigit() else 0
                    content = parts[2]
                    try:
                        rel = str(Path(file_abs).relative_to(self.workspace_dir))
                    except ValueError:
                        rel = file_abs
                    matches.append(SearchMatch(file_path=rel, line_number=line_num, line_content=content))

            return SearchResult(
                success=True,
                query=query,
                matches=matches,
                match_count=len(matches),
                truncated=len(lines) > 100,
            )
        except asyncio.TimeoutError:
            return SearchResult(success=False, query=query, error="Search timed out after 10 seconds.")
        except Exception as e:
            return SearchResult(success=False, query=query, error=str(e))

    async def execute(self, command: str, timeout_seconds: Optional[int] = None) -> CommandResult:
        timeout = timeout_seconds or settings.COMMAND_TIMEOUT_SECONDS
        start_time = time.time()

        env = self._get_enhanced_env()

        try:
            if not command.strip():
                return CommandResult(success=False, command=command, error="Empty command.")

            # Commands containing shell operators must run through a shell.
            # create_subprocess_exec treats "&&", "|" and ">" as literal
            # arguments, which is why commands like `pwd && ls -la` were failing.
            needs_shell = any(op in command for op in ("&&", "||", "|", ">", "<", ";", "$(", "`", "*"))

            if needs_shell:
                proc = await asyncio.create_subprocess_shell(
                    command,
                    cwd=str(self.workspace_dir),
                    env=env,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
            else:
                args = shlex.split(command)
                if not args:
                    return CommandResult(success=False, command=command, error="Empty command.")
                proc = await asyncio.create_subprocess_exec(
                    *args,
                    cwd=str(self.workspace_dir),
                    env=env,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )

            stdout_chunks: list = []
            stderr_chunks: list = []

            # Terminal output is buffered and flushed on a timer rather than
            # emitted per line. Awaiting one websocket emit per line stalls the
            # read loop on network I/O — with `npm install` producing thousands
            # of lines, that is what made the terminal crawl. xterm cannot
            # render faster than the display refresh anyway, so batching costs
            # nothing visually.
            pending: list = []

            async def flush_terminal():
                if not pending or not self.on_terminal_output:
                    return
                batch = "".join(pending)
                pending.clear()
                try:
                    await self.on_terminal_output(batch)
                except Exception:
                    pass

            async def flusher():
                while True:
                    await asyncio.sleep(0.05)
                    await flush_terminal()

            async def read_stream(stream, chunks_list):
                async for line in stream:
                    decoded = line.decode("utf-8", errors="replace")
                    chunks_list.append(decoded)
                    if self.on_terminal_output:
                        pending.append(decoded)

            # Readers run as named tasks so they can be cancelled and their
            # exceptions collected. Gathering coroutines inline meant a timeout
            # cancelled them with nobody retrieving the CancelledError, which
            # asyncio then reported as "exception was never retrieved".
            stdout_task = asyncio.create_task(read_stream(proc.stdout, stdout_chunks))
            stderr_task = asyncio.create_task(read_stream(proc.stderr, stderr_chunks))
            flush_task = asyncio.create_task(flusher())

            async def shutdown_readers():
                for t in (stdout_task, stderr_task, flush_task):
                    t.cancel()
                # return_exceptions collects the CancelledErrors so they are
                # retrieved rather than logged as orphaned futures.
                await asyncio.gather(
                    stdout_task, stderr_task, flush_task, return_exceptions=True
                )
                await flush_terminal()

            try:
                # Wait on the PROCESS, not on the readers. A shell command whose
                # child holds the pipe open keeps the readers blocked long after
                # the command itself has finished — waiting on them was making
                # ordinary commands hang until the timeout.
                await asyncio.wait_for(proc.wait(), timeout=float(timeout))

                # Give the readers a brief grace period to drain buffered output,
                # then stop regardless.
                try:
                    await asyncio.wait_for(
                        asyncio.gather(stdout_task, stderr_task, return_exceptions=True),
                        timeout=2.0,
                    )
                except asyncio.TimeoutError:
                    pass

                await shutdown_readers()
            except asyncio.TimeoutError:
                await shutdown_readers()
                proc.kill()
                await proc.wait()
                duration = int((time.time() - start_time) * 1000)
                return CommandResult(
                    success=False,
                    command=command,
                    exit_code=-1,
                    error=f"Command timed out after {timeout} seconds and was killed.",
                    duration_ms=duration,
                )

            duration = int((time.time() - start_time) * 1000)
            stdout = "".join(stdout_chunks)
            stderr = "".join(stderr_chunks)

            # Output truncation
            truncated = False
            if len(stdout) > settings.MAX_OUTPUT_CHARS:
                stdout = stdout[: settings.MAX_OUTPUT_CHARS] + "\n... [stdout truncated]"
                truncated = True
            if len(stderr) > settings.MAX_OUTPUT_CHARS:
                stderr = stderr[: settings.MAX_OUTPUT_CHARS] + "\n... [stderr truncated]"
                truncated = True

            return CommandResult(
                success=(proc.returncode == 0),
                command=command,
                exit_code=proc.returncode,
                stdout=stdout,
                stderr=stderr,
                duration_ms=duration,
                truncated=truncated,
            )
        except FileNotFoundError as e:
            return CommandResult(success=False, command=command, error=f"Executable not found: {str(e)}")
        except Exception as e:
            return CommandResult(success=False, command=command, error=str(e))

    async def start_process(self, command: str, cwd: Optional[str] = None) -> ProcessInfo:
        """Start and track background long-running dev servers."""
        process_id = f"proc-{uuid4().hex[:8]}"
        target_cwd = self.workspace_dir
        if cwd:
            valid, p, _ = PolicyEngine.resolve_and_validate_path(self.workspace_dir, cwd)
            if valid and p:
                target_cwd = p

        env = self._get_enhanced_env()

        args = shlex.split(command)
        proc = await asyncio.create_subprocess_exec(
            *args,
            cwd=str(target_cwd),
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        self.processes[process_id] = proc
        info = ProcessInfo(
            process_id=process_id,
            command=command,
            pid=proc.pid,
            status="RUNNING",
            started_at=self._get_utc_now(),
        )
        self.process_info[process_id] = info

        # Asynchronously scan process stdout for ports
        asyncio.create_task(self._monitor_process_output(process_id, proc))
        return info

    async def _monitor_process_output(self, process_id: str, proc: asyncio.subprocess.Process):
        port_pattern = re.compile(r"(?:https?://(?:localhost|127\.0\.0\.1):|port\s+)(\d{4,5})", re.IGNORECASE)
        try:
            while proc.returncode is None:
                line = await proc.stdout.readline()
                if not line:
                    break
                text = line.decode("utf-8", errors="replace")
                if self.on_terminal_output:
                    try:
                        if asyncio.iscoroutinefunction(self.on_terminal_output):
                            asyncio.create_task(self.on_terminal_output(text))
                        else:
                            self.on_terminal_output(text)
                    except Exception:
                        pass
                match = port_pattern.search(text)
                if match:
                    port = match.group(1)
                    if port not in settings.SYSTEM_PORTS:
                        self.detected_ports[port] = PortInfo(
                            port=port,
                            process_id=process_id,
                            detected_at=self._get_utc_now(),
                        )
                        if process_id in self.process_info:
                            if port not in self.process_info[process_id].ports:
                                self.process_info[process_id].ports.append(port)
                        if self.on_port_detected:
                            try:
                                if asyncio.iscoroutinefunction(self.on_port_detected):
                                    asyncio.create_task(self.on_port_detected(port))
                                else:
                                    self.on_port_detected(port)
                            except Exception:
                                pass
            await proc.wait()
            if process_id in self.process_info:
                self.process_info[process_id].status = "STOPPED" if proc.returncode == 0 else "FAILED"
                self.process_info[process_id].exit_code = proc.returncode
        except Exception:
            pass

    async def stop_process(self, process_id: str) -> bool:
        proc = self.processes.get(process_id)
        if not proc:
            return False

        try:
            proc.terminate()
            try:
                await asyncio.wait_for(proc.wait(), timeout=3.0)
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()

            if process_id in self.process_info:
                self.process_info[process_id].status = "STOPPED"
                self.process_info[process_id].exit_code = proc.returncode
            return True
        except Exception:
            return False

    async def get_processes(self) -> List[ProcessInfo]:
        return list(self.process_info.values())

    async def get_ports(self) -> List[PortInfo]:
        return list(self.detected_ports.values())
