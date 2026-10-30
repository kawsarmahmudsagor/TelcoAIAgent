from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# .env lives at the repo root (one level above backend/), shared by the API,
# agent worker, and scheduler processes regardless of which directory they're launched from.
_BACKEND_ROOT = Path(__file__).resolve().parent.parent
_REPO_ROOT_ENV = _BACKEND_ROOT.parent / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(".env", _REPO_ROOT_ENV), extra="ignore")

    # Postgres
    database_url: str = "postgresql+psycopg://telco:telco@localhost:5435/telco"

    # LiveKit
    livekit_url: str = "ws://127.0.0.1:7880"
    livekit_api_key: str = "devkey"
    livekit_api_secret: str = "secret"
    agent_name: str = "telco_agent"

    # STT/TTS provider -- selects which service app.agent.entrypoint wires up for
    # speech-to-text and text-to-speech. Swap by changing this one setting; both
    # providers' credentials/models below stay configured side by side.
    stt_tts_provider: Literal["elevenlabs", "deepgram"] = "elevenlabs"

    # Where the ElevenLabs models come from when stt_tts_provider is "elevenlabs".
    # "free": the ElevenLabs API directly, with the keys below. "openrouter": the same
    # models through OpenRouter, billed to the OpenRouter key (see
    # app.agent.openrouter_audio) -- its transcription is per-turn, not realtime.
    # Only the default: a voice provider picked in the dashboard (where OpenRouter is
    # its own option) wins. See agent_config_service.default_stt_tts_provider.
    elevenlabs_provider: Literal["free", "openrouter"] = "free"
    elevenlabs_openrouter_tts_model: str = "elevenlabs/eleven-v4-turbo"
    elevenlabs_openrouter_stt_model: str = "elevenlabs/scribe-v2"

    # ElevenLabs. elevenlabs_api_keys is a comma-separated list tried in order: when
    # one key runs out of credits mid-call the agent switches to the next, and
    # Deepgram (if its key is set) is the last resort. elevenlabs_api_key is the
    # legacy single key, appended after the list.
    elevenlabs_api_keys: str = ""
    elevenlabs_api_key: str = ""
    # A key with fewer credits left than this is tried only after the others --
    # a turn that runs out partway through loses the rest of that turn's audio.
    elevenlabs_min_remaining_credits: int = 1000
    elevenlabs_tts_voice_id: str = ""
    # eleven_v4_turbo or eleven_v3: both speak Bengali; v4 Turbo is the faster one.
    elevenlabs_tts_model: str = "eleven_v4_turbo"
    # scribe_v2 transcribes each turn whole once the caller stops: it detects Bangla
    # reliably. scribe_v2_realtime streams and replies sooner, but guesses the
    # language from the first moments of speech (Bangla written as Turkish).
    elevenlabs_stt_model: str = "scribe_v2"
    # scribe_v2_realtime only: seconds of silence after which ElevenLabs commits
    # (finalizes) a transcript. Lower replies faster; too low answers callers who
    # pause mid-sentence.
    elevenlabs_stt_silence_secs: float = Field(0.8, ge=0.3, le=3.0)
    # Batch STT only (OpenRouter's, or ElevenLabs' scribe_v2): seconds after the caller
    # goes quiet before the turn may close, so a mid-sentence pause doesn't split
    # the turn. See entrypoint._endpoint_min_delay.
    batch_stt_endpoint_min_delay_s: float = Field(2.0, ge=0.3, le=3.0)
    # Silero VAD sensitivity: higher activation_threshold requires clearer vocal energy
    # (default 0.50; 0.76 rejects background room noise/whispers).
    # min_speech_duration: minimum duration of continuous speech required before triggering
    # (default 0.05s / 50ms; 0.25s ignores coughs, keyboard taps, paper rustling).
    vad_activation_threshold: float = Field(0.76, ge=0.1, le=1.0)
    vad_min_speech_duration: float = Field(0.25, ge=0.02, le=2.0)
    default_language: str = "bn"

    # Deepgram
    deepgram_api_key: str = ""
    deepgram_stt_model: str = "nova-3"
    deepgram_tts_model: str = "aura-2-thalia-en"

    # LLM provider -- selects which LLM app.agent.entrypoint wires up. Both
    # providers' credentials/models below stay configured side by side.
    llm_provider: Literal["gemini", "openrouter"] = "openrouter"

    # Gemini
    google_api_key: str = ""
    gemini_model: str = "gemini-3.1-flash-lite"

    # OpenRouter (OpenAI-compatible API)
    openrouter_api_key: str = ""
    openrouter_model: str = "openai/gpt-6-luna"
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    # Reasoning effort sent to OpenRouter models (its unified `reasoning.effort`).
    # A voice agent has no use for long hidden reasoning: every reasoning token
    # delays the first spoken word. The dashboard can override it per agent.
    llm_reasoning_effort: Literal["none", "minimal", "low", "medium", "high"] = "minimal"

    # Voice turn gate for browser calls (app.agent.gated_agent): drops speech that
    # isn't the customer talking to the agent and gates barge-in. The judge is Jev
    # via OpenRouter; thresholds are on its P(addressed).
    turn_gate_enabled: bool = False
    turn_judge_model: str = "typesafe/jev-1.13"
    turn_judge_timeout_ms: int = Field(1500, ge=100, le=5000)
    # 0.3: people nearby scored 0.25-0.30 (run_53, "Hi, Deep" 0.28 got through
    # at 0.25); the customer's lowest real turn so far is "Yeah" at 0.49.
    # Lowered from 0.35 so quieter real turns aren't dropped.
    turn_drop_p: float = Field(0.3, ge=0.0, le=1.0)
    turn_interrupt_p: float = Field(0.4, ge=0.0, le=1.0)
    # Speech that paused the agent needs this to interrupt it instead of
    # turn_interrupt_p. Real questions over the agent scored 0.43-0.50 (run_47),
    # people nearby 0.25-0.30 (run_53).
    turn_pause_interrupt_p: float = Field(0.35, ge=0.0, le=1.0)
    turn_interrupt_min_words: int = Field(2, ge=1, le=10)
    # Speech over the agent pauses it at once when it is near the customer's own
    # level (learned from their accepted turns) for turn_pause_min_speech_s; the
    # judge then interrupts it or it resumes. Before the first turn sets that level,
    # turn_pause_fallback_dbfs is the bar. A pause with no decision ends after
    # turn_pause_resume_after_s of quiet, or turn_pause_max_s in all. See
    # app.agent.voice_level.
    turn_pause_enabled: bool = True
    turn_pause_min_speech_s: float = Field(0.3, ge=0.05, le=2.0)
    turn_pause_margin_db: float = Field(8.0, ge=0.0, le=30.0)
    turn_pause_fallback_dbfs: float = Field(-35.0, ge=-80.0, le=0.0)
    turn_pause_resume_after_s: float = Field(3.0, ge=0.5, le=10.0)
    turn_pause_max_s: float = Field(8.0, ge=1.0, le=30.0)
    turn_min_confidence: float = Field(0.4, ge=0.0, le=1.0)
    turn_other_language_cooldown_s: float = Field(180.0, ge=0.0)
    # Voice isolation (the customer sits nearest the mic): a turn quieter than
    # turn_speech_floor_dbfs, or more than turn_speech_margin_db below the caller's
    # learned level, is dropped as room chatter unless Jev rates it addressed or it
    # answers the agent's question. Frames under that bar reach the STT as silence.
    # Gated browser sessions only. See gated_agent.
    turn_voice_isolation_enabled: bool = True
    turn_speech_margin_db: float = Field(10.0, ge=4.0, le=30.0)
    turn_speech_floor_dbfs: float = Field(-42.0, ge=-80.0, le=-20.0)
    # Turn router (app.agent.turn_router): Jev also says which lookup a finished
    # turn needs, so a search can run before the LLM instead of costing it a
    # second round trip. Gated browser sessions with an OpenRouter LLM only.
    router_enabled: bool = True
    # The small LLM that writes the search arguments (Jev can't), alongside Jev.
    # gemini-3.1-flash-lite: 1.1 s p50 in scripts/router_bench, vs 1.4-2.5 s for
    # gpt-5.4-nano and gpt-6-luna, at the same accuracy.
    router_model: str = "google/gemini-3.1-flash-lite"
    router_reasoning_effort: Literal["none", "minimal", "low"] = "none"
    router_timeout_ms: int = Field(1500, ge=100, le=5000)
    # Prefetch only when Jev is at least this sure which lookup the turn needs.
    router_min_p: float = Field(0.6, ge=0.0, le=1.0)
    # Quick replies (app.agent.quick_reply), switched on per agent from the
    # dashboard: a small model answers turns Jev says need no lookup, and speaks a
    # short filler line while a lookup runs. The model is the default for an
    # agent that hasn't picked one (app.agent.quick_models lists the allowed ids).
    quick_reply_model: str = "google/gemini-3.5-flash-lite"
    # The small model answers only when Jev is at least this sure no lookup is needed.
    quick_route_min_p: float = Field(0.7, ge=0.0, le=1.0)
    # How long the filler model call may take before it is given up on. Only a
    # safety for a hung connection: a filler is spoken whenever it is ready before
    # the reply's first words, however long that takes, and dropped after.
    filler_timeout_ms: int = Field(10000, ge=100, le=30000)
    # With template fillers (quick_filler_llm off), the reply waits this long
    # (a random length in the range) after the line, even when it is ready.
    filler_pause_min_ms: int = Field(1000, ge=0, le=5000)
    filler_pause_max_ms: int = Field(1500, ge=0, le=5000)
    # A filler takes Jev's word for what the turn is about when Jev is at least
    # this sure; else the topic comes from the customer's words (quick_reply._TOPIC_RES).
    filler_topic_min_p: float = Field(0.7, ge=0.0, le=1.0)
    # The small model's first chunk must arrive within this, or the main model
    # answers instead: every handoff pays it before the main model starts.
    fast_timeout_ms: int = Field(1000, ge=300, le=5000)
    # Characters of the small model's answer held back to catch its handoff marker.
    fast_buffer_chars: int = Field(24, ge=8, le=200)

    # Admin / auth
    admin_username: str = "ceo"
    admin_password_hash: str = ""
    jwt_secret: str = "dev-secret-change-me"
    jwt_expire_minutes: int = 480
    # Fernet key that encrypts secrets saved from the dashboard (the agent's LLM
    # API key). Unset -> saving a key is refused; there's no insecure fallback.
    settings_encryption_key: str = ""

    # Operator identity
    operator_name: str = "telco"
    # Mock contact details: the agent points customers here for anything it
    # can't answer. Dashboard-editable (agent_config). One unbroken digit run:
    # speech_numbers only reads a number as a phone number in that form.
    operator_phone: str = "01700121121"
    operator_address: str = "telco Experience Centre, Gulshan Avenue, Dhaka 1212"
    agent_display_name: str = "Anika"
    ceo_email: str = "ceo@example.com"
    # IANA zone the agent resolves spoken times in -- "tomorrow at 3pm" means
    # 3pm here, not UTC. Shown to the LLM as "now" and attached to any naive
    # datetime a tool receives.
    agency_timezone: str = "Asia/Dhaka"
    # Browser calls: after this long with no turn from the customer (background
    # speech the turn gate drops doesn't count), the agent asks whether they need
    # anything else, and ends the call if they say no or stay quiet for
    # idle_end_s more (see app.agent.idle_checkin). 0 turns it off.
    idle_checkin_s: float = Field(300.0, ge=0.0)
    # Seconds between background re-reads of the prompt's account snapshot
    # while the agent is listening (app.agent.snapshot_refresh); 0 = only on
    # turn boundaries.
    snapshot_refresh_s: float = Field(15.0, ge=0.0)
    idle_end_s: float = Field(30.0, gt=0.0)

    # Real phone calls (Twilio Elastic SIP Trunk -> self-hosted livekit-sip). A
    # scheduled call with a dial_number rings that phone instead of the browser.
    # The LiveKit outbound trunk id (ST_...), from registering the trunk with LiveKit.
    sip_outbound_trunk_id: str = ""
    # Comma-separated numbers that may be dialed; empty = no number may be dialed.
    # Guards against ringing strangers (seed clients carry real-looking numbers).
    sip_dial_allowlist: str = ""
    # Keep the ring window below typical carrier voicemail pickup (~20-30s),
    # otherwise voicemail "answers" and the agent pitches to it.
    sip_ring_timeout_s: int = 25
    # Cost cap: the SIP leg is dropped after this long regardless.
    sip_max_call_duration_s: int = 600

    # Twilio Elastic SIP Trunk details -- kept for reference, not read by the app.
    twilio_phone_number: str = ""
    twilio_sip_termination_uri: str = ""
    twilio_sip_username: str = ""
    twilio_sip_password: str = ""

    # Knowledge base: Chroma server (chromadb/chroma, HTTP only -- the embedded
    # client must never be shared between processes) and where uploaded
    # documents are stored. Empty upload_dir = backend/storage/uploads.
    chroma_host: str = "localhost"
    chroma_port: int = 8001
    upload_dir: str = ""

    # Per-session timing logs (app.agent.run_log): logs/run_<N>.log at the repo
    # root, or in run_log_dir when set.
    run_log_enabled: bool = True
    run_log_dir: str = ""

    # CORS
    backend_cors_origins: str = "http://localhost:3000"

    @property
    def upload_path(self) -> Path:
        return Path(self.upload_dir) if self.upload_dir else _BACKEND_ROOT / "storage" / "uploads"

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.backend_cors_origins.split(",") if o.strip()]

    @property
    def elevenlabs_keys(self) -> list[str]:
        candidates = [*self.elevenlabs_api_keys.split(","), self.elevenlabs_api_key]
        return list(dict.fromkeys(k.strip() for k in candidates if _real_key(k)))

    @property
    def deepgram_key(self) -> str:
        return self.deepgram_api_key.strip() if _real_key(self.deepgram_api_key) else ""


def _real_key(value: str) -> bool:
    """False for blanks and the "changeme" placeholder .env.example ships with."""
    return value.strip() not in ("", "changeme")


@lru_cache
def get_settings() -> Settings:
    return Settings()
