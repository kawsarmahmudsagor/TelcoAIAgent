"""The small models quick replies may use (app.agent.quick_reply), each with the
OpenRouter `reasoning` setting that keeps its first token fastest.

Kept free of livekit so the dashboard API can import it.
"""

# Ordered fastest first (OpenRouter, measured for Sellora's quick replies).
QUICK_REPLY_MODELS: dict[str, dict] = {
    "google/gemini-3.5-flash-lite": {"effort": "minimal"},
    "google/gemini-3.1-flash-lite": {"enabled": False},
    "~anthropic/claude-haiku-latest": {"enabled": False},
    "openai/gpt-5.4-nano": {"effort": "none"},
}

QUICK_REPLY_LABELS: dict[str, str] = {
    "google/gemini-3.5-flash-lite": "Gemini 3.5 Flash Lite",
    "google/gemini-3.1-flash-lite": "Gemini 3.1 Flash Lite",
    "~anthropic/claude-haiku-latest": "Claude Haiku (latest)",
    "openai/gpt-5.4-nano": "GPT-5.4 nano",
}


def reasoning_for(model: str) -> dict:
    """The model's reasoning setting; minimal for one not in the list."""
    return QUICK_REPLY_MODELS.get(model, {"effort": "minimal"})
