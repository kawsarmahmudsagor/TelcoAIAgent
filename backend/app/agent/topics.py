"""Data topics and RPC method names shared with the browser."""

import json
import logging

from app.agent.userdata import SessionUserdata

logger = logging.getLogger("agent.topics")

ACCOUNT_CHANGED = "telco.account_changed"
OTP_SMS = "telco.otp_sms"
CONFIRM = "telco.confirm"
RPC_CONFIRM = "telco.confirm_action"
RPC_CANCEL = "telco.cancel_action"


async def publish(userdata: SessionUserdata, topic: str, payload: dict) -> None:
    """Sends `payload` as JSON on `topic` right away (never deferred like cards).
    A failed send is logged, not raised."""
    try:
        await userdata.room.local_participant.send_text(json.dumps(payload), topic=topic)
    except Exception:
        logger.exception("could not send on %s", topic)
