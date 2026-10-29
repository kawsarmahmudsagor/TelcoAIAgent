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
    cd backend && uv run python ../scripts/reply_bench/run.py --sim

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

from app.agent import closing_offer, highlights, prompt_defaults  # noqa: E402
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


# A stolen SIM, in Bangla: knowledge-base wording and the nearest care centre.
SIM_TURNS = [
    "amar sim ta churi hoye geche, ki korbo?",
    "হ্যাঁ, একটু বলেন কোথায় যেতে হবে। আমি গাজীপুরে থাকি।",
    "ফি কত?",
    "customer care kothay? ami mirpur e thaki",
    "NID কার্ডের ফটোকপি আনলে হবে? না আমাকে অরিজিনাল NID কার্ডটাই আনতে হবে?",
    "এছাড়া কি আর কিছু করা লাগবে?",
]


# Package questions in Bangla: does the reply sound spoken, or translated?
PACKAGE_TURNS = [
    "কী কী প্যাকেজ আছে?",
    "ডাটা প্যাকেজ",
    "হ্যাঁ, আরও বলুন",
    "হ্যাঁ",
    "মিনিটের প্যাকেজ কী আছে?",
    "বিকাশ দিয়ে প্যাকেজ কিনলে কি পয়েন্ট পাবো?",
    "সাত দিনের মধ্যে কোনো কম্বো প্যাকেজ আছে?",
]

# Word-for-word translations the prompt warns about (LANGUAGE).
CALQUES = {
    "শুনবেন/শুনতে চান (hear more)": re.compile(r"শুনবেন|শুনতে চান"),
    "two offers in one question": re.compile(r"নাকি[^?]*দেব"),
    "কথা বলা নেই / উল্লেখ নেই": re.compile(r"কথা বলা নেই|উল্লেখ নেই"),
}


class _BenchAgent(Agent):
    """The live agents' per-turn additions that don't need a room."""

    def llm_node(self, chat_ctx, tools, model_settings):
        chat_ctx = closing_offer.with_reminder(chat_ctx, self.session.userdata)
        return Agent.default.llm_node(self, chat_ctx, tools, model_settings)


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
    parser.add_argument("--sim", action="store_true", help="the stolen-SIM conversation")
    parser.add_argument("--packages", action="store_true", help="package questions in Bangla")
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
    agent = _BenchAgent(
        instructions=build_system_prompt(userdata, config, rag_tool_available=_rag_enabled(config)),
        tools=tools,
    )
    async with AgentSession(llm=_build_llm(get_settings(), config), userdata=userdata) as session:
        await session.start(agent)
        turns = (
            PACKAGE_TURNS if args.packages
            else SIM_TURNS if args.sim
            else GUEST_TURNS if args.guest
            else TURNS
        )
        said: list[str] = []
        for turn in turns:
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
            said += replies
            print()
        endings = [re.split(r"(?<=[।.!])\s+", r.strip())[-1] for r in said if r.strip().endswith("?")]
        repeats = sum(a == b for a, b in zip(endings, endings[1:]))
        print(f"Same closing question twice in a row: {repeats}")
        print("Calques:")
        for name, pattern in CALQUES.items():
            print(f"  {name}: {sum(len(pattern.findall(r)) for r in said)}")


if __name__ == "__main__":
    asyncio.run(main())
