import asyncio
import collections
import logging
import os
import re
import shlex
import shutil
import signal
import socket
import subprocess
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from services.agent.gateway.policy import PolicyEngine
from services.workspace_manager import run_config

logger = logging.getLogger("RunnerIDE-DevServer")


class DevServerManager:
    """
    Single-Owner Dev-Server Lifecycle Manager for a workspace session.
    Features:
    - Permanently resolves Next.js / Vite lock conflicts and port cascades (3000 -> 3009).
    - Cleans up orphaned Next.js Turbopack background daemons & stale .next/dev lockfiles.
    - Single tracked process per workspace session with strict single-process cap.
    - Real HTTP health-check readiness polling.
    - Port state as a strict mirror of currently alive servers (not an accumulator).
    - Ring-buffered stdout/stderr logs (250 lines).
    - Ongoing background liveness monitoring.
    """

    def __init__(
        self,
        workspace_dir: Path,
        session_id: str = "default",
        on_status_change: Optional[Callable[[Dict[str, Any]], Any]] = None,
        on_port_detected: Optional[Callable[[str], Any]] = None,
    ):
        self.workspace_dir = workspace_dir.resolve()
        self.session_id = session_id
        self.on_status_change = on_status_change
        self.on_port_detected = on_port_detected

        self.state: str = "stopped"  # 'stopped' | 'starting' | 'running' | 'crashed'
        self.command: Optional[str] = None
        self.port: int = 3000
        self.detected_port: Optional[int] = None
        self.pid: Optional[int] = None
        self.started_at: Optional[int] = None
        self.error: Optional[str] = None

        self.proc: Optional[asyncio.subprocess.Process] = None
        self.logs: collections.deque = collections.deque(maxlen=250)
        self._liveness_task: Optional[asyncio.Task] = None
        self._reader_task: Optional[asyncio.Task] = None

    def _get_enhanced_env(self) -> Dict[str, str]:
        env = os.environ.copy()
        env["CI"] = "true"
        env["TERM"] = "xterm-256color"
        env["PORT"] = str(self.port)

        home = Path.home()
        extra_paths: List[str] = [
            "/opt/homebrew/bin",
            "/usr/local/bin",
            "/opt/homebrew/sbin",
            str(home / ".local" / "bin"),
        ]

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

    async def _emit_status(self):
        payload = self.get_status()
        if self.on_status_change:
            if asyncio.iscoroutinefunction(self.on_status_change):
                await self.on_status_change(payload)
            else:
                self.on_status_change(payload)

    def get_status(self) -> Dict[str, Any]:
        """Returns the single-owner server status with exact currently alive ports mirror."""
        active_port = self.detected_port or self.port
        active_ports = [str(active_port)] if self.state == "running" else []
        return {
            "state": self.state,
            "command": self.command,
            "port": active_port,
            "active_ports": active_ports,
            "pid": self.pid,
            "started_at": self.started_at,
            "url": f"http://localhost:{active_port}" if self.state == "running" else None,
            "error": self.error,
            "logs": list(self.logs)[-50:],
        }

    @staticmethod
    def _port_is_free(port: int) -> bool:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind(("127.0.0.1", port))
                return True
            except OSError:
                return False

    def _pick_port(self, preferred: int) -> int:
        """
        The preferred port, or the next free one above it.

        Binding a port that is already taken produces
        `OSError: [Errno 48] Address already in use`, which surfaces to the user
        as "Dev Server Failed to Start" with a Python traceback and no
        indication that the real problem is a leftover process. Cleanup handles
        the common case; this handles the rest, including ports held by
        something we have no business killing.
        """
        for candidate in range(preferred, preferred + 16):
            if candidate in (8000,):  # the API itself
                continue
            if self._port_is_free(candidate):
                if candidate != preferred:
                    logger.info(f"Port {preferred} busy — using {candidate} instead")
                return candidate
        logger.warning(f"No free port in {preferred}-{preferred + 15}; using {preferred}")
        return preferred

    def _clean_all_competing_processes_and_locks(self, extra_ports: Optional[List[int]] = None):
        """
        Eliminates competing daemons, orphaned processes, and stale .next/dev
        lockfiles.

        Scans 3000-3015 plus any explicitly supplied port. The fixed range was
        written for Next.js and silently missed everything else — a static
        server on 8080 or a Flask app on 5000 was never cleaned up, so the
        second start always collided with the first.
        """
        current_pid = os.getpid()
        pids_to_kill = set()

        scan_ports = list(range(3000, 3016)) + [p for p in (extra_ports or []) if p not in range(3000, 3016)]

        for port in scan_ports:
            try:
                cmd = ["lsof", "-ti", f":{port}"]
                out = subprocess.check_output(cmd, stderr=subprocess.DEVNULL).decode().strip()
                if out:
                    for line in out.splitlines():
                        val = line.strip()
                        if val.isdigit():
                            pid = int(val)
                            if pid != current_pid:
                                pids_to_kill.add(pid)
            except Exception:
                pass

        # 2. Kill all identified conflicting PIDs
        for pid in pids_to_kill:
            try:
                logger.info(f"Force killing conflicting dev process PID {pid}")
                os.kill(pid, signal.SIGKILL)
            except Exception:
                pass

        # 3. Clean up Next.js lockfiles and stale dev logs in workspace
        try:
            next_dev_dir = self.workspace_dir / ".next" / "dev"
            if next_dev_dir.exists():
                shutil.rmtree(str(next_dev_dir), ignore_errors=True)
            
            lockfile = self.workspace_dir / ".next" / "lock"
            if lockfile.exists():
                lockfile.unlink(missing_ok=True)
        except Exception as e:
            logger.error(f"Error cleaning lockfiles: {e}")

    async def start(
        self,
        command: Optional[str] = None,
        target_port: Optional[int] = None,
        cwd: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Starts the dev server. Idempotent: returns current state if already starting or running.
        Eliminates lock conflicts, kills rogue daemons, and cleans .next/dev state.

        Command and port come from run_config.resolve() unless explicitly passed.
        This method used to default to `npm run dev` and refuse to start anything
        without a package.json, which made the preview a Next.js feature rather
        than a workspace feature. It is now stack-agnostic: it runs whatever the
        resolver says to run.
        """
        try:
            cfg = run_config.resolve(self.workspace_dir, cwd)
        except run_config.RunConfigError as e:
            # Actionable by design — the agent can read this and fix the cause
            # instead of retrying the same failing command.
            return {
                "success": False,
                "message": str(e),
                **self.get_status(),
            }

        target_cwd = cfg.cwd

        # An explicit cwd still goes through policy — the resolver checks
        # containment, but path validation is the security boundary and must not
        # be bypassed just because another check happened to run first.
        if cwd:
            valid, p, err = PolicyEngine.resolve_and_validate_path(self.workspace_dir, cwd)
            if not valid or not p:
                return {
                    "success": False,
                    "message": f"Invalid cwd: {err}",
                    **self.get_status(),
                }
            target_cwd = p

        # Caller overrides win; otherwise use what was resolved.
        command = command or cfg.command
        target_port = target_port or cfg.port

        # Starting a Node project with no node_modules fails in a way that reads
        # like a code error. Say what is actually wrong.
        if cfg.needs_install and cfg.install_command:
            return {
                "success": False,
                "message": (
                    f"Dependencies are not installed. Run `{cfg.install_command}` "
                    f"first, then start the server."
                ),
                **self.get_status(),
            }

        for w in cfg.warnings:
            logger.warning(f"Run config: {w}")
        logger.info(f"Resolved run config [{cfg.source}]: {cfg.describe()}")
        if self.state in ["starting", "running"] and self.proc and self.proc.returncode is None:
            logger.info(f"Dev server already in state '{self.state}'. Returning existing status.")
            return {
                "success": True,
                "message": f"Dev server is already {self.state}.",
                **self.get_status(),
            }

        # 1. Stop any prior tracked instance cleanly
        await self.stop(silent=True)

        # 2. Clean up conflicts, including on the port we are actually about to
        # bind — not just the Next.js range.
        self._clean_all_competing_processes_and_locks(extra_ports=[target_port])
        await asyncio.sleep(0.3)

        # 3. Then confirm the port is genuinely free. Cleanup may have missed a
        # holder it could not or should not kill, and binding a taken port fails
        # with a raw traceback that tells the user nothing useful.
        target_port = self._pick_port(target_port)

        # A static server takes its port from the command string, so the command
        # has to be rewritten when the port moves — otherwise it binds the
        # original busy port and the health check waits on the wrong one.
        if cfg.kind == "static" and target_port != cfg.port:
            command = command.replace(str(cfg.port), str(target_port))

        self.command = command
        self.port = target_port
        self.detected_port = None
        self.error = None
        self.logs.clear()
        self.state = "starting"
        self.started_at = int(time.time() * 1000)
        await self._emit_status()

        env = self._get_enhanced_env()

        try:
            self.proc = await asyncio.create_subprocess_shell(
                command,
                cwd=str(target_cwd),
                env=env,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                preexec_fn=os.setsid if hasattr(os, "setsid") else None,
            )
            self.pid = self.proc.pid
            logger.info(f"Spawned single dev server process PID {self.pid} with command: '{command}'")

            # Start reading stdout/stderr stream into ring buffer
            self._reader_task = asyncio.create_task(self._log_reader())

            # Real HTTP Readiness Polling (up to 30 seconds)
            ready = await self._poll_health_check(timeout_seconds=30.0)

            if ready:
                self.state = "running"
                await self._emit_status()
                # Start liveness monitor
                self._liveness_task = asyncio.create_task(self._liveness_monitor())
                return {
                    "success": True,
                    "message": f"Dev server is running and verified on port {self.detected_port or self.port}",
                    **self.get_status(),
                }
            else:
                self.state = "crashed"
                self.error = "\n".join(list(self.logs)[-25:]) or "Dev server failed HTTP readiness check within 15s."
                await self._emit_status()
                return {
                    "success": False,
                    "message": "Dev server failed HTTP readiness check.",
                    **self.get_status(),
                }

        except Exception as e:
            self.state = "crashed"
            self.error = str(e)
            await self._emit_status()
            return {
                "success": False,
                "message": f"Exception starting dev server: {e}",
                **self.get_status(),
            }

    async def _log_reader(self):
        """Continuously reads stdout/stderr lines into ring buffer and handles lock conflicts."""
        if not self.proc or not self.proc.stdout:
            return

        port_regex = re.compile(r"(?:https?://(?:localhost|127\.0\.0\.1):|port\s+)(\d{4,5})", re.IGNORECASE)
        conflict_regex = re.compile(r"(?:another next dev server is already running.*?PID\s*:\s*(\d+)|another next dev server is already running.*?PID\s+(\d+)|EADDRINUSE)", re.IGNORECASE)

        try:
            while True:
                line_bytes = await self.proc.stdout.readline()
                if not line_bytes:
                    break
                line = line_bytes.decode("utf-8", errors="replace").rstrip()
                self.logs.append(line)

                # Catch lock conflicts and kill rogue competitor
                conflict_match = conflict_regex.search(line)
                if conflict_match:
                    rogue_pid_str = conflict_match.group(1) or conflict_match.group(2)
                    if rogue_pid_str:
                        rogue_pid = int(rogue_pid_str)
                        logger.warning(f"Detected conflicting PID {rogue_pid} in Next.js logs. Force killing rogue process.")
                        try:
                            os.kill(rogue_pid, signal.SIGKILL)
                        except Exception:
                            pass

                # Dynamically scan for assigned port
                match = port_regex.search(line)
                if match:
                    found_port = int(match.group(1))
                    if found_port not in [5173, 8000, 5000, 7000]:
                        if self.detected_port != found_port:
                            self.detected_port = found_port
                            if self.on_port_detected:
                                if asyncio.iscoroutinefunction(self.on_port_detected):
                                    asyncio.create_task(self.on_port_detected(str(found_port)))
                                else:
                                    self.on_port_detected(str(found_port))

        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Error reading dev server output: {e}")

    async def _poll_health_check(self, timeout_seconds: float = 15.0) -> bool:
        """Polls the expected port with real HTTP/TCP health checks until responsive or timed out."""
        start = time.time()

        while time.time() - start < timeout_seconds:
            if self.proc and self.proc.returncode is not None:
                err_out = "\n".join(list(self.logs)[-25:])
                logger.warning(f"Dev server process exited early with code {self.proc.returncode}. Output:\n{err_out}")
                return False

            # The port we chose comes first and always. The 3000/3001 fallbacks
            # exist because Next.js cascades when its port is taken; they must
            # not shadow a static server or a Flask app on its own port.
            candidate_ports = (
                [self.detected_port]
                if self.detected_port
                else [self.port] + [p for p in (3000, 3001) if p != self.port]
            )
            for p in candidate_ports:
                if not p:
                    continue
                try:
                    reader, writer = await asyncio.wait_for(
                        asyncio.open_connection("127.0.0.1", p),
                        timeout=0.35,
                    )
                    writer.write(f"GET / HTTP/1.1\r\nHost: localhost:{p}\r\nConnection: close\r\n\r\n".encode("utf-8"))
                    await writer.drain()
                    
                    data = await asyncio.wait_for(reader.read(1024), timeout=0.5)
                    writer.close()
                    await writer.wait_closed()

                    if data:
                        self.detected_port = p
                        logger.info(f"Health check verified on port {p}!")
                        return True
                except Exception:
                    pass

            await asyncio.sleep(0.4)

        return False

    async def _liveness_monitor(self):
        """Continuously monitors if running process crashes after health check."""
        try:
            while self.state == "running" and self.proc:
                if self.proc.returncode is not None:
                    err_out = "\n".join(list(self.logs)[-25:])
                    logger.warning(f"Dev server crashed unexpectedly (Exit Code {self.proc.returncode}). Output:\n{err_out}")
                    self.state = "crashed"
                    self.error = err_out or "Dev server exited unexpectedly."
                    await self._emit_status()
                    break
                await asyncio.sleep(1.5)
        except asyncio.CancelledError:
            pass

    async def stop(self, silent: bool = False) -> Dict[str, Any]:
        """Stops the tracked dev server process cleanly."""
        if self._liveness_task and not self._liveness_task.done():
            self._liveness_task.cancel()

        if self._reader_task and not self._reader_task.done():
            self._reader_task.cancel()

        if self.proc and self.proc.returncode is None:
            try:
                if hasattr(os, "killpg") and hasattr(os, "getpgid"):
                    try:
                        os.killpg(os.getpgid(self.proc.pid), signal.SIGTERM)
                    except Exception:
                        self.proc.terminate()
                else:
                    self.proc.terminate()

                try:
                    await asyncio.wait_for(self.proc.wait(), timeout=2.0)
                except asyncio.TimeoutError:
                    if hasattr(os, "killpg") and hasattr(os, "getpgid"):
                        try:
                            os.killpg(os.getpgid(self.proc.pid), signal.SIGKILL)
                        except Exception:
                            self.proc.kill()
                    else:
                        self.proc.kill()
            except Exception as e:
                logger.error(f"Error stopping dev server PID {self.pid}: {e}")

        self.proc = None
        self.pid = None
        self.state = "stopped"
        if not silent:
            await self._emit_status()

        return {"success": True, "message": "Dev server stopped.", **self.get_status()}
