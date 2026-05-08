from unittest.mock import MagicMock, patch

from backend.monitoring.late_execution_monitor import (
    ORPHAN_REAP_MIN_AGE_SECONDS,
    reap_orphan_node_executions,
)


def test_reap_orphan_node_executions_calls_dbm_with_min_age():
    """The reaper wrapper must call the DB-manager RPC with the configured
    minimum-age threshold so we don't race healthy in-flight executions."""
    with patch(
        "backend.monitoring.late_execution_monitor.get_database_manager_client"
    ) as mock_client:
        mock_dbm = MagicMock()
        mock_dbm.reap_orphan_node_executions.return_value = 0
        mock_client.return_value = mock_dbm

        msg = reap_orphan_node_executions()

    mock_dbm.reap_orphan_node_executions.assert_called_once_with(
        min_age_seconds=ORPHAN_REAP_MIN_AGE_SECONDS,
    )
    assert "0 orphan" in msg


def test_reap_orphan_node_executions_returns_count_in_message():
    with patch(
        "backend.monitoring.late_execution_monitor.get_database_manager_client"
    ) as mock_client:
        mock_dbm = MagicMock()
        mock_dbm.reap_orphan_node_executions.return_value = 7
        mock_client.return_value = mock_dbm

        msg = reap_orphan_node_executions()

    assert "7 orphan" in msg
