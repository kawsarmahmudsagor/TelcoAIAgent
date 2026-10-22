import asyncio
import uuid
from types import SimpleNamespace

import pytest
from livekit.agents.llm import ToolError

from app.agent.tools.schedule_followup import schedule_followup
from app.agent.userdata import Channel, SessionUserdata


def test_past_followup_rejected():
    ctx = SimpleNamespace(
        userdata=SessionUserdata(
            channel=Channel.outbound_coldcall,
            room=None,
            client=SimpleNamespace(id=uuid.uuid4()),
            call_schedule_id=uuid.uuid4(),
        )
    )
    with pytest.raises(ToolError):
        asyncio.run(schedule_followup(ctx, follow_up_date="2020-01-01T10:00:00", note="busy"))
