from datetime import datetime, timedelta, timezone

from app.data import seed_clients, seed_offers, seed_properties
from app.db.session import SessionLocal
from app.models.client import Client
from app.models.call_schedule import CallScheduleEntry


def seed_call_schedule(db) -> int:
    existing = db.query(CallScheduleEntry).count()
    if existing:
        return 0
    clients = db.query(Client).limit(2).all()
    if not clients:
        return 0
    now = datetime.now(timezone.utc)
    for offset_minutes, client in zip([1, 5], clients, strict=False):
        db.add(
            CallScheduleEntry(
                client_id=client.id,
                scheduled_at=now + timedelta(minutes=offset_minutes),
            )
        )
    db.commit()
    return len(clients[:2])


def main() -> None:
    db = SessionLocal()
    try:
        props = seed_properties.seed(db)
        clients = seed_clients.seed(db)
        calls = seed_call_schedule(db)
        offers = seed_offers.seed(db)
        print(
            f"Seeded {props} properties, {clients} clients, {calls} call_schedule entries, "
            f"{offers} offers."
        )
    finally:
        db.close()


if __name__ == "__main__":
    main()
