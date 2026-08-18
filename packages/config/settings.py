import os
from pathlib import Path
from typing import List, Optional
from dotenv import load_dotenv
from pydantic import BaseModel, Field

# Load environment from project root.
#
# override=True is deliberate. By default load_dotenv leaves existing
# environment variables alone, so a stale value exported in the shell silently
# shadows .env — editing BEDROCK_MODEL in the file then appears to do nothing,
# because the old shell value keeps winning. For a local dev config file, .env
# should be the source of truth.
_project_root = Path(__file__).resolve().parent.parent.parent
load_dotenv(_project_root / ".env", override=True)


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
    # 5174/5175 are Vite's fallback ports when 5173 is occupied. Allowed so a
    # port collision degrades to a warning rather than a wall of CORS errors.
    CORS_ORIGINS: List[str] = Field(
        default_factory=lambda: [
            "http://localhost:5173",
            "http://localhost:5174",
            "http://localhost:5175",
            "http://localhost:3000",
            "http://127.0.0.1:5173",
            "http://127.0.0.1:5174",
            "http://127.0.0.1:5175",
            "http://127.0.0.1:3000",
        ]
    )
    MAX_FILE_SIZE_BYTES: int = Field(default=5 * 1024 * 1024)  # 5MB
    COMMAND_TIMEOUT_SECONDS: int = Field(default=60)
    MAX_OUTPUT_CHARS: int = Field(default=10000)

    # LLM Settings
    OPENAI_API_KEY: Optional[str] = Field(default_factory=lambda: os.getenv("OPENAI_API_KEY"))
    ANTHROPIC_API_KEY: Optional[str] = Field(default_factory=lambda: os.getenv("ANTHROPIC_API_KEY"))
    ANTHROPIC_MODEL: str = Field(default_factory=lambda: os.getenv("ANTHROPIC_MODEL", "claude-3-5-sonnet-latest"))
    DEFAULT_AGENT_MODEL: str = Field(default="gpt-4o")
    FAST_AGENT_MODEL: str = Field(default="gpt-4o-mini")

    # Local model support (Ollama, LM Studio, vLLM — anything OpenAI-compatible).
    # Set OPENAI_BASE_URL to http://localhost:11434/v1 to run everything locally
    # at zero API cost. When set, LOCAL_MODEL overrides all routing: a local
    # endpoint serves one model, so there is nothing to route between.
    OPENAI_BASE_URL: Optional[str] = Field(default_factory=lambda: os.getenv("OPENAI_BASE_URL"))
    LOCAL_MODEL: str = Field(default_factory=lambda: os.getenv("LOCAL_MODEL", "qwen2.5-coder:3b"))

    # AWS Bedrock — serve Claude through Bedrock instead of the Anthropic API,
    # so spend lands on AWS credits. Set USE_BEDROCK=true.
    #
    # Bedrock model IDs are NOT the same strings as the Anthropic API uses, and
    # the "us." prefix selects a cross-region inference profile (usually what
    # you want — higher throughput, fewer capacity errors).
    USE_BEDROCK: bool = Field(
        default_factory=lambda: os.getenv("USE_BEDROCK", "").lower() in ("1", "true", "yes")
    )
    BEDROCK_MODEL: str = Field(
        default_factory=lambda: os.getenv("BEDROCK_MODEL", "anthropic.claude-haiku-4-5-20251001-v1:0")
    )
    BEDROCK_REGION: str = Field(
        default_factory=lambda: os.getenv("BEDROCK_REGION", os.getenv("AWS_REGION", "us-east-1"))
    )

    @property
    def local_mode(self) -> bool:
        return bool(self.OPENAI_BASE_URL)

    @property
    def fast_model(self) -> str:
        """
        Model for cheap work — greetings, workspace questions, checklists.

        Resolves to whichever provider is actually configured. FAST_AGENT_MODEL
        is hardcoded to gpt-4o-mini, so without this a user running Claude still
        had every greeting billed to OpenAI, and every turn touched two
        providers.
        """
        if self.local_mode:
            return self.LOCAL_MODEL
        if self.bedrock_mode:
            return self.BEDROCK_MODEL
        if self.ANTHROPIC_API_KEY:
            return self.ANTHROPIC_MODEL
        return self.FAST_AGENT_MODEL

    @property
    def default_model(self) -> str:
        """Model for substantive work, resolved the same way."""
        if self.local_mode:
            return self.LOCAL_MODEL
        if self.bedrock_mode:
            return self.BEDROCK_MODEL
        if self.ANTHROPIC_API_KEY:
            return self.ANTHROPIC_MODEL
        return self.DEFAULT_AGENT_MODEL

    @property
    def bedrock_mode(self) -> bool:
        # Local mode wins — it is the explicit "no external calls" switch.
        return self.USE_BEDROCK and not self.local_mode

    # Database & Redis
    DATABASE_URL: str = Field(default_factory=lambda: os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./runner_ide.db"))
    REDIS_URL: str = Field(default_factory=lambda: os.getenv("REDIS_URL", "redis://localhost:6379/0"))

    # S3 Storage
    S3_BUCKET: str = Field(default_factory=lambda: os.getenv("S3_BUCKET", "runner-ide-workspace-data-v1"))
    AWS_REGION: str = Field(default_factory=lambda: os.getenv("AWS_REGION", "us-east-1"))

    # System & Host Ports (Excluded from workspace preview)
    # Ports belonging to RunnerIDE itself. Excluded from dev-server port
    # probing so the Preview pane never offers the IDE's own UI as the
    # user's running app.
    SYSTEM_PORTS: List[str] = Field(
        default_factory=lambda: ["8000", "5173", "5174", "5175", "5000", "7000"]
    )

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
