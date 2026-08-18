import asyncio
import json
import logging
import time
import re
from typing import Any, Callable, Dict, List, Optional

# Commands that start a server and never terminate on their own. Matched
# against each segment of a compound command, so `npm run build && npm run dev`
# is caught too.
_LONG_RUNNING = re.compile(
    r"\b("
    r"npm\s+(run\s+)?(dev|start|serve)"
    r"|yarn\s+(dev|start|serve)"
    r"|pnpm\s+(run\s+)?(dev|start|serve)"
    r"|next\s+(dev|start)"
    r"|vite(\s|$)"
    r"|nodemon"
    r"|http\.server"
    r"|flask\s+run"
    r"|uvicorn"
    r"|rails\s+s"
    r"|serve(\s|$)"
    r")",
    re.IGNORECASE,
)


# Payload returned to the model is bounded — enough to work with, not enough to
# blow the context window on one file. The agent can request a line range if it
# needs more.
MAX_PAYLOAD_CHARS = 6000


def _clip(text: str) -> str:
    text = text or ""
    if len(text) <= MAX_PAYLOAD_CHARS:
        return text
    return (
        text[:MAX_PAYLOAD_CHARS]
        + f"\n... [truncated, {len(text)} chars total — re-read with start_line/end_line for the rest]"
    )


# `cd` to an absolute path escapes the workspace. Commands already run with the
# workspace as cwd, so this is never needed and is usually the agent guessing at
# a path like /workspace that does not exist.
_ABSOLUTE_CD = re.compile(r"\bcd\s+(/[^\s;&|]*)")


def _escaping_cd(command: str) -> Optional[str]:
    m = _ABSOLUTE_CD.search(command)
    return m.group(1) if m else None


def _long_running_process(command: str) -> Optional[str]:
    """Returns the offending fragment if the command starts a server."""
    for segment in re.split(r"&&|\|\||;|\|", command):
        m = _LONG_RUNNING.search(segment)
        if m:
            # `... &` already backgrounds it at the shell level; leave it alone.
            if segment.rstrip().endswith("&"):
                continue
            return m.group(0).strip()
    return None
from uuid import uuid4

from services.agent.sandbox.base import Sandbox
from packages.protocol.events import ToolResult
from .policy import PolicyEngine, RiskLevel

logger = logging.getLogger("ToolGateway")


class AuditEvent:
    def __init__(
        self,
        event_id: str,
        session_id: str,
        workspace_id: str,
        tool_name: str,
        arguments: Dict[str, Any],
        risk_level: RiskLevel,
        success: bool,
        duration_ms: int,
        error: Optional[str] = None,
    ):
        self.event_id = event_id
        self.session_id = session_id
        self.workspace_id = workspace_id
        self.tool_name = tool_name
        self.arguments = arguments
        self.risk_level = risk_level
        self.success = success
        self.duration_ms = duration_ms
        self.error = error
        self.timestamp = time.time()


class ToolGateway:
    """
    Central Security, Authorization & Audit Gateway.
    All Agent Tool invocations MUST pass through this gateway.
    Separates Intelligence from Execution and Policy.
    """

    def __init__(self, sandbox: Sandbox, session_id: str = "default", workspace_id: str = "default"):
        self.sandbox = sandbox
        self.session_id = session_id
        self.workspace_id = workspace_id
        self.audit_log: List[AuditEvent] = []
        self.approval_callback: Optional[Callable[[str, RiskLevel, str], bool]] = None
        self.event_callback: Optional[Callable[[Dict[str, Any]], Any]] = None
        self.turn_diffs: Dict[str, Dict[str, Any]] = {}
        self.turn_tool_calls: Dict[str, int] = {}
        # Results of tool calls made this turn, keyed by call signature, so a
        # repeat can be replayed instead of re-executed or refused.
        self.turn_tool_cache: Dict[str, Any] = {}
        self.current_plan_step_id: Optional[str] = None

    def set_approval_callback(self, callback: Callable[[str, RiskLevel, str], bool]):
        self.approval_callback = callback

    def set_event_callback(self, callback: Callable[[Dict[str, Any]], Any]):
        self.event_callback = callback

    def reset_turn_diffs(self):
        """Resets the accumulated diffs for a new turn."""
        self.turn_diffs.clear()
        self.turn_tool_calls.clear()
        self.turn_tool_cache.clear()

    def get_turn_diff_data(self) -> Dict[str, Any]:
        """Returns aggregated diff text, modified files, and line counts for this turn."""
        diff_chunks: List[str] = []
        touched = list(self.turn_diffs.keys())
        total_added = 0
        total_removed = 0

        for path, data in self.turn_diffs.items():
            diff_str = data.get("diff", "").strip()
            if diff_str:
                diff_chunks.append(diff_str)
            total_added += data.get("added", 0)
            total_removed += data.get("removed", 0)

        return {
            "diff_text": "\n".join(diff_chunks),
            "touched_files": touched,
            "total_added": total_added,
            "total_removed": total_removed,
        }

    async def _emit_event(self, event_dict: Dict[str, Any]):
        if self.event_callback:
            try:
                if asyncio.iscoroutinefunction(self.event_callback):
                    await self.event_callback(event_dict)
                else:
                    self.event_callback(event_dict)
            except Exception as e:
                logger.error(f"Error in ToolGateway event callback: {e}")

    async def execute_tool(self, tool_name: str, **kwargs) -> ToolResult:
        """
        Executes a named tool through security authorization and sandbox delegation.
        Emits tool started and completed events with full diff metrics.
        """
        start_time = time.time()
        event_id = str(uuid4())

        # Notify tool started
        await self._emit_event({
            "type": "agent.tool.started",
            "tool_name": tool_name,
            "arguments": kwargs,
            "plan_step_id": self.current_plan_step_id,
        })

        # B4: Repeated Identical Commands check
        try:
            call_sig = f"{tool_name}:{json.dumps(kwargs, sort_keys=True)}"
        except Exception:
            call_sig = f"{tool_name}:{str(kwargs)}"

        self.turn_tool_calls[call_sig] = self.turn_tool_calls.get(call_sig, 0) + 1

        # Memoize repeats rather than refusing them.
        #
        # Returning an error here made things worse, not better: the agent still
        # needed the content, so it evaded the guard by rephrasing the same
        # request — cat, then `cat && echo`, then `ls -la && wc -l`, then
        # `test -f`, then `find`, then `head`. Each is a distinct signature, so
        # each got through, and the turn spent MORE calls dodging the guard than
        # the repeats would have cost.
        #
        # Replaying the cached result costs nothing, avoids re-executing the
        # work, and gives the agent what it asked for so it moves on.
        if self.turn_tool_calls[call_sig] >= 2 and call_sig in self.turn_tool_cache:
            cached: ToolResult = self.turn_tool_cache[call_sig]
            replay = cached.model_copy(deep=True)
            replay.summary = f"{cached.summary} (unchanged since earlier this turn)"
            await self._emit_event({
                "type": "agent.tool.completed",
                "tool_name": tool_name,
                "arguments": kwargs,
                "result": replay.model_dump(),
                "plan_step_id": self.current_plan_step_id,
            })
            return replay

        # 1. Policy Assessment
        risk_level: RiskLevel = "safe"
        rationale = "Standard tool invocation"

        if tool_name in ("run_command", "execute", "shell"):
            cmd = kwargs.get("command", "")
            risk_level, rationale = PolicyEngine.classify_command(cmd)

            # Reject absolute `cd` before executing. Left alone, `cd /workspace
            # && npm run build` fails inside the shell with exit code 1, the
            # agent reads that as a build failure rather than a bad path, and
            # in one observed turn went on to report the changes as verified
            # when nothing had been built.
            escaped = _escaping_cd(cmd)
            if escaped:
                err = ToolResult(
                    ok=False,
                    summary=(
                        f"'{escaped}' does not exist. Commands already run in the workspace "
                        f"root — drop the `cd` and use relative paths."
                    ),
                    data={"command": cmd, "reason": "absolute_cd"},
                    error_kind="invalid",
                )
                await self._emit_event({
                    "type": "agent.tool.completed",
                    "tool_name": tool_name,
                    "arguments": kwargs,
                    "result": err.model_dump(),
                    "plan_step_id": self.current_plan_step_id,
                })
                return err

            # A dev server never exits, so running one in the foreground blocks
            # until the command timeout — 60 seconds of nothing, repeated every
            # time the agent tries. Telling it "use background=true" in the
            # system prompt is not reliable enough; refuse immediately instead,
            # so the correction costs a fast error rather than a minute of
            # dead air.
            if not kwargs.get("background"):
                blocked = _long_running_process(cmd)
                if blocked:
                    err = ToolResult(
                        ok=False,
                        summary=(
                            f"'{blocked}' is a long-running process and would never return. "
                            f"Re-run it with background=true."
                        ),
                        data={"command": cmd, "reason": "long_running_in_foreground"},
                        error_kind="invalid",
                    )
                    await self._emit_event({
                        "type": "agent.tool.completed",
                        "tool_name": tool_name,
                        "arguments": kwargs,
                        "result": err.model_dump(),
                        "plan_step_id": self.current_plan_step_id,
                    })
                    return err
        elif tool_name in ("write_file", "patch_file", "edit_file"):
            risk_level = "restricted"
            rationale = "File modification"

        # 2. Human Approval Check for High-Risk Actions
        if PolicyEngine.requires_human_approval(risk_level):
            if self.approval_callback:
                approved = self.approval_callback(tool_name, risk_level, str(kwargs))
                if not approved:
                    duration = int((time.time() - start_time) * 1000)
                    self._record_audit(
                        event_id, tool_name, kwargs, risk_level, success=False,
                        duration_ms=duration, error=f"Operation rejected by human approval policy ({rationale})."
                    )
                    err_result = ToolResult(
                        ok=False,
                        summary=f"Security Error: Operation requiring approval was rejected ({rationale}).",
                        data={"risk_level": risk_level},
                        error_kind="denied"
                    )
                    await self._emit_event({
                        "type": "agent.tool.failed",
                        "tool_name": tool_name,
                        "arguments": kwargs,
                        "error": err_result.summary,
                        "plan_step_id": self.current_plan_step_id,
                    })
                    return err_result

        # 3. Sandbox Delegation
        phase = "running"
        target = "workspace"
        if tool_name in ("write_file", "patch_file", "edit_file"):
            phase = "writing"
            target = kwargs.get("path", "")
        elif tool_name in ("read_file", "list_dir", "search"):
            phase = "reading"
            target = kwargs.get("path") or kwargs.get("query") or "workspace"
        elif tool_name in ("run_command", "execute", "shell", "start_process"):
            phase = "running"
            target = kwargs.get("command") or "process"

        done_event = asyncio.Event()
        
        async def progress_loop():
            while not done_event.is_set():
                await asyncio.sleep(0.25)
                if done_event.is_set():
                    break
                await self._emit_event({
                    "type": "agent.tool.progress",
                    "run_id": self.session_id,
                    "call_id": event_id,
                    "phase": phase,
                    "target": target,
                    "plan_step_id": self.current_plan_step_id,
                })
                
        progress_task = asyncio.create_task(progress_loop())
        
        try:
            out = {}
            if tool_name == "read_file":
                start_line = kwargs.get("start_line")
                end_line = kwargs.get("end_line")
                res = await self.sandbox.read_file(kwargs.get("path", ""))
                out = res.model_dump()
                # Apply line ranges if specified
                if out.get("success") and not out.get("is_binary"):
                    content = out.get("content", "")
                    lines = content.split("\n")
                    total_lines = len(lines)
                    s_idx = max(0, start_line - 1) if start_line is not None else 0
                    e_idx = min(total_lines, end_line) if end_line is not None else total_lines
                    out["content"] = "\n".join(lines[s_idx:e_idx])
                    out["total_lines"] = total_lines
                    out["range"] = [s_idx + 1, e_idx]
            elif tool_name == "write_file":
                res = await self.sandbox.write_file(kwargs.get("path", ""), kwargs.get("content", ""))
                out = res.model_dump()
            elif tool_name in ("patch_file", "edit_file"):
                res = await self.sandbox.patch_file(
                    kwargs.get("path", ""),
                    kwargs.get("old", kwargs.get("target_content", "")),
                    kwargs.get("new", kwargs.get("replacement_content", "")),
                )
                out = res.model_dump()
            elif tool_name == "list_dir":
                res = await self.sandbox.list_dir(kwargs.get("path", ""), kwargs.get("recursive", False))
                out = res.model_dump()
            elif tool_name == "search":
                # handle kind optionally
                res = await self.sandbox.search(kwargs.get("query", ""), kwargs.get("path", ""))
                out = res.model_dump()
            elif tool_name in ("run_command", "execute", "shell"):
                background = kwargs.get("background", False)
                if background:
                    # use server manager if possible
                    cmd = kwargs.get("command", "")
                    if getattr(self.sandbox, "server_manager", None):
                        res = await self.sandbox.server_manager.start(command=cmd, target_port=3000, cwd=kwargs.get("cwd"))
                        out = res
                        if not out.get("success") and "message" in out:
                            out["error"] = out["message"]
                    else:
                        res = await self.sandbox.start_process(cmd, kwargs.get("cwd"))
                        out = res.model_dump()
                else:
                    res = await self.sandbox.execute(kwargs.get("command", ""), kwargs.get("timeout_ms", 60000) // 1000)
                    out = res.model_dump()
            elif tool_name == "start_process":
                res = await self.sandbox.start_process(kwargs.get("command", ""), kwargs.get("cwd"))
                out = res.model_dump()
            elif tool_name == "stop_process":
                success = await self.sandbox.stop_process(kwargs.get("process_id", ""))
                out = {"success": success}
            elif tool_name in ("get_processes", "list_processes"):
                procs = await self.sandbox.get_processes()
                out = {"success": True, "processes": [p.model_dump() for p in procs]}
                
                # Check server manager
                if getattr(self.sandbox, "server_manager", None):
                    st = self.sandbox.server_manager.get_status()
                    if st.get("state") != "stopped":
                        out["processes"].append({
                            "process_id": "dev_server",
                            "command": "dev_server",
                            "pid": st.get("pid"),
                            "status": st.get("state").upper(),
                            "ports": [st.get("url", "").split(":")[-1].strip("/")] if st.get("url") else []
                        })
            elif tool_name == "get_ports":
                ports = await self.sandbox.get_ports()
                out = {"success": True, "ports": [p.model_dump() for p in ports]}
            elif tool_name == "verify_project":
                from services.agent.verifier import ProjectVerifier
                result = await ProjectVerifier.verify(self.sandbox)
                out = {
                    "success": result.passed,
                    "language": result.language,
                    "checks_run": result.checks_run,
                    "details": result.details
                }
            elif tool_name == "update_plan":
                plan = kwargs.get("plan", [])
                
                # Emit the plan event
                await self._emit_event({
                    "type": "agent.plan.updated",
                    "plan": plan,
                })
                
                # Update current plan step
                self.current_plan_step_id = None
                for step in plan:
                    if step.get("status") == "in_progress":
                        self.current_plan_step_id = step.get("id")
                        break
                        
                out = {"success": True, "plan": plan}
            else:
                out = {"success": False, "error": f"Unknown tool: '{tool_name}'"}
                
            done_event.set()
            await progress_task

            success = out.get("success", False)
            
            # Track diffs for verification
            if tool_name in ["write_file", "patch_file", "edit_file"] and success:
                path = kwargs.get("path", "")
                self.turn_diffs[path] = {
                    "diff": out.get("diff", ""),
                    "added": out.get("added", 0),
                    "removed": out.get("removed", 0),
                }

            duration = int((time.time() - start_time) * 1000)
            self._record_audit(
                event_id, tool_name, kwargs, risk_level, success=success,
                duration_ms=duration, error=out.get("error")
            )

            if success:
                # The summary is what the MODEL sees; `data` goes only to the UI.
                #
                # So the rule is not "always be terse" — it is: omit anything the
                # model already knows, include anything it asked for. A write
                # does not need its own diff echoed back. A read is worthless
                # without the content, and a command is worthless without its
                # output. Returning bare status lines for reads left the agent
                # blind, which it worked around by re-reading and then falling
                # back to `cat` — which returned a bare status line too.
                summary = f"Tool {tool_name} completed successfully."

                if tool_name == "read_file":
                    lines_text = (
                        f"lines {out.get('range')[0]}-{out.get('range')[1]} of {out.get('total_lines')}"
                        if "range" in out else ""
                    )
                    header = f"Read {kwargs.get('path')} {lines_text}".strip()
                    summary = f"{header}\n\n{_clip(out.get('content', ''))}"

                elif tool_name in ("write_file", "patch_file", "edit_file"):
                    # Deliberately no diff — the model just authored this.
                    summary = f"Wrote {kwargs.get('path')} (+{out.get('added', 0)}/-{out.get('removed', 0)})"

                elif tool_name in ("run_command", "execute", "shell"):
                    if "exit_code" in out:
                        parts = [f"Command finished with code {out.get('exit_code')}"]
                        stdout = (out.get("stdout") or "").strip()
                        stderr = (out.get("stderr") or "").strip()
                        if stdout:
                            parts.append(_clip(stdout))
                        if stderr:
                            parts.append(f"stderr:\n{_clip(stderr)}")
                        if not stdout and not stderr:
                            parts.append("(no output)")
                        summary = "\n\n".join(parts)
                    else:
                        summary = f"Started background process {out.get('process_id') or 'dev_server'}"

                elif tool_name == "list_dir":
                    entries = out.get("entries") or out.get("items") or []
                    # DirectoryItem uses `type` with the values "file"/"directory".
                    rendered = "\n".join(
                        f"  {e.get('name')}{'/' if e.get('type') == 'directory' else ''}"
                        if isinstance(e, dict) else f"  {e}"
                        for e in entries[:200]
                    )
                    summary = f"{kwargs.get('path') or '.'} ({len(entries)} entries)\n{rendered}"

                elif tool_name == "search":
                    matches = out.get("matches") or []
                    rendered = "\n".join(
                        f"  {m.get('file_path')}:{m.get('line_number')}: {str(m.get('line_content', '')).strip()}"
                        if isinstance(m, dict) else f"  {m}"
                        for m in matches[:100]
                    )
                    summary = (
                        f"{out.get('match_count', len(matches))} match(es) for "
                        f"'{kwargs.get('query')}'\n{_clip(rendered)}"
                    )
                elif tool_name == "verify_project":
                    status = "✅ PASSED" if out.get("success") else "❌ FAILED"
                    summary = f"Project Verification ({out.get('language')}): {status}\nChecks: {', '.join(out.get('checks_run', []))}"
                elif tool_name == "update_plan":
                    summary = f"Updated plan ({len(out.get('plan', []))} steps)"
                
                tool_result = ToolResult(
                    ok=True,
                    summary=summary,
                    data=out
                )
            else:
                err_msg = out.get("error", "Unknown error")
                tool_result = ToolResult(
                    ok=False,
                    summary=f"Error: {err_msg}",
                    data=out,
                    error_kind="error"
                )

            # Notify tool completed with real diff metrics
            await self._emit_event({
                "type": "agent.tool.completed",
                "tool_name": tool_name,
                "arguments": kwargs,
                "result": tool_result.model_dump(),
                "plan_step_id": self.current_plan_step_id,
            })

            # Cache successful reads only. A failed call should be retryable —
            # the condition that caused it may have been fixed since — and
            # mutations must always re-execute.
            if tool_result.ok and tool_name in ("read_file", "list_dir", "search", "list_processes"):
                self.turn_tool_cache[call_sig] = tool_result

            return tool_result

        except Exception as e:
            done_event.set()
            await progress_task
            duration = int((time.time() - start_time) * 1000)
            self._record_audit(
                event_id, tool_name, kwargs, risk_level, success=False,
                duration_ms=duration, error=str(e)
            )
            err_result = ToolResult(
                ok=False,
                summary=f"Tool execution failed: {str(e)}",
                data={"duration_ms": duration},
                error_kind="error"
            )
            await self._emit_event({
                "type": "agent.tool.failed",
                "tool_name": tool_name,
                "arguments": kwargs,
                "error": str(e),
                "plan_step_id": self.current_plan_step_id,
            })
            return err_result

    def _record_audit(
        self,
        event_id: str,
        tool_name: str,
        arguments: Dict[str, Any],
        risk_level: RiskLevel,
        success: bool,
        duration_ms: int,
        error: Optional[str] = None,
    ):
        event = AuditEvent(
            event_id=event_id,
            session_id=self.session_id,
            workspace_id=self.workspace_id,
            tool_name=tool_name,
            arguments=arguments,
            risk_level=risk_level,
            success=success,
            duration_ms=duration_ms,
            error=error,
        )
        self.audit_log.append(event)

        # Feed tool wall time into the turn meter. Every tool execution passes
        # through here, so it is the right single place to record it — and it
        # is what separates "tools are slow" from "we are making too many
        # sequential LLM round trips".
        try:
            from services.agent import metering
            metering.record_tool(duration_ms)
        except Exception:
            pass

        logger.info(f"AUDIT [{risk_level.upper()}] {tool_name} success={success} duration={duration_ms}ms error={error}")
