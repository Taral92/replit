"""Agent chat socket handler — agent.start, agent.stop, and all turn events."""
import asyncio
import logging
import time
from typing import Any, Dict
from uuid import uuid4

from apps.api.realtime.socket_server import sio

logger = logging.getLogger("RunnerIDE-Agent")

# Tracks the in-flight agent task per socket so agent.stop can cancel it.
# One run per socket at a time — starting a new turn supersedes the old one.
_running_turns: Dict[str, asyncio.Task] = {}


@sio.on("agent.stop")
async def handle_agent_stop(sid, data: Any = None):
    """Cancel the in-flight agent run for this socket, if any."""
    task = _running_turns.get(sid)
    if task is None or task.done():
        return
    task.cancel()


@sio.on("agent.start")
async def handle_agent_start(sid, data: Any):
    from apps.api.main import get_or_create_session
    ctx = get_or_create_session(session_id=sid)

    # A new turn supersedes any run still in flight for this socket.
    previous = _running_turns.get(sid)
    if previous is not None and not previous.done():
        previous.cancel()

    _running_turns[sid] = asyncio.current_task()

    if isinstance(data, dict):
        prompt = data.get("prompt", "")
        requested_model = data.get("model", "auto")
        turn_id = str(data.get("turn_id") or uuid4())
    else:
        prompt = str(data)
        requested_model = "auto"
        turn_id = str(uuid4())

    started_at = int(time.time() * 1000)

    await sio.emit(
        "agent.turn.started",
        {"turn_id": turn_id, "started_at": started_at, "prompt": prompt},
        room=sid,
    )

    try:
        async def callback(event_dict):
            ev_type = event_dict.get("type")
            if ev_type == "agent.message":
                await sio.emit(
                    "agent.message",
                    {"turn_id": turn_id, "content": event_dict.get("content", "")},
                    room=sid,
                )
            elif ev_type == "agent.status":
                await sio.emit(
                    "agent.status",
                    {"turn_id": turn_id, "status": event_dict.get("status", "Thinking...")},
                    room=sid,
                )
            elif ev_type == "agent.tool.started":
                tool = event_dict.get("tool_name", "tool")
                args = event_dict.get("arguments", {})

                action = (
                    "explored" if tool in ["read_file", "list_dir", "search"]
                    else "edited" if tool in ["write_file", "patch_file"]
                    else "ran" if tool == "run_command"
                    else "verified" if tool == "verify_project"
                    else "action"
                )
                target_name = args.get("path") or args.get("command") or args.get("query") or "workspace"

                await sio.emit(
                    "agent.step",
                    {
                        "turn_id": turn_id,
                        "tool": tool,
                        "target": target_name,
                        "action": action,
                        "type": action,
                        "status": "running",
                        "args": args,
                        "timestamp": int(time.time() * 1000),
                    },
                    room=sid,
                )

            elif ev_type == "agent.tool.completed":
                tool = event_dict.get("tool_name", "tool")
                res = event_dict.get("result", {})

                action = "edited" if tool in ["write_file", "patch_file"] else "explored"
                target_name = res.get("path", "file") if isinstance(res, dict) else "file"
                added = res.get("added", 0) if isinstance(res, dict) else 0
                removed = res.get("removed", 0) if isinstance(res, dict) else 0
                diff = res.get("diff", "") if isinstance(res, dict) else ""

                await sio.emit(
                    "agent.tool.completed",
                    {
                        "turn_id": turn_id,
                        "tool": tool,
                        "file": target_name,
                        "target": target_name,
                        "action": action,
                        "type": action,
                        "added": added,
                        "removed": removed,
                        "diff": diff,
                        "status": "completed",
                        "timestamp": int(time.time() * 1000),
                    },
                    room=sid,
                )

        async for _ in ctx.agent.run_stream(
            prompt, session_id=sid, requested_model=requested_model, event_callback=callback
        ):
            pass

        ended_at = int(time.time() * 1000)
        await sio.emit(
            "agent.turn.completed",
            {
                "turn_id": turn_id,
                "started_at": started_at,
                "ended_at": ended_at,
                "duration_ms": ended_at - started_at,
            },
            room=sid,
        )
        await sio.emit("agent.status", {"turn_id": turn_id, "status": "Idle"}, room=sid)

    except asyncio.CancelledError:
        # User pressed stop. Close the turn cleanly so the UI leaves the
        # streaming state, then re-raise so asyncio unwinds properly.
        ended_at = int(time.time() * 1000)
        await sio.emit(
            "agent.turn.completed",
            {
                "turn_id": turn_id,
                "started_at": started_at,
                "ended_at": ended_at,
                "duration_ms": ended_at - started_at,
                "cancelled": True,
            },
            room=sid,
        )
        await sio.emit(
            "agent.message",
            {"turn_id": turn_id, "content": "Stopped by user."},
            room=sid,
        )
        await sio.emit("agent.status", {"turn_id": turn_id, "status": "Idle"}, room=sid)
        raise

    except Exception as e:
        logger.exception(f"Error in agent.start: {e}")
        ended_at = int(time.time() * 1000)
        await sio.emit(
            "agent.turn.completed",
            {"turn_id": turn_id, "started_at": started_at, "ended_at": ended_at, "error": str(e)},
            room=sid,
        )
        await sio.emit(
            "agent.message",
            {"turn_id": turn_id, "content": f"⚠️ Error: {str(e)}"},
            room=sid,
        )
        await sio.emit("agent.status", {"turn_id": turn_id, "status": "Idle"}, room=sid)

    finally:
        if _running_turns.get(sid) is asyncio.current_task():
            _running_turns.pop(sid, None)
