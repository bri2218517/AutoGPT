"""Sortable identifier helpers."""

from uuid_utils import uuid7


def new_uuid() -> str:
    """Return a fresh sortable UUIDv7 as a lower-case canonical string.

    Use this for any application-level ID generation that lands in a Prisma
    column. Schema-level ``@default(dbgenerated("uuid_generate_v7()"))``
    covers the path where Prisma populates the id; this helper is the
    Python-side counterpart for code that needs the id before insert.
    """
    return str(uuid7())
