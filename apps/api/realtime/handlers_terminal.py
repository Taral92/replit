"""Terminal socket handlers: terminal.input, terminal.output, terminal.resize"""
import asyncio
import fcntl
import logging
import os
import re
import struct
import termios

from packages.config import settings
from apps.api.realtime.socket_server import sio

logger = logging.getLogger("RunnerIDE-Terminal")


def start_session_terminal(ctx, loop, emit_fn):
    """Fork a pty and wire its output to a per-room socket emitter."""
    import pty as pty_mod

    if ctx.pty_fd:
        return

    pid, fd = pty_mod.fork()
    if pid == 0:
        os.chdir(str(ctx.workspace_dir))
        env = ctx.sandbox._get_enhanced_env()
        shell = os.environ.get("SHELL", "/bin/zsh" if os.path.exists("/bin/zsh") else "/bin/bash")
        os.execvpe(shell, [shell], env)
    else:
        ctx.pty_fd = fd

        def read_callback():
            try:
                data = os.read(fd, 1024)
                if data:
                    text = data.decode("utf-8", errors="replace")
                    asyncio.run_coroutine_threadsafe(emit_fn("terminal.output", text), loop)
                    port_regex = r"(?:https?://(?:localhost|127\.0\.0\.1):|port\s+)(\d{4,5})"
                    for match in re.finditer(port_regex, text, re.IGNORECASE):
                        port = match.group(1)
                        if port not in settings.SYSTEM_PORTS and port not in ctx.active_ports:
                            ctx.active_ports.add(port)
                            asyncio.run_coroutine_threadsafe(emit_fn("preview.ready", port), loop)
                            asyncio.run_coroutine_threadsafe(
                                emit_fn("ports.update", list(ctx.active_ports)), loop
                            )
                else:
                    loop.remove_reader(fd)
            except OSError:
                loop.remove_reader(fd)

        loop.add_reader(fd, read_callback)


@sio.on("terminal.input")
async def handle_terminal_input(sid, data):
    from apps.api.main import get_or_create_session
    ctx = get_or_create_session(session_id=sid)
    if ctx.pty_fd:
        try:
            os.write(ctx.pty_fd, data.encode("utf-8"))
        except OSError as e:
            logger.error(f"PTY write error: {e}")


@sio.on("terminal.resize")
async def handle_terminal_resize(sid, data):
    """Resize the pty to match the client terminal dimensions."""
    from apps.api.main import get_or_create_session
    ctx = get_or_create_session(session_id=sid)
    if ctx.pty_fd and isinstance(data, dict):
        cols = int(data.get("cols", 80))
        rows = int(data.get("rows", 24))
        try:
            winsize = struct.pack("HHHH", rows, cols, 0, 0)
            fcntl.ioctl(ctx.pty_fd, termios.TIOCSWINSZ, winsize)
        except OSError as e:
            logger.error(f"PTY resize error: {e}")
