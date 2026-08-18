"""Agent chat socket handler — agent.start, agent.stop, and all turn events."""
import asyncio
import logging
import time
from typing import Any, Dict
from uuid import uuid4

from apps.api.realtime.socket_server import sio

logger = logging.getLogger("RunnerIDE-Agent")


def _target_for(args: Any, data: Any = None) -> str:
    """
    The label a tool call is displayed under — and the key the frontend uses to
    pair a completion with its started row.

    Derived from the tool ARGUMENTS, not the result, because arguments are
    identical at start and finish while results are not. Two different
    derivations here is what left shell and list_dir rows spinning forever.
    """
    args = args if isinstance(args, dict) else {}
    data = data if isinstance(data, dict) else {}
    return (
        args.get("path")
        or args.get("command")
        or args.get("query")
        or data.get("path")
        or "workspace"
    )

# Tracks the in-flight agent task per socket so agent.stop can cancel it.
# One run per socket at a time — starting a new turn supersedes the old one.
_running_turns: Dict[str, asyncio.Task] = {}


@sio.on("agent.answer")
async def handle_agent_answer(sid, data: Any = None):
    """
    Deliver a user's answer to a parked ask_user call, resuming the turn.

    Carries interaction_id so a stale click from a reopened tab cannot answer a
    newer question.
    """
    from services.agent.interaction import broker

    if not isinstance(data, dict):
        return
    answer = str(data.get("answer", "")).strip()
    if not answer:
        return

    delivered = broker.resolve(sid, answer, data.get("interaction_id"))
    if not delivered:
        logger.info(f"agent.answer for {sid[:8]} had nothing waiting (or was stale)")


@sio.on("agent.stop")
async def handle_agent_stop(sid, data: Any = None):
    """Cancel the in-flight agent run for this socket, if any."""
    # Abandon any parked question first — otherwise the run stays blocked on a
    # Future that will never resolve and the cancel appears to do nothing.
    from services.agent.interaction import broker
    broker.cancel(sid)

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
            elif ev_type == "agent.plan.updated":
                await sio.emit(
                    "agent.plan.updated",
                    {"turn_id": turn_id, "plan": event_dict.get("plan", [])},
                    room=sid,
                )
            elif ev_type == "agent.tool.started":
                tool = event_dict.get("tool_name", "tool")
                args = event_dict.get("arguments", {})
                plan_step_id = event_dict.get("plan_step_id")

                action = "action"
                target_name = _target_for(args)

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
                        "plan_step_id": plan_step_id,
                        "timestamp": int(time.time() * 1000),
                    },
                    room=sid,
                )

            elif ev_type == "agent.question":
                # The turn is parked on a Future while this sits in the UI.
                await sio.emit(
                    "agent.question",
                    {
                        "turn_id": turn_id,
                        "interaction_id": event_dict.get("interaction_id"),
                        "kind": event_dict.get("kind", "question"),
                        "question": event_dict.get("question"),
                        "options": event_dict.get("options", []),
                    },
                    room=sid,
                )

            elif ev_type == "agent.tool.progress":
                await sio.emit(
                    "agent.step.progress",
                    {
                        "turn_id": turn_id,
                        "call_id": event_dict.get("call_id"),
                        "plan_step_id": event_dict.get("plan_step_id"),
                        "phase": event_dict.get("phase"),
                        "target": event_dict.get("target"),
                    },
                    room=sid,
                )

            elif ev_type == "agent.tool.completed":
                tool = event_dict.get("tool_name", "tool")
                res = event_dict.get("result", {})
                data = res.get("data", {}) if isinstance(res, dict) else {}

                # "edited" on a file that did not exist is actively misleading —
                # it reads as though the agent modified something pre-existing.
                # `removed == 0` with additions means the file was created.
                if tool in ("write_file", "patch_file", "edit_file"):
                    created = data.get("created") is True or (
                        data.get("added", 0) > 0 and data.get("removed", 0) == 0
                        and tool == "write_file"
                    )
                    action = "created" if created else "edited"
                else:
                    action = "explored"

                # MUST match the target emitted by agent.tool.started, because
                # the frontend pairs the completion to its row by (tool, target).
                # This previously read data["path"], so a shell call started as
                # "npm install" and completed as "file" — the pair never matched
                # and the row spun forever, long after the work had finished.
                target_name = _target_for(event_dict.get("arguments", {}), data)
                added = data.get("added", 0)
                removed = data.get("removed", 0)
                diff = data.get("diff", "")

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
                        "plan_step_id": event_dict.get("plan_step_id"),
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
