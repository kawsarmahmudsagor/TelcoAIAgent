import pytest

from app.agent import turn_gate
from app.agent.turn_gate import GateState, Thresholds, Verdict, decide, precheck


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("আমার বাজেট ৫০ লাখ।", ["আমার", "বাজেট", "লাখ"]),
        ("জানাবেন? শুনুন", ["জানাবেন", "শুনুন"]),
        ("My budget is 1.5 crore.", ["my", "budget", "is", "crore"]),
        ("rahim.uddin@gmail.com", ["rahim", "uddin@gmail", "com"]),
        ("   ", []),
    ],
)
def test_words_keep_bengali_words_whole(text, expected):
    assert turn_gate.words(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("আমার বাজেট ৫০ লাখ।", "bn"),
        ("Do you have anything in Dhanmondi?", "en"),
        ("আমার বাজেট 50 lakh", "bn"),
        ("Café near Gulshan", "en"),
        ("कल सुबह हम बाज़ार चलेंगे।", "other"),
        # A few letters of another script among English words (run_53).
        ("आ वो लोग milestone repeat की", "other"),
        ("А потом надо просто проталкивать и будет работать", "other"),
        ("আমার বাজেট 50 lakh, ok?", "bn"),
        ("آپ کہاں جا رہے ہیں؟", "other"),
        ("৫০", "none"),
        ("...", "none"),
    ],
)
def test_classify_script(text, expected):
    assert turn_gate.classify_script(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("hmm", True),
        ("Uh, um.", True),
        ("হুম", True),
        ("", True),
        ("৫০", True),
        ("হ্যাঁ", False),
        ("yes", False),
        ("hmm, three bedrooms", False),
        ("[clears throat]", True),
        ("(laughs)", True),
        ("[clears throat] হ্যাঁ", False),
    ],
)
def test_is_filler_or_empty(text, expected):
    assert turn_gate.is_filler_or_empty(text) is expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("[clears throat]", True),
        ("(laughs) [noise]", True),
        ("[clears throat] হ্যাঁ", False),
        ("hmm", False),
        ("", False),
        ("budget (2 crore)", False),
    ],
)
def test_is_sound_only(text, expected):
    assert turn_gate.is_sound_only(text) is expected


def test_sound_tags_dont_count_as_words():
    assert turn_gate.words("[clears throat] হ্যাঁ") == ["হ্যাঁ"]
    assert turn_gate.words("the price (2 crore) is fine") == [
        "the", "price", "crore", "is", "fine",
    ]
    pre = turn_gate.precheck("[clears throat]", None)
    assert pre.filler and pre.script == "none" and pre.word_count == 0
    assert not turn_gate.needs_judge(pre, stt_writes_bengali=True)
    assert turn_gate.is_stop_phrase("[laughs] wait")


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Wait.", True),
        ("wait, what was the price?", True),
        ("Hold on", True),
        ("No no, not Banani", True),
        ("না না, বনানী।", True),
        ("থামুন, দামটা আবার বলবেন?", True),
        ("এক মিনিট শুনুন", True),
        ("waiting for the price", False),
        ("I can't wait to see it", False),
        ("না, আমি ভাড়া খুঁজছি", False),
    ],
)
def test_is_stop_phrase(text, expected):
    assert turn_gate.is_stop_phrase(text) is expected


_BOT = "The Banani flat is 1,400 sqft with two bedrooms, priced at 85 lakh taka, and it has a lift."


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("the Banani flat is 1400 square", True),
        ("priced at eighty five lakh taka and it has a lift", True),
        ("No no, not Banani, I said Bashundhara", False),
        ("Banani", False),
        ("What was the price again?", False),
    ],
)
def test_is_echo(text, expected):
    assert turn_gate.is_echo(text, ["", _BOT]) is expected


def test_is_echo_bangla():
    bot = "গুলশানের ফ্ল্যাটটা ১৮০০ বর্গফুট, দাম ২ কোটি ৫০ লাখ টাকা, তিনটা বেডরুম"
    assert turn_gate.is_echo("ফ্ল্যাটটা আঠারোশো বর্গফুট দাম", [bot])
    assert not turn_gate.is_echo("না না, বনানী", [bot])


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("আপনারা কি সাভারেও কাজ করেন?", "formal"),
        ("নামটা জানাবেন?", "formal"),
        ("এক মিনিট শুনুন", "formal"),
        ("তুমি কি চা খাবে?", "informal"),
        ("ফোনটা দাও তো।", "informal"),
        ("তুই কি করিস?", "informal"),
        ("আমার বাজেট ৫০ লাখ।", None),
        ("Do you have parking?", None),
        ("আপনি তুমি", None),
    ],
)
def test_address_form(text, expected):
    assert turn_gate.address_form(text) == expected


@pytest.mark.parametrize(
    ("confidence", "expected"), [(None, False), (0.0, False), (0.01, True), (0.9, True)]
)
def test_confidence_known(confidence, expected):
    assert turn_gate.confidence_known(confidence) is expected


@pytest.mark.parametrize(
    ("text", "handled", "age", "expected"),
    [
        ("No no, Banani", "no no banani", 1.0, True),
        ("wait, what was the price again", "wait", 1.0, True),
        ("wait", "Wait, what was the price", 1.0, True),
        ("No no, Banani", "no no banani", 30.0, False),
        ("Something else", "wait", 1.0, False),
        ("anything", None, 0.0, False),
        ("", "wait", 0.0, False),
    ],
)
def test_matches_handled(text, handled, age, expected):
    assert turn_gate.matches_handled(text, handled, age) is expected


# ---- decide ----

_NOW = 1000.0


def _decide(text, p, *, confidence=0.9, bengali=True, state=None, now=_NOW, bot_asked=False):
    return decide(
        precheck(text, confidence),
        p,
        stt_writes_bengali=bengali,
        state=state or GateState(),
        now=now,
        bot_asked=bot_asked,
    )


@pytest.mark.parametrize("text", ["হুম", "hmm", "hmm.", "Mm-hmm", "হুঁম"])
def test_a_hum_answering_a_question_is_accepted(text):
    assert _decide(text, None, bot_asked=True) is Verdict.ACCEPT
    assert _decide(text, None) is Verdict.DROP


@pytest.mark.parametrize("text", ["um", "উম", "uh-huh", "ah"])
def test_other_fillers_after_a_question_are_still_dropped(text):
    assert _decide(text, None, bot_asked=True) is Verdict.DROP


def test_a_bangla_no_is_never_an_assent():
    # উহু ("no") isn't a filler: it goes to the judge like any other answer.
    assert not turn_gate.is_assent_filler("উহু")
    assert not turn_gate.is_assent_filler("উঁহু")


def test_every_assent_filler_is_a_filler():
    assert turn_gate._ASSENT_FILLERS <= turn_gate._FILLERS


@pytest.mark.parametrize(
    ("text", "p", "expected"),
    [
        ("hmm", 0.9, Verdict.DROP),
        ("", None, Verdict.DROP),
        ("আমার বাজেট ৫০ লাখ", 0.85, Verdict.ACCEPT),
        # Drop bar 0.35: the bench's lowest real turn is 0.39 ("What are your
        # office hours?"); people nearby in run_53 scored 0.25-0.30.
        ("What are your office hours?", 0.39, Verdict.ACCEPT),
        ("আমার বাজেট ৫০ লাখ", 0.35, Verdict.ACCEPT),
        ("Hi, Deep", 0.28, Verdict.DROP),
        ("Rahim Uddin", 0.24, Verdict.DROP),
        ("তুমি কি চা খাবে?", 0.06, Verdict.DROP),
        ("বাংলাদেশের ক্রিকেট টিম সম্পর্কে বলুন", 0.03, Verdict.DROP),
        ("Do you have parking?", None, Verdict.ACCEPT),
    ],
)
def test_decide_by_judge_score(text, p, expected):
    assert _decide(text, p) is expected


@pytest.mark.parametrize("confidence", [0.9, 0.2, 0.0])
def test_judge_failure_accepts(confidence):
    assert _decide("Do you have parking?", None, confidence=confidence) is Verdict.ACCEPT


_HINDI = "कल सुबह हम बाज़ार चलेंगे।"


def test_other_language_line_once_then_silent():
    state = GateState()
    assert _decide(_HINDI, None, state=state) is Verdict.OTHER_LANGUAGE
    state.record(Verdict.OTHER_LANGUAGE, _NOW)
    # not again until the agent has replied to something, and not within the cooldown
    assert _decide(_HINDI, None, state=state, now=_NOW + 1000) is Verdict.DROP
    state.record(Verdict.ACCEPT, _NOW + 10)
    assert _decide(_HINDI, None, state=state, now=_NOW + 20) is Verdict.DROP
    assert _decide(_HINDI, None, state=state, now=_NOW + 200) is Verdict.OTHER_LANGUAGE


@pytest.mark.parametrize(
    ("text", "confidence"),
    [("बेटा", 0.9), ("कल सुबह हम बाज़ार चलेंगे।", 0.2)],
)
def test_other_language_short_or_unsure_is_silent(text, confidence):
    assert _decide(text, None, confidence=confidence) is Verdict.DROP


def test_other_language_with_unknown_confidence_still_gets_the_line():
    assert _decide(_HINDI, None, confidence=0.0) is Verdict.OTHER_LANGUAGE


def test_other_script_from_an_stt_that_cannot_write_bengali_goes_to_the_judge():
    pre = precheck("आमार बाजेट पचास लाख", 0.5)
    assert turn_gate.needs_judge(pre, stt_writes_bengali=False)
    assert not turn_gate.needs_judge(pre, stt_writes_bengali=True)
    assert _decide("आमार बाजेट पचास लाख", 0.6, bengali=False) is Verdict.ACCEPT
    assert _decide("आमार बाजेट पचास लाख", 0.1, bengali=False) is Verdict.DROP


def test_needs_judge_skips_settled_turns():
    assert not turn_gate.needs_judge(precheck("hmm", 0.9), stt_writes_bengali=True)
    assert turn_gate.needs_judge(precheck("Is parking included?", 0.9), stt_writes_bengali=True)


def test_thresholds_are_configurable():
    th = Thresholds(drop_p=0.5)
    pre = precheck("Is parking included?", 0.9)
    v = decide(pre, 0.45, stt_writes_bengali=True, state=GateState(), now=_NOW, th=th)
    assert v is Verdict.DROP


@pytest.mark.parametrize(
    "text",
    [
        "ঠিক আছে Tata bye bye",
        "That's all for now",
        "Thanks, bye!",
        "Thanks for the help",
        "No, I do not need any more help",
        "ঠিক আছে, ধন্যবাদ",
        "না, আর কিছু লাগবে না",
        "আল্লাহ হাফেজ",
        "ঠিক আছে, টা টা",
        "ওকে বাই বাই",
        "আচ্ছা, আসি তাহলে",
        "ঠিক আছে, রাখি তাহলে",
        "আচ্ছা ভালো থাকবেন",
        "accha ashi tahole",
        "ok bhalo thakben",
        "thik ache, pore kotha hobe",
    ],
)
def test_goodbyes_are_accepted_without_the_judge(text):
    # Jev scored "ঠিক আছে Tata bye bye" 0.24: the agent never heard the goodbye.
    pre = precheck(text, 0.9)
    assert not turn_gate.needs_judge(pre, stt_writes_bengali=True)
    assert decide(pre, 0.1, stt_writes_bengali=True, state=GateState(), now=0.0) is Verdict.ACCEPT


@pytest.mark.parametrize(
    "text",
    [
        "Is parking included?",
        "বাজেট পঞ্চাশ লাখ",
        # Sign-off words inside a request aren't goodbyes.
        "বাজেট পঞ্চাশ লাখ রাখছি",
        "ফ্ল্যাটটা দেখতে কাল আসি?",
        "flat ta koto taka?",
        # Long turns are the judge's call, thanks or not.
        "I want something nearby, thanks, and also with parking and a lift please",
    ],
)
def test_other_turns_are_not_goodbyes(text):
    assert not turn_gate.is_closing(text)


def test_mixed_loanwords_classified_as_bengali():
    assert turn_gate.classify_script("জি, এহ booking টি confirm করুন।") == "bn"
    assert turn_gate.classify_script("এই flat টি visit করতে চাই") == "bn"


def test_phone_numbers_not_dropped_as_filler():
    pre = precheck("017909090", 0.9)
    assert not pre.filler
    assert pre.script == "bn"
    assert pre.word_count >= 1
    # If Jev scores 0.46 (above drop_p 0.35), it must be accepted!
    v = decide(pre, 0.46, stt_writes_bengali=True, state=GateState(), now=0.0)
    assert v is Verdict.ACCEPT



@pytest.mark.parametrize("text", ["910242", "৯১০২৪২", "কোডটি হলো 910242", "code is 4821"])
def test_a_code_read_out_is_always_accepted(text):
    # run_53: "Nine one zero two four two" arrived as "910242" and was dropped.
    pre = precheck(text, None)
    assert pre.code and not pre.filler and pre.script != "none"
    assert turn_gate.needs_judge(pre, stt_writes_bengali=True)
    for p in (None, 0.1, 0.73):
        assert decide(pre, p, stt_writes_bengali=True, state=GateState(), now=0.0) is Verdict.ACCEPT


@pytest.mark.parametrize("text", ["আমার 3 জিবি লাগবে", "১০০ টাকা", "123"])
def test_short_numbers_are_no_code(text):
    assert not turn_gate.has_code(text)


def test_gb_misheard_after_a_number_is_mended():
    # run_27: the STT wrote জিবি (GB) as জীবিত ("alive").
    assert turn_gate.clean_transcript("দুই জীবিতটা দেখান") == "দুই জিবিরটা দেখান"
    assert turn_gate.clean_transcript("৫ জীবি প্যাক আছে?") == "৫ জিবি প্যাক আছে?"
    # Not after a number, it is the word itself.
    assert turn_gate.clean_transcript("সবাই জীবিত আছে") == "সবাই জীবিত আছে"
