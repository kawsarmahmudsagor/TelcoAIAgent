"""Amounts named in speech-to-text's many spellings (app.agent.spoken_numbers)."""

import pytest

from app.agent.spoken_numbers import named_amounts


@pytest.mark.parametrize(
    ("heard", "expected"),
    [
        # From a call: the cards showed every data package.
        ("একটা প্যাকেজ দেখতে পাচ্ছি থ্রি জিবি উইকএন্ড উনসত্তর টাকা।", {("data_mb", 3072), ("price", 69)}),
        ("৩ জিবির প্যাকেজ", {("data_mb", 3072)}),
        ("3GB pack", {("data_mb", 3072)}),
        ("তিন জিবি", {("data_mb", 3072)}),
        ("পনেরো জিবি", {("data_mb", 15360)}),
        ("পনের জিবি", {("data_mb", 15360)}),
        ("একশো নয় টাকার", {("price", 109)}),
        ("একশত নয় টাকার", {("price", 109)}),
        ("দুশো মিনিট", {("minutes", 200)}),
        ("one hundred and nine taka", {("price", 109)}),
        ("five hundred sms", {("sms", 500)}),
        ("৫০০ এমবি", {("data_mb", 500)}),
        ("সাত দিনের প্যাকেজ", {("validity_days", 7)}),
    ],
)
def test_amounts_in_every_spelling(heard, expected):
    assert named_amounts(heard) == expected


@pytest.mark.parametrize("heard", ["আমি একটা প্যাকেজ চাই", "এক বা দুইটা", "", "data pack please"])
def test_a_number_without_a_unit_is_no_amount(heard):
    assert named_amounts(heard) == set()
