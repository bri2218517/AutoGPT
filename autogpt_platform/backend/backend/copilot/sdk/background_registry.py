"""Per-session registry of backgrounded tool calls.

When a tool exceeds its per-call ``timeout_seconds`` budget the in-flight
``asyncio.Task`` is parked here rather than being cancelled. The agent can
then use the ``check_background_tool`` tool (keyed by ``background_id``) to
wait longer, poll status, or cancel — keeping the autopilot in control of
slow sub-agents and graph executions.

Lives in its own module so that both ``tool_adapter.py`` (which registers
tasks during tool dispatch) and ``tools/check_background_tool.py`` (which
inspects them) can import the registry without creating a cycle via the
tool-registry import chain.
"""

import asyncio
import time
import uuid
from contextvars import ContextVar
from typing import Any

# Max wait a single check_background_tool call may block for. Kept below the
# stream-level idle timeout so the outer safety net still triggers if the
# whole session genuinely stalls.
MAX_BACKGROUND_WAIT_SECONDS = 9 * 60  # 9 minutes

_background_tasks: ContextVar[dict[str, dict[str, Any]]] = ContextVar(
    "_background_tasks",
    default=None,  # type: ignore[arg-type]
)


def init_registry() -> None:
    """Install a fresh per-session registry in the current context."""
    _background_tasks.set({})


def register_background_task(task: asyncio.Task, tool_name: str) -> str:
    """Register *task* in the per-session background registry, returning the id."""
    bg_id = f"bg-{uuid.uuid4().hex[:12]}"
    registry = _background_tasks.get(None)
    if registry is None:
        # Registry isn't initialized (e.g. unit tests that bypass
        # set_execution_context). Fall back to a fresh dict so we at least
        # don't drop the task silently.
        registry = {}
        _background_tasks.set(registry)
    registry[bg_id] = {
        "task": task,
        "tool_name": tool_name,
        "started_at": time.monotonic(),
    }
    return bg_id


def get_background_task(background_id: str) -> dict[str, Any] | None:
    """Return the registered entry for *background_id*, or ``None``."""
    registry = _background_tasks.get(None)
    if registry is None:
        return None
    return registry.get(background_id)


def unregister_background_task(background_id: str) -> None:
    """Drop a finished/cancelled task from the registry."""
    registry = _background_tasks.get(None)
    if registry is None:
        return
    registry.pop(background_id, None)
