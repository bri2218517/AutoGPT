"""Common test fixtures for server tests.

Note: Common fixtures like test_user_id, admin_user_id, target_user_id,
setup_test_user, and setup_admin_user are defined in the parent conftest.py
(backend/conftest.py) and are available here automatically.
"""

import pytest
from pytest_snapshot.plugin import Snapshot


@pytest.fixture
def configured_snapshot(snapshot: Snapshot) -> Snapshot:
    """Pre-configured snapshot fixture with standard settings."""
    snapshot.snapshot_dir = "snapshots"
    return snapshot


@pytest.fixture
def mock_jwt_user(test_user_id):
    """Provide mock JWT payload for regular user testing."""
    import fastapi

    from autogpt_libs.auth.models import RequestContext

    def override_get_jwt_payload(request: fastapi.Request) -> dict[str, str]:
        return {"sub": test_user_id, "role": "user", "email": "test@example.com"}

    def override_get_request_context() -> RequestContext:
        return RequestContext(
            user_id=test_user_id,
            org_id="test-org",
            team_id="test-team",
            is_org_owner=True,
            is_org_admin=True,
            is_org_billing_manager=False,
            is_team_admin=True,
            is_team_billing_manager=False,
            seat_status="ACTIVE",
        )

    return {
        "get_jwt_payload": override_get_jwt_payload,
        "get_request_context": override_get_request_context,
        "user_id": test_user_id,
    }


@pytest.fixture
def mock_jwt_admin(admin_user_id):
    """Provide mock JWT payload for admin user testing."""
    import fastapi

    from autogpt_libs.auth.models import RequestContext

    def override_get_jwt_payload(request: fastapi.Request) -> dict[str, str]:
        return {
            "sub": admin_user_id,
            "role": "admin",
            "email": "test-admin@example.com",
        }

    def override_get_request_context() -> RequestContext:
        return RequestContext(
            user_id=admin_user_id,
            org_id="test-org",
            team_id="test-team",
            is_org_owner=True,
            is_org_admin=True,
            is_org_billing_manager=True,
            is_team_admin=True,
            is_team_billing_manager=True,
            seat_status="ACTIVE",
        )

    return {
        "get_jwt_payload": override_get_jwt_payload,
        "get_request_context": override_get_request_context,
        "user_id": admin_user_id,
    }
