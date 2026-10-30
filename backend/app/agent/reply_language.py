"""The reply language the customer picked when the chat opened.

A browser chat starts with an English / Bangla pick (the token route's
dispatch metadata, `reply_language`). Once set, it is the only language the
agent replies in, whatever the customer writes or speaks: the prompt, the
per-turn reminder, fillers, idle lines and number speech all read it from
here. Unset (phone calls, chats from before the pick) every one of them keeps
following the customer's latest message.
"""

from typing import Literal, get_args

ReplyLanguage = Literal["en", "bn"]

_NAMES: dict[str, str] = {"en": "English", "bn": "Bangla (Bengali script)"}

# Said for speech in another language or that can't be made out.
OTHER_LANGUAGE_LINES: dict[str, str] = {
    "en": "I could not understand that. Could you kindly repeat that?",
    "bn": "দুঃখিত, বুঝতে পারিনি। আরেকবার বলবেন, প্লিজ?",
}


def parse(raw: object) -> ReplyLanguage | None:
    """"en" or "bn" exactly, else None."""
    return raw if isinstance(raw, str) and raw in get_args(ReplyLanguage) else None  # type: ignore[return-value]


def fixed(userdata: object) -> ReplyLanguage | None:
    """The session's picked language, or None when the customer picked none."""
    return parse(getattr(userdata, "reply_language", None))


def name(lang: ReplyLanguage) -> str:
    return _NAMES[lang]


def prompt_block(lang: ReplyLanguage) -> str:
    """The system prompt's language rule for a picked language."""
    script = " Write Bangla in Bengali script, never in English letters." if lang == "bn" else ""
    language = name(lang)
    return (
        f"REPLY LANGUAGE — the customer chose {language} for this chat. Reply only in "
        f"{language}, in every reply, whatever language the customer writes or speaks in "
        f"(English, Bangla or Banglish), including their very first message, and whatever "
        f"language a tool or the knowledge base returns.{script} Greet in {language}. This "
        f"overrides the LANGUAGE rules above and any note that says to use the language of the "
        f"customer's message. For speech you cannot make out, or another language, say exactly "
        f'"{OTHER_LANGUAGE_LINES[lang]}" and nothing else.\n'
    )


def in_language(lang: ReplyLanguage | None, default: str) -> str:
    """"in English" / "in Bangla (Bengali script)", or `default` when unset."""
    return f"in {name(lang)}" if lang else default
