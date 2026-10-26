"""How a browser session uses voice. Guests type and read; a logged-in
customer may speak, and hears the reply or reads it by the dashboard's Voice
responses switch (agent_config.voice_replies_enabled). A phone call is always
full voice.

The agent enforces the mode: with session input audio off nothing is
transcribed, even if the browser publishes a mic track, and with output audio
off livekit runs no TTS and the reply goes out as text only (fillers too).
The session is built with STT and TTS either way, so a guest who logs in
mid-chat is switched in place (account_link)."""

import logging
from enum import Enum

from livekit import rtc
from livekit.agents import Agent, AgentSession

from app.agent.prompt_defaults import CHANNEL_TEXT_NOTE
from app.agent.userdata import SessionUserdata
from app.services.agent_config_service import ResolvedAgentConfig

logger = logging.getLogger("agent.voice_mode")

# The agent's participant attribute: the session's VoiceMode value.
# Must match VOICE_ATTRIBUTE in frontend/components/customer/use-voice-mode.ts.
VOICE_ATTRIBUTE = "voice"


class VoiceMode(str, Enum):
    # Text in, text out.
    off = "off"
    # Voice or text in, text out.
    text_reply = "text_reply"
    # Voice or text in, voice (with synced text) out.
    full = "full"


def mode_for(userdata: SessionUserdata, config: ResolvedAgentConfig) -> VoiceMode:
    if userdata.is_phone_call:
        return VoiceMode.full
    if userdata.subscriber_id is None:
        return VoiceMode.off
    return VoiceMode.full if config.voice_replies_enabled else VoiceMode.text_reply


def channel_note(mode: VoiceMode) -> str:
    """The prompt's last block in the text modes; empty for full voice."""
    return "" if mode is VoiceMode.full else CHANNEL_TEXT_NOTE


async def apply(
    session: AgentSession,
    agent: Agent,
    userdata: SessionUserdata,
    config: ResolvedAgentConfig,
    room: rtc.Room,
) -> VoiceMode:
    """Keeps the CHANNEL note in the instructions in step with the mode,
    publishes the mode for the browser, then switches the session's audio.
    The awaited steps go first: if one fails, the audio is left as it was."""
    mode = mode_for(userdata, config)
    has_note = CHANNEL_TEXT_NOTE in agent.instructions
    wants_note = bool(channel_note(mode))
    if wants_note and not has_note:
        await agent.update_instructions(f"{agent.instructions}\n\n{CHANNEL_TEXT_NOTE}")
    elif has_note and not wants_note:
        await agent.update_instructions(
            agent.instructions.replace(f"\n\n{CHANNEL_TEXT_NOTE}", "", 1)
        )
    await room.local_participant.set_attributes({VOICE_ATTRIBUTE: mode.value})
    session.input.set_audio_enabled(mode is not VoiceMode.off)
    session.output.set_audio_enabled(mode is VoiceMode.full)
    userdata.voice_mode = mode
    return mode


async def apply_or_text_only(
    session: AgentSession,
    agent: Agent,
    userdata: SessionUserdata,
    config: ResolvedAgentConfig,
    room: rtc.Room,
) -> VoiceMode:
    """apply(), or on any failure text in and text out, told to the browser if
    it can be, so the UI never offers a mic that transcribes nothing."""
    try:
        return await apply(session, agent, userdata, config, room)
    except Exception:
        logger.exception("could not apply the voice mode; text only")
    session.input.set_audio_enabled(False)
    session.output.set_audio_enabled(False)
    userdata.voice_mode = VoiceMode.off
    try:
        await room.local_participant.set_attributes({VOICE_ATTRIBUTE: VoiceMode.off.value})
    except Exception:
        logger.exception("could not publish the text-only voice mode")
    return VoiceMode.off


def close_input(session: AgentSession) -> None:
    """Before session.start: no audio reaches STT until apply() opens it, even
    from a mic track published before the agent joined."""
    session.input.set_audio_enabled(False)
