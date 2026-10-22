"""Sentence splitting for TTS that knows the Bangla full stop.

The TTS StreamAdapter synthesizes one sentence at a time, so the agent starts
speaking as soon as the LLM finishes its first sentence. Its default tokenizer
(blingfire) only ends sentences at . ! ? -- a Bangla reply ending each sentence
with দাঁড়ি (।) came through as one chunk, sent to TTS only once the whole reply
was written (4+ s before the first audio in run_2, vs 0.7 s in English).

This is blingfire's splitter with । and ॥ added as sentence ends.
"""

import functools
import re

from livekit import blingfire
from livekit.agents.tokenize import token_stream, tokenizer

_DANDA = re.compile(r"[।॥]+")

# blingfire's defaults: spans shorter than this merge into the next sentence,
# so a short "জি।" doesn't become a TTS request of its own.
MIN_SENTENCE_LEN = 20
STREAM_CONTEXT_LEN = 10


def split_sentences(
    text: str, min_sentence_len: int = MIN_SENTENCE_LEN, *, retain_format: bool = True
) -> list[tuple[str, int, int]]:
    """(sentence, start, end) spans, like blingfire._split_sentences."""
    if not text or not text.strip():
        return []

    _, offsets = blingfire.text_to_sentences_with_offsets(text)
    ends = {end for _, end in offsets}
    ends.update(match.end() for match in _DANDA.finditer(text))

    sentences: list[tuple[str, int, int]] = []
    start = 0
    for end in sorted(ends):
        if end <= start:
            continue
        raw_sentence = text[start:end]
        sentence = re.sub(r"\s*\n+\s*", " ", raw_sentence).strip()
        if not sentence or len(sentence) < min_sentence_len:
            continue
        sentences.append((raw_sentence if retain_format else sentence, start, end))
        start = end

    if start < len(text):
        raw_sentence = text[start:]
        if retain_format:
            sentences.append((raw_sentence, start, len(text)))
        elif sentence := raw_sentence.strip():
            sentences.append((sentence, start, len(text)))
    return sentences


class SentenceTokenizer(tokenizer.SentenceTokenizer):
    """blingfire's SentenceTokenizer(retain_format=True), plus । and ॥."""

    def __init__(
        self,
        *,
        min_sentence_len: int = MIN_SENTENCE_LEN,
        stream_context_len: int = STREAM_CONTEXT_LEN,
    ) -> None:
        self._min_sentence_len = min_sentence_len
        self._stream_context_len = stream_context_len

    def _split(self):
        return functools.partial(split_sentences, min_sentence_len=self._min_sentence_len)

    def tokenize(self, text: str, *, language: str | None = None) -> list[str]:
        return [sentence for sentence, _, _ in self._split()(text)]

    def stream(self, *, language: str | None = None) -> tokenizer.SentenceStream:
        return token_stream.BufferedSentenceStream(
            tokenizer=self._split(),
            min_token_len=self._min_sentence_len,
            min_ctx_len=self._stream_context_len,
        )
