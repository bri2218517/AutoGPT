"""Sortable identifier helpers."""

from uuid_utils import uuid7


def new_uuid() -> str:
    """Return a fresh sortable UUIDv7 as a lower-case canonical string.

    Most create-paths can simply omit ``id`` — the schema default
    ``@default(dbgenerated("uuid_generate_v7()"))`` lets Postgres mint
    the value. Reach for this helper only when the id is needed *before*
    the insert (FK construction, return-then-insert, ID echoed back to
    a caller before the row is committed).
    """
    return str(uuid7())
