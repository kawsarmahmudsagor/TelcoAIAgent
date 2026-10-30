import inspect

import re

from app.agent import entrypoint
from app.agent.persona import build_system_prompt, knowledge_scope_text
from app.agent.prompt_defaults import (
    DEFAULT_GREETING_INBOUND,
    DEFAULT_GREETING_NUDGE,
    DEFAULT_IDENTITY_AND_RULES,
    IDLE_CHECKIN_LINES,
    IDLE_GOODBYE_LINES,
    SPOKEN_GREETINGS_GUEST,
    SPOKEN_GREETINGS_INBOUND,
)
from app.agent.snapshot import GUEST_SNAPSHOT
from app.agent.tools.search_knowledge_base import (
    NOTHING_FOUND,
    UNAVAILABLE,
    build_search_knowledge_base,
)
from app.agent.userdata import Channel, SessionUserdata
from app.services import agent_config_service
from word_checks import real_estate_words


def _prompts(*, rag: bool = False) -> dict[str, str]:
    config = agent_config_service.resolve(None)
    variants = {"inbound_web": SessionUserdata(channel=Channel.inbound_chat, room=None)}
    return {
        name: build_system_prompt(userdata, config, rag_tool_available=rag)
        for name, userdata in variants.items()
    }


def test_no_missing_tools_mentioned():
    for name, prompt in _prompts().items():
        assert "search_knowledge_base" not in prompt, name
        # Every session has end_call: a goodbye turns a browser session's mic off.
        assert "end_call" in prompt, name


TELCO_TOOL_NAMES = {
    "get_account_summary",
    "get_usage_breakdown",
    "explain_deductions",
    "search_packages",
    "recommend_packages",
    "purchase_package",
    "start_recharge",
    "lookup_transactions",
    "get_offers_and_points",
    "redeem_reward",
    "create_support_case",
    "get_case_status",
    "check_network_status",
    "find_care_centre",
    "request_human_agent",
    "verify_otp",
    "cancel_pending_action",
}


def test_session_tools_are_end_call_telco_plus_optional_knowledge_base():
    def names(config=None):
        userdata = SessionUserdata(channel=Channel.inbound_chat, room=None)
        return {
            getattr(t, "id", None) or getattr(t, "__name__", "")
            for t in entrypoint._session_tools(userdata, config)
        }

    assert names() == {"end_call"} | TELCO_TOOL_NAMES
    config = agent_config_service.resolve(None)
    config.rag_enabled = True
    assert names(config) == {"end_call", "search_knowledge_base"} | TELCO_TOOL_NAMES


def test_rag_scope_replaces_default_scope():
    config = agent_config_service.resolve(None)
    for prompt in _prompts(rag=True).values():
        assert "search_knowledge_base" in prompt
        assert knowledge_scope_text(config, False) not in prompt
        assert knowledge_scope_text(config, True) in prompt


def test_unknown_details_point_to_the_operator_hotline():
    config = agent_config_service.resolve(None)
    for rag in (False, True):
        for name, prompt in _prompts(rag=rag).items():
            assert config.operator_phone in prompt, (name, rag)
            assert config.operator_address in prompt, (name, rag)
            flat = _flat(prompt)
            assert "never say you don't have the information" in flat, (name, rag)
            assert "আমাদের কাছে নেই" in flat, (name, rag)
            assert "নিশ্চিত করে বলতে পারছি না" in flat, (name, rag)
            assert "hotline" in flat, (name, rag)
            assert "{operator_" not in prompt, (name, rag)
            assert "say you don't have that detail" not in flat, (name, rag)
            # "... কথা বলা নেই" is the same shrug: answer from the facts, then a next step.
            assert "কথা বলা নেই" in flat and "lightest exit" in flat, (name, rag)


def test_knowledge_base_tool_points_to_the_team_not_a_shrug():
    tool = build_search_knowledge_base(agent_config_service.resolve(None))
    description = _description(tool)
    assert "don't have that detail" not in description
    for text in (description, NOTHING_FOUND, UNAVAILABLE):
        assert "hotline" in text


def test_polite_examples_drop_janaben():
    flat = _flat(DEFAULT_IDENTITY_AND_RULES)
    examples = flat.split("use polite forms (")[1].split(")")[0]
    assert "জানাবেন" not in examples
    assert "don't tack \"জানাবেন?\" onto it" in flat


def test_bangla_asks_with_chacchen():
    for name, prompt in _prompts().items():
        assert 'use "চাচ্ছেন", never "চাইবেন"' in prompt, name


def test_prompt_refs_use_english_digits():
    for name, prompt in _prompts().items():
        assert "TC-2048" in prompt and "TXN-840219" in prompt, name


def test_default_agent_name(monkeypatch):
    from app.config import Settings

    monkeypatch.delenv("AGENT_NAME", raising=False)
    assert Settings(_env_file=None).agent_name == "telco_agent"


def test_boundaries_and_currency_rules_present():
    for name, prompt in _prompts().items():
        assert "BOUNDARIES" in prompt, name
        assert "digits, in every language" in prompt, name
        assert "reply in Bangla in Bengali\nscript, never in English letters" in prompt, name
        assert '"taka" (টাকা in Bangla script), never "৳"' in prompt, name


def _description(tool) -> str:
    return " ".join(tool.info.description.split())


def _flat(prompt: str) -> str:
    return " ".join(prompt.split())


# ---- telco copy ----


def _kb_description() -> str:
    return _description(build_search_knowledge_base(agent_config_service.resolve(None)))


def test_prompts_have_no_real_estate_words():
    texts = {
        "identity": DEFAULT_IDENTITY_AND_RULES,
        "greeting_inbound": DEFAULT_GREETING_INBOUND,
        "greeting_nudge": DEFAULT_GREETING_NUDGE,
        "kb_tool": _kb_description(),
        "kb_nothing": NOTHING_FOUND,
        "kb_unavailable": UNAVAILABLE,
        **{f"spoken_{i}": line for i, line in enumerate(SPOKEN_GREETINGS_INBOUND)},
        **{f"guest_{i}": line for i, line in enumerate(SPOKEN_GREETINGS_GUEST)},
        **{f"idle_{k}": v for k, v in {**IDLE_CHECKIN_LINES, **IDLE_GOODBYE_LINES}.items()},
    }
    for rag in (False, True):
        for name, prompt in _prompts(rag=rag).items():
            texts[f"{name}_rag_{rag}"] = prompt
    for name, text in texts.items():
        assert real_estate_words(text) == [], name


def test_prompt_mentions_only_registered_tools():
    for rag in (False, True):
        config = agent_config_service.resolve(None)
        config.rag_enabled = rag
        userdata = SessionUserdata(channel=Channel.inbound_chat, room=None)
        registered = {
            getattr(t, "id", None) or getattr(t, "__name__", "")
            for t in entrypoint._session_tools(userdata, config)
        }
        prompt = build_system_prompt(userdata, config, rag_tool_available=rag)
        # Every snake_case word in the prompt is a tool name.
        mentioned = set(re.findall(r"\b[a-z]+(?:_[a-z]+)+\b", prompt))
        assert mentioned <= registered, (rag, mentioned - registered)
        assert {"request_human_agent", "verify_otp", "end_call"} <= mentioned, rag


def test_prompt_rules_present():
    userdata = SessionUserdata(channel=Channel.inbound_chat, room=None)
    userdata.snapshot_text = "ACCOUNT SNAPSHOT pytest-marker"
    config = agent_config_service.resolve(None)
    prompt = build_system_prompt(userdata, config)
    flat = _flat(prompt)
    assert "never repeat" in flat.lower()
    assert "PIN" in prompt
    assert "request_human_agent" in prompt
    # Escalation is for account actions; information gaps go to the hotline.
    assert "an account action no tool can perform" in flat
    # The card needs the code too: there is no code-free Confirm button.
    assert "enter it on the confirm card" in flat and "tap Confirm" not in flat
    assert "when no tool can do what they need" not in flat
    assert "say so briefly" not in flat
    assert "ACCOUNT SNAPSHOT pytest-marker" in prompt
    # After the identity block, before the task and closing notes.
    assert prompt.index("pytest-marker") > prompt.index("CONFIDENTIALITY")
    assert prompt.index("pytest-marker") < prompt.index("ENDING THE VOICE CHAT")
    # A session without a snapshot is a guest.
    guest = build_system_prompt(SessionUserdata(channel=Channel.inbound_chat, room=None), config)
    assert GUEST_SNAPSHOT in guest


def test_a_text_start_prompt_answers_cold():
    config = agent_config_service.resolve(None)
    typed = SessionUserdata(channel=Channel.inbound_chat, room=None, text_start=True)
    assert "TYPED START" in build_system_prompt(typed, config)
    plain = SessionUserdata(channel=Channel.inbound_chat, room=None)
    assert "TYPED START" not in build_system_prompt(plain, config)
    # A nudge session still opens with the nudge greeting.
    nudged = SessionUserdata(
        channel=Channel.inbound_chat, room=None, text_start=True, nudge_text="low balance"
    )
    assert "TYPED START" not in build_system_prompt(nudged, config)


def test_greeting_defaults_fit_the_operator():
    assert "{nudge_text}" in DEFAULT_GREETING_NUDGE
    assert len(SPOKEN_GREETINGS_INBOUND) == 2
    assert all("{customer_name}" in line for line in SPOKEN_GREETINGS_INBOUND)
    assert len(SPOKEN_GREETINGS_GUEST) == 2
    assert not any("{customer_name}" in line for line in SPOKEN_GREETINGS_GUEST)
    # get_offers_and_points needs a login, so the guest copy never offers it.
    assert not any("অফার" in line for line in SPOKEN_GREETINGS_GUEST)
    can_do = " ".join(GUEST_SNAPSHOT.split()).split("You can still talk about")[1].split(".")[0]
    assert "offer" not in can_do and "district" in can_do


def test_bangla_is_said_not_translated_and_a_broad_package_ask_is_narrowed_first():
    from app.agent.prompt_defaults import DEFAULTS

    flat = _flat(DEFAULTS["prompt_identity_rules"])
    assert "never translate" in flat and "not lines to reuse" in flat
    assert "they'd like to hear more" not in flat
    assert "what kind they're after" in flat and "recommend_packages" in flat


def test_prompt_fixed_english():
    from app.agent.prompt_defaults import CHANNEL_TEXT_NOTE

    config = agent_config_service.resolve(None)
    config = __import__("dataclasses").replace(config, voice_replies_enabled=False)
    userdata = SessionUserdata(channel=Channel.inbound_chat, room=None, reply_language="en")
    prompt = build_system_prompt(userdata, config)
    assert "REPLY LANGUAGE" in prompt and "Reply only in English" in prompt
    assert prompt.endswith(CHANNEL_TEXT_NOTE)
    assert prompt.index("REPLY LANGUAGE") > prompt.index("ENDING THE VOICE CHAT")


def test_prompt_fixed_bangla_says_bengali_script():
    config = agent_config_service.resolve(None)
    userdata = SessionUserdata(channel=Channel.inbound_chat, room=None, reply_language="bn")
    prompt = build_system_prompt(userdata, config)
    assert "Reply only in Bangla (Bengali script)" in prompt
    assert "never in English letters" in prompt.split("REPLY LANGUAGE")[1]
    assert "দুঃখিত, বুঝতে পারিনি।" in prompt


def test_prompt_unset_unchanged():
    config = agent_config_service.resolve(None)
    prompt = build_system_prompt(SessionUserdata(channel=Channel.inbound_chat, room=None), config)
    assert "REPLY LANGUAGE" not in prompt
    assert "in the language of their\nlatest message" in prompt


def test_text_start_and_end_notes_follow_pick():
    config = agent_config_service.resolve(None)
    userdata = SessionUserdata(
        channel=Channel.inbound_chat, room=None, text_start=True, reply_language="en"
    )
    prompt = build_system_prompt(userdata, config)
    typed = prompt.split("TYPED START")[1].split("ENDING THE VOICE CHAT")[0]
    assert "in English" in typed and "language of their message" not in typed
    ending = prompt.split("ENDING THE VOICE CHAT")[1].split("REPLY LANGUAGE")[0]
    assert "in English" in ending and "language of their" not in ending


def test_goodbye_texts_follow_pick():
    assert "In Bangla" in entrypoint.browser_end_goodbye("bn")
    assert "latest message" not in entrypoint.browser_end_goodbye("bn")
    assert "In English" in entrypoint.end_call_goodbye("en")
    assert "In the language of the customer's latest message" in entrypoint.end_call_goodbye(None)
    assert "latest message" in entrypoint.browser_end_goodbye(None)
