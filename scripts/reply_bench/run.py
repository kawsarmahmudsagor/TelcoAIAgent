"""Run a scripted chat through the agent's real prompt, tools and LLM, in text
mode (no LiveKit room, no voice), and print each reply -- to compare reply
style before and after a prompt or tool-output change.

--baseline turns off the account highlights (app.agent.highlights) and drops
the BEYOND THE FIGURE paragraph from the default prompt, which is how the agent
answered before they were added.

Run from backend/ so the backend environment, .env and database are used:
    cd backend && uv run python ../scripts/reply_bench/run.py --customer Samiha
    cd backend && uv run python ../scripts/reply_bench/run.py --customer Samiha --baseline
    cd backend && uv run python ../scripts/reply_bench/run.py --guest

There is no turn gate here, so the router never prefetches: a lookup always
costs two LLM calls, where the live agent may need one.
"""

import argparse
import asyncio
import re
import sys
import time
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parents[1] / "backend"))

from livekit.agents import Agent, AgentSession  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app.agent import highlights, prompt_defaults  # noqa: E402
from app.agent.entrypoint import (  # noqa: E402
    _build_llm,
    _load_agent_config,
    _load_customer,
    _rag_enabled,
)
from app.agent.tools.search_knowledge_base import build_search_knowledge_base  # noqa: E402
from app.agent.persona import build_system_prompt  # noqa: E402
from app.agent.tools import registry  # noqa: E402
from app.agent.userdata import Channel, SessionUserdata  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.models.telco import Subscriber  # noqa: E402

# The turns of the sample conversation that prompted the change.
TURNS = [
    "amar balance koto?",
    "amar data koto ache?",
    "Which pack do I have?",
    "Balance?",
    "How many reward points do I have?",
    "How much data did I use this week?",
    "Which package is best for me?",
    "No, explain this one in details",
    "Show my usage for the last 30 days",
]

# A visitor who isn't logged in (the home page bubble).
GUEST_TURNS = [
    "Which monthly data packs do you have?",
    "amar balance koto?",
    "How do I get a new SIM?",
    "Is there a network problem in Dhaka?",
    "300 takar moddhe kono internet pack ache?",
    "Where is your nearest store?",
]


class _NoRoom:
    """Cards are published to the room; here they go nowhere."""

    class local_participant:  # noqa: N801
        @staticmethod
        async def send_text(*_args, **_kwargs):
            return None


def _subscriber_id(name: str):
    db = SessionLocal()
    try:
        sub = db.scalar(select(Subscriber).where(Subscriber.full_name.ilike(f"{name}%")).limit(1))
        if sub is None:
            raise SystemExit(f"no subscriber named {name!r}")
        return sub.id
    finally:
        db.close()


def _apply_baseline() -> None:
    highlights.block = lambda _items: ""
    highlights.relative_day = lambda _when, _today: None
    key = "prompt_identity_rules"
    prompt_defaults.DEFAULTS[key] = re.sub(
        r"\nBEYOND THE FIGURE.*?\n\n", "\n\n", prompt_defaults.DEFAULTS[key], flags=re.S
    )
    assert "BEYOND THE FIGURE" not in prompt_defaults.DEFAULTS[key]


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--customer", default="Samiha", help="start of the subscriber's full name")
    parser.add_argument("--baseline", action="store_true")
    parser.add_argument("--guest", action="store_true", help="not logged in")
    args = parser.parse_args()
    if args.baseline:
        _apply_baseline()

    config = _load_agent_config()
    if config.prompt_identity_rules is not None:
        print("NOTE: the dashboard has a customised identity/rules prompt; the default isn't used.\n")
    userdata = SessionUserdata(
        channel=Channel.inbound_chat,
        room=_NoRoom(),
        subscriber_id=None if args.guest else _subscriber_id(args.customer),
    )
    await _load_customer(userdata)
    userdata.greeting_done = True
    tools = registry.telco_tools()
    if _rag_enabled(config):
        tools.append(build_search_knowledge_base(config))
    agent = Agent(
        instructions=build_system_prompt(userdata, config, rag_tool_available=_rag_enabled(config)),
        tools=tools,
    )
    async with AgentSession(llm=_build_llm(get_settings(), config), userdata=userdata) as session:
        await session.start(agent)
        for turn in GUEST_TURNS if args.guest else TURNS:
            started = time.perf_counter()
            result = await session.run(user_input=turn)
            took = time.perf_counter() - started
            tools = [
                ev.item.name for ev in result.events if getattr(ev, "type", "") == "function_call"
            ]
            replies = [
                ev.item.text_content
                for ev in result.events
                if getattr(ev, "type", "") == "message" and ev.item.role == "assistant"
            ]
            print(f"> {turn}  ({took:.1f} s)")
            if tools:
                print(f"  [{', '.join(tools)}]")
            for reply in replies:
                print(f"  {reply}")
            print()


if __name__ == "__main__":
    asyncio.run(main())
