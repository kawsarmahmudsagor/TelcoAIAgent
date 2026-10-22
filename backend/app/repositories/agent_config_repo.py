from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.agent_config import AgentConfig


def get(db: Session) -> AgentConfig | None:
    return db.scalar(select(AgentConfig).limit(1))


def get_or_create(db: Session) -> AgentConfig:
    """The migration inserts the singleton row; this only recreates it if
    someone deleted it. The singleton unique index turns a concurrent second
    insert into an IntegrityError, after which the winner's row is returned."""
    row = get(db)
    if row is not None:
        return row
    db.add(AgentConfig())
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
    return get(db)


def update(db: Session, row: AgentConfig, values: dict) -> AgentConfig:
    """Sets every key in `values`, None included (None = back to the default)."""
    for key, value in values.items():
        setattr(row, key, value)
    db.commit()
    db.refresh(row)
    return row
