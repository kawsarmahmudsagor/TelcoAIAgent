"""Helpers shared by the transaction-writing BSS modules."""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.telco import Transaction, txn_ref_seq


def existing(db: Session, subscriber_id: uuid.UUID, action_id: uuid.UUID) -> Transaction | None:
    """Replay lookup, scoped to the subscriber so another subscriber's action_id
    never short-circuits OTP verification."""
    return db.scalar(
        select(Transaction).where(
            Transaction.action_id == action_id, Transaction.subscriber_id == subscriber_id
        )
    )


def next_ref(db: Session) -> str:
    return f"TXN-{db.scalar(txn_ref_seq.next_value())}"
