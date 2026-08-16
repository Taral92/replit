"""Agent chat socket handler — agent.start and all turn events."""
import logging
import time
from typing import Any
from uuid import uuid4

from apps.api.realtime.socket_server import sio

logger = logging.getLogger("RunnerIDE-Agent")


@sio.on("agent.start")
async def handle_agent_start(sid, data: Any):
    from apps.api.main import get_or_create_session
    ctx = get_or_create_session(session_id=sid)

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
