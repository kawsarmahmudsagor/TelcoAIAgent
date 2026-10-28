"""The conversation eval sets under scripts/ stay valid against the agent's schema."""

import json
from pathlib import Path

import pytest

from app.agent import turn_router
from app.agent.tools.registry import telco_tools
from word_checks import real_estate_words

_BENCH = Path(__file__).resolve().parents[2] / "scripts"
_ROUTER = _BENCH / "router_bench" / "cases.json"
_JUDGE = _BENCH / "judge_bench" / "cases.json"

_LOOKUPS = {"packages", "knowledge_base", "care_centre", "none"}
_PACKAGE_KEYS = set(turn_router._SCHEMA["properties"]["packages"]["properties"])
_TOOLS = {t.info.name for t in telco_tools()} | {"search_knowledge_base"}


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_router_cases_are_valid():
    data = _load(_ROUTER)
    cases = data["cases"]
    assert len(cases) >= 25
    assert len({c["id"] for c in cases}) == len(cases)
    for c in cases:
        assert c["h"] in data["histories"], c["id"]
        assert c["lookup"] in _LOOKUPS, c["id"]
        assert set(c.get("packages", {})) <= _PACKAGE_KEYS, c["id"]
        assert c["expected_tool"] is None or c["expected_tool"] in _TOOLS, c["id"]
        if c["lookup"] == "packages":
            assert "packages" in c, c["id"]


def test_router_cases_cover_languages_and_tools():
    cases = _load(_ROUTER)["cases"]
    by_lang = {lang: sum(c["lang"] == lang for c in cases) for lang in ("bn", "en", "bi")}
    assert by_lang["bn"] >= 8 and by_lang["en"] >= 8 and by_lang["bi"] >= 6
    assert sum(by_lang.values()) == len(cases)
    covered = {c["expected_tool"] for c in cases}
    assert (_TOOLS - covered) == set(), f"tools without a case: {_TOOLS - covered}"
    assert {c["lookup"] for c in cases} == _LOOKUPS


@pytest.mark.parametrize("path", [_ROUTER, _JUDGE], ids=["router", "judge"])
def test_cases_have_no_real_estate_words(path):
    assert real_estate_words(path.read_text(encoding="utf-8")) == []


def test_judge_cases_reference_known_histories():
    data = _load(_JUDGE)
    assert len(data["cases"]) > 0
    for c in data["cases"]:
        assert c["h"] in data["histories"], c["id"]
        assert c["expected"] in {"addressed", "not_addressed"}, c["id"]
