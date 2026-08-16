"""Server lifecycle socket handlers: server.start, server.stop, server.status, server.crashed"""
import logging
from typing import Any

from apps.api.realtime.socket_server import sio

logger = logging.getLogger("RunnerIDE-Server")


@sio.on("server.start")
async def handle_server_start(sid, data: Any = None):
    from apps.api.main import get_or_create_session
    ctx = get_or_create_session(session_id=sid)
    cmd = "npm run dev"
    port = 3000
    if isinstance(data, dict):
        cmd = data.get("command", "npm run dev")
        port = int(data.get("port", 3000))
    elif isinstance(data, str) and data.strip():
        cmd = data.strip()

    if hasattr(ctx.sandbox, "server_manager"):
        res = await ctx.sandbox.server_manager.start(command=cmd, target_port=port)
        await sio.emit("server.status", res, room=sid)

        # Emit server.crashed if launch failed
        if isinstance(res, dict) and res.get("state") == "crashed":
            await sio.emit("server.crashed", res, room=sid)
        return res
    return {"success": False, "message": "Server manager not available."}


@sio.on("server.stop")
async def handle_server_stop(sid, data: Any = None):
    from apps.api.main import get_or_create_session
    ctx = get_or_create_session(session_id=sid)
    if hasattr(ctx.sandbox, "server_manager"):
        res = await ctx.sandbox.server_manager.stop()
        await sio.emit("server.status", res, room=sid)
        return res
    return {"success": False, "message": "Server manager not available."}


@sio.on("server.status")
async def handle_server_status(sid, data: Any = None):
    from apps.api.main import get_or_create_session
    ctx = get_or_create_session(session_id=sid)
    if hasattr(ctx.sandbox, "server_manager"):
        status = ctx.sandbox.server_manager.get_status()
        await sio.emit("server.status", status, room=sid)
        return status
    return {"state": "stopped"}
