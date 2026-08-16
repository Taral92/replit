import os
from pathlib import Path
from typing import List, Optional
from dotenv import load_dotenv
from pydantic import BaseModel, Field

# Load environment from project root
_project_root = Path(__file__).resolve().parent.parent.parent
load_dotenv(_project_root / ".env")


class Settings(BaseModel):
    # App & Environment
    ENV: str = Field(default="development")
    DEBUG: bool = Field(default=True)
    HOST: str = Field(default="0.0.0.0")
    PORT: int = Field(default=8000)

    # Workspaces & Filesystem
    PROJECT_ROOT: Path = Field(default_factory=lambda: _project_root)
    BASE_WORKSPACE_DIR: Path = Field(
        default_factory=lambda: Path(
            os.environ.get("WORKSPACE_DIR", _project_root / "workspaces")
        )
    )

    # Security & CORS
    CORS_ORIGINS: List[str] = Field(
        default_factory=lambda: [
            "http://localhost:5173",
            "http://localhost:3000",
            "http://127.0.0.1:5173",
            "http://127.0.0.1:3000",
        ]
    )
    MAX_FILE_SIZE_BYTES: int = Field(default=5 * 1024 * 1024)  # 5MB
    COMMAND_TIMEOUT_SECONDS: int = Field(default=60)
    MAX_OUTPUT_CHARS: int = Field(default=10000)

    # LLM Settings
    OPENAI_API_KEY: Optional[str] = Field(default_factory=lambda: os.getenv("OPENAI_API_KEY"))
    ANTHROPIC_API_KEY: Optional[str] = Field(default_factory=lambda: os.getenv("ANTHROPIC_API_KEY"))
    ANTHROPIC_MODEL: str = Field(default=os.getenv("ANTHROPIC_MODEL", "claude-3-5-sonnet-latest"))
    DEFAULT_AGENT_MODEL: str = Field(default="gpt-4o")
    FAST_AGENT_MODEL: str = Field(default="gpt-4o-mini")

    # Database & Redis
    DATABASE_URL: str = Field(default=os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./runner_ide.db"))
    REDIS_URL: str = Field(default=os.getenv("REDIS_URL", "redis://localhost:6379/0"))

    # S3 Storage
    S3_BUCKET: str = Field(default=os.getenv("S3_BUCKET", "runner-ide-workspace-data-v1"))
    AWS_REGION: str = Field(default=os.getenv("AWS_REGION", "us-east-1"))

    # System & Host Ports (Excluded from workspace preview)
    SYSTEM_PORTS: List[str] = Field(default_factory=lambda: ["8000", "5173", "5000", "7000"])

    def get_workspace_dir_for_session(self, session_id: Optional[str] = None, workspace_id: Optional[str] = None) -> Path:
        """
        Returns the workspace directory.
        Defaults to BASE_WORKSPACE_DIR so project files are persistent across socket reconnects.
        If an explicit non-default workspace_id is provided, scopes to that directory.
        """
        if workspace_id and workspace_id != "default":
            clean_id = "".join(c for c in workspace_id if c.isalnum() or c in ("-", "_"))
            target = self.BASE_WORKSPACE_DIR / clean_id
        else:
            target = self.BASE_WORKSPACE_DIR

        target.mkdir(parents=True, exist_ok=True)
        return target.resolve()


settings = Settings()
