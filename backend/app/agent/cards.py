"""Cards for the browser: JSON sent on a data topic to the customer's screen.

With quick replies on (userdata.defer_cards) a card waits in userdata.pending_card
until the main model's reply starts speaking (GatedAgent._cards_with_speech), not
while a filler line or the lookup is still going."""

import logging

from app.agent.userdata import SessionUserdata

logger = logging.getLogger("agent.cards")


async def send_card(userdata: SessionUserdata, topic: str, payload: str) -> None:
    """Puts the card (a JSON string) on the customer's screen under `topic`.
    With userdata.defer_cards the latest card waits for flush_pending_card."""
    if userdata.defer_cards:
        userdata.pending_card = (topic, payload)
        return
    await _send(userdata, topic, payload)


async def _send(userdata: SessionUserdata, topic: str, payload: str) -> None:
    """To the linked browser alone, as app.agent.topics.publish sends; with no
    identity to send to, nothing is sent."""
    identity = userdata.linked_identity() if userdata.linked_identity else None
    if identity is None:
        logger.warning("no linked participant; %s card not sent", topic)
        return
    await userdata.room.local_participant.send_text(
        payload, topic=topic, destination_identities=[identity]
    )


async def flush_pending_card(userdata: SessionUserdata) -> bool:
    """Sends the card send_card held back. False when there was none (or the
    send failed)."""
    pending = userdata.pending_card
    if pending is None:
        return False
    userdata.pending_card = None
    topic, payload = pending
    try:
        await _send(userdata, topic, payload)
    except Exception:
        logger.exception("could not send the %s card", topic)
        return False
    return True
