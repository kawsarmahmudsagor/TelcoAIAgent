import inspect

from app.agent import entrypoint
from app.agent.persona import build_system_prompt, knowledge_scope_text
from app.agent.prompt_defaults import DEFAULT_IDENTITY_AND_RULES
from app.agent.tools.search_knowledge_base import (
    NOTHING_FOUND,
    UNAVAILABLE,
    build_search_knowledge_base,
)
from app.agent.userdata import Channel, SessionUserdata
from app.services import agent_config_service


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
        # Every session has end_call: a browser call ends on a goodbye.
        assert "end_call" in prompt, name


def test_session_tools_are_end_call_plus_optional_knowledge_base():
    def names(config=None):
        userdata = SessionUserdata(channel=Channel.inbound_chat, room=None)
        return {
            getattr(t, "id", None) or getattr(t, "__name__", "")
            for t in entrypoint._session_tools(userdata, config)
        }

    assert names() == {"end_call"}
    config = agent_config_service.resolve(None)
    config.rag_enabled = True
    assert names(config) == {"end_call", "search_knowledge_base"}


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
            assert config.operator_phone in prompt, (name, rag)
            assert config.operator_address in prompt, (name, rag)
            flat = _flat(prompt)
            assert "never say you don't have the information" in flat, (name, rag)
            assert "আমাদের কাছে নেই" in flat, (name, rag)
            assert "নিশ্চিত করে বলতে পারছি না" in flat, (name, rag)
            assert "fixed or negotiable" in flat, (name, rag)
            # Citing the listing is allowed; only commercial questions reach the head office.
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
