from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from backend.data.execution import ExecutionStatus, reap_orphan_node_executions


def _candidate(node_exec_id: str, parent_status: str, started_seconds_ago: int = 600):
    """Build a fake AgentNodeExecution row with an attached GraphExecution."""
    return SimpleNamespace(
        id=node_exec_id,
        executionStatus=ExecutionStatus.RUNNING.value,
        startedTime=datetime.now(tz=timezone.utc)
        - timedelta(seconds=started_seconds_ago),
        GraphExecution=SimpleNamespace(executionStatus=parent_status),
    )


@pytest.mark.asyncio
async def test_reaper_marks_node_execs_failed_when_parent_terminal():
    """RUNNING node_execs whose parent is FAILED/COMPLETED/TERMINATED should be reaped."""
    candidates = [
        _candidate("ne-failed", ExecutionStatus.FAILED.value),
        _candidate("ne-completed", ExecutionStatus.COMPLETED.value),
        _candidate("ne-terminated", ExecutionStatus.TERMINATED.value),
        _candidate("ne-still-running", ExecutionStatus.RUNNING.value),
    ]

    with (
        patch("backend.data.execution.AgentNodeExecution") as mock_ne,
        patch(
            "backend.data.execution.update_node_execution_status_batch",
            new_callable=AsyncMock,
        ) as mock_batch,
    ):
        mock_ne.prisma.return_value.find_many = AsyncMock(return_value=candidates)
        mock_batch.return_value = 3

        reaped = await reap_orphan_node_executions()

    assert reaped == 3
    mock_batch.assert_awaited_once()
    reaped_ids, status, *_ = mock_batch.await_args.args
    kwargs = mock_batch.await_args.kwargs
    assert sorted(reaped_ids) == ["ne-completed", "ne-failed", "ne-terminated"]
    assert status == ExecutionStatus.FAILED
    assert kwargs.get("stats", {}).get("error") == "orphaned_after_graph_terminal"


@pytest.mark.asyncio
async def test_reaper_no_op_when_all_parents_running():
    """No reaping if all parents are still RUNNING."""
    candidates = [
        _candidate(f"ne-{i}", ExecutionStatus.RUNNING.value) for i in range(3)
    ]

    with (
        patch("backend.data.execution.AgentNodeExecution") as mock_ne,
        patch(
            "backend.data.execution.update_node_execution_status_batch",
            new_callable=AsyncMock,
        ) as mock_batch,
    ):
        mock_ne.prisma.return_value.find_many = AsyncMock(return_value=candidates)

        reaped = await reap_orphan_node_executions()

    assert reaped == 0
    mock_batch.assert_not_awaited()


@pytest.mark.asyncio
async def test_reaper_query_filters_by_min_age_and_running_status():
    """Verify the prisma find_many is constrained to old RUNNING node_execs only."""
    with (
        patch("backend.data.execution.AgentNodeExecution") as mock_ne,
        patch(
            "backend.data.execution.update_node_execution_status_batch",
            new_callable=AsyncMock,
        ),
    ):
        find_many = AsyncMock(return_value=[])
        mock_ne.prisma.return_value.find_many = find_many

        await reap_orphan_node_executions(min_age_seconds=900, limit=500)

    where = find_many.await_args.kwargs["where"]
    assert where["executionStatus"] == ExecutionStatus.RUNNING.value
    assert "lt" in where["startedTime"]
    assert find_many.await_args.kwargs["take"] == 500
    assert find_many.await_args.kwargs["include"] == {"GraphExecution": True}


@pytest.mark.asyncio
async def test_reaper_returns_actual_db_update_count_not_candidate_count():
    """If a candidate transitions away from RUNNING between find_many and
    update_many (TOCTOU), the reaper must report the real DB-update count
    rather than `len(orphan_ids)`."""
    candidates = [
        _candidate("ne-1", ExecutionStatus.FAILED.value),
        _candidate("ne-2", ExecutionStatus.FAILED.value),
        _candidate("ne-3", ExecutionStatus.FAILED.value),
    ]

    with (
        patch("backend.data.execution.AgentNodeExecution") as mock_ne,
        patch(
            "backend.data.execution.update_node_execution_status_batch",
            new_callable=AsyncMock,
        ) as mock_batch,
    ):
        mock_ne.prisma.return_value.find_many = AsyncMock(return_value=candidates)
        # Simulate one row already having transitioned away from RUNNING.
        mock_batch.return_value = 2

        reaped = await reap_orphan_node_executions()

    assert reaped == 2
