"""Logs which provider APIs a session called and what they used.

Every usage update from the session (LLM tokens, STT audio seconds, TTS
characters) is logged as the increase since the previous update, so each line
is roughly one API call; tool calls are logged with their arguments, and the
session's totals per model when it closes. All lines use the "agent.usage"
logger, so they can be filtered out of the agent worker's console.
"""

import json
import logging

from livekit.agents import AgentSession

logger = logging.getLogger("agent.usage")

_MAX_ARGS_CHARS = 300

# Numeric fields worth logging per usage type; the rest stay zero for our providers.
_FIELDS = {
    "llm_usage": ("input_tokens", "input_cached_tokens", "output_tokens"),
    "stt_usage": ("audio_duration", "input_tokens", "output_tokens"),
    "tts_usage": ("characters_count", "audio_duration", "input_tokens", "output_tokens"),
}


def _fmt(kind: str, values: dict[str, float]) -> str:
    def n(field: str) -> str:
        v = values.get(field, 0)
        return f"{v:.1f}" if isinstance(v, float) else str(v)

    if kind == "llm_usage":
        text = f"{n('input_tokens')} input tokens"
        if values.get("input_cached_tokens"):
            text += f" ({n('input_cached_tokens')} cached)"
        return f"{text}, {n('output_tokens')} output tokens"
    if kind == "stt_usage":
        text = f"{n('audio_duration')}s audio"
    else:
        text = f"{n('characters_count')} chars, {n('audio_duration')}s audio"
    if values.get("input_tokens") or values.get("output_tokens"):
        text += f", {n('input_tokens')} in / {n('output_tokens')} out tokens"
    return text


_LABEL = {"llm_usage": "LLM", "stt_usage": "STT", "tts_usage": "TTS"}


class UsageLogger:
    def __init__(self, session_label: str = "") -> None:
        self._prefix = f"[{session_label}] " if session_label else ""
        self._last: dict[tuple[str, str, str], dict[str, float]] = {}

    def attach(self, session: AgentSession) -> None:
        session.on("session_usage_updated", self._on_usage)
        session.on("function_tools_executed", self._on_tools)
        session.on("close", self._on_close)

    def _on_usage(self, ev) -> None:
        for usage in ev.usage.model_usage:
            kind = usage.type
            fields = _FIELDS.get(kind)
            if fields is None:
                continue
            key = (kind, usage.provider, usage.model)
            current = {f: getattr(usage, f, 0) for f in fields}
            previous = self._last.get(key, {})
            delta = {f: current[f] - previous.get(f, 0) for f in fields}
            self._last[key] = current
            if not any(delta.values()):
                continue
            logger.info(
                "%s%s %s/%s: %s | session total: %s",
                self._prefix,
                _LABEL[kind],
                usage.provider or "?",
                usage.model or "?",
                _fmt(kind, delta),
                _fmt(kind, current),
            )

    def _on_tools(self, ev) -> None:
        for call in ev.function_calls:
            args = call.arguments or ""
            try:
                args = json.dumps(json.loads(args), ensure_ascii=False)
            except (TypeError, ValueError):
                pass
            if len(args) > _MAX_ARGS_CHARS:
                args = args[:_MAX_ARGS_CHARS] + "..."
            logger.info("%stool %s(%s)", self._prefix, call.name, args)

    def _on_close(self, _ev) -> None:
        if not self._last:
            return
        logger.info("%ssession usage totals:", self._prefix)
        for (kind, provider, model), values in self._last.items():
            logger.info("  %s %s/%s: %s", _LABEL[kind], provider or "?", model or "?", _fmt(kind, values))
