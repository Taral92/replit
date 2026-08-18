import asyncio
import re
import time
from pathlib import Path
from typing import Any, AsyncGenerator, Callable, Dict, List, Optional, Set
from uuid import uuid4
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import create_react_agent

from packages.config import settings
from packages.protocol.events import (
    AgentMessageEvent,
    AgentStartEvent,
    AgentStatusEvent,
    AgentToolCompletedEvent,
    AgentToolFailedEvent,
    AgentToolStartedEvent,
)
from services.agent.context import SYSTEM_INSTRUCTIONS, ContextManager
from services.agent.gateway.tool_gateway import ToolGateway
from services.agent import metering, project_context
from services.agent.router import ModelRouter
from services.agent.tools import create_agent_tools
from services.agent.verifier import IndependentVerifier, TurnVerificationReport


def _is_auth_error(exc: Exception) -> bool:
    """
    True if an exception is a provider authentication failure.

    Matches on the message rather than the exception class so it works across
    openai, anthropic, and langchain wrapper types without importing them.
    """
    text = str(exc).lower()
    return (
        "authentication_error" in text
        or "invalid api key" in text
        or "api key is invalid" in text
        or "incorrect api key" in text
        or "error code: 401" in text
        or "status code: 401" in text
    )


def strip_redundant_code_blocks(text: str) -> str:
    """Removes large redundant fenced code blocks from agent prose when diff cards already show the code."""
    code_blocks = re.findall(r"```[\w]*\n[\s\S]*?\n```", text)
    if not code_blocks:
        return text

    total_len = len(text)
    code_len = sum(len(cb) for cb in code_blocks)

    # If code blocks make up >60% of the entire message
    if total_len > 0 and (code_len / total_len) > 0.6:
        cleaned = re.sub(r"```[\w]*\n[\s\S]*?\n```", "", text)
        cleaned_lines = [l for l in cleaned.splitlines() if l.strip()]
        return "\n\n".join(cleaned_lines)

    return text


class AgentRuntime:
    """
    Single Unified Agent Runtime for RunnerIDE with Smart Model Routing,
    Conversational Fast-Path, Real Tool Diff Relaying, and Independent Verification.
    """

    def __init__(self, gateway: ToolGateway):
        self.gateway = gateway
        self.tools = create_agent_tools(gateway)
        self.checkpointer = MemorySaver()
        self.graphs: Dict[str, Any] = {}

    # Workspace generation per session. Incremented when the workspace is
    # emptied, which invalidates every file fact the agent has accumulated.
    _generations: Dict[str, int] = {}
    _was_empty: Dict[str, bool] = {}

    def _workspace_generation(self, session_id: str) -> int:
        """
        Returns the current history generation, bumping it when the workspace
        transitions from populated to empty.

        Only the populated → empty edge bumps. Starting empty and creating files
        must NOT reset — that is the normal case and would wipe the agent's
        memory mid-build.
        """
        try:
            root = Path(self.gateway.sandbox.workspace_dir)
            meaningful = [
                p for p in root.iterdir()
                if not p.name.startswith(".") and p.name not in ("node_modules",)
            ]
            is_empty = len(meaningful) == 0
        except OSError:
            return self._generations.get(session_id, 0)

        gen = self._generations.get(session_id, 0)
        previously_populated = self._was_empty.get(session_id) is False

        if is_empty and previously_populated:
            gen += 1
            self._generations[session_id] = gen
            print(
                f"[Agent Runtime] Workspace emptied — starting history generation "
                f"{gen} for session {session_id[:8]}. Prior conversation discarded."
            )

        self._was_empty[session_id] = is_empty
        return gen

    def _thread_has_history(self, config: Dict[str, Any]) -> bool:
        """
        Whether this thread already holds a conversation.

        Read straight from the checkpointer rather than a graph, because this is
        needed before a model has been resolved — and all graphs share one
        checkpointer, so the answer is the same either way.
        """
        try:
            tup = self.checkpointer.get_tuple(config)
            if not tup or not tup.checkpoint:
                return False
            msgs = (tup.checkpoint.get("channel_values") or {}).get("messages") or []
            return len(msgs) > 0
        except Exception:
            return False

    def _repair_thread_state(self, graph: Any, config: Dict[str, Any]) -> None:
        """
        Surgically remove orphaned tool calls from the persisted thread.

        Uses RemoveMessage so the rest of the conversation survives — abandoning
        the whole thread would work but throws away everything the agent has
        learned this session, which is a heavy price for one interrupted call.

        Best-effort by design: if anything here fails, the turn should still be
        attempted rather than blocked by the repair itself.
        """
        try:
            from langchain_core.messages import RemoveMessage

            state = graph.get_state(config)
            messages = (state.values or {}).get("messages", []) if state else []
            if not messages:
                return

            answered = {
                getattr(m, "tool_call_id", None)
                for m in messages
                if getattr(m, "tool_call_id", None)
            }

            to_remove = []
            for m in messages:
                calls = getattr(m, "tool_calls", None) or []
                if not calls:
                    continue
                ids = {
                    (c.get("id") if isinstance(c, dict) else getattr(c, "id", None))
                    for c in calls
                }
                # Any unanswered call invalidates the whole message — the
                # provider rejects the pairing, not the individual call.
                if ids - answered:
                    mid = getattr(m, "id", None)
                    if mid:
                        to_remove.append(mid)

            if not to_remove:
                return

            graph.update_state(config, {"messages": [RemoveMessage(id=i) for i in to_remove]})
            print(
                f"[Agent Runtime] Repaired thread {config['configurable']['thread_id']}: "
                f"removed {len(to_remove)} message(s) with unanswered tool calls."
            )
        except Exception as e:
            print(f"[Agent Runtime] Thread repair skipped: {e}")

    def _get_or_create_graph(self, model_name: str):
        """Lazy caches compiled LangGraph instances per model name."""
        if model_name in self.graphs:
            return self.graphs[model_name]

        from services.agent.llm import get_llm
        llm = get_llm(model_name)

        graph = create_react_agent(
            model=llm,
            tools=self.tools,
            checkpointer=self.checkpointer,
            prompt=ContextManager.prune_messages,
        )
        self.graphs[model_name] = graph
        return graph

    async def run_stream(
        self,
        prompt: Any,
        session_id: str,
        requested_model: str = "auto",
        event_callback: Optional[Callable[[Dict[str, Any]], Any]] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Executes a user request with:
        - Conversational Fast-Path.
        - Granular tool call & diff extraction from ToolMessage and ToolGateway.
        - Redundant code block trimming.
        - Independent diff verification.
        """
        if isinstance(prompt, dict):
            requested_model = prompt.get("model", requested_model)
            clean_prompt = str(prompt.get("prompt", "")).strip()
        else:
            clean_prompt = str(prompt).strip()

        # 1. Initial Start Event
        # Begin accounting for this turn. Every LLM call made from here on is
        # counted, including the verifier's, because metering is attached in
        # the get_llm factory.
        metering.start_turn(session_id)

        start_ev = AgentStartEvent(
            workspace_id=self.gateway.workspace_id,
            session_id=session_id,
            prompt=clean_prompt,
        ).model_dump()
        if event_callback:
            await event_callback(start_ev)
        yield start_ev

        # The thread identity is needed before the fast-path decision, because
        # whether a short prompt like "continue" is conversational depends
        # entirely on whether a conversation already exists.
        generation = self._workspace_generation(session_id)
        config = {"configurable": {"thread_id": f"{session_id}:{generation}"}}
        has_history = self._thread_has_history(config)

        # 2. Check for Conversational Fast-Path
        if ModelRouter.is_conversational_query(clean_prompt, has_history=has_history):
            status_ev = AgentStatusEvent(
                workspace_id=self.gateway.workspace_id,
                session_id=session_id,
                status="Responding...",
                phase="DONE",
            ).model_dump()
            if event_callback:
                await event_callback(status_ev)
            yield status_ev

            try:
                # Respect local mode here too — this fast path builds its own
                # client and would otherwise ask Ollama for gpt-4o-mini (404)
                # or, with a real key configured, silently bill the paid API.
                from services.agent.llm import get_llm
                llm = get_llm(
                    model=settings.fast_model,
                    purpose="fast-path",
                    temperature=0.7,
                )
                sys_msg = SystemMessage(
                    content=(
                        "You are RunnerIDE AI Engineer, a helpful and capable autonomous software engineering assistant.\n"
                        "Respond to greetings and conversational questions in a friendly, concise, and direct manner.\n"
                        "Offer to help with coding tasks, building pages, debugging errors, or starting the dev server."
                    )
                )
                res = await llm.ainvoke([sys_msg, HumanMessage(content=clean_prompt)])
                reply_text = str(res.content).strip()

                msg_ev = AgentMessageEvent(
                    workspace_id=self.gateway.workspace_id,
                    session_id=session_id,
                    content=reply_text,
                ).model_dump()
                if event_callback:
                    await event_callback(msg_ev)
                yield msg_ev

                final_status = AgentStatusEvent(
                    workspace_id=self.gateway.workspace_id,
                    session_id=session_id,
                    status="Idle",
                    phase="DONE",
                ).model_dump()
                if event_callback:
                    await event_callback(final_status)
                yield final_status
                return

            except Exception:
                pass

        # 3. Engineering Task Pipeline
        resolved_model, route_reason = ModelRouter.route(clean_prompt, requested_model)
        graph = self._get_or_create_graph(resolved_model)

        # Conversation history is versioned by workspace generation.
        #
        # MemorySaver keys on thread_id, so history outlives the files it
        # describes. Delete the project and ask for something new, and the agent
        # still has the old file contents in context — it edits remembered files
        # instead of creating fresh ones, and trusts stale detail over the
        # (correct) project_context saying the workspace is empty.
        #
        # The rule: an empty workspace cannot have meaningful history. Nothing
        # the agent learned about files is valid once there are no files. Bumping
        # the generation starts a clean thread rather than mutating the old one,
        # so the previous conversation is still inspectable for debugging.
        # config and generation were resolved before the fast-path check above.

        # Repair the CHECKPOINTED STATE, not just the model input.
        #
        # LangGraph validates state["messages"] inside the agent node, before the
        # `prompt=` hook runs — so cleaning the messages in prune_messages is too
        # late. A turn that dies between requesting a tool and recording its
        # result leaves an AIMessage with tool_calls and no matching ToolMessage,
        # and from then on EVERY turn on that thread fails with
        # INVALID_CHAT_HISTORY before reaching the model at all (note the 0.0s
        # duration on those errors). The thread is unrecoverable without this.
        self._repair_thread_state(graph, config)

        # Reset turn diff buffer
        self.gateway.reset_turn_diffs()

        # Connect gateway event stream to broadcast tool completed events with full diff metrics
        if event_callback:
            self.gateway.set_event_callback(event_callback)

        current_plan: List[Dict[str, Any]] = []

        def get_phase() -> str:
            if not current_plan:
                return "EXPLORE"
            if any(step.get("status") == "in_progress" for step in current_plan):
                return "IMPLEMENT"
            return "PLAN"

        # Emit initial status
        status_ev = AgentStatusEvent(
            workspace_id=self.gateway.workspace_id,
            session_id=session_id,
            status=f"{route_reason}...",
            phase=get_phase(),
        ).model_dump()
        if event_callback:
            await event_callback(status_ev)
        yield status_ev

        current_state = graph.get_state(config)
        existing_messages = current_state.values.get("messages", []) if current_state else []

        messages_to_send: List[BaseMessage] = []
        if not existing_messages:
            messages_to_send.append(SystemMessage(content=SYSTEM_INSTRUCTIONS))

        # Ground the agent in what the project actually is before it acts. This
        # is a plain file read — no LLM call — and it removes the pwd/ls/cat/
        # test -f/find thrash that otherwise opens every turn.
        ctx_block = project_context.build(self.gateway.sandbox.workspace_dir)
        messages_to_send.append(HumanMessage(content=f"{ctx_block}\n\n{clean_prompt}"))

        initial_input = {"messages": messages_to_send}
        retry_count = 0
        # One corrective pass. A second rarely fixes what the first could not,
        # and each pass costs a verify call plus however many calls the agent
        # spends reacting to it.
        max_retries = 1
        latest_agent_text = ""
        tool_call_args: Dict[str, Dict[str, Any]] = {}
        tool_call_count = 0

        try:
            while retry_count <= max_retries:
                async for event in graph.astream(initial_input, config=config):
                    for node_name, node_state in event.items():
                        messages = node_state.get("messages", [])
                        for msg in messages:
                            # 1. Capture AIMessage tool calls and text
                            if isinstance(msg, AIMessage) or msg.__class__.__name__ == "AIMessage":
                                if getattr(msg, "tool_calls", None):
                                    for tc in msg.tool_calls:
                                        tool_call_count += 1
                                        call_id = tc.get("id") or str(uuid4())
                                        tool_name = tc.get("name", "tool")
                                        args = tc.get("args", {})
                                        tool_call_args[call_id] = {"tool": tool_name, "args": args}

                                if msg.content:
                                    content_str = str(msg.content).strip()
                                    if content_str:
                                        latest_agent_text = content_str

                            # 2. Capture ToolMessage results and extract diffs
                            elif isinstance(msg, ToolMessage) or msg.__class__.__name__ == "ToolMessage":
                                content = str(msg.content)
                                call_id = getattr(msg, "tool_call_id", None)
                                call_info = tool_call_args.get(call_id, {})
                                tool_name = getattr(msg, "name", None) or call_info.get("tool") or "tool"
                                args = call_info.get("args", {})
                                file_path = args.get("path") or args.get("file_path") or args.get("target")

                                if tool_name == "update_plan":
                                    current_plan = args.get("plan", [])
                                    if event_callback:
                                        phase_ev = AgentStatusEvent(
                                            workspace_id=self.gateway.workspace_id,
                                            session_id=session_id,
                                            status="Executing plan...",
                                            phase=get_phase(),
                                        ).model_dump()
                                        await event_callback(phase_ev)
                                        yield phase_ev

                    if tool_call_count >= 40:
                        msg_ev = AgentMessageEvent(
                            workspace_id=self.gateway.workspace_id,
                            session_id=session_id,
                            content="⚠️ **Iteration Cap Reached**: The agent hit the hard limit of 40 tool calls per turn. I have stopped cleanly. Please review what was completed and ask me to continue if more work remains.",
                        ).model_dump()
                        if event_callback:
                            await event_callback(msg_ev)
                        yield msg_ev
                        break

                if tool_call_count >= 40:
                    break

                # Collect Real Unified Diffs directly from ToolGateway
                diff_data = self.gateway.get_turn_diff_data()
                diff_text = diff_data.get("diff_text", "")
                touched_files = diff_data.get("touched_files", [])

                # Clean redundant code blocks from trailing prose if files were modified
                has_edits = len(touched_files) > 0
                cleaned_agent_text = strip_redundant_code_blocks(latest_agent_text) if has_edits else latest_agent_text

                # If no files were modified (e.g. conversational response, explanation, or command without edits)
                if not touched_files:
                    final_content = cleaned_agent_text or "Task completed."
                    msg_ev = AgentMessageEvent(
                        workspace_id=self.gateway.workspace_id,
                        session_id=session_id,
                        content=final_content,
                    ).model_dump()
                    if event_callback:
                        await event_callback(msg_ev)
                    yield msg_ev
                    break

                # Verification costs a full LLM call, plus up to max_retries more
                # if it fails. That is worth paying on a multi-step build and
                # pure overhead on a one-line edit, so gate it on the size of
                # what actually changed.
                plan_steps = len(current_plan or [])
                total_lines = (diff_text or "").count("\n")
                needs_verification = (
                    plan_steps > 1
                    or len(touched_files) > 1
                    or total_lines > 30
                )

                if not needs_verification:
                    final_content = cleaned_agent_text or "Task completed."
                    msg_ev = AgentMessageEvent(
                        workspace_id=self.gateway.workspace_id,
                        session_id=session_id,
                        content=final_content,
                    ).model_dump()
                    if event_callback:
                        await event_callback(msg_ev)
                    yield msg_ev
                    break

                # If files were modified, run Independent Verification Call
                verify_status = AgentStatusEvent(
                    workspace_id=self.gateway.workspace_id,
                    session_id=session_id,
                    status="Auditing diff against requirements contract...",
                    phase="VERIFY",
                ).model_dump()
                if event_callback:
                    await event_callback(verify_status)
                yield verify_status

                report = await IndependentVerifier.verify_diff(
                    prompt=clean_prompt,
                    plan=current_plan,
                    diff_text=diff_text,
                    touched_files=touched_files,
                    model=resolved_model,
                )

                if report.all_passed or retry_count >= max_retries:
                    full_content = ""
                    if cleaned_agent_text:
                        full_content += f"{cleaned_agent_text}\n\n"
                    full_content += report.format_user_message()

                    msg_ev = AgentMessageEvent(
                        workspace_id=self.gateway.workspace_id,
                        session_id=session_id,
                        content=full_content,
                    ).model_dump()
                    if event_callback:
                        await event_callback(msg_ev)
                    yield msg_ev
                    break
                else:
                    retry_count += 1
                    retry_status = AgentStatusEvent(
                        workspace_id=self.gateway.workspace_id,
                        session_id=session_id,
                        status=f"Refining missing requirements (Pass {retry_count}/{max_retries})...",
                        phase="IMPLEMENT",
                    ).model_dump()
                    if event_callback:
                        await event_callback(retry_status)
                    yield retry_status

                    initial_input = {
                        "messages": [
                            HumanMessage(
                                content=(
                                    f"Independent Auditor Report:\n"
                                    f"{report.feedback_for_agent}\n\n"
                                    f"Please implement the missing code in the workspace files to satisfy all checklist items."
                                )
                            )
                        ]
                    }

            final_status = AgentStatusEvent(
                workspace_id=self.gateway.workspace_id,
                session_id=session_id,
                status="Idle",
                phase="DONE",
            ).model_dump()
            if event_callback:
                await event_callback(final_status)
            yield final_status

        except Exception as e:
            # A provider auth failure is a configuration problem, not a task
            # failure. Disable the dead provider and retry once on the other
            # one rather than burning the user's turn.
            if _is_auth_error(e) and "claude" in resolved_model:
                ModelRouter.disable_anthropic("API key rejected (401)")
                self.graphs.pop(resolved_model, None)

                notice = AgentMessageEvent(
                    workspace_id=self.gateway.workspace_id,
                    session_id=session_id,
                    content=(
                        f"Anthropic rejected the configured API key. "
                        f"Retrying on {settings.DEFAULT_AGENT_MODEL}."
                    ),
                    role="system",
                ).model_dump()
                if event_callback:
                    await event_callback(notice)
                yield notice

                async for ev in self.run_stream(
                    prompt,
                    session_id=session_id,
                    requested_model=settings.DEFAULT_AGENT_MODEL,
                    event_callback=event_callback,
                ):
                    yield ev
                return

            err_msg = AgentMessageEvent(
                workspace_id=self.gateway.workspace_id,
                session_id=session_id,
                content=f"⚠️ Agent execution error: {str(e)}",
                role="system",
            ).model_dump()
            if event_callback:
                await event_callback(err_msg)
            yield err_msg

        finally:
            # Logs e.g. "turn a1b2c3d4 · 14 calls · 182.4k in (71% cached) · $0.03"
            metering.finish_turn()
