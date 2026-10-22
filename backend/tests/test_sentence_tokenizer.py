"""TTS sentence splitting ends Bangla sentences at । as well as . ! ?"""

import asyncio

from app.agent.sentence_tokenizer import SentenceTokenizer, split_sentences

_BANGLA = (
    "আপনার শর্ত অনুযায়ী আমাদের কাছে পাঁচটি ফ্ল্যাট আছে। "
    "সাভার বাজারে দুই বেডরুমের নয়শো বর্গফুটের ফ্ল্যাট আছে। "
    "আপনি কি দেখতে চান?"
)


def _texts(text: str) -> list[str]:
    return [sentence.strip() for sentence, _, _ in split_sentences(text)]


def test_bangla_splits_at_the_danda():
    assert _texts(_BANGLA) == [
        "আপনার শর্ত অনুযায়ী আমাদের কাছে পাঁচটি ফ্ল্যাট আছে।",
        "সাভার বাজারে দুই বেডরুমের নয়শো বর্গফুটের ফ্ল্যাট আছে।",
        "আপনি কি দেখতে চান?",
    ]


def test_english_splits_as_before():
    text = "We have four flats in Uttara for you. They start at 55 lakh taka. Want details?"
    assert _texts(text) == [
        "We have four flats in Uttara for you.",
        "They start at 55 lakh taka.",
        "Want details?",
    ]


def test_mixed_language_reply():
    text = "Uttara-তে আমাদের চারটি ফ্ল্যাট আছে। The cheapest is 55 lakh taka."
    assert _texts(text) == ["Uttara-তে আমাদের চারটি ফ্ল্যাট আছে।", "The cheapest is 55 lakh taka."]


def test_danda_without_a_following_space():
    text = "মোহাম্মদপুরে তিনটি ফ্ল্যাট আছে।সবগুলোতেই এখন অফার রয়েছে।"
    assert _texts(text) == ["মোহাম্মদপুরে তিনটি ফ্ল্যাট আছে।", "সবগুলোতেই এখন অফার রয়েছে।"]


def test_offsets_slice_the_original_text():
    for sentence, start, end in split_sentences(_BANGLA):
        assert _BANGLA[start:end] == sentence


def test_short_sentence_merges_into_the_next():
    text = "জি। মোহাম্মদপুরে কেনার জন্য তিনটি ফ্ল্যাট আছে।"
    assert _texts(text) == [text]


def test_stream_emits_the_first_sentence_before_the_reply_ends():
    async def go():
        stream = SentenceTokenizer().stream()
        stream.push_text("আপনার শর্ত অনুযায়ী আমাদের কাছে পাঁচটি ফ্ল্যাট আছে। ")
        stream.push_text("সাভার বাজারে দুই বেডরুমের নয়শো বর্গফুটের ফ্ল্যাট ")
        stream.end_input()
        return [ev.token.strip() async for ev in stream]

    tokens = asyncio.run(go())
    assert tokens[0] == "আপনার শর্ত অনুযায়ী আমাদের কাছে পাঁচটি ফ্ল্যাট আছে।"
    assert len(tokens) == 2
