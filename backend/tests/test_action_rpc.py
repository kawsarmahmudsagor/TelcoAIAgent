"""The confirm card's RPC methods (app.agent.action_rpc). Room and session are fakes."""

import asyncio
import json
from decimal import Decimal
from types import SimpleNamespace

from sqlalchemy import func, select

from app.agent import actions
from app.agent.action_rpc import ActionRpc
from app.agent.tools import packages as package_tools
from app.agent.tools._common import ERROR_TEXT
from app.agent.topics import CONFIRM, OTP_SMS, RPC_CANCEL, RPC_CONFIRM
from app.agent.userdata import Channel, SessionUserdata
from app.models.telco import Transaction

CALLER = "web-user"


class FakeRoom:
    def __init__(self):
        self.sent: list[tuple[str, dict]] = []
        self.rpc: dict[str, object] = {}
        self.local_participant = self

    async def send_text(self, payload, *, topic, destination_identities=None):
        assert destination_identities == [CALLER]
        self.sent.append((topic, json.loads(payload)))

    def register_rpc_method(self, method, handler):
        self.rpc[method] = handler


class FakeSession:
    def __init__(self):
        self.replies: list[str] = []

    def generate_reply(self, *, instructions=None, **kwargs):
        self.replies.append(instructions)


def _setup(world):
    sub = world.subscriber(main_balance=Decimal("500"))
    pkg = world.package(name="PYTEST Net 10", data_mb=10240, price=Decimal("120"))
    room, session = FakeRoom(), FakeSession()
    ud = SessionUserdata(
        channel=Channel.inbound_chat,
        room=room,
        subscriber_id=sub.id,
        linked_identity=lambda: CALLER,
    )
    rpc = ActionRpc(session=session, userdata=ud, room=room, linked_identity=ud.linked_identity)
    rpc.register()
    return SimpleNamespace(sub=sub, pkg=pkg, room=room, session=session, ud=ud, rpc=rpc)


def _code(t) -> str:
    return [p for topic, p in t.room.sent if topic == OTP_SMS][-1]["code"]


def _txns(world, t) -> int:
    world.db.expire_all()
    return world.db.scalar(
        select(func.count()).select_from(Transaction).where(Transaction.subscriber_id == t.sub.id)
    )


async def _call(t, method, payload, caller=CALLER) -> dict:
    data = SimpleNamespace(
        request_id="r1", caller_identity=caller, payload=json.dumps(payload), response_timeout=15
    )
    return json.loads(await t.room.rpc[method](data))


async def _pending(t) -> str:
    await package_tools.run_purchase_package(t.ud, t.pkg.code)
    return str(t.ud.pending_action.action_id)


def test_rpc_registers_both_methods(bss_world):
    t = _setup(bss_world)
    assert set(t.room.rpc) == {RPC_CONFIRM, RPC_CANCEL}


def test_rpc_wrong_caller_refused(bss_world):
    t = _setup(bss_world)

    async def go():
        aid = await _pending(t)
        for method in (RPC_CONFIRM, RPC_CANCEL):
            r = await _call(t, method, {"action_id": aid, "code": _code(t)}, caller="intruder")
            assert r == {"ok": False, "error": "Not allowed."}
        assert t.ud.pending_action is not None and _txns(bss_world, t) == 0
        assert t.session.replies == []

    asyncio.run(go())


def test_rpc_bad_payload(bss_world):
    t = _setup(bss_world)

    async def go():
        data = SimpleNamespace(request_id="r", caller_identity=CALLER, payload="nope")
        r = json.loads(await t.rpc.confirm(data))
        assert r == {"ok": False, "error": "Bad request."}
        assert (await _call(t, RPC_CONFIRM, {"action_id": "x", "code": "1"}))["ok"] is False

    asyncio.run(go())


def test_rpc_confirm_executes_and_speaks(bss_world):
    t = _setup(bss_world)

    async def go():
        aid = await _pending(t)
        r = await _call(t, RPC_CONFIRM, {"action_id": aid, "code": _code(t)})
        assert r == {"ok": True, "error": None}
        assert _txns(bss_world, t) == 1 and t.ud.pending_action is None
        (said,) = t.session.replies
        assert said.startswith("The customer confirmed on the card. Done:")
        assert said.endswith("Tell them briefly it's done.")
        assert [p["state"] for topic, p in t.room.sent if topic == CONFIRM][-1] == "done"

    asyncio.run(go())


def test_rpc_wrong_code_reports_and_tells_session(bss_world):
    t = _setup(bss_world)

    async def go():
        aid = await _pending(t)
        bad = "000000" if _code(t) != "000000" else "111111"
        r = await _call(t, RPC_CONFIRM, {"action_id": aid, "code": bad})
        assert r == {"ok": False, "error": ERROR_TEXT["otp_invalid"]}
        assert ERROR_TEXT["otp_invalid"] in t.session.replies[0]
        assert _txns(bss_world, t) == 0 and t.ud.pending_action is not None

    asyncio.run(go())


def test_rpc_stale_action_id(bss_world):
    t = _setup(bss_world)

    async def go():
        await _pending(t)
        stale = "00000000-0000-4000-8000-000000000000"
        r = await _call(t, RPC_CONFIRM, {"action_id": stale, "code": _code(t)})
        assert r == {"ok": False, "error": ERROR_TEXT["no_pending_action"]}
        assert _txns(bss_world, t) == 0 and t.ud.pending_action is not None

    asyncio.run(go())


def test_rpc_and_voice_confirm_race_creates_one_transaction(bss_world):
    t = _setup(bss_world)

    async def go():
        aid = await _pending(t)
        code = _code(t)
        voice, card = await asyncio.gather(
            actions.confirm_action(t.ud, code),
            _call(t, RPC_CONFIRM, {"action_id": aid, "code": code}),
        )
        assert card["ok"] is True and voice.startswith("Done:")
        assert _txns(bss_world, t) == 1

    asyncio.run(go())


def test_rpc_cancel(bss_world):
    t = _setup(bss_world)

    async def go():
        aid = await _pending(t)
        r = await _call(t, RPC_CANCEL, {"action_id": aid})
        assert r == {"ok": True, "error": None}
        assert t.ud.pending_action is None and _txns(bss_world, t) == 0
        assert [p["state"] for topic, p in t.room.sent if topic == CONFIRM][-1] == "cancelled"
        assert t.session.replies[0].startswith("The customer cancelled on the card.")
        await t.rpc.settle()

    asyncio.run(go())
