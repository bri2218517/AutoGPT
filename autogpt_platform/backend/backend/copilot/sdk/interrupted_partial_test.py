"""Tests for partial-work preservation when an SDK turn is interrupted.

Covers the regression path SECRT-2275 surfaced: when the SDK retry loop
rolls back ``session.messages`` for a failed attempt (correct behavior so a
successful retry doesn't duplicate content) it MUST re-attach the rolled-back
work on final-failure exit. Otherwise the user's UI streamed tokens live but
a refresh shows an empty turn — described by users as "the turn is gone".

Tests target the helper functions directly (unit) plus the rollback-then-
restore contract (state-driven). Full end-to-end coverage of the retry loop
lives in retry_scenarios_test.py.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from backend.copilot.constants import (
    COPILOT_ERROR_PREFIX,
    COPILOT_RETRYABLE_ERROR_PREFIX,
)
from backend.copilot.model import ChatMessage, ChatSession
from backend.copilot.response_model import StreamToolOutputAvailable

from .service import (
    _flush_orphan_tool_uses_to_session,
    _restore_partial_with_error_marker,
)


def _make_session(messages: list[ChatMessage] | None = None) -> ChatSession:
    session = ChatSession.new(user_id="user-1", dry_run=False)
    session.messages = list(messages or [])
    return session


def _make_tool_output(tool_call_id: str, output) -> StreamToolOutputAvailable:
    return StreamToolOutputAvailable(
        toolCallId=tool_call_id,
        toolName="t",
        output=output,
    )


def _adapter_with_unresolved(unresolved_responses: list[StreamToolOutputAvailable]):
    """Build a stub _RetryState whose adapter flushes the given responses."""
    adapter = MagicMock()
    adapter.has_unresolved_tool_calls = bool(unresolved_responses)

    def _flush(responses: list) -> None:
        responses.extend(unresolved_responses)
        adapter.has_unresolved_tool_calls = False

    adapter._flush_unresolved_tool_calls.side_effect = _flush
    state = MagicMock()
    state.adapter = adapter
    return state


class TestRestorePartialWithErrorMarker:
    def test_appends_partial_then_marker_when_partial_present(self):
        session = _make_session([ChatMessage(role="user", content="hi")])
        partial = [
            ChatMessage(role="assistant", content="I was working on "),
            ChatMessage(role="tool", content="result-1", tool_call_id="t1"),
        ]
        _restore_partial_with_error_marker(
            session,
            state=None,
            partial=partial,
            display_msg="Boom",
            retryable=False,
        )
        # Pre-existing user msg + 2 partial msgs + error marker
        assert len(session.messages) == 4
        assert session.messages[1].content == "I was working on "
        assert session.messages[2].role == "tool"
        assert session.messages[3].content.startswith(COPILOT_ERROR_PREFIX)
        # Partial list is consumed (cleared) so a stray follow-up call won't
        # double-attach the same content.
        assert partial == []

    def test_only_marker_when_partial_empty(self):
        session = _make_session([ChatMessage(role="user", content="hi")])
        _restore_partial_with_error_marker(
            session,
            state=None,
            partial=[],
            display_msg="Boom",
            retryable=True,
        )
        assert len(session.messages) == 2
        assert session.messages[-1].content.startswith(COPILOT_RETRYABLE_ERROR_PREFIX)

    def test_noop_when_session_is_none(self):
        # Signature accepts None — must not raise.
        _restore_partial_with_error_marker(
            None,
            state=None,
            partial=[ChatMessage(role="assistant", content="x")],
            display_msg="Boom",
            retryable=False,
        )

    def test_flushes_unresolved_tools_between_partial_and_marker(self):
        session = _make_session([ChatMessage(role="user", content="hi")])
        partial = [
            ChatMessage(
                role="assistant",
                content="calling tool",
                tool_calls=[
                    {
                        "id": "t1",
                        "type": "function",
                        "function": {"name": "lookup", "arguments": "{}"},
                    }
                ],
            ),
        ]
        state = _adapter_with_unresolved([_make_tool_output("t1", "interrupted")])
        _restore_partial_with_error_marker(
            session,
            state=state,
            partial=partial,
            display_msg="Boom",
            retryable=False,
        )
        roles = [m.role for m in session.messages]
        # user, assistant(partial), tool(synthetic), assistant(error marker)
        assert roles == ["user", "assistant", "tool", "assistant"]
        synthetic_tool = session.messages[2]
        assert synthetic_tool.tool_call_id == "t1"
        assert synthetic_tool.content == "interrupted"


class TestFlushOrphanToolUses:
    def test_appends_synthetic_tool_results_for_unresolved(self):
        session = _make_session()
        state = _adapter_with_unresolved(
            [
                _make_tool_output("t1", "r1"),
                _make_tool_output("t2", {"ok": False}),
            ]
        )
        _flush_orphan_tool_uses_to_session(session, state)
        assert [m.tool_call_id for m in session.messages] == ["t1", "t2"]
        # Dict outputs are JSON-encoded so they survive the str-only ChatMessage
        # content field without losing structure for the next-turn LLM read.
        assert session.messages[1].content == '{"ok": false}'

    def test_noop_when_state_is_none(self):
        session = _make_session()
        _flush_orphan_tool_uses_to_session(session, None)
        assert session.messages == []

    def test_noop_when_no_unresolved(self):
        session = _make_session()
        adapter = MagicMock()
        adapter.has_unresolved_tool_calls = False
        state = MagicMock()
        state.adapter = adapter
        _flush_orphan_tool_uses_to_session(session, state)
        adapter._flush_unresolved_tool_calls.assert_not_called()


class TestRetryRollbackContract:
    """Property-style: a rolled-back attempt must be recoverable on final exit.

    Simulates the retry loop's rollback by mirroring the exact slicing and
    captured-list shape used in stream_chat_completion_sdk so that any drift
    in that contract is caught here without needing the full SDK fixture.
    """

    def test_capture_slice_matches_rollback(self):
        session = _make_session([ChatMessage(role="user", content="hi")])
        pre_attempt_msg_count = len(session.messages)
        # Simulate incremental SDK appends during the attempt.
        session.messages.extend(
            [
                ChatMessage(role="assistant", content="part-1"),
                ChatMessage(role="assistant", content="part-2"),
            ]
        )
        captured = list(session.messages[pre_attempt_msg_count:])
        session.messages = session.messages[:pre_attempt_msg_count]
        # Final-failure restore.
        _restore_partial_with_error_marker(
            session,
            state=None,
            partial=captured,
            display_msg="Boom",
            retryable=False,
        )
        contents = [m.content for m in session.messages]
        assert contents == [
            "hi",
            "part-1",
            "part-2",
            f"{COPILOT_ERROR_PREFIX} Boom",
        ]
