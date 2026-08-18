"""
Blocking user interaction from inside the agent loop.

The agent loop is otherwise one-way: the model asks for a tool, the harness
runs it, the result goes back. There is no way for the model to ask the *user*
anything, so when a request is genuinely ambiguous — "make a snake game", with
no framework specified and an empty workspace — it can only guess, act, and
explain afterwards. That is the worst ordering: the cost is already paid by the
time the user finds out it picked wrong.

This makes a round trip to the human look like a tool call. The model calls
ask_user(...), execution parks on an asyncio.Future, the UI renders the question,
and the answer comes back as the tool result. The loop resumes with the answer
in context, exactly as if a tool had returned it.

The same mechanism serves command approval — a high-risk shell command is just
a question with two options — so both go through here rather than growing two
parallel implementations.
"""
import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional
from uuid import uuid4

logger = logging.getLogger("RunnerIDE-Interaction")

# A question left unanswered must not hold the turn open forever — a closed tab
# would strand the run and its container. Long enough for someone to actually
# read and answer; short enough to not leak a run.
DEFAULT_TIMEOUT_SECONDS = 300


@dataclass
class Pending:
    interaction_id: str
    kind: str                      # "question" | "approval"
    question: str
    options: List[str]
    future: asyncio.Future = field(repr=False)


class InteractionBroker:
    """
    One pending interaction per session, at most.

    Serialised deliberately: two simultaneous questions in one panel is a
    confusing UI and an ambiguous protocol — there would be no way to know
    which answer belongs to which question.
    """

    def __init__(self) -> None:
        self._pending: Dict[str, Pending] = {}

    def pending_for(self, session_id: str) -> Optional[Pending]:
        return self._pending.get(session_id)

    async def ask(
        self,
        session_id: str,
        question: str,
        options: List[str],
        emit: Callable[[Dict[str, Any]], Any],
        kind: str = "question",
        timeout: int = DEFAULT_TIMEOUT_SECONDS,
    ) -> str:
        """
        Emit a question and block until answered, timed out, or cancelled.

        Returns the answer text. On timeout returns a sentinel the model can
        act on rather than raising — a stalled question should degrade to "the
        user did not answer, use your judgement", not kill the turn.
        """
        if session_id in self._pending:
            # Should not happen, but returning a clear string beats deadlocking.
            return "A question is already awaiting an answer; do not ask another."

        interaction_id = str(uuid4())
        loop = asyncio.get_running_loop()
        future: asyncio.Future = loop.create_future()

        entry = Pending(interaction_id, kind, question, options, future)
        self._pending[session_id] = entry

        payload = {
            "type": "agent.question",
            "interaction_id": interaction_id,
            "kind": kind,
            "question": question,
            "options": options,
        }
        try:
            if asyncio.iscoroutinefunction(emit):
                await emit(payload)
            else:
                emit(payload)
        except Exception as e:
            logger.warning(f"Failed to emit question: {e}")
            self._pending.pop(session_id, None)
            return "Could not reach the user; proceed with your best judgement."

        try:
            answer = await asyncio.wait_for(future, timeout=timeout)
            logger.info(f"Interaction {interaction_id[:8]} answered: {answer!r}")
            return answer
        except asyncio.TimeoutError:
            logger.info(f"Interaction {interaction_id[:8]} timed out after {timeout}s")
            return (
                "The user did not answer in time. Proceed with the most conventional "
                "choice and state clearly which default you used."
            )
        except asyncio.CancelledError:
            # agent.stop while parked here. Re-raise so the turn unwinds.
            raise
        finally:
            self._pending.pop(session_id, None)

    def resolve(self, session_id: str, answer: str, interaction_id: Optional[str] = None) -> bool:
        """
        Deliver an answer. Returns False if there was nothing waiting, or if the
        id does not match — a stale click from a reopened tab must not answer a
        newer question.
        """
        entry = self._pending.get(session_id)
        if entry is None:
            return False
        if interaction_id and interaction_id != entry.interaction_id:
            logger.info("Ignoring answer for a stale interaction id")
            return False
        if entry.future.done():
            return False
        entry.future.set_result(answer)
        return True

    def cancel(self, session_id: str) -> None:
        """Abandon any pending interaction — used when a turn is stopped."""
        entry = self._pending.pop(session_id, None)
        if entry and not entry.future.done():
            entry.future.cancel()


# Process-wide broker. Session-keyed, so concurrent turns do not collide.
broker = InteractionBroker()
