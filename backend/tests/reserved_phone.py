"""Phone numbers for tests that book viewings (bookings find or create the
client by phone). Numbers come from a range set aside for tests and are checked
unused, so a test never books onto, or cleans up, a real client. Tests clean up
by the client ids they created, never by matching a phone."""

import random

from sqlalchemy import text

from app.db.session import SessionLocal
from app.repositories import client_repo
from app.services.phone_numbers import normalize_bd_mobile

# 0139999xxxx: a valid Grameenphone-shaped mobile range kept for tests.
TEST_PHONE_PREFIX = "0139999"


def unused_test_phone() -> str:
    """A local-format ("0139999xxxx") test number no client has."""
    db = SessionLocal()
    try:
        for _ in range(50):
            local = f"{TEST_PHONE_PREFIX}{random.randrange(10_000):04d}"
            if client_repo.find_by_phone(db, normalize_bd_mobile(local)) is None:
                return local
    finally:
        db.close()
    raise RuntimeError("no unused test phone number left")


def delete_clients(client_ids) -> None:
    """Deletes these clients with their bookings and invites."""
    ids = [str(i) for i in client_ids if i is not None]
    if not ids:
        return
    db = SessionLocal()
    try:
        p = {"ids": ids}
        db.execute(
            text(
                "delete from meeting_invites where booking_id in "
                "(select id from bookings where client_id::text = any(:ids))"
            ),
            p,
        )
        db.execute(text("delete from bookings where client_id::text = any(:ids)"), p)
        db.execute(text("delete from clients where id::text = any(:ids)"), p)
        db.commit()
    finally:
        db.close()
