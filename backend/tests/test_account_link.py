"""The agent tells the browser whose session it is: "" for a guest, the
subscriber id for a customer. The browser ends a session whose account no
longer matches the login."""

import asyncio
import uuid

from app.agent import account_link
from app.agent.account_link import ACCOUNT_ATTRIBUTE
from app.agent.userdata import Channel, SessionUserdata


class FakeRoom:
    def __init__(self):
        self.attributes: dict[str, str] = {}
        self.local_participant = self

    async def set_attributes(self, attributes):
        self.attributes.update(attributes)


def test_publish_account_marks_guest_and_customer():
    async def go():
        room = FakeRoom()
        userdata = SessionUserdata(channel=Channel.inbound_chat, room=None)
        await account_link.publish_account(room, userdata)
        assert room.attributes == {ACCOUNT_ATTRIBUTE: ""}
        userdata.subscriber_id = uuid.uuid4()
        await account_link.publish_account(room, userdata)
        assert room.attributes == {ACCOUNT_ATTRIBUTE: str(userdata.subscriber_id)}

    asyncio.run(go())
