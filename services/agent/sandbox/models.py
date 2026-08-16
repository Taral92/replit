from typing import List, Optional
from pydantic import BaseModel, Field


class FileReadResult(BaseModel):
    success: bool
    path: str
    content: Optional[str] = None
    error: Optional[str] = None
    is_binary: bool = False
    size_bytes: int = 0


class FileWriteResult(BaseModel):
    success: bool
    path: str
    diff: Optional[str] = None
    added: int = 0
    removed: int = 0
    error: Optional[str] = None


class FilePatchResult(BaseModel):
    success: bool
    path: str
    diff: Optional[str] = None
    added: int = 0
    removed: int = 0
    error: Optional[str] = None


class DirectoryItem(BaseModel):
    name: str
    path: str
    type: str  # "file" or "directory"
    size_bytes: Optional[int] = None
    children: Optional[List["DirectoryItem"]] = None


DirectoryItem.model_rebuild()


class DirectoryResult(BaseModel):
    success: bool
    path: str
    items: List[DirectoryItem] = Field(default_factory=list)
    error: Optional[str] = None


class SearchMatch(BaseModel):
    file_path: str
    line_number: int
    line_content: str


class SearchResult(BaseModel):
    success: bool
    query: str
    matches: List[SearchMatch] = Field(default_factory=list)
    match_count: int = 0
    truncated: bool = False
    error: Optional[str] = None


class CommandResult(BaseModel):
    success: bool
    command: str
    exit_code: Optional[int] = None
    stdout: str = ""
    stderr: str = ""
    duration_ms: int = 0
    truncated: bool = False
    error: Optional[str] = None


class ProcessInfo(BaseModel):
    process_id: str
    command: str
    pid: Optional[int] = None
    status: str  # "STARTING", "RUNNING", "STOPPED", "FAILED"
    started_at: str
    exit_code: Optional[int] = None
    ports: List[str] = Field(default_factory=list)


class PortInfo(BaseModel):
    port: str
    process_id: Optional[str] = None
    detected_at: str
