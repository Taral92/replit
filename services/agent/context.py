from typing import Any, Dict, List

try:
    from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
except ImportError:
    class BaseMessage:
        def __init__(self, content: Any = ""):
            self.content = content

    class SystemMessage(BaseMessage):
        pass

    class HumanMessage(BaseMessage):
        pass

    class AIMessage(BaseMessage):
        pass

    class ToolMessage(BaseMessage):
        def __init__(self, content: Any = "", tool_call_id: str = "default_id"):
            super().__init__(content)
            self.tool_call_id = tool_call_id


SYSTEM_INSTRUCTIONS = """You are RunnerIDE Autonomous AI Agent, an industry-grade coding assistant operating in a secure workspace sandbox.

### CRITICAL RULES:
1. For any task involving code or files, always use tools to verify contents before modifying them — never assume file contents or past results without re-checking via a tool call this turn.
2. PRESERVE EXISTING CODE: When modifying code or adding features, PRESERVE all working logic, state, and functionality. Never rewrite whole files when surgical edits suffice.
3. SURGICAL PATCHING: Always prefer `patch_file` for targeted changes. Use `write_file` only for brand new files or complete restructures.
4. MODERN UI & STYLING ARCHITECTURE:
   - Coordinate changes across `globals.css` (custom CSS, animations) and component/page files (JSX classes).
   - Ensure clean background hierarchy and responsive viewport support.
5. CODE RELIABILITY: When adding packages, install dependencies with `run_command` (e.g. `npm install ...`).
6. Do not invent details; use your tools to explore the workspace live.
7. Anti-hallucination grounding: Never state that something was verified, tested, fixed, or confirmed unless a tool call in this turn produced that result. If you haven't checked, say what you changed and that it's unverified — don't claim confidence you don't have.

### STANDARD WORKFLOW:
1. EXPLORE: live workspace structure (`list_dir`, `read_file`, `grep_search`).
2. PLAN: identify all files needing modification to deliver a complete, visible UI result.
3. IMPLEMENT: apply clean edits using `patch_file` or `write_file`.
4. VERIFY: confirm that the implementation satisfies the task requirements.
5. COMPLETE: report a concise summary of the changes to the user.
"""


class ContextManager:
    """
    Manages LLM context window budgeting, history pruning, and token tracking.
    Prevents token explosion from large file reads and tool outputs.
    """

    MAX_RECENT_MESSAGES = 12
    MAX_TOOL_OUTPUT_CHARS = 4000

    @classmethod
    def prune_messages(cls, messages: List[BaseMessage]) -> List[BaseMessage]:
        """
        Prunes message history to stay strictly within token budget.
        Always retains System Instructions, original user prompt, and recent tool exchanges.
        """
        if not messages:
            return [SystemMessage(content=SYSTEM_INSTRUCTIONS)]

        pruned: List[BaseMessage] = [SystemMessage(content=SYSTEM_INSTRUCTIONS)]

        # If there is a root human message, preserve it
        user_messages = [m for m in messages if isinstance(m, HumanMessage)]
        if user_messages and user_messages[0] not in messages[-cls.MAX_RECENT_MESSAGES:]:
            pruned.append(user_messages[0])

        recent = messages[-cls.MAX_RECENT_MESSAGES:]

        for msg in recent:
            if isinstance(msg, ToolMessage):
                content_str = str(msg.content)
                tool_id = getattr(msg, "tool_call_id", "default_id")
                if len(content_str) > cls.MAX_TOOL_OUTPUT_CHARS:
                    truncated = (
                        content_str[: cls.MAX_TOOL_OUTPUT_CHARS]
                        + f"\n... [Output truncated ({len(content_str)} chars)]"
                    )
                    pruned.append(ToolMessage(content=truncated, tool_call_id=tool_id))
                else:
                    pruned.append(msg)
            elif isinstance(msg, AIMessage):
                content_str = str(msg.content)
                tool_calls = getattr(msg, "tool_calls", None)
                if len(content_str) > cls.MAX_TOOL_OUTPUT_CHARS:
                    truncated = (
                        content_str[: cls.MAX_TOOL_OUTPUT_CHARS]
                        + f"\n... [Output truncated ({len(content_str)} chars)]"
                    )
                    pruned.append(AIMessage(content=truncated, tool_calls=tool_calls or []))
                else:
                    pruned.append(msg)
            elif not isinstance(msg, SystemMessage):
                pruned.append(msg)

        return pruned
