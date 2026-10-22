"""Tells the agent which listing the customer has open on the website.

The property page sets a `viewing_property_id` attribute on the browser's own
participant while a call is connected (and '' when it leaves). An attribute,
unlike a one-off message, is still there for whoever reads it later, so the
agent picks it up whether the page or the agent came first.

On each change the listing is loaded, numbered into `shown_listings` exactly
like a search result (so "book this one" resolves through the same
listing_number), and a short note is appended to the agent's instructions.
Agent.update_instructions replaces the instructions wholesale, so the note is
always added to the prompt the agent was built with, never to the current one.
"""

import asyncio
import logging
import uuid
from collections.abc import Callable

from livekit import rtc
from livekit.agents import Agent

from app.agent.tools.search_apartments import _assign_listing_numbers, listing_card
from app.agent.userdata import SessionUserdata
from app.db.session import SessionLocal
from app.repositories import property_repo
from app.services.taka import format_taka

logger = logging.getLogger("agent.viewing_context")

VIEWING_ATTRIBUTE = "viewing_property_id"


def _load_card(property_id: uuid.UUID) -> dict | None:
    db = SessionLocal()
    try:
        prop = property_repo.get_active(db, property_id)
        return listing_card(prop) if prop is not None else None
    finally:
        db.close()


def viewing_note(number: int, card: dict) -> str:
    area = card["neighborhood"] or card["city"]
    price = format_taka(card["price"], sale=card["listing_type"] == "sale")
    return (
        f"\n\nThe user is currently viewing listing #{number}: {card['title']}, {area}, "
        f"{price} ({card['listing_type']}), on the website. When they say "
        f'"this one", "this flat" or similar, they mean it: pass listing_number {number} '
        "to update_booking_form when booking it. Refer to it aloud by title or area, never by "
        "#number."
    )


class ViewingContext:
    def __init__(
        self,
        *,
        agent: Agent,
        userdata: SessionUserdata,
        base_prompt: str,
        linked_identity: Callable[[], str | None],
        load_card: Callable[[uuid.UUID], dict | None] = _load_card,
    ) -> None:
        self._agent = agent
        self._userdata = userdata
        self._base_prompt = base_prompt
        self._linked_identity = linked_identity
        self._load_card = load_card
        # Bumped on every change, so a slow load for a page the customer has
        # already left can't overwrite the newer one.
        self._generation = 0
        self._tasks: set[asyncio.Task] = set()

    def attach(self, room: rtc.Room) -> None:
        """Reads the linked participant's current value once, then follows changes."""
        identity = self._linked_identity()
        participant = room.remote_participants.get(identity) if identity else None
        if participant is not None:
            value = participant.attributes.get(VIEWING_ATTRIBUTE, "")
            if value:
                self._spawn(value)
        room.on("participant_attributes_changed", self.on_attributes_changed)

    def on_attributes_changed(self, changed: dict[str, str], participant) -> None:
        if VIEWING_ATTRIBUTE not in changed:
            return
        if participant.identity != self._linked_identity():
            return
        self._spawn(changed[VIEWING_ATTRIBUTE])

    def _spawn(self, value: str) -> None:
        self._generation += 1
        task = asyncio.ensure_future(self.apply(value, self._generation))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def settle(self) -> None:
        """Waits for every pending update (tests)."""
        while self._tasks:
            await asyncio.gather(*list(self._tasks))

    async def apply(self, value: str, generation: int | None = None) -> None:
        try:
            await self._apply(value, generation)
        except Exception:
            logger.exception("could not update the viewing context to %r", value)

    async def _apply(self, value: str, generation: int | None) -> None:
        card = None
        property_id = None
        if value:
            try:
                property_id = uuid.UUID(value)
            except ValueError:
                logger.warning("ignoring malformed %s %r", VIEWING_ATTRIBUTE, value)
            else:
                card = await asyncio.to_thread(self._load_card, property_id)
        if generation is not None and generation != self._generation:
            return

        if card is None:
            # Left the page, or a listing that's gone: drop the note.
            self._userdata.viewing_property_id = None
            await self._agent.update_instructions(self._base_prompt)
            return

        (number,) = _assign_listing_numbers(self._userdata.shown_listings, [card])
        self._userdata.viewing_property_id = property_id
        await self._agent.update_instructions(self._base_prompt + viewing_note(number, card))
