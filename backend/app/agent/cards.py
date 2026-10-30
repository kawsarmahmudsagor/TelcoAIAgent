"""Cards for the browser: JSON sent on a data topic to the customer's screen.

On gated sessions (userdata.defer_cards) a card waits in userdata.pending_card
until the reply that goes with it is heard: its text is all in (cards_ready, from
GatedAgent._cards_with_speech, which also picks the package card) and its own
speech has started (reply_speaking, from GatedAgent.transcription_node), not
while a filler line, its pause or the lookup is still going."""

import json
import logging

from app.agent.topics import PACKAGES
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
    if topic == PACKAGES:
        userdata.shown_packages = payload
        userdata.turn_card_codes |= {p["code"] for p in json.loads(payload)["packages"]}


async def send_now(userdata: SessionUserdata, topic: str, payload: str) -> None:
    """Sends the card at once, deferred or not: for a reply already speaking."""
    await _send(userdata, topic, payload)


def new_reply(userdata: SessionUserdata) -> None:
    """A reply step starts: its card waits for its own text and speech."""
    userdata.cards_ready = False
    userdata.reply_speaking = False


async def cards_ready(userdata: SessionUserdata) -> None:
    """The reply's text is in: the held card goes once its speech has started."""
    userdata.cards_ready = True
    if userdata.reply_speaking:
        await flush_pending_card(userdata)


async def reply_speaking(userdata: SessionUserdata) -> None:
    """A segment of the reply starts being heard: the held card goes once the
    reply's text is in."""
    userdata.reply_speaking = True
    if userdata.cards_ready:
        await flush_pending_card(userdata)


def held_packages(userdata: SessionUserdata) -> bool:
    """Whether the held card is a package card: it waits for the reply's words
    to end (app.agent.tools.packages.publish_reply_cards), not its first ones."""
    return userdata.pending_card is not None and userdata.pending_card[0] == PACKAGES


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
