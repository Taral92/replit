import asyncio
import re
import time
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
from services.agent.context import SYSTEM_INSTRUCTIONS
from services.agent.gateway.tool_gateway import ToolGateway
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

    def _get_or_create_graph(self, model_name: str):
        """Lazy caches compiled LangGraph instances per model name."""
        if model_name in self.graphs:
            return self.graphs[model_name]

        # Check for Anthropic Claude
        if "claude" in model_name:
            if not ModelRouter.anthropic_available():
                print(f"[Model Runtime] ⚠️ ANTHROPIC_API_KEY not found. Falling back to {settings.DEFAULT_AGENT_MODEL}")
                llm = ChatOpenAI(
                    model=settings.DEFAULT_AGENT_MODEL,
                    api_key=settings.OPENAI_API_KEY,
                    temperature=0.1,
                )
            else:
                try:
                    from langchain_anthropic import ChatAnthropic
                    print(f"[Model Runtime] 🏆 Initializing native Anthropic Claude ({model_name})")
                    llm = ChatAnthropic(
                        model_name=model_name,
                        api_key=settings.ANTHROPIC_API_KEY,
                        temperature=0.1,
                    )
                except ImportError:
                    print("[Model Runtime] ⚠️ 'langchain-anthropic' package not installed. Falling back to OpenAI.")
                    llm = ChatOpenAI(
                        model=settings.DEFAULT_AGENT_MODEL,
                        api_key=settings.OPENAI_API_KEY,
                        temperature=0.1,
                    )
        else:
            # OpenAI Models (gpt-4o, gpt-4o-mini, o3-mini)
            print(f"[Model Runtime] ⚡ Initializing OpenAI model ({model_name})")
            llm = ChatOpenAI(
                model=model_name,
                api_key=settings.OPENAI_API_KEY,
                temperature=0.1 if "o3" not in model_name else 1.0,
            )

        graph = create_react_agent(
            model=llm,
            tools=self.tools,
            checkpointer=self.checkpointer,
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
        start_ev = AgentStartEvent(
            workspace_id=self.gateway.workspace_id,
            session_id=session_id,
            prompt=clean_prompt,
        ).model_dump()
        if event_callback:
            await event_callback(start_ev)
        yield start_ev

        # 2. Check for Conversational Fast-Path
        if ModelRouter.is_conversational_query(clean_prompt):
            status_ev = AgentStatusEvent(
                workspace_id=self.gateway.workspace_id,
                session_id=session_id,
                status="Responding...",
                phase="EXPLORE",
            ).model_dump()
            if event_callback:
                await event_callback(status_ev)
            yield status_ev

            try:
                llm = ChatOpenAI(
                    model=settings.FAST_AGENT_MODEL,
                    api_key=settings.OPENAI_API_KEY,
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

        config = {"configurable": {"thread_id": session_id}}

        # Reset turn diff buffer
        self.gateway.reset_turn_diffs()

        # Connect gateway event stream to broadcast tool completed events with full diff metrics
        if event_callback:
            self.gateway.set_event_callback(event_callback)

        # Generate Contract Checklist upfront
        checklist_status = AgentStatusEvent(
            workspace_id=self.gateway.workspace_id,
            session_id=session_id,
            status="Defining requirements checklist contract...",
            phase="EXPLORE",
        ).model_dump()
        if event_callback:
            await event_callback(checklist_status)
        yield checklist_status

        checklist = await IndependentVerifier.generate_checklist(clean_prompt)

        status_ev = AgentStatusEvent(
            workspace_id=self.gateway.workspace_id,
            session_id=session_id,
            status=f"{route_reason} ({len(checklist)} criteria defined)...",
            phase="EXPLORE",
        ).model_dump()
        if event_callback:
            await event_callback(status_ev)
        yield status_ev

        current_state = graph.get_state(config)
        existing_messages = current_state.values.get("messages", []) if current_state else []

        messages_to_send: List[BaseMessage] = []
        if not existing_messages:
            messages_to_send.append(SystemMessage(content=SYSTEM_INSTRUCTIONS))
        messages_to_send.append(HumanMessage(content=clean_prompt))

        initial_input = {"messages": messages_to_send}
        retry_count = 0
        max_retries = 2
        latest_agent_text = ""
        tool_call_args: Dict[str, Dict[str, Any]] = {}

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
                                        call_id = tc.get("id") or str(uuid4())
                                        tool_name = tc.get("name", "tool")
                                        args = tc.get("args", {})
                                        tool_call_args[call_id] = {"tool": tool_name, "args": args}

                                        t_ev = AgentToolStartedEvent(
                                            workspace_id=self.gateway.workspace_id,
                                            session_id=session_id,
                                            tool_name=tool_name,
                                            arguments=args,
                                        ).model_dump()
                                        if event_callback:
                                            await event_callback(t_ev)
                                        yield t_ev

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

                                # Extract unified diff if present
                                diff_part = ""
                                if "DIFF_START" in content and "DIFF_END" in content:
                                    diff_match = re.search(r"DIFF_START\s*\n(.*?)\nDIFF_END", content, re.DOTALL)
                                    if diff_match:
                                        diff_part = diff_match.group(1).strip()
                                elif "+++" in content or "---" in content:
                                    diff_part = content

                                added = sum(1 for line in diff_part.splitlines() if line.startswith("+") and not line.startswith("+++"))
                                removed = sum(1 for line in diff_part.splitlines() if line.startswith("-") and not line.startswith("---"))

                                completed_payload = {
                                    "type": "agent.tool.completed",
                                    "tool_name": tool_name,
                                    "arguments": args,
                                    "result": {
                                        "path": file_path,
                                        "diff": diff_part,
                                        "added": added,
                                        "removed": removed,
                                        "success": "error" not in content.lower(),
                                    },
                                }
                                if event_callback:
                                    await event_callback(completed_payload)

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

                # If files were modified, run Independent Verification Call
                verify_status = AgentStatusEvent(
                    workspace_id=self.gateway.workspace_id,
                    session_id=session_id,
                    status="Auditing diff against requirements contract...",
                    phase="EXPLORE",
                ).model_dump()
                if event_callback:
                    await event_callback(verify_status)
                yield verify_status

                report = await IndependentVerifier.verify_diff(
                    prompt=clean_prompt,
                    checklist=checklist,
                    diff_text=diff_text,
                    touched_files=touched_files,
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
                        phase="EXPLORE",
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
