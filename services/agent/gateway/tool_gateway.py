import asyncio
import logging
import time
from typing import Any, Callable, Dict, List, Optional
from uuid import uuid4

from services.agent.sandbox.base import Sandbox
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

    def set_approval_callback(self, callback: Callable[[str, RiskLevel, str], bool]):
        self.approval_callback = callback

    def set_event_callback(self, callback: Callable[[Dict[str, Any]], Any]):
        self.event_callback = callback

    def reset_turn_diffs(self):
        """Resets the accumulated diffs for a new turn."""
        self.turn_diffs.clear()

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

    async def execute_tool(self, tool_name: str, **kwargs) -> Dict[str, Any]:
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
        })

        # 1. Policy Assessment
        risk_level: RiskLevel = "safe"
        rationale = "Standard tool invocation"

        if tool_name in ("run_command", "execute"):
            cmd = kwargs.get("command", "")
            risk_level, rationale = PolicyEngine.classify_command(cmd)
        elif tool_name in ("write_file", "patch_file"):
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
                    err_out = {
                        "success": False,
                        "error": f"Security Error: Operation requiring approval was rejected ({rationale}).",
                        "risk_level": risk_level,
                    }
                    await self._emit_event({
                        "type": "agent.tool.failed",
                        "tool_name": tool_name,
                        "arguments": kwargs,
                        "error": err_out["error"],
                    })
                    return err_out

        # 3. Sandbox Delegation
        try:
            if tool_name == "read_file":
                res = await self.sandbox.read_file(kwargs.get("path", ""))
                out = res.model_dump()
            elif tool_name == "write_file":
                res = await self.sandbox.write_file(kwargs.get("path", ""), kwargs.get("content", ""))
                out = res.model_dump()
            elif tool_name == "patch_file":
                res = await self.sandbox.patch_file(
                    kwargs.get("path", ""),
                    kwargs.get("target_content", ""),
                    kwargs.get("replacement_content", ""),
                )
                out = res.model_dump()
            elif tool_name == "list_dir":
                res = await self.sandbox.list_dir(kwargs.get("path", ""), kwargs.get("recursive", False))
                out = res.model_dump()
            elif tool_name == "search":
                res = await self.sandbox.search(kwargs.get("query", ""), kwargs.get("path", ""))
                out = res.model_dump()
            elif tool_name in ("run_command", "execute"):
                res = await self.sandbox.execute(kwargs.get("command", ""), kwargs.get("timeout_seconds"))
                out = res.model_dump()
            elif tool_name == "start_process":
                res = await self.sandbox.start_process(kwargs.get("command", ""), kwargs.get("cwd"))
                out = res.model_dump()
            elif tool_name == "stop_process":
                success = await self.sandbox.stop_process(kwargs.get("process_id", ""))
                out = {"success": success}
            elif tool_name == "get_processes":
                procs = await self.sandbox.get_processes()
                out = {"success": True, "processes": [p.model_dump() for p in procs]}
            elif tool_name == "get_ports":
                ports = await self.sandbox.get_ports()
                out = {"success": True, "ports": [p.model_dump() for p in ports]}
            else:
                out = {"success": False, "error": f"Unknown tool: '{tool_name}'"}

            # Track diffs for verification
            if tool_name in ["write_file", "patch_file"] and out.get("success"):
                path = kwargs.get("path", "")
                self.turn_diffs[path] = {
                    "diff": out.get("diff", ""),
                    "added": out.get("added", 0),
                    "removed": out.get("removed", 0),
                }

            duration = int((time.time() - start_time) * 1000)
            self._record_audit(
                event_id, tool_name, kwargs, risk_level, success=out.get("success", False),
                duration_ms=duration, error=out.get("error")
            )

            # Notify tool completed with real diff metrics
            await self._emit_event({
                "type": "agent.tool.completed",
                "tool_name": tool_name,
                "arguments": kwargs,
                "result": out,
            })

            return out

        except Exception as e:
            duration = int((time.time() - start_time) * 1000)
            self._record_audit(
                event_id, tool_name, kwargs, risk_level, success=False,
                duration_ms=duration, error=str(e)
            )
            err_dict = {"success": False, "error": f"Tool execution failed: {str(e)}", "duration_ms": duration}
            await self._emit_event({
                "type": "agent.tool.failed",
                "tool_name": tool_name,
                "arguments": kwargs,
                "error": str(e),
            })
            return err_dict

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
        logger.info(f"AUDIT [{risk_level.upper()}] {tool_name} success={success} duration={duration_ms}ms error={error}")
