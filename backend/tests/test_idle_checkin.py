import asyncio
from types import SimpleNamespace

from app.agent.idle_checkin import IdleCheckIn
from app.agent.prompt_defaults import IDLE_CHECKIN_LINES, IDLE_GOODBYE_LINES

IDLE = 0.2
GRACE = 0.2


class FakeHandle:
    async def wait_for_playout(self):
        return None


class FakeSession:
    def __init__(self, last_reply="আপনি কেমন বাসা খুঁজছেন?"):
        self.handlers: dict[str, object] = {}
        self.said: list[str] = []
        self.history = SimpleNamespace(
            items=[SimpleNamespace(role="assistant", text_content=last_reply)]
        )

    def on(self, event, handler):
        self.handlers[event] = handler

    def say(self, text, **kwargs):
        self.said.append(text)
        return FakeHandle()

    def emit(self, event, ev):
        self.handlers[event](ev)


def _state(new_state):
    return SimpleNamespace(new_state=new_state)


def _user_turn():
    return SimpleNamespace(item=SimpleNamespace(role="user"))


def _watcher(session, ended):
    async def on_end():
        ended.append(True)

    watcher = IdleCheckIn(
        session=session,
        on_end=on_end,
        idle_s=IDLE,
        grace_s=GRACE,
    )
    watcher.attach()
    watcher.start()
    return watcher


async def _wait(seconds):
    await asyncio.sleep(seconds + 0.1)


def test_quiet_customer_is_asked_then_call_ends():
    async def run():
        session, ended = FakeSession(), []
        _watcher(session, ended)
        await _wait(IDLE)
        assert session.said == [IDLE_CHECKIN_LINES["bn"]]
        # The check-in plays out.
        session.emit("agent_state_changed", _state("speaking"))
        session.emit("agent_state_changed", _state("listening"))
        await _wait(GRACE)
        assert session.said[-1] == IDLE_GOODBYE_LINES["bn"]
        assert ended == [True]

    asyncio.run(run())


def test_check_in_follows_the_reply_language():
    async def run():
        session = FakeSession(last_reply="Here are three flats in Gulshan.")
        _watcher(session, [])
        await _wait(IDLE)
        assert session.said == [IDLE_CHECKIN_LINES["en"]]

    asyncio.run(run())


def test_answer_to_check_in_keeps_the_call():
    async def run():
        session, ended = FakeSession(), []
        _watcher(session, ended)
        await _wait(IDLE)
        session.emit("agent_state_changed", _state("listening"))
        # They ask something; the agent answers it.
        session.emit("conversation_item_added", _user_turn())
        session.emit("agent_state_changed", _state("thinking"))
        session.emit("agent_state_changed", _state("speaking"))
        await _wait(GRACE)
        assert ended == []
        session.emit("agent_state_changed", _state("listening"))
        # The clock starts over: asked again, not hung up on.
        await _wait(IDLE)
        assert session.said == [IDLE_CHECKIN_LINES["bn"]] * 2
        assert ended == []

    asyncio.run(run())


def test_agent_speaking_doesnt_count_as_idle():
    async def run():
        session = FakeSession()
        _watcher(session, [])
        session.emit("agent_state_changed", _state("speaking"))
        await _wait(IDLE)
        assert session.said == []

    asyncio.run(run())


def test_customer_turns_restart_the_clock():
    async def run():
        session = FakeSession()
        _watcher(session, [])
        for _ in range(3):
            await asyncio.sleep(IDLE * 0.4)
            session.emit("conversation_item_added", _user_turn())
        assert session.said == []

    asyncio.run(run())


def test_nothing_before_start():
    async def run():
        session = FakeSession()
        watcher = IdleCheckIn(
            session=session,
                on_end=None,
            idle_s=IDLE,
            grace_s=GRACE,
        )
        watcher.attach()
        session.emit("agent_state_changed", _state("listening"))
        await _wait(IDLE)
        assert session.said == []

    asyncio.run(run())
