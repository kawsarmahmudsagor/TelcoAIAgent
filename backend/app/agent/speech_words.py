"""TTS text transform that respells Bangla words the voice mispronounces.

Bangla letters carry an inherent "o" the script doesn't always mark, and the
TTS guesses it wrong on some common words: কোন ("which", said "kon") comes out
as কোনো ("any", "kono"). Writing the word with a hasanta (কোন্) marks the
dropped vowel, and the voice then says it right. The agent is told to spell
"any" as কোনো, so a bare কোন is "which". Only the TTS input is changed -- the
chat transcript keeps the agent's spelling.
"""

import re
from collections.abc import AsyncIterable

# Bengali letters, vowel signs and marks; a respelt word must stand alone, so
# "যেকোন" or "কোনটা" are left as they are.
_BN_CHAR = "ঀ-৿"

# Word as the agent writes it -> how the voice should get it.
_RESPELLINGS = {
    "কোন": "কোন্",
}

_RESPELL_RE = re.compile(
    rf"(?<![{_BN_CHAR}])({'|'.join(map(re.escape, _RESPELLINGS))})(?![{_BN_CHAR}])"
)

# A Bengali word still being streamed: "কো" may yet become "কোন" or "কোনো".
_UNFINISHED_WORD_RE = re.compile(rf"[{_BN_CHAR}]+\Z")


def respell_for_speech(text: str) -> str:
    return _RESPELL_RE.sub(lambda m: _RESPELLINGS[m.group(1)], text)


async def respell_words_for_speech(text: AsyncIterable[str]) -> AsyncIterable[str]:
    """Streaming `tts_text_transforms` entry for AgentSession. A Bengali word
    at the end of a chunk is held back until the next chunk shows where it ends."""
    buffer = ""
    async for chunk in text:
        buffer += chunk
        held = _UNFINISHED_WORD_RE.search(buffer)
        flush_to = held.start() if held else len(buffer)
        if flush_to > 0:
            yield respell_for_speech(buffer[:flush_to])
            buffer = buffer[flush_to:]
    if buffer:
        yield respell_for_speech(buffer)
