"""
Per-turn LLM usage metering.

Attached as a callback to every client produced by get_llm(), so it cannot be
bypassed by a new call site. This is the measurement layer every cost
optimization is judged against — without it, "the caching fix worked" is a
vibe rather than a number.

The number that matters most here is the cache hit rate. Prompt caching turns
the agent loop from quadratic into linear, so a low hit rate means you are
paying full price for context you have already sent.
"""
import contextvars
import time
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from langchain_core.callbacks import BaseCallbackHandler

logger = logging.getLogger("RunnerIDE-Usage")

# Approximate USD per 1M tokens. These change — treat as indicative and verify
# against your provider dashboard before trusting the dollar figure. The token
# counts and cache hit rate are exact regardless.
PRICES: Dict[str, tuple[float, float]] = {
    "gpt-4o": (2.50, 10.00),
    "gpt-4o-mini": (0.15, 0.60),
    "o3-mini": (1.10, 4.40),
    "claude-haiku-4-5-20251001": (1.00, 5.00),
    "claude-sonnet-5": (3.00, 15.00),
    "claude-opus-5": (15.00, 75.00),
    # Bedrock uses its own model ids, so they need their own entries or the
    # cost column silently reads $0.
    "anthropic.claude-haiku-4-5-20251001-v1:0": (1.00, 5.00),
    "us.anthropic.claude-haiku-4-5-20251001-v1:0": (1.00, 5.00),
    "anthropic.claude-3-haiku-20240307-v1:0": (0.25, 1.25),
}


@dataclass
class TurnUsage:
    turn_id: str = ""
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cached_tokens: int = 0
    by_model: Dict[str, int] = field(default_factory=dict)

    # Wall-clock split. Tool execution runs in single-digit milliseconds, so
    # when a turn takes a minute the time is in sequential LLM round trips.
    # These fields make that visible instead of assumed.
    llm_seconds: float = 0.0
    tool_seconds: float = 0.0
    tool_calls: int = 0
    started_at: float = field(default_factory=time.monotonic)

    @property
    def wall_seconds(self) -> float:
        return time.monotonic() - self.started_at

    @property
    def calls_per_message(self) -> float:
        """
        Tool calls divided by LLM round trips.

        1.0 means everything is sequential — four file reads cost four round
        trips. Above 1.0 means the model is batching independent calls into one
        message, which is the single biggest latency win available.
        """
        return (self.tool_calls / self.calls) if self.calls else 0.0

    @property
    def cache_hit_rate(self) -> float:
        return (self.cached_tokens / self.input_tokens) if self.input_tokens else 0.0

    @property
    def cost_usd(self) -> float:
        total = 0.0
        for model, calls in self.by_model.items():
            price_in, price_out = PRICES.get(model, (0.0, 0.0))
            share = calls / self.calls if self.calls else 0
            # Cached input is heavily discounted; approximate at 10% of list.
            billed_in = (self.input_tokens - self.cached_tokens) + self.cached_tokens * 0.1
            total += (billed_in * share / 1_000_000) * price_in
            total += (self.output_tokens * share / 1_000_000) * price_out
        return total

    def summary(self) -> str:
        other = max(0.0, self.wall_seconds - self.llm_seconds - self.tool_seconds)
        return (
            f"turn {self.turn_id[:8]} · {self.wall_seconds:.1f}s wall "
            f"(llm {self.llm_seconds:.1f}s / tools {self.tool_seconds:.1f}s / other {other:.1f}s) · "
            f"{self.calls} round trips, {self.tool_calls} tool calls "
            f"({self.calls_per_message:.1f} per message) · "
            f"{self.input_tokens / 1000:.1f}k in ({self.cache_hit_rate:.0%} cached) · "
            f"{self.output_tokens / 1000:.1f}k out · ${self.cost_usd:.4f}"
        )


# One accumulator per turn. A contextvar rather than a global so concurrent
# turns on the same process do not pollute each other's counts.
_current_turn: contextvars.ContextVar[Optional[TurnUsage]] = contextvars.ContextVar(
    "current_turn_usage", default=None
)


def start_turn(turn_id: str) -> TurnUsage:
    usage = TurnUsage(turn_id=turn_id)
    _current_turn.set(usage)
    return usage


def get_current() -> Optional[TurnUsage]:
    return _current_turn.get()


def finish_turn() -> Optional[TurnUsage]:
    usage = _current_turn.get()
    if usage:
        logger.info(usage.summary())
    _current_turn.set(None)
    return usage


def record_tool(duration_ms: int) -> None:
    """Called by the tool gateway so tool time can be separated from LLM time."""
    usage = _current_turn.get()
    if usage is None:
        return
    usage.tool_calls += 1
    usage.tool_seconds += duration_ms / 1000.0


class UsageCallback(BaseCallbackHandler):
    """Accumulates token usage and latency into the active turn."""

    def __init__(self, model: str):
        self.model = model
        self._started: Optional[float] = None

    def on_llm_start(self, *args: Any, **kwargs: Any) -> None:
        self._started = time.monotonic()

    def on_chat_model_start(self, *args: Any, **kwargs: Any) -> None:
        self._started = time.monotonic()

    def on_llm_end(self, response: Any, **kwargs: Any) -> None:
        usage = _current_turn.get()
        if usage is None:
            return

        if self._started is not None:
            usage.llm_seconds += time.monotonic() - self._started
            self._started = None

        usage.calls += 1
        usage.by_model[self.model] = usage.by_model.get(self.model, 0) + 1

        # Providers report usage in two different shapes depending on the
        # langchain integration, so try both rather than assuming one.
        meta: Dict[str, Any] = {}
        try:
            gen = response.generations[0][0]
            meta = getattr(gen.message, "usage_metadata", None) or {}
        except (AttributeError, IndexError):
            pass

        if meta:
            usage.input_tokens += meta.get("input_tokens", 0)
            usage.output_tokens += meta.get("output_tokens", 0)
            details = meta.get("input_token_details") or {}
            usage.cached_tokens += details.get("cache_read", 0)
            return

        legacy = (getattr(response, "llm_output", None) or {}).get("token_usage") or {}
        usage.input_tokens += legacy.get("prompt_tokens", 0)
        usage.output_tokens += legacy.get("completion_tokens", 0)
        cached = (legacy.get("prompt_tokens_details") or {}).get("cached_tokens", 0)
        usage.cached_tokens += cached
