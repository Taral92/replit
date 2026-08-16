import os
import re
import shlex
from pathlib import Path
from typing import List, Literal, Optional, Set, Tuple

RiskLevel = Literal["safe", "restricted", "destructive", "privileged"]

# Command classification patterns
SAFE_COMMANDS: Set[str] = {
    "ls", "dir", "cat", "head", "tail", "grep", "rg", "find", "pwd", "echo",
    "git status", "git diff", "git log", "git show", "git branch",
    "npm test", "npm run test", "pytest", "ruff", "python -m unittest", "go test", "cargo test",
    "node -v", "npm -v", "python -v", "python --version"
}

RESTRICTED_COMMANDS: Set[str] = {
    "npm install", "npm i", "npm add", "npm run build", "npm run dev", "npm start",
    "pip install", "poetry install", "yarn add", "pnpm add",
    "git add", "git commit", "git checkout", "git switch",
    "mkdir", "touch", "cp", "mv"
}

DESTRUCTIVE_PATTERNS: List[re.Pattern] = [
    re.compile(r"\brm\s+(-[a-zA-Z]*r[a-zA-Z]*f*|-[a-zA-Z]*f*r[a-zA-Z]*)\s+"),
    re.compile(r"\brm\s+-[a-zA-Z]*\s+"),
    re.compile(r"\bgit\s+reset\s+--hard\b"),
    re.compile(r"\bgit\s+clean\s+-[a-zA-Z]*f\b"),
    re.compile(r"\bdrop\s+(database|table)\b", re.IGNORECASE),
    re.compile(r"\btruncate\s+table\b", re.IGNORECASE),
    re.compile(r"\bformat\s+[a-zA-Z]:", re.IGNORECASE),
    re.compile(r"\bmkfs\b"),
    re.compile(r"\bdd\s+if="),
]

PRIVILEGED_PATTERNS: List[re.Pattern] = [
    re.compile(r"\bsudo\b"),
    re.compile(r"\bsu\s+"),
    re.compile(r"\bchmod\s+[0-7]*[4-7][0-7]{2}\b"),
    re.compile(r"\bchown\b"),
    re.compile(r"\bchgrp\b"),
    re.compile(r"\buseradd\b"),
    re.compile(r"\bgroupadd\b"),
    re.compile(r"\bpasswd\b"),
    re.compile(r"\bshadow\b"),
    re.compile(r"\biptables\b"),
    re.compile(r"\bkubectl\b"),
    re.compile(r"\bdocker\b"),
]


class PolicyEngine:
    """
    Central Security & Authorization Policy Engine.
    Validates canonical paths, classifies commands, and identifies high-risk operations.
    """

    @staticmethod
    def resolve_and_validate_path(base_dir: Path, requested_path: str) -> Tuple[bool, Optional[Path], Optional[str]]:
        """
        Symlink-proof canonical path validator.
        Ensures the requested path strictly resolves within base_dir.
        Rejects absolute paths outside base_dir and relative directory traversal escapes.
        """
        try:
            raw_path = requested_path.strip()
            if not raw_path:
                return True, base_dir.resolve(), None

            base_resolved = base_dir.resolve()

            # If path is given as absolute or relative
            if os.path.isabs(raw_path):
                full_path = Path(raw_path).resolve()
            else:
                full_path = (base_dir / raw_path).resolve()

            # Check if resolved path is strictly within base_dir
            try:
                full_path.relative_to(base_resolved)
            except ValueError:
                return False, None, f"Path traversal denied: '{requested_path}' escapes workspace boundary."

            return True, full_path, None
        except Exception as e:
            return False, None, f"Invalid path resolution: {str(e)}"

    @staticmethod
    def classify_command(command: str) -> Tuple[RiskLevel, Optional[str]]:
        """
        Classifies a shell command into a RiskLevel and provides rationale.
        """
        trimmed = command.strip()
        if not trimmed:
            return "safe", "Empty command"

        # Check privileged commands first
        for pat in PRIVILEGED_PATTERNS:
            if pat.search(trimmed):
                return "privileged", f"Command matches privileged system execution rule: {pat.pattern}"

        # Check destructive commands
        for pat in DESTRUCTIVE_PATTERNS:
            if pat.search(trimmed):
                return "destructive", f"Command matches destructive deletion/reset rule: {pat.pattern}"

        # Check safe exact/prefix commands
        try:
            tokens = shlex.split(trimmed)
            binary = tokens[0] if tokens else ""
            two_words = f"{tokens[0]} {tokens[1]}" if len(tokens) >= 2 else binary
            three_words = f"{tokens[0]} {tokens[1]} {tokens[2]}" if len(tokens) >= 3 else two_words

            if three_words in SAFE_COMMANDS or two_words in SAFE_COMMANDS or binary in SAFE_COMMANDS:
                return "safe", "Standard read-only or test execution"

            if two_words in RESTRICTED_COMMANDS or binary in RESTRICTED_COMMANDS:
                return "restricted", "Build, package installation, or state modification"

        except Exception:
            pass

        # Unknown commands default to restricted for safety
        return "restricted", "Standard development command"

    @staticmethod
    def requires_human_approval(risk: RiskLevel) -> bool:
        """Determines if operation must be paused for human confirmation."""
        return risk in ("destructive", "privileged")
