"""Tells the browser whose session this is, through ACCOUNT_ATTRIBUTE on the
agent participant. A session never changes account: when a guest logs in, or a
customer logs out or switches, the browser ends it and starts a new
conversation (frontend/components/customer/account-link.tsx).
"""

from livekit import rtc

from app.agent.userdata import SessionUserdata

# The agent's participant attribute: the session's subscriber id, "" for a guest.
# Must match ACCOUNT_ATTRIBUTE in frontend/components/customer/account-link.tsx.
ACCOUNT_ATTRIBUTE = "account"


async def publish_account(room: rtc.Room, userdata: SessionUserdata) -> None:
    sid = userdata.subscriber_id
    await room.local_participant.set_attributes({ACCOUNT_ATTRIBUTE: str(sid) if sid else ""})
