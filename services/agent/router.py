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

    # Set when a provider returns an authentication error. A configured-but-
    # invalid key would otherwise route every request to a provider that can
    # only 401, while a working provider sits unused.
    _anthropic_disabled: bool = False
    _anthropic_disabled_reason: str = ""

    @classmethod
    def disable_anthropic(cls, reason: str = "authentication failed") -> None:
        """Mark Anthropic unusable for the rest of this process."""
        if not cls._anthropic_disabled:
            print(
                f"[Model Router] Anthropic disabled ({reason}). "
                f"Falling back to {settings.DEFAULT_AGENT_MODEL} for all routes."
            )
        cls._anthropic_disabled = True
        cls._anthropic_disabled_reason = reason

    @classmethod
    def anthropic_available(cls) -> bool:
        """
        True if Claude is reachable at all.

        In Bedrock mode there is no ANTHROPIC_API_KEY — AWS credentials carry
        the auth — so the key check would otherwise route every coding task to
        OpenAI and the Bedrock branch would never be hit.
        """
        if settings.bedrock_mode:
            return True
        return bool(settings.ANTHROPIC_API_KEY) and not cls._anthropic_disabled

    @classmethod
    def is_conversational_query(cls, prompt: str, has_history: bool = False) -> bool:
        """
        True if this can be answered by a single stateless reply.

        `has_history` matters enormously. The fast path does NOT load the
        conversation thread — it sends one system message and the user's text,
        nothing else. That is correct for "hi" on an empty session and badly
        wrong for "continue" after the agent stopped at the iteration cap: the
        reply came back as "I don't see any previous context", because there
        genuinely wasn't any.

        So once a conversation exists, only unmistakable social phrases take the
        fast path. Anything short and ambiguous — "continue", "yes", "1", "go
        on" — is a continuation of work and must reach the main loop with the
        thread attached.
        """
        trimmed = prompt.strip()
        if not trimmed:
            return True

        if CONVERSATIONAL_PATTERNS.search(trimmed):
            if not CODING_ACTION_PATTERNS.search(trimmed):
                return True

        # The short-input heuristic is only safe on a fresh session. With
        # history present it swallows every terse follow-up.
        if not has_history:
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

        # 0. Local mode short-circuit. An Ollama/LM Studio endpoint serves one
        # model, so routing between providers is meaningless — and asking for
        # "gpt-4o" against localhost:11434 would just 404.
        if settings.local_mode:
            return settings.LOCAL_MODEL, f"🖥️ Local Model ({settings.LOCAL_MODEL})"

        # 0b. Bedrock mode: every request goes to AWS, nothing to OpenAI or the
        # Anthropic API. Short-circuited here rather than filtered later because
        # several branches below hardcode OpenAI model names — the deep-debug
        # path returns "gpt-4o" outright, and the conversational fast path uses
        # FAST_AGENT_MODEL. Either would silently bill a second provider.
        if settings.bedrock_mode:
            return settings.BEDROCK_MODEL, f"☁️ Bedrock ({settings.BEDROCK_MODEL})"

        # 1. Manual user override
        if requested_model and requested_model != "auto":
            clean_model = requested_model.lower()
            if "mini" in clean_model and "o3" not in clean_model:
                return "gpt-4o-mini", "Manual Selection (Fast & Cheap)"
            elif "o3" in clean_model:
                return "o3-mini", "Manual Selection (Deep Reasoning)"
            elif "sonnet" in clean_model or "claude" in clean_model:
                if cls.anthropic_available():
                    return settings.ANTHROPIC_MODEL, f"Manual Selection ({settings.ANTHROPIC_MODEL})"
                return "gpt-4o", "Manual Selection (GPT-4o — Anthropic unavailable)"
            elif "4o" in clean_model:
                return "gpt-4o", "Manual Selection (GPT-4o)"
            
            return settings.default_model, f"Manual Selection (Fallback: '{requested_model}' is unsupported/deprecated)"

        # 2. Conversational greetings
        if cls.is_conversational_query(trimmed):
            return settings.fast_model, "⚡ Auto Router: Routed to Fast Model (Conversational Query)"

        if SIMPLE_QUERY_PATTERNS.search(trimmed):
            return settings.fast_model, "⚡ Auto Router: Routed to Fast Model (Workspace Inspection)"

        # 3. Deep Reasoning & Error Debugging
        if DEEP_DEBUG_PATTERNS.search(trimmed):
            return settings.default_model, "🧠 Auto Router: High-Precision Model (Error Debugging)"

        # 4. Standard Feature Coding & Implementation
        if cls.anthropic_available():
            return (
                settings.ANTHROPIC_MODEL,
                f"🏆 Auto Router: Routed to {settings.ANTHROPIC_MODEL} (Feature Coding)",
            )

        return (
            settings.DEFAULT_AGENT_MODEL,
            f"⚡ Auto Router: Routed to {settings.DEFAULT_AGENT_MODEL} (Feature Coding)",
        )
