import asyncio
import logging
import random
from collections.abc import Callable
from pathlib import Path

import httpx
from livekit import rtc
from livekit.agents import NOT_GIVEN, Agent, AgentSession, JobContext
from livekit.agents import llm as llm_utils
from livekit.agents import stt as stt_utils
from livekit.agents import tts as tts_utils
from livekit.agents import vad as vad_utils
from livekit.agents.beta.tools.end_call import EndCallTool
from livekit.plugins import deepgram, elevenlabs, google, openai, silero

from app.agent import (
    action_rpc,
    browser_end_call,
    elevenlabs_keys,
    gated_agent,
    idle_checkin,
    openrouter_audio,
    prefetch,
    quick_reply,
    run_log,
    sentence_tokenizer,
    session_context,
    usage_log,
)
from app.agent.persona import build_system_prompt
from app.agent.prompt_defaults import (
    SALAM_INSTRUCTION,
    SPOKEN_GREETINGS_INBOUND,
)
from app.agent.speech_numbers import speak_numbers_as_words
from app.agent.speech_words import respell_words_for_speech
from app.agent.tools.search_knowledge_base import build_search_knowledge_base
from app.agent.tools import registry
from app.agent.transcript import TranscriptRecorder
from app.agent.userdata import SessionUserdata
from app.config import Settings, get_settings
from app.services import agent_config_service
from app.services.agent_config_service import ResolvedAgentConfig, render_template

logger = logging.getLogger("agent.entrypoint")

GREETING_DONE_ATTRIBUTE = "greeting_done"

# How long the gate's OpenRouter connections (Jev, the router) stay open idle.
_GATE_KEEPALIVE_S = 300.0


async def _log_if_failed(handle) -> None:
    await handle.wait_for_playout()
    if (exc := handle.exception()) is not None:
        logger.error("greeting generation failed", exc_info=exc)


async def _await_greeting(
    handle,
    session: AgentSession,
    agent: Agent,
    userdata: SessionUserdata,
    room: rtc.Room | None,
    on_done: Callable[[], None] | None = None,
) -> None:
    try:
        await _log_if_failed(handle)
    except Exception:
        logger.exception("greeting playout failed")
    finally:
        # Even after a failed greeting, or the session would never take input.
        await _mark_greeting_done(session, agent, userdata, room)
        if on_done is not None:
            on_done()


async def _mark_greeting_done(
    session: AgentSession,
    agent: Agent,
    userdata: SessionUserdata,
    room: rtc.Room | None,
) -> None:
    """Opens the session to the customer once the greeting has played out.
    Until then typed text is dropped (gated_agent._text_input_cb) and the turn
    gate ignores transcripts; the library already skips voice turns that end
    during uninterruptible speech."""
    try:
        # Speech heard during the greeting must not leak into the next turn.
        session.clear_user_turn()
    except RuntimeError:
        pass  # the session closed during the greeting
    if (on_greeting_done := getattr(agent, "on_greeting_done", None)) is not None:
        on_greeting_done()
    if room is not None:
        try:
            # Enables Send in the browser; sent before input reopens below.
            await room.local_participant.set_attributes({GREETING_DONE_ATTRIBUTE: "1"})
        except Exception:
            logger.exception("could not publish the greeting_done attribute")
    userdata.greeting_done = True


async def _announce_user_turns(room: rtc.Room) -> None:
    """Tells the browser to show only the voice turns the agent publishes on
    USER_TURN_TOPIC (gated or not), not the raw transcription."""
    try:
        await room.local_participant.set_attributes({gated_agent.GATE_ATTRIBUTE: "1"})
    except Exception:
        logger.exception("could not publish the turn_gate attribute")


def _load_agent_config() -> ResolvedAgentConfig:
    """Reads the dashboard-configured agent config fresh on every call, so a
    change in the dashboard takes effect on the next call without restarting
    the agent worker. Falls back to env defaults if the DB can't be read."""
    return agent_config_service.load()


async def _elevenlabs_keys_for_call(settings: Settings, config: ResolvedAgentConfig) -> list[str]:
    """The configured keys, near-empty ones last and unusable ones dropped (see
    elevenlabs_keys.usable_keys). If the check itself fails, all keys in order."""
    if config.stt_tts_provider == "openrouter":
        return []
    keys = settings.elevenlabs_keys
    if config.stt_tts_provider != "elevenlabs":
        return keys
    try:
        return await elevenlabs_keys.usable_keys(
            keys, config.elevenlabs_voice_id, settings.elevenlabs_min_remaining_credits
        )
    except Exception:
        logger.exception("elevenlabs key check failed, using all keys in order")
        return keys


def _labelled(instance, label: str):
    # FallbackAdapter's own "failed, switching to next" logs print .label; without
    # this every ElevenLabs instance would print the same class name.
    instance._label = label
    return instance


def _log_availability(kind: str):
    def _on_change(ev) -> None:
        instance = getattr(ev, kind)
        state = "back" if ev.available else "down"
        logger.warning("%s %s is %s", kind.upper(), instance.label, state)

    return _on_change


def _deepgram_fallback(
    settings: Settings, config: ResolvedAgentConfig
) -> tuple[stt_utils.STT, tts_utils.TTS]:
    """The last-resort Deepgram pair appended after ElevenLabs. "multi" keeps
    nova-3 transcribing non-English callers; the Aura voice is English-only."""
    stt = deepgram.STT(
        api_key=settings.deepgram_key,
        model=settings.deepgram_stt_model,
        language="multi",
    )
    # Wrapped like the ElevenLabs ones: FallbackAdapter only reports
    # aligned_transcript if every instance does, and raw deepgram.TTS doesn't.
    tts = _sentence_tts(
        deepgram.TTS(api_key=settings.deepgram_key, model=config.deepgram_tts_model)
    )
    return _labelled(stt, "deepgram"), _labelled(tts, "deepgram")


def _sentence_tts(tts: tts_utils.TTS) -> tts_utils.StreamAdapter:
    """Synthesizes sentence by sentence, splitting Bangla at । too (see
    app.agent.sentence_tokenizer), so speech starts after the first sentence."""
    return tts_utils.StreamAdapter(
        tts=tts, sentence_tokenizer=sentence_tokenizer.SentenceTokenizer()
    )


def _build_openrouter_stt_and_tts(
    settings: Settings, config: ResolvedAgentConfig, vad: vad_utils.VAD | None
) -> tuple[stt_utils.STT, tts_utils.TTS]:
    """ElevenLabs models through OpenRouter (voice provider "openrouter")."""
    # Not only for embeddings: this is the agent's OpenRouter key -- the
    # dashboard-saved one when the LLM runs on OpenRouter, else OPENROUTER_API_KEY.
    key = agent_config_service.embedding_api_key(config, settings)
    if not key:
        raise RuntimeError(
            "ELEVENLABS_PROVIDER is openrouter but no OpenRouter API key is configured"
        )
    if not config.elevenlabs_voice_id:
        raise RuntimeError("no ElevenLabs voice configured")
    if settings.deepgram_key and vad is None:
        raise RuntimeError("the OpenRouter STT needs a VAD to fall back to Deepgram")

    stt = openrouter_audio.make_openrouter_stt(settings, key)
    tts = _sentence_tts(
        openrouter_audio.OpenRouterTTS(
            api_key=key,
            base_url=settings.openrouter_base_url,
            model=config.elevenlabs_tts_model or settings.elevenlabs_openrouter_tts_model,
            voice=config.elevenlabs_voice_id,
        )
    )
    if not settings.deepgram_key:
        # AgentSession drives the non-streaming STT with its own VAD.
        return stt, tts

    label = "openrouter elevenlabs"
    deepgram_stt, deepgram_tts = _deepgram_fallback(settings, config)
    # Wrapped here rather than by FallbackAdapter(vad=...), which would drop the label.
    stt_chain = stt_utils.FallbackAdapter(
        [_labelled(stt_utils.StreamAdapter(stt=stt, vad=vad), label), deepgram_stt],
        attempt_timeout=5,
        max_retry_per_stt=1,
    )
    tts_chain = tts_utils.FallbackAdapter(
        [_labelled(tts, label), deepgram_tts], max_retry_per_tts=1, sample_rate=tts.sample_rate
    )
    stt_chain.on("stt_availability_changed", _log_availability("stt"))
    tts_chain.on("tts_availability_changed", _log_availability("tts"))
    return stt_chain, tts_chain


def _build_stt_and_tts(
    settings: Settings,
    config: ResolvedAgentConfig,
    el_keys: list[str] | None = None,
    vad: vad_utils.VAD | None = None,
) -> tuple[stt_utils.STT, tts_utils.TTS]:
    if config.stt_tts_provider == "deepgram":
        return (
            deepgram.STT(
                api_key=settings.deepgram_api_key,
                model=settings.deepgram_stt_model,
            ),
            deepgram.TTS(
                api_key=settings.deepgram_api_key,
                model=config.deepgram_tts_model,
            ),
        )

    if config.stt_tts_provider == "openrouter":
        return _build_openrouter_stt_and_tts(settings, config, vad)

    if el_keys is None:
        el_keys = settings.elevenlabs_keys
    stts: list[stt_utils.STT] = []
    ttss: list[tts_utils.TTS] = []
    for key in el_keys:
        label = f"elevenlabs {elevenlabs_keys.key_tail(key)}"
        stt = elevenlabs_keys.FailFastElevenLabsSTT(
            api_key=key,
            model=settings.elevenlabs_stt_model,
            # no language_code set -> ElevenLabs Scribe auto-detects the spoken
            # language across turns; DEFAULT_LANGUAGE is used as the persona's
            # fallback tone/wording, not as an STT constraint.
            # Without server_vad the plugin uses manual commits, and nothing in the
            # session sends one: turns then hang on partial transcripts until
            # ElevenLabs commits on its own (minutes, or never).
            server_vad={"vad_silence_threshold_secs": settings.elevenlabs_stt_silence_secs},
        )
        if not stt.capabilities.streaming:
            # FallbackAdapter would need a VAD to drive a non-streaming STT.
            raise RuntimeError(
                f"ELEVENLABS_STT_MODEL={settings.elevenlabs_stt_model} is not a realtime model"
            )
        stts.append(_labelled(stt, label))
        # StreamAdapter wraps the ElevenLabs TTS to synthesize sentence-by-sentence over its
        # REST endpoint instead of via AgentSession's default websocket streaming call pattern.
        # The websocket path was observed (via an asyncio task-stack dump while it hung) to
        # stall forever in the plugin's _recv_loop waiting on a response that never arrived,
        # even though the same plugin's REST synthesize() and a simple push_text/end_input()
        # websocket stream both worked fine in isolation outside of AgentSession.
        raw_tts = elevenlabs.TTS(
            api_key=key,
            voice_id=config.elevenlabs_voice_id,
            model=config.elevenlabs_tts_model or settings.elevenlabs_tts_model,
        )
        ttss.append(_labelled(_sentence_tts(raw_tts), label))

    if settings.deepgram_key:
        # Last resort once every ElevenLabs key is spent.
        deepgram_stt, deepgram_tts = _deepgram_fallback(settings, config)
        stts.append(deepgram_stt)
        ttss.append(deepgram_tts)

    if not stts:
        raise RuntimeError(
            "no STT/TTS provider available: no usable ELEVENLABS_API_KEYS and no DEEPGRAM_API_KEY"
        )
    if len(stts) == 1:
        return stts[0], ttss[0]

    # Retry once so a network blip doesn't write off a good key; quota/auth
    # errors are 4xx, never retried, so those switch immediately.
    stt_chain = stt_utils.FallbackAdapter(stts, attempt_timeout=5, max_retry_per_stt=1)
    # Output at the first key's rate, so only the Deepgram fallback gets resampled.
    tts_chain = tts_utils.FallbackAdapter(
        ttss, max_retry_per_tts=1, sample_rate=ttss[0].sample_rate
    )
    stt_chain.on("stt_availability_changed", _log_availability("stt"))
    tts_chain.on("tts_availability_changed", _log_availability("tts"))
    return stt_chain, tts_chain


def _build_llm(settings: Settings, config: ResolvedAgentConfig) -> llm_utils.LLM:
    temperature = config.temperature if config.temperature is not None else NOT_GIVEN
    max_tokens = config.max_output_tokens if config.max_output_tokens else NOT_GIVEN
    if config.llm_provider == "openrouter":
        if not config.api_key:
            raise RuntimeError(
                "LLM provider is openrouter but no API key is saved and OPENROUTER_API_KEY is not set"
            )
        # openai.LLM directly rather than with_openrouter, which has no max-tokens parameter.
        return openai.LLM(
            model=config.llm_model,
            api_key=config.api_key,
            base_url=settings.openrouter_base_url,
            temperature=temperature,
            max_completion_tokens=max_tokens,
            # OpenRouter's unified field, not OpenAI's top-level reasoning_effort,
            # so it reaches whichever provider OpenRouter routes the model to.
            extra_body={"reasoning": {"effort": config.reasoning_effort}},
        )

    # Gemini 3 models (incl. gemini-3.1-flash-lite) only accept thinking_level,
    # not the thinking_budget used by Gemini 2.5 and earlier -- passing
    # thinking_budget here is silently ignored with a warning on every LLM call.
    # "low" keeps latency down for a voice agent that has no use for deep
    # reasoning, while still keeping the thought_signature bookkeeping
    # (livekit/agents#4767) intact for function-call turns like search_apartments.
    return google.LLM(
        api_key=config.api_key,
        model=config.llm_model,
        thinking_config={"thinking_level": "low"},
        temperature=temperature,
        max_output_tokens=max_tokens,
    )


_END_CALL_DESCRIPTION = (
    "Call it on its own, with no goodbye first (its result asks you for one): once they've "
    "booked, asked to be called later, said they're not interested, or want to end the call."
)

_BROWSER_END_CALL_DESCRIPTION = (
    "Call it once the customer says goodbye (bye, আল্লাহ হাফেজ, আসি তাহলে), or says no when "
    "you ask whether they need anything else -- in your goodbye reply, after the goodbye. When "
    "they only thank you or say that's all, ask whether they need anything else first, and don't "
    "call it. Not when a thanks comes with a question or they clearly want to go on."
)

# end_call's result when no goodbye came before it: the goodbye is the reply to
# it, and the call ends once that has played. Kept fitting the conversation, not
# a fixed line.
_END_CALL_GOODBYE = (
    "The call ends after your next words. In the language of the customer's latest message, "
    "say goodbye in one or two short sentences that fit what happened: thank them and invite "
    "them back anytime. If you already said goodbye just now, say nothing more."
)


def _idle_checkin(
    ctx: JobContext, settings: Settings, session: AgentSession
) -> idle_checkin.IdleCheckIn | None:
    """Browser sessions only; None when settings turn it off."""
    if settings.idle_checkin_s <= 0:
        return None

    async def _end_call() -> None:
        # Deleting the room disconnects the browser, which then shows the call ended.
        await ctx.delete_room()
        ctx.shutdown(reason="customer idle")

    watcher = idle_checkin.IdleCheckIn(
        session=session,
        on_end=_end_call,
        idle_s=settings.idle_checkin_s,
        grace_s=settings.idle_end_s,
    )
    watcher.attach()
    return watcher


def _router_enabled(settings: Settings, config: ResolvedAgentConfig) -> bool:
    """The turn router runs lookups before the LLM and hands it their results as
    if it had called the tools. OpenRouter LLMs only: Gemini 3 rejects a tool
    call it didn't make (no thought_signature)."""
    return settings.router_enabled and config.llm_provider == "openrouter"


def _rag_enabled(config: ResolvedAgentConfig | None) -> bool:
    return config is not None and config.rag_enabled


def _session_tools(userdata: SessionUserdata, config: ResolvedAgentConfig | None = None) -> list:
    """Tools for this session. end_call is always there: on a phone call the agent has to hang
    up itself (EndCallTool deletes the room), and a browser call ends after the
    goodbye, by the browser (BrowserEndCall). Both keep per-session state, so
    they're built fresh each time.

    search_knowledge_base is added only when `config` has the knowledge base
    enabled (see _rag_enabled), bound to that config's top-k/threshold/scope."""
    tools: list = list(registry.telco_tools())
    if _rag_enabled(config):
        tools.append(build_search_knowledge_base(config))
    if userdata.is_phone_call:
        # The model calls end_call with no text and says the goodbye from its
        # result (end_instructions), the way the library's own description wants.
        tools.append(
            EndCallTool(
                delete_room=True,
                end_instructions=_END_CALL_GOODBYE,
                extra_description=_END_CALL_DESCRIPTION,
            )
        )
    else:
        # Goodbye first, end_call after it in the same reply; the browser then
        # ends the call itself (see browser_end_call).
        tools.append(
            browser_end_call.BrowserEndCall(
                goodbye_instructions=_END_CALL_GOODBYE,
                extra_description=_BROWSER_END_CALL_DESCRIPTION,
            ).tool
        )
    return tools


def _linked_identity(session: AgentSession, caller_identity: str) -> Callable[[], str | None]:
    """The identity of the browser participant the session talks to."""

    def _identity() -> str | None:
        # RoomIO links the participant from a background task, so right after
        # session.start it may not be set yet; it then links the first caller,
        # the one entrypoint waited for.
        participant = session.room_io.linked_participant
        return participant.identity if participant is not None else caller_identity

    return _identity


def _turn_handling(gated: bool, endpoint_min_delay: float | None = None) -> dict:
    """Gated sessions turn the library's interruption off: the turn gate decides
    who may cut the agent off, and STT keeps hearing the user while it talks so
    the gate can. A turn that ends while the agent talks is then dropped by the
    library unless the gate interrupted first. Preemptive generation is off too,
    so the LLM never runs on a turn the gate goes on to drop.

    endpoint_min_delay (batch STT only, see _endpoint_min_delay) is how long
    after the caller goes quiet the turn may close."""
    handling: dict = {"turn_detection": "vad"}
    if endpoint_min_delay is not None:
        handling["endpointing"] = {
            "min_delay": endpoint_min_delay,
            "max_delay": max(3.0, endpoint_min_delay + 0.5),
        }
    if gated:
        handling["interruption"] = {"enabled": False, "discard_audio_if_uninterruptible": False}
        handling["preemptive_generation"] = {"enabled": False}
    return handling


def _endpoint_min_delay(settings: Settings, config: ResolvedAgentConfig) -> float | None:
    """With batch STT (voice provider "openrouter") a caller who pauses mid-sentence
    loses half the sentence: when the second part stops, the library closes the
    turn on the first part's text after min_delay (0.5 s), before the second
    part's transcript is back (1.66 s later in run_2). A longer min_delay covers
    that; a single-part turn waits for its transcript (2+ s) anyway, so it costs
    nothing there. Streaming STT finalizes fast and keeps the library default."""
    if config.stt_tts_provider != "openrouter":
        return None
    return settings.batch_stt_endpoint_min_delay_s


def _gate_api_key(settings: Settings, config: ResolvedAgentConfig) -> str:
    """The OpenRouter key the turn judge uses, or "" when the gate is off or has
    no key (then the session runs ungated)."""
    if not settings.turn_gate_enabled:
        return ""
    key = agent_config_service.embedding_api_key(config, settings)
    if not key:
        logger.warning("TURN_GATE_ENABLED is set but no OpenRouter key is configured; ungated")
    return key


def _open_run_log(settings: Settings, label: str) -> run_log.RunLog | None:
    """A new logs/run_<N>.log for this session, or None when RUN_LOG_ENABLED is
    off or the file can't be created (the call goes on without it)."""
    if not settings.run_log_enabled:
        return None
    try:
        return run_log.RunLog.open(label, Path(settings.run_log_dir) if settings.run_log_dir else None)
    except OSError:
        logger.exception("could not create the timing log")
        return None


def _build_session(
    settings: Settings,
    userdata: SessionUserdata,
    config: ResolvedAgentConfig,
    el_keys: list[str] | None = None,
    *,
    gate_key: str = "",
    room: rtc.Room | None = None,
    timing: run_log.RunLog | None = None,
) -> tuple[AgentSession, Agent]:
    """A non-empty gate_key builds a gated browser session (see gated_agent);
    the phone path never passes one, nor a room. An ungated browser session
    (room given) still publishes the voice turns it answers, like the gate.
    `timing` gets the session's per-turn timings (see run_log)."""
    gated = bool(gate_key)
    vad = silero.VAD.load()
    stt, tts = _build_stt_and_tts(settings, config, el_keys, vad)
    session = AgentSession(
        userdata=userdata,
        stt=stt,
        llm=_build_llm(settings, config),
        tts=tts,
        vad=vad,
        turn_handling=_turn_handling(gated, _endpoint_min_delay(settings, config)),
        # The first two are the library defaults; speak_numbers_as_words makes TTS say
        # "200" as "two hundred" instead of digit-by-digit, and respell_words_for_speech
        # fixes Bangla words the voice mispronounces (transcript keeps the text as written).
        tts_text_transforms=[
            "filter_markdown",
            "filter_emoji",
            speak_numbers_as_words,
            respell_words_for_speech,
        ],
    )
    usage_log.UsageLogger(room.name if room is not None else "").attach(session)
    if timing is not None:
        timing.attach(session)
    # The prompt mentions search_knowledge_base only when _session_tools
    # registers it -- both follow _rag_enabled.
    agent_kwargs = {
        "instructions": build_system_prompt(
            userdata, config, rag_tool_available=_rag_enabled(config)
        ),
        "tools": _session_tools(userdata, config),
    }
    if not gated:
        if room is not None and settings.turn_pause_enabled:
            # The pause lives in the gate; ungated, the library's own interruption
            # (any 0.5 s of voice, no loudness check) handles talking over the agent.
            logger.warning(
                "TURN_PAUSE_ENABLED is set but this browser session is ungated "
                "(TURN_GATE_ENABLED off or no OpenRouter key); the pause is off"
            )
        # A phone call has no room: nothing is published, tags are still dropped.
        return session, gated_agent.TurnPublishingAgent(room=room, **agent_kwargs)

    # httpx drops an idle connection after 5 s by default, and turns are further
    # apart than that: every turn's Jev and router calls paid for a new TLS
    # connection to OpenRouter. Kept open for the call instead.
    client = httpx.AsyncClient(limits=httpx.Limits(keepalive_expiry=_GATE_KEEPALIVE_S))
    session.on("close", lambda _ev: asyncio.ensure_future(client.aclose()))
    prefetcher = None
    if _router_enabled(settings, config):
        prefetcher = prefetch.Prefetcher(
            session=session,
            settings=settings,
            config=config,
            api_key=gate_key,
            client=client,
            on_routed=timing.routed if timing is not None else None,
        )
    quick = None
    if quick_reply.quick_on(config):
        # The small model goes through OpenRouter with the gate's key, whatever
        # the main LLM's provider.
        quick = quick_reply.QuickReplyRuntime(
            config=config,
            settings=settings,
            api_key=gate_key,
            client=client,
            on_event=timing.quick if timing is not None else None,
        )
    # The shortlist cards wait for the main model's first words, so they don't
    # appear while a filler line plays.
    userdata.defer_cards = quick is not None
    gate = gated_agent.TurnGateController(
        session=session,
        room=room,
        config=gated_agent.gate_config(settings, config.stt_tts_provider),
        judge=gated_agent.jev_judge(
            session,
            settings,
            gate_key,
            client,
            timing.judged if timing is not None else None,
            # Quick replies route on Jev's lookup answer, so they ask for it too.
            router=_router_enabled(settings, config) or quick is not None,
            knowledge_base=_rag_enabled(config),
        ),
        on_gate_reply=timing.gate_reply if timing is not None else None,
        prefetcher=prefetcher,
        quick=quick,
        on_filler=timing.filler if timing is not None else None,
        on_fast=timing.fast_route if timing is not None else None,
        on_barge_in=timing.barge_in if timing is not None else None,
    )
    gate.attach()
    return session, gated_agent.GatedAgent(gate=gate, **agent_kwargs)


def _greet(
    session: AgentSession,
    agent: Agent,
    userdata: SessionUserdata,
    config: ResolvedAgentConfig,
    room: rtc.Room | None = None,
    on_done: Callable[[], None] | None = None,
) -> None:
    """Speaks the first message. Nothing interrupts it -- not voice (someone
    picking up a phone says "Hello?" right away, and without this the agent
    re-introduces itself), not the turn gate, not typed text -- and the session
    takes no input until it has played out (_mark_greeting_done). `room` is the
    browser room to flag the end of the greeting on; None for a phone call.
    `on_done` runs once input has reopened."""
    values = {
        "agent_name": config.assistant_name,
        "operator_name": config.operator_name,
        "customer_name": "",
    }
    field, template, lines = (
        "greeting_inbound",
        config.greeting_inbound,
        SPOKEN_GREETINGS_INBOUND,
    )
    if template is None:
        # Still the default: speak a canned line, no LLM round trip.
        handle = session.say(random.choice(lines).format(**values), allow_interruptions=False)
    else:
        # A dashboard greeting still opens with the Salam.
        instructions = f"{render_template(field, template, values)}\n{SALAM_INSTRUCTION}"
        handle = session.generate_reply(instructions=instructions, allow_interruptions=False)
    # generate_reply()'s SpeechHandle silently swallows failures unless awaited and
    # checked (per its own docstring) -- log any greeting failure instead of losing it.
    asyncio.ensure_future(_await_greeting(handle, session, agent, userdata, room, on_done))


async def entrypoint(ctx: JobContext) -> None:
    await ctx.connect()
    settings = get_settings()

    # The caller is already connected by the time this job starts, so this
    # resolves immediately; waiting guarantees a listener is in the room before
    # the greeting's text-stream chunks go out.
    caller = await ctx.wait_for_participant()

    userdata = session_context.resolve(ctx.job.metadata, ctx.room)
    config = _load_agent_config()
    el_keys = await _elevenlabs_keys_for_call(settings, config)
    gate_key = _gate_api_key(settings, config)
    timing = _open_run_log(settings, ctx.room.name)
    try:
        session, agent = _build_session(
            settings, userdata, config, el_keys, gate_key=gate_key, room=ctx.room, timing=timing
        )
    except RuntimeError as e:
        if timing is not None:
            timing.close()
        logger.error("session can't start: %s", e)
        ctx.shutdown(reason=str(e))
        return

    recorder: TranscriptRecorder | None = None

    async def _on_shutdown() -> None:
        if recorder is not None:
            await recorder.close()

    ctx.add_shutdown_callback(_on_shutdown)
    # Both paths use the gate's text callback: it drops text sent before the
    # greeting has played out.
    await session.start(agent=agent, room=ctx.room, room_options=gated_agent.room_options())
    action_rpc.ActionRpc(
        session=session,
        userdata=userdata,
        room=ctx.room,
        linked_identity=_linked_identity(session, caller.identity),
    ).register()
    await _announce_user_turns(ctx.room)
    if isinstance(agent, gated_agent.GatedAgent) and agent.prefetcher:
        agent.prefetcher.warm()
    recorder = await TranscriptRecorder.start(session, userdata, ctx.room.name)
    if recorder is not None and isinstance(agent, gated_agent.GatedAgent) and agent.prefetcher:
        # Prefetched lookups never fire function_tools_executed, which is how the
        # recorder stores the LLM's own tool calls.
        agent.prefetcher.on_prefetch = recorder.record_tool_after
    if recorder is not None and isinstance(agent, gated_agent.GatedAgent):
        # A filler is said outside the chat context, so the recorder never sees it.
        agent.gate.on_filler_store = recorder.record_assistant_after
    idle = _idle_checkin(ctx, settings, session)
    _greet(session, agent, userdata, config, room=ctx.room, on_done=idle.start if idle else None)
