import logging
from typing import Any, Dict, List

from packages.config import settings

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


logger = logging.getLogger("RunnerIDE-Context")

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
8. DO NOT CREATE UNSOLICITED DOCUMENTATION. Never create README.md, QUICKSTART.md, PROJECT_SUMMARY.md, FEATURES.md, START_HERE.md, BUILD_SUMMARY.md, or any other documentation file unless the user explicitly requested documentation. Build only what was asked for. This is a hard prohibition.
9. FRAMEWORK AWARENESS: When working with Next.js, check if the project uses the App Router (`app/`) or Pages Router (`pages/`). Strictly adhere to the existing router. Never create `pages/` files in an App Router project, or vice versa, as this will break the build.

10. BATCH INDEPENDENT TOOL CALLS. Every message you send costs a full network
    round trip of two to three seconds, while the tools themselves run in
    milliseconds. When you need several things that do not depend on each other
    — reading four files, listing two directories, a read plus a search —
    request them ALL in a single message. Reading four files one at a time
    costs four round trips; requesting them together costs one.
    Only go sequentially when a call genuinely depends on the previous result.

11. NEVER run a dev server or other long-running process in the foreground.
    Use background=true. Foreground commands must terminate on their own.

12. NEVER use `cd` or absolute paths. Commands already run in the workspace
    root; use paths relative to it.

13. ASKING THE USER. You have an `ask_user` tool. It STOPS the run and waits for
    a human, so it is expensive — but guessing wrong on an unrecoverable choice
    is more expensive.

    ASK when ALL THREE are true:
      a) the workspace is empty (nothing to infer the answer from), AND
      b) the choice is costly to reverse — framework, language, or architecture, AND
      c) the request does not already imply an answer.

    Examples that SHOULD ask:
      "make a snake game" in an empty workspace  → which framework?
      "build me an API"                          → which language/framework?

    Examples that must NOT ask:
      "make a snake game in Next.js"      → the framework is stated. Just build it.
      any request in a non-empty workspace → match the existing project.
      "add dark mode"                     → a default is obvious.
      confirming work you already did     → never. Report it instead.
      asking permission to continue       → never. Continue.

    At most ONE question per turn, and only before you start implementing. Never
    interrupt mid-implementation.

    For everything else: DECIDE, state the default you chose in one line, and
    offer the alternative. "Used JavaScript since you asked for something simple
    — say the word and I'll convert to TypeScript." Do not present menus, do not
    ask which the user prefers after the fact.

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

    # Keep at least this many recent messages verbatim.
    MAX_RECENT_MESSAGES = 12
    MAX_TOOL_OUTPUT_CHARS = 4000

    # The clearing boundary advances in blocks of this size rather than by one
    # message at a time.
    #
    # This is the difference between paying full price on every call and almost
    # never paying it. Prompt caching only hits on an EXACT prefix match, so a
    # boundary that slides by one message per call rewrites the prefix every
    # call and guarantees a cache miss. Quantizing it means the prefix stays
    # byte-identical for CLEAR_BLOCK consecutive calls, then shifts once.
    #
    # Codex treats anything that busts the cache as a bug for this reason —
    # caching is what makes the agent loop linear instead of quadratic.
    CLEAR_BLOCK = 20

    @classmethod
    def _clear_cutoff(cls, total: int) -> int:
        """
        Index below which tool results are cleared. Quantized to CLEAR_BLOCK so
        the emitted prefix is stable across consecutive calls.

        Short conversations return 0 — nothing is rewritten, the history is
        purely append-only, and every call after the first is a full cache hit.
        """
        excess = total - cls.MAX_RECENT_MESSAGES
        if excess <= cls.CLEAR_BLOCK:
            return 0
        return (excess // cls.CLEAR_BLOCK) * cls.CLEAR_BLOCK

    @classmethod
    def _system_message(cls) -> SystemMessage:
        """
        The system block. Deliberately NOT the cache breakpoint.

        Anthropic silently ignores a cache breakpoint whose cached prefix is
        under 1024 tokens (2048 on some models). SYSTEM_INSTRUCTIONS is roughly
        570 tokens, so marking it here produced exactly zero cache hits — the
        request succeeds, the marker is dropped, and you pay full price with no
        error to tell you.

        The breakpoint therefore goes on the first user message instead — see
        _cache_marked(). Anthropic caches everything up to and including a
        marked block, and the order it receives is system → tools → messages,
        so marking there covers the system prompt AND all nine tool schemas.
        """
        return SystemMessage(content=SYSTEM_INSTRUCTIONS)

    @classmethod
    def _repair_orphaned_tool_calls(cls, messages: List[BaseMessage]) -> List[BaseMessage]:
        """
        Drop tool calls that never got a result, and results with no call.

        Providers reject a history containing an AIMessage with tool_calls that
        has no matching ToolMessage. That state is easy to reach: a turn that
        dies between requesting a tool and recording its result — an exception,
        a timeout, or agent.stop cancelling mid-call — leaves the checkpointed
        thread permanently invalid. Every later turn on that thread then fails
        with INVALID_CHAT_HISTORY before reaching the model, and the session is
        unrecoverable without wiping it.

        Repairing here rather than at write time covers threads that are
        already broken, not just future ones.
        """
        answered: set = set()
        for m in messages:
            if isinstance(m, ToolMessage):
                tc_id = getattr(m, "tool_call_id", None)
                if tc_id:
                    answered.add(tc_id)

        requested: set = set()
        for m in messages:
            for tc in (getattr(m, "tool_calls", None) or []):
                tc_id = tc.get("id") if isinstance(tc, dict) else getattr(tc, "id", None)
                if tc_id:
                    requested.add(tc_id)

        orphan_calls = requested - answered
        orphan_results = answered - requested
        if not orphan_calls and not orphan_results:
            return messages

        repaired: List[BaseMessage] = []
        for m in messages:
            if isinstance(m, ToolMessage):
                if getattr(m, "tool_call_id", None) in orphan_results:
                    continue
                repaired.append(m)
                continue

            calls = getattr(m, "tool_calls", None) or []
            if calls:
                kept = [
                    tc for tc in calls
                    if (tc.get("id") if isinstance(tc, dict) else getattr(tc, "id", None))
                    not in orphan_calls
                ]
                if len(kept) != len(calls):
                    # An assistant turn that only ever requested unanswered tools
                    # carries no information; drop it rather than emit an empty
                    # tool_calls array, which some providers also reject.
                    if not kept and not str(getattr(m, "content", "")).strip():
                        continue
                    repaired.append(AIMessage(content=m.content, tool_calls=kept))
                    continue
            repaired.append(m)

        logger.warning(
            f"Repaired chat history: dropped {len(orphan_calls)} unanswered tool call(s) "
            f"and {len(orphan_results)} orphaned result(s)."
        )
        return repaired

    @classmethod
    def _cache_marked(cls, msg: "HumanMessage") -> "HumanMessage":
        """
        Attach an Anthropic cache breakpoint to the end of the stable prefix.

        OpenAI caches an exact prefix automatically and ignores this marker, so
        one code path serves both providers.
        """
        # Bedrock's Converse API marks cache points with its own `cachePoint`
        # block rather than Anthropic's `cache_control`. Sending the Anthropic
        # form there is either ignored or rejected, so skip it in Bedrock mode
        # rather than emitting something the provider will not understand.
        if settings.bedrock_mode:
            return msg

        if not settings.ANTHROPIC_API_KEY:
            return msg

        text = msg.content if isinstance(msg.content, str) else str(msg.content)
        return HumanMessage(
            content=[
                {
                    "type": "text",
                    "text": text,
                    "cache_control": {"type": "ephemeral"},
                }
            ]
        )

    @classmethod
    def prune_messages(cls, state_or_messages: Any) -> List[BaseMessage]:
        """
        Prunes message history to stay strictly within token budget.
        Always retains System Instructions, original user prompt, and recent tool exchanges.
        Summarizes older tool results to save tokens.
        """
        if isinstance(state_or_messages, dict):
            messages = state_or_messages.get("messages", [])
        else:
            messages = state_or_messages

        if not messages:
            return [cls._system_message()]

        # Repair before pruning. An invalid pairing is rejected by the provider
        # before the model is even reached, so nothing downstream matters until
        # the history is well-formed.
        messages = cls._repair_orphaned_tool_calls(messages)

        pruned: List[BaseMessage] = [cls._system_message()]

        # The original request is preserved verbatim and carries the cache
        # breakpoint — it is the last element of the stable prefix, so
        # everything before it (system prompt + tool schemas) gets cached.
        user_messages = [m for m in messages if isinstance(m, HumanMessage)]
        if user_messages:
            pruned.append(cls._cache_marked(user_messages[0]))

        recent_cutoff = cls._clear_cutoff(len(messages))

        for i, msg in enumerate(messages):
            if i == 0 and isinstance(msg, HumanMessage) and user_messages and msg == user_messages[0]:
                continue

            if i < recent_cutoff:
                # Older messages: drop outputs to save tokens
                if isinstance(msg, ToolMessage):
                    pruned.append(ToolMessage(content="[Archived Tool Result]", tool_call_id=getattr(msg, "tool_call_id", "default_id")))
                elif isinstance(msg, AIMessage):
                    tool_calls = getattr(msg, "tool_calls", None)
                    pruned.append(AIMessage(content="[Archived Response]", tool_calls=tool_calls or []))
                elif not isinstance(msg, SystemMessage):
                    pruned.append(msg)
            else:
                # Recent messages: keep verbatim but truncate huge outputs
                if isinstance(msg, ToolMessage):
                    content_str = str(msg.content)
                    if len(content_str) > cls.MAX_TOOL_OUTPUT_CHARS:
                        truncated = (
                            content_str[: cls.MAX_TOOL_OUTPUT_CHARS]
                            + f"\n... [Output truncated ({len(content_str)} chars)]"
                        )
                        pruned.append(ToolMessage(content=truncated, tool_call_id=getattr(msg, "tool_call_id", "default_id")))
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

