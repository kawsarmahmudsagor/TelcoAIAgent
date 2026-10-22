import inspect
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

from app.agent.persona import build_system_prompt, knowledge_scope_text
from app.agent.prompt_defaults import DEFAULT_IDENTITY_AND_RULES
from app.agent.tools.search_knowledge_base import (
    NOTHING_FOUND,
    UNAVAILABLE,
    build_search_knowledge_base,
)
from app.agent.tools.book_appointment import book_appointment
from app.agent.tools.booking_form import update_booking_form
from app.agent.tools.search_apartments import search_apartments
from app.agent import entrypoint
from app.agent.userdata import Channel, SessionUserdata, UpcomingViewing
from app.services import agent_config_service


def _client():
    return SimpleNamespace(
        id=uuid.uuid4(), full_name="Rahim Uddin", email=None, preferred_property_type=None,
        preferred_location=None, budget_min=None, budget_max=None, rent_or_buy=None,
    )  # fmt: skip


def _viewing() -> UpcomingViewing:
    # 04:00 UTC is 10:00 in Dhaka (the default AGENCY_TIMEZONE).
    return UpcomingViewing(
        booking_id=uuid.uuid4(),
        when=datetime(2026, 10, 14, 4, 0, tzinfo=timezone.utc),
        property_title="3-bed Gulshan flat",
    )


def _prompts(*, rag: bool = False) -> dict[str, str]:
    config = agent_config_service.resolve(None)
    variants = {
        "inbound_web": SessionUserdata(channel=Channel.inbound_chat, room=None),
        "inbound_phone": SessionUserdata(
            channel=Channel.inbound_chat, room=None, is_phone_call=True
        ),
        "outbound_web": SessionUserdata(
            channel=Channel.outbound_coldcall, room=None, client=_client()
        ),
        "outbound_phone": SessionUserdata(
            channel=Channel.outbound_coldcall, room=None, client=_client(), is_phone_call=True
        ),
        "outbound_viewing_web": SessionUserdata(
            channel=Channel.outbound_coldcall, room=None, client=_client(),
            upcoming_viewing=_viewing(),
        ),
        "outbound_viewing_phone": SessionUserdata(
            channel=Channel.outbound_coldcall, room=None, client=_client(), is_phone_call=True,
            upcoming_viewing=_viewing(),
        ),
    }  # fmt: skip
    return {
        name: build_system_prompt(userdata, config, rag_tool_available=rag)
        for name, userdata in variants.items()
    }


def test_no_missing_tools_mentioned():
    for name, prompt in _prompts().items():
        assert "search_knowledge_base" not in prompt, name
        # Every session has end_call: a browser call ends on a goodbye.
        assert "end_call" in prompt, name
        # Inbound sessions never get the cold-call tools.
        assert ("confirm_interest" in prompt) == name.startswith("outbound"), name
        # Only a follow-up of a booked viewing can move it.
        assert ("reschedule_viewing" in prompt) == ("_viewing_" in name), name


def test_a_viewing_follow_up_names_the_viewing_in_local_time():
    for name, prompt in _prompts().items():
        assert ("VIEWING FOLLOW-UP" in prompt) == ("_viewing_" in name), name
        if "_viewing_" in name:
            assert "3-bed Gulshan flat on Wednesday 14 October 2026, 10:00" in prompt


def test_a_cold_call_claims_no_earlier_interest():
    for name, prompt in _prompts().items():
        if not name.startswith("outbound"):
            continue
        cold = "_viewing_" not in name
        # Only a lead with no booked viewing gets the cold-call introduction.
        assert ("introductory cold call" in prompt) == cold, name
        assert "interested in:" not in prompt, name
        assert "still interested" not in prompt, name
        assert "Nothing on file — find out what they're looking for." in prompt, name


def test_a_cold_call_passes_on_file_criteria_as_a_hint():
    client = _client()
    client.preferred_property_type = "apartment"
    client.preferred_location = "Gulshan"
    userdata = SessionUserdata(channel=Channel.outbound_coldcall, room=None, client=client)
    prompt = build_system_prompt(userdata, agent_config_service.resolve(None))
    assert "Their file has: apartment, in Gulshan." in prompt
    assert "Nothing on file" not in prompt


def test_reschedule_viewing_is_a_tool_only_when_there_is_a_viewing_to_move():
    def names(userdata):
        return {getattr(t, "id", None) or getattr(t, "__name__", "") for t in
                entrypoint._session_tools(userdata)}  # fmt: skip

    inbound = SessionUserdata(channel=Channel.inbound_chat, room=None)
    cold = SessionUserdata(channel=Channel.outbound_coldcall, room=None, client=_client())
    followup = SessionUserdata(
        channel=Channel.outbound_coldcall, room=None, client=_client(), upcoming_viewing=_viewing()
    )
    assert "reschedule_viewing" not in names(inbound)
    assert "reschedule_viewing" not in names(cold)
    assert "reschedule_viewing" in names(followup)


def test_rag_scope_replaces_default_scope():
    config = agent_config_service.resolve(None)
    for prompt in _prompts(rag=True).values():
        assert "search_knowledge_base" in prompt
        assert knowledge_scope_text(config, False) not in prompt
        assert knowledge_scope_text(config, True) in prompt


def test_unknown_details_point_to_the_agency_contact():
    config = agent_config_service.resolve(None)
    for rag in (False, True):
        for name, prompt in _prompts(rag=rag).items():
            assert config.agency_phone in prompt, (name, rag)
            assert config.agency_address in prompt, (name, rag)
            flat = _flat(prompt)
            assert "never say you don't have the information" in flat, (name, rag)
            assert "আমাদের কাছে নেই" in flat, (name, rag)
            assert "নিশ্চিত করে বলতে পারছি না" in flat, (name, rag)
            assert "fixed or negotiable" in flat, (name, rag)
            # Citing the listing is allowed; only commercial questions reach the head office.
            assert "the listing doesn't mention" in flat, (name, rag)
            assert "offer a viewing" in flat, (name, rag)
            assert "Questions on schools, transport" not in flat, (name, rag)
            assert "{agency_" not in prompt, (name, rag)
            assert "say you don't have that detail" not in flat, (name, rag)
            assert "no data on" not in flat, (name, rag)


def test_knowledge_base_tool_points_to_the_team_not_a_shrug():
    tool = build_search_knowledge_base(agent_config_service.resolve(None))
    description = _description(tool)
    assert "don't have that detail" not in description
    assert "head office" in description
    assert "head office" in NOTHING_FOUND
    assert "head office" in UNAVAILABLE


def test_polite_examples_drop_janaben():
    flat = _flat(DEFAULT_IDENTITY_AND_RULES)
    examples = flat.split("use polite forms (")[1].split(")")[0]
    assert "জানাবেন" not in examples
    assert "don't tack \"জানাবেন?\" onto it" in flat


def test_bangla_asks_with_chacchen():
    for name, prompt in _prompts().items():
        assert 'use "চাচ্ছেন", never "চাইবেন"' in prompt, name


def test_screen_is_only_mentioned_for_web_chat():
    prompts = _prompts()
    assert "on web chat they also see every result on screen" in prompts["inbound_web"]
    assert "the customer has no screen" in prompts["inbound_phone"]


def test_boundaries_and_currency_rules_present():
    for name, prompt in _prompts().items():
        assert "BOUNDARIES" in prompt, name
        assert "digits, in every language" in prompt, name
        assert "reply in Bangla in Bengali\nscript, never in English letters" in prompt, name
        assert '"taka" (টাকা in Bangla script), never "৳"' in prompt, name


def test_phone_end_reasons_match_the_channel():
    prompts = _prompts()
    assert "asked to be called later" in prompts["outbound_phone"]
    assert "said they'll call back later" in prompts["inbound_phone"]
    assert "asked to be called later" not in prompts["inbound_phone"]
    for name in ("inbound_phone", "outbound_phone"):
        assert "abusive after a warning" in prompts[name]


def _description(tool) -> str:
    return " ".join(tool.info.description.split())


def test_search_description_keeps_partial_criteria_rules():
    description = _description(search_apartments)
    for phrase in ("a location alone", "a budget alone", "a property type alone"):
        assert phrase in description
    assert "budget_max to None" in description


def _params(tool) -> list[str]:
    return list(inspect.signature(tool._func).parameters)


def test_booking_takes_a_name_and_phone_never_an_email():
    assert "Never ask for an email address" in _description(update_booking_form)
    assert _params(update_booking_form) == [
        "ctx",
        "listing_number",
        "proposed_datetime",
        "full_name",
        "phone",
    ]
    booking = _description(book_appointment)
    assert "It takes no arguments" in booking
    assert "clearly said yes" in booking
    assert _params(book_appointment) == ["ctx"]


def _flat(prompt: str) -> str:
    return " ".join(prompt.split())


def test_prompts_ask_for_name_and_phone_never_email():
    for name, prompt in _prompts().items():
        flat = _flat(prompt)
        assert "ask only for a name and a mobile phone number, never an email address" in flat, name
        assert "Never ask for an email address" in flat, name
        assert "update_booking_form" in flat, name
        assert "read back the name, phone number, property and time" in flat, name
        assert "call book_appointment (it takes no arguments)" in flat, name
        on_screen = "type their name and number into the form on screen" in flat
        assert on_screen == name.endswith("_web"), name


def test_offers_guardrail_in_every_prompt():
    from app.agent.tools import ALL_TOOLS, INBOUND_TOOLS
    from app.agent.tools.search_offers import search_offers

    assert search_offers in ALL_TOOLS and search_offers in INBOUND_TOOLS
    for name, prompt in _prompts().items():
        flat = _flat(prompt)
        assert "call search_offers and quote only the offers it returns" in flat, name
        assert "Never invent, combine, estimate or negotiate a discount" in flat, name
