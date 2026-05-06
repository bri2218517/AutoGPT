# autogpt_platform/backend/backend/server/v2/preferences/routes.py
#
# User preferences endpoints. Generic per-user key/value store scoped under
# /api/me/preferences. The changelog feature uses key "changelog.lastSeenId".
#
# Integration TODOs (three short edits):
# 1. Auth dependency: replace `get_user_id` with whatever the v2 routes use
#    (likely `requires_user` from backend.server.utils).
# 2. Prisma import: adjust `from backend.data.db import prisma` to match your
#    generated client path.
# 3. Router mounting: wire into the v2 app in backend/server/v2/__init__.py
#    the same way other v2 routers are mounted.

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from backend.data.db import prisma  # adjust import to match your setup
from backend.server.utils import get_user_id  # adjust to your auth dep

router = APIRouter(prefix="/preferences", tags=["preferences"])

KEY_CHANGELOG_LAST_SEEN = "changelog.lastSeenId"


class ChangelogPrefs(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    last_seen_id: str | None = Field(default=None, alias="lastSeenId")


@router.get(
    "/changelog",
    response_model=ChangelogPrefs,
    response_model_by_alias=True,
)
async def get_changelog_prefs(
    user_id: str = Depends(get_user_id),
) -> ChangelogPrefs:
    pref = await prisma.userpreference.find_unique(
        where={
            "userId_key": {
                "userId": user_id,
                "key": KEY_CHANGELOG_LAST_SEEN,
            }
        }
    )
    return ChangelogPrefs(last_seen_id=pref.value if pref else None)


@router.put(
    "/changelog",
    response_model=ChangelogPrefs,
    response_model_by_alias=True,
)
async def put_changelog_prefs(
    body: ChangelogPrefs,
    user_id: str = Depends(get_user_id),
) -> ChangelogPrefs:
    if not body.last_seen_id:
        raise HTTPException(status_code=400, detail="lastSeenId is required")

    if len(body.last_seen_id) > 64:
        raise HTTPException(status_code=400, detail="lastSeenId too long")

    await prisma.userpreference.upsert(
        where={
            "userId_key": {
                "userId": user_id,
                "key": KEY_CHANGELOG_LAST_SEEN,
            }
        },
        data={
            "create": {
                "userId": user_id,
                "key": KEY_CHANGELOG_LAST_SEEN,
                "value": body.last_seen_id,
            },
            "update": {"value": body.last_seen_id},
        },
    )
    return body
