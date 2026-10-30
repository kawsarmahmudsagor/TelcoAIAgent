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
    assert clean_reply_text("The D8-7D package, case TC-2048.") == "The D8-7D package, case TC-2048."
    assert clean_reply_text("২–৩ কাজের দিনে") == "২-৩ কাজের দিনে"


def test_pack_is_always_package():
    assert clean_reply_text("আপনার ডাটা প্যাকটা আজ শেষ, নতুন প্যাক নেবেন?") == (
        "আপনার ডাটা প্যাকেজটা আজ শেষ, নতুন প্যাকেজ নেবেন?"
    )
    assert clean_reply_text("প্যাকে ১ জিবি আছে, ডাটাপ্যাকগুলো") == "প্যাকেজে ১ জিবি আছে, ডাটাপ্যাকেজগুলো"
    assert clean_reply_text("Two packs: the Pack 7D and a PACK.") == (
        "Two packages: the Package 7D and a PACKAGE."
    )
    # Already a package, or another word.
    for text in ("প্যাকেজটা", "একটা প্যাকেট", "প্যাকিং", "a package, packed and packaging"):
        assert clean_reply_text(text) == text


def test_a_pack_split_across_chunks_is_still_a_package():
    assert "".join(_clean(["আপনার ডাটা প্যা", "কটা শেষ"])) == "আপনার ডাটা প্যাকেজটা শেষ"
    assert "".join(_clean(["আপনার প্যাকে", "জটা শেষ"])) == "আপনার প্যাকেজটা শেষ"
    assert "".join(_clean(["Your data pa", "ck ends; buy a pa", "ckage?"])) == (
        "Your data package ends, buy a package?"
    )
    assert "".join(_clean(["a new pack"])) == "a new package"


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


def test_slow_is_slow_not_dhir():
    # The user's word: "স্লো" for a slow connection, not the bookish ধীর.
    assert clean_reply_text("চাইলে ধীর বা বন্ধ নেটের সমস্যায় একটা কেস খুলে দিতে পারি।") == (
        "চাইলে স্লো বা বন্ধ নেটের সমস্যায় একটা কেস খুলে দিতে পারি।"
    )
    assert clean_reply_text("নেট ধীরে চলছে, ধীরগতির নেটওয়ার্ক, ধীর গতিতে") == (
        "নেট স্লো চলছে, স্লো নেটওয়ার্ক, স্লো"
    )
    # "Gradually" keeps its words.
    assert clean_reply_text("ধীরে ধীরে ঠিক হয়ে যাবে") == "ধীরে ধীরে ঠিক হয়ে যাবে"


def test_a_dhir_split_across_chunks_is_still_slow():
    assert "".join(_clean(["নেট ধী", "র চলছে"])) == "নেট স্লো চলছে"
    assert "".join(_clean(["নেট ধীরে", " ধীরে ঠিক হবে"])) == "নেট ধীরে ধীরে ঠিক হবে"
