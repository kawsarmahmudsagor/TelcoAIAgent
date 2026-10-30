import asyncio
import re

import pytest

from app.agent.speech_numbers import (
    numbers_to_bangla_words,
    numbers_to_words,
    speak_numbers_as_words,
)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("It costs 200 taka.", "It costs two hundred taka."),
        ("Rent is 25,000 a month", "Rent is twenty-five thousand a month"),
        ("Price: 2500000", "Price: twenty-five lakh"),
        ("1,20,00,000 taka", "one crore twenty lakh taka"),
        ("৳25000", "twenty-five thousand taka"),
        ("৳2,500,000", "twenty-five lakh taka"),
        ("৳25 lakh", "twenty-five lakh taka"),
        ("৳10,000–৳20,000", "ten thousand taka–twenty thousand taka"),
        ("apnar budget 25000 taka", "apnar budget twenty-five thousand taka"),
        ("1200 sqft", "one thousand two hundred sqft"),
        ("1.5 km away", "one point five km away"),
        ("on the 2nd floor", "on the second floor"),
        ("at 3:30 PM", "at three thirty PM"),
        ("at 3:00 PM", "at three PM"),
        ("at 10:05", "at ten oh five"),
        ("3 bedrooms, 2 baths.", "three bedrooms, two baths."),
    ],
)
def test_numbers_become_words(text, expected):
    assert numbers_to_words(text) == expected


_SPOKEN_017 = "zero one seven one two three four five six seven eight"

# The English words a Bangla reply's voice gets in Bangla script.
_IN_BENGALI = {
    "zero": "জিরো", "one": "ওয়ান", "two": "টু", "three": "থ্রি", "four": "ফোর",
    "five": "ফাইভ", "six": "সিক্স", "seven": "সেভেন", "eight": "এইট", "nine": "নাইন",
    "twelve": "টুয়েলভ", "double": "ডাবল", "triple": "ট্রিপল",
}  # fmt: skip


def _bn(text: str) -> str:
    """English number words in `text` as written for a Bangla reply's voice."""
    return re.sub(r"[a-z]+", lambda m: _IN_BENGALI.get(m.group(), m.group()), text)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (
            "Call 01701001398",
            "Call zero one seven zero one double zero one three nine eight",
        ),
        ("Call 01700000000", "Call zero one seven triple zero triple zero double zero"),
        ("Call 01712345678", f"Call {_SPOKEN_017}"),
        ("Call +8801712345678", f"Call {_SPOKEN_017}"),
        ("Call +880 1712-345678", f"Call {_SPOKEN_017}"),
        ("Call 017-1234-5678", f"Call {_SPOKEN_017}"),
        (
            "Call 01811110000",
            "Call zero one eight double one double one double zero double zero",
        ),
        (
            "Call +44 20 7946 0000",
            "Call plus double four two zero seven nine four six double zero double zero",
        ),
        ("No numbers here.", "No numbers here."),
    ],
)
def test_phone_numbers_said_digit_by_digit_in_english(text, expected):
    assert numbers_to_words(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        # Always English, even in a Bangla reply with Bengali digits.
        (
            "নম্বর ০১৭০০০০০০০০, ঠিক আছে?",
            "নম্বর zero one seven triple zero triple zero double zero, ঠিক আছে?",
        ),
        (
            "কল করুন ০১৭০১০০১৩৯৮",
            "কল করুন zero one seven zero one double zero one three nine eight",
        ),
        # The agent is told to write one unbroken run, but sometimes splits it or
        # drops the "+"; it must still not be read as a Bangla quantity.
        ("নম্বর ০১৭১২-৩৪৫৬৭৮।", f"নম্বর {_SPOKEN_017}।"),
        ("নম্বর ০১৭১২ ৩৪৫৬৭৮।", f"নম্বর {_SPOKEN_017}।"),
        ("নম্বর ০১৭ ১২৩৪ ৫৬৭৮।", f"নম্বর {_SPOKEN_017}।"),
        ("নম্বর 01712-345678।", f"নম্বর {_SPOKEN_017}।"),
        ("নম্বর ৮৮০১৭১২৩৪৫৬৭৮।", f"নম্বর {_SPOKEN_017}।"),
        ("নম্বর ৮৮০ ১৭১২-৩৪৫৬৭৮।", f"নম্বর {_SPOKEN_017}।"),
        ("নম্বর ১৭১২৩৪৫৬৭৮।", "নম্বর one seven one two three four five six seven eight।"),
        ("নম্বর ০১৭১২৩৪৫৬৭৮ ২৫ লাখ", f"নম্বর {_SPOKEN_017} পঁচিশ লাখ"),
    ],
)
def test_phone_numbers_in_bangla_are_said_in_english(text, expected):
    # In Bangla script: the voice reads Latin-letter English words the Bangla way.
    assert numbers_to_bangla_words(text) == _bn(expected)


def test_default_operator_phone_is_said_as_a_phone_number():
    # The prompt tells the agent to repeat this number as given.
    from app.config import get_settings

    phone = get_settings().operator_phone
    bangla = phone.translate(str.maketrans("0123456789", "০১২৩৪৫৬৭৮৯"))
    spoken = "zero one seven double zero one two double one two one"
    assert numbers_to_words(f"Call {phone} today") == f"Call {spoken} today"
    assert numbers_to_bangla_words(f"{bangla} নম্বরে কল করুন") == _bn(f"{spoken} নম্বরে কল করুন")


def test_bengali_digit_phone_split_across_chunks():
    assert _run(["মোবাইল নম্বর ০১৭০", "০০০০০০০, ঠিক?"]) == _bn(
        "মোবাইল নম্বর zero one seven triple zero triple zero double zero, ঠিক?"
    )


async def _stream(chunks):
    for chunk in chunks:
        yield chunk


def _run(chunks) -> str:
    async def collect():
        return "".join([c async for c in speak_numbers_as_words(_stream(chunks))])

    return asyncio.run(collect())


def test_number_split_across_chunks():
    assert _run(["Price is 25", ",000 taka."]) == "Price is twenty-five thousand taka."


def test_ordinal_split_across_chunks():
    assert _run(["the 2", "nd floor"]) == "the second floor"


def test_phone_split_across_chunks():
    assert _run(["Call +880 ", "1712 345678 now"]) == f"Call {_SPOKEN_017} now"


def test_spaced_phone_split_across_chunks():
    assert _run(["Call 01712 ", "345678 now"]) == f"Call {_SPOKEN_017} now"
    assert _run(["নম্বর ০১৭১২ ", "৩৪৫৬৭৮।"]) == _bn(f"নম্বর {_SPOKEN_017}।")


def test_taka_sign_does_not_count_as_bangla():
    assert (
        _run(["Rent is ৳25,000, ", "3 beds"])
        == "Rent is twenty-five thousand taka, three beds"
    )


def test_taka_sign_split_from_amount():
    assert _run(["Price ৳", "25,000."]) == "Price twenty-five thousand taka."


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("দাম ২৫ লাখ টাকা", "দাম পঁচিশ লাখ টাকা"),
        ("৳২৫ লাখ", "পঁচিশ লাখ টাকা"),
        ("ভাড়া ৳25,000", "ভাড়া পঁচিশ হাজার টাকা"),
        ("ভাড়া ২২,০০০ টাকা, ১২০০ বর্গফুট", "ভাড়া বাইশ হাজার টাকা, এক হাজার দুইশো বর্গফুট"),
        # Hundreds as spoken, "শো", not the bookish "শত".
        ("৫০০ বর্গফুট", "পাঁচশো বর্গফুট"),
        ("১০০ টাকা", "একশো টাকা"),
        ("৯০০", "নয়শো"),
        ("৫ম তলা", "পঞ্চম তলা"),
        ("২য় তলা", "দ্বিতীয় তলা"),  # য় as one code point
        ("২য় তলা", "দ্বিতীয় তলা"),  # য় as two
        ("১০মিনিট", "দশমিনিট"),
    ],
)
def test_bangla_numbers_become_bangla_words(text, expected):
    assert numbers_to_bangla_words(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("10% off", "ten percent off"),
        ("up to 17 % discount", "up to seventeen percent discount"),
        ("2.5% fee", "two point five percent fee"),
        ("a 10％ waiver", "a ten percent waiver"),  # full-width sign
    ],
)
def test_percent_sign_is_said_as_percent(text, expected):
    assert numbers_to_words(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("১০% ছাড়", "দশ পার্সেন্ট ছাড়"),
        ("10% discount", "দশ পার্সেন্ট discount"),
        ("৫٪ ছাড়", "পাঁচ পার্সেন্ট ছাড়"),  # Arabic percent sign
    ],
)
def test_percent_sign_is_said_as_percent_in_bangla(text, expected):
    # "Percent", not "শতাংশ" -- in Bangla script so the voice says it the same way.
    assert numbers_to_bangla_words(text) == expected


def test_percent_sign_split_from_its_number():
    assert _run(["Get 10", "% off."]) == "Get ten percent off."


def test_banglish_reply_says_percent():
    assert (
        _run(["Apnar jonno ", "10% chhar ache."]) == "Apnar jonno দশ পার্সেন্ট chhar ache."
    )


def test_bengali_reply_gets_bangla_words():
    assert _run(["দাম 25000 ", "টাকা"]) == "দাম পঁচিশ হাজার টাকা"


def test_reply_opening_with_a_number_waits_for_the_script():
    assert _run(["25 ", "লাখ টাকা"]) == "পঁচিশ লাখ টাকা"


def test_bangla_ordinal_split_across_chunks():
    assert _run(["৪র", "্থ তলা"]) == "চতুর্থ তলা"


def test_banglish_reply_gets_bangla_words():
    assert _run(["Apnar budget-er moddhe ", "28,000 taka, 1200 sqft ache."]) == (
        "Apnar budget-er moddhe আটাশ হাজার taka, এক হাজার দুইশো sqft ache."
    )


def test_banglish_reply_opening_with_a_number_waits_for_its_words():
    assert _run(["28,000 taka, 2 ", "bedroom, parking shoho. ", "Dekhte chan?"]) == (
        "আটাশ হাজার taka, দুই bedroom, parking shoho. Dekhte chan?"
    )


def test_english_reply_decided_at_the_end_of_its_first_sentence():
    assert _run(["28,000 taka, 2 ", "bedrooms. ", "Apni ki dekhte chan?"]) == (
        "twenty-eight thousand taka, two bedrooms. Apni ki dekhte chan?"
    )


def test_english_text_streams_before_the_first_number():
    async def first_chunk():
        stream = speak_numbers_as_words(_stream(["Rent is ", "25,000 taka."]))
        return await anext(aiter(stream))

    assert asyncio.run(first_chunk()) == "Rent is "


@pytest.mark.parametrize(
    "text, expected",
    [
        ("106 lakh taka", "one crore six lakh taka"),
        ("142.5 lakh", "one crore forty-two point five lakh"),
        ("200 lakh taka", "two crore taka"),
        ("95 lakh taka", "ninety-five lakh taka"),
    ],
)
def test_lakh_from_a_hundred_up_is_said_as_crore(text, expected):
    assert numbers_to_words(text) == expected


def test_bangla_lakh_from_a_hundred_up_is_said_as_crore():
    assert numbers_to_bangla_words("১০৬ লাখ টাকা") == numbers_to_bangla_words("১ কোটি ৬ লাখ টাকা")
    assert numbers_to_bangla_words("১৮৩ লাখ") == numbers_to_bangla_words("১ কোটি ৮৩ লাখ")


def test_lakh_split_from_its_number_across_chunks():
    assert _run(["নিকেতানে ১০৬", " লা", "খ টাকা"]) == _run(["নিকেতানে ১ কোটি ৬ লাখ টাকা"])
    assert _run(["It is 106", " lakh taka."]) == "It is one crore six lakh taka."


_ADDRESS_SPOKEN = "House টুয়েলভ, Road সেভেন, Gulshan ওয়ান, Dhaka ওয়ান টু ওয়ান টু"


def test_english_address_in_a_bangla_reply_is_said_in_english_in_bangla_script():
    text = "আমাদের হেড অফিস House 12, Road 7, Gulshan 1, Dhaka 1212-এ এসে কথা বলতে পারেন।"
    assert numbers_to_bangla_words(text) == (
        f"আমাদের হেড অফিস {_ADDRESS_SPOKEN}-এ এসে কথা বলতে পারেন।"
    )


def test_bangla_numbers_after_a_capitalised_word_need_the_word_right_before():
    # Bangla words, a phone number and a price keep their usual reading.
    assert numbers_to_bangla_words("Gulshan-এ ৩টি ফ্ল্যাট") == "Gulshan-এ তিনটি ফ্ল্যাট"
    assert numbers_to_bangla_words("Horizon 01711234567") == _bn(
        "Horizon zero one seven double one two three four five six seven"
    )
    assert numbers_to_bangla_words("Banani 25,000 টাকা") == "Banani পঁচিশ হাজার টাকা"


def test_english_address_split_across_chunks_in_a_bangla_reply():
    chunks = ["হেড অফিস House", " 12, Road ", "7, Gulshan 1, Dhaka", " 1212-এ আসুন।"]
    assert _run(chunks) == f"হেড অফিস {_ADDRESS_SPOKEN}-এ আসুন।"


def _run_fixed(chunks, language) -> str:
    from app.agent.speech_numbers import number_speaker

    async def collect():
        return "".join([c async for c in number_speaker(language)(_stream(chunks))])

    return asyncio.run(collect())


def test_number_speaker_fixed_bangla_speaks_bangla_without_bengali_letters():
    assert _run_fixed(["৳300"], "bn") == numbers_to_bangla_words("৳300")
    assert "তিন" in _run_fixed(["৳300"], "bn")


def test_number_speaker_fixed_english():
    assert _run_fixed(["দাম 25", " টাকা"], "en") == numbers_to_words("দাম 25 টাকা")


def test_number_speaker_unset_is_the_default_transform():
    assert _run_fixed(["Price is 25", ",000 taka."], None) == _run(["Price is 25", ",000 taka."])
