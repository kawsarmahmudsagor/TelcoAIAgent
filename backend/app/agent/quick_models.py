"""The small models quick replies may use (app.agent.quick_reply), each with the
OpenRouter `reasoning` setting that keeps its first token fastest.

Kept free of livekit so the dashboard API can import it.
"""

# Ordered fastest first (OpenRouter, measured for Sellora's quick replies).
QUICK_REPLY_MODELS: dict[str, dict] = {
    "google/gemini-3.5-flash-lite": {"effort": "minimal"},
    "google/gemini-3.1-flash-lite": {"enabled": False},
    "openai/gpt-5.4-nano": {"effort": "none"},
    "x-ai/grok-4.7": {"effort": "none"},
    "openai/gpt-oss-120b": {"effort": "none"},
    "anthropic/claude-haiku-4.5": {"effort": "none"},
    "google/gemini-3.5-flash": {"effort": "minimal"},
    "~anthropic/claude-haiku-latest": {"enabled": False},
}

QUICK_REPLY_LABELS: dict[str, str] = {
    "google/gemini-3.5-flash-lite": "Gemini 3.5 Flash Lite",
    "google/gemini-3.1-flash-lite": "Gemini 3.1 Flash Lite",
    "openai/gpt-5.4-nano": "GPT-5.4 nano",
    "x-ai/grok-4.7": "xAI Grok 4.7",
    "openai/gpt-oss-120b": "OpenAI GPT-OSS 120B",
    "anthropic/claude-haiku-4.5": "Claude Haiku 4.5",
    "google/gemini-3.5-flash": "Gemini 3.5 Flash",
    "~anthropic/claude-haiku-latest": "Claude Haiku (latest)",
}


def reasoning_for(model: str) -> dict:
    """The model's reasoning setting; minimal for one not in the list."""
    conf = QUICK_REPLY_MODELS.get(model, {})
    if "effort" in conf:
        return {"effort": conf["effort"]}
    if "max_tokens" in conf:
        return {"max_tokens": conf["max_tokens"]}
    return {"effort": "minimal"}
