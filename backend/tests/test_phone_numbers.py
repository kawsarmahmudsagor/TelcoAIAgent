import pytest
from reserved_phone import delete_clients, unused_test_phone
from sqlalchemy import text

from app.config import get_settings
from app.db.session import SessionLocal
from app.repositories import client_repo
from app.services.phone_numbers import (
    bd_mobile_local,
    dial_allowlist,
    is_dial_allowed,
    normalize_bd_mobile,
    normalize_e164,
    spoken_digits_in_text,
)


@pytest.mark.parametrize(
    "raw",
    ["+880-1711-234567", "+8801711234567", "01711234567", "01711 234 567", "8801711234567"],
)
def test_bangladeshi_formats_normalize_to_e164(raw):
    assert normalize_e164(raw) == "+8801711234567"


def test_foreign_number_keeps_its_country():
    assert normalize_e164("+1 415 555 2671") == "+14155552671"


@pytest.mark.parametrize("raw", ["", "hello", "123", "+880-1711"])
def test_invalid_numbers_rejected(raw):
    with pytest.raises(ValueError):
        normalize_e164(raw)


@pytest.mark.parametrize(
    "raw",
    [
        "zero one seven triple zero triple zero nine eight",
        "zero one seven, double zero zero, zero zero zero, nine eight",
        "oh one seven 000 000 98",
        "শূন্য এক সাত ট্রিপল শূন্য ট্রিপল শূন্য নয় আট",
        "shunno ek shat tripple shunno tripple shunno noy aat",
    ],
)
def test_spoken_digits_normalize(raw):
    # Speech-to-text writes a spoken number as words.
    assert normalize_bd_mobile(raw) == "+8801700000098"


@pytest.mark.parametrize("raw", ["zero one seven", "zero one seven triple banana nine eight"])
def test_spoken_digits_still_validated(raw):
    with pytest.raises(ValueError):
        normalize_bd_mobile(raw)


@pytest.mark.parametrize(
    ("heard", "expected"),
    [
        # From call logs: the LLM wrote these as 0170011398 and 0170000028.
        (
            "আমার নাম হলো Test User আর phone number zero one seven zero one double zero one "
            "three nine eight",
            "আমার নাম হলো Test User আর phone number 01701001398",
        ),
        (
            "হ্যাঁ, আমার ফোন নাম্বার হলো zero one seven triple zero triple zero two eight",
            "হ্যাঁ, আমার ফোন নাম্বার হলো 01700000028",
        ),
        ("zero one seven triple zero triple zero two eight.", "01700000028."),
        ("নম্বর শূন্য এক সাত ট্রিপল শূন্য ট্রিপল শূন্য নয় আট, ঠিক আছে?", "নম্বর 01700000098, ঠিক আছে?"),
        ("zero one seven, double zero zero, zero zero zero, nine eight", "01700000098"),
        ("oh one seven 000 000 98", "01700000098"),
        # A sentence end closes the run: the "two" isn't part of the number.
        (
            "I need two. zero one seven zero one double zero one three nine eight",
            "I need two. 01701001398",
        ),
    ],
)
def test_spoken_digits_in_text_become_digits(heard, expected):
    assert spoken_digits_in_text(heard) == expected


@pytest.mark.parametrize(
    "heard",
    [
        "I want one bedroom, maybe two",
        "আমি এক বা দুই বেডরুমের ফ্ল্যাট চাই",
        "double room with a triple window",
        "call me at seven",
        "budget twenty five thousand",
        "",
    ],
)
def test_text_without_a_spoken_number_is_left_alone(heard):
    assert spoken_digits_in_text(heard) == heard


def _settings(allowlist: str):
    return get_settings().model_copy(update={"sip_dial_allowlist": allowlist})


def test_allowlist_entries_normalized_before_matching():
    settings = _settings("01711234567, +1 415 555 2671")
    assert dial_allowlist(settings) == {"+8801711234567", "+14155552671"}
    assert is_dial_allowed("+8801711234567", settings)


def test_empty_allowlist_allows_nothing():
    assert not is_dial_allowed("+8801711234567", _settings(""))


def test_invalid_allowlist_entry_ignored():
    settings = _settings("not-a-number,01711234567")
    assert dial_allowlist(settings) == {"+8801711234567"}
    assert not is_dial_allowed("+8801922345678", settings)


# ---- normalize_bd_mobile / client lookup by phone ----


@pytest.mark.parametrize(
    "raw",
    [
        "+8801711234567",
        "+880 1711-234567",
        "8801711234567",
        "01711234567",
        "01711-234567",
        "(+880) 1711 234567",
        "০১৭১১২৩৪৫৬৭",
        "+৮৮০ ১৭১১-২৩৪৫৬৭",
    ],
)
def test_bd_mobile_forms_normalize_to_e164(raw):
    assert normalize_bd_mobile(raw) == "+8801711234567"


@pytest.mark.parametrize(
    "raw",
    ["", None, "hello", "0171123", "017112345678", "+1 415 555 2671", "02-9123456"],
)
def test_non_bd_mobiles_rejected(raw):
    with pytest.raises(ValueError):
        normalize_bd_mobile(raw)


def test_local_form():
    assert bd_mobile_local("+8801711234567") == "01711234567"


def _stored_variants(local: str) -> list[str]:
    """`local` ("0139999xxxx") the ways a phone ends up stored."""
    tail = local[1:]
    return [f"{local[:5]}-{local[5:]}", f"(+880) {tail[:4]} {tail[4:]}", f"880{tail}"]


@pytest.mark.parametrize("variant", range(3))
def test_find_by_phone_matches_raw_stored_formats(variant):
    local = unused_test_phone()
    stored = _stored_variants(local)[variant]
    db = SessionLocal()
    created = []
    try:
        client = client_repo.create(db, {"full_name": "Pytest Phone", "phone": stored})
        created.append(client.id)
        found = client_repo.find_by_phone(db, normalize_bd_mobile(local))
        assert found is not None and found.id == client.id
    finally:
        db.close()
        delete_clients(created)


def test_find_by_phone_prefers_the_latest_duplicate_and_keeps_its_name():
    local = unused_test_phone()
    e164 = normalize_bd_mobile(local)
    db = SessionLocal()
    created = []
    try:
        older = client_repo.create(db, {"full_name": "Pytest Old", "phone": local})
        created.append(older.id)
        newer = client_repo.create(db, {"full_name": "Pytest New", "phone": e164})
        created.append(newer.id)
        db.execute(
            text("update clients set updated_at = now() - interval '1 day' where id = :id"),
            {"id": older.id},
        )
        db.commit()
        assert client_repo.find_by_phone(db, e164).id == newer.id

        same = client_repo.get_or_create_by_phone(db, full_name="Someone Else", phone=e164)
        assert same.id == newer.id
        assert same.full_name == "Pytest New"
    finally:
        db.close()
        delete_clients(created)


def test_get_or_create_by_phone_creates_with_e164():
    e164 = normalize_bd_mobile(unused_test_phone())
    db = SessionLocal()
    created = []
    try:
        client = client_repo.get_or_create_by_phone(db, full_name="Pytest Phone", phone=e164)
        created.append(client.id)
        assert client.phone == e164
        assert client.email is None
    finally:
        db.close()
        delete_clients(created)
