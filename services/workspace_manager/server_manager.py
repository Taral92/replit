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
    ):
        self.workspace_dir = workspace_dir.resolve()
        self.session_id = session_id
        self.on_status_change = on_status_change

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
            try:
                if asyncio.iscoroutinefunction(self.on_status_change):
                    await self.on_status_change(payload)
                else:
                    self.on_status_change(payload)
            except Exception as e:
                logger.error(f"Error in on_status_change: {e}")

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

    def _clean_all_competing_processes_and_locks(self):
        """
        Permanently eliminates competing daemons, orphaned Next.js processes,
        and stale .next/dev lockfiles across all candidate ports (3000-3015).
        """
        current_pid = os.getpid()
        pids_to_kill = set()

        # 1. Scan and kill all processes holding ports 3000 to 3015
        for port in range(3000, 3016):
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

    async def start(self, command: str = "npm run dev", target_port: int = 3000) -> Dict[str, Any]:
        """
        Starts the dev server. Idempotent: returns current state if already starting or running.
        Eliminates lock conflicts, kills rogue daemons, and cleans .next/dev state.
        """
        if self.state in ["starting", "running"] and self.proc and self.proc.returncode is None:
            logger.info(f"Dev server already in state '{self.state}'. Returning existing status.")
            return {
                "success": True,
                "message": f"Dev server is already {self.state}.",
                **self.get_status(),
            }

        # 1. Stop any prior tracked instance cleanly
        await self.stop(silent=True)

        # 2. Lock-conflict resolution: kill any conflicting orphaned process on ports 3000-3015 & clean locks
        self._clean_all_competing_processes_and_locks()
        await asyncio.sleep(0.3)

        self.command = command
        self.port = target_port
        self.detected_port = None
        self.error = None
        self.logs.clear()
        self.state = "starting"
        self.started_at = int(time.time() * 1000)
        await self._emit_status()

        env = self._get_enhanced_env()
        args = shlex.split(command)

        try:
            self.proc = await asyncio.create_subprocess_exec(
                *args,
                cwd=str(self.workspace_dir),
                env=env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                preexec_fn=os.setsid if hasattr(os, "setsid") else None,
            )
            self.pid = self.proc.pid
            logger.info(f"Spawned single dev server process PID {self.pid} with command: '{command}'")

            # Start reading stdout/stderr stream into ring buffer
            self._reader_task = asyncio.create_task(self._log_reader())

            # Real HTTP Readiness Polling (up to 15 seconds)
            ready = await self._poll_health_check(timeout_seconds=15.0)

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
                        self.detected_port = found_port

        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Error reading dev server output: {e}")

    async def _poll_health_check(self, timeout_seconds: float = 15.0) -> bool:
        """Polls the expected port with real HTTP/TCP health checks until responsive or timed out."""
        start = time.time()

        while time.time() - start < timeout_seconds:
            if self.proc and self.proc.returncode is not None:
                logger.warning(f"Dev server process exited early with code {self.proc.returncode}")
                return False

            candidate_ports = [self.detected_port] if self.detected_port else [self.port, 3000, 3001]
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
                    logger.warning(f"Dev server crashed unexpectedly (Exit Code {self.proc.returncode})")
                    self.state = "crashed"
                    self.error = "\n".join(list(self.logs)[-25:]) or "Dev server exited unexpectedly."
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
