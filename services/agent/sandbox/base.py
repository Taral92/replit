from abc import ABC, abstractmethod
from typing import List, Optional
from .models import (
    CommandResult,
    DirectoryResult,
    FilePatchResult,
    FileReadResult,
    FileWriteResult,
    PortInfo,
    ProcessInfo,
    SearchResult,
)


class Sandbox(ABC):
    """
    Abstract Execution Sandbox Interface.
    Intelligence is completely separated from Execution.
    The agent and control plane interact strictly with this interface.
    """

    @abstractmethod
    async def read_file(self, path: str) -> FileReadResult:
        """Read file contents safely within the sandbox."""
        pass

    @abstractmethod
    async def write_file(self, path: str, content: str) -> FileWriteResult:
        """Write file contents safely within the sandbox, generating a unified diff."""
        pass

    @abstractmethod
    async def patch_file(self, path: str, target_content: str, replacement_content: str) -> FilePatchResult:
        """Find and replace a specific content block within a file."""
        pass

    @abstractmethod
    async def list_dir(self, path: str = "", recursive: bool = False) -> DirectoryResult:
        """List files and folders within the sandbox directory."""
        pass

    @abstractmethod
    async def search(self, query: str, path: str = "") -> SearchResult:
        """Search across files within the sandbox safely without shell injection."""
        pass

    @abstractmethod
    async def execute(self, command: str, timeout_seconds: Optional[int] = None) -> CommandResult:
        """Execute a short-lived shell command within the sandbox with timeout."""
        pass

    @abstractmethod
    async def start_process(self, command: str, cwd: Optional[str] = None) -> ProcessInfo:
        """Start and track a long-running background process (e.g. dev server)."""
        pass

    @abstractmethod
    async def stop_process(self, process_id: str) -> bool:
        """Gracefully stop a running background process."""
        pass

    @abstractmethod
    async def get_processes(self) -> List[ProcessInfo]:
        """List all tracked active and stopped background processes."""
        pass

    @abstractmethod
    async def get_ports(self) -> List[PortInfo]:
        """Get currently active and detected server ports."""
        pass
