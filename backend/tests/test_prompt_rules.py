import pytest

from app.agent import idle_checkin, prompt_rules, quick_reply

_SHARED = {
    "PACKAGE_WORD": prompt_rules.PACKAGE_WORD,
    "BANGLA_WORDS": prompt_rules.BANGLA_WORDS,
    "BRAND": prompt_rules.BRAND,
}


@pytest.mark.parametrize("name", sorted(_SHARED))
def test_shared_rules_have_no_braces(name):
    # They are inserted into str.format templates (the dashboard prompt), where
    # a lone brace breaks rendering.
    assert "{" not in _SHARED[name] and "}" not in _SHARED[name]


@pytest.mark.parametrize(
    "prompt",
    [quick_reply._FILLER_SYSTEM, quick_reply._CARE_FILLER_SYSTEM, idle_checkin._CHECK_IN_SYSTEM],
    ids=["filler", "care_filler", "check_in"],
)
def test_every_quick_prompt_uses_the_shared_package_rule(prompt):
    assert prompt_rules.PACKAGE_WORD in prompt


def test_care_filler_states_the_brand_once():
    assert quick_reply._CARE_FILLER_SYSTEM.count(prompt_rules.BRAND) == 1
