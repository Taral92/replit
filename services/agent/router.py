import os
import re
from typing import Optional, Tuple
from packages.config import settings

# Conversational & Greeting Patterns
CONVERSATIONAL_PATTERNS = re.compile(
    r"^(hi|hello|hey|yo|sup|whats\s*up|what\'?s\s*up|howdy|good\s*(morning|afternoon|evening|day)|"
    r"who\s*are\s*you|what\s*are\s*you|what\s*can\s*you\s*do|how\s*are\s*you|how\s*do\s*you\s*work|"
    r"thanks|thank\s*you|help|test|ping)\b",
    re.IGNORECASE,
)

# Explicit Coding & Modification Keywords
CODING_ACTION_PATTERNS = re.compile(
    r"\b(create|make|build|add|implement|fix|refactor|update|edit|write|patch|delete|remove|"
    r"install|run|start|deploy|change|replace|generate|wire|connect|setup|configure|"
    r"page|component|route|endpoint|button|style|css|tsx|jsx|html|js|py|sql|api)\b",
    re.IGNORECASE,
)

SIMPLE_QUERY_PATTERNS = re.compile(
    r"\b(what files|list files|show files|directory structure|what is this project|how do i run|what port|status)\b",
    re.IGNORECASE,
)

DEEP_DEBUG_PATTERNS = re.compile(
    r"(traceback|typeerror|referenceerror|syntaxerror|runtimeerror|cannot read properties|uncaught exception|failed with exit code|unhandled exception|build failed)",
    re.IGNORECASE,
)


class ModelRouter:
    """
    Intelligent Multi-Provider Model Router & Intent Classifier.
    Distinguishes casual conversational queries from active engineering tasks.
    """

    @classmethod
    def is_conversational_query(cls, prompt: str) -> bool:
        """
        Determines if a prompt is a pure conversational question / greeting
        that does not require editing files, generating checklists, or auditing diffs.
        """
        trimmed = prompt.strip()
        if not trimmed:
            return True

        # If it explicitly matches conversational greetings/questions and doesn't ask for coding actions
        if CONVERSATIONAL_PATTERNS.search(trimmed):
            if not CODING_ACTION_PATTERNS.search(trimmed):
                return True

        # Very short non-command inputs (e.g. "ok", "cool", "nice", "hello there")
        words = trimmed.split()
        if len(words) <= 3 and not CODING_ACTION_PATTERNS.search(trimmed):
            return True

        return False

    @classmethod
    def route(cls, prompt: str, requested_model: Optional[str] = "auto") -> Tuple[str, str]:
        """
        Returns (resolved_model_name, reasoning_description).
        """
        trimmed = prompt.strip()

        # 1. Manual user override
        if requested_model and requested_model != "auto":
            clean_model = requested_model.lower()
            if "mini" in clean_model and "o3" not in clean_model:
                return "gpt-4o-mini", "Manual Selection (Fast & Cheap)"
            elif "o3" in clean_model:
                return "o3-mini", "Manual Selection (Deep Reasoning)"
            elif "sonnet" in clean_model or "claude" in clean_model:
                if settings.ANTHROPIC_API_KEY:
                    return settings.ANTHROPIC_MODEL, "Manual Selection (Claude 3.5 Sonnet)"
                return "gpt-4o", "Manual Selection (GPT-4o)"
            elif "4o" in clean_model:
                return "gpt-4o", "Manual Selection (GPT-4o)"
            return requested_model, "Manual Selection"

        # 2. Conversational greetings
        if cls.is_conversational_query(trimmed):
            return settings.FAST_AGENT_MODEL, "⚡ Auto Router: Routed to Fast Model (Conversational Query)"

        if SIMPLE_QUERY_PATTERNS.search(trimmed):
            return settings.FAST_AGENT_MODEL, "⚡ Auto Router: Routed to Fast Model (Workspace Inspection)"

        # 3. Deep Reasoning & Error Debugging
        if DEEP_DEBUG_PATTERNS.search(trimmed):
            return "gpt-4o", "🧠 Auto Router: Routed to High-Precision Model (Error Debugging)"

        # 4. Standard Feature Coding & Implementation
        if settings.ANTHROPIC_API_KEY:
            return settings.ANTHROPIC_MODEL, "🏆 Auto Router: Routed to Claude 3.5 Sonnet (Feature Coding)"

        return settings.DEFAULT_AGENT_MODEL, "⚡ Auto Router: Routed to GPT-4o (Feature Coding)"
