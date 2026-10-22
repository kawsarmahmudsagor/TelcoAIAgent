import asyncio

import pytest

from app.agent.speech_words import respell_for_speech, respell_words_for_speech


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("কোন এলাকায় খুঁজছেন?", "কোন্ এলাকায় খুঁজছেন?"),
        ("আপনি কোন ফ্ল্যাটটি দেখতে চাচ্ছেন?", "আপনি কোন্ ফ্ল্যাটটি দেখতে চাচ্ছেন?"),
        ("কোন?", "কোন্?"),
        # "any" and longer words are left alone.
        ("কোনো সমস্যা নেই", "কোনো সমস্যা নেই"),
        ("যেকোন সময়", "যেকোন সময়"),
        ("কোনটা পছন্দ?", "কোনটা পছন্দ?"),
        ("Which area?", "Which area?"),
    ],
)
def test_respell_for_speech(text, expected):
    assert respell_for_speech(text) == expected


async def _collect(chunks):
    async def gen():
        for c in chunks:
            yield c

    return "".join([part async for part in respell_words_for_speech(gen())])


@pytest.mark.parametrize(
    ("chunks", "expected"),
    [
        (["কো", "ন এলাকায়?"], "কোন্ এলাকায়?"),
        (["কোন", " এলাকায়?"], "কোন্ এলাকায়?"),
        (["কোন", "ো সমস্যা নেই"], "কোনো সমস্যা নেই"),
        (["আপনি কোন"], "আপনি কোন্"),
    ],
)
def test_streamed_word_split_across_chunks(chunks, expected):
    assert asyncio.run(_collect(chunks)) == expected
