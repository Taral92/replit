from typing import Any, Dict, List, Optional

try:
    from langchain_core.tools import tool
except ImportError:
    def tool(func):
        return func

from services.agent.gateway.tool_gateway import ToolGateway
from services.agent.verifier import ProjectVerifier


def create_agent_tools(gateway: ToolGateway):
    """
    Creates a suite of LangChain tools bound strictly to the provided ToolGateway.
    Ensures that LLMs never interact with the host filesystem or unmanaged processes.
    """

    @tool
    async def read_file(path: str) -> str:
        """Read the contents of a file in the workspace."""
        res = await gateway.execute_tool("read_file", path=path)
        if not res.get("success"):
            return f"Error reading file: {res.get('error')}"
        if res.get("is_binary"):
            return f"[Binary file, size: {res.get('size_bytes')} bytes]"
        return res.get("content", "")

    @tool
    async def write_file(path: str, content: str) -> str:
        """Write content to a file in the workspace. Automatically creates missing directories."""
        res = await gateway.execute_tool("write_file", path=path, content=content)
        if not res.get("success"):
            return f"Error writing file: {res.get('error')}"
        return f"Successfully wrote {path} (+{res.get('added', 0)} / -{res.get('removed', 0)} lines).\nDiff:\n{res.get('diff', '')}"

    @tool
    async def patch_file(path: str, target_content: str, replacement_content: str) -> str:
        """Patch a file by finding a target block of code and replacing it."""
        res = await gateway.execute_tool(
            "patch_file",
            path=path,
            target_content=target_content,
            replacement_content=replacement_content,
        )
        if not res.get("success"):
            return f"Error patching file: {res.get('error')}"
        return f"Successfully patched {path}.\nDiff:\n{res.get('diff', '')}"

    @tool
    async def list_dir(path: str = "", recursive: bool = False) -> str:
        """List files and folders in the workspace directory."""
        res = await gateway.execute_tool("list_dir", path=path, recursive=recursive)
        if not res.get("success"):
            return f"Error listing directory: {res.get('error')}"
        items = res.get("items", [])
        if not items:
            return f"Directory '{path}' is empty."
        output = [f"{'📁' if item['type'] == 'directory' else '📄'} {item['path']}" for item in items]
        return "\n".join(output)

    @tool
    async def search(query: str, path: str = "") -> str:
        """Search for a string across workspace files (ignores node_modules/git)."""
        res = await gateway.execute_tool("search", query=query, path=path)
        if not res.get("success"):
            return f"Error searching: {res.get('error')}"
        matches = res.get("matches", [])
        if not matches:
            return f"No matches found for query '{query}'."
        lines = [f"{m['file_path']}:{m['line_number']} | {m['line_content'].strip()}" for m in matches]
        return "\n".join(lines)

    @tool
    async def run_command(command: str, timeout_seconds: Optional[int] = 60) -> str:
        """Execute a short-lived shell command in the workspace (e.g. 'npm install', 'git status')."""
        res = await gateway.execute_tool("run_command", command=command, timeout_seconds=timeout_seconds)
        if not res.get("success"):
            return f"Command failed or error: {res.get('error')}\nStdout:\n{res.get('stdout', '')}\nStderr:\n{res.get('stderr', '')}"
        out = (res.get("stdout", "") + "\n" + res.get("stderr", "")).strip()
        return f"Command finished with code {res.get('exit_code')}.\nOutput:\n{out}"

    @tool
    async def start_process(command: str, cwd: Optional[str] = None) -> str:
        """Start a long-running background development server process (e.g. 'npm run dev', 'uvicorn app:main')."""
        res = await gateway.execute_tool("start_process", command=command, cwd=cwd)
        if not res.get("success") and "process_id" not in res:
            return f"Error starting process: {res.get('error')}"
        return f"Started background process {res.get('process_id')} (PID: {res.get('pid')}) for command: '{command}'"

    @tool
    async def stop_process(process_id: str) -> str:
        """Stop a running background process by ID."""
        res = await gateway.execute_tool("stop_process", process_id=process_id)
        if res.get("success"):
            return f"Process {process_id} stopped successfully."
        return f"Failed to stop process {process_id}."

    @tool
    async def get_processes() -> str:
        """List all active and stopped background processes and their listening ports."""
        res = await gateway.execute_tool("get_processes")
        procs = res.get("processes", [])
        if not procs:
            return "No background processes currently running."
        lines = [f"[{p['status']}] {p['process_id']} (PID {p.get('pid')}) - '{p['command']}' (Ports: {', '.join(p.get('ports', []))})" for p in procs]
        return "\n".join(lines)

    @tool
    async def start_dev_server(command: str = "npm run dev", port: int = 3000, cwd: Optional[str] = None) -> str:
        """Start the single-owner development server and await verified HTTP readiness."""
        sandbox = getattr(gateway, "sandbox", None)
        if sandbox and hasattr(sandbox, "server_manager"):
            res = await sandbox.server_manager.start(command=command, target_port=port, cwd=cwd)
            if res.get("success"):
                return f"✅ Dev server is healthy and running on {res.get('url')} (PID {res.get('pid')})."
            return f"❌ Failed to start dev server: {res.get('message')}\nError/Logs:\n{res.get('error')}"
        return "Dev server manager not available in sandbox."

    @tool
    async def stop_dev_server() -> str:
        """Stop the workspace development server."""
        sandbox = getattr(gateway, "sandbox", None)
        if sandbox and hasattr(sandbox, "server_manager"):
            res = await sandbox.server_manager.stop()
            return f"Dev server stopped ({res.get('state')})."
        return "Dev server manager not available."

    @tool
    async def get_server_status() -> str:
        """Get the current live health and state of the workspace development server ('stopped', 'starting', 'running', 'crashed')."""
        sandbox = getattr(gateway, "sandbox", None)
        if sandbox and hasattr(sandbox, "server_manager"):
            st = sandbox.server_manager.get_status()
            if st.get("state") == "running":
                return f"Server is RUNNING on {st.get('url')} (PID {st.get('pid')})."
            elif st.get("state") == "starting":
                return "Server is currently STARTING up and awaiting HTTP readiness."
            elif st.get("state") == "crashed":
                return f"Server is CRASHED.\nError:\n{st.get('error')}"
            else:
                return "Server is STOPPED."
        return "Dev server manager not available."

    @tool
    async def verify_project() -> str:
        """Automatically verify the current workspace by running project-specific tests and builds."""
        result = await ProjectVerifier.verify(gateway.sandbox)
        status = "✅ PASSED" if result.passed else "❌ FAILED"
        return f"Project Verification ({result.language}): {status}\nChecks: {', '.join(result.checks_run)}\nDetails:\n{result.details}"

    return [
        read_file,
        write_file,
        patch_file,
        list_dir,
        search,
        run_command,
        start_dev_server,
        stop_dev_server,
        get_server_status,
        start_process,
        stop_process,
        get_processes,
        verify_project,
    ]
