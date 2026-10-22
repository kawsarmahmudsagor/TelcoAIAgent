import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.client import Client, LeadStatus
from app.services.phone_numbers import normalize_bd_mobile


def get(db: Session, client_id: uuid.UUID) -> Client | None:
    return db.get(Client, client_id)


def get_by_email(db: Session, email: str) -> Client | None:
    stmt = select(Client).where(Client.email == email)
    return db.scalars(stmt).first()


def list_all(
    db: Session, *, lead_status: LeadStatus | None = None, limit: int = 100, offset: int = 0
) -> list[Client]:
    stmt = select(Client).order_by(Client.created_at.desc())
    if lead_status is not None:
        stmt = stmt.where(Client.lead_status == lead_status)
    stmt = stmt.limit(limit).offset(offset)
    return list(db.scalars(stmt))


def create(db: Session, data: dict) -> Client:
    client = Client(**data)
    db.add(client)
    db.commit()
    db.refresh(client)
    return client


def get_or_create_by_email(db: Session, *, full_name: str, email: str, phone: str | None) -> Client:
    existing = get_by_email(db, email)
    if existing:
        return existing
    return create(db, {"full_name": full_name, "email": email, "phone": phone})


def find_by_phone(db: Session, e164: str) -> Client | None:
    """The client whose stored phone is the BD mobile `e164`, however it was
    typed in ("01711-234567", "(+880) 1711 234567"). Phones are stored as
    entered, so the database narrows by the last 10 digits and Python confirms.
    Duplicates can exist (there's no unique index): the most recently updated
    one wins. A sequential scan is fine at this table's size."""
    digits = func.regexp_replace(Client.phone, "[^0-9]", "", "g")
    stmt = (
        select(Client)
        .where(Client.phone.is_not(None), func.right(digits, 10) == e164[-10:])
        .order_by(Client.updated_at.desc())
    )
    for client in db.scalars(stmt):
        try:
            if normalize_bd_mobile(client.phone) == e164:
                return client
        except ValueError:
            continue
    return None


def get_or_create_by_phone(db: Session, *, full_name: str, phone: str) -> Client:
    """`phone` is E.164 (normalize_bd_mobile). An existing client keeps the name
    on file: a name typed into a chat must never rename someone's record."""
    existing = find_by_phone(db, phone)
    if existing:
        return existing
    return create(db, {"full_name": full_name, "phone": phone})


def update(db: Session, client: Client, data: dict) -> Client:
    for key, value in data.items():
        if value is not None:
            setattr(client, key, value)
    db.commit()
    db.refresh(client)
    return client


def count(db: Session) -> int:
    return db.scalar(select(func.count()).select_from(Client)) or 0
