from app.agent import reply_language


def test_parse():
    assert reply_language.parse("en") == "en"
    assert reply_language.parse("bn") == "bn"
    for raw in ("EN", "fr", ["en"], None, ""):
        assert reply_language.parse(raw) is None, raw


def test_in_language():
    assert reply_language.in_language("en", "X") == "in English"
    assert reply_language.in_language("bn", "X") == "in Bangla (Bengali script)"
    assert reply_language.in_language(None, "X") == "X"


def test_fixed_reads_userdata():
    class U:
        reply_language = "en"

    assert reply_language.fixed(U()) == "en"
    assert reply_language.fixed(object()) is None
