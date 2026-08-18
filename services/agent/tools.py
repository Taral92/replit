from typing import Any, Dict, List, Optional, Literal

try:
    from langchain_core.tools import tool
except ImportError:
    def tool(func):
        return func

from services.agent.gateway.tool_gateway import ToolGateway
from services.agent.verifier import ProjectVerifier
from packages.protocol.events import PlanStep


def create_agent_tools(gateway: ToolGateway):
    """
    Creates a suite of LangChain tools bound strictly to the provided ToolGateway.
    Ensures that LLMs never interact with the host filesystem or unmanaged processes.
    """

    @tool
    async def read_file(path: str, start_line: Optional[int] = None, end_line: Optional[int] = None) -> str:
        """Read the contents of a file in the workspace. Optionally specify a line range."""
        res = await gateway.execute_tool("read_file", path=path, start_line=start_line, end_line=end_line)
        return res.summary

    @tool
    async def write_file(path: str, content: str) -> str:
        """Write content to a file in the workspace. Automatically creates missing directories."""
        res = await gateway.execute_tool("write_file", path=path, content=content)
        return res.summary

    @tool
    async def edit_file(path: str, old: str, new: str) -> str:
        """Edit a file by finding a target block of code (old) and replacing it with (new)."""
        res = await gateway.execute_tool(
            "edit_file",
            path=path,
            old=old,
            new=new,
        )
        return res.summary

    @tool
    async def list_dir(path: str = "", recursive: bool = False) -> str:
        """List files and folders in the workspace directory."""
        res = await gateway.execute_tool("list_dir", path=path, recursive=recursive)
        return res.summary

    @tool
    async def search(query: str, path: str = "", kind: str = "content") -> str:
        """Search for a string across workspace files (ignores node_modules/git). Kind can be 'content' or 'filename'."""
        res = await gateway.execute_tool("search", query=query, path=path, kind=kind)
        return res.summary

    @tool
    async def shell(command: str, cwd: Optional[str] = None, timeout_ms: Optional[int] = 60000, background: bool = False) -> str:
        """Execute a shell command. Set background=True for long-running servers. Kills can be run as shell('kill <pid>')."""
        res = await gateway.execute_tool(
            "shell",
            command=command,
            cwd=cwd,
            timeout_ms=timeout_ms,
            background=background
        )
        return res.summary

    @tool
    async def list_processes() -> str:
        """List all active and stopped background processes and their listening ports."""
        res = await gateway.execute_tool("list_processes")
        return res.summary

    @tool
    async def verify_project() -> str:
        """Automatically verify the current workspace by running project-specific tests and builds."""
        res = await gateway.execute_tool("verify_project")
        return res.summary

    @tool
    async def update_plan(plan: List[PlanStep], explanation: Optional[str] = None) -> str:
        """Create or revise the task plan. Call this before starting work, and again whenever the plan changes. Each step has: id, title, status."""
        plan_dicts = [p.model_dump() for p in plan]
        res = await gateway.execute_tool("update_plan", plan=plan_dicts, explanation=explanation)
        return res.summary

    @tool
    async def ask_user(question: str, options: List[str]) -> str:
        """Ask the user a single blocking question and wait for their answer.

        Use ONLY when the workspace is empty and a choice is expensive to reverse
        (framework, language, or architecture) and the request does not already
        imply an answer. Provide 2-4 concrete options.

        Do NOT use this to confirm work you have already done, to ask permission
        to proceed, or for anything a sensible default covers. Asking has a real
        cost: it stops the run and waits for a human.
        """
        from services.agent.interaction import broker

        opts = [str(o) for o in (options or [])][:4]
        if len(opts) < 2:
            return "ask_user requires at least two concrete options. Decide yourself instead."

        return await broker.ask(
            session_id=gateway.session_id,
            question=str(question),
            options=opts,
            emit=gateway._emit_event,
        )

    return [
        read_file,
        write_file,
        edit_file,
        list_dir,
        search,
        shell,
        list_processes,
        verify_project,
        update_plan,
        ask_user,
    ]




