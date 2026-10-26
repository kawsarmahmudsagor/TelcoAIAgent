"""Dashes and semicolons in the agent's replies become commas; hyphens in codes
and digit ranges stay."""

import asyncio

from livekit.agents import llm

from app.agent.reply_punctuation import clean_reply_stream, clean_reply_text


def _clean(chunks):
    async def stream():
        for chunk in chunks:
            yield chunk

    async def go():
        return [chunk async for chunk in clean_reply_stream(stream())]

    return asyncio.run(go())


def test_a_dash_or_semicolon_becomes_a_comma():
    assert clean_reply_text("২ ঘণ্টার মধ্যে চালু হয়—চাইলে বলি?") == "২ ঘণ্টার মধ্যে চালু হয়, চাইলে বলি?"
    assert clean_reply_text("Block it first; then visit us.") == "Block it first, then visit us."
    assert clean_reply_text("It's 200 taka – paid at the counter.") == "It's 200 taka, paid at the counter."


def test_codes_and_ranges_keep_their_hyphen():
    assert clean_reply_text("The D8-7D pack, case TC-2048.") == "The D8-7D pack, case TC-2048."
    assert clean_reply_text("২–৩ কাজের দিনে") == "২-৩ কাজের দিনে"


def test_a_dash_split_across_chunks_is_still_one_comma():
    out = _clean(["চালু হয় ", "—", " চাইলে বলি?"])
    assert "".join(out) == "চালু হয়, চাইলে বলি?"


def test_a_range_split_across_chunks_stays_a_range():
    assert "".join(_clean(["২ ", "– ", "৩ দিনে"])) == "২-৩ দিনে"


def test_chat_chunks_are_cleaned_and_a_trailing_dash_dropped():
    def chunk(text):
        return llm.ChatChunk(id="c", delta=llm.ChoiceDelta(role="assistant", content=text))

    out = _clean([chunk("Sure;"), chunk(" one moment —")])
    assert [c.delta.content if isinstance(c, llm.ChatChunk) else c for c in out] == [
        "Sure",
        ", one moment",
    ]
