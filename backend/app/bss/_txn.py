"""Helpers shared by the transaction-writing BSS modules."""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.telco import Transaction, TxnType, txn_ref_seq


def existing(
    db: Session, subscriber_id: uuid.UUID, action_id: uuid.UUID, txn_type: TxnType
) -> Transaction | None:
    """Replay lookup, scoped to the subscriber so another subscriber's action_id
    never short-circuits OTP verification, and to the write's transaction type so
    an action_id used for one kind of write is never replayed as another.

    Writers call it twice: before OTP verification (the cheap replay) and again
    once they hold their row lock, so a concurrent confirmer that waited on the
    lock returns the first result instead of re-checking against the new state."""
    return db.scalar(
        select(Transaction).where(
            Transaction.action_id == action_id,
            Transaction.subscriber_id == subscriber_id,
            Transaction.type == txn_type,
        )
    )


def next_ref(db: Session) -> str:
    return f"TXN-{db.scalar(txn_ref_seq.next_value())}"
