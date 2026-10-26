"""How a browser session uses voice. Guests type and read; a logged-in
customer may speak, and hears the reply or reads it by the dashboard's Voice
responses switch (agent_config.voice_replies_enabled). A phone call is always
full voice.

The agent enforces the mode: with session input audio off nothing is
transcribed, even if the browser publishes a mic track, and with output audio
off livekit runs no TTS and the reply goes out as text only (fillers too).
The session is built with STT and TTS either way, so a guest who logs in
mid-chat is switched in place (account_link)."""

from enum import Enum

from livekit import rtc
from livekit.agents import Agent, AgentSession

from app.agent.prompt_defaults import CHANNEL_TEXT_NOTE
from app.agent.userdata import SessionUserdata
from app.services.agent_config_service import ResolvedAgentConfig

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
    """Switches the session's audio to the mode, keeps the CHANNEL note in the
    instructions in step with it, and publishes the mode for the browser."""
    mode = mode_for(userdata, config)
    session.input.set_audio_enabled(mode is not VoiceMode.off)
    session.output.set_audio_enabled(mode is VoiceMode.full)
    has_note = CHANNEL_TEXT_NOTE in agent.instructions
    wants_note = bool(channel_note(mode))
    if wants_note and not has_note:
        await agent.update_instructions(f"{agent.instructions}\n\n{CHANNEL_TEXT_NOTE}")
    elif has_note and not wants_note:
        await agent.update_instructions(
            agent.instructions.replace(f"\n\n{CHANNEL_TEXT_NOTE}", "", 1)
        )
    userdata.voice_mode = mode
    await room.local_participant.set_attributes({VOICE_ATTRIBUTE: mode.value})
    return mode
