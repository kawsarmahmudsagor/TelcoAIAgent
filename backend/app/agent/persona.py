from datetime import datetime

from app.agent import reply_language, voice_mode
from app.agent.prompt_defaults import KNOWLEDGE_SCOPE_DEFAULT, KNOWLEDGE_SCOPE_RAG
from app.agent.snapshot import GUEST_SNAPSHOT
from app.agent.tools._datetime import agency_tz
from app.agent.userdata import SessionUserdata
from app.services import agent_config_service
from app.services.agent_config_service import ResolvedAgentConfig, render_template

# A session opened by a typed message has no greeting (entrypoint._greet), so
# the first reply mustn't make up for it.
_TEXT_START_NOTE = """TYPED START: the customer opened this chat by typing a message, and you haven't greeted them.
Answer that message directly: don't greet, don't say Salam and don't introduce yourself. Reply {language}.
"""

_INBOUND_TASK = (
    "Help the customer with their mobile service using your tools and the ACCOUNT SNAPSHOT.\n"
)

# Browser sessions: a wrap-up gets "anything else?" first; a goodbye, or a no to
# that, gets the goodbye and end_call in the same reply. end_call waits for the
# goodbye to play, then the browser turns the mic off and the chat stays open
# (browser_end_call). Should the model call end_call alone, its result asks for
# the goodbye (run_48 did only one).
_BROWSER_END_NOTE = """ENDING THE VOICE CHAT: when the customer seems to be wrapping up (thanks for the help, that's all for
now, no more help needed, ঠিক আছে ধন্যবাদ, আর কিছু লাগবে না), don't end yet: ask
whether they need anything else. When they then say no, or when they say goodbye outright (bye,
আল্লাহ হাফেজ, আসি তাহলে, রাখি তাহলে), say goodbye in one or two short sentences that fit what
happened (thank them and say you're here if they need anything else), {language}, and call end_call in that same reply, after the goodbye. Their mic turns off once
the goodbye has played; the chat stays open, so never say the call or chat is over. If a thanks
comes with a question, or they clearly want to go on, just carry on and don't call end_call.
"""


def knowledge_scope_text(config: ResolvedAgentConfig, rag_tool_available: bool) -> str:
    template = KNOWLEDGE_SCOPE_RAG if rag_tool_available else KNOWLEDGE_SCOPE_DEFAULT
    return template.format(
        operator_name=config.operator_name,
        operator_phone=config.operator_phone,
        operator_address=config.operator_address,
    )


def build_system_prompt(
    userdata: SessionUserdata,
    config: ResolvedAgentConfig | None = None,
    *,
    rag_tool_available: bool = False,
) -> str:
    """`config` None loads the saved agent config (env/code defaults if the DB
    can't be read). `rag_tool_available` must only be True when the
    search_knowledge_base tool is actually registered for the session."""
    if config is None:
        config = agent_config_service.load()
    tz = agency_tz()
    current_date = datetime.now(tz).strftime(f"%A, %Y-%m-%d %H:%M ({tz.key})")
    knowledge_scope = knowledge_scope_text(config, rag_tool_available)
    identity = render_template(
        "prompt_identity_rules",
        config.prompt_identity_rules,
        {
            "agent_name": config.assistant_name,
            "operator_name": config.operator_name,
            "current_date": current_date,
            "timezone": tz.key,
            "knowledge_scope": knowledge_scope,
        },
    )
    if knowledge_scope not in identity:
        # A custom prompt without {knowledge_scope} still gets the scope rules.
        identity = f"{identity.rstrip()}\n\n{knowledge_scope}\n"

    # The session's account snapshot (app.agent.snapshot), never editable.
    snapshot = userdata.snapshot_text or GUEST_SNAPSHOT
    task = _INBOUND_TASK
    lang = reply_language.fixed(userdata)
    if userdata.text_start and not userdata.nudge_text:
        typed = reply_language.in_language(lang, "in the language of their message")
        task = f"{task}\n{_TEXT_START_NOTE.format(language=typed)}"
    end_note = _BROWSER_END_NOTE.format(
        language=reply_language.in_language(lang, "in the language of their\nlatest message")
    )
    prompt = f"{identity}\n{snapshot}\n\n{task}\n{end_note}"
    # After every editable part, so it outranks their LANGUAGE rules.
    if lang:
        prompt = f"{prompt}\n{reply_language.prompt_block(lang)}"
    # Last, so the snapshot block above stays replaceable in place.
    if note := voice_mode.channel_note(voice_mode.mode_for(userdata, config)):
        prompt = f"{prompt}\n\n{note}"
    return prompt
